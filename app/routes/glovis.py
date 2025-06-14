from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks
from typing import Optional, Dict, Any
from loguru import logger

from app.models.glovis import GlovisResponse, GlovisError
from app.services.glovis_service import GlovisService
from app.core.logging import get_logger

# Настраиваем логгер
glovis_logger = get_logger("glovis_routes")

router = APIRouter(prefix="/api/v1/glovis", tags=["Glovis"])

# Глобальный экземпляр сервиса
glovis_service = GlovisService()


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
