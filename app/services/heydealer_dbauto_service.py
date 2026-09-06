"""HeyDealer feed served from the dbauto tokenless API.

This replaces the dealer-portal scraper. The old path logged into
`api.heydealer.com` with one shared dealer account, and because HeyDealer allows a
single live session per account, any human signing in with those credentials
silently evicted our cached cookie -- and our re-login evicted them right back.
dbauto needs no account at all, so that failure mode has nowhere to live.

Everything here is async because the routes are, but the transport underneath is
`requests`; each call is handed to a worker thread. That is the same arrangement
`_hd_get_async` used, and `tests/test_event_loop_blocking.py` enforces it: a
synchronous upstream call made directly from `async def` blocks the event loop for
the whole round trip to Korea, during which the worker answers nothing and
gunicorn eventually kills it.
"""

from __future__ import annotations

import asyncio
import functools
import os
import re
import time
from typing import Any, Iterable, Mapping, Sequence

from loguru import logger

from app.core.async_cache import SwrCache
from app.services.dbauto_transport import (
    BULK,
    CASCADE,
    INTERACTIVE,
    DbautoServiceConfig,
    DbautoTransport,
    DbautoUpstreamError,
    Lane,
)
from app.services.heydealer_dbauto_mapper import (
    build_diagram,
    map_detail,
    map_facet_options,
    map_list_card,
    normalize_list,
)

#: dbauto serves `/cars` in fixed 20-row pages. `page_size`, `limit` and `per_page`
#: are all accepted and all ignored, so the window has to be assembled here.
UPSTREAM_PAGE_SIZE = 20

#: Cap on upstream pages fetched for one caller page. A caller asking for 100 rows
#: costs 5 upstream calls; anything beyond that is refused rather than silently
#: turning one request into a fan-out that starves the interactive lane.
MAX_UPSTREAM_PAGES = 5

#: dbauto only honours these two `ordering` values -- verified live 2026-09-06.
#: `-` prefixes, `end_at`, `desired_price` and `approved_at` are all accepted and
#: silently ignored, so offering a price or ending-soonest sort would be a lie.
ORDERING = {
    "mileage_asc": "mileage",
    "year_desc": "year",
}

#: The 13 categorical facet sections. NB: region's section id is
#: `location_first_part` while its filter key on /cars is `location`.
SECTIONS = (
    "auction_type",
    "car_segment",
    "location_first_part",
    "fuel",
    "transmission",
    "payment",
    "car_type",
    "owner_change_record",
    "use_record",
    "wheel_drive",
    "special_accident_record",
    "operation_availability",
    "accident_repairs_summary",
)

#: Our public filter names -> dbauto's. Values that are lists upstream are listed
#: in MULTI so a comma-joined string from the frontend becomes repeated keys.
FILTER_ALIASES = {
    "brand": "brand",
    "model_group": "model_group",
    "model": "model",
    "grade": "grade",
    "min_year": "year_min",
    "max_year": "year_max",
    "min_mileage": "mileage_min",
    "max_mileage": "mileage_max",
    "min_price": "desired_price_min",
    "max_price": "desired_price_max",
    "fuel": "fuel",
    "transmission": "transmission",
    "car_segment": "car_segment",
    "car_type": "car_type",
    "payment": "payment",
    "wheel_drive": "wheel_drive",
    "location": "location",
    "location_first_part": "location",
    "auction_type": "auction_type",
    "accident_repairs_summary": "accident_repairs_summary",
    "accident_group": "accident_repairs_summary",
    "owner_change_record": "owner_change_record",
    "use_record": "use_record",
    "special_accident_record": "special_accident_record",
    "operation_availability": "operation_availability",
}

#: dbauto expresses these as repeated keys; the frontend sends them comma-joined.
MULTI_VALUE = frozenset(
    {
        "model",
        "grade",
        "fuel",
        "transmission",
        "car_segment",
        "car_type",
        "payment",
        "wheel_drive",
        "location",
        "auction_type",
        "accident_repairs_summary",
        "owner_change_record",
        "use_record",
        "special_accident_record",
        "operation_availability",
    }
)

#: Cascade dimensions must never narrow their own facet query -- a Make facet
#: filtered by the selected Make would return only that one Make.
CASCADE_KEYS = ("brand", "model_group", "model", "grade")

ALLOWED_PATHS = frozenset(
    {
        "/cars",
        "/car",
        "/accident_repairs",
        "/brand-counts",
        "/model-counts",
        "/section-counts",
    }
)

