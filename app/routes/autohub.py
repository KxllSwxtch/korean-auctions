from fastapi import APIRouter, HTTPException, Query, Depends, status
from typing import Optional, Dict, Any, List
import asyncio

from app.models.autohub import (
    AutohubResponse,
    AutohubError,
    AutohubCar,
    AutohubCarDetail,
    AutohubCarDetailRequest,
    AutohubCarDetailResponse,
)
from app.models.autohub_filters import (
    AutohubSearchRequest,
    AutohubManufacturersResponse,
    AutohubModelsResponse,
    AutohubGenerationsResponse,
    AutohubConfigurationsResponse,
    AutohubConfiguration,
    AutohubAuctionSessionsResponse,
    AutohubFilterInfo,
    AUTOHUB_MANUFACTURERS,
    AUTOHUB_MILEAGE_OPTIONS,
    AUTOHUB_PRICE_OPTIONS,
    AutohubFuelType,
    AutohubAuctionResult,
    AutohubLane,
)
from app.services.autohub_service import autohub_service, AutohubService
from app.core.logging import get_logger

logger = get_logger("autohub_routes")

router = APIRouter(
    responses={404: {"description": "Not found"}},
)


# Dependency для получения сервиса
def get_autohub_service() -> AutohubService:
    return autohub_service


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


@router.post("/car-detail", response_model=AutohubCarDetailResponse)
async def get_car_detail(request: AutohubCarDetailRequest):
    """
    Получение детальной информации об автомобиле

    Требуемые параметры:
    - **auction_number**: Номер аукциона
    - **auction_date**: Дата аукциона в формате YYYY-MM-DD
    - **auction_title**: Название аукциона
    - **auction_code**: Код аукциона
    - **receive_code**: Код получения

    Опциональные параметры:
    - **page_number**: Номер страницы (по умолчанию 1)
    - **page_size**: Размер страницы (по умолчанию 10)
    - **sort_flag**: Флаг сортировки (по умолчанию "entry")
    """
    try:
        result = autohub_service.get_car_detail(request)

        if not result.success:
            raise HTTPException(
                status_code=(
                    status.HTTP_404_NOT_FOUND
                    if "не найден" in (result.error or "")
                    else status.HTTP_503_SERVICE_UNAVAILABLE
                ),
                detail=result.error or "Не удалось получить информацию об автомобиле",
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Внутренняя ошибка сервера: {str(e)}",
        )


@router.get("/car-detail/{auction_number}", response_model=AutohubCarDetailResponse)
async def get_car_detail_by_params(
    auction_number: str,
    auction_date: str = Query(..., description="Дата аукциона в формате YYYY-MM-DD"),
    auction_title: str = Query(..., description="Название аукциона"),
    auction_code: str = Query(..., description="Код аукциона"),
    receive_code: str = Query(..., description="Код получения"),
    page_number: int = Query(1, description="Номер страницы", ge=1),
    page_size: int = Query(10, description="Размер страницы", ge=1, le=100),
    sort_flag: str = Query("entry", description="Флаг сортировки"),
):
    """
    Альтернативный способ получения детальной информации об автомобиле через GET запрос

    - **auction_number**: Номер аукциона
    - **auction_date**: Дата аукциона в формате YYYY-MM-DD
    - **auction_title**: Название аукциона
    - **auction_code**: Код аукциона
    - **receive_code**: Код получения
    - **page_number**: Номер страницы (по умолчанию 1)
    - **page_size**: Размер страницы (по умолчанию 10)
    - **sort_flag**: Флаг сортировки (по умолчанию "entry")
    """

    # Создаем объект запроса
    request = AutohubCarDetailRequest(
        auction_number=auction_number,
        auction_date=auction_date,
        auction_title=auction_title,
        auction_code=auction_code,
        receive_code=receive_code,
        page_number=page_number,
        page_size=page_size,
        sort_flag=sort_flag,
    )

    # Используем тот же обработчик
    return await get_car_detail(request)


@router.post("/auth/set-cookies")
async def set_auth_cookies(cookies: dict):
    """
    Установка cookies для аутентификации

    Передайте словарь с cookies в теле запроса:
    ```json
    {
        "WMONID": "your_wmonid",
        "gubun": "on",
        "userid": "your_userid",
        "JSESSIONID": "your_jsessionid"
    }
    ```
    """
    try:
        autohub_service.set_auth_cookies(cookies)
        return {"message": "Cookies успешно установлены"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при установке cookies: {str(e)}",
        )


@router.post("/search", response_model=AutohubResponse)
async def search_cars(
    search_params: AutohubSearchRequest,
    service: AutohubService = Depends(get_autohub_service),
):
    """
    Расширенный поиск автомобилей с фильтрами
    
    Поддерживает все фильтры с сайта AutoHub:
    - Производитель, модель, поколение
    - Тип топлива, расширенная гарантия
    - Диапазон года выпуска
    - Диапазон пробега
    - Диапазон цен
    - Статус аукциона и полоса
    - Поиск по номерам
    - SOH диагностика
    """
    try:
        logger.info("Расширенный поиск автомобилей с фильтрами")
        
        response = await service.search_cars(search_params)
        
        # Always return the response, even if no cars found
        # Let the frontend handle empty results
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Внутренняя ошибка сервера: {str(e)}",
        )
    finally:
        service.close()


@router.get("/manufacturers", response_model=AutohubManufacturersResponse)
async def get_manufacturers(
    service: AutohubService = Depends(get_autohub_service),
):
    """
    Получает список всех производителей
    
    Returns:
        Список производителей с кодами и названиями
    """
    try:
        logger.info("Получение списка производителей")
        
        response = service.get_manufacturers()
        
        if not response.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.message,
            )
            
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Внутренняя ошибка сервера: {str(e)}",
        )


@router.get("/models/{manufacturer_code}", response_model=AutohubModelsResponse)
async def get_models(
    manufacturer_code: str,
    service: AutohubService = Depends(get_autohub_service),
):
    """
    Получает список моделей для указанного производителя
    
    Args:
        manufacturer_code: Код производителя (например, 'KA' для Kia)
        
    Returns:
        Список моделей с кодами и названиями
    """
    try:
        logger.info(f"Получение моделей для производителя {manufacturer_code}")
        
        response = await service.get_models(manufacturer_code)
        
        if not response.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.message,
            )
            
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Внутренняя ошибка сервера: {str(e)}",
        )
    finally:
        service.close()


@router.get("/generations/{model_code}", response_model=AutohubGenerationsResponse)
async def get_generations(
    model_code: str,
    service: AutohubService = Depends(get_autohub_service),
):
    """
    Получает список поколений для указанной модели
    
    Args:
        model_code: Код модели (например, 'KA01')
        
    Returns:
        Список поколений с кодами и названиями
    """
    try:
        logger.info(f"Получение поколений для модели {model_code}")
        
        response = await service.get_generations(model_code)
        
        if not response.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.message,
            )
            
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Внутренняя ошибка сервера: {str(e)}",
        )
    finally:
        service.close()


@router.get("/configurations/{generation_code}", response_model=AutohubConfigurationsResponse)
async def get_configurations(
    generation_code: str,
    model_code: str = Query(..., description="Код модели (обязательный параметр)"),
    service: AutohubService = Depends(get_autohub_service),
):
    """
    Получает список конфигураций для указанного поколения
    
    Args:
        generation_code: Код поколения (например, '003')
        model_code: Код модели (например, 'HD03')
        
    Returns:
        Список конфигураций с кодами и названиями
    """
    try:
        logger.info(f"Получение конфигураций для поколения {generation_code} модели {model_code}")
        
        response = await service.get_configurations(generation_code, model_code)
        
        if not response.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.message,
            )
            
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Внутренняя ошибка сервера: {str(e)}",
        )
    finally:
        service.close()


@router.get("/auction-sessions", response_model=AutohubAuctionSessionsResponse)
async def get_auction_sessions(
    service: AutohubService = Depends(get_autohub_service),
):
    """
    Получает список активных сессий аукциона
    
    Returns:
        Список сессий с информацией о датах и номерах аукционов
    """
    try:
        logger.info("Получение списка сессий аукциона")
        
        response = await service.get_auction_sessions()
        
        if not response.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.message,
            )
            
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Внутренняя ошибка сервера: {str(e)}",
        )
    finally:
        service.close()


@router.get("/filters/info")
async def get_filters_info():
    """
    Получает информацию о доступных фильтрах
    
    Returns:
        Подробная информация о всех доступных фильтрах и их значениях
    """
    try:
        filter_info = AutohubFilterInfo(
            manufacturers=[
                {"code": m.code, "name": m.name, "name_en": m.name_en or m.name}
                for m in AUTOHUB_MANUFACTURERS
            ],
            fuel_types=[
                {"code": ft.value, "name": name}
                for ft, name in [
                    (AutohubFuelType.ALL, "전체"),
                    (AutohubFuelType.GASOLINE, "휘발유"),
                    (AutohubFuelType.DIESEL, "경유"),
                    (AutohubFuelType.LPG, "LPG"),
                    (AutohubFuelType.HYBRID, "하이브리드"),
                    (AutohubFuelType.ELECTRIC, "전기"),
                    (AutohubFuelType.OTHER, "기타"),
                ]
            ],
            lanes=[
                {"code": lane.value, "name": name}
                for lane, name in [
                    (AutohubLane.ALL, "전체"),
                    (AutohubLane.A, "A레인"),
                    (AutohubLane.B, "B레인"),
                    (AutohubLane.C, "C레인"),
                    (AutohubLane.D, "D레인"),
                ]
            ],
            auction_results=[
                {"code": result.value, "name": name}
                for result, name in [
                    (AutohubAuctionResult.ALL, "전체"),
                    (AutohubAuctionResult.SOLD, "낙찰 & 후상담낙찰"),
                    (AutohubAuctionResult.UNSOLD, "유찰 & 낙찰취소"),
                    (AutohubAuctionResult.NOT_HELD, "미실시"),
                ]
            ],
            year_range={"min": 1990, "max": 2025},
            mileage_options=AUTOHUB_MILEAGE_OPTIONS,
            price_options=AUTOHUB_PRICE_OPTIONS,
        )
        
        return {
            "success": True,
            "message": "Информация о фильтрах получена успешно",
            "filters": filter_info,
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Внутренняя ошибка сервера: {str(e)}",
        )


