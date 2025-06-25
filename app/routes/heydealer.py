from fastapi import APIRouter, HTTPException, Query, Depends, Path
from typing import Optional, Dict, Any
import logging
import requests
import json

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
)
from app.services.heydealer_service import HeyDealerService
from app.parsers.heydealer_parser import HeyDealerParser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/heydealer", tags=["HeyDealer"])


def get_heydealer_service() -> HeyDealerService:
    """Dependency для получения сервиса HeyDealer"""
    return HeyDealerService()


@router.get("/cars", response_model=HeyDealerResponse)
async def get_heydealer_cars(
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
            f"Получение автомобилей HeyDealer: страница {page}, тип {auction_type}"
        )

        # Формируем фильтры
        filters = HeyDealerFilters(
            page=page,
            type=auction_type,
            is_subscribed=is_subscribed,
            is_retried=is_retried,
            is_previously_bid=is_previously_bid,
            order=order,
        )

        # Получаем доступы из конфигурации
        # В реальном приложении эти данные должны быть в environment variables
        username = "arman97"  # Из auctions-auth.txt
        password = "for1657721@"  # Из auctions-auth.txt

        # Получаем автомобили через сервис
        car_list = await service.fetch_cars_with_auth(username, password, filters)

        if car_list is None:
            logger.error("Не удалось получить данные от HeyDealer API")
            return HeyDealerResponse(
                success=False,
                data=None,
                message="Не удалось получить данные от HeyDealer API",
                total_count=0,
                current_page=page,
            )

        # Формируем успешный ответ
        response = HeyDealerResponse(
            success=True,
            data=car_list,
            message="Данные успешно получены",
            total_count=car_list.total_count,
            current_page=page,
        )

        logger.info(f"Успешно получено {len(car_list.cars)} автомобилей HeyDealer")
        return response

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
    Получает нормализованный список автомобилей с аукциона HeyDealer

    Возвращает данные в едином формате для всех аукционов
    """
    try:
        logger.info(f"Получение нормализованных автомобилей HeyDealer: страница {page}")

        # Формируем фильтры
        filters = HeyDealerFilters(
            page=page,
            type=auction_type,
            is_subscribed=is_subscribed,
            is_retried=is_retried,
            is_previously_bid=is_previously_bid,
            order=order,
        )

        # Получаем доступы
        username = "arman97"
        password = "for1657721@"

        # Получаем автомобили
        car_list = await service.fetch_cars_with_auth(username, password, filters)

        if car_list is None:
            return {
                "success": False,
                "message": "Не удалось получить данные от HeyDealer API",
                "cars": [],
                "total_count": 0,
                "current_page": page,
                "auction_name": "HeyDealer",
            }

        # Нормализуем данные через парсер
        parser = HeyDealerParser()
        normalized_data = parser.format_response_data(
            cars=car_list.cars, total_count=car_list.total_count, page=page
        )

        logger.info(
            f"Успешно нормализовано {len(normalized_data['cars'])} автомобилей HeyDealer"
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
    Проверяет статус подключения к HeyDealer API
    """
    try:
        username = "arman97"
        password = "for1657721@"

        # Пытаемся аутентифицироваться
        auth_result = await service.authenticate(username, password)

        if auth_result:
            return {
                "status": "success",
                "message": "Подключение к HeyDealer API работает",
                "auction_name": "HeyDealer",
                "authenticated": True,
            }
        else:
            return {
                "status": "error",
                "message": "Не удалось аутентифицироваться в HeyDealer API",
                "auction_name": "HeyDealer",
                "authenticated": False,
            }

    except Exception as e:
        logger.error(f"Ошибка при проверке статуса HeyDealer: {e}")
        return {
            "status": "error",
            "message": f"Ошибка подключения к HeyDealer API: {str(e)}",
            "auction_name": "HeyDealer",
            "authenticated": False,
        }


