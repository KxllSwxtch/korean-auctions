#!/usr/bin/env python3
"""
SSANCAR Car Detail Routes

Маршруты для получения детальной информации об автомобилях SSANCAR.
Предоставляет endpoint для получения всей информации о конкретном автомобиле.
"""

from fastapi import APIRouter, HTTPException, Query
from app.services.glovis_service import GlovisService
from app.models.glovis import SSANCARCarDetailResponse
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/ssancar", tags=["SSANCAR Car Details"])


@router.get(
    "/car/{car_no}",
    response_model=SSANCARCarDetailResponse,
    summary="Получить детальную информацию об автомобиле",
    description="""
    Получает детальную информацию об автомобиле SSANCAR по его номеру.
    
    Возвращает:
    - Основную информацию (название, бренд, модель, Stock NO)
    - Технические характеристики (год, КПП, топливо, объем, пробег, оценка)
    - Все фотографии автомобиля
    - Информацию о цене и аукционе
    - Даты загрузки и начала аукциона
    - Ссылки на детальную страницу и менеджеров
    """,
)
async def get_car_detail(car_no: str):
    """
    Получает детальную информацию об автомобиле SSANCAR

    Args:
        car_no: Номер автомобиля SSANCAR (например: "1515765")

    Returns:
        SSANCARCarDetailResponse: Детальная информация об автомобиле

    Raises:
        HTTPException: При ошибках валидации или получения данных
    """
    try:
        logger.info(f"🚗 Запрос детальной информации для автомобиля: {car_no}")

        # Валидация car_no
        if not car_no or not car_no.strip():
            raise HTTPException(
                status_code=400, detail="Номер автомобиля (car_no) не может быть пустым"
            )

        # Создаем сервис
        service = GlovisService()

        # Получаем детальную информацию
        result = await service.get_ssancar_car_detail(car_no.strip())

        # Проверяем результат
        if not result.success:
            logger.warning(
                f"⚠️ Не удалось получить детали для автомобиля {car_no}: {result.message}"
            )
            raise HTTPException(
                status_code=404 if "не найден" in result.message.lower() else 500,
                detail=result.message,
            )

        logger.info(f"✅ Успешно получена детальная информация для автомобиля {car_no}")

        return result

    except HTTPException:
        # Перепрокидываем HTTP исключения как есть
        raise

    except Exception as e:
        logger.error(
            f"🚫 Неожиданная ошибка при получении деталей автомобиля {car_no}: {e}"
        )
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get(
    "/car/{car_no}/images",
    summary="Получить только изображения автомобиля",
    description="Получает только список URL изображений для указанного автомобиля",
)
async def get_car_images(car_no: str):
    """
    Получает только изображения автомобиля SSANCAR

    Args:
        car_no: Номер автомобиля SSANCAR

    Returns:
        dict: Список изображений автомобиля
    """
    try:
        logger.info(f"📸 Запрос изображений для автомобиля: {car_no}")

        if not car_no or not car_no.strip():
            raise HTTPException(
                status_code=400, detail="Номер автомобиля (car_no) не может быть пустым"
            )

        service = GlovisService()

        # Получаем полную информацию
        result = await service.get_ssancar_car_detail(car_no.strip())

        if not result.success or not result.car_detail:
            raise HTTPException(
                status_code=404,
                detail="Автомобиль не найден или изображения недоступны",
            )

        images_data = {
            "success": True,
            "car_no": car_no,
            "car_name": result.car_detail.car_name,
            "main_image": result.car_detail.main_image,
            "images": result.car_detail.images,
            "total_images": len(result.car_detail.images),
        }

        logger.info(
            f"✅ Найдено {len(result.car_detail.images)} изображений для автомобиля {car_no}"
        )

        return images_data

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"🚫 Ошибка при получении изображений автомобиля {car_no}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get(
    "/health",
    summary="Проверка работоспособности SSANCAR Detail API",
    description="Проверяет доступность SSANCAR и возможность получения детальной информации",
)
async def health_check():
    """Проверка работоспособности SSANCAR Detail API"""
    try:
        service = GlovisService()

        # Проверяем базовую доступность
        health_status = await service.health_check()

        return {
            "status": "healthy",
            "message": "SSANCAR Detail API работает нормально",
            "ssancar_available": health_status.get("ssancar_available", False),
            "detail_parsing": "available",
            "features": [
                "car_detail_by_car_no",
                "all_car_images",
                "technical_specifications",
                "auction_information",
                "price_information",
            ],
        }

    except Exception as e:
        logger.error(f"🚫 Ошибка health check: {e}")
        return {
            "status": "unhealthy",
            "message": f"Проблемы с SSANCAR Detail API: {str(e)}",
            "ssancar_available": False,
            "detail_parsing": "unavailable",
        }