#: dbauto geo-blocks Korea, so KR is the one country that must never appear here.
#: Measured from production 2026-08-27: JP/HK/TW/SG/US/DE/GB/NL/FR/CA/AU/VN all
#: answer 200, JP fastest.
ALLOWED_EGRESS_COUNTRIES = frozenset(
    {"JP", "HK", "TW", "SG", "US", "DE", "GB", "NL", "FR", "CA", "AU", "VN", "JE"}
)

SUPPORTED_LANGS = frozenset({"en", "ru", "es", "ko"})

#: HeyDealer hash ids are short mixed-case alphanumerics ("lD6m16Jn").
_HASH_ID = re.compile(r"[A-Za-z0-9]{6,12}")

#: An unknown car id does not 404 upstream -- dbauto answers 500, or 503 after its
#: own 10 s timeout to HeyDealer, taking 8-33 s to do it. Retrying that three times
#: would hold an interactive slot for two minutes per bogus id, which is a
#: self-inflicted outage as soon as anything scans /cars/<random>. So the detail
#: path gets a short deadline and a single retry.
DETAIL_DEADLINE_SECONDS = 20.0
DETAIL_MAX_ATTEMPTS = 2

#: Shared ceiling for a facet fan-out. Deliberately larger than one request's
#: patience: the calls that miss it are still populating the cache, so the cost is
#: paid once per 6 h TTL rather than per user.
SECTIONS_BUDGET_SECONDS = 25.0

#: The facet dimensions the filter UI can actually drive. The full 13-section tree
#: is available through /filters/sections/{section}; fetching all of it on every
#: /filters call would spend a cold minute upstream on dropdowns nothing renders.
FILTER_SECTIONS = ("fuel", "transmission", "wheel_drive", "car_segment")


def is_valid_hash_id(hash_id: str | None) -> bool:
    """Cheap shape check, so obviously malformed ids never reach the network."""
    return bool(hash_id) and bool(_HASH_ID.fullmatch(str(hash_id)))


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def build_config() -> DbautoServiceConfig:
    return DbautoServiceConfig(
        name="heydealer",
        api_prefix="/api/auctions/heydealer",
        referer="https://cars.dbauto.kr/en/heydealer",
        allowed_paths=ALLOWED_PATHS,
        allowed_countries=ALLOWED_EGRESS_COUNTRIES,
        # A shared DBAUTO_PROXY_* is preferred; GLOVIS_PROXY_* is honoured as a
        # fallback so an already-deployed service keeps booting mid-rollout.
        proxy_env_prefixes=("DBAUTO_PROXY", "HEYDEALER_DBAUTO_PROXY", "GLOVIS_PROXY"),
        max_sessions=_env_int("HEYDEALER_MAX_CONCURRENCY", 4),
        facet_concurrency=_env_int("HEYDEALER_FACET_CONCURRENCY", 2),
    )


def normalize_lang(lang: str | None) -> str:
    """dbauto serves en/ru/es natively (and ko); anything else falls back to en."""
    candidate = (lang or "").strip().lower()
    return candidate if candidate in SUPPORTED_LANGS else "en"