@router.get("/cars/{car_hash_id}")
async def get_heydealer_car_detail_final_working(
    car_hash_id: str = Path(..., description="Hash ID автомобиля"),
):
    """
    Получает детальную информацию об автомобиле HeyDealer

    - **car_hash_id**: Уникальный идентификатор автомобиля (hash_id)
    """
    try:
        logger.info(f"Получение детальной информации об автомобиле: {car_hash_id}")

        # Данные для логина
        login_url = "https://api.heydealer.com/v2/dealers/web/login/"
        login_data = {
            "username": "arman97",
            "password": "for1657721@",
            "device_type": "pc",
        }

        # Заголовки
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "App-Os": "pc",
            "App-Type": "dealer",
            "App-Version": "1.9.0",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Origin": "https://dealer.heydealer.com",
            "Referer": "https://dealer.heydealer.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

        # Создаем сессию
        session = requests.Session()

        # Логин
        response = session.post(login_url, json=login_data, headers=headers)

        if response.status_code == 200:
            # Получаем CSRF токен из cookies
            csrf_token = session.cookies.get("csrftoken")
            if csrf_token:
                headers["X-CSRFToken"] = csrf_token

            # Получаем детальную информацию
            detail_url = f"https://api.heydealer.com/v2/dealers/web/cars/{car_hash_id}/"
            detail_response = session.get(detail_url, headers=headers)

            if detail_response.status_code == 200:
                detail_data = detail_response.json()

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
                        "transmission_display": detail_section.get(
                            "transmission_display"
                        ),
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
                        "inspected_condition": detail_section.get(
                            "inspected_condition"
                        ),
                        # Опции и описания
                        "is_advanced_options": detail_section.get(
                            "is_advanced_options"
                        ),
                        "advanced_options": detail_section.get("advanced_options", []),
                        "description": detail_section.get("description"),
                        "car_description": detail_section.get("car_description"),
                        "customer_comment": detail_section.get("customer_comment"),
                        "inspector_comment": detail_section.get("inspector_comment"),
                        "comment": detail_section.get("comment"),
                        # История автомобиля
                        "carhistory_summary": detail_section.get("carhistory_summary"),
                        "vehicle_information": detail_section.get(
                            "vehicle_information"
                        ),
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
                        "zero_auction_message": auction_section.get(
                            "zero_auction_message"
                        ),
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
                    "message": "Детальная информация успешно получена",
                    "timestamp": detail_response.headers.get("Date", ""),
                }

                return result
            else:
                return {
                    "success": False,
                    "error": f"Ошибка получения данных: {detail_response.status_code}",
                    "detail": detail_response.text,
                }
        else:
            return {
                "success": False,
                "error": f"Ошибка аутентификации: {response.status_code}",
                "detail": response.text,
            }

    except Exception as e:
        logger.error(
            f"Ошибка при получении детальной информации об автомобиле {car_hash_id}: {e}"
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

        # Данные для логина
        login_url = "https://api.heydealer.com/v2/dealers/web/login/"
        login_data = {
            "username": "arman97",
            "password": "for1657721@",
            "device_type": "pc",
        }

        # Заголовки
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "App-Os": "pc",
            "App-Type": "dealer",
            "App-Version": "1.9.0",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Origin": "https://dealer.heydealer.com",
            "Referer": "https://dealer.heydealer.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

        # Создаем сессию
        session = requests.Session()

        # Логин
        response = session.post(login_url, json=login_data, headers=headers)

        if response.status_code == 200:
            # Получаем CSRF токен из cookies
            csrf_token = session.cookies.get("csrftoken")
            if csrf_token:
                headers["X-CSRFToken"] = csrf_token

            # Получаем детальную информацию
            detail_url = f"https://api.heydealer.com/v2/dealers/web/cars/{car_hash_id}/"
            detail_response = session.get(detail_url, headers=headers)

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
                        data=HeyDealerCarList(
                            cars=[detailed_car], total_count=1, page=1
                        ),
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
        else:
            logger.error(
                f"Ошибка аутентификации: {response.status_code} - {response.text}"
            )
            return {
                "success": False,
                "data": None,
                "message": f"Ошибка аутентификации: {response.status_code}",
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

        # Данные для логина
        login_url = "https://api.heydealer.com/v2/dealers/web/login/"
        login_data = {
            "username": "arman97",
            "password": "for1657721@",
            "device_type": "pc",
        }

        # Заголовки
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "App-Os": "pc",
            "App-Type": "dealer",
            "App-Version": "1.9.0",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Origin": "https://dealer.heydealer.com",
            "Referer": "https://dealer.heydealer.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

        # Создаем сессию
        session = requests.Session()

        # Логин
        response = session.post(login_url, json=login_data, headers=headers)

        if response.status_code == 200:
            # Получаем CSRF токен из cookies
            csrf_token = session.cookies.get("csrftoken")
            if csrf_token:
                headers["X-CSRFToken"] = csrf_token

            # Получаем детальную информацию
            detail_url = f"https://api.heydealer.com/v2/dealers/web/cars/{car_hash_id}/"
            detail_response = session.get(detail_url, headers=headers)

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
                        "detail_full_name": detail_data.get("detail", {}).get(
                            "full_name"
                        ),
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
        else:
            return {
                "success": False,
                "message": f"Ошибка аутентификации: {response.status_code}",
                "error_text": response.text[:500],
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

        # Данные для логина
        login_url = "https://api.heydealer.com/v2/dealers/web/login/"
        login_data = {
            "username": "arman97",
            "password": "for1657721@",
            "device_type": "pc",
        }

        # Заголовки
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "App-Os": "pc",
            "App-Type": "dealer",
            "App-Version": "1.9.0",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Origin": "https://dealer.heydealer.com",
            "Referer": "https://dealer.heydealer.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

        # Создаем сессию
        session = requests.Session()

        # Логин
        response = session.post(login_url, json=login_data, headers=headers)

        if response.status_code == 200:
            # Получаем CSRF токен из cookies
            csrf_token = session.cookies.get("csrftoken")
            if csrf_token:
                headers["X-CSRFToken"] = csrf_token

            # Получаем детальную информацию
            detail_url = f"https://api.heydealer.com/v2/dealers/web/cars/{car_hash_id}/"
            detail_response = session.get(detail_url, headers=headers)

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
        else:
            return {
                "success": False,
                "message": f"Ошибка аутентификации: {response.status_code}",
                "error_text": response.text[:500],
            }

    except Exception as e:
        logger.error(
            f"Ошибка при получении упрощенных данных об автомобиле {car_hash_id}: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Внутренняя ошибка сервера: {str(e)}",
        )


@router.get("/cars/{car_hash_id}/debug")
async def debug_heydealer_car(
    car_hash_id: str = Path(..., description="Hash ID автомобиля"),
):
    """
    Отладочный endpoint для проверки данных

    - **car_hash_id**: Уникальный идентификатор автомобиля (hash_id)
    """
    try:
        # Используем существующий сервис
        service = HeyDealerService()
        username = "arman97"
        password = "for1657721@"

        # Аутентификация
        auth_result = await service.authenticate(username, password)

        if auth_result:
            # Прямой запрос к API
            response = await service.http_client.get(
                url=f"{service.base_url}/v2/dealers/web/cars/{car_hash_id}/",
                headers=service._get_headers(),
                cookies=service._cookies,
            )

            if response.status_code == 200:
                data = response.json()
                detail_section = data.get("detail", {})
                auction_section = data.get("auction", {})

                return {
                    "success": True,
                    "hash_id": data.get("hash_id"),
                    "status_display": data.get("status_display"),
                    "detail_full_name": detail_section.get("full_name"),
                    "detail_year": detail_section.get("year"),
                    "detail_mileage": detail_section.get("mileage"),
                    "auction_desired_price": auction_section.get("desired_price"),
                    "auction_bids_count": auction_section.get("bids_count"),
                    "detail_keys_count": (
                        len(detail_section.keys()) if detail_section else 0
                    ),
                    "auction_keys_count": (
                        len(auction_section.keys()) if auction_section else 0
                    ),
                }
            else:
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": response.text[:500],
                }
        else:
            return {"success": False, "error": "Authentication failed"}

    except Exception as e:
        return {"success": False, "error": f"Exception: {str(e)}"}


@router.get("/cars/{car_hash_id}/direct-json")
async def get_heydealer_car_detail_direct_json(
    car_hash_id: str = Path(..., description="Hash ID автомобиля"),
):
    """
    Получает детальную информацию об автомобиле HeyDealer без Pydantic моделей
    """
    try:
        logger.info(f"Получение детальной информации об автомобиле: {car_hash_id}")

        # Данные для логина
        login_url = "https://api.heydealer.com/v2/dealers/web/login/"
        login_data = {
            "username": "arman97",
            "password": "for1657721@",
            "device_type": "pc",
        }

        # Заголовки
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "App-Os": "pc",
            "App-Type": "dealer",
            "App-Version": "1.9.0",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Origin": "https://dealer.heydealer.com",
            "Referer": "https://dealer.heydealer.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

        # Создаем сессию
        session = requests.Session()

        # Логин
        response = session.post(login_url, json=login_data, headers=headers)

        if response.status_code == 200:
            # Получаем CSRF токен из cookies
            csrf_token = session.cookies.get("csrftoken")
            if csrf_token:
                headers["X-CSRFToken"] = csrf_token

            # Получаем детальную информацию
            detail_url = f"https://api.heydealer.com/v2/dealers/web/cars/{car_hash_id}/"
            detail_response = session.get(detail_url, headers=headers)

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
        else:
            return {
                "success": False,
                "error": f"Ошибка аутентификации: {response.status_code}",
                "detail": response.text,
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

        # Данные для логина
        login_url = "https://api.heydealer.com/v2/dealers/web/login/"
        login_data = {
            "username": "arman97",
            "password": "for1657721@",
            "device_type": "pc",
        }

        # Заголовки
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "App-Os": "pc",
            "App-Type": "dealer",
            "App-Version": "1.9.0",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Origin": "https://dealer.heydealer.com",
            "Referer": "https://dealer.heydealer.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

        # Создаем сессию
        session = requests.Session()

        # Логин
        response = session.post(login_url, json=login_data, headers=headers)

        if response.status_code == 200:
            # Получаем CSRF токен из cookies
            csrf_token = session.cookies.get("csrftoken")
            if csrf_token:
                headers["X-CSRFToken"] = csrf_token

            # Получаем детальную информацию
            detail_url = f"https://api.heydealer.com/v2/dealers/web/cars/{car_hash_id}/"
            detail_response = session.get(detail_url, headers=headers)

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
        else:
            return {
                "success": False,
                "error": f"Ошибка аутентификации: {response.status_code}",
                "detail": response.text,
            }

    except Exception as e:
        logger.error(
            f"Ошибка при получении детальной информации об автомобиле {car_hash_id}: {e}"
        )
        return {"success": False, "error": f"Внутренняя ошибка сервера: {str(e)}"}


@router.get("/brands", response_model=HeyDealerBrandsResponse)
async def get_brands():
    """Получение списка марок автомобилей"""
    try:
        service = HeyDealerService()
        brands_data = await service.get_brands()

        if brands_data:
            # Парсим данные в модели Pydantic
            brands = [HeyDealerBrand(**brand) for brand in brands_data]
            return HeyDealerBrandsResponse(
                success=True, data=brands, message=f"Получено {len(brands)} марок"
            )
        else:
            return HeyDealerBrandsResponse(
                success=False, data=[], message="Не удалось получить список марок"
            )

    except Exception as e:
        logger.error(f"Ошибка в эндпоинте получения марок: {str(e)}")
        return HeyDealerBrandsResponse(
            success=False, data=[], message=f"Ошибка: {str(e)}"
        )


@router.get("/brands/{brand_hash_id}", response_model=HeyDealerBrandDetailResponse)
async def get_brand_models(brand_hash_id: str):
    """Получение списка моделей для выбранной марки"""
    try:
        service = HeyDealerService()
        brand_data = await service.get_brand_models(brand_hash_id)

        if brand_data:
            return HeyDealerBrandDetailResponse(
                success=True,
                data=brand_data,
                message=f"Получены модели для марки {brand_hash_id}",
            )
        else:
            return HeyDealerBrandDetailResponse(
                success=False, data={}, message="Не удалось получить список моделей"
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
    """Получение списка поколений для выбранной модели"""
    try:
        service = HeyDealerService()
        model_data = await service.get_model_generations(model_group_hash_id)

        if model_data:
            return HeyDealerModelDetailResponse(
                success=True,
                data=model_data,
                message=f"Получены поколения для модели {model_group_hash_id}",
            )
        else:
            return HeyDealerModelDetailResponse(
                success=False, data={}, message="Не удалось получить список поколений"
            )

    except Exception as e:
        logger.error(f"Ошибка в эндпоинте получения поколений: {str(e)}")
        return HeyDealerModelDetailResponse(
            success=False, data={}, message=f"Ошибка: {str(e)}"
        )


@router.get("/models/{model_hash_id}", response_model=HeyDealerGradeDetailResponse)
async def get_model_configurations(model_hash_id: str):
    """Получение списка конфигураций для выбранного поколения"""
    try:
        service = HeyDealerService()
        config_data = await service.get_model_configurations(model_hash_id)

        if config_data:
            return HeyDealerGradeDetailResponse(
                success=True,
                data=config_data,
                message=f"Получены конфигурации для поколения {model_hash_id}",
            )
        else:
            return HeyDealerGradeDetailResponse(
                success=False,
                data={},
                message="Не удалось получить список конфигураций",
            )

    except Exception as e:
        logger.error(f"Ошибка в эндпоинте получения конфигураций: {str(e)}")
        return HeyDealerGradeDetailResponse(
            success=False, data={}, message=f"Ошибка: {str(e)}"
        )


@router.get("/cars/filtered", response_model=HeyDealerListResponse)
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
    location: Optional[str] = Query(None, description="Местоположение"),
):
    """Получение отфильтрованного списка автомобилей"""
    try:
        service = HeyDealerService()

        # Формируем фильтры
        filters = {"page": page, "order": order}

        # Добавляем только непустые фильтры
        if brand:
            filters["brand"] = brand
        if model_group:
            filters["model_group"] = model_group
        if model:
            filters["model"] = model
        if grade:
            filters["grade"] = grade
        if min_year:
            filters["min_year"] = min_year
        if max_year:
            filters["max_year"] = max_year
        if min_price:
            filters["min_price"] = min_price
        if max_price:
            filters["max_price"] = max_price
        if min_mileage:
            filters["min_mileage"] = min_mileage
        if max_mileage:
            filters["max_mileage"] = max_mileage
        if fuel:
            filters["fuel"] = fuel
        if transmission:
            filters["transmission"] = transmission
        if location:
            filters["location"] = location

        cars_data = await service.get_filtered_cars(filters)

        if cars_data:
            # Парсим данные в модели Pydantic
            cars = [HeyDealerCar(**car) for car in cars_data]
            return HeyDealerListResponse(
                success=True,
                data=cars,
                message=f"Получено {len(cars)} автомобилей с фильтрами",
            )
        else:
            return HeyDealerListResponse(
                success=False, data=[], message="Не удалось получить список автомобилей"
            )

    except Exception as e:
        logger.error(f"Ошибка в эндпоинте фильтрации автомобилей: {str(e)}")
        return HeyDealerListResponse(
            success=False, data=[], message=f"Ошибка: {str(e)}"
        )


@router.get("/brands/raw", response_model=Dict[str, Any])
async def get_brands_raw():
    """Получение сырых данных марок для отладки"""
    try:
        service = HeyDealerService()
        brands_data = await service.get_brands()

        return {
            "success": True,
            "data": brands_data,
            "count": len(brands_data) if brands_data else 0,
            "message": "Сырые данные марок",
        }

    except Exception as e:
        logger.error(f"Ошибка в эндпоинте сырых данных марок: {str(e)}")
        return {"success": False, "data": [], "message": f"Ошибка: {str(e)}"}


@router.get("/cars/filtered/raw", response_model=Dict[str, Any])
async def get_filtered_cars_raw(
    page: int = Query(1, description="Номер страницы"),
    grade: Optional[str] = Query(None, description="ID конфигурации"),
):
    """Получение сырых данных отфильтрованных автомобилей для отладки"""
    try:
        service = HeyDealerService()

        filters = {"page": page}
        if grade:
            filters["grade"] = grade

        cars_data = await service.get_filtered_cars(filters)

        return {
            "success": True,
            "data": cars_data,
            "count": len(cars_data) if cars_data else 0,
            "message": "Сырые данные отфильтрованных автомобилей",
        }

    except Exception as e:
        logger.error(f"Ошибка в эндпоинте сырых данных автомобилей: {str(e)}")
        return {"success": False, "data": [], "message": f"Ошибка: {str(e)}"}


# === ПРЯМЫЕ ЭНДПОИНТЫ ДЛЯ ТЕСТИРОВАНИЯ ===


@router.get("/brands/direct", response_model=Dict[str, Any])
async def get_brands_direct():
    """Прямое получение списка марок без сервиса"""
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
            "_ga_D0D36Y0VSC": "GS2.2.s1750804665$o1$g1$t1750808852$j51$l0$h0",
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
            "_ga_P1L3JSNSES": "GS2.2.s1750808840$o1$g0$t1750808840$j60$l0$h0",
            "_ga_4N2EP0M69Q": "GS2.1.s1750808839$o1$g0$t1750808842$j57$l0$h0",
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
