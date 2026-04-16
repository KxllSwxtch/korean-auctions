from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from starlette.middleware.gzip import GZipMiddleware
import uvicorn

from app.routes import (
    autohub,
    autohub_demo,
    lotte,
    lotte_filters,
    kcar,
    enhanced_lotte,
    heydealer,
    heydealer_filters,
    ssancar,
    bikemart,
    encar,
    encar_truck,
    sk_auction,
    pan_auto,
    green_equipment,
    happycar,
    exchange_rate,
)
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.scheduler import start_scheduler, stop_scheduler

# Настройка логирования
setup_logging()

# Настройки приложения
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: eagerly init services, start background warming."""
    # Eagerly initialise service singletons so the first user request
    # doesn't pay the initialisation cost.
    from app.routes.lotte import get_lotte_service
    get_lotte_service()

    # Start background cache warming scheduler
    await start_scheduler()

    yield

    # Shutdown
    await stop_scheduler()


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

# Bikemart routes - Motorcycle marketplace
app.include_router(bikemart.router, prefix="/api/v1/bikemart", tags=["Bikemart"])

# Encar routes - Encar catalog
app.include_router(encar.router, prefix="/api/v1/encar", tags=["Encar"])

# Encar Truck routes - Trucks and special equipment
app.include_router(encar_truck.router, prefix="/api/v1/encar", tags=["Encar Trucks"])

# SK Auction routes - SK Car Rental Auction
app.include_router(sk_auction.router, tags=["SK Auction"])

# Pan-Auto routes - HP and Russian customs costs data
app.include_router(pan_auto.router, prefix="/api/v1/pan-auto", tags=["Pan-Auto"])

# Green Heavy Equipment routes - 4396200.com heavy equipment marketplace
app.include_router(green_equipment.router, prefix="/api/v1/green", tags=["Green Heavy Equipment"])

# HappyCar Insurance Auction routes - Insurance salvage/scrap vehicles
app.include_router(happycar.router, prefix="/api/v1/happycar", tags=["HappyCar Insurance Auction"])

# SMMotors routes - Live USD/KRW and EUR/KRW from Naver
app.include_router(exchange_rate.router, prefix="/api/v1/smmotors", tags=["SMMotors"])


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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
