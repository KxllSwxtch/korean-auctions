"""HeyDealer HTTP surface backed by the dbauto tokenless API.

Twelve endpoints -- the ones `autobazaapp` actually calls. The legacy router
exposed about thirty, of which four were permanently shadowed by earlier path
patterns, one was declared twice, and several existed only as debugging aids that
echoed raw upstream payloads (including hardcoded session cookies).

Response envelopes are byte-compatible with the old ones on purpose. The frontend
nests these flat rows into `detail{}`/`auction{}` itself, through two different
transforms, and the Next proxy at `app/api/v1/[...path]/route.ts` forwards the whole
`/api/v1/heydealer/**` prefix generically -- so keeping the shapes identical is what
makes this a data-source swap rather than a full-stack rewrite.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException, Query, Request
from loguru import logger

from app.services.dbauto_transport import DbautoUpstreamError
from app.services.heydealer_dbauto_service import (
    FILTER_SECTIONS,
    SECTIONS,
    HeyDealerDbautoService,
    get_service,
    is_valid_hash_id,
    normalize_lang,
)

router = APIRouter(prefix="/heydealer", tags=["HeyDealer"])
filters_router = APIRouter(tags=["HeyDealer Filters"])

#: Upstream failure -> HTTP status. Codes are stable and machine-readable so the
#: frontend can branch on them; the previous implementation forced clients to
#: substring-match Russian error prose.
ERROR_STATUS: dict[str, int] = {
    "upstream_auth": 502,
    "upstream_invalid_response": 502,
    "upstream_unavailable": 502,
    "upstream_timeout": 504,
    "proxy_unavailable": 503,
    "egress_geo_blocked": 503,
}

MESSAGES: dict[str, str] = {
    "upstream_auth": "HeyDealer provider rejected the request",
    "upstream_invalid_response": "HeyDealer provider returned an unexpected response",
    "upstream_unavailable": "HeyDealer provider is temporarily unavailable",
    "upstream_timeout": "HeyDealer provider timed out",
    "proxy_unavailable": "HeyDealer egress is not configured",
    "egress_geo_blocked": "HeyDealer egress is blocked in this region",
}


def _now() -> str:
    return datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT")


def _raise_upstream(error: DbautoUpstreamError) -> NoReturn:
    """Translate an upstream failure without leaking its text.

    The message is looked up from the code, never taken from the exception: a
    requests/proxy error string embeds `http://user:pass@host`, and the old routes
    returned `str(e)` straight to unauthenticated callers.
    """
    code = error.code
    logger.warning(
        "heydealer_upstream_error code={} status={} egress={}",
        code,
        error.status_code,
        error.egress,
    )
    raise HTTPException(
        status_code=ERROR_STATUS.get(code, 502),
        detail={
            "code": code,
            "message": MESSAGES.get(code, "HeyDealer provider is unavailable"),
            "retryable": bool(getattr(error, "retryable", True)),
        },
        headers={"Cache-Control": "no-store"},
    )


def _raise_not_found(hash_id: str) -> NoReturn:
    raise HTTPException(
        status_code=404,
        detail={
            "code": "car_unavailable",
            "message": "Car is no longer available",
            "retryable": False,
        },
        headers={"Cache-Control": "no-store"},
    )


def _lang(request: Request, explicit: str | None) -> str:
    """Resolve the content language.

    dbauto translates its payloads natively into en/ru/es -- the same three locales
    this site ships -- so the locale is worth forwarding rather than translating
    Korean on the client. An explicit query parameter wins; otherwise the browser's
    Accept-Language is used, which keeps older clients working without a change.
    """
    if explicit:
        return normalize_lang(explicit)
    header = request.headers.get("accept-language") or ""
    for chunk in header.split(","):
        tag = chunk.split(";")[0].strip().lower()
        primary = tag.split("-")[0]
        if primary in {"ru", "es", "en", "ko"}:
            return primary
    return "en"


def _service() -> HeyDealerDbautoService:
    return get_service()


def _collect_filters(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value not in (None, "")}


def _list_envelope(result: dict[str, Any]) -> dict[str, Any]:
    """The list envelope both frontend transforms expect."""
    total = result["total_count"]
    page = result["page"]
    page_size = result["page_size"]
    return {
        "success": True,
        "data": {
            "cars": result["cars"],
            "total_count": total,
            "page": page,
        },
        "message": "OK",
        "total_count": total,
        "current_page": page,
        "pagination": {
            "current_page": page,
            "total_count": total,
            "page_size": page_size,
            "has_next": page * page_size < (total or 0),
        },
    }


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #


@router.get("/health")
async def health() -> dict[str, Any]:
    """Always 200, so a polling frontend never renders a hard error on a blip."""
    report = await _service().health()
    return {
        "status": report.get("status"),
        "has_data": bool(report.get("total_cars")),
        # Retained for contract compatibility. dbauto needs no account at all,
        # which is the entire point of this migration.
        "authenticated": True,
        "source": report.get("source"),
        "code": report.get("code"),
        "egress": report.get("egress"),
    }


@router.get("/status")
async def status() -> dict[str, Any]:
    report = await _service().health()
    ok = report.get("status") == "ok"
    return {
        "status": "online" if ok else "offline",
        "message": "HeyDealer via dbauto" if ok else MESSAGES.get(report.get("code", ""), "unavailable"),
        "auction_name": "HeyDealer",
        "authenticated": True,
        "cars_count": report.get("total_cars") or 0,
    }


@router.get("/stats")
async def stats() -> dict[str, Any]:
    """Total live lots. The frontend has always called this; it used to 404."""
    try:
        report = await _service().health()
    except DbautoUpstreamError as error:
        _raise_upstream(error)
    return {
        "success": report.get("status") == "ok",
        "data": {
            "total_cars": report.get("total_cars") or 0,
            "auction_name": "HeyDealer",
        },
        "message": "OK",
    }


# --------------------------------------------------------------------------- #
# Catalog
#
# NB: `/cars/filtered` is declared before `/cars/{car_hash_id}`. FastAPI matches in
# declaration order, so the reverse would resolve it as a car whose id is
# "filtered" -- which is exactly how four routes in the legacy module became
# unreachable.
# --------------------------------------------------------------------------- #


@router.get("/cars")
async def list_cars(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    order: str | None = None,
    lang: str | None = None,
    brand: str | None = None,
    model_group: str | None = None,
    model: str | None = None,
    grade: str | None = None,
    auction_type: str | None = None,
) -> dict[str, Any]:
    try:
        result = await _service().list_cars(
            page=page,
            page_size=page_size,
            order=order,
            lang=_lang(request, lang),
            filters=_collect_filters(
                brand=brand,
                model_group=model_group,
                model=model,
                grade=grade,
                auction_type=auction_type,
            ),
        )
    except DbautoUpstreamError as error:
        _raise_upstream(error)
    return _list_envelope(result)


@router.get("/cars/filtered")
async def list_cars_filtered(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    order: str | None = None,
    lang: str | None = None,
    brand: str | None = None,
    model_group: str | None = None,
    model: str | None = None,
    grade: str | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    min_mileage: int | None = None,
    max_mileage: int | None = None,
    fuel: str | None = None,
    transmission: str | None = None,
    wheel_drive: str | None = None,
    car_segment: str | None = None,
    car_type: str | None = None,
    payment: str | None = None,
    location: str | None = None,
    location_first_part: str | None = None,
    auction_type: str | None = None,
    accident_group: str | None = None,
    owner_change_record: str | None = None,
    use_record: str | None = None,
    special_accident_record: str | None = None,
    operation_availability: str | None = None,
) -> dict[str, Any]:
    """The filtered catalog. Multi-value filters arrive comma-joined and are
    expanded into dbauto's repeated query keys by the service."""
    try:
        result = await _service().list_cars(
            page=page,
            page_size=page_size,
            order=order,
            lang=_lang(request, lang),
            filters=_collect_filters(
                brand=brand,
                model_group=model_group,
                model=model,
                grade=grade,
                min_year=min_year,
                max_year=max_year,
                min_price=min_price,
                max_price=max_price,
                min_mileage=min_mileage,
                max_mileage=max_mileage,
                fuel=fuel,
                transmission=transmission,
                wheel_drive=wheel_drive,
                car_segment=car_segment,
                car_type=car_type,
                payment=payment,
                location=location,
                location_first_part=location_first_part,
                auction_type=auction_type,
                accident_group=accident_group,
                owner_change_record=owner_change_record,
                use_record=use_record,
                special_accident_record=special_accident_record,
                operation_availability=operation_availability,
            ),
        )
    except DbautoUpstreamError as error:
        _raise_upstream(error)
    return _list_envelope(result)


