from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional, Dict, Any
from loguru import logger

from app.models.kcar import KCarResponse, KCarCar, KCarStatsResponse, KCarDetailResponse
from app.services.kcar_service import KCarService

router = APIRouter(prefix="/api/v1/kcar", tags=["KCar"])

# Создаем глобальный экземпляр сервиса
kcar_service = KCarService()


@router.get("/cars", response_model=KCarResponse)
async def get_kcar_cars(
    manufacturer: Optional[str] = Query(None, description="Код производителя"),
    model: Optional[str] = Query(None, description="Код модели"),
    year_from: Optional[str] = Query(None, description="Год от"),
    year_to: Optional[str] = Query(None, description="Год до"),
    price_from: Optional[str] = Query(None, description="Цена от"),
    price_to: Optional[str] = Query(None, description="Цена до"),
    mileage_from: Optional[str] = Query(None, description="Пробег от"),
    mileage_to: Optional[str] = Query(None, description="Пробег до"),
    fuel_type: Optional[str] = Query(None, description="Тип топлива"),
    transmission: Optional[str] = Query(None, description="Коробка передач"),
    color: Optional[str] = Query(None, description="Цвет"),
    auction_type: Optional[str] = Query(
        "weekly", description="Тип аукциона (weekly только)"
    ),
    location: Optional[str] = Query(None, description="Локация"),
    page_size: int = Query(50, ge=1, le=100, description="Количество результатов"),
    page: int = Query(1, ge=1, description="Номер страницы"),
):
    """
    Получить список автомобилей KCar

    Возвращает список автомобилей с KCar аукциона с возможностью фильтрации.
    Требует авторизации на сайте KCar.
    """
    try:
        logger.info(
            f"🚗 Запрос автомобилей KCar с параметрами: manufacturer={manufacturer}, model={model}"
        )

        # Формируем параметры запроса
        params = {
            "AUC_TYPE": auction_type or "daily",
            "PAGE_CNT": str(page_size),
            "START_RNUM": str((page - 1) * page_size + 1),
        }

        # Добавляем фильтры если указаны
        if manufacturer:
            params["MNUFTR_CD"] = manufacturer
        if model:
            params["MODEL_CD"] = model
        if year_from:
            params["FORM_YR_ST"] = year_from
        if year_to:
            params["FORM_YR_ED"] = year_to
        if price_from:
            params["AUC_START_PRC_ST"] = price_from
        if price_to:
            params["AUC_START_PRC_ED"] = price_to
        if mileage_from:
            params["MILG_ST"] = mileage_from
        if mileage_to:
            params["MILG_ED"] = mileage_to
        if fuel_type:
            params["FUEL_CD"] = fuel_type
        if transmission:
            params["GBOX_DCD"] = transmission
        if color:
            params["COLOR_CD"] = color
        if location:
            params["AUC_PLC_CD"] = location

        # Получаем данные
        result = kcar_service.get_cars(params)

        if not result.success:
            # Только если это реальная ошибка (не пустой список), показываем fallback
            logger.warning(f"⚠️ KCar API вернул ошибку: {result.message}")
            logger.info("🎭 Переключаюсь на демо данные вместо ошибки")

            # Вместо ошибки возвращаем демо данные
            demo_result = kcar_service.get_test_cars(page_size)
            if demo_result.success:
                # Добавляем информацию о том, что это демо данные
                demo_result.message = f"Произошла ошибка API. Показаны демо данные ({len(demo_result.car_list)} автомобилей)"
                logger.info("✅ Возвращаю демо данные из-за ошибки API")
                return demo_result
            else:
                # Если даже демо данные не работают, тогда ошибка
                logger.error("❌ Не удалось получить даже демо данные")
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Ошибка получения данных KCar",
                        "message": result.message,
                        "suggestion": "Попробуйте позже или используйте /cars/demo для тестовых данных",
                    },
                )

        # Успешный ответ (даже если список пустой)
        if len(result.car_list) == 0:
            logger.info("ℹ️ Возвращаю пустой список - торги завершены или не активны")
        else:
            logger.success(f"✅ Возвращаю {len(result.car_list)} автомобилей KCar")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка в KCar endpoint: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Внутренняя ошибка сервера", "message": str(e)},
        )


