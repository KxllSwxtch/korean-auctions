from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query, HTTPException, Depends, Body
from fastapi.responses import JSONResponse

from app.models.lotte_filters import (
    LotteFilterRequest,
    LotteManufacturersResponse,
    LotteModelsResponse,
    LotteCarGroupsResponse,
    LotteMPriceCarsResponse,
    LotteFilterError,
)
from app.services.lotte_filter_service import LotteFilterService
from app.core.logging import logger

router = APIRouter(prefix="/api/v1/lotte/filters", tags=["Lotte Filters"])

# Глобальный экземпляр сервиса
_filter_service = None


def get_filter_service() -> LotteFilterService:
    """Dependency для получения сервиса фильтров Lotte"""
    global _filter_service
    if _filter_service is None:
        _filter_service = LotteFilterService()
    return _filter_service


@router.get("/manufacturers", response_model=LotteManufacturersResponse)
async def get_manufacturers(service: LotteFilterService = Depends(get_filter_service)):
    """
    Получение списка всех производителей автомобилей Lotte

    Возвращает:
    - Список производителей с кодами и названиями
    - Общее количество производителей
    - Статус операции

    Пример ответа:
    ```json
    {
        "success": true,
        "message": "Получено 37 производителей",
        "manufacturers": [
            {"code": "HD", "name": "현대자동차"},
            {"code": "KI", "name": "기아자동차"},
            {"code": "AD", "name": "AUDI"}
        ],
        "total_count": 37,
        "timestamp": "2025-01-21T10:30:00"
    }
    ```
    """
    try:
        logger.info("Запрос списка производителей Lotte")

        response = service.get_manufacturers()

        if not response.success:
            return JSONResponse(status_code=500, content=response.model_dump())

        logger.info(f"Возвращено {response.total_count} производителей")
        return response

    except Exception as e:
        logger.error(f"Ошибка при получении производителей: {e}")
        error_response = LotteFilterError(
            error_code="MANUFACTURERS_ERROR",
            message=f"Ошибка получения производителей: {str(e)}",
            timestamp=datetime.now().isoformat(),
        )
        return JSONResponse(status_code=500, content=error_response.model_dump())