@router.get("/cars/{car_hash_id}/accident-diagram")
async def accident_diagram(
    request: Request, car_hash_id: str, lang: str | None = None
) -> dict[str, Any]:
    """The damage diagram, as four views.

    dbauto splits this: `/accident_repairs` holds the part coordinates and view
    images but reports every status as "none" (it is byte-identical for every car,
    verified live), while the real per-part statuses are on the car detail with no
    coordinates. The join happens in the mapper; the atlas half is cached for a day.
    """
    if not is_valid_hash_id(car_hash_id):
        _raise_not_found(car_hash_id)
    try:
        diagram = await _service().get_diagram(car_hash_id, lang=_lang(request, lang))
    except DbautoUpstreamError as error:
        _raise_upstream(error)
    if diagram is None:
        _raise_not_found(car_hash_id)
    return {
        "success": True,
        "data": diagram,
        "message": "OK",
        "timestamp": _now(),
    }


@router.get("/cars/{car_hash_id}")
async def get_car(
    request: Request, car_hash_id: str, lang: str | None = None
) -> dict[str, Any]:
    if not is_valid_hash_id(car_hash_id):
        _raise_not_found(car_hash_id)
    service = _service()
    language = _lang(request, lang)
    try:
        # Concurrent, not sequential: the diagram needs the same detail payload,
        # and the cache single-flights it, so this costs one upstream detail call
        # plus a (near-always cached) atlas read. Sequentially it was two round
        # trips to Korea and cold detail pages breached the 15 s proxy timeout.
        car, diagram = await asyncio.gather(
            service.get_car(car_hash_id, lang=language),
            service.get_diagram(car_hash_id, lang=language),
        )
        if car is None:
            _raise_not_found(car_hash_id)
    except DbautoUpstreamError as error:
        # dbauto has no 404: a lot it does not know answers 500 (or 503 after its
        # own upstream timeout). If the catalog was answering moments ago, the
        # feed is up and this is a stale or sold lot -- which happens constantly
        # on an auction site, and deserves "no longer available" rather than
        # "try again later".
        if service.feed_recently_healthy() and error.code in {
            "upstream_unavailable",
            "upstream_invalid_response",
        }:
            _raise_not_found(car_hash_id)
        _raise_upstream(error)

    car = dict(car)
    car["accident_repairs_data"] = diagram
    car["accident_repairs_available"] = bool(diagram and diagram.get("views"))
    car["accident_repairs_error"] = None
    return {
        "success": True,
        "data": car,
        "message": "OK",
        "timestamp": _now(),
        "total_requests": 2,
        "car_request_success": True,
        "accident_repairs_request_success": car["accident_repairs_available"],
    }


