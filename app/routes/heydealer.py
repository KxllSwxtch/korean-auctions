from fastapi import APIRouter, HTTPException, Query, Depends, Path
from typing import Optional, Dict, Any
import logging
import requests
import json
from datetime import datetime

from app.models.heydealer import (
    HeyDealerResponse,
    HeyDealerFilters,
    HeyDealerDetailResponse,
    HeyDealerCarList,
    HeyDealerBrandsResponse,
    HeyDealerBrandDetailResponse,
    HeyDealerModelDetailResponse,
    HeyDealerGradeDetailResponse,
    HeyDealerListResponse,
    HeyDealerCar,
    HeyDealerBrand,
    HeyDealerCarWithTechSheet,
    HeyDealerCarWithTechSheetResponse,
    AccidentRepairsResponse,
)
from app.services.heydealer_service import HeyDealerService
from app.parsers.heydealer_parser import HeyDealerParser
from app.services.heydealer_auth_service import heydealer_auth
from app.services.heydealer_client_filter import client_filter
from app.core.heydealer_data_store import heydealer_data_store

logger = logging.getLogger(__name__)


def _sync_unavailable_response(page: int = 1):
    """Standard response when data store has no data yet."""
    return {
        "success": False,
        "data": {"cars": [], "total_count": 0, "page": page},
        "message": "Data sync in progress, please retry in a few minutes",
        "total_count": 0,
        "current_page": page,
        "pagination": {
            "current_page": page,
            "total_count": 0,
            "page_size": 20,
            "has_next": False,
        },
    }


def is_valid_hash_id(value: str) -> bool:
    """Validate HeyDealer hash_id format.

    Standard hash_ids are 6 alphanumeric characters.
    Special category IDs like 'etc' (화물·특장·Other) are shorter but valid.
    """
    if not value or not value.strip():
        return False
    clean = value.replace("_", "").replace("-", "")
    return 2 <= len(clean) <= 6 and clean.isalnum()


router = APIRouter(prefix="/heydealer", tags=["HeyDealer"])

# Глобальный экземпляр сервиса (singleton)
_heydealer_service = None


def get_heydealer_service() -> HeyDealerService:
    """Dependency для получения сервиса HeyDealer (singleton)"""
    global _heydealer_service
    if _heydealer_service is None:
        _heydealer_service = HeyDealerService()
    return _heydealer_service


@router.get("/cars")
async def get_heydealer_cars(
    page: int = Query(default=1, description="Номер страницы"),
    auction_type: str = Query(default="auction", description="Тип аукциона"),
    is_subscribed: bool = Query(default=False, description="Только подписанные"),
    is_retried: bool = Query(default=False, description="Только повторные"),
    is_previously_bid: bool = Query(
        default=False, description="Только с предыдущими ставками"
    ),
    order: str = Query(default="default", description="Порядок сортировки"),
    # Параметры фильтрации
    brand: Optional[str] = Query(
        None, description="Hash ID марки (6 символов) или название"
    ),
    model_group: Optional[str] = Query(
        None, description="Hash ID группы моделей (6 символов)"
    ),
    model: Optional[str] = Query(None, description="Hash ID поколения (6 символов)"),
    grade: Optional[str] = Query(None, description="Hash ID конфигурации (6 символов)"),
    service: HeyDealerService = Depends(get_heydealer_service),
):
    """
    Получает список автомобилей с аукциона HeyDealer

    - **page**: Номер страницы для пагинации
    - **auction_type**: Тип аукциона (auction, fixed_price_zero, dealer_zero, self)
    - **is_subscribed**: Фильтр только по подписанным автомобилям
    - **is_retried**: Фильтр только по повторным аукционам
    - **is_previously_bid**: Фильтр только по автомобилям с предыдущими ставками
    - **order**: Порядок сортировки (default, price_asc, price_desc, end_time_asc, end_time_desc)
    """
    try:
        logger.info(
            f"Получение автомобилей HeyDealer: страница {page}, brand={brand}, model_group={model_group}, model={model}, grade={grade}"
        )

        if not heydealer_data_store.is_data_available():
            return _sync_unavailable_response(page)

        # Get raw cars from data store and filter in-memory
        cars_data = heydealer_data_store.get_cars_raw()

        # Apply brand filter
        if brand and brand.strip() and is_valid_hash_id(brand):
            cars_data = [
                c for c in cars_data
                if c.get("detail", {}).get("brand", {}).get("hash_id") == brand
            ]

        # Apply model_group expansion
        if model_group and model_group.strip() and is_valid_hash_id(model_group) and not model:
            from app.services.heydealer_model_mapper import HeyDealerModelMapper
            generation_ids = HeyDealerModelMapper.get_generation_ids_for_model_group(model_group)
            if generation_ids:
                generation_id_set = set(generation_ids)
                cars_data = [
                    c for c in cars_data
                    if c.get("detail", {}).get("model", {}).get("hash_id") in generation_id_set
                ]
            else:
                cars_data = []

        # Apply model filter
        if model and model.strip() and is_valid_hash_id(model):
            cars_data = [
                c for c in cars_data
                if c.get("detail", {}).get("model", {}).get("hash_id") == model
            ]

        # Apply grade filter
        if grade and grade.strip() and is_valid_hash_id(grade):
            cars_data = [
                c for c in cars_data
                if c.get("detail", {}).get("grade", {}).get("hash_id") == grade
            ]

        total_count = len(cars_data)
        page_size = 20
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        page_cars = cars_data[start_index:end_index]

        # Parse through existing parser
        parser = HeyDealerParser()
        car_list = parser.parse_car_list_with_pagination(
            page_cars, total_count, page, page_size
        )

        if not car_list:
            return {
                "success": True,
                "data": {"cars": [], "total_count": 0, "page": page},
                "message": "Нет автомобилей",
                "total_count": 0,
                "current_page": page,
            }

        normalized_data = parser.format_response_data(
            cars=car_list.cars, total_count=total_count, page=page
        )

        return {
            "success": True,
            "data": {
                "cars": normalized_data["cars"],
                "total_count": normalized_data["total_count"],
                "page": normalized_data["current_page"],
            },
            "message": normalized_data["message"],
            "total_count": normalized_data["total_count"],
            "current_page": normalized_data["current_page"],
            "pagination": normalized_data["pagination"],
        }

    except Exception as e:
        logger.error(f"Ошибка при получении автомобилей HeyDealer: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Внутренняя ошибка сервера при получении данных HeyDealer: {str(e)}",
        )


@router.get("/cars/normalized")
async def get_normalized_heydealer_cars(
    page: int = Query(default=1, description="Номер страницы"),
    auction_type: str = Query(default="auction", description="Тип аукциона"),
    is_subscribed: bool = Query(default=False, description="Только подписанные"),
    is_retried: bool = Query(default=False, description="Только повторные"),
    is_previously_bid: bool = Query(
        default=False, description="Только с предыдущими ставками"
    ),
    order: str = Query(default="default", description="Порядок сортировки"),
    service: HeyDealerService = Depends(get_heydealer_service),
):
    """
    Получает нормализованный список автомобилей HeyDealer

    Возвращает данные в общем формате для всех аукционов.
    """
    try:
        if not heydealer_data_store.is_data_available():
            return {
                "success": False,
                "message": "Data sync in progress",
                "cars": [],
                "total_count": 0,
                "current_page": page,
                "auction_name": "HeyDealer",
            }

        cars_data = heydealer_data_store.get_cars_raw()
        page_size = 20
        total_count = len(cars_data)
        start = (page - 1) * page_size
        page_cars = cars_data[start : start + page_size]

        parser = HeyDealerParser()
        car_list = parser.parse_car_list(page_cars)

        if not car_list:
            return {
                "success": False,
                "message": "Ошибка парсинга данных",
                "cars": [],
                "total_count": 0,
                "current_page": page,
                "auction_name": "HeyDealer",
            }

        normalized_data = parser.format_response_data(
            cars=car_list.cars, total_count=total_count, page=page
        )
        return normalized_data

    except Exception as e:
        logger.error(f"Ошибка при получении нормализованных автомобилей HeyDealer: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Внутренняя ошибка сервера при получении нормализованных данных HeyDealer: {str(e)}",
        )


@router.get("/status")
async def get_heydealer_status(
    service: HeyDealerService = Depends(get_heydealer_service),
):
    """
    Проверяет статус подключения к HeyDealer API.
    Returns sync metadata and data availability.
    """
    try:
        meta = heydealer_data_store.get_sync_metadata()
        has_data = heydealer_data_store.is_data_available()
        age = heydealer_data_store.get_data_age_seconds()

        if has_data:
            return {
                "status": "success",
                "message": f"HeyDealer data available. {meta.get('total_cars', 0)} cars cached. Last sync: {meta.get('last_sync_at', 'N/A')}",
                "auction_name": "HeyDealer",
                "authenticated": True,
                "cars_count": meta.get("total_cars", 0),
                "sync": meta,
                "data_age_seconds": age,
            }
        else:
            return {
                "status": "error",
                "message": f"Data sync pending or failed. Status: {meta.get('status', 'unknown')}",
                "auction_name": "HeyDealer",
                "authenticated": False,
                "sync": meta,
                "data_age_seconds": age,
            }

    except Exception as e:
        logger.error(f"Ошибка при проверке статуса HeyDealer: {e}")
        return {
            "status": "error",
            "message": f"Ошибка: {str(e)}",
            "auction_name": "HeyDealer",
            "authenticated": False,
        }


