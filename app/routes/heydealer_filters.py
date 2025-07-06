"""
HeyDealer фильтры API - роуты для получения брендов, моделей, поколений и конфигураций
"""

import requests
from fastapi import APIRouter, HTTPException
from typing import List

from app.models.heydealer import (
    HeyDealerBrandsResponse,
    HeyDealerBrandDetailResponse,
    HeyDealerModelDetailResponse,
    HeyDealerGradeDetailResponse,
    HeyDealerListResponse,
    HeyDealerFilterParams,
    HeyDealerAdvancedFilterParams,
    HeyDealerFiltersResponse,
)
from app.parsers.heydealer_parser import HeyDealerParser
from app.services.heydealer_auth_service import heydealer_auth
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
parser = HeyDealerParser()

# Removed hardcoded headers and cookies - using auth service instead


@router.get("/brands", response_model=HeyDealerBrandsResponse)
async def get_brands():
    """Получить список всех брендов автомобилей"""
    try:
        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()
        
        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            raise HTTPException(
                status_code=401,
                detail="Ошибка авторизации HeyDealer"
            )
        
        params = {
            "type": "auction",
            "is_subscribed": "false",
            "is_retried": "false",
            "is_previously_bid": "false",
        }

        response = requests.get(
            "https://api.heydealer.com/v2/dealers/web/car_meta/brands/",
            params=params,
            headers=headers,
            cookies=cookies,
            timeout=30,
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"HeyDealer API error: {response.status_code}",
            )

        data = response.json()
        return parser.parse_brands(data)

    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)}")


@router.get(
    "/brands/{brand_hash_id}/models", response_model=HeyDealerBrandDetailResponse
)
async def get_brand_models(brand_hash_id: str):
    """Получить модели для указанного бренда"""
    try:
        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()
        
        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            raise HTTPException(
                status_code=401,
                detail="Ошибка авторизации HeyDealer"
            )
        
        params = {
            "type": "auction",
            "is_subscribed": "false",
            "is_retried": "false",
            "is_previously_bid": "false",
        }

        response = requests.get(
            f"https://api.heydealer.com/v2/dealers/web/car_meta/brands/{brand_hash_id}/",
            params=params,
            headers=headers,
            cookies=cookies,
            timeout=30,
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"HeyDealer API error: {response.status_code}",
            )

        response_data = response.json()
        return parser.parse_brand_detail(response_data)

    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)}")


@router.get(
    "/model-groups/{model_group_hash_id}/generations",
    response_model=HeyDealerModelDetailResponse,
)
async def get_model_generations(model_group_hash_id: str):
    """Получить поколения для указанной группы моделей"""
    try:
        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()
        
        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            raise HTTPException(
                status_code=401,
                detail="Ошибка авторизации HeyDealer"
            )
        
        params = {
            "type": "auction",
            "is_subscribed": "false",
            "is_retried": "false",
            "is_previously_bid": "false",
            "model_group": model_group_hash_id,
        }

        response = requests.get(
            f"https://api.heydealer.com/v2/dealers/web/car_meta/model_groups/{model_group_hash_id}/",
            params=params,
            headers=headers,
            cookies=cookies,
            timeout=30,
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"HeyDealer API error: {response.status_code}",
            )

        response_data = response.json()
        return parser.parse_model_detail(response_data)

    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)}")


@router.get(
    "/models/{model_hash_id}/configurations",
    response_model=HeyDealerGradeDetailResponse,
)
async def get_model_configurations(model_hash_id: str):
    """Получить конфигурации для указанной модели"""
    try:
        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()
        
        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            raise HTTPException(
                status_code=401,
                detail="Ошибка авторизации HeyDealer"
            )
        
        params = {
            "type": "auction",
            "is_subscribed": "false",
            "is_retried": "false",
            "is_previously_bid": "false",
            "model": model_hash_id,
        }

        response = requests.get(
            f"https://api.heydealer.com/v2/dealers/web/car_meta/models/{model_hash_id}/",
            params=params,
            headers=headers,
            cookies=cookies,
            timeout=30,
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"HeyDealer API error: {response.status_code}",
            )

        response_data = response.json()
        return parser.parse_grade_detail(response_data)

    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)}")


@router.get("/cars/search", response_model=HeyDealerListResponse)
async def search_cars(
    page: int = 1,
    type: str = "auction",
    is_subscribed: str = "false",
    is_retried: str = "false",
    is_previously_bid: str = "false",
    grade: str = None,
    order: str = "default",
):
    """Простой поиск автомобилей с основными параметрами (GET)"""
    try:
        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()
        
        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            raise HTTPException(
                status_code=401,
                detail="Ошибка авторизации HeyDealer"
            )
        
        params = {
            "page": str(page),
            "type": type,
            "is_subscribed": is_subscribed,
            "is_retried": is_retried,
            "is_previously_bid": is_previously_bid,
            "order": order,
        }

        if grade:
            params["grade"] = grade
            logger.info(f"🔍 Поиск автомобилей с grade={grade}")

        response = requests.get(
            "https://api.heydealer.com/v2/dealers/web/cars/",
            params=params,
            headers=headers,
            cookies=cookies,
            timeout=30,
        )

        if response.status_code == 200:
            data = response.json()
            return parser.parse_filtered_cars(data)
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"API request failed: {response.text}",
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")


