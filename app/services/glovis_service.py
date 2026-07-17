"""Validated provider operations for the DB Auto Glovis API."""

from __future__ import annotations

import base64
import binascii
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timezone
import re
import threading
import time
from typing import Any, Callable, TypeVar
from urllib.parse import urlsplit

from pydantic import BaseModel, ValidationError

from app.models.glovis import (
    GlovisAuction,
    GlovisAuctionsResponse,
    GlovisCar,
    GlovisCarDetail,
    GlovisCarDetailResponse,
    GlovisCarsQuery,
    GlovisCarsResponse,
    GlovisFilterItemsResponse,
    GlovisFilterOptionsResponse,
    GlovisDetailHealthResponse,
    GlovisHealthResponse,
    GlovisOption,
    GlovisSearchForm,
)
from app.services.glovis_transport import (
    GlovisTransport,
    GlovisUpstreamInvalidResponseError,
    GlovisUpstreamUnavailableError,
    OVERALL_DEADLINE_SECONDS,
)


AUCTIONS_PATH = "/api/auctions/glovis/auctions"
CARS_PATH = "/api/auctions/glovis/cars"
BRANDS_PATH = "/api/auctions/glovis/brands"
MODELS_PATH = "/api/auctions/glovis/models"
SUBMODELS_PATH = "/api/auctions/glovis/submodels"
SEARCH_FORM_PATH = "/api/auctions/glovis/search-form"
DETAIL_PATH = "/api/auctions/glovis/car"

AUCTIONS_TTL = 30.0
CARS_TTL = 30.0
METADATA_TTL = 120.0
DETAIL_TTL = 300.0
HEALTH_TTL = 30.0
DETAIL_HEALTH_TTL = 300.0
CACHE_MAX_ENTRIES = 512

PROVIDER_ID_RE = re.compile(r"^[0-9]{1,12}$", re.ASCII)
_ISO_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", re.ASCII)
_INTERNAL_EGRESS_RE = re.compile(
    r"^kr-[a-z0-9]{1,12}(?:-[a-z0-9]{1,12}){0,2}$",
    re.ASCII,
)
_BESTPROXY_EGRESS_RE = re.compile(
    r"^bestproxy-kr-([a-z0-9]{1,12}(?:-[a-z0-9]{1,12})?)$",
    re.ASCII,
)
_SEARCH_FORM_FIELDS = (
    "colors",
    "options",
    "lanes",
    "transmissions",
    "fuels",
    "insurance_damage",
    "usage_history",
    "accident_history",
    "sort_orders",
    "rooms",
    "bid_statuses",
)
_SEARCH_FORM_ALIASES = {
    "fuels": "fuel_types",
}
_DETAIL_MAPPING_FIELDS = (
    "properties",
    "performance",
    "total_table",
    "summary_table",
    "inspection_record",
)
_DETAIL_OPTIONAL_MAPPING_FIELDS = (
    "legal_status",
    "insurance_history",
)
_VEHICLE_FACT_FIELDS = (
    "lane",
    "room",
    "plate_number",
    "vin",
    "year",
    "mileage",
    "displacement",
    "fuel_type",
    "transmission",
    "color",
    "vehicle_type",
    "brand_code",
    "brand",
    "model_code",
    "model",
    "submodel_code",
    "submodel",
    "configuration",
    "first_registration_date",
    "registration_date",
    "rating",
    "status",
)
_PRICE_FIELDS = ("start_price", "sold_price", "hope_price")

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True)
class _CacheEntry:
    value: Any
    expires_at: float


class GlovisCarUnavailableError(RuntimeError):
    code = "car_unavailable"
    retryable = False


def validate_provider_id(value: str, name: str) -> str:
    if not PROVIDER_ID_RE.fullmatch(value or ""):
        raise ValueError(f"{name} must contain 1 to 12 ASCII digits")
    return value


def validate_gn(value: str) -> str:
    if not value or len(value) > 128:
        raise ValueError("gn must be canonical base64")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("gn must be canonical base64") from None
    if not decoded or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError("gn must be canonical base64")
    return value