@router.get("/cars/test", response_model=KCarResponse)
async def get_kcar_test_cars(
    count: int = Query(10, ge=1, le=100, description="Количество тестовых автомобилей")
):
    """
    Получить тестовые данные автомобилей KCar

    Возвращает сгенерированные тестовые данные для демонстрации.
    Не требует авторизации.
    """
    try:
        logger.info(f"🧪 Запрос {count} тестовых автомобилей KCar")

        result = kcar_service.get_test_cars(count)

        logger.success(f"✅ Возвращаю {len(result.car_list)} тестовых автомобилей KCar")
        return result

    except Exception as e:
        logger.error(f"❌ Ошибка генерации тестовых данных KCar: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Ошибка генерации тестовых данных", "message": str(e)},
        )


@router.get("/cars/demo", response_model=KCarResponse)
async def get_kcar_demo_cars(
    count: int = Query(25, ge=1, le=100, description="Количество демо автомобилей")
):
    """
    Получить демонстрационные данные автомобилей KCar

    Возвращает расширенный набор тестовых данных с различными вариациями.
    """
    try:
        logger.info(f"🎭 Запрос {count} демо автомобилей KCar")

        # Генерируем демо данные с вариациями
        base_result = kcar_service.get_test_cars(count)

        # Добавляем разнообразие в демо данные
        if base_result.success and base_result.car_list:
            demo_cars = []
            for i, car in enumerate(base_result.car_list):
                # Создаем вариации для демо
                demo_car_data = car.model_dump()

                # Изменяем некоторые поля для разнообразия
                if i % 3 == 0:
                    demo_car_data["auction_type_desc"] = "WEEKLY"
                    demo_car_data["auction_status_name"] = "위클리 대기"
                elif i % 3 == 1:
                    demo_car_data["auction_type_desc"] = "DAILY"
                    demo_car_data["auction_status_name"] = "데일리 진행중"
                else:
                    demo_car_data["auction_type_desc"] = "SPECIAL"
                    demo_car_data["auction_status_name"] = "특별 경매"

                # Варьируем локации
                locations = [
                    "서울경매장",
                    "부산경매장",
                    "경기경매장",
                    "대구경매장",
                    "광주경매장",
                ]
                demo_car_data["car_location"] = locations[i % len(locations)]
                demo_car_data["auction_place_name"] = locations[i % len(locations)]

                # Варьируем производителей
                manufacturers = ["현대", "기아", "삼성르노", "쌍용", "한국GM"]
                models = ["소나타", "K5", "QM6", "티볼리", "말리부"]
                demo_car_data["car_name"] = (
                    f"{manufacturers[i % len(manufacturers)]} {models[i % len(models)]} {2018 + (i % 7)} 모델"
                )

                demo_cars.append(KCarCar(**demo_car_data))

            demo_result = KCarResponse(
                car_list=demo_cars,
                total_count=len(demo_cars),
                success=True,
                message=f"Сгенерировано {len(demo_cars)} демо автомобилей KCar",
            )

            logger.success(f"✅ Возвращаю {len(demo_cars)} демо автомобилей KCar")
            return demo_result

        return base_result

    except Exception as e:
        logger.error(f"❌ Ошибка генерации демо данных KCar: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Ошибка генерации демо данных", "message": str(e)},
        )


@router.get("/cars/stats", response_model=KCarStatsResponse)
async def get_kcar_stats(
    auction_type: Optional[str] = Query(
        "weekly", description="Тип аукциона для статистики"
    )
):
    """
    Получить статистику по автомобилям KCar

    Возвращает агрегированную статистику: количество, средние цены, локации.
    """
    try:
        logger.info("📊 Запрос статистики KCar")

        # Получаем данные для расчета статистики
        params = {"AUC_TYPE": auction_type, "PAGE_CNT": "100"}
        cars_result = kcar_service.get_cars(params)

        if not cars_result.success:
            # Если не удалось получить реальные данные, используем тестовые
            logger.warning(
                "⚠️ Не удалось получить реальные данные, используем тестовые для статистики"
            )
            cars_result = kcar_service.get_test_cars(50)

        # Рассчитываем статистику
        stats = kcar_service.parser.calculate_stats(cars_result.car_list)

        logger.success("✅ Статистика KCar рассчитана")
        return stats

    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики KCar: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Ошибка получения статистики", "message": str(e)},
        )


