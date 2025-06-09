from fastapi import APIRouter, HTTPException, Query, Depends, status
from typing import Optional, Dict, Any

from app.models.autohub import AutohubResponse, AutohubError
from app.services.autohub_service import AutohubService
from app.core.logging import get_logger

logger = get_logger("autohub_demo")

router = APIRouter()


# Dependency для получения сервиса
def get_autohub_service() -> AutohubService:
    return AutohubService()


@router.get(
    "/demo",
    response_model=AutohubResponse,
    summary="Демо данные с увеличенным количеством автомобилей",
    description="Возвращает демо данные, симулирующие большой список автомобилей",
)
async def get_demo_cars(
    count: int = Query(
        20, description="Количество автомобилей для генерации", ge=1, le=100
    ),
    service: AutohubService = Depends(get_autohub_service),
) -> AutohubResponse:
    """
    Возвращает демо данные для демонстрации возможностей API

    Генерирует указанное количество автомобилей на основе тестовых данных
    """
    try:
        logger.info(f"Генерация демо данных: {count} автомобилей")

        # Получаем базовые тестовые данные
        base_response = service.get_test_data()

        if not base_response.success or not base_response.cars:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось загрузить базовые данные для демо",
            )

        # Генерируем больше автомобилей на основе базовых
        demo_cars = []
        base_cars = base_response.cars

        for i in range(count):
            base_car = base_cars[i % len(base_cars)]

            # Создаём вариацию автомобиля
            demo_car_dict = base_car.model_dump()
            demo_car_dict["car_id"] = f"DEMO{i+1:04d}"
            demo_car_dict["auction_number"] = str(1000 + i)

            # Варьируем цены
            if demo_car_dict["starting_price"]:
                price_variation = (i * 137) % 1000  # Простая формула для вариации
                demo_car_dict["starting_price"] += price_variation

            # Варьируем годы
            if demo_car_dict["year"]:
                year_variation = (i % 10) - 5  # ±5 лет
                demo_car_dict["year"] = max(
                    2000, demo_car_dict["year"] + year_variation
                )

            from app.models.autohub import AutohubCar

            demo_cars.append(AutohubCar(**demo_car_dict))

        return AutohubResponse(
            success=True,
            message=f"Демо данные: {len(demo_cars)} автомобилей",
            total_count=len(demo_cars),
            cars=demo_cars,
        )

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Ошибка при генерации демо данных: {str(e)}"
        logger.error(error_msg)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_msg
        )

    finally:
        # Закрываем сервис
        service.close()