@router.get("/cars/filtered")
async def get_filtered_cars(
    page: int = Query(1, description="Номер страницы"),
    order: str = Query("default", description="Сортировка"),
    brand: Optional[str] = Query(None, description="ID марки"),
    model_group: Optional[str] = Query(None, description="ID группы моделей"),
    model: Optional[str] = Query(None, description="ID поколения"),
    grade: Optional[str] = Query(None, description="ID конфигурации"),
    min_year: Optional[int] = Query(None, description="Минимальный год"),
    max_year: Optional[int] = Query(None, description="Максимальный год"),
    min_price: Optional[int] = Query(None, description="Минимальная цена"),
    max_price: Optional[int] = Query(None, description="Максимальная цена"),
    min_mileage: Optional[int] = Query(None, description="Минимальный пробег"),
    max_mileage: Optional[int] = Query(None, description="Максимальный пробег"),
    fuel: Optional[str] = Query(None, description="Тип топлива"),
    transmission: Optional[str] = Query(None, description="Тип КПП"),
    wheel_drive: Optional[str] = Query(None, description="Тип привода (например: 2WD,4WD)"),
    location: Optional[str] = Query(None, description="Местоположение"),
):
    """Получение отфильтрованного списка автомобилей (from local data store)"""
    try:
        if not heydealer_data_store.is_data_available():
            return _sync_unavailable_response(page)

        cars_data = heydealer_data_store.get_cars_raw()

        # Apply hash_id-based filters
        if brand and brand.strip() and is_valid_hash_id(brand):
            cars_data = [
                c for c in cars_data
                if c.get("detail", {}).get("brand", {}).get("hash_id") == brand
            ]

        if model_group and model_group.strip() and is_valid_hash_id(model_group) and not model:
            from app.services.heydealer_model_mapper import HeyDealerModelMapper
            generation_ids = HeyDealerModelMapper.get_generation_ids_for_model_group(model_group)
            if not generation_ids:
                return {
                    "success": True,
                    "data": {"cars": [], "total_count": 0, "page": page},
                    "message": f"Не найдены поколения для модели {model_group}",
                    "total_count": 0,
                    "current_page": page,
                }
            generation_id_set = set(generation_ids)
            cars_data = [
                c for c in cars_data
                if c.get("detail", {}).get("model", {}).get("hash_id") in generation_id_set
            ]

        if model and model.strip() and is_valid_hash_id(model):
            cars_data = [
                c for c in cars_data
                if c.get("detail", {}).get("model", {}).get("hash_id") == model
            ]

        if grade and grade.strip() and is_valid_hash_id(grade):
            cars_data = [
                c for c in cars_data
                if c.get("detail", {}).get("grade", {}).get("hash_id") == grade
            ]

        # Normalize cars and apply additional filters
        parser = HeyDealerParser()
        normalized_cars = []
        for car_raw in cars_data:
            try:
                pydantic_car = HeyDealerCar(**car_raw)
                normalized_car = parser.normalize_car_data(pydantic_car)
                detail_data = car_raw.get("detail", {})

                title = normalized_car.get("title", "")
                grade_part_name = normalized_car.get("grade_part_name", "")

                fuel_type = None
                fuel_display = None
                if "가솔린" in title or "가솔린" in grade_part_name:
                    fuel_type, fuel_display = "gasoline", "Бензин"
                elif "디젤" in title or "디젤" in grade_part_name:
                    fuel_type, fuel_display = "diesel", "Дизель"
                elif "하이브리드" in title or "하이브리드" in grade_part_name:
                    fuel_type, fuel_display = "hybrid", "Гибрид"
                elif "전기" in title or "전기" in grade_part_name or "EV" in title:
                    fuel_type, fuel_display = "electric", "Электро"
                elif "LPG" in title or "LPI" in title:
                    fuel_type, fuel_display = "lpg", "ГБО"

                transmission_type = None
                transmission_display = None
                if "AWD" in title or "AWD" in grade_part_name or "4WD" in title or "4WD" in grade_part_name:
                    transmission_type, transmission_display = "awd", "Полный привод"
                elif "2WD" in title or "2WD" in grade_part_name or "FWD" in title or "FWD" in grade_part_name:
                    transmission_type, transmission_display = "fwd", "Передний привод"
                elif "RWD" in title or "RWD" in grade_part_name:
                    transmission_type, transmission_display = "rwd", "Задний привод"

                gear_type, gear_display = "automatic", "Автомат"
                if "수동" in title:
                    gear_type, gear_display = "manual", "Механика"
                elif "CVT" in title:
                    gear_type, gear_display = "cvt", "Вариатор"

                normalized_car.update({
                    "fuel": fuel_type, "fuel_display": fuel_display, "fuel_type": fuel_type,
                    "transmission": transmission_type, "transmission_display": transmission_display,
                    "gear": gear_type, "gear_display": gear_display,
                    "payment": detail_data.get("payment"), "payment_display": detail_data.get("payment_display"),
                    "color": detail_data.get("color"),
                    "accident": detail_data.get("accident"), "accident_display": detail_data.get("accident_display"),
                })
                normalized_cars.append(normalized_car)
            except Exception as e:
                logger.error(f"Ошибка обработки автомобиля: {e}")
                continue

        # Apply client-side value filters
        if min_year:
            normalized_cars = [c for c in normalized_cars if (c.get("year") or 0) >= min_year]
        if max_year:
            normalized_cars = [c for c in normalized_cars if (c.get("year") or 9999) <= max_year]
        if min_price:
            normalized_cars = [c for c in normalized_cars if (c.get("price") or c.get("desired_price") or 0) >= min_price]
        if max_price:
            normalized_cars = [c for c in normalized_cars if (c.get("price") or c.get("desired_price") or 999999999) <= max_price]
        if min_mileage:
            normalized_cars = [c for c in normalized_cars if (c.get("mileage") or 0) >= min_mileage]
        if max_mileage:
            normalized_cars = [c for c in normalized_cars if (c.get("mileage") or 999999) <= max_mileage]
        if fuel and fuel.strip():
            fuel_values = [v.strip().lower() for v in fuel.split(",") if v.strip()]
            if fuel_values:
                normalized_cars = [c for c in normalized_cars if c.get("fuel") in fuel_values]

        total_count = len(normalized_cars)
        page_size = 20
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        page_cars = normalized_cars[start_index:end_index]

        return {
            "success": True,
            "data": {"cars": page_cars, "total_count": total_count, "page": page},
            "message": f"Получено {len(page_cars)} автомобилей с фильтрами",
            "total_count": total_count,
            "current_page": page,
            "pagination": {
                "current_page": page,
                "total_count": total_count,
                "page_size": page_size,
                "has_next": end_index < total_count,
            },
        }

    except Exception as e:
        logger.error(f"Ошибка в эндпоинте фильтрации автомобилей: {str(e)}")
        return {
            "success": False,
            "data": {"cars": [], "total_count": 0, "page": page},
            "message": f"Ошибка: {str(e)}",
            "total_count": 0,
            "current_page": page,
        }


