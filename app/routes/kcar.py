from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional, Dict, Any
from loguru import logger

from app.models.kcar import (
    KCarResponse,
    KCarCar,
    KCarStatsResponse,
    KCarDetailResponse,
    KCarModelsResponse,
    KCarGenerationsResponse,
    KCarSearchResponse,
    KCarSearchFilters,
    KCAR_MANUFACTURERS,
)
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
        # В KCar START_RNUM = номер страницы, а не номер записи!
        params = {
            "AUC_TYPE": auction_type or "weekly",
            "PAGE_CNT": page_size,
            "page": page,  # Передаем номер страницы отдельно
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


@router.get("/cars/search/by-number")
async def search_car_by_number(
    car_number: str = Query(..., description="Номер автомобиля"),
    auction_code: str = Query(None, description="Код аукциона (опционально)"),
):
    """
    Поиск car_id по номеру автомобиля

    Возвращает car_id для автомобиля по его номеру.
    Полезно когда фронтенд знает только номер автомобиля (например: "20머3749"),
    но для получения детальной информации нужен car_id (например: "CA20324182").

    Параметры:
    - car_number: Номер автомобиля (например: "20머3749")
    - auction_code: Код аукциона (опционально, для более точного поиска)

    Пример использования:
    1. Поиск car_id: GET /cars/search/by-number?car_number=20머3749
    2. Получение детальной информации: GET /cars/{car_id}/detail?auction_code=AC20250604
    """
    try:
        logger.info(f"🔍 Поиск car_id по номеру автомобиля: {car_number}")

        # Валидация параметров
        if not car_number:
            raise HTTPException(
                status_code=400, detail="car_number является обязательным параметром"
            )

        # Поиск автомобиля
        search_result = kcar_service.find_car_id_by_number(car_number, auction_code)

        if not search_result["success"]:
            logger.warning(f"⚠️ Автомобиль с номером {car_number} не найден")
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "Автомобиль не найден",
                    "message": search_result["message"],
                    "car_number": car_number,
                    "searched_count": search_result.get("searched_count", 0),
                },
            )

        logger.success(
            f"✅ Найден car_id {search_result['car_id']} для номера {car_number}"
        )

        return {
            "success": True,
            "car_number": car_number,
            "car_id": search_result["car_id"],
            "found_car_number": search_result["car_number"],
            "match_type": search_result["match_type"],
            "confidence": search_result["confidence"],
            "message": search_result["message"],
            "all_matches": search_result.get("all_matches", []),
            "detail_url": f"/api/v1/kcar/cars/{search_result['car_id']}/detail",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка поиска автомобиля по номеру: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Внутренняя ошибка сервера",
                "message": str(e),
                "car_number": car_number,
            },
        )


@router.get("/info")
async def get_kcar_info():
    """
    Получить информацию о KCar API

    Возвращает базовую информацию о работе с KCar API.
    """
    try:
        return {
            "name": "KCar Auction API",
            "version": "1.0.0",
            "description": "API для работы с корейским автомобильным аукционом KCar",
            "features": [
                "Получение списка автомобилей",
                "Детальная информация об автомобилях",
                "Поиск по номеру автомобиля",
                "Статистика аукционов",
                "Тестовые данные",
            ],
            "supported_auctions": ["WEEKLY"],
            "authentication": "Required (username/password)",
            "base_url": "https://www.kcarauction.com",
            "status": "Active",
            "last_updated": "2025-01-24",
        }
    except Exception as e:
        logger.error(f"❌ Ошибка получения информации о KCar API: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Ошибка получения информации", "message": str(e)},
        )


# =============================================================================
# ЭНДПОИНТЫ СИСТЕМЫ ФИЛЬТРАЦИИ
# =============================================================================


@router.get("/manufacturers")
async def get_manufacturers():
    """
    Получить список производителей автомобилей

    Возвращает статический список всех поддерживаемых производителей.
    """
    try:
        logger.info("📋 Запрос списка производителей KCar")

        manufacturers = kcar_service.get_manufacturers()

        logger.success(f"✅ Возвращено {len(manufacturers)} производителей")
        return {
            "manufacturers": manufacturers,
            "total_count": len(manufacturers),
            "success": True,
            "message": f"Получено {len(manufacturers)} производителей",
        }

    except Exception as e:
        logger.error(f"❌ Ошибка получения списка производителей: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Ошибка получения производителей", "message": str(e)},
        )