@router.get("/health")
async def health_check():
    """Проверка здоровья сервиса Autohub"""
    return {"status": "healthy", "service": "autohub", "version": "1.0.0"}


@router.get("/test/models/{manufacturer_code}")
async def test_models_loading(
    manufacturer_code: str,
    auction_code: Optional[str] = Query(None, description="Код аукциона для тестирования"),
    service: AutohubService = Depends(get_autohub_service),
):
    """
    Тестовый эндпоинт для отладки загрузки моделей
    
    Позволяет протестировать загрузку моделей с разными параметрами
    """
    try:
        logger.info(f"Тестирование загрузки моделей для {manufacturer_code}")
        
        # Если передан код аукциона, временно устанавливаем его
        original_code = None
        if auction_code:
            logger.info(f"Использование тестового кода аукциона: {auction_code}")
            # Сохраняем оригинальный код для восстановления
            sessions_response = await service.get_auction_sessions()
            if sessions_response.success and sessions_response.current_session:
                original_code = sessions_response.current_session.auction_code
        
        # Получаем модели
        response = await service.get_models(manufacturer_code)
        
        # Добавляем дополнительную информацию для отладки
        debug_info = {
            "manufacturer_code": manufacturer_code,
            "test_auction_code": auction_code,
            "models_count": len(response.models) if response.success else 0,
            "session_info": {
                "has_session": hasattr(service, "_session") and service._session is not None,
                "cookies": service.session.cookies.get_dict() if service.session else {},
            },
            "response": response.dict(),
        }
        
        return debug_info
        
    except Exception as e:
        logger.error(f"Ошибка при тестировании загрузки моделей: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка тестирования: {str(e)}",
        )
    finally:
        service.close()


@router.get("/test/generations/{model_code}")
async def test_generations_loading(
    model_code: str,
    auction_code: Optional[str] = Query(None, description="Код аукциона для тестирования"),
    use_fallback: bool = Query(False, description="Использовать fallback данные"),
    service: AutohubService = Depends(get_autohub_service),
):
    """
    Тестовый эндпоинт для отладки загрузки поколений
    
    Позволяет протестировать загрузку поколений с разными параметрами
    
    Args:
        model_code: Код модели (например, HD20)
        auction_code: Опциональный код аукциона для тестирования
        use_fallback: Принудительно использовать fallback данные
    """
    try:
        logger.info(f"Тестирование загрузки поколений для {model_code}")
        
        # Получаем поколения
        response = await service.get_generations(model_code)
        
        # Проверяем наличие лог файлов
        import os
        from datetime import datetime
        
        debug_dir = "logs/autohub_debug"
        log_files = []
        if os.path.exists(debug_dir):
            for file in os.listdir(debug_dir):
                if file.startswith(f"generations_response_{model_code}"):
                    log_files.append(file)
        
        # Добавляем дополнительную информацию для отладки
        debug_info = {
            "model_code": model_code,
            "test_auction_code": auction_code,
            "use_fallback": use_fallback,
            "generations_count": len(response.generations) if response.success else 0,
            "has_fallback": model_code == "HD20",
            "session_info": {
                "has_session": hasattr(service, "_session") and service._session is not None,
                "cookies": service.session.cookies.get_dict() if service.session else {},
            },
            "debug_logs": log_files[-5:] if log_files else [],  # Последние 5 логов
            "response": response.dict(),
        }
        
        # Если запрошен тест с fallback и это HD20
        if use_fallback and model_code == "HD20":
            fallback_generations = service._get_fallback_generations(model_code)
            debug_info["fallback_data"] = {
                "count": len(fallback_generations),
                "generations": [{"code": g.generation_code, "name": g.name} for g in fallback_generations]
            }
        
        return debug_info
        
    except Exception as e:
        logger.error(f"Ошибка при тестировании загрузки поколений: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка тестирования: {str(e)}",
        )
    finally:
        service.close()