@router.get("/cars/{car_hash_id}", response_model=HeyDealerCarWithTechSheetResponse)
async def get_heydealer_car_detail_with_tech_sheet(
    car_hash_id: str = Path(..., description="Hash ID автомобиля"),
    service: HeyDealerService = Depends(get_heydealer_service),
):
    """
    Получает детальную информацию об автомобиле HeyDealer с интегрированным техническим листом

    - **car_hash_id**: Уникальный идентификатор автомобиля (hash_id)

    Этот эндпоинт выполняет два запроса параллельно:
    1. Получение детальной информации об автомобиле
    2. Получение данных технического листа (accident repairs)

    Возвращает объединенные данные в одном JSON объекте.
    """
    try:
        logger.info(
            f"Получение детальной информации об автомобиле с техническим листом: {car_hash_id}"
        )

        # Read from data store instead of live API
        car_data = heydealer_data_store.get_car_detail(car_hash_id)
        repairs_data = heydealer_data_store.get_accident_repairs(car_hash_id)

        car_request_success = car_data is not None
        repairs_request_success = repairs_data is not None

        # Проверяем успешность основного запроса
        if not car_data:
            logger.error(f"Car detail not found in data store: {car_hash_id}")
            return HeyDealerCarWithTechSheetResponse(
                success=False,
                data=None,
                message=f"Автомобиль {car_hash_id} не найден в кэше данных",
                timestamp=datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT"),
                total_requests=0,
                car_request_success=False,
                accident_repairs_request_success=False,
            )

        # Извлекаем данные автомобиля
        detail_section = car_data.get("detail", {})
        auction_section = car_data.get("auction", {})
        etc_section = car_data.get("etc", {})

        # Обрабатываем данные технического листа
        accident_repairs_data = None
        accident_repairs_available = False
        accident_repairs_error = None

        if repairs_data:
            try:
                # Парсим данные технического листа через наш парсер
                from app.parsers.heydealer_parser import HeyDealerParser

                parser = HeyDealerParser()
                accident_repairs_data = parser.parse_accident_repairs(repairs_data)
                accident_repairs_available = True
                logger.info(f"Технический лист успешно получен для {car_hash_id}")
            except Exception as e:
                logger.error(f"Ошибка парсинга технического листа: {e}")
                accident_repairs_error = f"Ошибка парсинга технического листа: {str(e)}"
        else:
            accident_repairs_error = "Технический лист не найден в кэше данных"
            logger.warning(
                f"Не удалось получить технический лист для {car_hash_id} из кэша"
            )

        # Создаем объединенный объект данных
        combined_car_data = HeyDealerCarWithTechSheet(
            # Основные данные автомобиля
            hash_id=car_data.get("hash_id"),
            status=car_data.get("status"),
            status_display=car_data.get("status_display"),
            # Основная информация об автомобиле
            full_name=detail_section.get("full_name"),
            model_part_name=detail_section.get("model_part_name"),
            grade_part_name=detail_section.get("grade_part_name"),
            brand_name=detail_section.get("brand_name"),
            brand_image_url=detail_section.get("brand_image_url"),
            main_image_url=detail_section.get("main_image_url"),
            image_urls=detail_section.get("image_urls", []),
            image_groups=detail_section.get("image_groups") or [],
            # Технические характеристики
            car_number=detail_section.get("car_number"),
            year=detail_section.get("year"),
            initial_registration_date=detail_section.get("initial_registration_date"),
            mileage=detail_section.get("mileage"),
            color=detail_section.get("color"),
            interior=detail_section.get("interior"),
            color_info=detail_section.get("color_info"),
            interior_info=detail_section.get("interior_info"),
            # Местоположение и условия
            location=detail_section.get("location"),
            short_location=detail_section.get("short_location"),
            payment=detail_section.get("payment"),
            payment_display=detail_section.get("payment_display"),
            fuel=detail_section.get("fuel"),
            fuel_display=detail_section.get("fuel_display"),
            transmission=detail_section.get("transmission"),
            transmission_display=detail_section.get("transmission_display"),
            # Состояние автомобиля
            accident=detail_section.get("accident"),
            accident_display=detail_section.get("accident_display"),
            accident_repairs_summary=detail_section.get("accident_repairs_summary"),
            accident_repairs_summary_display=detail_section.get(
                "accident_repairs_summary_display"
            ),
            condition_data=detail_section.get("condition_data"),
            condition_description=detail_section.get("condition_description"),
            inspected_condition=detail_section.get("inspected_condition"),
            # Опции и описания
            is_advanced_options=detail_section.get("is_advanced_options"),
            advanced_options=detail_section.get("advanced_options") or [],
            description=detail_section.get("description"),
            car_description=detail_section.get("car_description"),
            customer_comment=detail_section.get("customer_comment"),
            inspector_comment=detail_section.get("inspector_comment"),
            comment=detail_section.get("comment"),
            # История автомобиля
            carhistory=detail_section.get("carhistory"),
            carhistory_summary=detail_section.get("carhistory_summary"),
            vehicle_information=detail_section.get("vehicle_information"),
            # Информация об аукционе
            auction_type=auction_section.get("auction_type"),
            visits_count=auction_section.get("visits_count"),
            approved_at=auction_section.get("approved_at"),
            end_at=auction_section.get("end_at"),
            bids_count=auction_section.get("bids_count"),
            max_bids_count=auction_section.get("max_bids_count"),
            desired_price=auction_section.get("desired_price"),
            highest_bid=auction_section.get("highest_bid"),
            is_starred=auction_section.get("is_starred"),
            category=auction_section.get("category"),
            zero_auction_message=auction_section.get("zero_auction_message"),
            previous_auction_result=auction_section.get("previous_auction_result"),
            # Дополнительная информация
            etc=etc_section,
            is_pre_inspected=detail_section.get("is_pre_inspected"),
            zero_type=detail_section.get("zero_type"),
            standard_new_car_price=detail_section.get("standard_new_car_price"),
            # Технический лист
            accident_repairs_data=accident_repairs_data,
            accident_repairs_available=accident_repairs_available,
            accident_repairs_error=accident_repairs_error,
        )

        # Формируем успешный ответ
        return HeyDealerCarWithTechSheetResponse(
            success=True,
            data=combined_car_data,
            message=f"Детальная информация об автомобиле успешно получена"
            + (
                f" с техническим листом"
                if accident_repairs_available
                else f" (технический лист недоступен)"
            ),
            timestamp=datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT"),
            total_requests=0,
            car_request_success=car_request_success,
            accident_repairs_request_success=accident_repairs_available,
        )

    except Exception as e:
        logger.error(
            f"Ошибка при получении детальной информации об автомобиле {car_hash_id}: {e}"
        )
        return HeyDealerCarWithTechSheetResponse(
            success=False,
            data=None,
            message=f"Внутренняя ошибка сервера: {str(e)}",
            timestamp=datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT"),
            total_requests=0,
            car_request_success=False,
            accident_repairs_request_success=False,
        )


@router.get("/cars/{car_hash_id}/basic")
async def get_heydealer_car_detail_basic(
    car_hash_id: str = Path(..., description="Hash ID автомобиля"),
):
    """
    Получает только базовую детальную информацию об автомобиле HeyDealer (без технического листа)

    Этот эндпоинт предназначен для случаев, когда нужны только данные автомобиля
    без дополнительной нагрузки на получение технического листа.

    - **car_hash_id**: Уникальный идентификатор автомобиля (hash_id)
    """
    try:
        logger.info(
            f"Получение базовой детальной информации об автомобиле: {car_hash_id}"
        )

        detail_data = heydealer_data_store.get_car_detail(car_hash_id)

        if detail_data:

            # Извлекаем данные напрямую
            detail_section = detail_data.get("detail", {})
            auction_section = detail_data.get("auction", {})
            etc_section = detail_data.get("etc", {})

            # Возвращаем полную структуру данных
            result = {
                "success": True,
                "data": {
                    "hash_id": detail_data.get("hash_id"),
                    "status": detail_data.get("status"),
                    "status_display": detail_data.get("status_display"),
                    # Основная информация об автомобиле
                    "full_name": detail_section.get("full_name"),
                    "model_part_name": detail_section.get("model_part_name"),
                    "grade_part_name": detail_section.get("grade_part_name"),
                    "brand_name": detail_section.get("brand_name"),
                    "brand_image_url": detail_section.get("brand_image_url"),
                    "main_image_url": detail_section.get("main_image_url"),
                    "image_urls": detail_section.get("image_urls", []),
                    "image_groups": detail_section.get("image_groups", []),
                    # Технические характеристики
                    "car_number": detail_section.get("car_number"),
                    "year": detail_section.get("year"),
                    "initial_registration_date": detail_section.get(
                        "initial_registration_date"
                    ),
                    "mileage": detail_section.get("mileage"),
                    "color": detail_section.get("color"),
                    "interior": detail_section.get("interior"),
                    "color_info": detail_section.get("color_info"),
                    "interior_info": detail_section.get("interior_info"),
                    # Местоположение и условия
                    "location": detail_section.get("location"),
                    "short_location": detail_section.get("short_location"),
                    "payment": detail_section.get("payment"),
                    "payment_display": detail_section.get("payment_display"),
                    "fuel": detail_section.get("fuel"),
                    "fuel_display": detail_section.get("fuel_display"),
                    "transmission": detail_section.get("transmission"),
                    "transmission_display": detail_section.get("transmission_display"),
                    # Состояние автомобиля
                    "accident": detail_section.get("accident"),
                    "accident_display": detail_section.get("accident_display"),
                    "accident_repairs_summary": detail_section.get(
                        "accident_repairs_summary"
                    ),
                    "accident_repairs_summary_display": detail_section.get(
                        "accident_repairs_summary_display"
                    ),
                    "condition_data": detail_section.get("condition_data"),
                    "condition_description": detail_section.get(
                        "condition_description"
                    ),
                    "inspected_condition": detail_section.get("inspected_condition"),
                    # Опции и описания
                    "is_advanced_options": detail_section.get("is_advanced_options"),
                    "advanced_options": detail_section.get("advanced_options", []),
                    "description": detail_section.get("description"),
                    "car_description": detail_section.get("car_description"),
                    "customer_comment": detail_section.get("customer_comment"),
                    "inspector_comment": detail_section.get("inspector_comment"),
                    "comment": detail_section.get("comment"),
                    # История автомобиля
                    "carhistory": detail_section.get("carhistory"),
                    "carhistory_summary": detail_section.get("carhistory_summary"),
                    "vehicle_information": detail_section.get("vehicle_information"),
                    # Информация об аукционе
                    "auction_type": auction_section.get("auction_type"),
                    "visits_count": auction_section.get("visits_count"),
                    "approved_at": auction_section.get("approved_at"),
                    "end_at": auction_section.get("end_at"),
                    "bids_count": auction_section.get("bids_count"),
                    "max_bids_count": auction_section.get("max_bids_count"),
                    "desired_price": auction_section.get("desired_price"),
                    "highest_bid": auction_section.get("highest_bid"),
                    "is_starred": auction_section.get("is_starred"),
                    "category": auction_section.get("category"),
                    "zero_auction_message": auction_section.get("zero_auction_message"),
                    "previous_auction_result": auction_section.get(
                        "previous_auction_result"
                    ),
                    # Дополнительная информация
                    "etc": etc_section,
                    "is_pre_inspected": detail_section.get("is_pre_inspected"),
                    "zero_type": detail_section.get("zero_type"),
                    "standard_new_car_price": detail_section.get(
                        "standard_new_car_price"
                    ),
                },
                "message": "Базовая детальная информация успешно получена",
                "timestamp": datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT"),
            }

            return result
        else:
            logger.error(
                f"Автомобиль {car_hash_id} не найден в кэше данных"
            )
            return {
                "success": False,
                "error": f"Автомобиль {car_hash_id} не найден",
                "detail": "Данные отсутствуют в кэше. Дождитесь следующей синхронизации.",
            }

    except Exception as e:
        logger.error(
            f"Ошибка при получении базовой детальной информации об автомобиле {car_hash_id}: {e}"
        )
        return {"success": False, "error": f"Внутренняя ошибка сервера: {str(e)}"}


