from contextlib import asynccontextmanager
import os
from pathlib import Path
import secrets

from dotenv import load_dotenv
from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, ORJSONResponse
from starlette.middleware.gzip import GZipMiddleware
import uvicorn

# Hydrate os.environ from the repo-local .env BEFORE any app.* import: modules
# such as app.services.glovis_transport read secret-managed variables straight
# from os.environ, and pydantic-settings' env_file fills only the Settings
# object — it never exports to os.environ. override=False keeps real
# environment variables (Render dashboard) authoritative; when no .env file is
# deployed (production) this call is a no-op.
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=False)

from app.routes import (  # noqa: E402 — env hydration must precede app imports
    autohub,
    autohub_demo,
    lotte,
    lotte_filters,
    kcar,
    enhanced_lotte,
    heydealer,
    heydealer_filters,
    glovis,
    ssancar,
    bikemart,
    encar,
    encar_proxy,
    encar_truck,
    sk_auction,
    pan_auto,
    customs,
    green_equipment,
    happycar,
    exchange_rate,
    diagnostics,
)
from app.core.config import get_settings  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.core.scheduler import start_scheduler, stop_scheduler  # noqa: E402

# Настройка логирования
setup_logging()

# Настройки приложения
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: eagerly init services, start background warming."""
    # Eagerly initialise service singletons so the first user request
    # doesn't pay the initialisation cost.
    from app.core.startup_checks import log_egress_configuration
    from app.routes.lotte import get_lotte_service
    from app.routes.lotte_filters import get_filter_service
    from app.routes.glovis import close_glovis_service
    from app.routes.encar_proxy import close_encar_proxy_client

    # Report missing egress variables before any route can 502 over them.
    log_egress_configuration()

    main_service = get_lotte_service()
    # Warm the filter singleton wired to the shared main service, so the first
    # /filters request reuses the proven authenticated session.
    get_filter_service(main_service)
    try:
        # Start background cache warming scheduler
        await start_scheduler()
        yield
    finally:
        # Stop scheduled work before closing the pooled provider sessions.
        try:
            await stop_scheduler()
        finally:
            await close_encar_proxy_client()
            close_glovis_service()


# Создание FastAPI приложения
app = FastAPI(
    title="AutoBaza Parser API",
    description="API для парсинга автомобильных аукционов",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

# GZip compression (before CORS to compress all responses)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение маршрутов
app.include_router(autohub.router, prefix="/api/v1/autohub", tags=["Autohub"])
# Demo routes should be under a different path to avoid conflicts
app.include_router(
    autohub_demo.router, prefix="/api/v1/autohub-demo", tags=["Autohub Demo"]
)
app.include_router(lotte.router, tags=["Lotte Auction"])
app.include_router(lotte_filters.router, tags=["Lotte Filters"])
app.include_router(kcar.router, tags=["KCar Auction"])

# Новые улучшенные маршруты
app.include_router(enhanced_lotte.router, tags=["Enhanced Lotte Auction V2"])
app.include_router(heydealer.router, prefix="/api/v1", tags=["HeyDealer Auction"])
app.include_router(
    heydealer_filters.router,
    prefix="/api/v1/heydealer/filters",
    tags=["HeyDealer Filters"],
)
# SSANCAR routes - Direct SSANCAR API without PLC wrapper
app.include_router(ssancar.router, tags=["SSANCAR Auction"])

# DB Auto Glovis routes - canonical Glovis provider contract
app.include_router(glovis.router, tags=["Glovis Auction"])

# Bikemart routes - Motorcycle marketplace
app.include_router(bikemart.router, prefix="/api/v1/bikemart", tags=["Bikemart"])

# Encar routes - Encar catalog
app.include_router(encar.router, prefix="/api/v1/encar", tags=["Encar"])

# Encar transparent proxy — used by the Next.js frontend to fetch catalog/nav
# data from api.encar.com through the backend's proxy pool.
app.include_router(encar_proxy.router, tags=["Encar Proxy"])

# Encar Truck routes - Trucks and special equipment
app.include_router(encar_truck.router, prefix="/api/v1/encar", tags=["Encar Trucks"])

# SK Auction routes - SK Car Rental Auction
app.include_router(sk_auction.router, tags=["SK Auction"])

# Pan-Auto routes - HP and Russian customs costs data
app.include_router(pan_auto.router, prefix="/api/v1/pan-auto", tags=["Pan-Auto"])

# Customs Calculator - server-to-server proxy for calcus.ru (turnkey HP flow)
app.include_router(customs.router, prefix="/api/v1/customs", tags=["Customs Calculator"])

# Green Heavy Equipment routes - 4396200.com heavy equipment marketplace
app.include_router(green_equipment.router, prefix="/api/v1/green", tags=["Green Heavy Equipment"])

# HappyCar Insurance Auction routes - Insurance salvage/scrap vehicles
app.include_router(happycar.router, prefix="/api/v1/happycar", tags=["HappyCar Insurance Auction"])

# SMMotors routes - Live USD/KRW and EUR/KRW from Naver
app.include_router(exchange_rate.router, prefix="/api/v1/smmotors", tags=["SMMotors"])

# Read-only deployment diagnostics - egress readiness by provider
app.include_router(diagnostics.router, prefix="/api/v1/diagnostics", tags=["Diagnostics"])


@app.get("/")
async def root():
    return {"message": "AutoBaza Parser API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Service is running"}


@app.get("/api/v1/cache/stats", tags=["Cache"])
async def cache_stats():
    """Get cache statistics for all services"""
    stats = []

    # Collect cache stats from each service that has _get_cache_stats
    try:
        from app.routes.kcar import kcar_service
        if kcar_service and hasattr(kcar_service, '_get_cache_stats'):
            stats.append(kcar_service._get_cache_stats())
    except Exception:
        pass

    try:
        from app.routes.lotte import get_lotte_service
        svc = get_lotte_service()
        if svc and hasattr(svc, '_get_cache_stats'):
            stats.append(svc._get_cache_stats())
    except Exception:
        pass

    try:
        from app.routes.heydealer import get_heydealer_service
        svc = get_heydealer_service()
        if svc and hasattr(svc, '_get_cache_stats'):
            stats.append(svc._get_cache_stats())
    except Exception:
        pass

    try:
        from app.routes.sk_auction import sk_auction_service
        if sk_auction_service and hasattr(sk_auction_service, '_get_cache_stats'):
            stats.append(sk_auction_service._get_cache_stats())
    except Exception:
        pass

    try:
        from app.routes.ssancar import get_ssancar_service
        svc = get_ssancar_service()
        if svc and hasattr(svc, '_get_cache_stats'):
            stats.append(svc._get_cache_stats())
    except Exception:
        pass

    try:
        from app.routes.glovis import get_existing_glovis_service
        svc = get_existing_glovis_service()
        if svc is not None:
            stats.append(svc.get_cache_stats())
    except Exception:
        pass

    try:
        from app.routes.autohub import get_autohub_service
        svc = get_autohub_service()
        if svc and hasattr(svc, '_get_cache_stats'):
            stats.append(svc._get_cache_stats())
    except Exception:
        pass

    try:
        from app.routes.happycar import get_happycar_service
        svc = get_happycar_service()
        if svc and hasattr(svc, '_get_cache_stats'):
            stats.append(svc._get_cache_stats())
    except Exception:
        pass

    return {"services": stats, "total_services": len(stats)}


@app.post("/api/v1/cache/clear", tags=["Cache"])
async def clear_cache():
    """Clear all service caches"""
    cleared = []

    try:
        from app.routes.kcar import kcar_service
        if kcar_service and hasattr(kcar_service, '_cache'):
            kcar_service._cache.clear()
            kcar_service._cache_hits = 0
            kcar_service._cache_misses = 0
            cleared.append("KCar")
    except Exception:
        pass

    try:
        from app.routes.lotte import get_lotte_service
        svc = get_lotte_service()
        if svc and hasattr(svc, '_clear_cache'):
            svc._clear_cache()
            cleared.append("Lotte")
    except Exception:
        pass

    try:
        from app.routes.heydealer import get_heydealer_service
        svc = get_heydealer_service()
        if svc and hasattr(svc, '_clear_cache'):
            svc._clear_cache()
            cleared.append("HeyDealer")
    except Exception:
        pass

    try:
        from app.routes.sk_auction import sk_auction_service
        if sk_auction_service and hasattr(sk_auction_service, '_cache'):
            sk_auction_service._cache.clear()
            sk_auction_service._cache_hits = 0
            sk_auction_service._cache_misses = 0
            cleared.append("SK Auction")
    except Exception:
        pass

    try:
        from app.routes.ssancar import get_ssancar_service
        svc = get_ssancar_service()
        if svc and hasattr(svc, '_cache'):
            svc._cache.clear()
            svc._cache_hits = 0
            svc._cache_misses = 0
            cleared.append("SSANCAR")
    except Exception:
        pass

    try:
        from app.routes.autohub import get_autohub_service
        svc = get_autohub_service()
        if svc and hasattr(svc, '_cache'):
            svc._cache.clear()
            svc._cache_hits = 0
            svc._cache_misses = 0
            cleared.append("Autohub")
    except Exception:
        pass

    try:
        from app.routes.happycar import get_happycar_service
        svc = get_happycar_service()
        if svc and hasattr(svc, '_cache'):
            svc._cache.clear()
            svc._cache_hits = 0
            svc._cache_misses = 0
            cleared.append("HappyCar")
    except Exception:
        pass

    return {"cleared": cleared, "message": f"Cleared cache for {len(cleared)} services"}


def _glovis_admin_error(
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": {
                "code": code,
                "message": message,
                "retryable": False,
            }
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/v1/internal/glovis/cache/clear", tags=["Internal Cache"])
async def clear_glovis_cache_internal(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Clear only Glovis cache after secret-managed admin authorization."""
    expected = os.getenv("GLOVIS_CACHE_ADMIN_TOKEN", "")
    if not expected:
        return _glovis_admin_error(
            status_code=503,
            code="admin_unavailable",
            message="Glovis cache administration is not configured",
        )
    provided_bytes = (x_admin_token or "").encode("utf-8")
    expected_bytes = expected.encode("utf-8")
    if not secrets.compare_digest(provided_bytes, expected_bytes):
        return _glovis_admin_error(
            status_code=403,
            code="forbidden",
            message="Forbidden",
        )

    from app.routes.glovis import get_existing_glovis_service

    service = get_existing_glovis_service()
    if service is not None:
        service.clear_cache()
    return JSONResponse(
        content={"cleared": service is not None, "service": "Glovis"},
        headers={"Cache-Control": "no-store"},
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