def _split_multi(value: Any) -> list[str]:
    """Turn the frontend's comma-joined string into dbauto's repeated keys."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        parts: list[str] = []
        for item in value:
            parts.extend(_split_multi(item))
        return parts
    return [part.strip() for part in str(value).split(",") if part.strip()]


def filter_params(
    filters: Mapping[str, Any] | None,
    *,
    drop: Iterable[str] = (),
) -> list[tuple[str, str]]:
    """Serialise our filter bag into dbauto query pairs.

    ``drop`` removes a dimension from the query, which is what makes contextual
    faceting correct: the Make facet must be narrowed by everything *except* Make.
    """
    pairs: list[tuple[str, str]] = []
    dropped = set(drop)
    for key, value in (filters or {}).items():
        if key in dropped or value is None or value == "":
            continue
        target = FILTER_ALIASES.get(key)
        if not target:
            continue
        if target in MULTI_VALUE:
            for part in _split_multi(value):
                pairs.append((target, part))
        else:
            pairs.append((target, str(value)))
    return pairs


class HeyDealerDbautoService:
    """Cached, lane-aware access to the six dbauto HeyDealer endpoints."""

    def __init__(self, transport: DbautoTransport | None = None) -> None:
        self._transport = transport or DbautoTransport(build_config())
        self._list_cache: SwrCache[dict[str, Any]] = SwrCache(
            ttl=60, stale_ttl=240, maxsize=512, jitter=5, name="heydealer_list"
        )
        self._detail_cache: SwrCache[dict[str, Any]] = SwrCache(
            ttl=300, stale_ttl=900, maxsize=512, jitter=15, name="heydealer_detail"
        )
        self._facet_cache: SwrCache[list[dict[str, Any]]] = SwrCache(
            ttl=21_600, stale_ttl=86_400, maxsize=512, jitter=300, name="heydealer_facets"
        )
        # The atlas is byte-identical across cars (verified live: three cars, one
        # geometry hash), so it is fetched once and held for a day.
        self._atlas_cache: SwrCache[list[Any]] = SwrCache(
            ttl=86_400, stale_ttl=604_800, maxsize=4, jitter=600, name="heydealer_atlas"
        )
        #: When any dbauto call last succeeded. dbauto has no 404 -- an id it does
        #: not know answers 500, or 503 after its own timeout -- so this is what
        #: separates "that car is gone" from "the feed is down".
        self._last_success: float | None = None

    # -- plumbing ------------------------------------------------------------ #

    async def _get(
        self,
        path: str,
        params: Sequence[tuple[str, Any]],
        operation: str,
        *,
        lane: Lane = INTERACTIVE,
        lang: str = "en",
        deadline_at: float | None = None,
        max_attempts: int | None = None,
    ) -> Any:
        result = await asyncio.to_thread(
            functools.partial(
                self._transport.get_json,
                path,
                list(params),
                operation,
                lane=lane,
                lang=lang,
                deadline_at=deadline_at,
                max_attempts=max_attempts,
            )
        )
        self._last_success = time.monotonic()
        return result.value

    def feed_recently_healthy(self, within_seconds: float = 120.0) -> bool:
        """True when some dbauto call succeeded recently.

        Used to interpret a failing detail call. dbauto answers an unknown car id
        with a 500 rather than a 404, which is indistinguishable from an outage in
        isolation -- but if the catalog answered a moment ago, the feed is plainly
        up and the id is simply not one it has.
        """
        if self._last_success is None:
            return False
        return (time.monotonic() - self._last_success) <= within_seconds

    def close(self) -> None:
        self._transport.close()

    # -- catalog ------------------------------------------------------------- #

    async def list_cars(
        self,
        *,
        page: int = 1,
        page_size: int = UPSTREAM_PAGE_SIZE,
        order: str | None = None,
        filters: Mapping[str, Any] | None = None,
        lang: str = "en",
    ) -> dict[str, Any]:
        """One page of the catalog, mapped onto dbauto's fixed 20-row pages."""
        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or UPSTREAM_PAGE_SIZE), 100))
        lang = normalize_lang(lang)

        offset = (page - 1) * page_size
        first_page = offset // UPSTREAM_PAGE_SIZE + 1
        last_page = (offset + page_size - 1) // UPSTREAM_PAGE_SIZE + 1
        last_page = min(last_page, first_page + MAX_UPSTREAM_PAGES - 1)

        ordering = ORDERING.get((order or "").strip())
        base_params = filter_params(filters)
        if ordering:
            base_params.append(("ordering", ordering))

        async def fetch(upstream_page: int) -> dict[str, Any]:
            key = (lang, ordering, upstream_page, tuple(sorted(base_params)))

            async def loader() -> dict[str, Any]:
                body = await self._get(
                    "/cars",
                    [("page", upstream_page), *base_params],
                    "list",
                    lane=INTERACTIVE,
                    lang=lang,
                )
                return normalize_list(body)

            return await self._list_cache.get(key, loader)

        pages = await asyncio.gather(
            *(fetch(number) for number in range(first_page, last_page + 1))
        )

        total: int | None = None
        rows: list[Mapping[str, Any]] = []
        seen: set[str] = set()
        for number, body in zip(range(first_page, last_page + 1), pages):
            # dbauto echoes the page it actually served. It does not clamp -- an
            # out-of-range page comes back empty -- but a mismatch would mean the
            # rows belong to a different window, so the page is dropped whole.
            echoed = body.get("page")
            if echoed is not None and echoed != number:
                logger.warning(
                    "heydealer_page_mismatch requested={} echoed={}", number, echoed
                )
                continue
            if total is None:
                total = body.get("total")
            for item in body["items"]:
                hash_id = item.get("hash_id")
                if hash_id and hash_id not in seen:
                    seen.add(hash_id)
                    rows.append(item)

        start = offset - (first_page - 1) * UPSTREAM_PAGE_SIZE
        window = rows[start : start + page_size]
        return {
            "cars": [map_list_card(row) for row in window],
            "total_count": total if total is not None else len(rows),
            "page": page,
            "page_size": page_size,
        }

    async def _get_raw_car(self, hash_id: str, *, lang: str = "en") -> dict[str, Any]:
        """The cached, unmapped detail payload.

        Kept separate from `get_car` because the diagram needs the raw
        `accident_repairs` array, and re-deriving it from the mapped shape would
        mean either a second upstream call or a lossy round trip.
        """
        lang = normalize_lang(lang)
        if not is_valid_hash_id(hash_id):
            return {}

        async def loader() -> dict[str, Any]:
            body = await self._get(
                "/car",
                [("hash_id", hash_id)],
                "detail",
                lane=INTERACTIVE,
                lang=lang,
                deadline_at=time.monotonic() + DETAIL_DEADLINE_SECONDS,
                max_attempts=DETAIL_MAX_ATTEMPTS,
            )
            return body if isinstance(body, dict) else {}

        return await self._detail_cache.get((hash_id, lang), loader)

    async def get_car(self, hash_id: str, *, lang: str = "en") -> dict[str, Any] | None:
        """Full detail for one car, or ``None`` when dbauto does not know it.

        An unknown id does not 404 upstream -- it returns an object with no
        `hash_id` -- so absence has to be detected on content.
        """
        raw = await self._get_raw_car(hash_id, lang=lang)
        if not raw.get("hash_id"):
            return None
        return map_detail(raw)

    # -- damage diagram ------------------------------------------------------ #

    async def get_atlas(self, hash_id: str, *, lang: str = "en") -> list[Any]:
        """The 4-view geometry atlas.

        Cached under a constant key because it is genuinely car-independent: the
        `car` parameter is required by the endpoint but does not change the answer.
        """
        lang = normalize_lang(lang)

        async def loader() -> list[Any]:
            body = await self._get(
                "/accident_repairs",
                [("car", hash_id)],
                "atlas",
                lane=BULK,
                lang=lang,
            )
            return body if isinstance(body, list) else []

        return await self._atlas_cache.get(("atlas", lang), loader)

    async def get_diagram(self, hash_id: str, *, lang: str = "en") -> dict[str, Any] | None:
        """Join the cached atlas geometry with this car's actual repairs.

        The two halves are fetched concurrently: neither depends on the other, and
        the atlas is almost always a cache hit anyway.
        """
        raw, atlas = await asyncio.gather(
            self._get_raw_car(hash_id, lang=lang),
            self.get_atlas(hash_id, lang=lang),
        )
        if not raw.get("hash_id"):
            return None
        return build_diagram(atlas, raw.get("accident_repairs") or [])

    # -- taxonomy ------------------------------------------------------------ #

    async def get_brands(
        self, *, lang: str = "en", filters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        lang = normalize_lang(lang)
        params = filter_params(filters, drop=CASCADE_KEYS)
        key = ("brands", lang, tuple(sorted(params)))

        async def loader() -> list[dict[str, Any]]:
            body = await self._get(
                "/brand-counts", params, "brands", lane=CASCADE, lang=lang
            )
            return map_facet_options(body)

        return await self._facet_cache.get(key, loader)

    async def get_models(
        self,
        *,
        brand: str,
        model_group: str | None = None,
        model: str | None = None,
        lang: str = "en",
        filters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Cascade levels 2-4, all served by `/model-counts`.

        `brand` is structurally required: without it dbauto answers with the whole
        tree, which would silently populate a Model dropdown with every model of
        every make.
        """
        if not brand:
            raise ValueError("brand is required for the HeyDealer model cascade")
        lang = normalize_lang(lang)

        params = filter_params(filters, drop=CASCADE_KEYS)
        params.append(("brand", brand))
        if model_group:
            params.append(("model_group", model_group))
        if model:
            params.append(("model", model))
        key = ("models", lang, tuple(sorted(params)))

        async def loader() -> list[dict[str, Any]]:
            body = await self._get(
                "/model-counts", params, "models", lane=CASCADE, lang=lang
            )
            return map_facet_options(body)

        return await self._facet_cache.get(key, loader)

    async def get_section(
        self,
        section: str,
        *,
        lang: str = "en",
        filters: Mapping[str, Any] | None = None,
        deadline_at: float | None = None,
    ) -> list[dict[str, Any]]:
        if section not in SECTIONS:
            raise ValueError(f"unknown HeyDealer facet section: {section!r}")
        lang = normalize_lang(lang)
        # A facet must not be narrowed by its own dimension, or every other option
        # in it reads as having zero cars.
        own = "location" if section == "location_first_part" else section
        params = filter_params(filters, drop=(own,))
        params.append(("section", section))
        key = ("section", lang, tuple(sorted(params)))

        async def loader() -> list[dict[str, Any]]:
            body = await self._get(
                "/section-counts",
                params,
                "section",
                lane=BULK,
                lang=lang,
                deadline_at=deadline_at,
            )
            return map_facet_options(body)

        return await self._facet_cache.get(key, loader)

    async def get_sections(
        self,
        sections: Sequence[str] = SECTIONS,
        *,
        lang: str = "en",
        filters: Mapping[str, Any] | None = None,
        budget_seconds: float = SECTIONS_BUDGET_SECONDS,
    ) -> dict[str, list[dict[str, Any]]]:
        """Fan out over facet sections, keeping partial results usable.

        A cold `/section-counts` costs 12-15 s upstream (dbauto counts over ~7,000
        lots) and the facet lane holds two slots, so a cold fan-out over all
        thirteen sections cannot fit in a request. One shared budget is spread
        across the fan-out; whatever lands inside it is returned, the rest keeps
        computing into the cache and is there for the next caller.

        A section whose call failed is **omitted**, never returned as ``[]``. An
        empty list is a claim that upstream has zero options for that dimension,
        and a caller that renders or caches it turns a transient timeout into a
        permanently empty dropdown.
        """
        deadline = time.monotonic() + max(1.0, budget_seconds)
        results = await asyncio.gather(
            *(
                self.get_section(
                    name, lang=lang, filters=filters, deadline_at=deadline
                )
                for name in sections
            ),
            return_exceptions=True,
        )
        out: dict[str, list[dict[str, Any]]] = {}
        for name, result in zip(sections, results):
            if isinstance(result, BaseException):
                logger.warning(
                    "heydealer_section_failed section={} error={}",
                    name,
                    type(result).__name__,
                )
                continue
            out[name] = result
        return out

    async def warm(self, langs: Sequence[str] = ("ru", "en", "es")) -> None:
        """Populate the caches a catalog page needs, off the request path.

        Runs at startup and is intentionally forgiving: a warm failure is logged
        and dropped, because it must never keep the app from serving.
        """
        for lang in langs:
            try:
                page = await self.list_cars(page=1, lang=lang)
                await self.get_brands(lang=lang)
                await self.get_sections(FILTER_SECTIONS, lang=lang)
                # The damage atlas is one shared payload per language, so warming
                # it here takes it off the first car detail's critical path
                # entirely -- that page was breaching the proxy timeout cold.
                cars = page.get("cars") or []
                if cars:
                    await self.get_atlas(cars[0]["hash_id"], lang=lang)
            except Exception as error:  # noqa: BLE001 - warming is best effort
                logger.warning(
                    "heydealer_warm_failed lang={} error={}", lang, type(error).__name__
                )

    # -- health -------------------------------------------------------------- #

    async def health(self) -> dict[str, Any]:
        """Cheapest call that proves egress, token mint and the feed all work."""
        try:
            body = await self._get("/cars", [("page", 1)], "health", lane=INTERACTIVE)
            normalized = normalize_list(body)
            return {
                "status": "ok",
                "source": "dbauto",
                "total_cars": normalized.get("total"),
                "egress": list(self._transport.egress_labels),
            }
        except DbautoUpstreamError as error:
            return {
                "status": "error",
                "source": "dbauto",
                "code": error.code,
                "egress": list(self._transport.egress_labels),
            }


_service: HeyDealerDbautoService | None = None


def get_service() -> HeyDealerDbautoService:
    """Process-wide singleton so the session pool and caches are actually shared."""
    global _service
    if _service is None:
        _service = HeyDealerDbautoService()
    return _service


def close_service() -> None:
    global _service
    if _service is not None:
        _service.close()
        _service = None