@router.get("/cars/count")
async def get_kcar_count(
    auction_type: Optional[str] = Query("weekly", description="Тип аукциона")
):
    """
    Получить количество автомобилей KCar

    Возвращает общее количество автомобилей в указанном типе аукциона.
    """
    try:
        logger.info(f"📊 Запрос количества автомобилей KCar (тип: {auction_type})")

        params = {"AUC_TYPE": auction_type}
        result = kcar_service.get_car_count(params)

        if result.get("count", 0) == 0:
            logger.info("ℹ️ Торги завершены или не активны, показываю демо значение")
            return {
                "count": 150,  # Демо значение
                "auction_type": auction_type,
                "message": "Торги завершены. Показано демонстрационное значение.",
                "demo": True,
            }

        logger.success(f"✅ Количество автомобилей: {result['count']}")
        return result

    except Exception as e:
        logger.error(f"❌ Ошибка получения количества автомобилей: {e}")
        # Возвращаем демо данные вместо ошибки
        return {
            "count": 150,
            "auction_type": auction_type or "weekly",
            "message": f"Ошибка API: {str(e)}. Показано демонстрационное значение.",
            "demo": True,
        }


@router.get("/cars/{car_id}/detail", response_model=KCarDetailResponse)
async def get_kcar_car_detail(
    car_id: str,
    auction_code: str = Query(..., description="Код аукциона"),
    page_type: str = Query("wCfm", description="Тип страницы"),
):
    """
    Получить детальную информацию об автомобиле KCar

    Возвращает подробную информацию о конкретном автомобиле включая:
    - Полные технические характеристики
    - Детальную информацию об аукционе
    - Список всех изображений
    - Информацию о состоянии и оценке
    - Сведения о владельце (анонимизированные)
    - Результаты технического осмотра

    Параметры:
    - car_id: Идентификатор автомобиля (например: CA20324182)
    - auction_code: Код аукциона (например: AC20250604)
    - page_type: Тип страницы (по умолчанию: wCfm)
    """
    try:
        logger.info(f"🔍 Запрос детальной информации для автомобиля {car_id}")

        # Валидация параметров
        if not car_id:
            raise HTTPException(
                status_code=400, detail="car_id является обязательным параметром"
            )

        if not auction_code:
            raise HTTPException(
                status_code=400, detail="auction_code является обязательным параметром"
            )

        # Получаем детальную информацию
        result = kcar_service.get_car_detail(car_id, auction_code, page_type)

        if not result.success:
            logger.error(f"❌ Ошибка получения детальной информации: {result.message}")
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "Не удалось получить детальную информацию об автомобиле",
                    "message": result.message,
                    "car_id": car_id,
                    "auction_code": auction_code,
                },
            )

        logger.success(f"✅ Детальная информация получена для автомобиля {car_id}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка в endpoint детальной информации: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Внутренняя ошибка сервера",
                "message": str(e),
                "car_id": car_id,
            },
        )


@router.get("/info")
async def get_kcar_info():
    """
    Получить информацию о KCar API

    Возвращает общую информацию о сервисе и доступных параметрах.
    """
    return {
        "service": "KCar Auction Parser",
        "version": "1.0.0",
        "description": "API для получения данных автомобилей с KCar аукциона",
        "base_url": "https://www.kcarauction.com",
        "features": [
            "Получение списка автомобилей",
            "Фильтрация по параметрам",
            "Статистика и аналитика",
            "Тестовые и демо данные",
        ],
        "parameters": {
            "auction_types": ["daily", "weekly", "special"],
            "fuel_types": ["G", "D", "H", "E"],  # Бензин, Дизель, Гибрид, Электро
            "transmissions": ["A", "M"],  # Автомат, Механика
            "locations": ["서울경매장", "부산경매장", "경기경매장", "대구경매장"],
        },
        "endpoints": [
            {"path": "/cars", "method": "GET", "description": "Список автомобилей"},
            {"path": "/cars/test", "method": "GET", "description": "Тестовые данные"},
            {"path": "/cars/demo", "method": "GET", "description": "Демо данные"},
            {"path": "/cars/stats", "method": "GET", "description": "Статистика"},
            {"path": "/cars/count", "method": "GET", "description": "Количество"},
            {
                "path": "/cars/{car_id}/detail",
                "method": "GET",
                "description": "Детальная информация",
            },
            {"path": "/info", "method": "GET", "description": "Информация о API"},
        ],
        "auth_required": {
            "/cars": True,
            "/cars/test": False,
            "/cars/demo": False,
            "/cars/stats": True,
            "/cars/count": True,
            "/cars/{car_id}/detail": True,
        },
    }