def _invalid_response() -> GlovisUpstreamInvalidResponseError:
    return GlovisUpstreamInvalidResponseError()


def _is_str(value: Any) -> bool:
    return type(value) is str


def _require_nonempty_string(value: Any) -> str:
    if not _is_str(value) or not value.strip():
        raise _invalid_response()
    return value


def _require_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _invalid_response()
    return value


def _require_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise _invalid_response()
    return value


def _validate_https_image(value: Any) -> str:
    if not _is_str(value):
        raise _invalid_response()
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError:
        raise _invalid_response() from None
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise _invalid_response()
    return value


def _validate_model(model_type: type[ModelT], value: Any) -> ModelT:
    try:
        return model_type.model_validate(value)
    except (TypeError, ValueError, ValidationError):
        raise _invalid_response() from None


def _validated_provider_id(value: Any, name: str) -> str:
    if not _is_str(value):
        raise _invalid_response()
    try:
        return validate_provider_id(value, name)
    except ValueError:
        raise _invalid_response() from None


def _validated_gn(value: Any) -> str:
    if not _is_str(value):
        raise _invalid_response()
    try:
        return validate_gn(value)
    except ValueError:
        raise _invalid_response() from None


def _safe_egress(value: Any) -> str:
    if not _is_str(value):
        return "unknown"
    if _INTERNAL_EGRESS_RE.fullmatch(value):
        return value
    configured = _BESTPROXY_EGRESS_RE.fullmatch(value)
    if configured:
        return f"kr-bestproxy-{configured.group(1)}"
    return "unknown"


def _is_substantive(value: Any) -> bool:
    if value is None:
        return False
    if _is_str(value):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_is_substantive(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_is_substantive(item) for item in value)
    return True


def _main_has_non_placeholder_data(main: dict[str, Any]) -> bool:
    identity_fields = {"gn", "rc", "acc", "atn", "lot_number"}
    for name, value in main.items():
        if name in identity_fields:
            if value is None or _is_str(value) or not _is_substantive(value):
                continue
            return True
        if name == "title" and not _is_substantive(value):
            continue
        if _is_substantive(value):
            return True
    return False


def _is_unavailable_detail(payload: dict[str, Any]) -> bool:
    if not payload:
        return True

    raw_main = payload.get("main")
    other_sections = {name: value for name, value in payload.items() if name != "main"}
    if not isinstance(raw_main, dict):
        return not _is_substantive(raw_main) and not _is_substantive(other_sections)
    if not raw_main:
        return not _is_substantive(other_sections)

    title = raw_main.get("title")
    return not _is_substantive(title) and not _main_has_non_placeholder_data(raw_main)


