"""
HeyDealer фильтры API - роуты для получения брендов, моделей, поколений и конфигураций.
All data served from local data store (background sync).
"""

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
from app.core.heydealer_data_store import heydealer_data_store
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
parser = HeyDealerParser()


@router.get("/brands", response_model=HeyDealerBrandsResponse)
async def get_brands():
    """Получить список всех брендов автомобилей (from data store)"""
    try:
        data = heydealer_data_store.get_brands()

        if not data:
            raise HTTPException(
                status_code=503,
                detail="Brand data not yet available. Sync in progress.",
            )

        return parser.parse_brands(data)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)}")


@router.get(
    "/brands/{brand_hash_id}/models", response_model=HeyDealerBrandDetailResponse
)
async def get_brand_models(brand_hash_id: str):
    """Получить модели для указанного бренда (from data store)"""
    try:
        response_data = heydealer_data_store.get_brand_models(brand_hash_id)

        if not response_data:
            raise HTTPException(
                status_code=404,
                detail=f"Models for brand {brand_hash_id} not found in cache",
            )

        return parser.parse_brand_detail(response_data)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)}")


@router.get(
    "/model-groups/{model_group_hash_id}/generations",
    response_model=HeyDealerModelDetailResponse,
)
async def get_model_generations(model_group_hash_id: str):
    """Получить поколения для указанной группы моделей (from data store)"""
    try:
        clean_id = model_group_hash_id.replace("_", "").replace("-", "") if model_group_hash_id else ""
        if not model_group_hash_id or not (2 <= len(clean_id) <= 6 and clean_id.isalnum()):
            raise HTTPException(
                status_code=400,
                detail=f"Неверный формат model_group_hash_id: {model_group_hash_id}"
            )

        response_data = heydealer_data_store.get_model_generations(model_group_hash_id)

        if not response_data:
            raise HTTPException(
                status_code=404,
                detail=f"Generations for model group {model_group_hash_id} not found in cache",
            )

        return parser.parse_model_detail(response_data)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)}")


@router.get(
    "/models/{model_hash_id}/configurations",
    response_model=HeyDealerGradeDetailResponse,
)
async def get_model_configurations(model_hash_id: str):
    """Получить конфигурации для указанной модели (from data store)"""
    try:
        response_data = heydealer_data_store.get_model_configurations(model_hash_id)

        if not response_data:
            raise HTTPException(
                status_code=404,
                detail=f"Configurations for model {model_hash_id} not found in cache",
            )

        return parser.parse_grade_detail(response_data)

    except HTTPException:
        raise
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
    """Простой поиск автомобилей с основными параметрами (from data store)"""
    try:
        cars_data = heydealer_data_store.get_cars_raw()

        if grade:
            cars_data = [
                c for c in cars_data
                if c.get("detail", {}).get("grade", {}).get("hash_id") == grade
            ]

        page_size = 20
        start = (page - 1) * page_size
        page_cars = cars_data[start : start + page_size]

        return parser.parse_filtered_cars(page_cars)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")


@router.get("/filters", response_model=HeyDealerFiltersResponse)
async def get_available_filters():
    """Получить список всех доступных фильтров (from data store)"""
    try:
        data = heydealer_data_store.get_filters()

        if data:
            return parser.parse_available_filters(data)

        # Fallback: try building from brands data
        brands_data = heydealer_data_store.get_brands()
        if brands_data:
            return parser.parse_available_filters(brands_data)

        raise HTTPException(
            status_code=503,
            detail="Filter data not yet available. Sync in progress.",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")


@router.post("/cars/advanced-search", response_model=HeyDealerListResponse)
async def advanced_search_cars(filters: HeyDealerAdvancedFilterParams):
    """Расширенный поиск автомобилей (from data store)"""
    try:
        cars_data = heydealer_data_store.get_cars_raw()

        params = filters.dict(exclude_none=True)
        grade = params.get("grade")
        if grade:
            cars_data = [
                c for c in cars_data
                if c.get("detail", {}).get("grade", {}).get("hash_id") == grade
            ]

        brand = params.get("brand")
        if brand:
            cars_data = [
                c for c in cars_data
                if c.get("detail", {}).get("brand", {}).get("hash_id") == brand
            ]

        return parser.parse_filtered_cars(cars_data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")


@router.get("/cars/advanced-search", response_model=HeyDealerListResponse)
async def advanced_search_cars_get(
    page: int = 1,
    type: str = "auction",
    is_subscribed: str = "false",
    is_retried: str = "false",
    is_previously_bid: str = "false",
    order: str = "default",
    brand: str = None,
    model_group: str = None,
    model: str = None,
    grade: str = None,
    min_year: int = None,
    max_year: int = None,
    min_mileage: int = None,
    max_mileage: int = None,
    mileage_group: str = None,
    fuel: str = None,
    transmission: str = None,
    wheel_drive: str = None,
    car_segment: str = None,
    car_type: str = None,
    location_first_part: str = None,
    payment: str = None,
    min_approved_at: str = None,
    max_approved_at: str = None,
    accident_repairs_summary: str = None,
    accident_group: str = None,
    my_car_accident_cost: str = None,
    owner_change_record: str = None,
    use_record: str = None,
    special_accident_record: str = None,
    operation_availability: str = None,
):
    """Расширенный поиск автомобилей с множественными фильтрами (from data store)"""
    try:
        cars_data = heydealer_data_store.get_cars_raw()

        if brand:
            cars_data = [
                c for c in cars_data
                if c.get("detail", {}).get("brand", {}).get("hash_id") == brand
            ]
        if model:
            cars_data = [
                c for c in cars_data
                if c.get("detail", {}).get("model", {}).get("hash_id") == model
            ]
        if grade:
            cars_data = [
                c for c in cars_data
                if c.get("detail", {}).get("grade", {}).get("hash_id") == grade
            ]

        page_size = 20
        start = (page - 1) * page_size
        page_cars = cars_data[start : start + page_size]

        return parser.parse_filtered_cars(page_cars)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")
