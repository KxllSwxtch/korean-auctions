from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from pydantic import BaseModel

from app.models.autohub import (
    AutohubResponse,
    AutohubCarDetailResponse,
)
from app.models.autohub_filters import (
    AutohubSearchRequest,
    AutohubBrandsResponse,
    AutohubFilterInfo,
    AUTOHUB_MILEAGE_OPTIONS,
    AUTOHUB_PRICE_OPTIONS,
    AutohubFuelType,
    AutohubAuctionResult,
    AutohubLane,
)
from app.services.autohub_service import autohub_service, AutohubService
from app.core.logging import get_logger

logger = get_logger("autohub_routes")

router = APIRouter(
    responses={404: {"description": "Not found"}},
)


def get_autohub_service() -> AutohubService:
    return autohub_service


# ===== Car Listing & Search =====


@router.post(
    "/search",
    response_model=AutohubResponse,
    summary="Search cars with filters",
)
async def search_cars(
    search_params: AutohubSearchRequest,
    service: AutohubService = Depends(get_autohub_service),
) -> AutohubResponse:
    """Search cars with multi-brand filters and pagination."""
    try:
        logger.info(f"Search request: page={search_params.page}, brands={search_params.car_brands}")
        return service.get_car_list(search_params)
    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        return AutohubResponse(
            success=False,
            error=str(e),
            current_page=search_params.page,
            page_size=search_params.page_size,
        )


@router.get(
    "/cars",
    response_model=AutohubResponse,
    summary="Get car listing (backward compat)",
)
async def get_cars(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: AutohubService = Depends(get_autohub_service),
) -> AutohubResponse:
    """Get car listing with default filters. Backward compatible endpoint."""
    params = AutohubSearchRequest(page=page, page_size=page_size)
    return service.get_car_list(params)


# ===== Car Detail =====


@router.get(
    "/car-detail/{car_id}",
    response_model=AutohubCarDetailResponse,
    summary="Get car detail",
)
async def get_car_detail(
    car_id: str,
    perf_id: Optional[str] = Query(None, description="Performance/inspection ID"),
    service: AutohubService = Depends(get_autohub_service),
) -> AutohubCarDetailResponse:
    """Get composite car detail: info + inspection + diagram."""
    try:
        logger.info(f"Car detail request: car_id={car_id}, perf_id={perf_id}")
        return service.get_car_detail(car_id, perf_id)
    except Exception as e:
        logger.error(f"Car detail error: {e}", exc_info=True)
        return AutohubCarDetailResponse(success=False, error=str(e))


# ===== Brands =====


@router.get(
    "/brands",
    response_model=AutohubBrandsResponse,
    summary="Get hierarchical brands",
)
async def get_brands(
    service: AutohubService = Depends(get_autohub_service),
) -> AutohubBrandsResponse:
    """Get full hierarchical brands data (brand → model → model detail)."""
    try:
        return service.get_brands()
    except Exception as e:
        logger.error(f"Brands error: {e}", exc_info=True)
        return AutohubBrandsResponse(success=False, error=str(e))


# ===== Auth =====


@router.get(
    "/auth/status",
    summary="Check JWT token status",
)
async def auth_status(
    service: AutohubService = Depends(get_autohub_service),
):
    """Check JWT token validity and service status."""
    return service.get_auth_status()


class SetTokenRequest(BaseModel):
    token: str


@router.post(
    "/auth/set-token",
    summary="Set JWT token",
)
async def set_token(
    request: SetTokenRequest,
    service: AutohubService = Depends(get_autohub_service),
):
    """Set or update JWT bearer token."""
    is_valid = service.set_jwt_token(request.token)
    return {
        "success": True,
        "message": "Token set successfully",
        "is_valid": is_valid,
    }


# ===== Filters & Health =====


@router.get(
    "/filters/info",
    summary="Get available filter options",
)
async def get_filters_info(
    service: AutohubService = Depends(get_autohub_service),
):
    """Get all available filter options for the frontend."""
    filters = service.get_filters_info()
    return {
        "success": True,
        "message": "Filter options loaded",
        "filters": filters,
    }


@router.get(
    "/health",
    summary="Health check",
)
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "autohub",
        "api_mode": "json",
        "message": "Autohub JSON API service is running",
    }