# --------------------------------------------------------------------------- #
# Filters and taxonomy
# --------------------------------------------------------------------------- #


@router.get("/filters")
async def available_filters(
    request: Request, lang: str | None = None
) -> dict[str, Any]:
    """The filter tree, built from live facet counts.

    The legacy version hardcoded fuel types, transmissions and a 1990-2025 year
    range, so the dropdowns disagreed with the catalog they filtered.
    """
    language = _lang(request, lang)
    service = _service()
    try:
        brands = await service.get_brands(lang=language)
    except DbautoUpstreamError as error:
        _raise_upstream(error)

    sections = await service.get_sections(FILTER_SECTIONS, lang=language)
    data: dict[str, Any] = {
        "brands": brands,
        # Present when the facet call succeeded; absent when it failed. An empty
        # list would be a claim that dbauto has zero options for the dimension,
        # and the client would render a permanently empty dropdown.
        "fuel_types": sections.get("fuel"),
        "transmissions": sections.get("transmission"),
        "wheel_drives": sections.get("wheel_drive"),
        "car_segments": sections.get("car_segment"),
        "years": {"min": 1990, "max": datetime.now().year + 1},
        "mileage": {"min": 0, "max": 500_000},
        "price": {"min": 0, "max": 100_000_000},
    }
    missing = [key for key, value in data.items() if value is None]
    return {
        "success": True,
        "data": {key: value for key, value in data.items() if value is not None},
        # A caller can tell "dbauto has no options here" from "we could not find
        # out in time" -- the difference between an empty dropdown and a retry.
        "degraded": bool(missing),
        "stale_groups": missing,
        "message": "OK",
    }


