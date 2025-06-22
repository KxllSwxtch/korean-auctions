from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.routes import (
    autohub,
    autohub_demo,
    lotte,
    kcar,
    glovis,
    enhanced_lotte,
    glovis_detail,
    glovis_windows_auth,
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
app.include_router(
    autohub_demo.router, prefix="/api/v1/autohub/cars", tags=["Autohub Demo"]
)
app.include_router(lotte.router, tags=["Lotte Auction"])
app.include_router(kcar.router, tags=["KCar Auction"])
app.include_router(glovis.router, tags=["Glovis Auction"])

# Новые улучшенные маршруты
app.include_router(enhanced_lotte.router, tags=["Enhanced Lotte Auction V2"])
app.include_router(
    glovis_detail.router, prefix="/api/v1/glovis", tags=["Glovis Car Details"]
)
app.include_router(
    glovis_windows_auth.router, prefix="/api/v1", tags=["Glovis Windows Auth"]
)


@app.get("/")
async def root():
    return {"message": "AutoBaza Parser API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Service is running"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