@router.get("/cars/{car_hash_id}/direct")
async def get_heydealer_car_detail_direct(
    car_hash_id: str = Path(..., description="Hash ID автомобиля"),
):
    """
    Получает детальную информацию об автомобиле напрямую (для тестирования)

    - **car_hash_id**: Уникальный идентификатор автомобиля (hash_id)
    """
    try:
        logger.info(
            f"Получение детальной информации об автомобиле (напрямую): {car_hash_id}"
        )

        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()

        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            return {
                "success": False,
                "data": None,
                "message": "Ошибка авторизации HeyDealer",
            }

        # Получаем детальную информацию
        detail_url = f"https://api.heydealer.com/v2/dealers/web/cars/{car_hash_id}/"
        detail_response = requests.get(detail_url, headers=headers, cookies=cookies)

        if detail_response.status_code == 200:
            detail_data = detail_response.json()

            # Отладочная информация
            logger.info(f"Структура данных: {list(detail_data.keys())}")
            logger.info(
                f"Detail keys: {list(detail_data.get('detail', {}).keys())[:10]}"
            )  # Первые 10 ключей
            logger.info(
                f"Auction keys: {list(detail_data.get('auction', {}).keys())[:10]}"
            )  # Первые 10 ключей

            # Парсим через наш парсер
            parser = HeyDealerParser()
            detailed_car = parser.parse_detailed_car_direct(detail_data)

            if detailed_car:
                return HeyDealerResponse(
                    success=True,
                    data=HeyDealerCarList(cars=[detailed_car], total_count=1, page=1),
                    message="Детальная информация успешно получена (напрямую)",
                    total_count=1,
                    current_page=1,
                )
        else:
            logger.error(
                f"Ошибка получения детальной информации: {detail_response.status_code} - {detail_response.text}"
            )
            return {
                "success": False,
                "data": None,
                "message": f"Ошибка получения детальной информации: {detail_response.status_code}",
            }

    except Exception as e:
        logger.error(
            f"Ошибка при получении детальной информации об автомобиле {car_hash_id}: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Внутренняя ошибка сервера: {str(e)}",
        )


@router.get("/cars/{car_hash_id}/raw")
async def get_heydealer_car_raw(
    car_hash_id: str = Path(..., description="Hash ID автомобиля"),
):
    """
    Получает сырые данные об автомобиле для отладки

    - **car_hash_id**: Уникальный идентификатор автомобиля (hash_id)
    """
    try:
        logger.info(f"Получение сырых данных об автомобиле: {car_hash_id}")

        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()

        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            return {
                "success": False,
                "message": "Ошибка авторизации HeyDealer",
                "error_text": "Не удалось получить валидную сессию HeyDealer",
            }

        # Получаем детальную информацию
        detail_url = f"https://api.heydealer.com/v2/dealers/web/cars/{car_hash_id}/"
        detail_response = requests.get(detail_url, headers=headers, cookies=cookies)

        if detail_response.status_code == 200:
            detail_data = detail_response.json()

            # Возвращаем сырые данные с некоторой информацией
            return {
                "success": True,
                "car_hash_id": car_hash_id,
                "data_keys": (
                    list(detail_data.keys())
                    if isinstance(detail_data, dict)
                    else "not_dict"
                ),
                "detail_keys": (
                    list(detail_data.get("detail", {}).keys())
                    if detail_data.get("detail")
                    else "no_detail"
                ),
                "auction_keys": (
                    list(detail_data.get("auction", {}).keys())
                    if detail_data.get("auction")
                    else "no_auction"
                ),
                "sample_data": {
                    "hash_id": detail_data.get("hash_id"),
                    "status": detail_data.get("status"),
                    "status_display": detail_data.get("status_display"),
                    "detail_full_name": detail_data.get("detail", {}).get("full_name"),
                    "detail_year": detail_data.get("detail", {}).get("year"),
                    "detail_mileage": detail_data.get("detail", {}).get("mileage"),
                },
                "raw_data": detail_data,  # Полные сырые данные
            }
        else:
            return {
                "success": False,
                "message": f"Ошибка получения данных: {detail_response.status_code}",
                "error_text": detail_response.text[:500],
            }

    except Exception as e:
        logger.error(
            f"Ошибка при получении сырых данных об автомобиле {car_hash_id}: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Внутренняя ошибка сервера: {str(e)}",
        )


@router.get("/cars/{car_hash_id}/simple")
async def get_heydealer_car_simple(
    car_hash_id: str = Path(..., description="Hash ID автомобиля"),
):
    """
    Получает упрощенные данные об автомобиле (для тестирования)

    - **car_hash_id**: Уникальный идентификатор автомобиля (hash_id)
    """
    try:
        logger.info(f"Получение упрощенных данных об автомобиле: {car_hash_id}")

        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()

        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            return {
                "success": False,
                "message": "Ошибка авторизации HeyDealer",
                "error_text": "Не удалось получить валидную сессию HeyDealer",
            }

        # Получаем детальную информацию
        detail_url = f"https://api.heydealer.com/v2/dealers/web/cars/{car_hash_id}/"
        detail_response = requests.get(detail_url, headers=headers, cookies=cookies)

        if detail_response.status_code == 200:
            detail_data = detail_response.json()

            # Отладочная информация
            logger.info(f"Raw detail_data keys: {list(detail_data.keys())}")
            detail_section = detail_data.get("detail", {})
            logger.info(f"Detail section keys: {list(detail_section.keys())[:10]}")
            logger.info(f"Detail full_name: {detail_section.get('full_name')}")
            logger.info(f"Detail year: {detail_section.get('year')}")
            logger.info(f"Detail mileage: {detail_section.get('mileage')}")

            # Возвращаем упрощенные данные без парсера
            auction_section = detail_data.get("auction", {})

            simple_car = {
                "hash_id": detail_data.get("hash_id"),
                "status": detail_data.get("status"),
                "status_display": detail_data.get("status_display"),
                "detail": {
                    "full_name": detail_section.get("full_name"),
                    "year": detail_section.get("year"),
                    "mileage": detail_section.get("mileage"),
                    "location": detail_section.get("location"),
                    "short_location": detail_section.get("short_location"),
                    "brand_image_url": detail_section.get("brand_image_url"),
                    "main_image_url": detail_section.get("main_image_url"),
                    "image_urls": detail_section.get("image_urls", []),
                    "car_number": detail_section.get("car_number"),
                },
                "auction": {
                    "auction_type": auction_section.get("auction_type"),
                    "end_at": auction_section.get("end_at"),
                    "bids_count": auction_section.get("bids_count"),
                    "max_bids_count": auction_section.get("max_bids_count"),
                    "desired_price": auction_section.get("desired_price"),
                    "is_starred": auction_section.get("is_starred"),
                    "category": auction_section.get("category"),
                },
            }

            return {
                "success": True,
                "data": simple_car,
                "message": "Упрощенные данные получены успешно",
            }
        else:
            return {
                "success": False,
                "message": f"Ошибка получения данных: {detail_response.status_code}",
                "error_text": detail_response.text[:500],
            }

    except Exception as e:
        logger.error(
            f"Ошибка при получении упрощенных данных об автомобиле {car_hash_id}: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Внутренняя ошибка сервера: {str(e)}",
        )


@router.get("/cars/{car_hash_id}/direct-json")
async def get_heydealer_car_detail_direct_json(
    car_hash_id: str = Path(..., description="Hash ID автомобиля"),
):
    """
    Получает детальную информацию об автомобиле HeyDealer без Pydantic моделей
    """
    try:
        logger.info(f"Получение детальной информации об автомобиле: {car_hash_id}")

        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()

        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            return {
                "success": False,
                "error": "Ошибка авторизации HeyDealer",
                "detail": "Не удалось получить валидную сессию HeyDealer",
            }

        # Получаем детальную информацию
        detail_url = f"https://api.heydealer.com/v2/dealers/web/cars/{car_hash_id}/"
        detail_response = requests.get(detail_url, headers=headers, cookies=cookies)

        if detail_response.status_code == 200:
            detail_data = detail_response.json()

            # Извлекаем данные напрямую
            detail_section = detail_data.get("detail", {})
            auction_section = detail_data.get("auction", {})

            # Возвращаем простой JSON
            return {
                "success": True,
                "car": {
                    "hash_id": detail_data.get("hash_id"),
                    "status": detail_data.get("status"),
                    "status_display": detail_data.get("status_display"),
                    "full_name": detail_section.get("full_name"),
                    "year": detail_section.get("year"),
                    "mileage": detail_section.get("mileage"),
                    "car_number": detail_section.get("car_number"),
                    "location": detail_section.get("location"),
                    "desired_price": auction_section.get("desired_price"),
                    "bids_count": auction_section.get("bids_count"),
                    "auction_type": auction_section.get("auction_type"),
                    "end_at": auction_section.get("end_at"),
                },
            }
        else:
            return {
                "success": False,
                "error": f"Ошибка получения данных: {detail_response.status_code}",
                "detail": detail_response.text,
            }

    except Exception as e:
        logger.error(
            f"Ошибка при получении детальной информации об автомобиле {car_hash_id}: {e}"
        )
        return {"success": False, "error": f"Внутренняя ошибка сервера: {str(e)}"}