@router.get("/models", response_model=LotteModelsResponse)
async def get_models(
    manufacturer_code: str = Query(
        ..., description="Код производителя (например, 'AD' для Audi)"
    ),
    service: LotteFilterService = Depends(get_filter_service),
):
    """
    Получение списка моделей автомобилей для указанного производителя

    Параметры:
    - manufacturer_code: Код производителя (обязательный)

    Возвращает:
    - Список моделей для указанного производителя
    - Код производителя
    - Общее количество моделей

    Пример запроса:
    ```
    GET /api/v1/lotte/filters/models?manufacturer_code=AD
    ```

    Пример ответа:
    ```json
    {
        "success": true,
        "message": "Получено 20 моделей для AD",
        "models": [
            {"code": "AD001", "name": "아우디 A3", "manufacturer_code": "AD"},
            {"code": "AD004", "name": "아우디 A6", "manufacturer_code": "AD"}
        ],
        "manufacturer_code": "AD",
        "total_count": 20,
        "timestamp": "2025-01-21T10:30:00"
    }
    ```
    """
    try:
        logger.info(f"Запрос моделей для производителя {manufacturer_code}")

        if not manufacturer_code or len(manufacturer_code) < 1:
            raise HTTPException(
                status_code=400, detail="Код производителя не может быть пустым"
            )

        response = service.get_models(manufacturer_code)

        if not response.success:
            return JSONResponse(status_code=500, content=response.model_dump())

        logger.info(
            f"Возвращено {response.total_count} моделей для {manufacturer_code}"
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении моделей для {manufacturer_code}: {e}")
        error_response = LotteFilterError(
            error_code="MODELS_ERROR",
            message=f"Ошибка получения моделей для {manufacturer_code}: {str(e)}",
            timestamp=datetime.now().isoformat(),
        )
        return JSONResponse(status_code=500, content=error_response.model_dump())


@router.get("/car-groups", response_model=LotteCarGroupsResponse)
async def get_car_groups(
    model_code: str = Query(
        ..., description="Код модели (например, 'AD004' для Audi A6)"
    ),
    service: LotteFilterService = Depends(get_filter_service),
):
    """
    Получение списка групп автомобилей для указанной модели

    Параметры:
    - model_code: Код модели (обязательный)

    Возвращает:
    - Список групп автомобилей для указанной модели
    - Код модели
    - Общее количество групп

    Пример запроса:
    ```
    GET /api/v1/lotte/filters/car-groups?model_code=AD004
    ```

    Пример ответа:
    ```json
    {
        "success": true,
        "message": "Получено 1 групп для AD004",
        "car_groups": [
            {"code": "AD004001", "name": "아우디 A6", "model_code": "AD004"}
        ],
        "model_code": "AD004",
        "total_count": 1,
        "timestamp": "2025-01-21T10:30:00"
    }
    ```
    """
    try:
        logger.info(f"Запрос групп автомобилей для модели {model_code}")

        if not model_code or len(model_code) < 1:
            raise HTTPException(
                status_code=400, detail="Код модели не может быть пустым"
            )

        response = service.get_car_groups(model_code)

        if not response.success:
            return JSONResponse(status_code=500, content=response.model_dump())

        logger.info(f"Возвращено {response.total_count} групп для {model_code}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении групп для {model_code}: {e}")
        error_response = LotteFilterError(
            error_code="CAR_GROUPS_ERROR",
            message=f"Ошибка получения групп для {model_code}: {str(e)}",
            timestamp=datetime.now().isoformat(),
        )
        return JSONResponse(status_code=500, content=error_response.model_dump())


@router.get("/mprice-cars", response_model=LotteMPriceCarsResponse)
async def get_mprice_cars(
    car_group_code: str = Query(
        ..., description="Код группы автомобилей (например, 'AD004001')"
    ),
    service: LotteFilterService = Depends(get_filter_service),
):
    """
    Получение списка подмоделей с ценами для указанной группы автомобилей

    Параметры:
    - car_group_code: Код группы автомобилей (обязательный)

    Возвращает:
    - Список подмоделей с ценами для указанной группы
    - Код группы автомобилей
    - Общее количество подмоделей

    Пример запроса:
    ```
    GET /api/v1/lotte/filters/mprice-cars?car_group_code=AD004001
    ```

    Пример ответа:
    ```json
    {
        "success": true,
        "message": "Получено 50 подмоделей для AD004001",
        "mprice_cars": [
            {
                "code": "0000002309",
                "name": "AUDI A6 (D) 2.0 35 TDI DYNAMIC",
                "car_group_code": "AD004001"
            }
        ],
        "car_group_code": "AD004001",
        "total_count": 50,
        "timestamp": "2025-01-21T10:30:00"
    }
    ```
    """
    try:
        logger.info(f"Запрос подмоделей для группы {car_group_code}")

        if not car_group_code or len(car_group_code) < 1:
            raise HTTPException(
                status_code=400, detail="Код группы автомобилей не может быть пустым"
            )

        response = service.get_mprice_cars(car_group_code)

        if not response.success:
            return JSONResponse(status_code=500, content=response.model_dump())

        logger.info(
            f"Возвращено {response.total_count} подмоделей для {car_group_code}"
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении подмоделей для {car_group_code}: {e}")
        error_response = LotteFilterError(
            error_code="MPRICE_CARS_ERROR",
            message=f"Ошибка получения подмоделей для {car_group_code}: {str(e)}",
            timestamp=datetime.now().isoformat(),
        )
        return JSONResponse(status_code=500, content=error_response.model_dump())


@router.post("/search")
async def search_cars_with_filters(
    filter_request: LotteFilterRequest = Body(..., description="Параметры фильтрации"),
    service: LotteFilterService = Depends(get_filter_service),
):
    """
    Поиск автомобилей с применением фильтров

    Принимает объект с параметрами фильтрации и возвращает список автомобилей,
    соответствующих указанным критериям.

    Параметры фильтрации:
    - manufacturer_code: Код производителя
    - model_code: Код модели
    - car_group_codes: Список кодов групп автомобилей
    - mprice_car_codes: Список кодов подмоделей
    - auction_date: Дата аукциона (YYYYMMDD)
    - min_price, max_price: Ценовой диапазон
    - min_year, max_year: Диапазон годов выпуска
    - fuel_code: Код типа топлива
    - transmission_code: Код трансмиссии
    - page, per_page: Параметры пагинации

    Пример запроса:
    ```json
    {
        "manufacturer_code": "AD",
        "model_code": "AD004",
        "car_group_codes": ["AD004001"],
        "mprice_car_codes": ["0000002309", "0000002310"],
        "min_price": 1000,
        "max_price": 5000,
        "min_year": 2018,
        "max_year": 2023,
        "page": 1,
        "per_page": 20
    }
    ```
    """
    try:
        logger.info(f"Поиск автомобилей с фильтрами: {filter_request.model_dump()}")

        # Выполняем поиск через сервис
        search_result = service.search_cars(filter_request)

        if not search_result.get("success", False):
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error_code": search_result.get("error_code", "SEARCH_FAILED"),
                    "message": search_result.get("message", "Ошибка поиска"),
                    "filter_request": filter_request.model_dump(),
                    "timestamp": datetime.now().isoformat(),
                },
            )

        # Возвращаем результат поиска
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": search_result.get("message", "Поиск выполнен успешно"),
                "html_length": search_result.get("total_length", 0),
                "search_params": search_result.get("search_params", {}),
                "filter_request": filter_request.model_dump(),
                "timestamp": datetime.now().isoformat(),
                "note": "HTML содержимое можно получить через отдельный endpoint для парсинга результатов",
            },
        )

    except Exception as e:
        logger.error(f"Ошибка при поиске с фильтрами: {e}")
        error_response = LotteFilterError(
            error_code="SEARCH_ERROR",
            message=f"Ошибка поиска с фильтрами: {str(e)}",
            timestamp=datetime.now().isoformat(),
        )
        return JSONResponse(status_code=500, content=error_response.model_dump())


@router.delete("/cache")
async def clear_cache(service: LotteFilterService = Depends(get_filter_service)):
    """
    Очистка кэша фильтров

    Удаляет все закэшированные данные фильтров.
    Полезно для принудительного обновления данных.

    Возвращает:
    - Статус операции
    - Сообщение об успешной очистке
    """
    try:
        service.clear_cache()
        return {
            "success": True,
            "message": "Кэш фильтров успешно очищен",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Ошибка при очистке кэша: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error_code": "CACHE_CLEAR_ERROR",
                "message": f"Ошибка очистки кэша: {str(e)}",
                "timestamp": datetime.now().isoformat(),
            },
        )