@filters_router.get("/brands")
async def brands(request: Request, lang: str | None = None) -> dict[str, Any]:
    try:
        options = await _service().get_brands(lang=_lang(request, lang))
    except DbautoUpstreamError as error:
        _raise_upstream(error)
    return {"success": True, "data": options, "message": "OK"}


@filters_router.get("/brands/{brand_hash_id}/models")
async def brand_models(
    request: Request, brand_hash_id: str, lang: str | None = None
) -> dict[str, Any]:
    try:
        options = await _service().get_models(
            brand=brand_hash_id, lang=_lang(request, lang)
        )
    except ValueError:
        _raise_cascade_requires_brand()
    except DbautoUpstreamError as error:
        _raise_upstream(error)
    return {
        "success": True,
        "data": {"model_groups": options, "models": options},
        "message": "OK",
    }


def _raise_cascade_requires_brand() -> NoReturn:
    """dbauto's `/model-counts` needs the brand at every cascade level.

    Without it the endpoint answers with the whole tree, which would quietly fill
    a Model dropdown with every model of every make -- a wrong answer is worse
    here than a loud one.
    """
    raise HTTPException(
        status_code=400,
        detail={
            "code": "brand_required",
            "message": "brand is required to resolve the HeyDealer model cascade",
            "retryable": False,
        },
        headers={"Cache-Control": "no-store"},
    )


@filters_router.get("/model-groups/{model_group_hash_id}/generations")
async def model_group_generations(
    request: Request,
    model_group_hash_id: str,
    brand: str | None = None,
    lang: str | None = None,
) -> dict[str, Any]:
    if not brand:
        _raise_cascade_requires_brand()
    try:
        options = await _service().get_models(
            brand=brand,
            model_group=model_group_hash_id,
            lang=_lang(request, lang),
        )
    except ValueError:
        _raise_cascade_requires_brand()
    except DbautoUpstreamError as error:
        _raise_upstream(error)
    return {"success": True, "data": {"models": options}, "message": "OK"}


@filters_router.get("/models/{model_hash_id}/configurations")
async def model_configurations(
    request: Request,
    model_hash_id: str,
    brand: str | None = None,
    model_group: str | None = None,
    lang: str | None = None,
) -> dict[str, Any]:
    if not brand:
        _raise_cascade_requires_brand()
    try:
        options = await _service().get_models(
            brand=brand,
            model_group=model_group,
            model=model_hash_id,
            lang=_lang(request, lang),
        )
    except ValueError:
        _raise_cascade_requires_brand()
    except DbautoUpstreamError as error:
        _raise_upstream(error)
    return {"success": True, "data": {"grades": options}, "message": "OK"}


@filters_router.get("/sections/{section}")
async def section_facets(
    request: Request, section: str, lang: str | None = None
) -> dict[str, Any]:
    """One categorical facet with live counts."""
    if section not in SECTIONS:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "unknown_section",
                "message": "Unknown HeyDealer facet section",
                "retryable": False,
            },
        )
    try:
        options = await _service().get_section(section, lang=_lang(request, lang))
    except DbautoUpstreamError as error:
        _raise_upstream(error)
    return {"success": True, "data": options, "message": "OK"}