@router.get("/cars/{car_hash_id}/debug-json")
async def get_heydealer_car_debug_json(
    car_hash_id: str = Path(..., description="Hash ID автомобиля"),
):
    """
    Debug endpoint для проверки данных
    """
    try:
        logger.info(
            f"Debug: Получение детальной информации об автомобиле: {car_hash_id}"
        )

        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()

        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            return {
                "success": False,
                "error": "Ошибка авторизации HeyDealer",
                "detail": "Не удалось получить валидную сессию HeyDealer",
            }

        # Получаем детальную информацию
        detail_url = f"https://api.heydealer.com/v2/dealers/web/cars/{car_hash_id}/"
        detail_response = requests.get(detail_url, headers=headers, cookies=cookies)

        if detail_response.status_code == 200:
            detail_data = detail_response.json()

            # Извлекаем данные напрямую
            detail_section = detail_data.get("detail", {})
            auction_section = detail_data.get("auction", {})

            # Debug информация
            debug_info = {
                "detail_section_keys": list(detail_section.keys()),
                "auction_section_keys": list(auction_section.keys()),
                "detail_full_name": detail_section.get("full_name"),
                "detail_year": detail_section.get("year"),
                "detail_mileage": detail_section.get("mileage"),
                "auction_desired_price": auction_section.get("desired_price"),
                "auction_bids_count": auction_section.get("bids_count"),
                "raw_detail_type": str(type(detail_section.get("full_name"))),
                "raw_year_type": str(type(detail_section.get("year"))),
            }

            return {
                "success": True,
                "debug": debug_info,
                "raw_detail_section": detail_section,
                "raw_auction_section": auction_section,
            }
        else:
            return {
                "success": False,
                "error": f"Ошибка получения данных: {detail_response.status_code}",
                "detail": detail_response.text,
            }

    except Exception as e:
        logger.error(
            f"Ошибка при получении детальной информации об автомобиле {car_hash_id}: {e}"
        )
        return {"success": False, "error": f"Внутренняя ошибка сервера: {str(e)}"}


@router.get("/brands", response_model=HeyDealerBrandsResponse)
async def get_brands():
    """Получение списка марок автомобилей (from data store)"""
    try:
        brands_data = heydealer_data_store.get_brands()

        if brands_data:
            brands = [HeyDealerBrand(**brand) for brand in brands_data] if isinstance(brands_data, list) else []
            return HeyDealerBrandsResponse(
                success=True, data=brands, message=f"Получено {len(brands)} марок"
            )
        else:
            return HeyDealerBrandsResponse(
                success=False, data=[], message="Данные марок ещё не загружены"
            )

    except Exception as e:
        logger.error(f"Ошибка в эндпоинте получения марок: {str(e)}")
        return HeyDealerBrandsResponse(
            success=False, data=[], message=f"Ошибка: {str(e)}"
        )


@router.get("/brands/raw", response_model=Dict[str, Any])
async def get_brands_raw():
    """Получение сырых данных марок для отладки (from data store)"""
    try:
        brands_data = heydealer_data_store.get_brands()

        return {
            "success": True,
            "data": brands_data,
            "count": len(brands_data) if brands_data else 0,
            "message": "Сырые данные марок (из кэша)",
        }

    except Exception as e:
        logger.error(f"Ошибка в эндпоинте сырых данных марок: {str(e)}")
        return {"success": False, "data": [], "message": f"Ошибка: {str(e)}"}


@router.get("/brands/{brand_hash_id}", response_model=HeyDealerBrandDetailResponse)
async def get_brand_models(brand_hash_id: str):
    """Получение списка моделей для выбранной марки (from data store)"""
    try:
        brand_data = heydealer_data_store.get_brand_models(brand_hash_id)

        if brand_data:
            return HeyDealerBrandDetailResponse(
                success=True,
                data=brand_data,
                message=f"Получены модели для марки {brand_hash_id}",
            )
        else:
            return HeyDealerBrandDetailResponse(
                success=False, data={}, message="Модели для этой марки ещё не загружены"
            )

    except Exception as e:
        logger.error(f"Ошибка в эндпоинте получения моделей: {str(e)}")
        return HeyDealerBrandDetailResponse(
            success=False, data={}, message=f"Ошибка: {str(e)}"
        )


@router.get(
    "/model-groups/{model_group_hash_id}", response_model=HeyDealerModelDetailResponse
)
async def get_model_generations(model_group_hash_id: str):
    """Получение списка поколений для выбранной модели (from data store)"""
    try:
        model_data = heydealer_data_store.get_model_generations(model_group_hash_id)

        if model_data:
            parser = HeyDealerParser()
            parsed_response = parser.parse_model_detail(model_data)
            return parsed_response
        else:
            return HeyDealerModelDetailResponse(
                success=False, data={}, message="Поколения для этой модели ещё не загружены"
            )

    except Exception as e:
        logger.error(f"Ошибка в эндпоинте получения поколений: {str(e)}")
        return HeyDealerModelDetailResponse(
            success=False, data={}, message=f"Ошибка: {str(e)}"
        )


@router.get("/models/{model_hash_id}", response_model=HeyDealerGradeDetailResponse)
async def get_model_configurations(model_hash_id: str):
    """Получение списка конфигураций для выбранного поколения (from data store)"""
    try:
        config_data = heydealer_data_store.get_model_configurations(model_hash_id)

        if config_data:
            parser = HeyDealerParser()
            parsed_response = parser.parse_grade_detail(config_data)
            return parsed_response
        else:
            return HeyDealerGradeDetailResponse(
                success=False,
                data={},
                message="Конфигурации для этой модели ещё не загружены",
            )

    except Exception as e:
        logger.error(f"Ошибка в эндпоинте получения конфигураций: {str(e)}")
        return HeyDealerGradeDetailResponse(
            success=False, data={}, message=f"Ошибка: {str(e)}"
        )


@router.get("/cars/filtered/raw", response_model=Dict[str, Any])
async def get_filtered_cars_raw(
    page: int = Query(1, description="Номер страницы"),
    grade: Optional[str] = Query(None, description="ID конфигурации"),
):
    """Получение сырых данных отфильтрованных автомобилей (from data store)"""
    try:
        cars_data = heydealer_data_store.get_cars_raw()
        if grade:
            cars_data = [
                c for c in cars_data
                if c.get("detail", {}).get("grade", {}).get("hash_id") == grade
            ]

        return {
            "success": True,
            "data": cars_data,
            "count": len(cars_data) if cars_data else 0,
            "message": "Сырые данные отфильтрованных автомобилей (из кэша)",
        }

    except Exception as e:
        logger.error(f"Ошибка в эндпоинте сырых данных автомобилей: {str(e)}")
        return {"success": False, "data": [], "message": f"Ошибка: {str(e)}"}


# === ПРЯМЫЕ ЭНДПОИНТЫ ДЛЯ ТЕСТИРОВАНИЯ ===


