"""
API endpoints для работы с детальными страницами автомобилей Glovis
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, List
from urllib.parse import unquote

from app.services.glovis_detail_service import GlovisDetailService
from app.models.glovis_detail import GlovisCarDetailResponse, GlovisCarDetailError
from app.core.logging import get_logger

logger = get_logger("glovis_detail_routes")

router = APIRouter()
detail_service = GlovisDetailService()


@router.get("/detail/{car_id}", response_model=GlovisCarDetailResponse)
async def get_car_detail(
    car_id: str,
    auction_number: str = Query("747", description="Номер аукциона"),
    acc: str = Query("30", description="Параметр acc"),
    rc: str = Query("1100", description="Параметр rc"),
):
    """
    Получение детальной информации об автомобиле по ID

    **Параметры:**
    - **car_id**: ID автомобиля (параметр gn из URL)
    - **auction_number**: Номер аукциона (по умолчанию 747)
    - **acc**: Дополнительный параметр (по умолчанию 30)
    - **rc**: Дополнительный параметр (по умолчанию 1100)

    **Автоматическое определение параметров:**
    Система автоматически ищет правильные параметры (rc, acc, atn) для автомобиля
    в списке автомобилей. Если параметры найдены, они используются вместо дефолтных.

    **Возвращает:**
    Детальную информацию об автомобиле включая:
    - Базовую информацию (название, производитель, модель, год, пробег)
    - Цены (новый автомобиль, оценочная стоимость)
    - Детальные характеристики (топливо, объем двигателя, цвет)
    - Результаты технической проверки
    - Список опций
    - Изображения автомобиля
    """
    logger.info(f"🔍 API запрос детальной информации об автомобиле: {car_id}")

    try:
        # Декодируем car_id, если он закодирован
        decoded_car_id = unquote(car_id)

        # Получаем детальную информацию (с автоматическим поиском параметров)
        result = await detail_service.get_car_detail(
            car_id=decoded_car_id, auction_number=auction_number, acc=acc, rc=rc
        )

        if not result.success:
            logger.error(f"❌ Ошибка получения данных: {result.message}")
            raise HTTPException(status_code=404, detail=result.message)

        logger.info(
            f"✅ Детальная информация успешно получена: {result.data.basic_info.name}"
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.post("/detail/by-url", response_model=GlovisCarDetailResponse)
async def get_car_detail_by_url(
    detail_url: str = Body(..., description="Полный URL детальной страницы автомобиля")
):
    """
    Получение детальной информации об автомобиле по URL

    **Параметры:**
    - **detail_url**: Полный URL детальной страницы автомобиля

    **Пример URL:**
    ```
    https://auction.autobell.co.kr/auction/exhibitView.do?acc=30&gn=v2DlTk1F5%2BMckBC3dGOf2g%3D%3D&rc=1100&atn=747
    ```

    **Возвращает:**
    Детальную информацию об автомобиле
    """
    logger.info(f"🔍 API запрос детальной информации по URL: {detail_url}")

    try:
        # Получаем детальную информацию
        result = await detail_service.get_car_detail_by_url(detail_url)

        if not result.success:
            logger.error(f"❌ Ошибка получения данных: {result.message}")
            raise HTTPException(status_code=404, detail=result.message)

        logger.info(
            f"✅ Детальная информация успешно получена: {result.data.basic_info.name}"
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.post("/detail/multiple", response_model=List[GlovisCarDetailResponse])
async def get_multiple_car_details(
    car_ids: List[str] = Body(..., description="Список ID автомобилей"),
    auction_number: str = Body("747", description="Номер аукциона"),
    max_concurrent: int = Body(
        5, description="Максимальное количество одновременных запросов"
    ),
):
    """
    Получение детальной информации о нескольких автомобилях

    **Параметры:**
    - **car_ids**: Список ID автомобилей для получения информации
    - **auction_number**: Номер аукциона (по умолчанию 747)
    - **max_concurrent**: Максимальное количество одновременных запросов (по умолчанию 5)

    **Возвращает:**
    Список детальной информации о всех запрошенных автомобилях

    **Примечание:**
    Если для некоторых автомобилей не удастся получить данные,
    в списке будут объекты с success=False и описанием ошибки
    """
    logger.info(f"🔍 API запрос детальной информации о {len(car_ids)} автомобилях")

    try:
        if not car_ids:
            raise HTTPException(
                status_code=400, detail="Список ID автомобилей не может быть пустым"
            )

        if len(car_ids) > 20:
            raise HTTPException(
                status_code=400,
                detail="Максимальное количество автомобилей за один запрос: 20",
            )

        if max_concurrent > 10:
            max_concurrent = 10  # Ограничиваем для предотвращения перегрузки

        # Получаем детальную информацию
        results = await detail_service.get_multiple_car_details(
            car_ids=car_ids,
            auction_number=auction_number,
            max_concurrent=max_concurrent,
        )

        successful_count = sum(1 for r in results if r.success)
        logger.info(
            f"✅ Успешно получено {successful_count} из {len(car_ids)} автомобилей"
        )

        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/detail/{car_id}/validate")
async def validate_car_detail(
    car_id: str,
    auction_number: str = Query("747", description="Номер аукциона"),
    acc: str = Query("30", description="Параметр acc"),
    rc: str = Query("1100", description="Параметр rc"),
):
    """
    Получение и валидация детальной информации об автомобиле

    **Параметры:**
    - **car_id**: ID автомобиля
    - **auction_number**: Номер аукциона
    - **acc**: Дополнительный параметр
    - **rc**: Дополнительный параметр

    **Возвращает:**
    Детальную информацию об автомобиле с результатами валидации:
    - **car_detail**: Полная информация об автомобиле
    - **validation**: Результаты валидации данных
    """
    logger.info(f"🔍 API запрос валидации данных автомобиля: {car_id}")

    try:
        # Декодируем car_id, если он закодирован
        decoded_car_id = unquote(car_id)

        # Получаем детальную информацию
        result = await detail_service.get_car_detail(
            car_id=decoded_car_id, auction_number=auction_number, acc=acc, rc=rc
        )

        if not result.success:
            logger.error(f"❌ Ошибка получения данных: {result.message}")
            raise HTTPException(status_code=404, detail=result.message)

        # Валидируем полученные данные
        validation_result = await detail_service.validate_car_detail(result.data)

        logger.info(
            f"✅ Валидация завершена: {validation_result['data_quality']} качество"
        )

        return {"car_detail": result.data, "validation": validation_result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/test/parser")
async def test_parser():
    """
    Тестовый endpoint для проверки работы парсера

    Использует пример данных из приложенного файла glovis-car-page-example.html
    """
    logger.info("🧪 Тестирование парсера детальной страницы")

    try:
        # Используем тестовый URL из примера
        test_url = "https://auction.autobell.co.kr/auction/exhibitView.do?acc=30&gn=v2DlTk1F5%2BMckBC3dGOf2g%3D%3D&rc=1100&atn=747"

        result = await detail_service.get_car_detail_by_url(test_url)

        if not result.success:
            logger.error(f"❌ Ошибка тестирования: {result.message}")
            return {"success": False, "message": result.message, "test_url": test_url}

        # Валидируем полученные данные
        validation_result = await detail_service.validate_car_detail(result.data)

        logger.info(f"✅ Тестирование завершено успешно: {result.data.basic_info.name}")

        return {
            "success": True,
            "message": "Парсер работает корректно",
            "test_url": test_url,
            "car_name": result.data.basic_info.name,
            "validation": validation_result,
            "data_preview": {
                "manufacturer": result.data.basic_info.manufacturer,
                "model": result.data.basic_info.model,
                "year": result.data.basic_info.year,
                "mileage": result.data.basic_info.mileage,
                "fuel_type": result.data.basic_info.fuel_type,
                "images_count": len(result.data.images),
                "has_pricing": result.data.pricing is not None,
                "has_specs": result.data.detailed_specs is not None,
                "has_performance_check": result.data.performance_check is not None,
            },
        }

    except Exception as e:
        logger.error(f"❌ Ошибка тестирования: {str(e)}")
        return {
            "success": False,
            "message": f"Ошибка тестирования: {str(e)}",
            "test_url": test_url,
        }


@router.get("/health")
async def health_check():
    """
    Проверка состояния сервиса детальных страниц Glovis
    """
    logger.info("🏥 Проверка состояния сервиса")

    try:
        # Проверяем доступность базового URL
        health_status = {
            "service": "Glovis Detail Service",
            "status": "healthy",
            "base_url": detail_service.base_url,
            "cache_size": len(detail_service._car_params_cache),
            "features": {
                "auto_param_detection": True,
                "parameter_caching": True,
                "batch_processing": True,
                "data_validation": True,
            },
        }

        return {"success": True, "data": health_status}

    except Exception as e:
        logger.error(f"❌ Ошибка проверки состояния: {str(e)}")
        return {"success": False, "error": str(e)}


@router.post("/cache/clear")
async def clear_cache():
    """
    Очистка кэша параметров автомобилей

    Полезно при обновлении данных аукциона или для освобождения памяти.
    """
    logger.info("🧹 Очистка кэша параметров автомобилей")

    try:
        cache_size_before = len(detail_service._car_params_cache)
        detail_service._car_params_cache.clear()

        logger.info(f"✅ Кэш очищен: удалено {cache_size_before} записей")

        return {
            "success": True,
            "message": f"Кэш очищен: удалено {cache_size_before} записей",
            "cache_size_before": cache_size_before,
            "cache_size_after": 0,
        }

    except Exception as e:
        logger.error(f"❌ Ошибка очистки кэша: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка очистки кэша: {str(e)}")


@router.get("/cache/stats")
async def get_cache_stats():
    """
    Получение статистики кэша параметров автомобилей
    """
    logger.info("📊 Получение статистики кэша")

    try:
        cache_stats = {
            "cache_size": len(detail_service._car_params_cache),
            "cached_cars": list(detail_service._car_params_cache.keys())[
                :10
            ],  # Первые 10
            "total_cached_cars": len(detail_service._car_params_cache),
        }

        return {"success": True, "data": cache_stats}

    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики кэша: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Ошибка получения статистики: {str(e)}"
        )


@router.get("/detail/{car_id}/with-params", response_model=GlovisCarDetailResponse)
async def get_car_detail_with_params(
    car_id: str,
    rc: str = Query(..., description="Код региона (обязательный)"),
    acc: str = Query("30", description="Параметр acc"),
    atn: str = Query("747", description="Номер аукциона"),
):
    """
    Получение детальной информации об автомобиле с явным указанием параметров

    **Параметры:**
    - **car_id**: ID автомобиля (параметр gn из URL)
    - **rc**: Код региона (ОБЯЗАТЕЛЬНЫЙ) - 1100=분당, 2100=시화, 3100=양산, 5100=인천
    - **acc**: Дополнительный параметр (по умолчанию 30)
    - **atn**: Номер аукциона (по умолчанию 747)

    **Пример использования:**
    ```
    GET /api/v1/glovis/car/JkSvM%2Fvdt6NccTdCJooXww%3D%3D/with-params?rc=3100
    ```

    **Возвращает:**
    Детальную информацию об автомобиле
    """
    logger.info(f"🔍 API запрос с явными параметрами: car_id={car_id}, rc={rc}")

    try:
        # Декодируем car_id, если он закодирован
        decoded_car_id = unquote(car_id)

        # Получаем детальную информацию с явными параметрами
        result = await detail_service.get_car_detail_direct(
            car_id=decoded_car_id, auction_number=atn, acc=acc, rc=rc
        )

        if not result.success:
            logger.error(f"❌ Ошибка получения данных: {result.message}")
            raise HTTPException(status_code=404, detail=result.message)

        logger.info(
            f"✅ Детальная информация успешно получена: {result.data.basic_info.name}"
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/detail/debug/{car_id}")
async def debug_car_detail(
    car_id: str,
    rc: str = Query("3100", description="Код региона"),
    acc: str = Query("30", description="Параметр acc"),
    atn: str = Query("747", description="Номер аукциона"),
):
    """
    Отладочный endpoint для диагностики проблем с получением детальной информации
    """
    logger.info(f"🐛 DEBUG: car_id={car_id}, rc={rc}, acc={acc}, atn={atn}")

    try:
        from urllib.parse import unquote

        decoded_car_id = unquote(car_id)

        # Формируем URL напрямую
        url = f"https://auction.autobell.co.kr/auction/exhibitView.do?acc={acc}&gn={car_id}&rc={rc}&atn={atn}"

        logger.info(f"🔗 Сформированный URL: {url}")

        # Проверяем сессию
        session_check = await detail_service.glovis_service.health_check()

        return {
            "debug_info": {
                "original_car_id": car_id,
                "decoded_car_id": decoded_car_id,
                "parameters": {"rc": rc, "acc": acc, "atn": atn},
                "generated_url": url,
                "session_status": session_check,
            },
            "message": "Отладочная информация собрана",
        }

    except Exception as e:
        logger.error(f"❌ Ошибка в отладке: {str(e)}")
        return {"error": str(e), "debug_info": None}


@router.get("/car-detail")
async def get_car_detail_simple(
    gn: str = Query(..., description="ID автомобиля (gn)"),
    rc: str = Query(..., description="Код региона (rc)"),
    acc: str = Query("30", description="Параметр acc"),
    atn: str = Query("747", description="Номер аукциона"),
):
    """
    Простой endpoint для получения детальной информации об автомобиле

    **Параметры:**
    - **gn**: ID автомобиля (ОБЯЗАТЕЛЬНЫЙ)
    - **rc**: Код региона (ОБЯЗАТЕЛЬНЫЙ) - 1100=분당, 2100=시화, 3100=양산, 5100=인천
    - **acc**: Параметр acc (по умолчанию 30)
    - **atn**: Номер аукциона (по умолчанию 747)

    **Пример:**
    ```
    GET /api/v1/glovis/car-detail?gn=JkSvM%2Fvdt6NccTdCJooXww%3D%3D&rc=3100
    ```
    """
    # Получаем дополнительные параметры
    rc = request.args.get("rc", "3100")
    acc = request.args.get("acc")
    atn = request.args.get("atn")

    # Проверяем наличие важных параметров
    if not acc or not atn:
        logger.warning(
            f"⚠️ Отсутствуют параметры acc или atn. acc={acc}, atn={atn}. Результат может быть пустым!"
        )

    logger.info(
        f"🔍 Простой запрос детальной информации: gn={gn}, rc={rc}, acc={acc}, atn={atn}"
    )

    try:
        # Декодируем gn, если он закодирован
        decoded_gn = unquote(gn)

        # Получаем детальную информацию напрямую
        result = await detail_service.get_car_detail_direct(
            car_id=decoded_gn, auction_number=atn, acc=acc, rc=rc
        )

        if not result.success:
            logger.error(f"❌ Ошибка получения данных: {result.message}")
            raise HTTPException(status_code=404, detail=result.message)

        logger.info(
            f"✅ Детальная информация успешно получена: {result.data.basic_info.name}"
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )
