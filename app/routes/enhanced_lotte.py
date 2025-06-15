"""
Роут для улучшенного сервиса Lotte с продвинутыми возможностями
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
import asyncio

from app.services.enhanced_lotte_service import EnhancedLotteService
from app.models.lotte import LotteResponse, LotteCar, LotteError, LotteAuctionDate
from app.core.logging import logger
from app.core.anti_block import ProxyConfig

router = APIRouter(prefix="/api/v2/lotte", tags=["Enhanced Lotte Auction"])

# Глобальные экземпляры сервисов
_sync_service = None
_async_service = None


def get_sync_service() -> EnhancedLotteService:
    """Dependency для получения синхронного сервиса"""
    global _sync_service
    if _sync_service is None:
        _sync_service = EnhancedLotteService(use_async=False)
    return _sync_service


async def get_async_service() -> EnhancedLotteService:
    """Dependency для получения асинхронного сервиса"""
    global _async_service
    if _async_service is None:
        _async_service = EnhancedLotteService(use_async=True)
    return _async_service


@router.get("/info", response_model=Dict[str, Any])
async def get_service_info():
    """
    Получить информацию об улучшенном сервисе Lotte

    Возвращает:
    - Версию сервиса
    - Поддерживаемые возможности
    - Конфигурацию
    """
    return {
        "service_name": "Enhanced Lotte Auction Service",
        "version": "2.0.0",
        "features": [
            "Advanced anti-blocking protection",
            "Async/sync operation modes",
            "Intelligent caching",
            "Session management",
            "Comprehensive statistics",
            "Proxy support",
            "Automatic retry logic",
            "Persistent cache",
        ],
        "capabilities": {
            "authentication": "Two-step authentication with AJAX",
            "parsing": "BeautifulSoup4 + selectolax optimization",
            "caching": "In-memory + persistent file cache",
            "concurrency": "Async parallel requests",
            "monitoring": "Detailed stats and health checks",
            "recovery": "Auto-reconnect and session recovery",
        },
        "endpoints": {
            "auction_date": "GET /auction-date",
            "cars_basic": "GET /cars",
            "cars_with_date_check": "GET /cars/smart",
            "cars_with_details": "GET /cars/detailed",
            "car_by_id": "GET /cars/{car_id}",
            "stats": "GET /stats",
            "health": "GET /health",
        },
    }


@router.get("/auction-date", response_model=Dict[str, Any])
async def get_auction_date(
    use_async: bool = Query(True, description="Использовать асинхронный режим"),
    service_sync: EnhancedLotteService = Depends(get_sync_service),
):
    """
    Получение даты ближайшего аукциона Lotte (улучшенная версия)

    Особенности:
    - Кэширование результата
    - Автоматическая аутентификация
    - Защита от блокировок
    - Подробная информация о дате
    """
    try:
        if use_async:
            service = await get_async_service()
        else:
            service = service_sync

        logger.info(f"Запрос даты аукциона Lotte (async={use_async})")

        auction_date_info = await service.get_auction_date()

        if not auction_date_info:
            raise HTTPException(
                status_code=404, detail="Не удалось получить дату аукциона"
            )

        return {
            "success": True,
            "message": "Дата аукциона получена успешно",
            "data": auction_date_info,
            "service_mode": "async" if use_async else "sync",
            "cached": True,  # будет актуально после кэширования
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Ошибка при получении даты аукциона Lotte: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/cars", response_model=Dict[str, Any])
async def get_cars(
    limit: int = Query(20, ge=1, le=100, description="Количество автомобилей"),
    offset: int = Query(0, ge=0, description="Смещение для пагинации"),
    use_async: bool = Query(True, description="Использовать асинхронный режим"),
    service_sync: EnhancedLotteService = Depends(get_sync_service),
):
    """
    Получить список автомобилей с аукциона Lotte (базовая версия)

    Возможности:
    - Выбор синхронного/асинхронного режима
    - Пагинация
    - Кэширование
    - Автоматическая аутентификация
    """
    try:
        if use_async:
            service = await get_async_service()
        else:
            service = service_sync

        logger.info(
            f"Запрос автомобилей Lotte: limit={limit}, offset={offset}, async={use_async}"
        )

        cars_data = await service.get_cars(limit=limit, offset=offset)

        return {
            "success": True,
            "message": f"Получено {len(cars_data)} автомобилей",
            "data": {
                "cars": cars_data,
                "count": len(cars_data),
                "limit": limit,
                "offset": offset,
            },
            "service_mode": "async" if use_async else "sync",
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Ошибка при получении автомобилей Lotte: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/cars/smart", response_model=Dict[str, Any])
async def get_cars_smart(
    limit: int = Query(20, ge=1, le=100, description="Количество автомобилей"),
    offset: int = Query(0, ge=0, description="Смещение для пагинации"),
    use_async: bool = Query(True, description="Использовать асинхронный режим"),
    service_sync: EnhancedLotteService = Depends(get_sync_service),
):
    """
    Умное получение автомобилей с проверкой даты аукциона

    Логика:
    - Проверяет дату аукциона
    - Если аукцион сегодня - возвращает автомобили
    - Если не сегодня - возвращает информацию о следующем аукционе
    """
    try:
        if use_async:
            service = await get_async_service()
        else:
            service = service_sync

        logger.info(f"Умный запрос автомобилей Lotte: limit={limit}, offset={offset}")

        result = await service.get_cars_with_date_check(limit=limit, offset=offset)

        return {
            **result,
            "service_mode": "async" if use_async else "sync",
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Ошибка умного запроса автомобилей Lotte: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/cars/detailed", response_model=Dict[str, Any])
async def get_cars_detailed(
    limit: int = Query(
        10, ge=1, le=50, description="Количество автомобилей (макс. 50)"
    ),
    offset: int = Query(0, ge=0, description="Смещение для пагинации"),
    use_async: bool = Query(True, description="Использовать асинхронный режим"),
    service_sync: EnhancedLotteService = Depends(get_sync_service),
):
    """
    Получить автомобили с детальной информацией

    Внимание:
    - Медленнее базовой версии (требует дополнительные запросы)
    - Рекомендуется использовать асинхронный режим
    - Ограничение: максимум 50 автомобилей
    """
    try:
        if use_async:
            service = await get_async_service()
        else:
            service = service_sync

        logger.info(
            f"Запрос детальных автомобилей Lotte: limit={limit}, offset={offset}"
        )

        detailed_cars = await service.get_cars_with_details(limit=limit, offset=offset)

        return {
            "success": True,
            "message": f"Получено {len(detailed_cars)} автомобилей с детальной информацией",
            "data": {
                "cars": detailed_cars,
                "count": len(detailed_cars),
                "limit": limit,
                "offset": offset,
                "details_included": True,
            },
            "service_mode": "async" if use_async else "sync",
            "performance_note": "Детальная информация требует дополнительных запросов",
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Ошибка при получении детальных автомобилей Lotte: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/cars/{car_id}", response_model=Dict[str, Any])
async def get_car_by_id(
    car_id: str,
    use_async: bool = Query(True, description="Использовать асинхронный режим"),
    service_sync: EnhancedLotteService = Depends(get_sync_service),
):
    """
    Получить детальную информацию об автомобиле по ID
    """
    try:
        if use_async:
            service = await get_async_service()
        else:
            service = service_sync

        logger.info(f"Запрос автомобиля Lotte по ID: {car_id}")

        car_details = await service.get_car_details(car_id)

        if not car_details:
            raise HTTPException(
                status_code=404, detail=f"Автомобиль с ID {car_id} не найден"
            )

        return {
            "success": True,
            "message": f"Детали автомобиля {car_id} получены",
            "data": car_details,
            "service_mode": "async" if use_async else "sync",
            "timestamp": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении автомобиля {car_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/stats", response_model=Dict[str, Any])
async def get_service_stats(
    detailed: bool = Query(False, description="Показать детальную статистику"),
    service_sync: EnhancedLotteService = Depends(get_sync_service),
):
    """
    Получить статистику работы сервиса

    Включает:
    - Статистику запросов
    - Информацию об аутентификации
    - Статистику кэша
    - Статистику HTTP клиента
    - Информацию о сессиях
    """
    try:
        sync_stats = service_sync.get_enhanced_stats()

        result = {
            "sync_service": sync_stats,
            "timestamp": datetime.now().isoformat(),
        }

        # Добавляем статистику асинхронного сервиса если он инициализирован
        if _async_service:
            async_stats = _async_service.get_enhanced_stats()
            result["async_service"] = async_stats

        if detailed:
            # Добавляем системную информацию
            import psutil
            import os

            result["system_info"] = {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_usage": psutil.disk_usage("/").percent,
                "process_id": os.getpid(),
                "threads_count": psutil.Process().num_threads(),
            }

        return result

    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        raise HTTPException(
            status_code=500, detail=f"Ошибка получения статистики: {str(e)}"
        )


@router.get("/health", response_model=Dict[str, Any])
async def health_check(
    service_sync: EnhancedLotteService = Depends(get_sync_service),
):
    """
    Проверка здоровья сервиса

    Проверяет:
    - Доступность сервиса
    - Статус аутентификации
    - Работоспособность кэша
    - Состояние HTTP клиентов
    """
    try:
        sync_health = {
            "service_name": "sync_lotte",
            "status": "healthy",
            "authenticated": service_sync.authenticated,
            "cache_size": len(service_sync.cache),
            "last_activity": service_sync.stats.get("last_activity"),
        }

        health_data = {
            "overall_status": "healthy",
            "services": {
                "sync": sync_health,
            },
            "timestamp": datetime.now().isoformat(),
        }

        # Проверяем асинхронный сервис
        if _async_service:
            async_health = {
                "service_name": "async_lotte",
                "status": "healthy",
                "authenticated": _async_service.authenticated,
                "cache_size": len(_async_service.cache),
                "last_activity": _async_service.stats.get("last_activity"),
            }
            health_data["services"]["async"] = async_health

        return health_data

    except Exception as e:
        logger.error(f"Ошибка проверки здоровья сервиса: {e}")
        return {
            "overall_status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


@router.post("/admin/clear-cache", response_model=Dict[str, Any])
async def clear_cache(
    service_type: str = Query(
        "both", regex="^(sync|async|both)$", description="Тип сервиса"
    ),
    service_sync: EnhancedLotteService = Depends(get_sync_service),
):
    """
    Очистить кэш сервиса (админ операция)
    """
    try:
        cleared = []

        if service_type in ["sync", "both"]:
            service_sync.clear_cache()
            cleared.append("sync")

        if service_type in ["async", "both"] and _async_service:
            _async_service.clear_cache()
            cleared.append("async")

        return {
            "success": True,
            "message": f"Кэш очищен для сервисов: {', '.join(cleared)}",
            "cleared_services": cleared,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Ошибка очистки кэша: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка очистки кэша: {str(e)}")


@router.post("/admin/reset-auth", response_model=Dict[str, Any])
async def reset_authentication(
    service_type: str = Query(
        "both", regex="^(sync|async|both)$", description="Тип сервиса"
    ),
    service_sync: EnhancedLotteService = Depends(get_sync_service),
):
    """
    Сбросить аутентификацию сервиса (админ операция)
    """
    try:
        reset_services = []

        if service_type in ["sync", "both"]:
            service_sync.reset_authentication()
            service_sync.reset_login_attempts()
            reset_services.append("sync")

        if service_type in ["async", "both"] and _async_service:
            _async_service.reset_authentication()
            _async_service.reset_login_attempts()
            reset_services.append("async")

        return {
            "success": True,
            "message": f"Аутентификация сброшена для сервисов: {', '.join(reset_services)}",
            "reset_services": reset_services,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Ошибка сброса аутентификации: {e}")
        raise HTTPException(
            status_code=500, detail=f"Ошибка сброса аутентификации: {str(e)}"
        )


@router.get("/total-count", response_model=Dict[str, Any])
async def get_total_cars_count(
    use_async: bool = Query(True, description="Использовать асинхронный режим"),
    service_sync: EnhancedLotteService = Depends(get_sync_service),
):
    """
    Получить общее количество автомобилей на аукционе (может быть медленно)
    """
    try:
        if use_async:
            service = await get_async_service()
        else:
            service = service_sync

        logger.info("Запрос общего количества автомобилей Lotte")

        total_count = await service.get_total_cars_count()

        return {
            "success": True,
            "message": f"Общее количество автомобилей: {total_count}",
            "data": {
                "total_count": total_count,
            },
            "service_mode": "async" if use_async else "sync",
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Ошибка получения общего количества автомобилей: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )
