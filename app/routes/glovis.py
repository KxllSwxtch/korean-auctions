"""Canonical FastAPI contract for the DB Auto Glovis provider."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable, NoReturn, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.types import Receive, Scope, Send

from app.models.glovis import (
    GlovisAuctionsResponse,
    GlovisCarDetailResponse,
    GlovisCarsQuery,
    GlovisCarsResponse,
    GlovisDetailHealthResponse,
    GlovisFilterItemsResponse,
    GlovisFilterOptionsResponse,
    GlovisHealthResponse,
)
from app.services.glovis_service import (
    GlovisCarUnavailableError,
    GlovisService,
    validate_gn,
    validate_provider_id,
)
from app.services.glovis_transport import GlovisUpstreamError


ERROR_STATUS = {
    "proxy_unavailable": 503,
    "upstream_timeout": 504,
    "upstream_auth": 502,
    "upstream_invalid_response": 502,
    "upstream_unavailable": 502,
}

ResponseT = TypeVar("ResponseT")


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    retryable: bool,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": {
                "code": code,
                "message": message,
                "retryable": retryable,
            }
        },
        headers={"Cache-Control": "no-store"},
    )


class _StableErrorRoute(APIRoute):
    """Keep framework-level validation and unexpected failures contract-safe."""

    async def handle(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if self.methods and scope["method"] not in self.methods:
            response = _error_response(
                status_code=405,
                code="method_not_allowed",
                message="Method not allowed",
                retryable=False,
            )
            response.headers["Allow"] = ", ".join(sorted(self.methods))
            await response(scope, receive, send)
            return
        await super().handle(scope, receive, send)

    def get_route_handler(self) -> Callable[[Request], Any]:
        route_handler = super().get_route_handler()

        async def stable_route_handler(request: Request):
            try:
                return await route_handler(request)
            except RequestValidationError:
                return _error_response(
                    status_code=422,
                    code="invalid_request",
                    message="Invalid request parameters",
                    retryable=False,
                )
            except HTTPException:
                raise
            except GlovisUpstreamError as error:
                return _error_response(
                    status_code=ERROR_STATUS[error.code],
                    code=error.code,
                    message="Glovis provider is temporarily unavailable",
                    retryable=True,
                )
            except Exception:
                return _error_response(
                    status_code=500,
                    code="internal_error",
                    message="Glovis request could not be completed",
                    retryable=False,
                )

        return stable_route_handler


router = APIRouter(
    prefix="/api/v1/glovis",
    tags=["Glovis Auction"],
    route_class=_StableErrorRoute,
)

glovis_service: GlovisService | None = None
_glovis_service_lock = threading.Lock()


def get_glovis_service() -> GlovisService:
    """Lazily create the process-wide Glovis service."""
    global glovis_service
    if glovis_service is None:
        with _glovis_service_lock:
            if glovis_service is None:
                glovis_service = GlovisService()
    return glovis_service


def get_existing_glovis_service() -> GlovisService | None:
    """Return an existing service without triggering proxy configuration."""
    return glovis_service


def close_glovis_service() -> None:
    """Close and discard the singleton if a request successfully created it."""
    global glovis_service
    with _glovis_service_lock:
        service = glovis_service
        glovis_service = None
    if service is not None:
        service.close()


def raise_upstream(error: GlovisUpstreamError) -> NoReturn:
    raise HTTPException(
        status_code=ERROR_STATUS[error.code],
        detail={
            "code": error.code,
            "message": "Glovis provider is temporarily unavailable",
            "retryable": True,
        },
        headers={"Cache-Control": "no-store"},
    )


def _raise_invalid_identifier() -> NoReturn:
    raise HTTPException(
        status_code=422,
        detail={
            "code": "invalid_identifier",
            "message": "Invalid Glovis identifier or filter relationship",
            "retryable": False,
        },
        headers={"Cache-Control": "no-store"},
    )


def _raise_car_unavailable() -> NoReturn:
    raise HTTPException(
        status_code=404,
        detail={
            "code": "car_unavailable",
            "message": "Car details are not available",
            "retryable": False,
        },
        headers={"Cache-Control": "no-store"},
    )


def _validate_ids(**identifiers: str | None) -> None:
    try:
        for name, value in identifiers.items():
            if value is not None:
                validate_provider_id(value, name)
    except ValueError:
        _raise_invalid_identifier()


async def _run_service(
    operation: Callable[..., ResponseT],
    /,
    *args: Any,
    **kwargs: Any,
) -> ResponseT:
    try:
        return await asyncio.to_thread(operation, *args, **kwargs)
    except GlovisUpstreamError as error:
        raise_upstream(error)
    except GlovisCarUnavailableError:
        _raise_car_unavailable()
    except ValueError:
        _raise_invalid_identifier()


@router.get("/auctions", response_model=GlovisAuctionsResponse)
async def get_auctions(
    service: GlovisService = Depends(get_glovis_service),
) -> GlovisAuctionsResponse:
    return await _run_service(service.get_auctions)


@router.get("/cars", response_model=GlovisCarsResponse)
async def get_cars(
    atn: str = Query(...),
    acc: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=60),
    brand: str | None = Query(None),
    model: str | None = Query(None),
    submodel: str | None = Query(None),
    year_from: int | None = Query(None, ge=1900, le=2200),
    year_to: int | None = Query(None, ge=1900, le=2200),
    mileage_from: int | None = Query(None, ge=0),
    mileage_to: int | None = Query(None, ge=0),
    price_from: int | None = Query(None, ge=0),
    price_to: int | None = Query(None, ge=0),
    transmission: str | None = Query(None),
    fuel_type: str | None = Query(None),
    color: str | None = Query(None),
    options: list[str] = Query(default_factory=list),
    insurance_damage: str | None = Query(None),
    usage_history: list[str] = Query(default_factory=list),
    accident_history: str | None = Query(None),
    room: str | None = Query(None),
    lane: str | None = Query(None),
    bid_status: str | None = Query(None),
    sort_order: str = Query("01"),
    service: GlovisService = Depends(get_glovis_service),
) -> GlovisCarsResponse:
    try:
        query = GlovisCarsQuery(
            atn=atn,
            acc=acc,
            page=page,
            page_size=page_size,
            brand=brand,
            model=model,
            submodel=submodel,
            year_from=year_from,
            year_to=year_to,
            mileage_from=mileage_from,
            mileage_to=mileage_to,
            price_from=price_from,
            price_to=price_to,
            transmission=transmission,
            fuel_type=fuel_type,
            color=color,
            options=options,
            insurance_damage=insurance_damage,
            usage_history=usage_history,
            accident_history=accident_history,
            room=room,
            lane=lane,
            bid_status=bid_status,
            sort_order=sort_order,
        )
    except ValueError:
        _raise_invalid_identifier()
    _validate_ids(
        atn=query.atn,
        acc=query.acc,
        brand=query.brand,
        model=query.model,
        submodel=query.submodel,
    )
    return await _run_service(service.get_cars, query)


@router.get("/brands", response_model=GlovisFilterItemsResponse)
async def get_brands(
    atn: str = Query(...),
    acc: str = Query(...),
    service: GlovisService = Depends(get_glovis_service),
) -> GlovisFilterItemsResponse:
    _validate_ids(atn=atn, acc=acc)
    return await _run_service(service.get_brands, atn=atn, acc=acc)


@router.get("/models", response_model=GlovisFilterItemsResponse)
async def get_models(
    brand: str = Query(...),
    atn: str = Query(...),
    acc: str = Query(...),
    service: GlovisService = Depends(get_glovis_service),
) -> GlovisFilterItemsResponse:
    _validate_ids(brand=brand, atn=atn, acc=acc)
    return await _run_service(
        service.get_models,
        brand=brand,
        atn=atn,
        acc=acc,
    )


@router.get("/submodels", response_model=GlovisFilterItemsResponse)
async def get_submodels(
    brand: str = Query(...),
    model: str = Query(...),
    atn: str = Query(...),
    acc: str = Query(...),
    service: GlovisService = Depends(get_glovis_service),
) -> GlovisFilterItemsResponse:
    _validate_ids(brand=brand, model=model, atn=atn, acc=acc)
    return await _run_service(
        service.get_submodels,
        brand=brand,
        model=model,
        atn=atn,
        acc=acc,
    )


@router.get("/filters/options", response_model=GlovisFilterOptionsResponse)
async def get_filter_options(
    atn: str = Query(...),
    acc: str = Query(...),
    service: GlovisService = Depends(get_glovis_service),
) -> GlovisFilterOptionsResponse:
    _validate_ids(atn=atn, acc=acc)
    return await _run_service(service.get_filter_options, atn=atn, acc=acc)


@router.get("/car-detail", response_model=GlovisCarDetailResponse)
async def get_car_detail(
    gn: str = Query(...),
    rc: str = Query(...),
    acc: str = Query(...),
    atn: str = Query(...),
    service: GlovisService = Depends(get_glovis_service),
) -> GlovisCarDetailResponse:
    try:
        validate_gn(gn)
    except ValueError:
        _raise_invalid_identifier()
    _validate_ids(rc=rc, acc=acc, atn=atn)
    return await _run_service(
        service.get_car_detail,
        gn=gn,
        rc=rc,
        acc=acc,
        atn=atn,
    )


@router.get("/health", response_model=GlovisHealthResponse)
async def get_health(
    service: GlovisService = Depends(get_glovis_service),
) -> GlovisHealthResponse:
    return await _run_service(service.check_health)


@router.get("/health/detail", response_model=GlovisDetailHealthResponse)
async def get_detail_health(
    service: GlovisService = Depends(get_glovis_service),
) -> GlovisDetailHealthResponse:
    return await _run_service(service.check_detail_health)