class GlovisService:
    """Normalize and semantically validate DB Auto provider payloads."""

    def __init__(
        self,
        *,
        transport: GlovisTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._transport = transport if transport is not None else GlovisTransport()
        self._clock = clock
        self._cache: OrderedDict[tuple[Any, ...], _CacheEntry] = OrderedDict()
        self._cache_lock = threading.RLock()
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_evictions = 0
        self._cache_generation = 0
        self._closed = False

    def _cached(
        self,
        key: tuple[Any, ...],
        ttl: float,
        loader: Callable[[], Any],
    ) -> Any:
        now = self._clock()
        with self._cache_lock:
            if self._closed:
                raise GlovisUpstreamUnavailableError()
            generation = self._cache_generation
            entry = self._cache.get(key)
            if entry is not None and entry.expires_at > now:
                self._cache.move_to_end(key)
                self._cache_hits += 1
                return entry.value
            if entry is not None:
                del self._cache[key]
            self._cache_misses += 1

        value = loader()

        with self._cache_lock:
            if self._closed or generation != self._cache_generation:
                return value
            self._cache[key] = _CacheEntry(
                value=value,
                expires_at=self._clock() + ttl,
            )
            self._cache.move_to_end(key)
            while len(self._cache) > CACHE_MAX_ENTRIES:
                self._cache.popitem(last=False)
                self._cache_evictions += 1
        return value

    def get_cache_stats(self) -> dict[str, int]:
        with self._cache_lock:
            return {
                "size": len(self._cache),
                "max_entries": CACHE_MAX_ENTRIES,
                "hits": self._cache_hits,
                "misses": self._cache_misses,
                "evictions": self._cache_evictions,
            }

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache_generation += 1
            self._cache.clear()

    def _load_auctions(
        self,
        deadline_at: float | None = None,
    ) -> tuple[GlovisAuctionsResponse, str]:
        result = self._transport.get_json(
            AUCTIONS_PATH,
            [("lang", "en")],
            operation="auctions",
            deadline_at=deadline_at,
        )
        payload = _require_list(result.value)
        seen: set[tuple[str, str]] = set()
        auctions: list[GlovisAuction] = []
        for raw_item in payload:
            item = _require_mapping(raw_item)
            raw_number = item.get("number")
            legacy_atn = item.get("atn")
            if raw_number is None:
                raw_number = legacy_atn
            elif legacy_atn is not None and legacy_atn != raw_number:
                raise _invalid_response()
            number = _validated_provider_id(raw_number, "number")
            acc = _validated_provider_id(item.get("acc"), "acc")
            identity = (number, acc)
            if identity in seen:
                raise _invalid_response()
            seen.add(identity)
            title = _require_nonempty_string(item.get("title"))
            raw_date = item.get("date")
            if not _is_str(raw_date) or not _ISO_DATE_RE.fullmatch(raw_date):
                raise _invalid_response()
            try:
                auction_date = date.fromisoformat(raw_date)
            except ValueError:
                raise _invalid_response() from None
            auctions.append(
                GlovisAuction(
                    number=number,
                    acc=acc,
                    title=title,
                    date=auction_date,
                )
            )
        auctions.sort(key=lambda auction: (auction.date, auction.number))
        return GlovisAuctionsResponse(auctions=auctions), result.egress

    def get_auctions(self) -> GlovisAuctionsResponse:
        value, _ = self._cached(
            ("auctions", ("lang", "en")),
            AUCTIONS_TTL,
            self._load_auctions,
        )
        return value

    def _validate_query_ids(self, query: GlovisCarsQuery) -> None:
        validate_provider_id(query.atn, "atn")
        validate_provider_id(query.acc, "acc")
        for name in ("brand", "model", "submodel"):
            value = getattr(query, name)
            if value is not None:
                validate_provider_id(value, name)

    def _normalize_car_item(
        self,
        raw_item: Any,
        *,
        expected_atn: str,
        expected_acc: str,
    ) -> GlovisCar:
        item = _require_mapping(raw_item)
        gn = _validated_gn(item.get("gn"))
        rc = _validated_provider_id(item.get("rc"), "rc")
        atn = _validated_provider_id(item.get("atn"), "atn")
        acc = _validated_provider_id(item.get("acc"), "acc")
        if atn != expected_atn or acc != expected_acc:
            raise _invalid_response()
        _require_nonempty_string(item.get("title"))
        _require_nonempty_string(item.get("lot_number"))
        thumbnail = item.get("thumbnail")
        if thumbnail is not None:
            _validate_https_image(thumbnail)
        car = _validate_model(GlovisCar, item)
        if car.gn != gn or car.rc != rc:
            raise _invalid_response()
        return car

    def _load_cars(
        self,
        query: GlovisCarsQuery,
        deadline_at: float | None = None,
    ) -> tuple[GlovisCarsResponse, str]:
        self._validate_query_ids(query)
        result = self._transport.get_json(
            CARS_PATH,
            query.upstream_params(),
            operation="cars",
            deadline_at=deadline_at,
        )
        payload = _require_mapping(result.value)
        total = payload.get("total")
        if type(total) is not int or total < 0:
            raise _invalid_response()
        raw_items = _require_list(payload.get("items"))
        if len(raw_items) > query.page_size or len(raw_items) > total:
            raise _invalid_response()
        seen: set[tuple[str, str]] = set()
        items: list[GlovisCar] = []
        for raw_item in raw_items:
            item = self._normalize_car_item(
                raw_item,
                expected_atn=query.atn,
                expected_acc=query.acc,
            )
            identity = (item.gn, item.rc)
            if identity in seen:
                raise _invalid_response()
            seen.add(identity)
            items.append(item)
        response = GlovisCarsResponse(
            total=total,
            items=items,
            page=query.page,
            page_size=query.page_size,
            atn=query.atn,
            acc=query.acc,
        )
        return response, result.egress

    def get_cars(self, query: GlovisCarsQuery) -> GlovisCarsResponse:
        self._validate_query_ids(query)
        params = query.upstream_params()
        value, _ = self._cached(
            ("cars", *params),
            CARS_TTL,
            lambda: self._load_cars(query),
        )
        return value

    @staticmethod
    def _normalize_options(payload: Any) -> list[GlovisOption]:
        raw_items = _require_list(payload)
        items: list[GlovisOption] = []
        seen: set[str] = set()
        for raw_item in raw_items:
            item = _require_mapping(raw_item)
            value = _require_nonempty_string(item.get("value"))
            label = _require_nonempty_string(item.get("label"))
            count = item.get("count", 0)
            if count is None:
                count = 0
            if type(count) is not int or count < 0 or value in seen:
                raise _invalid_response()
            seen.add(value)
            items.append(GlovisOption(value=value, label=label, count=count))
        return items

    def _load_metadata(
        self,
        *,
        path: str,
        params: list[tuple[str, str]],
        operation: str,
        deadline_at: float | None = None,
    ) -> tuple[GlovisFilterItemsResponse, str]:
        result = self._transport.get_json(
            path,
            params,
            operation=operation,
            deadline_at=deadline_at,
        )
        return (
            GlovisFilterItemsResponse(items=self._normalize_options(result.value)),
            result.egress,
        )

    def get_brands(self, *, atn: str, acc: str) -> GlovisFilterItemsResponse:
        validate_provider_id(atn, "atn")
        validate_provider_id(acc, "acc")
        params = [("atn", atn), ("acc", acc), ("lang", "en")]
        value, _ = self._cached(
            ("brands", *params),
            METADATA_TTL,
            lambda: self._load_metadata(
                path=BRANDS_PATH,
                params=params,
                operation="brands",
            ),
        )
        return value

    def get_models(
        self,
        *,
        brand: str,
        atn: str,
        acc: str,
    ) -> GlovisFilterItemsResponse:
        validate_provider_id(brand, "brand")
        validate_provider_id(atn, "atn")
        validate_provider_id(acc, "acc")
        params = [
            ("brand", brand),
            ("atn", atn),
            ("acc", acc),
            ("lang", "en"),
        ]
        value, _ = self._cached(
            ("models", *params),
            METADATA_TTL,
            lambda: self._load_metadata(
                path=MODELS_PATH,
                params=params,
                operation="models",
            ),
        )
        return value

    def get_submodels(
        self,
        *,
        brand: str,
        model: str,
        atn: str,
        acc: str,
    ) -> GlovisFilterItemsResponse:
        validate_provider_id(brand, "brand")
        validate_provider_id(model, "model")
        validate_provider_id(atn, "atn")
        validate_provider_id(acc, "acc")
        params = [
            ("brand", brand),
            ("model", model),
            ("atn", atn),
            ("acc", acc),
            ("lang", "en"),
        ]
        value, _ = self._cached(
            ("submodels", *params),
            METADATA_TTL,
            lambda: self._load_metadata(
                path=SUBMODELS_PATH,
                params=params,
                operation="submodels",
            ),
        )
        return value

    def _load_filter_options(
        self,
        *,
        atn: str,
        acc: str,
        deadline_at: float | None = None,
    ) -> tuple[GlovisFilterOptionsResponse, str]:
        result = self._transport.get_json(
            SEARCH_FORM_PATH,
            [("atn", atn), ("acc", acc), ("lang", "en")],
            operation="filter_options",
            deadline_at=deadline_at,
        )
        payload = _require_mapping(result.value)
        normalized: dict[str, list[GlovisOption]] = {}
        for name in _SEARCH_FORM_FIELDS:
            provider_name = (
                name
                if name in payload
                else _SEARCH_FORM_ALIASES.get(name)
            )
            if provider_name is None or provider_name not in payload:
                raise _invalid_response()
            normalized[name] = self._normalize_options(payload[provider_name])
        return (
            GlovisFilterOptionsResponse(filters=GlovisSearchForm(**normalized)),
            result.egress,
        )

    def get_filter_options(
        self,
        *,
        atn: str,
        acc: str,
    ) -> GlovisFilterOptionsResponse:
        validate_provider_id(atn, "atn")
        validate_provider_id(acc, "acc")
        params = [("atn", atn), ("acc", acc), ("lang", "en")]
        value, _ = self._cached(
            ("filter_options", *params),
            METADATA_TTL,
            lambda: self._load_filter_options(atn=atn, acc=acc),
        )
        return value

    @staticmethod
    def _validate_detail_shapes(payload: dict[str, Any]) -> None:
        for name in _DETAIL_MAPPING_FIELDS:
            if name in payload:
                _require_mapping(payload[name])
        for name in _DETAIL_OPTIONAL_MAPPING_FIELDS:
            if name in payload and payload[name] is not None:
                _require_mapping(payload[name])

        if "options" in payload:
            for raw_option in _require_list(payload["options"]):
                option = _require_mapping(raw_option)
                _require_nonempty_string(option.get("name"))
                if type(option.get("enabled")) is not bool:
                    raise _invalid_response()

        if "accident_records" in payload:
            for raw_record in _require_list(payload["accident_records"]):
                _require_mapping(raw_record)

        for name in ("images", "inspection_images"):
            if name in payload:
                for image in _require_list(payload[name]):
                    _validate_https_image(image)
        for name in ("performance_image", "registration_certificate_image"):
            image = payload.get(name)
            if image is not None:
                _validate_https_image(image)

    @staticmethod
    def _has_detail_substance(payload: dict[str, Any]) -> bool:
        main = payload["main"]
        has_vehicle_fact = any(
            _is_substantive(main.get(name)) for name in _VEHICLE_FACT_FIELDS
        )
        has_price = any(_is_substantive(main.get(name)) for name in _PRICE_FIELDS)
        has_gallery = any(
            _is_substantive(payload.get(name))
            for name in ("images", "inspection_images")
        )
        return bool(
            has_vehicle_fact
            or has_price
            or has_gallery
            or _is_substantive(payload.get("performance_image"))
            or _is_substantive(payload.get("registration_certificate_image"))
        )

    def _load_car_detail(
        self,
        *,
        gn: str,
        rc: str,
        acc: str,
        atn: str,
        deadline_at: float | None = None,
    ) -> tuple[GlovisCarDetailResponse, str]:
        result = self._transport.get_json(
            DETAIL_PATH,
            [
                ("gn", gn),
                ("rc", rc),
                ("acc", acc),
                ("atn", atn),
                ("lang", "en"),
            ],
            operation="car_detail",
            deadline_at=deadline_at,
        )
        payload = _require_mapping(result.value)
        if _is_unavailable_detail(payload):
            raise GlovisCarUnavailableError()
        main = _require_mapping(payload.get("main"))
        identities = {
            "gn": _validated_gn(main.get("gn")),
            "rc": _validated_provider_id(main.get("rc"), "rc"),
            "acc": _validated_provider_id(main.get("acc"), "acc"),
            "atn": _validated_provider_id(main.get("atn"), "atn"),
        }
        if identities != {"gn": gn, "rc": rc, "acc": acc, "atn": atn}:
            raise _invalid_response()
        title = main.get("title")
        if not _is_str(title) or not title.strip():
            raise _invalid_response()
        self._validate_detail_shapes(payload)
        if not self._has_detail_substance(payload):
            raise GlovisCarUnavailableError()
        detail = _validate_model(GlovisCarDetail, payload)
        return GlovisCarDetailResponse(data=detail), result.egress

    def get_car_detail(
        self,
        *,
        gn: str,
        rc: str,
        acc: str,
        atn: str,
    ) -> GlovisCarDetailResponse:
        validate_gn(gn)
        validate_provider_id(rc, "rc")
        validate_provider_id(acc, "acc")
        validate_provider_id(atn, "atn")
        key = (
            "car_detail",
            ("gn", gn),
            ("rc", rc),
            ("acc", acc),
            ("atn", atn),
            ("lang", "en"),
        )
        value, _ = self._cached(
            key,
            DETAIL_TTL,
            lambda: self._load_car_detail(gn=gn, rc=rc, acc=acc, atn=atn),
        )
        return value

    @staticmethod
    def _health_query(auction: GlovisAuction) -> GlovisCarsQuery:
        return GlovisCarsQuery(
            atn=auction.number,
            acc=auction.acc,
            page=1,
            page_size=1,
        )

    def _load_health(self) -> GlovisHealthResponse:
        deadline_at = self._clock() + OVERALL_DEADLINE_SECONDS
        auctions, auctions_egress = self._load_auctions(deadline_at)
        if not auctions.auctions:
            return GlovisHealthResponse(
                auction_count=0,
                list_count=0,
                egress=_safe_egress(auctions_egress),
                checked_at=datetime.now(timezone.utc),
            )

        cars, cars_egress = self._load_cars(
            self._health_query(auctions.auctions[0]),
            deadline_at,
        )
        return GlovisHealthResponse(
            auction_count=len(auctions.auctions),
            list_count=cars.total,
            egress=_safe_egress(cars_egress),
            checked_at=datetime.now(timezone.utc),
        )

    def check_health(self) -> GlovisHealthResponse:
        return self._cached(
            ("health_probe",),
            HEALTH_TTL,
            self._load_health,
        )

    def _load_detail_health(self) -> GlovisDetailHealthResponse:
        deadline_at = self._clock() + OVERALL_DEADLINE_SECONDS
        auctions, auctions_egress = self._load_auctions(deadline_at)
        if not auctions.auctions:
            return GlovisDetailHealthResponse(
                auction_count=0,
                list_count=0,
                egress=_safe_egress(auctions_egress),
                checked_at=datetime.now(timezone.utc),
            )

        cars, cars_egress = self._load_cars(
            self._health_query(auctions.auctions[0]),
            deadline_at,
        )
        if cars.total == 0:
            return GlovisDetailHealthResponse(
                auction_count=len(auctions.auctions),
                list_count=0,
                egress=_safe_egress(cars_egress),
                checked_at=datetime.now(timezone.utc),
            )
        if not cars.items:
            raise _invalid_response()

        sample = cars.items[0]
        _, detail_egress = self._load_car_detail(
            gn=sample.gn,
            rc=sample.rc,
            acc=sample.acc,
            atn=sample.atn,
            deadline_at=deadline_at,
        )
        return GlovisDetailHealthResponse(
            auction_count=len(auctions.auctions),
            list_count=cars.total,
            egress=_safe_egress(detail_egress),
            checked_at=datetime.now(timezone.utc),
        )

    def check_detail_health(self) -> GlovisDetailHealthResponse:
        return self._cached(
            ("detail_health_probe",),
            DETAIL_HEALTH_TTL,
            self._load_detail_health,
        )

    def close(self) -> None:
        should_close = False
        with self._cache_lock:
            if not self._closed:
                self._closed = True
                self._cache_generation += 1
                self._cache.clear()
                should_close = True
        if should_close:
            self._transport.close()
