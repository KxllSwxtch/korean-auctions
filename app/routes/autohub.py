from fastapi import APIRouter, HTTPException, Query, Depends, status
from typing import Optional, Dict, Any
import asyncio

from app.models.autohub import AutohubResponse, AutohubError
from app.services.autohub_service import AutohubService
from app.core.logging import get_logger

logger = get_logger("autohub_routes")

router = APIRouter()


# Dependency для получения сервиса
def get_autohub_service() -> AutohubService:
    return AutohubService()


@router.get(
    "/cars",
    response_model=AutohubResponse,
    summary="Получить список автомобилей",
    description="Получает список автомобилей с аукциона Autohub",
    responses={
        200: {
            "description": "Успешно получен список автомобилей",
            "model": AutohubResponse,
        },
        500: {"description": "Внутренняя ошибка сервера", "model": AutohubError},
    },
)
async def get_cars(
    page: Optional[int] = Query(1, description="Номер страницы", ge=1),
    limit: Optional[int] = Query(
        20, description="Количество автомобилей на странице", ge=1, le=100
    ),
    search: Optional[str] = Query(None, description="Поисковый запрос"),
    min_price: Optional[int] = Query(None, description="Минимальная цена"),
    max_price: Optional[int] = Query(None, description="Максимальная цена"),
    fuel_type: Optional[str] = Query(None, description="Тип топлива"),
    year_from: Optional[int] = Query(None, description="Год выпуска от"),
    year_to: Optional[int] = Query(None, description="Год выпуска до"),
    service: AutohubService = Depends(get_autohub_service),
) -> AutohubResponse:
    """
    Получает список автомобилей с аукциона Autohub

    - **page**: Номер страницы (по умолчанию 1)
    - **limit**: Количество автомобилей на странице (по умолчанию 20, максимум 100)
    - **search**: Поисковый запрос по названию автомобиля
    - **min_price**: Минимальная цена в манвонах
    - **max_price**: Максимальная цена в манвонах
    - **fuel_type**: Тип топлива (휘발유, 경유, 전기, 하이브리드)
    - **year_from**: Год выпуска от
    - **year_to**: Год выпуска до
    """
    try:
        logger.info(
            f"Получение списка автомобилей. Параметры: page={page}, limit={limit}"
        )

        # Подготавливаем параметры для запроса
        params = {}

        if search:
            params["search"] = search
        if min_price:
            params["min_price"] = min_price
        if max_price:
            params["max_price"] = max_price
        if fuel_type:
            params["fuel_type"] = fuel_type
        if year_from:
            params["year_from"] = year_from
        if year_to:
            params["year_to"] = year_to

        # Добавляем параметры пагинации
        params["page"] = page
        params["limit"] = limit

        # Получаем данные (пагинация выполняется на стороне сервера Autohub)
        response = await service.get_car_list(params)

        return response

    except Exception as e:
        error_msg = f"Ошибка при получении списка автомобилей: {str(e)}"
        logger.error(error_msg)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_msg
        )

    finally:
        # Закрываем сервис
        service.close()


@router.get(
    "/cars/test",
    response_model=AutohubResponse,
    summary="Получить тестовые данные",
    description="Возвращает тестовые данные для проверки парсера",
    responses={
        200: {
            "description": "Тестовые данные успешно получены",
            "model": AutohubResponse,
        },
        500: {
            "description": "Ошибка при получении тестовых данных",
            "model": AutohubError,
        },
    },
)
async def get_test_cars(
    service: AutohubService = Depends(get_autohub_service),
) -> AutohubResponse:
    """
    Возвращает тестовые данные для проверки работы парсера

    Использует локальный HTML файл для демонстрации возможностей парсера
    """
    try:
        logger.info("Получение тестовых данных")

        response = service.get_test_data()
        return response

    except Exception as e:
        error_msg = f"Ошибка при получении тестовых данных: {str(e)}"
        logger.error(error_msg)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_msg
        )

    finally:
        # Закрываем сервис
        service.close()


