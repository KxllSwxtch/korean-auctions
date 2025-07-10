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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/heydealer", tags=["HeyDealer"])


def get_heydealer_service() -> HeyDealerService:
    """Dependency для получения сервиса HeyDealer"""
    return HeyDealerService()


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
            f"Получение автомобилей HeyDealer: страница {page}, тип {auction_type}"
        )
        logger.info(
            f"Параметры фильтров: brand={brand}, model_group={model_group}, model={model}, grade={grade}"
        )

        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()

        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            return HeyDealerResponse(
                success=False,
                data=None,
                message="Ошибка авторизации HeyDealer",
                total_count=0,
                current_page=page,
            )

        # Подготавливаем параметры
        params = {
            "page": page,
            "type": auction_type,
            "is_subscribed": str(is_subscribed).lower(),
            "is_retried": str(is_retried).lower(),
            "is_previously_bid": str(is_previously_bid).lower(),
            "order": order,
        }

        # Добавляем параметры фильтрации если они указаны (и не пустые)
        if brand and brand.strip():
            # Проверяем, является ли brand hash_id (6 символов, содержит буквы и цифры)
            if len(brand) == 6 and brand.replace("_", "").replace("-", "").isalnum():
                # Это hash_id, используем как есть
                params["brand"] = brand
                logger.info(f"Используем brand hash_id: {brand}")
            else:
                # Для обратной совместимости пытаемся найти hash_id по названию
                brand_hash_id = await find_brand_by_name(brand)
                if brand_hash_id:
                    params["brand"] = brand_hash_id
                    logger.info(f"Найден hash_id для бренда {brand}: {brand_hash_id}")
                else:
                    logger.warning(
                        f"Бренд {brand} не найден. Используйте hash_id из 6 символов"
                    )

        # Обработка model_group - расширяем до generation IDs
        needs_model_group_expansion = False
        if model_group and model_group.strip() and not model:
            # Принимаем только hash_id (как в оригинальном API HeyDealer)
            if (
                len(model_group) == 6
                and model_group.replace("_", "").replace("-", "").isalnum()
            ):
                # HeyDealer API не поддерживает model_group напрямую
                needs_model_group_expansion = True
                logger.info(f"🔧 model_group ({model_group}) будет расширен до generation IDs")
            else:
                logger.warning(
                    f"Неверный формат model_group: {model_group}. Ожидается hash_id из 6 символов"
                )
        if model and model.strip():
            # Принимаем только hash_id для model (поколение)
            if len(model) == 6 and model.replace("_", "").replace("-", "").isalnum():
                params["model"] = model
                logger.info(f"Используем model hash_id: {model}")
            else:
                logger.warning(
                    f"Неверный формат model: {model}. Ожидается hash_id из 6 символов"
                )

        if grade and grade.strip():
            # Принимаем только hash_id для grade (конфигурация)
            if len(grade) == 6 and grade.replace("_", "").replace("-", "").isalnum():
                params["grade"] = grade
                logger.info(f"✅ Используем grade hash_id: {grade} для фильтрации")
            else:
                logger.warning(
                    f"⚠️ Неверный формат grade: {grade}. Ожидается hash_id из 6 символов"
                )

        # Если нужно расширение model_group
        if needs_model_group_expansion:
            from app.services.heydealer_model_mapper import HeyDealerModelMapper
            
            generation_ids = HeyDealerModelMapper.get_generation_ids_for_model_group(model_group)
            
            if not generation_ids:
                logger.warning(f"Не найдены generation IDs для model_group {model_group}")
                return HeyDealerResponse(
                    success=True,
                    data=HeyDealerCarList(cars=[], total_count=0, page=page),
                    message=f"Не найдены поколения для модели {model_group}",
                    total_count=0,
                    current_page=page,
                )
            
            # Делаем запросы для каждого generation
            all_cars = []
            for gen_id in generation_ids:
                gen_params = params.copy()
                gen_params["model"] = gen_id
                # Удаляем brand, так как generation ID уже подразумевает конкретный бренд
                gen_params.pop("brand", None)
                
                logger.info(f"Запрос для generation {gen_id} с параметрами: {gen_params}")
                gen_response = requests.get(
                    "https://api.heydealer.com/v2/dealers/web/cars/",
                    params=gen_params,
                    headers=headers,
                    cookies=cookies,
                    timeout=30,
                )
                
                if gen_response.status_code == 200:
                    gen_cars = gen_response.json()
                    all_cars.extend(gen_cars)
                    logger.info(f"Получено {len(gen_cars)} автомобилей для generation {gen_id}")
            
            cars_data = all_cars
            total_count = len(cars_data)
            
            # Применяем пагинацию к объединенным результатам
            page_size = 20
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            cars_data = cars_data[start_index:end_index]
            
            logger.info(f"Всего получено {total_count} автомобилей для model_group {model_group}")
        else:
            # Обычный запрос
            logger.info(f"📡 Отправка запроса к HeyDealer API с параметрами: {params}")
            
            # Создаем полный URL для логирования
            from urllib.parse import urlencode
            full_url = f"https://api.heydealer.com/v2/dealers/web/cars/?{urlencode(params)}"
            logger.info(f"🔍 Полный URL запроса: {full_url}")
            
            response = requests.get(
                "https://api.heydealer.com/v2/dealers/web/cars/",
                params=params,
                headers=headers,
                cookies=cookies,
                timeout=30,
            )
        
        # Обрабатываем результаты
        if not needs_model_group_expansion:
            # Логируем статус и первые несколько машин для отладки
            logger.info(f"📊 Статус ответа: {response.status_code}")
            logger.info(f"📊 Заголовки пагинации: Count={response.headers.get('X-Pagination-Count', 'N/A')}, PageSize={response.headers.get('X-Pagination-Page-Size', 'N/A')}")

            if response.status_code == 200:
                cars_data = response.json()
                
                # Извлекаем информацию о пагинации из заголовков
                total_count = int(response.headers.get("X-Pagination-Count", 0))
                page_size = int(response.headers.get("X-Pagination-Page-Size", 20))

                # Если total_count = 0, это означает бесконечную прокрутку
                if total_count == 0:
                    link_header = response.headers.get("Link", "")
                    has_next_page = 'rel="next"' in link_header

                    if has_next_page:
                        estimated_total = len(cars_data) + (page * page_size)
                    else:
                        estimated_total = len(cars_data) + ((page - 1) * page_size)

                    total_count = estimated_total
            else:
                logger.error(
                    f"Ошибка получения автомобилей HeyDealer: {response.status_code} - {response.text}"
                )
                return HeyDealerResponse(
                    success=False,
                    data=None,
                    message=f"Ошибка получения данных: {response.status_code}",
                    total_count=0,
                    current_page=page,
                )
            
            # Логируем количество и примеры машин для отладки
            logger.info(f"📊 Получено автомобилей: {len(cars_data)}")
            if cars_data and len(cars_data) > 0:
                first_car = cars_data[0]
                car_detail = first_car.get('detail', {})
                logger.info(f"🚗 Пример первого автомобиля: full_name={car_detail.get('full_name', 'N/A')}, model_part={car_detail.get('model_part_name', 'N/A')}")
                
                # Проверяем, применились ли фильтры
                if model_group:
                    # Проверяем первые несколько машин
                    logger.info(f"🔍 Проверка применения фильтра model_group={model_group}:")
                    for i, car in enumerate(cars_data[:5]):
                        car_model = car.get('detail', {}).get('model_part_name', '')
                        logger.info(f"  Авто {i+1}: {car_model}")

        # Парсим данные через парсер (для обоих случаев)
        parser = HeyDealerParser()
        car_list = parser.parse_car_list_with_pagination(
            cars_data, total_count, page, page_size
        )

        if not car_list:
            logger.error("Не удалось распарсить данные автомобилей")
            return HeyDealerResponse(
                success=False,
                data=None,
                message="Ошибка парсинга данных",
                total_count=0,
                current_page=page,
            )

        # Нормализуем данные через парсер для правильного отображения
        normalized_data = parser.format_response_data(
            cars=car_list.cars, total_count=car_list.total_count, page=page
        )

        # Формируем успешный ответ в формате HeyDealerResponse
        response_obj = HeyDealerResponse(
            success=True,
            data=car_list,  # Оставляем для совместимости с моделью
            message=f"Успешно получено {len(car_list.cars)} автомобилей",
            total_count=car_list.total_count,
            current_page=page,
        )

        logger.info(f"✅ Успешно получено {len(car_list.cars)} автомобилей HeyDealer")
        if grade:
            logger.info(f"🔍 Фильтрация по grade={grade} применена на стороне API")

        # Возвращаем нормализованные данные вместо Pydantic объектов
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
        logger.info(
            f"Получение нормализованных автомобилей HeyDealer: страница {page}, тип {auction_type}"
        )

        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()

        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            return {
                "success": False,
                "message": "Ошибка авторизации HeyDealer",
                "cars": [],
                "total_count": 0,
                "current_page": page,
                "auction_name": "HeyDealer",
            }

        # Подготавливаем параметры
        params = {
            "page": page,
            "type": auction_type,
            "is_subscribed": str(is_subscribed).lower(),
            "is_retried": str(is_retried).lower(),
            "is_previously_bid": str(is_previously_bid).lower(),
            "order": order,
        }

        # Выполняем запрос
        response = requests.get(
            "https://api.heydealer.com/v2/dealers/web/cars/",
            params=params,
            headers=headers,
            cookies=cookies,
            timeout=30,
        )

        if response.status_code == 200:
            cars_data = response.json()

            # Парсим данные через парсер
            parser = HeyDealerParser()
            car_list = parser.parse_car_list(cars_data)

            if not car_list:
                return {
                    "success": False,
                    "message": "Ошибка парсинга данных",
                    "cars": [],
                    "total_count": 0,
                    "current_page": page,
                    "auction_name": "HeyDealer",
                }

            # Нормализуем данные через парсер
            normalized_data = parser.format_response_data(
                cars=car_list.cars, total_count=car_list.total_count, page=page
            )

            logger.info(
                f"Успешно получено {len(car_list.cars)} автомобилей HeyDealer (normalized)"
            )
            return normalized_data
        else:
            logger.error(
                f"Ошибка получения автомобилей HeyDealer: {response.status_code} - {response.text}"
            )
            return {
                "success": False,
                "message": f"Ошибка получения данных: {response.status_code}",
                "cars": [],
                "total_count": 0,
                "current_page": page,
                "auction_name": "HeyDealer",
            }

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
        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()

        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            return {
                "status": "error",
                "message": "Ошибка авторизации HeyDealer",
                "auction_name": "HeyDealer",
                "authenticated": False,
            }

        # Проверяем доступность API
        response = requests.get(
            "https://api.heydealer.com/v2/dealers/web/cars/",
            params={"page": 1, "type": "auction", "is_subscribed": "false"},
            headers=headers,
            cookies=cookies,
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json()
            return {
                "status": "success",
                "message": f"Подключение к HeyDealer API работает. Получено {len(data)} автомобилей.",
                "auction_name": "HeyDealer",
                "authenticated": True,
                "cars_count": len(data),
            }
        else:
            return {
                "status": "error",
                "message": f"Ошибка подключения к HeyDealer API: {response.status_code}",
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
    """Получение отфильтрованного списка автомобилей"""
    try:
        logger.info(f"Получение отфильтрованных автомобилей HeyDealer: страница {page}")

        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()

        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            return {
                "success": False,
                "data": {"cars": [], "total_count": 0, "page": page},
                "message": "Ошибка авторизации HeyDealer",
                "total_count": 0,
                "current_page": page,
            }

        # Подготавливаем параметры
        params = {
            "page": page,
            "type": "auction",
            "is_subscribed": "false",
            "is_retried": "false",
            "is_previously_bid": "false",
            "order": order,
        }

        # Добавляем фильтры (только если они не пустые и валидные)
        if brand and brand.strip():
            # Проверяем формат hash_id для brand
            if len(brand) == 6 and brand.replace("_", "").replace("-", "").isalnum():
                params["brand"] = brand
                logger.info(f"Используем brand hash_id: {brand}")
            else:
                logger.warning(
                    f"Неверный формат brand: {brand}. Ожидается hash_id из 6 символов"
                )

        # Обработка model_group - НЕ добавляем в params, так как API не поддерживает
        needs_model_group_expansion = False
        if model_group and model_group.strip() and not model:
            # Проверяем формат hash_id для model_group
            if (
                len(model_group) == 6
                and model_group.replace("_", "").replace("-", "").isalnum()
            ):
                # HeyDealer API не поддерживает model_group напрямую
                # Нужно будет сделать отдельные запросы для каждого generation
                needs_model_group_expansion = True
                logger.info(f"Model_group {model_group} будет расширен до generation IDs")
            else:
                logger.warning(
                    f"Неверный формат model_group: {model_group}. Ожидается hash_id из 6 символов"
                )

        if model and model.strip():
            # Проверяем формат hash_id для model
            if len(model) == 6 and model.replace("_", "").replace("-", "").isalnum():
                params["model"] = model
                logger.info(f"Используем model hash_id: {model}")
            else:
                logger.warning(
                    f"Неверный формат model: {model}. Ожидается hash_id из 6 символов"
                )

        if grade and grade.strip():
            # Проверяем формат hash_id для grade
            if len(grade) == 6 and grade.replace("_", "").replace("-", "").isalnum():
                params["grade"] = grade
                logger.info(f"Используем grade hash_id: {grade}")
            else:
                logger.warning(
                    f"Неверный формат grade: {grade}. Ожидается hash_id из 6 символов"
                )
        if min_year:
            params["min_year"] = min_year
        if max_year:
            params["max_year"] = max_year
        if min_price:
            params["min_price"] = min_price
        if max_price:
            params["max_price"] = max_price
        if min_mileage:
            params["min_mileage"] = min_mileage
        if max_mileage:
            params["max_mileage"] = max_mileage
        if fuel and fuel.strip():
            params["fuel"] = fuel
        if transmission and transmission.strip():
            params["transmission"] = transmission
        if wheel_drive and wheel_drive.strip():
            # Wheel drive should be sent as a list
            wheel_drive_values = [v.strip() for v in wheel_drive.split(',') if v.strip()]
            if wheel_drive_values:
                params["wheel_drive"] = wheel_drive_values
                logger.info(f"Используем wheel_drive: {wheel_drive_values}")
        if location and location.strip():
            params["location"] = location

        logger.info(f"Параметры фильтрации: {params}")
        
        # Если нужно расширение model_group
        if needs_model_group_expansion:
            from app.services.heydealer_model_mapper import HeyDealerModelMapper
            
            generation_ids = HeyDealerModelMapper.get_generation_ids_for_model_group(model_group)
            
            if not generation_ids:
                logger.warning(f"Не найдены generation IDs для model_group {model_group}")
                return {
                    "success": True,
                    "data": {"cars": [], "total_count": 0, "page": page},
                    "message": f"Не найдены поколения для модели {model_group}",
                    "total_count": 0,
                    "current_page": page,
                }
            
            # Делаем запросы для каждого generation
            all_cars = []
            for gen_id in generation_ids:
                gen_params = params.copy()
                gen_params["model"] = gen_id
                # Удаляем brand, так как generation ID уже подразумевает конкретный бренд
                gen_params.pop("brand", None)
                
                logger.info(f"Запрос для generation {gen_id} с параметрами: {gen_params}")
                gen_response = requests.get(
                    "https://api.heydealer.com/v2/dealers/web/cars/",
                    params=gen_params,
                    headers=headers,
                    cookies=cookies,
                    timeout=30,
                )
                
                if gen_response.status_code == 200:
                    gen_cars = gen_response.json()
                    all_cars.extend(gen_cars)
                    logger.info(f"Получено {len(gen_cars)} автомобилей для generation {gen_id}")
            
            cars_data = all_cars
            logger.info(f"Model group expansion для {model_group}: получено {len(cars_data)} автомобилей из {len(generation_ids)} поколений")
        else:
            # Обычный запрос
            response = requests.get(
                "https://api.heydealer.com/v2/dealers/web/cars/",
                params=params,
                headers=headers,
                cookies=cookies,
                timeout=30,
            )
            
            if response.status_code != 200:
                logger.error(f"Ошибка API: {response.status_code}")
                return {
                    "success": False,
                    "data": {"cars": [], "total_count": 0, "page": page},
                    "message": f"Ошибка получения данных: {response.status_code}",
                    "total_count": 0,
                    "current_page": page,
                }
                
            cars_data = response.json()
        
        # Теперь обрабатываем полученные данные
        logger.info(f"Получено {len(cars_data)} автомобилей с фильтрами")

        # Парсим данные через парсер для нормализации
        from app.parsers.heydealer_parser import HeyDealerParser

        parser = HeyDealerParser()

        # Создаем Pydantic объекты и нормализуем данные
        normalized_cars = []
        for car_data in cars_data:
            try:
                # Создаем Pydantic объект
                pydantic_car = HeyDealerCar(**car_data)

                # Нормализуем данные через парсер
                normalized_car = parser.normalize_car_data(pydantic_car)

                # Дополняем данными из сырого API ответа (для полей, которых нет в Pydantic)
                detail_data = car_data.get("detail", {})

                # Извлекаем данные о топливе и трансмиссии из названия и других полей
                title = normalized_car.get("title", "")
                grade_part_name = normalized_car.get("grade_part_name", "")

                # Определяем тип топлива из названия
                fuel_type = None
                fuel_display = None
                if "가솔린" in title or "가솔린" in grade_part_name:
                    fuel_type = "gasoline"
                    fuel_display = "Бензин"
                elif "디젤" in title or "디젤" in grade_part_name:
                    fuel_type = "diesel"
                    fuel_display = "Дизель"
                elif "하이브리드" in title or "하이브리드" in grade_part_name:
                    fuel_type = "hybrid"
                    fuel_display = "Гибрид"
                elif "전기" in title or "전기" in grade_part_name or "EV" in title:
                    fuel_type = "electric"
                    fuel_display = "Электро"
                elif "LPG" in title or "LPI" in title:
                    fuel_type = "lpg"
                    fuel_display = "ГБО"

                # Определяем тип трансмиссии из названия
                transmission_type = None
                transmission_display = None
                if (
                    "AWD" in title
                    or "AWD" in grade_part_name
                    or "4WD" in title
                    or "4WD" in grade_part_name
                ):
                    transmission_type = "awd"
                    transmission_display = "Полный привод"
                elif (
                    "2WD" in title
                    or "2WD" in grade_part_name
                    or "FWD" in title
                    or "FWD" in grade_part_name
                ):
                    transmission_type = "fwd"
                    transmission_display = "Передний привод"
                elif "RWD" in title or "RWD" in grade_part_name:
                    transmission_type = "rwd"
                    transmission_display = "Задний привод"

                # Пытаемся определить коробку передач (это сложнее, так как в названии не всегда указано)
                gear_type = None
                gear_display = None
                if "수동" in title:  # Ручная
                    gear_type = "manual"
                    gear_display = "Механика"
                elif "자동" in title:  # Автоматическая
                    gear_type = "automatic"
                    gear_display = "Автомат"
                elif "CVT" in title:
                    gear_type = "cvt"
                    gear_display = "Вариатор"
                else:
                    # По умолчанию считаем автоматической для современных автомобилей
                    gear_type = "automatic"
                    gear_display = "Автомат"

                normalized_car.update(
                    {
                        "fuel": fuel_type,
                        "fuel_display": fuel_display,
                        "fuel_type": fuel_type,
                        "transmission": transmission_type,
                        "transmission_display": transmission_display,
                        "gear": gear_type,
                        "gear_display": gear_display,
                        "payment": detail_data.get("payment"),
                        "payment_display": detail_data.get("payment_display"),
                        "color": detail_data.get("color"),
                        "accident": detail_data.get("accident"),
                        "accident_display": detail_data.get("accident_display"),
                    }
                )

                normalized_cars.append(normalized_car)
            except Exception as e:
                logger.error(f"Ошибка обработки автомобиля: {e}")
                continue

        # Применяем пагинацию если нужно
        total_count = len(normalized_cars)
        page_size = 20
        
        # Если это расширение model_group, применяем пагинацию к объединенным результатам
        if needs_model_group_expansion:
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            normalized_cars = normalized_cars[start_index:end_index]

        # Возвращаем структуру, совместимую с /cars endpoint
        return {
            "success": True,
            "data": {
                "cars": normalized_cars,
                "total_count": total_count,
                "page": page,
            },
            "message": f"Получено {len(normalized_cars)} автомобилей с фильтрами",
            "total_count": total_count,
            "current_page": page,
            "pagination": {
                "current_page": page,
                "total_count": total_count,
                "page_size": page_size,
                "has_next": len(normalized_cars) == page_size,
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

        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()

        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            return HeyDealerCarWithTechSheetResponse(
                success=False,
                data=None,
                message="Ошибка авторизации HeyDealer",
                timestamp=datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT"),
                total_requests=0,
                car_request_success=False,
                accident_repairs_request_success=False,
            )

        # Выполняем два запроса параллельно
        detail_url = f"https://api.heydealer.com/v2/dealers/web/cars/{car_hash_id}/"
        accident_repairs_url = f"https://api.heydealer.com/v2/dealers/web/accident_repairs_for_auction/{car_hash_id}/"

        # Параллельные запросы для лучшей производительности
        import asyncio
        import aiohttp

        async def fetch_car_details():
            try:
                response = requests.get(
                    detail_url, headers=headers, cookies=cookies, timeout=30
                )
                return response.status_code, (
                    response.json() if response.status_code == 200 else None
                )
            except Exception as e:
                logger.error(f"Ошибка получения данных автомобиля: {e}")
                return 500, None

        async def fetch_accident_repairs():
            try:
                response = requests.get(
                    accident_repairs_url, headers=headers, cookies=cookies, timeout=30
                )
                return response.status_code, (
                    response.json() if response.status_code == 200 else None
                )
            except Exception as e:
                logger.error(f"Ошибка получения технического листа: {e}")
                return 500, None

        # Выполняем запросы параллельно
        car_status, car_data = await fetch_car_details()
        repairs_status, repairs_data = await fetch_accident_repairs()

        # Проверяем успешность основного запроса
        if car_status != 200 or not car_data:
            logger.error(f"Ошибка получения детальной информации: {car_status}")
            return HeyDealerCarWithTechSheetResponse(
                success=False,
                data=None,
                message=f"Ошибка получения данных автомобиля: {car_status}",
                timestamp=datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT"),
                total_requests=2,
                car_request_success=False,
                accident_repairs_request_success=repairs_status == 200,
            )

        # Извлекаем данные автомобиля
        detail_section = car_data.get("detail", {})
        auction_section = car_data.get("auction", {})
        etc_section = car_data.get("etc", {})

        # Обрабатываем данные технического листа
        accident_repairs_data = None
        accident_repairs_available = False
        accident_repairs_error = None

        if repairs_status == 200 and repairs_data:
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
            accident_repairs_error = (
                f"Ошибка получения технического листа: {repairs_status}"
            )
            logger.warning(
                f"Не удалось получить технический лист для {car_hash_id}: {repairs_status}"
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
            total_requests=2,
            car_request_success=True,
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
                "timestamp": detail_response.headers.get("Date", ""),
            }

            return result
        else:
            logger.error(
                f"Ошибка получения детальной информации: {detail_response.status_code} - {detail_response.text}"
            )
            return {
                "success": False,
                "error": f"Ошибка получения данных: {detail_response.status_code}",
                "detail": detail_response.text,
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


@router.get("/cars/{car_hash_id}/debug")
async def debug_heydealer_car(
    car_hash_id: str = Path(..., description="Hash ID автомобиля"),
):
    """
    Отладочный endpoint для проверки данных

    - **car_hash_id**: Уникальный идентификатор автомобиля (hash_id)
    """
    try:
        # Используем автоматический сервис авторизации
        cookies, headers = heydealer_auth.get_valid_session()

        if not cookies or not headers:
            logger.error("Не удалось получить валидную сессию HeyDealer")
            return {
                "success": False,
                "status_code": 500,
                "error": "Ошибка авторизации HeyDealer",
            }

        # Прямой запрос к API
        response = requests.get(
            f"https://api.heydealer.com/v2/dealers/web/cars/{car_hash_id}/",
            headers=headers,
            cookies=cookies,
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
            # Парсим данные через парсер
            from app.parsers.heydealer_parser import HeyDealerParser

            parser = HeyDealerParser()
            parsed_response = parser.parse_model_detail(model_data)
            return parsed_response
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
            # Парсим данные через парсер
            from app.parsers.heydealer_parser import HeyDealerParser

            parser = HeyDealerParser()
            parsed_response = parser.parse_grade_detail(config_data)
            return parsed_response
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
    service: HeyDealerService = Depends(get_heydealer_service),
):
    """Получение сырых данных отфильтрованных автомобилей для отладки"""
    try:
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
        service = HeyDealerService()
        brands_data = await service.get_brands()

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
    """Получение всех доступных фильтров для frontend"""
    try:
        service = HeyDealerService()

        # Получаем список брендов
        brands_data = await service.get_brands()

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
        service = HeyDealerService()
        brands_data = await service.get_brands()

        if not brands_data:
            return None

        # Преобразуем название если есть соответствие
        search_name = model_mapping.get(model_group_name.lower(), model_group_name)

        # Ищем во всех брендах
        for brand in brands_data:
            try:
                brand_models = await service.get_brand_models(brand.get("hash_id"))
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
    """Отладочная информация об автомобиле"""
    try:
        service = HeyDealerService()

        # Получаем детальные данные
        car_detail = await service.get_car_detail(car_hash_id)
        if not car_detail:
            raise HTTPException(status_code=404, detail="Автомобиль не найден")

        # Формируем отладочную информацию
        debug_info = {
            "hash_id": car_hash_id,
            "status": car_detail.status,
            "detail_keys": list(car_detail.detail.__dict__.keys()),
            "auction_keys": list(car_detail.auction.__dict__.keys()),
            "etc_keys": list(car_detail.etc.__dict__.keys()),
            "has_detail": bool(car_detail.detail),
            "has_auction": bool(car_detail.auction),
            "has_etc": bool(car_detail.etc),
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
    Получает технический лист (accident repairs) для автомобиля

    Args:
        car_hash_id: Уникальный ID автомобиля

    Returns:
        Технический лист с информацией о состоянии всех частей автомобиля
    """
    try:
        service = HeyDealerService()

        # Получаем технический лист
        accident_repairs = await service.get_accident_repairs(car_hash_id)
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
    Получает детальную информацию об автомобиле вместе с техническим листом

    Args:
        car_hash_id: Уникальный ID автомобиля

    Returns:
        Полная информация об автомобиле включая технический лист
    """
    try:
        service = HeyDealerService()

        # Получаем комбинированные данные
        combined_data = await service.get_car_with_accident_repairs(car_hash_id)
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
    Получает сырые данные технического листа (для отладки)

    Args:
        car_hash_id: Уникальный ID автомобиля

    Returns:
        Необработанные данные технического листа от API
    """
    try:
        service = HeyDealerService()

        # Получаем сырые данные
        raw_data = await service.get_accident_repairs(car_hash_id)
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
        service = HeyDealerService()

        # Получаем технический лист
        accident_repairs = await service.get_accident_repairs(car_hash_id)
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
