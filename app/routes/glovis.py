from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks, Body
from typing import Optional, Dict, Any, List
from datetime import datetime
from loguru import logger
from urllib.parse import unquote

from app.models.glovis import GlovisResponse, GlovisError
from app.models.glovis_filters import (
    GlovisFilterOptions,
    GlovisManufacturersResponse,
    GlovisModelsResponse,
    GlovisDetailModelsResponse,
    GlovisFilteredCarsResponse,
)
from app.services.glovis_service import GlovisService
from app.core.logging import get_logger
from app.utils.glovis_cookies_updater import GlovisCookiesUpdater

# Настраиваем логгер
glovis_logger = get_logger("glovis_routes")

router = APIRouter(prefix="/api/v1/glovis", tags=["Glovis"])

# Глобальный экземпляр сервиса
glovis_service = GlovisService()


def get_glovis_service() -> GlovisService:
    """Dependency для получения экземпляра GlovisService"""
    return glovis_service


@router.get("/cars", response_model=GlovisResponse)
async def get_glovis_cars(
    page: int = Query(1, ge=1, description="Номер страницы"),
    search_rc: Optional[str] = Query(
        None, description="Регион поиска (1100=분당, 2100=시화, 3100=양산, 5100=인천)"
    ),
    search_type: Optional[str] = Query(
        None, description="Тип поиска (exhino=выставочный номер, carno=номер авто)"
    ),
    search_text: Optional[str] = Query(None, description="Текст для поиска"),
    car_manufacturer: Optional[str] = Query(None, description="Код производителя"),
    auction_number: Optional[str] = Query(None, description="Номер аукциона"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> GlovisResponse:
    """
    Получить список автомобилей с аукциона Hyundai Glovis

    **Параметры поиска:**
    - **page**: Номер страницы (по умолчанию 1)
    - **search_rc**: Регион (1100=분당, 2100=시화, 3100=양산, 5100=인천)
    - **search_type**: Тип поиска (exhino или carno)
    - **search_text**: Текст для поиска
    - **car_manufacturer**: Код производителя автомобиля
    - **auction_number**: Номер аукциона

    **Пример использования:**
    ```
    GET /api/v1/glovis/cars?page=1&search_rc=1100&auction_number=944
    ```
    """
    try:
        glovis_logger.info(f"📥 Запрос списка автомобилей Glovis (страница {page})")

        # Подготавливаем параметры
        params = {"page": page}

        if search_rc:
            params["search_rc"] = search_rc
        if search_type:
            params["search_type"] = search_type
        if search_text:
            params["search_text"] = search_text
        if car_manufacturer:
            params["car_manufacturer"] = car_manufacturer
        if auction_number:
            params["auction_number"] = auction_number

        # Получаем данные
        result = await glovis_service.get_car_list(params)

        if result.success:
            glovis_logger.info(
                f"✅ Успешно получено {len(result.cars)} автомобилей Glovis"
            )
        else:
            glovis_logger.error(f"❌ Ошибка получения данных Glovis: {result.message}")

        return result

    except Exception as e:
        glovis_logger.error(
            f"❌ Неожиданная ошибка при получении автомобилей Glovis: {e}"
        )
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/cars/{car_gn}", response_model=Dict[str, Any])
async def get_glovis_car_details(
    car_gn: str,
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> Dict[str, Any]:
    """
    Получить детальную информацию об автомобиле по его GN идентификатору

    **Параметры:**
    - **car_gn**: Уникальный идентификатор автомобиля (GN)

    **Пример использования:**
    ```
    GET /api/v1/glovis/cars/teMUgP8zkuB4ZMgXXSZJdA==
    ```
    """
    try:
        glovis_logger.info(f"📥 Запрос деталей автомобиля Glovis gn={car_gn}")

        # Получаем детальную информацию
        result = await glovis_service.get_car_details(car_gn)

        if result:
            glovis_logger.info(f"✅ Успешно получены детали автомобиля Glovis")
            return {
                "success": True,
                "message": "Детальная информация получена",
                "data": result,
            }
        else:
            glovis_logger.warning(f"⚠️ Автомобиль не найден: {car_gn}")
            raise HTTPException(status_code=404, detail="Автомобиль не найден")

    except HTTPException:
        raise
    except Exception as e:
        glovis_logger.error(f"❌ Ошибка при получении деталей автомобиля Glovis: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/test", response_model=GlovisResponse)
async def get_glovis_test_data() -> GlovisResponse:
    """
    Получить тестовые данные Glovis для отладки

    Возвращает фиксированный набор тестовых автомобилей для проверки API.

    **Пример использования:**
    ```
    GET /api/v1/glovis/test
    ```
    """
    try:
        glovis_logger.info("📥 Запрос тестовых данных Glovis")

        result = glovis_service.get_test_data()

        glovis_logger.info(
            f"✅ Возвращены тестовые данные Glovis ({len(result.cars)} автомобилей)"
        )
        return result

    except Exception as e:
        glovis_logger.error(f"❌ Ошибка при получении тестовых данных Glovis: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/regions", response_model=Dict[str, Any])
async def get_glovis_regions() -> Dict[str, Any]:
    """
    Получить список доступных регионов Glovis

    Возвращает справочник регионов с их кодами для использования в параметре search_rc.

    **Пример использования:**
    ```
    GET /api/v1/glovis/regions
    ```
    """
    try:
        glovis_logger.info("📥 Запрос справочника регионов Glovis")

        regions = {
            "1100": {"code": "1100", "name": "분당", "name_en": "Bundang"},
            "2100": {"code": "2100", "name": "시화", "name_en": "Siheung"},
            "3100": {"code": "3100", "name": "양산", "name_en": "Yangsan"},
            "5100": {"code": "5100", "name": "인천", "name_en": "Incheon"},
        }

        return {
            "success": True,
            "message": "Справочник регионов Glovis",
            "data": regions,
        }

    except Exception as e:
        glovis_logger.error(f"❌ Ошибка при получении справочника регионов: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/search-types", response_model=Dict[str, Any])
async def get_glovis_search_types() -> Dict[str, Any]:
    """
    Получить доступные типы поиска Glovis

    Возвращает справочник типов поиска для использования в параметре search_type.

    **Пример использования:**
    ```
    GET /api/v1/glovis/search-types
    ```
    """
    try:
        glovis_logger.info("📥 Запрос справочника типов поиска Glovis")

        search_types = {
            "exhino": {
                "code": "exhino",
                "name": "출품번호",
                "name_en": "Exhibition Number",
            },
            "carno": {"code": "carno", "name": "차량번호", "name_en": "Car Number"},
        }

        return {
            "success": True,
            "message": "Справочник типов поиска Glovis",
            "data": search_types,
        }

    except Exception as e:
        glovis_logger.error(f"❌ Ошибка при получении справочника типов поиска: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/status", response_model=Dict[str, Any])
async def get_glovis_status() -> Dict[str, Any]:
    """
    Проверить статус сервиса Glovis

    Возвращает информацию о состоянии подключения к аукциону Glovis.

    **Пример использования:**
    ```
    GET /api/v1/glovis/status
    ```
    """
    try:
        glovis_logger.info("📥 Проверка статуса сервиса Glovis")

        # Проверяем доступность сервиса
        status_info = {
            "service": "Hyundai Glovis Auction",
            "status": "active",
            "base_url": "https://auction.autobell.co.kr",
            "endpoints": {
                "car_list": "/auction/exhibitListInclude.do",
                "page_size": 18,
                "supported_regions": ["분당", "시화", "양산", "인천"],
                "supported_search_types": ["exhino", "carno"],
            },
            "features": {
                "pagination": True,
                "search": True,
                "car_details": True,
                "real_time_data": True,
            },
        }

        return {
            "success": True,
            "message": "Сервис Glovis активен",
            "data": status_info,
        }

    except Exception as e:
        glovis_logger.error(f"❌ Ошибка при проверке статуса Glovis: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/check-session", response_model=Dict[str, Any])
async def check_glovis_session() -> Dict[str, Any]:
    """
    Проверить валидность сессии Glovis

    Проверяет работоспособность JSESSIONID и других cookies.

    **Пример использования:**
    ```
    GET /api/v1/glovis/check-session
    ```
    """
    try:
        glovis_logger.info("🔍 Запрос на проверку сессии Glovis")

        # Проверяем сессию
        session_status = await glovis_service.check_session_validity()

        return {
            "success": session_status.get("is_valid", False),
            "message": (
                "Сессия валидна"
                if session_status.get("is_valid", False)
                else "Сессия требует обновления"
            ),
            "data": session_status,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        glovis_logger.error(f"❌ Ошибка при проверке сессии Glovis: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.post("/refresh-session", response_model=Dict[str, Any])
async def refresh_glovis_session() -> Dict[str, Any]:
    """
    Принудительно обновить сессию Glovis

    Полезно при получении ошибок 401 или проблемах с аутентификацией.

    **Пример использования:**
    ```
    POST /api/v1/glovis/refresh-session
    ```
    """
    try:
        glovis_logger.info("🔄 Запрос на обновление сессии Glovis")

        # Обновляем сессию
        glovis_service.refresh_session()

        # Проверяем новую сессию
        session_status = await glovis_service.check_session_validity()

        return {
            "success": True,
            "message": "Сессия Glovis успешно обновлена",
            "data": {
                "timestamp": datetime.now().isoformat(),
                "action": "session_refreshed",
                "new_session_status": session_status,
            },
        }

    except Exception as e:
        glovis_logger.error(f"❌ Ошибка при обновлении сессии Glovis: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.post("/update-cookies", response_model=Dict[str, Any])
async def update_glovis_cookies(cookies: Dict[str, str]) -> Dict[str, Any]:
    """
    Обновить cookies для сессии Glovis

    Полезно для ручного обновления JSESSIONID и других cookies.

    **Пример использования:**
    ```json
    POST /api/v1/glovis/update-cookies
    {
      "JSESSIONID": "новый_jsessionid_здесь",
      "_ga_H9G80S9QWN": "новое_значение_здесь"
    }
    ```
    """
    try:
        glovis_logger.info("🍪 Запрос на обновление cookies Glovis")

        # Обновляем cookies
        glovis_service.update_cookies(cookies)

        # Проверяем новую сессию
        session_status = await glovis_service.check_session_validity()

        return {
            "success": True,
            "message": f"Cookies успешно обновлены ({len(cookies)} штук)",
            "data": {
                "timestamp": datetime.now().isoformat(),
                "action": "cookies_updated",
                "updated_cookies": list(cookies.keys()),
                "new_session_status": session_status,
            },
        }

    except Exception as e:
        glovis_logger.error(f"❌ Ошибка при обновлении cookies Glovis: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/filters/manufacturers", response_model=GlovisManufacturersResponse)
async def get_glovis_manufacturers() -> GlovisManufacturersResponse:
    """
    Получить список производителей автомобилей для фильтрации

    Возвращает список доступных производителей с количеством автомобилей.

    **Пример использования:**
    ```
    GET /api/v1/glovis/filters/manufacturers
    ```

    **Ответ включает:**
    - Код производителя (prodmancd)
    - Название производителя
    - Количество доступных автомобилей
    - Статус доступности
    """
    try:
        glovis_logger.info("🏭 Запрос списка производителей Glovis")

        result = await glovis_service.get_manufacturers()

        if result.success:
            glovis_logger.info(f"✅ Получено {result.total_count} производителей")
        else:
            glovis_logger.error(f"❌ Ошибка получения производителей: {result.message}")

        return result

    except Exception as e:
        glovis_logger.error(f"❌ Неожиданная ошибка при получении производителей: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/filters/models/{manufacturer_code}", response_model=GlovisModelsResponse)
async def get_glovis_models(manufacturer_code: str) -> GlovisModelsResponse:
    """
    Получить список моделей для выбранного производителя

    **Параметры:**
    - **manufacturer_code**: Код производителя (prodmancd)

    **Пример использования:**
    ```
    GET /api/v1/glovis/filters/models/2  # Получить модели KIA
    GET /api/v1/glovis/filters/models/5  # Получить модели Hyundai
    ```

    **Ответ включает:**
    - ID модели (makeid)
    - Название модели
    - Код модели (reprcarcd)
    - Количество доступных автомобилей
    """
    try:
        glovis_logger.info(f"🚗 Запрос моделей для производителя {manufacturer_code}")

        result = await glovis_service.get_models(manufacturer_code)

        if result.success:
            glovis_logger.info(f"✅ Получено {result.total_count} моделей")
        else:
            glovis_logger.error(f"❌ Ошибка получения моделей: {result.message}")

        return result

    except Exception as e:
        glovis_logger.error(f"❌ Неожиданная ошибка при получении моделей: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.post("/filters/detail-models", response_model=GlovisDetailModelsResponse)
async def get_glovis_detail_models(
    manufacturer_code: str = Body(..., description="Код производителя"),
    model_codes: List[str] = Body(..., description="Список кодов моделей"),
) -> GlovisDetailModelsResponse:
    """
    Получить детальные модели для выбранных базовых моделей

    **Тело запроса:**
    ```json
    {
        "manufacturer_code": "2",
        "model_codes": ["38", "1420"]
    }
    ```

    **Пример использования:**
    ```
    POST /api/v1/glovis/filters/detail-models
    Content-Type: application/json

    {
        "manufacturer_code": "2",
        "model_codes": ["38"]
    }
    ```

    **Ответ включает:**
    - ID детальной модели
    - Название детальной модели
    - Код детальной модели (detacarcd)
    - Количество доступных автомобилей
    """
    try:
        glovis_logger.info(f"🔍 Запрос детальных моделей для {model_codes}")

        if not model_codes:
            raise HTTPException(
                status_code=400, detail="Необходимо указать хотя бы один код модели"
            )

        result = await glovis_service.get_detail_models(manufacturer_code, model_codes)

        if result.success:
            glovis_logger.info(f"✅ Получено {result.total_count} детальных моделей")
        else:
            glovis_logger.error(
                f"❌ Ошибка получения детальных моделей: {result.message}"
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        glovis_logger.error(
            f"❌ Неожиданная ошибка при получении детальных моделей: {e}"
        )
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.post("/search", response_model=GlovisFilteredCarsResponse)
async def search_glovis_cars_with_filters(
    filters: GlovisFilterOptions,
) -> GlovisFilteredCarsResponse:
    """
    Поиск автомобилей с расширенными фильтрами

    **Тело запроса:**
    ```json
    {
        "manufacturers": ["2", "5"],
        "models": ["38", "64"],
        "detail_models": ["2828", "2829"],
        "min_price": 1000,
        "max_price": 50000,
        "min_year": 2020,
        "max_year": 2024,
        "min_mileage": "10000",
        "max_mileage": "100000",
        "transmission": "자동",
        "location": "1100",
        "car_grade": "A",
        "search_text": "K5",
        "search_type": "exhino",
        "page": 1,
        "page_size": 18,
        "sort_order": "01"
    }
    ```

    **Поддерживаемые фильтры:**
    - **manufacturers**: Список кодов производителей
    - **models**: Список кодов моделей
    - **detail_models**: Список кодов детальных моделей
    - **min_price/max_price**: Диапазон стартовой цены (в тысячах вон)
    - **min_year/max_year**: Диапазон годов выпуска
    - **min_mileage/max_mileage**: Диапазон пробега
    - **transmission**: Тип трансмиссии
    - **location**: Код локации (1100=분당, 2100=시화, и т.д.)
    - **car_grade**: Оценка состояния
    - **search_text**: Текст для поиска
    - **search_type**: Тип поиска (exhino, carno)
    - **page**: Номер страницы
    - **page_size**: Размер страницы (1-100)
    - **sort_order**: Порядок сортировки

    **Пример использования:**
    ```
    POST /api/v1/glovis/search
    Content-Type: application/json

    {
        "manufacturers": ["2"],
        "min_year": 2020,
        "page": 1
    }
    ```
    """
    try:
        glovis_logger.info(f"🔍 Поиск автомобилей с фильтрами")

        result = await glovis_service.search_cars_with_filters(filters)

        if result.success:
            glovis_logger.info(
                f"✅ Найдено {result.total_count} автомобилей "
                f"(страница {result.current_page}/{result.total_pages})"
            )
        else:
            glovis_logger.error(f"❌ Ошибка поиска: {result.message}")

        return result

    except Exception as e:
        glovis_logger.error(f"❌ Неожиданная ошибка при поиске с фильтрами: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/find-car")
async def find_car_by_license_plate(
    license_plate: str = Query(..., description="Номер автомобиля для поиска"),
    max_pages: int = Query(
        3, ge=1, le=10, description="Максимальное количество страниц для поиска"
    ),
):
    """
    Простой поиск автомобиля по номеру (для frontend)

    **Параметры:**
    - **license_plate**: Номер автомобиля (поддерживает URL-кодирование)
    - **max_pages**: Максимальное количество страниц для поиска

    **Пример использования:**
    ```
    GET /api/v1/glovis/find-car?license_plate=244다7548
    GET /api/v1/glovis/find-car?license_plate=244%EB%8B%A47548
    ```
    """
    try:
        # Декодируем номер если он URL-кодирован
        decoded_license_plate = unquote(license_plate)

        glovis_logger.info(
            f"🔍 Поиск автомобиля: {license_plate} -> {decoded_license_plate}"
        )

        # Проверяем только регион 1100 сначала (там большинство автомобилей)
        regions = ["1100", "2100", "3100", "5100"]
        total_checked = 0

        for region in regions:
            # Просматриваем страницы в регионе
            for page in range(1, max_pages + 1):
                try:
                    params = {"page": page, "search_rc": region}
                    result = await glovis_service.get_car_list(params)

                    if not result.success or not result.cars:
                        break

                    total_checked += len(result.cars)

                    # Ищем точное совпадение
                    for car in result.cars:
                        if car.license_plate == decoded_license_plate:
                            return {
                                "success": True,
                                "message": "Автомобиль найден",
                                "found": True,
                                "car": {
                                    "license_plate": car.license_plate,
                                    "car_name": car.car_name,
                                    "gn": car.gn,
                                    "rc": car.rc,
                                    "acc": car.acc,
                                    "atn": car.atn,
                                    "entry_number": car.entry_number,
                                    "year": car.year,
                                    "mileage": car.mileage,
                                    "starting_price": car.starting_price,
                                    "location": car.location.value,
                                    "main_image_url": (
                                        str(car.main_image_url)
                                        if car.main_image_url
                                        else None
                                    ),
                                    "region": region,
                                    "page": page,
                                },
                            }

                except Exception as e:
                    glovis_logger.error(f"❌ Ошибка при поиске: {e}")
                    continue

        return {
            "success": True,
            "message": f"Автомобиль с номером {decoded_license_plate} не найден",
            "found": False,
            "total_checked": total_checked,
            "searched_regions": regions,
        }

    except Exception as e:
        glovis_logger.error(f"❌ Ошибка при поиске: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")


@router.post("/admin/update-cookies")
async def update_cookies_from_curl(
    file_path: str = "glovis-curl-request.py",
    glovis_service: GlovisService = Depends(get_glovis_service),
):
    """
    Обновляет cookies Glovis из curl файла

    Args:
        file_path: Путь к файлу с curl запросом (по умолчанию glovis-curl-request.py)

    Returns:
        Результат обновления cookies
    """
    try:
        logger.info(f"🔄 Начинаю обновление cookies из файла: {file_path}")

        # Извлекаем данные из curl файла
        updater = GlovisCookiesUpdater()
        result = updater.update_cookies_from_curl_file(file_path)

        if not result["success"]:
            logger.error(f"❌ Ошибка извлечения данных: {result['message']}")
            return {
                "success": False,
                "message": result["message"],
                "timestamp": datetime.now().isoformat(),
            }

        # Обновляем cookies в сервисе
        glovis_service.update_cookies(result["cookies"])

        # Проверяем валидность обновленной сессии
        session_check = await glovis_service.check_session_validity()

        logger.info(f"✅ Cookies успешно обновлены из {file_path}")

        return {
            "success": True,
            "message": f"Cookies успешно обновлены из {file_path}",
            "jsessionid": result["jsessionid"],
            "session_valid": session_check.get("is_valid", False),
            "cookies_count": len(result["cookies"]),
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении cookies: {e}")
        return {
            "success": False,
            "message": f"Ошибка при обновлении cookies: {str(e)}",
            "timestamp": datetime.now().isoformat(),
        }


@router.get("/admin/session-info")
async def get_session_info(glovis_service: GlovisService = Depends(get_glovis_service)):
    """
    Получает информацию о текущей сессии Glovis

    Returns:
        Информация о сессии
    """
    try:
        logger.info("📊 Получаю информацию о сессии Glovis")

        # Проверяем валидность сессии
        session_check = await glovis_service.check_session_validity()

        # Получаем текущие cookies
        current_cookies = glovis_service.get_current_cookies()

        # Извлекаем JSESSIONID
        jsessionid = current_cookies.get("JSESSIONID", "Не найден")

        # Информация о сессии
        session_info = {
            "session_valid": session_check.get("is_valid", False),
            "jsessionid": jsessionid,
            "cookies_count": len(current_cookies),
            "session_created": (
                glovis_service._session_created_at.isoformat()
                if glovis_service._session_created_at
                else None
            ),
            "last_cookie_update": (
                glovis_service._last_cookie_update.isoformat()
                if glovis_service._last_cookie_update
                else None
            ),
            "session_expired": glovis_service._is_session_expired(),
            "timestamp": datetime.now().isoformat(),
        }

        logger.info(
            f"📊 Информация о сессии получена: валидность={session_info['session_valid']}"
        )

        return {
            "success": True,
            "session_info": session_info,
            "message": "Информация о сессии получена успешно",
        }

    except Exception as e:
        logger.error(f"❌ Ошибка при получении информации о сессии: {e}")
        return {
            "success": False,
            "message": f"Ошибка при получении информации о сессии: {str(e)}",
            "timestamp": datetime.now().isoformat(),
        }