@router.get(
    "/cars/stats",
    summary="Статистика по автомобилям",
    description="Возвращает статистику по автомобилям на аукционе",
)
async def get_cars_stats(
    service: AutohubService = Depends(get_autohub_service),
) -> Dict[str, Any]:
    """
    Возвращает статистику по автомобилям

    Включает:
    - Общее количество автомобилей
    - Распределение по статусам
    - Средние цены
    - Популярные марки
    """
    try:
        logger.info("Получение статистики по автомобилям")

        # Получаем все автомобили
        response = await service.get_car_list()

        if not response.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.message,
            )

        cars = response.cars
        total_count = len(cars)

        # Подсчитываем статистику
        status_counts = {}
        fuel_type_counts = {}
        transmission_counts = {}
        prices = []
        brands = {}

        for car in cars:
            # Статусы
            status_counts[car.status.value] = status_counts.get(car.status.value, 0) + 1

            # Типы топлива
            fuel_type_counts[car.fuel_type.value] = (
                fuel_type_counts.get(car.fuel_type.value, 0) + 1
            )

            # Трансмиссия
            transmission_counts[car.transmission.value] = (
                transmission_counts.get(car.transmission.value, 0) + 1
            )

            # Цены
            if car.starting_price:
                prices.append(car.starting_price)

            # Марки (извлекаем из названия)
            brand = car.title.split()[0] if car.title else "Unknown"
            brands[brand] = brands.get(brand, 0) + 1

        # Вычисляем статистику по ценам
        avg_price = sum(prices) / len(prices) if prices else 0
        min_price = min(prices) if prices else 0
        max_price = max(prices) if prices else 0

        # Топ-5 брендов
        top_brands = sorted(brands.items(), key=lambda x: x[1], reverse=True)[:5]

        stats = {
            "total_cars": total_count,
            "status_distribution": status_counts,
            "fuel_type_distribution": fuel_type_counts,
            "transmission_distribution": transmission_counts,
            "price_stats": {
                "average": round(avg_price, 0),
                "minimum": min_price,
                "maximum": max_price,
                "count": len(prices),
            },
            "top_brands": [
                {"brand": brand, "count": count} for brand, count in top_brands
            ],
        }

        return stats

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Ошибка при получении статистики: {str(e)}"
        logger.error(error_msg)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_msg
        )

    finally:
        # Закрываем сервис
        service.close()


@router.get(
    "/auth/status",
    summary="Статус авторизации",
    description="Проверяет статус авторизации на сайте Autohub",
)
async def get_auth_status(
    service: AutohubService = Depends(get_autohub_service),
) -> Dict[str, Any]:
    """
    Проверяет и возвращает статус авторизации
    """
    try:
        logger.info("Проверка статуса авторизации")

        # Инициализируем сессию (включая авторизацию)
        auth_success = await service._initialize_session()

        return {
            "authenticated": auth_success,
            "username": service.settings.autohub_username,
            "base_url": service.settings.autohub_base_url,
            "message": (
                "✅ Авторизация успешна"
                if auth_success
                else "❌ Авторизация не удалась"
            ),
        }

    except Exception as e:
        logger.error(f"Ошибка при проверке авторизации: {e}")
        return {
            "authenticated": False,
            "username": None,
            "base_url": None,
            "message": f"❌ Ошибка: {str(e)}",
        }

    finally:
        # Закрываем сервис
        service.close()


@router.get(
    "/pagination/demo",
    summary="Демонстрация пагинации",
    description="Показывает работу пагинации на нескольких страницах",
)
async def pagination_demo(
    max_pages: int = Query(
        3, ge=1, le=5, description="Максимальное количество страниц для демонстрации"
    ),
    service: AutohubService = Depends(get_autohub_service),
) -> Dict[str, Any]:
    """
    Демонстрирует работу пагинации, показывая первые автомобили с нескольких страниц
    """
    try:
        logger.info(f"Демонстрация пагинации для {max_pages} страниц")

        pages_data = []

        for page_num in range(1, max_pages + 1):
            # Получаем данные страницы
            params = {"page": page_num, "limit": 20}
            response = await service.get_car_list(params)

            if response.success and response.cars:
                # Берём только первый автомобиль для демонстрации
                first_car = response.cars[0]
                page_info = {
                    "page": page_num,
                    "cars_total_on_page": len(response.cars),
                    "has_next_page": response.has_next_page,
                    "has_prev_page": response.has_prev_page,
                    "first_car": {
                        "car_id": first_car.car_id,
                        "title": first_car.title,
                        "year": first_car.year,
                        "price": first_car.starting_price,
                    },
                }
                pages_data.append(page_info)
            else:
                # Страница пустая или ошибка
                page_info = {
                    "page": page_num,
                    "cars_total_on_page": 0,
                    "has_next_page": False,
                    "has_prev_page": page_num > 1,
                    "error": (
                        response.message if not response.success else "Нет автомобилей"
                    ),
                }
                pages_data.append(page_info)
                break  # Прекращаем если дошли до пустой страницы

        return {
            "pagination_demo": True,
            "max_pages_requested": max_pages,
            "pages_processed": len(pages_data),
            "pages_data": pages_data,
            "summary": f"Успешно обработано {len(pages_data)} страниц пагинации",
        }

    except Exception as e:
        logger.error(f"Ошибка в демонстрации пагинации: {e}")
        return {"pagination_demo": False, "error": str(e), "pages_data": []}

    finally:
        # Закрываем сервис
        service.close()