@router.get("/brands-direct", response_model=Dict[str, Any])
async def get_brands_direct():
    """Прямое получение списка марок без сервиса (debug — uses live API)"""
    try:
        # Данные из файла brands.py
        cookies = {
            "_gid": "GA1.2.607092972.1750804665",
            "ga_dsi": "2f27c9738d9441acb3019f0388816973",
            "_gat": "1",
            "_ga_P1L3JSNSES": "GS2.2.s1750808840$o1$g0$t1750808840$j60$l0$h0",
            "_ga_4N2EP0M69Q": "GS2.1.s1750808839$o1$g0$t1750808842$j57$l0$h0",
            "_ga": "GA1.2.225253972.1750804665",
            "csrftoken": "86vF233dOdoOCeznt8rwfXkVlwacieWi",
            "sessionid": "03qqprbun190abkr8nj2dkfcxzvfvmxl",
            "_ga_D0D36Y0VSC": "GS2.2.s1750804665$o1$g1$t1750809091$j50$l0$h0",
        }

        headers = {
            "Accept": "*/*",
            "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "App-Os": "pc",
            "App-Type": "dealer",
            "App-Version": "1.9.0",
            "Connection": "keep-alive",
            "Origin": "https://dealer.heydealer.com",
            "Referer": "https://dealer.heydealer.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "X-CSRFToken": "86vF233dOdoOCeznt8rwfXkVlwacieWi",
            "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

        params = {
            "type": "auction",
            "is_subscribed": "false",
            "is_retried": "false",
            "is_previously_bid": "false",
        }

        response = requests.get(
            "https://api.heydealer.com/v2/dealers/web/car_meta/brands/",
            params=params,
            cookies=cookies,
            headers=headers,
            timeout=10,
        )

        if response.status_code == 200:
            brands_data = response.json()
            return {
                "success": True,
                "data": brands_data,
                "count": len(brands_data),
                "message": f"Получено {len(brands_data)} марок напрямую",
            }
        else:
            return {
                "success": False,
                "data": [],
                "status_code": response.status_code,
                "message": f"Ошибка API: {response.status_code}",
            }

    except Exception as e:
        logger.error(f"Ошибка в прямом эндпоинте марок: {str(e)}")
        return {"success": False, "data": [], "message": f"Ошибка: {str(e)}"}


@router.get("/brands/{brand_hash_id}/direct", response_model=Dict[str, Any])
async def get_brand_models_direct(brand_hash_id: str):
    """Прямое получение моделей для марки без сервиса"""
    try:
        # Данные из файла get-models.py
        cookies = {
            "_ga": "GA1.2.225253972.1750804665",
            "_gid": "GA1.2.607092972.1750804665",
            "ga_dsi": "2f27c9738d9441acb3019f0388816973",
            "csrftoken": "oF1QX8pojFyAYw9J9yYO3JZgEHkxNEzB",
            "sessionid": "9kr7h1uvkd0y7dqjq3tlrbptgsd1jxi2",
            "_gat": "1",
            "_ga_D0D36Y0VSC": "GS2.2.s1750804665$o1$g1$t1750805516$j60$l0$h0",
        }

        headers = {
            "Accept": "*/*",
            "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "App-Os": "pc",
            "App-Type": "dealer",
            "App-Version": "1.9.0",
            "Connection": "keep-alive",
            "Origin": "https://dealer.heydealer.com",
            "Referer": "https://dealer.heydealer.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "X-CSRFToken": "oF1QX8pojFyAYw9J9yYO3JZgEHkxNEzB",
            "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

        params = {
            "type": "auction",
            "is_subscribed": "false",
            "is_retried": "false",
            "is_previously_bid": "false",
        }

        response = requests.get(
            f"https://api.heydealer.com/v2/dealers/web/car_meta/brands/{brand_hash_id}/",
            params=params,
            cookies=cookies,
            headers=headers,
            timeout=10,
        )

        if response.status_code == 200:
            brand_data = response.json()
            return {
                "success": True,
                "data": brand_data,
                "brand_name": brand_data.get("name", ""),
                "models_count": len(brand_data.get("model_groups", [])),
                "message": f"Получены модели для марки {brand_hash_id}",
            }
        else:
            return {
                "success": False,
                "data": {},
                "status_code": response.status_code,
                "message": f"Ошибка API: {response.status_code}",
            }

    except Exception as e:
        logger.error(f"Ошибка в прямом эндпоинте моделей: {str(e)}")
        return {"success": False, "data": {}, "message": f"Ошибка: {str(e)}"}


@router.get("/cars/filtered/direct", response_model=Dict[str, Any])
async def get_filtered_cars_direct(
    page: int = Query(1, description="Номер страницы"),
    grade: Optional[str] = Query(None, description="ID конфигурации"),
    order: str = Query("default", description="Сортировка"),
):
    """Прямое получение отфильтрованных автомобилей без сервиса"""
    try:
        # Данные из файла filtered-cars.py
        cookies = {
            "_gid": "GA1.2.607092972.1750804665",
            "ga_dsi": "2f27c9738d9441acb3019f0388816973",
            "ga_P1L3JSNSES": "GS2.2.s1750808840$o1$g0$t1750808840$j60$l0$h0",
            "ga_4N2EP0M69Q": "GS2.1.s1750808839$o1$g0$t1750808842$j57$l0$h0",
            "_ga": "GA1.2.225253972.1750804665",
            "csrftoken": "86vF233dOdoOCeznt8rwfXkVlwacieWi",
            "sessionid": "03qqprbun190abkr8nj2dkfcxzvfvmxl",
            "_gat": "1",
            "multidb_pin_writes": "y",
            "_ga_D0D36Y0VSC": "GS2.2.s1750804665$o1$g1$t1750809091$j50$l0$h0",
        }

        headers = {
            "Accept": "*/*",
            "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "App-Os": "pc",
            "App-Type": "dealer",
            "App-Version": "1.9.0",
            "Connection": "keep-alive",
            "Origin": "https://dealer.heydealer.com",
            "Referer": "https://dealer.heydealer.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "X-CSRFToken": "86vF233dOdoOCeznt8rwfXkVlwacieWi",
            "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

        params = {
            "page": str(page),
            "type": "auction",
            "is_subscribed": "false",
            "is_retried": "false",
            "is_previously_bid": "false",
            "order": order,
        }

        # Добавляем фильтр по конфигурации если указан
        if grade:
            params["grade"] = grade

        response = requests.get(
            "https://api.heydealer.com/v2/dealers/web/cars/",
            params=params,
            cookies=cookies,
            headers=headers,
            timeout=10,
        )

        if response.status_code == 200:
            cars_data = response.json()
            return {
                "success": True,
                "data": cars_data,
                "count": len(cars_data),
                "page": page,
                "filters": {"grade": grade, "order": order},
                "message": f"Получено {len(cars_data)} автомобилей с фильтрами",
            }
        else:
            return {
                "success": False,
                "data": [],
                "status_code": response.status_code,
                "message": f"Ошибка API: {response.status_code}",
            }

    except Exception as e:
        logger.error(f"Ошибка в прямом эндпоинте автомобилей: {str(e)}")
        return {"success": False, "data": [], "message": f"Ошибка: {str(e)}"}


# === НОВЫЕ МАРШРУТЫ ДЛЯ СОВМЕСТИМОСТИ С FRONTEND ===


async def find_brand_by_name(brand_name: str) -> Optional[str]:
    """Поиск hash_id бренда по названию (на английском или корейском)"""
    try:
        brands_data = heydealer_data_store.get_brands()

        if not brands_data:
            return None

        # Словарь соответствий английских названий корейским
        brand_mapping = {
            "hyundai": "현대",
            "kia": "기아",
            "genesis": "제네시스",
            "samsung": "삼성",
            "chevrolet": "쉐보레",
            "toyota": "토요타",
            "honda": "혼다",
            "nissan": "닛산",
            "mazda": "마쯔다",
            "volkswagen": "폭스바겐",
            "bmw": "BMW",
            "mercedes": "메르세데스-벤츠",
            "audi": "아우디",
            "lexus": "렉서스",
            "infiniti": "인피니티",
            "acura": "아큐라",
            "cadillac": "캐딜락",
            "lincoln": "링컨",
            "volvo": "볼보",
            "jaguar": "재규어",
            "land rover": "랜드로버",
            "porsche": "포르쉐",
            "ferrari": "페라리",
            "lamborghini": "람보르기니",
            "bentley": "벤틀리",
            "rolls royce": "롤스로이스",
            "maserati": "마세라티",
            "alfa romeo": "알파로메오",
        }

        # Ищем по точному совпадению
        brand_name_lower = brand_name.lower()
        korean_name = brand_mapping.get(brand_name_lower, brand_name)

        for brand in brands_data:
            if (
                brand.get("name", "").lower() == brand_name_lower
                or brand.get("name", "") == korean_name
                or brand.get("name", "") == brand_name
            ):
                return brand.get("hash_id")

        return None

    except Exception as e:
        logger.error(f"Ошибка поиска бренда по названию {brand_name}: {str(e)}")
        return None


@router.get("/brands/{brand_name}/models", response_model=HeyDealerBrandDetailResponse)
async def get_brand_models_by_name(brand_name: str):
    """Получение списка моделей для выбранной марки по названию"""
    try:
        # Находим hash_id бренда по названию
        brand_hash_id = await find_brand_by_name(brand_name)

        if not brand_hash_id:
            return HeyDealerBrandDetailResponse(
                success=False, data={}, message=f"Бренд {brand_name} не найден"
            )

        # Используем существующую функцию
        return await get_brand_models(brand_hash_id)

    except Exception as e:
        logger.error(f"Ошибка в эндпоинте получения моделей по названию: {str(e)}")
        return HeyDealerBrandDetailResponse(
            success=False, data={}, message=f"Ошибка: {str(e)}"
        )


@router.get("/filters", response_model=Dict[str, Any])
async def get_filters():
    """Получение всех доступных фильтров для frontend (from data store)"""
    try:
        brands_data = heydealer_data_store.get_brands()

        if not brands_data:
            return {
                "success": False,
                "data": {},
                "message": "Не удалось получить данные фильтров",
            }

        # Формируем структуру фильтров для frontend
        filters_data = {
            "brands": [
                {
                    "id": brand.get("hash_id"),
                    "name": brand.get("name"),
                    "count": brand.get("count", 0),
                }
                for brand in brands_data
            ],
            "fuel_types": [
                {"id": "gasoline", "name": "Бензин"},
                {"id": "diesel", "name": "Дизель"},
                {"id": "hybrid", "name": "Гибрид"},
                {"id": "electric", "name": "Электро"},
                {"id": "lpg", "name": "ГБО"},
            ],
            "transmissions": [
                {"id": "manual", "name": "Механика"},
                {"id": "automatic", "name": "Автомат"},
                {"id": "cvt", "name": "Вариатор"},
            ],
            "years": {"min": 1990, "max": 2025},
            "price": {"min": 0, "max": 100000000},
            "mileage": {"min": 0, "max": 500000},
        }

        return {
            "success": True,
            "data": filters_data,
            "message": f"Получены фильтры с {len(brands_data)} брендами",
        }

    except Exception as e:
        logger.error(f"Ошибка в эндпоинте фильтров: {str(e)}")
        return {"success": False, "data": {}, "message": f"Ошибка: {str(e)}"}


async def find_model_group_by_name(model_group_name: str) -> Optional[str]:
    """Поиск hash_id группы моделей по названию"""
    try:
        # Словарь соответствий английских названий корейским для BMW
        model_mapping = {
            "1-series": "1시리즈",
            "2-series": "2시리즈",
            "3-series": "3시리즈",
            "4-series": "4시리즈",
            "5-series": "5시리즈",
            "6-series": "6시리즈",
            "7-series": "7시리즈",
            "8-series": "8시리즈",
            "6-er": "6시리즈",
            "x1": "X1",
            "x2": "X2",
            "x3": "X3",
            "x4": "X4",
            "x5": "X5",
            "x6": "X6",
            "x7": "X7",
            "z3": "Z3",
            "z4": "Z4",
            "i3": "i3",
            "i8": "i8",
            "m3": "M3",
            "m5": "M5",
            "m6": "M6",
        }

        # Поскольку у нас нет полного списка всех model_groups,
        # попробуем найти через бренды
        brands_data = heydealer_data_store.get_brands()

        if not brands_data:
            return None

        # Преобразуем название если есть соответствие
        search_name = model_mapping.get(model_group_name.lower(), model_group_name)

        # Ищем во всех брендах
        for brand in brands_data:
            try:
                brand_models = heydealer_data_store.get_brand_models(brand.get("hash_id"))
                if brand_models and "model_groups" in brand_models:
                    for model_group in brand_models["model_groups"]:
                        model_name = model_group.get("name", "")
                        if (
                            model_name.lower() == model_group_name.lower()
                            or model_name == search_name
                            or model_name == model_group_name
                        ):
                            return model_group.get("hash_id")
            except:
                continue

        return None

    except Exception as e:
        logger.error(
            f"Ошибка поиска model_group по названию {model_group_name}: {str(e)}"
        )
        return None


@router.get(
    "/model-groups/{model_group_name}/generations",
    response_model=HeyDealerModelDetailResponse,
)
async def get_model_generations_by_name(model_group_name: str):
    """Получение списка поколений для выбранной модели по названию"""
    try:
        # Находим hash_id группы моделей по названию
        model_group_hash_id = await find_model_group_by_name(model_group_name)

        if not model_group_hash_id:
            return HeyDealerModelDetailResponse(
                success=False,
                data={},
                message=f"Группа моделей {model_group_name} не найдена",
            )

        # Используем существующую функцию
        return await get_model_generations(model_group_hash_id)

    except Exception as e:
        logger.error(f"Ошибка в эндпоинте получения поколений по названию: {str(e)}")
        return HeyDealerModelDetailResponse(
            success=False, data={}, message=f"Ошибка: {str(e)}"
        )


@router.get("/cars/{car_hash_id}/debug")
async def get_car_debug(car_hash_id: str):
    """Отладочная информация об автомобиле (from data store)"""
    try:
        car_data = heydealer_data_store.get_car_detail(car_hash_id)
        if not car_data:
            raise HTTPException(status_code=404, detail="Автомобиль не найден в кэше")

        debug_info = {
            "hash_id": car_hash_id,
            "status": car_data.get("status"),
            "detail_keys": list(car_data.get("detail", {}).keys()),
            "auction_keys": list(car_data.get("auction", {}).keys()),
            "etc_keys": list(car_data.get("etc", {}).keys()),
            "has_detail": bool(car_data.get("detail")),
            "has_auction": bool(car_data.get("auction")),
            "has_etc": bool(car_data.get("etc")),
            "source": "data_store",
        }

        return {
            "success": True,
            "data": debug_info,
            "message": "Отладочная информация получена",
            "timestamp": datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения отладочной информации: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === НОВЫЕ ЭНДПОИНТЫ ДЛЯ ТЕХНИЧЕСКОГО ЛИСТА ===


@router.get("/cars/{car_hash_id}/accident-repairs")
async def get_car_accident_repairs(car_hash_id: str):
    """
    Получает технический лист (accident repairs) для автомобиля (from data store)

    Args:
        car_hash_id: Уникальный ID автомобиля

    Returns:
        Технический лист с информацией о состоянии всех частей автомобиля
    """
    try:
        accident_repairs = heydealer_data_store.get_accident_repairs(car_hash_id)
        if not accident_repairs:
            raise HTTPException(
                status_code=404, detail="Технический лист для автомобиля не найден"
            )

        # Парсим данные
        parsed_data = HeyDealerParser.parse_accident_repairs(accident_repairs)
        if not parsed_data:
            raise HTTPException(
                status_code=500, detail="Ошибка парсинга технического листа"
            )

        return {
            "success": True,
            "data": parsed_data,
            "message": "Технический лист успешно получен",
            "timestamp": datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения технического листа для {car_hash_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cars/{car_hash_id}/with-accident-repairs")
async def get_car_with_accident_repairs(car_hash_id: str):
    """
    Получает детальную информацию об автомобиле вместе с техническим листом (from data store)

    Args:
        car_hash_id: Уникальный ID автомобиля

    Returns:
        Полная информация об автомобиле включая технический лист
    """
    try:
        car_detail = heydealer_data_store.get_car_detail(car_hash_id)
        accident_data = heydealer_data_store.get_accident_repairs(car_hash_id)
        combined_data = car_detail
        if combined_data and accident_data:
            combined_data["accident_repairs"] = accident_data
        if not combined_data:
            raise HTTPException(
                status_code=404, detail="Автомобиль или его технический лист не найден"
            )

        # Парсим комбинированные данные
        parsed_data = HeyDealerParser.parse_car_with_accident_repairs(
            combined_data, combined_data.get("accident_repairs")
        )
        if not parsed_data:
            raise HTTPException(
                status_code=500,
                detail="Ошибка парсинга данных автомобиля с техническим листом",
            )

        return {
            "success": True,
            "data": parsed_data,
            "message": "Данные автомобиля с техническим листом успешно получены",
            "timestamp": datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Ошибка получения данных автомобиля {car_hash_id} с техническим листом: {e}"
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cars/{car_hash_id}/accident-repairs/raw")
async def get_car_accident_repairs_raw(car_hash_id: str):
    """
    Получает сырые данные технического листа (from data store)

    Args:
        car_hash_id: Уникальный ID автомобиля

    Returns:
        Необработанные данные технического листа
    """
    try:
        raw_data = heydealer_data_store.get_accident_repairs(car_hash_id)
        if not raw_data:
            raise HTTPException(
                status_code=404, detail="Технический лист для автомобиля не найден"
            )

        return {
            "success": True,
            "data": raw_data,
            "message": "Сырые данные технического листа получены",
            "timestamp": datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Ошибка получения сырых данных технического листа для {car_hash_id}: {e}"
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cars/{car_hash_id}/accident-repairs/summary")
async def get_car_accident_repairs_summary(car_hash_id: str):
    """
    Получает краткую сводку по техническому листу автомобиля

    Args:
        car_hash_id: Уникальный ID автомобиля

    Returns:
        Краткая сводка о состоянии автомобиля
    """
    try:
        accident_repairs = heydealer_data_store.get_accident_repairs(car_hash_id)
        if not accident_repairs:
            raise HTTPException(
                status_code=404, detail="Технический лист для автомобиля не найден"
            )

        # Анализируем данные для создания сводки
        repairs_list = accident_repairs.get("accident_repairs", [])

        summary = {
            "total_parts": len(repairs_list),
            "parts_with_repairs": 0,
            "parts_with_exchange": 0,
            "parts_with_weld": 0,
            "frame_parts_damaged": 0,
            "outer_panel_parts_damaged": 0,
            "critical_damage": False,
            "max_reduction_ratio": 0.0,
            "damaged_parts": [],
        }

        for part in repairs_list:
            repair_type = part.get("repair", "none")
            category = part.get("category", "")

            if repair_type != "none":
                summary["parts_with_repairs"] += 1
                summary["damaged_parts"].append(
                    {
                        "part": part.get("part_display", part.get("part", "")),
                        "repair": part.get("repair_display", repair_type),
                        "category": category,
                    }
                )

                if repair_type == "exchange":
                    summary["parts_with_exchange"] += 1
                elif repair_type == "weld":
                    summary["parts_with_weld"] += 1

                if "frame" in category:
                    summary["frame_parts_damaged"] += 1
                    summary["critical_damage"] = True
                elif "outer_panel" in category:
                    summary["outer_panel_parts_damaged"] += 1

                # Находим максимальный коэффициент снижения
                max_ratio = part.get("max_reduction_ratio", {})
                exchange_ratio = max_ratio.get("exchange", 0.0)
                weld_ratio = max_ratio.get("weld", 0.0)
                current_max = max(exchange_ratio, weld_ratio)

                if current_max > summary["max_reduction_ratio"]:
                    summary["max_reduction_ratio"] = current_max

        # Определяем общее состояние
        if summary["parts_with_repairs"] == 0:
            summary["condition"] = "excellent"
            summary["condition_display"] = "Отличное состояние"
        elif summary["critical_damage"]:
            summary["condition"] = "poor"
            summary["condition_display"] = "Плохое состояние (повреждения рамы)"
        elif summary["parts_with_repairs"] > 3:
            summary["condition"] = "fair"
            summary["condition_display"] = "Удовлетворительное состояние"
        else:
            summary["condition"] = "good"
            summary["condition_display"] = "Хорошее состояние"

        return {
            "success": True,
            "data": summary,
            "message": "Сводка по техническому листу успешно создана",
            "timestamp": datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Ошибка создания сводки технического листа для {car_hash_id}: {e}"
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cars/{car_hash_id}/accident-repairs/demo")
async def get_car_accident_repairs_demo(car_hash_id: str):
    """
    Демонстрационный эндпоинт с тестовыми данными технического листа

    Args:
        car_hash_id: Уникальный ID автомобиля

    Returns:
        Пример структуры данных технического листа
    """
    try:
        # Используем данные из предоставленного файла
        demo_data = {
            "type": None,
            "image_url": "https://heydealer-api.s3.amazonaws.com/static-dj42/img/v2/categorized_accident/dealers/web/accident_repairs_front_panel.fd308c17aee5.png",
            "image_width": 420,
            "accident_repairs": [
                {
                    "part": "bumper_front",
                    "part_display": "앞범퍼 또는 라이트",
                    "repair": "none",
                    "repair_display": "없음",
                    "position": [148, 12],
                    "category": "etc",
                    "max_reduction_ratio": {"exchange": 0.0, "weld": 0.0},
                    "max_reduction_ratio_for_zero": {"exchange": 0.0, "weld": 0.0},
                },
                {
                    "part": "hood",
                    "part_display": "본넷",
                    "repair": "none",
                    "repair_display": "없음",
                    "position": [148, 72],
                    "category": "outer_panel_rank_1",
                    "max_reduction_ratio": {"exchange": 0.04, "weld": 0.04},
                    "max_reduction_ratio_for_zero": {"exchange": 0.03, "weld": 0.02},
                },
                {
                    "part": "trunk_lid",
                    "part_display": "트렁크 도어",
                    "repair": "exchange",
                    "repair_display": "교환",
                    "position": [148, 240],
                    "category": "outer_panel_rank_1",
                    "max_reduction_ratio": {"exchange": 0.03, "weld": 0.03},
                    "max_reduction_ratio_for_zero": {"exchange": 0.02, "weld": 0.02},
                },
            ],
        }

        # Парсим демо-данные
        parsed_data = HeyDealerParser.parse_accident_repairs(demo_data)
        if not parsed_data:
            raise HTTPException(
                status_code=500, detail="Ошибка парсинга демонстрационных данных"
            )

        return {
            "success": True,
            "data": parsed_data,
            "message": f"Демонстрационный технический лист для автомобиля {car_hash_id}",
            "timestamp": datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT"),
            "note": "Это демонстрационные данные для показа структуры технического листа",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Ошибка создания демонстрационного технического листа для {car_hash_id}: {e}"
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cars/{car_hash_id}/accident-diagram")
async def get_car_accident_diagram(car_hash_id: str, use_scraper: bool = True):
    """
    Получает диаграмму повреждений автомобиля
    
    Args:
        car_hash_id: Уникальный ID автомобиля
        use_scraper: Использовать Playwright scraper для получения полных данных
        
    Returns:
        URL изображения диаграммы и данные о повреждениях
    """
    try:
        logger.info(f"Получение диаграммы повреждений для автомобиля {car_hash_id}")
        
        # Если use_scraper=True, пробуем использовать Playwright для полных данных
        if use_scraper:
            try:
                from app.services.heydealer_playwright_scraper import scrape_car_diagram
                import asyncio
                
                logger.info(f"Использование Playwright scraper для {car_hash_id}")
                scraped_data = await scrape_car_diagram(car_hash_id)
                
                if scraped_data.get("success"):
                    # Добавляем метки для маркеров если их нет
                    for repair in scraped_data.get("data", {}).get("accident_repairs", []):
                        if not repair.get("label"):
                            if repair.get("repair") == "weld":
                                repair["label"] = "W"
                            elif repair.get("repair") == "painted":
                                repair["label"] = "P"
                            elif repair.get("repair") == "exchange":
                                repair["label"] = "E"
                    
                    scraped_data["timestamp"] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT")
                    return scraped_data
                    
            except Exception as e:
                logger.warning(f"Playwright scraper failed, falling back to API: {e}")
        
        # Fallback: read from data store
        diagram_data = heydealer_data_store.get_accident_repairs(car_hash_id)

        if not diagram_data:
            raise HTTPException(
                status_code=404,
                detail=f"Диаграмма повреждений для {car_hash_id} не найдена в кэше"
            )

        # Merge actual damage data from car details
        car_details = heydealer_data_store.get_car_detail(car_hash_id)
        if car_details:
            detail_section = car_details.get('detail', {})
            actual_repairs = detail_section.get('accident_repairs', [])
            if actual_repairs:
                repair_map = {}
                for repair in actual_repairs:
                    part = repair.get('part', '')
                    repair_type = repair.get('repair', 'none')
                    if part and repair_type != 'none':
                        repair_map[part] = repair_type

                for diagram_repair in diagram_data.get('accident_repairs', []):
                    part_name = diagram_repair.get('part', '')
                    if part_name in repair_map:
                        diagram_repair['repair'] = repair_map[part_name]
                        repair_displays = {
                            'weld': '용접 (Welded)',
                            'painted': '도색 (Painted)',
                            'exchange': '교환 (Exchanged)',
                            'none': '없음 (None)'
                        }
                        diagram_repair['repair_display'] = repair_displays.get(repair_map[part_name], repair_map[part_name])
        
        # Обрабатываем данные о повреждениях
        accident_repairs = []
        raw_repairs = diagram_data.get("accident_repairs", [])
        
        for repair in raw_repairs:
            # Преобразуем данные о повреждениях с учетом возможных вариантов структуры
            repair_item = {
                "part": repair.get("part", ""),
                "part_display": repair.get("part_display", repair.get("part", "")),
                "repair": repair.get("repair", "none"),
                "repair_display": repair.get("repair_display", repair.get("repair", "")),
                "position": repair.get("position", [0, 0]),
                "category": repair.get("category", "etc"),
                "max_reduction_ratio": repair.get("max_reduction_ratio", {
                    "exchange": 0,
                    "weld": 0
                }),
                "label": ""  # Add label field
            }
            
            # Add label based on repair type
            if repair_item["repair"] == "weld":
                repair_item["label"] = "W"
            elif repair_item["repair"] == "painted":
                repair_item["label"] = "P"
            elif repair_item["repair"] == "exchange":
                repair_item["label"] = "E"
            
            accident_repairs.append(repair_item)
        
        # Подсчитываем типы повреждений
        damage_counts = diagram_data.get("damage_summary", {
            "exchange": 0,
            "weld": 0,
            "painted": 0,
            "none": 0
        })
        
        # If damage_summary is not in diagram_data, calculate it
        if "damage_summary" not in diagram_data:
            damage_counts = {
                "exchange": 0,
                "weld": 0,
                "painted": 0,
                "none": 0
            }
            
            for repair in accident_repairs:
                repair_type = repair.get("repair", "none")
                if repair_type in damage_counts:
                    damage_counts[repair_type] += 1
                elif repair_type != "none":
                    # Для неизвестных типов считаем как exchange
                    damage_counts["exchange"] += 1
        
        # Извлекаем информацию о диаграмме
        result = {
            "success": True,
            "data": {
                "type": diagram_data.get("type"),
                "image_url": diagram_data.get("image_url"),
                "image_width": diagram_data.get("image_width", 420),
                "accident_repairs": accident_repairs,
                "total_damages": sum([
                    damage_counts["exchange"],
                    damage_counts["weld"],
                    damage_counts["painted"]
                ]),
                "damage_summary": damage_counts
            },
            "message": "Диаграмма повреждений успешно получена",
            "timestamp": datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT"),
        }
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения диаграммы повреждений для {car_hash_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === SYNC CONTROL ENDPOINTS ===


@router.get("/sync/status")
async def get_sync_status():
    """Get current HeyDealer data sync status and freshness"""
    meta = heydealer_data_store.get_sync_metadata()
    return {
        "success": True,
        "sync": meta,
        "data_available": heydealer_data_store.is_data_available(),
        "data_age_seconds": heydealer_data_store.get_data_age_seconds(),
    }


@router.post("/sync/trigger")
async def trigger_sync():
    """Manually trigger a HeyDealer data sync"""
    import threading
    from app.services.heydealer_sync_service import HeyDealerSyncService

    sync_service = HeyDealerSyncService()
    thread = threading.Thread(target=sync_service.run_sync, daemon=True)
    thread.start()

    return {
        "success": True,
        "message": "Sync triggered in background",
        "current_status": heydealer_data_store.get_sync_metadata(),
    }
