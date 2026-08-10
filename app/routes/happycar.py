from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from datetime import datetime
from loguru import logger
import asyncio
import threading

from app.core.auth_errors import AuthError, missing_credential_names
from app.core.config import get_settings
from app.core.proxy_config import ProxyConfigurationError, get_proxy_pool
from app.models.happycar import (
    HappyCarResponse, HappyCarDetailResponse, HappyCarHealthResponse,
)
from app.services.happycar_service import HappyCarService
from app.core.logging import get_logger

# Setup logger
happycar_logger = get_logger("happycar_routes")

settings = get_settings()

router = APIRouter(tags=["HappyCar Insurance Auction"])

# Global service instance, created only when a HappyCar operation needs it.
happycar_service: HappyCarService | None = None
_happycar_service_lock = threading.Lock()


def get_happycar_service() -> HappyCarService:
    """Dependency to get HappyCarService instance"""
    global happycar_service
    if happycar_service is None:
        with _happycar_service_lock:
            if happycar_service is None:
                happycar_service = HappyCarService()
    return happycar_service


@router.get("/cars", response_model=HappyCarResponse)
async def get_happycar_cars(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(12, description="Items per page (12, 21, or 33)"),
    sale_type: Optional[str] = Query(None, description="Sale type: 구제, 폐차, 부품"),
    model_filter: Optional[str] = Query(None, description="Car model name filter"),
    year_start: Optional[str] = Query(None, description="Start year filter"),
    month_start: Optional[str] = Query(None, description="Start month filter"),
    year_end: Optional[str] = Query(None, description="End year filter"),
    month_end: Optional[str] = Query(None, description="End month filter"),
    region: Optional[str] = Query(None, description="Korean region filter"),
    search_type: Optional[str] = Query(None, description="Search type: 차명, 차량번호, 등재번호"),
    search_text: Optional[str] = Query(None, description="Search keyword"),
    service: HappyCarService = Depends(get_happycar_service),
) -> HappyCarResponse:
    """
    Get list of cars from HappyCar insurance auction

    **Filter options:**
    - sale_type: 구제 (salvage), 폐차 (scrap), 부품 (parts)
    - model_filter: car model name (e.g., 쏘나타)
    - region: Korean province/city
    - search_type + search_text: combined text search

    **Example usage:**
    ```
    GET /api/v1/happycar/cars?page=1&sale_type=구제
    GET /api/v1/happycar/cars?page=1&model_filter=쏘나타&region=서울
    ```
    """
    try:
        happycar_logger.info(f"📥 Request for HappyCar cars (page {page})")

        result = await asyncio.to_thread(
            service.fetch_cars,
            page=page,
            page_size=page_size,
            sale_type=sale_type or "",
            model_filter=model_filter or "",
            year_start=year_start or "",
            month_start=month_start or "",
            year_end=year_end or "",
            month_end=month_end or "",
            region=region or "",
            search_type=search_type or "",
            search_text=search_text or "",
        )

        if result.success:
            happycar_logger.info(
                f"✅ Fetched {len(result.data)} cars from HappyCar (total: {result.total_count})"
            )
        else:
            happycar_logger.error(f"❌ Error fetching HappyCar data: {result.message}")

        return result

    except AuthError:
        # Let the AuthError handler in main.py answer (503 + a code saying
        # whether a retry can help). HappyCar needs both credentials and the
        # shared proxy, and folding either failure in here made an
        # unprovisioned deployment look like a server crash.
        raise
    except Exception as e:
        happycar_logger.error(f"❌ Unexpected error fetching HappyCar cars: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}",
        )


@router.get("/cars/{idx}", response_model=HappyCarDetailResponse)
async def get_happycar_car_detail(
    idx: str,
    service: HappyCarService = Depends(get_happycar_service),
) -> HappyCarDetailResponse:
    """
    Get detailed information about a specific car

    **Parameters:**
    - **idx**: The car ID from HappyCar (e.g., "881525")

    **Example usage:**
    ```
    GET /api/v1/happycar/cars/881525
    ```
    """
    try:
        happycar_logger.info(f"📥 Request for car detail: {idx}")

        result = await asyncio.to_thread(service.fetch_car_detail, idx)

        if result.success and result.data:
            happycar_logger.info(f"✅ Retrieved car detail for idx={idx}")
            return result
        elif not result.success:
            happycar_logger.error(f"❌ Failed to fetch car detail: {result.message}")
            raise HTTPException(status_code=502, detail=result.message)
        else:
            happycar_logger.error(f"❌ Car not found: {idx}")
            raise HTTPException(status_code=404, detail=f"Car not found: {idx}")

    except HTTPException:
        raise
    except AuthError:
        # Let the AuthError handler in main.py answer (503 + a code saying
        # whether a retry can help). HappyCar needs both credentials and the
        # shared proxy, and folding either failure in here made an
        # unprovisioned deployment look like a server crash.
        raise
    except Exception as e:
        happycar_logger.error(f"❌ Unexpected error getting car detail: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}",
        )


@router.get("/health", response_model=HappyCarHealthResponse)
async def health_check() -> HappyCarHealthResponse:
    """
    Check health status of HappyCar service

    **Example usage:**
    ```
    GET /api/v1/happycar/health
    ```
    """
    # Previously a hardcoded success=True/status="active" literal: it reported
    # "healthy" on a deployment with no credentials and no proxy, i.e. it could
    # not fail and therefore told you nothing. HappyCar needs BOTH, so both are
    # checked — names only, never values.
    missing = missing_credential_names(
        {
            "HAPPYCAR_USERNAME": settings.happycar_username,
            "HAPPYCAR_PASSWORD": settings.happycar_password,
        }
    )
    try:
        get_proxy_pool()
    except ProxyConfigurationError:
        missing.append("AUCTION_PROXY_*")

    ready = not missing
    return HappyCarHealthResponse(
        success=ready,
        message=(
            "HappyCar service is healthy"
            if ready
            else f"HappyCar is not provisioned; missing {', '.join(missing)}"
        ),
        service="HappyCar Insurance Auction",
        status="active" if ready else "unconfigured",
        base_url=HappyCarService.BASE_URL,
    )
