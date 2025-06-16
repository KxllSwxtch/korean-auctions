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


@router.get("/car/{car_id}", response_model=GlovisCarDetailResponse)
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

        # Получаем детальную информацию
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


@router.post("/car/by-url", response_model=GlovisCarDetailResponse)
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


@router.post("/cars/multiple", response_model=List[GlovisCarDetailResponse])
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


@router.get("/car/{car_id}/validate")
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
    Проверка здоровья сервиса детальных страниц

    **Возвращает:**
    Статус работы сервиса и его компонентов
    """
    logger.info("🏥 Проверка здоровья сервиса детальных страниц")

    try:
        # Проверяем доступность основного сервиса Glovis
        glovis_health = await detail_service.glovis_service.health_check()

        # Базовая проверка парсера
        parser_health = True
        try:
            # Проверяем, что парсер может быть инициализирован
            test_parser = detail_service.parser
            if not hasattr(test_parser, "parse"):
                parser_health = False
        except Exception:
            parser_health = False

        overall_health = glovis_health.get("healthy", False) and parser_health

        return {
            "healthy": overall_health,
            "service": "glovis_detail",
            "components": {
                "glovis_service": glovis_health,
                "parser": {
                    "healthy": parser_health,
                    "status": "ok" if parser_health else "error",
                },
            },
            "message": (
                "Сервис работает корректно" if overall_health else "Обнаружены проблемы"
            ),
        }

    except Exception as e:
        logger.error(f"❌ Ошибка проверки здоровья: {str(e)}")
        return {
            "healthy": False,
            "service": "glovis_detail",
            "message": f"Ошибка проверки: {str(e)}",
        }
