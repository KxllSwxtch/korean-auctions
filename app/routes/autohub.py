import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from typing import Optional
from pydantic import BaseModel

from app.core.config import get_settings
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


# ===== Image Proxy =====


@router.get(
    "/image/{file_id}",
    summary="Proxy image from Autohub API",
    responses={200: {"content": {"image/*": {}}}},
)
async def get_image(
    file_id: str,
    service: AutohubService = Depends(get_autohub_service),
) -> Response:
    """Proxy image from Autohub API with authentication."""
    try:
        image_bytes, content_type = service.get_image(file_id)
        return Response(
            content=image_bytes,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except Exception as e:
        logger.error(f"Image proxy error for {file_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to fetch image")


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


# ===== Snapshot mode (Wednesday catalogue cache) =====


@router.get(
    "/snapshot/status",
    summary="Snapshot mode status",
)
async def snapshot_status():
    """Report active snapshot metadata and which mode today resolves to.

    Public — used for monitoring and the frontend banner.
    """
    settings = get_settings()
    if not settings.autohub_snapshot_enabled:
        return {
            "snapshot_enabled": False,
            "mode_today": "live",
            "active_snapshot": None,
            "recent": [],
        }
    try:
        from app.services.autohub_snapshot_job import get_repo
        repo = await get_repo()
        active = await asyncio.to_thread(repo.get_active_snapshot)
        recent = await asyncio.to_thread(repo.list_snapshots, 5)
    except Exception as e:
        logger.error(f"snapshot/status repo failure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Snapshot repo unavailable")

    tz = ZoneInfo(settings.autohub_snapshot_timezone)
    weekday = datetime.now(tz).weekday()
    snapshot_days = {int(d) for d in settings.autohub_snapshot_days.split(",") if d.strip().isdigit()}
    mode_today = "snapshot" if weekday in snapshot_days else "live"

    age_hours: Optional[float] = None
    if active and active.get("completed_at"):
        completed = datetime.fromisoformat(active["completed_at"])
        if completed.tzinfo is None:
            completed = completed.replace(tzinfo=ZoneInfo("UTC"))
        age_hours = round((datetime.now(ZoneInfo("UTC")) - completed).total_seconds() / 3600, 2)

    return {
        "snapshot_enabled": True,
        "mode_today": mode_today,
        "snapshot_days": sorted(snapshot_days),
        "timezone": settings.autohub_snapshot_timezone,
        "active_snapshot": (
            None if not active else {
                **active,
                "age_hours": age_hours,
            }
        ),
        "recent": recent,
    }


@router.post(
    "/snapshot/run",
    status_code=202,
    summary="Manually trigger a snapshot run (admin)",
)
async def snapshot_run(
    background_tasks: BackgroundTasks,
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
):
    """Fire a snapshot run in the background.

    Auth: requires `X-Admin-Token` header matching `AUTOHUB_SNAPSHOT_ADMIN_TOKEN`.
    The job acquires its own filelock; if a run is already in progress this
    endpoint returns 409 immediately.
    """
    settings = get_settings()
    expected = settings.autohub_snapshot_admin_token
    if not expected:
        raise HTTPException(status_code=503, detail="Admin trigger not configured")
    if not x_admin_token or x_admin_token != expected:
        raise HTTPException(status_code=403, detail="Forbidden")

    from app.services.autohub_snapshot_job import run_snapshot_job, _run_lock_path
    from filelock import FileLock, Timeout
    # Probe the lock without holding it — surfaces "already running" cleanly.
    probe = FileLock(_run_lock_path(), timeout=0)
    try:
        probe.acquire()
        probe.release()
    except Timeout:
        raise HTTPException(status_code=409, detail="A snapshot run is already in progress")

    background_tasks.add_task(_safe_run_snapshot)
    return {"accepted": True, "message": "Snapshot run scheduled in background"}


async def _safe_run_snapshot() -> None:
    """Wrap run_snapshot_job in a try/except so background-task failures are logged."""
    from app.services.autohub_snapshot_job import run_snapshot_job
    try:
        await run_snapshot_job(triggered_by="admin")
    except Exception as e:
        logger.error(f"Background snapshot run failed: {e}", exc_info=True)


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
