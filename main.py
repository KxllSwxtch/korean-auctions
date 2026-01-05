from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
)
from app.core.config import get_settings
from app.core.logging import setup_logging

# Настройка логирования
setup_logging()

# Настройки приложения
settings = get_settings()

# Создание FastAPI приложения
app = FastAPI(
    title="AutoBaza Parser API",
    description="API для парсинга автомобильных аукционов",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

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


@app.get("/")
async def root():
    return {"message": "AutoBaza Parser API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Service is running"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