@router.get("/models/{manufacturer_code}", response_model=KCarModelsResponse)
async def get_models(
    manufacturer_code: str,
    input_car_code: str = Query("001", description="Код типа автомобиля"),
):
    """
    Получить список моделей для производителя

    Возвращает все доступные модели для указанного производителя.
    """
    try:
        logger.info(f"📋 Запрос моделей для производителя {manufacturer_code}")

        result = kcar_service.get_models(manufacturer_code, input_car_code)

        if not result.success:
            logger.warning(
                f"⚠️ Не удалось получить модели для производителя {manufacturer_code}: {result.message}"
            )
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Ошибка получения моделей",
                    "message": result.message,
                    "manufacturer_code": manufacturer_code,
                },
            )

        logger.success(
            f"✅ Возвращено {len(result.models)} моделей для производителя {manufacturer_code}"
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка в эндпоинте получения моделей: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Внутренняя ошибка сервера", "message": str(e)},
        )


@router.get(
    "/generations/{manufacturer_code}/{model_group_code}",
    response_model=KCarGenerationsResponse,
)
async def get_generations(
    manufacturer_code: str,
    model_group_code: str,
    input_car_code: str = Query("001", description="Код типа автомобиля"),
):
    """
    Получить список поколений для модели

    Возвращает все доступные поколения для указанной модели производителя.
    """
    try:
        logger.info(
            f"📋 Запрос поколений для модели {model_group_code} производителя {manufacturer_code}"
        )

        result = kcar_service.get_generations(
            manufacturer_code, model_group_code, input_car_code
        )

        if not result.success:
            logger.warning(f"⚠️ Не удалось получить поколения: {result.message}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Ошибка получения поколений",
                    "message": result.message,
                    "manufacturer_code": manufacturer_code,
                    "model_group_code": model_group_code,
                },
            )

        logger.success(
            f"✅ Возвращено {len(result.generations)} поколений для модели {model_group_code}"
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка в эндпоинте получения поколений: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Внутренняя ошибка сервера", "message": str(e)},
        )


@router.post("/search", response_model=KCarSearchResponse)
async def search_cars(filters: KCarSearchFilters):
    """
    Расширенный поиск автомобилей с фильтрами

    Позволяет искать автомобили с множественными фильтрами:
    - Производитель, модель, поколение
    - Год выпуска, цена, пробег
    - Тип топлива, коробка передач, цвет
    - Местоположение аукциона
    """
    try:
        logger.info(f"🔍 Запрос расширенного поиска автомобилей KCar")
        logger.debug(f"🔍 Параметры поиска: {filters.model_dump()}")

        result = kcar_service.search_cars(filters)

        if not result.success:
            logger.warning(f"⚠️ Ошибка расширенного поиска: {result.message}")
            # Для поиска возвращаем ошибку, но не критичную
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Ошибка поиска автомобилей",
                    "message": result.message,
                    "filters": filters.model_dump(),
                },
            )

        # Успешный результат (может быть пустым)
        if len(result.cars) == 0:
            logger.info("ℹ️ Поиск не вернул результатов")
        else:
            logger.success(f"✅ Найдено {len(result.cars)} автомобилей")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка в эндпоинте расширенного поиска: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Внутренняя ошибка сервера", "message": str(e)},
        )


@router.get("/search/filters/info")
async def get_search_filters_info():
    """
    Получить информацию о доступных фильтрах поиска

    Возвращает справочную информацию о всех возможных фильтрах.
    """
    try:
        logger.info("📋 Запрос информации о фильтрах поиска")

        # Получаем схему модели фильтров
        schema = KCarSearchFilters.model_json_schema()

        # Дополнительная информация
        additional_info = {
            "manufacturer_codes": {
                "001": "현대 (Hyundai)",
                "002": "기아 (Kia)",
                "003": "삼성르노 (Samsung Renault)",
                "004": "대우GM (Daewoo GM)",
                "005": "쌍용 (SsangYong)",
                "006": "한국GM (GM Korea)",
                "007": "수입 (Import)",
                "008": "기타 (Others)",
            },
            "auction_types": ["weekly"],
            "lane_types": ["A", "B"],
            "common_fuel_types": ["가솔린", "디젤", "LPG", "하이브리드", "전기"],
            "common_transmissions": ["오토", "수동", "CVT", "DCT"],
            "tips": [
                "Используйте manufacturer_code для получения списка моделей",
                "Получите поколения через manufacturer_code + model_group_code",
                "Фильтры можно комбинировать для точного поиска",
                "Пагинация поддерживается через page и page_size",
                "START_RNUM в KCar = номер страницы, не записи",
            ],
        }

        return {
            "schema": schema,
            "additional_info": additional_info,
            "success": True,
            "message": "Информация о фильтрах получена успешно",
        }

    except Exception as e:
        logger.error(f"❌ Ошибка получения информации о фильтрах: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Ошибка получения информации о фильтрах",
                "message": str(e),
            },
        )