@router.get("/filters", response_model=HeyDealerFiltersResponse)
async def get_available_filters():
    """Получить список всех доступных фильтров для поиска автомобилей"""
    try:
        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()
        
        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            raise HTTPException(
                status_code=401,
                detail="Ошибка авторизации HeyDealer"
            )
        
        response = requests.get(
            "https://api.heydealer.com/v2/dealers/web/auction_filter/",
            headers=headers,
            cookies=cookies,
            timeout=30,
        )

        if response.status_code == 200:
            data = response.json()
            return parser.parse_available_filters(data)
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"API request failed: {response.text}",
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")


@router.post("/cars/advanced-search", response_model=HeyDealerListResponse)
async def advanced_search_cars(filters: HeyDealerAdvancedFilterParams):
    """Расширенный поиск автомобилей с множественными фильтрами (POST)"""
    try:
        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()
        
        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            raise HTTPException(
                status_code=401,
                detail="Ошибка авторизации HeyDealer"
            )
        
        # Конвертируем Pydantic модель в словарь для отправки
        params = filters.dict(exclude_none=True)

        # Обрабатываем списковые параметры
        for key, value in params.items():
            if isinstance(value, list):
                params[key] = value  # requests автоматически обработает списки

        response = requests.get(
            "https://api.heydealer.com/v2/dealers/web/cars/",
            params=params,
            headers=headers,
            cookies=cookies,
            timeout=30,
        )

        if response.status_code == 200:
            data = response.json()
            return parser.parse_filtered_cars(data)
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"API request failed: {response.text}",
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")


@router.get("/cars/advanced-search", response_model=HeyDealerListResponse)
async def advanced_search_cars_get(
    # Базовые параметры
    page: int = 1,
    type: str = "auction",
    is_subscribed: str = "false",
    is_retried: str = "false",
    is_previously_bid: str = "false",
    order: str = "default",
    # Фильтры по автомобилю
    brand: str = None,
    model_group: str = None,
    model: str = None,
    grade: str = None,
    # Год выпуска
    min_year: int = None,
    max_year: int = None,
    # Пробег
    min_mileage: int = None,
    max_mileage: int = None,
    mileage_group: str = None,
    # Топливо (список через запятую)
    fuel: str = None,  # "gasoline,diesel"
    # Трансмиссия
    transmission: str = None,
    # Привод
    wheel_drive: str = None,
    # Тип кузова/сегмент (список через запятую)
    car_segment: str = None,  # "a,b,c"
    # Тип автомобиля
    car_type: str = None,
    # Местоположение (список через запятую)
    location_first_part: str = None,  # "9,101"
    # Способ оплаты (список через запятую)
    payment: str = None,  # "cash,finance_lease"
    # Дата одобрения
    min_approved_at: str = None,
    max_approved_at: str = None,
    # Аварийность
    accident_repairs_summary: str = None,
    accident_group: str = None,  # "minor,major"
    # История автомобиля
    my_car_accident_cost: str = None,
    owner_change_record: str = None,
    use_record: str = None,
    special_accident_record: str = None,
    # Работоспособность
    operation_availability: str = None,
):
    """Расширенный поиск автомобилей с множественными фильтрами (GET)"""
    try:
        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()
        
        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            raise HTTPException(
                status_code=401,
                detail="Ошибка авторизации HeyDealer"
            )
        
        params = {
            "page": page,
            "type": type,
            "is_subscribed": is_subscribed,
            "is_retried": is_retried,
            "is_previously_bid": is_previously_bid,
            "order": order,
        }

        # Добавляем опциональные параметры
        optional_params = {
            "brand": brand,
            "model_group": model_group,
            "model": model,
            "grade": grade,
            "min_year": min_year,
            "max_year": max_year,
            "min_mileage": min_mileage,
            "max_mileage": max_mileage,
            "mileage_group": mileage_group,
            "transmission": transmission,
            "wheel_drive": wheel_drive,
            "car_type": car_type,
            "min_approved_at": min_approved_at,
            "max_approved_at": max_approved_at,
            "accident_repairs_summary": accident_repairs_summary,
            "my_car_accident_cost": my_car_accident_cost,
            "owner_change_record": owner_change_record,
            "use_record": use_record,
            "special_accident_record": special_accident_record,
            "operation_availability": operation_availability,
        }

        # Добавляем не-None параметры
        for key, value in optional_params.items():
            if value is not None:
                params[key] = value

        # Обрабатываем списковые параметры (разделенные запятыми)
        list_params = {
            "fuel": fuel,
            "car_segment": car_segment,
            "location_first_part": location_first_part,
            "payment": payment,
            "accident_group": accident_group,
        }

        for key, value in list_params.items():
            if value:
                # Разделяем по запятой и добавляем как список
                params[key] = [item.strip() for item in value.split(",")]

        response = requests.get(
            "https://api.heydealer.com/v2/dealers/web/cars/",
            params=params,
            headers=headers,
            cookies=cookies,
            timeout=30,
        )

        if response.status_code == 200:
            data = response.json()
            return parser.parse_filtered_cars(data)
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"API request failed: {response.text}",
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")
