from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query, HTTPException, Depends, Path
from fastapi.responses import JSONResponse
import time

from app.models.lotte import (
    LotteResponse,
    LotteCar,
    LotteError,
    LotteAuctionDate,
    LotteCarResponse,
    LotteCarHistoryResponse,
    LotteCountResponse,
)
from app.services.lotte_service import LotteService
from app.core.logging import logger
from app.core.single_flight import SingleFlight

router = APIRouter(prefix="/api/v1/lotte", tags=["Lotte Auction"])
_lotte_flight = SingleFlight()

# Глобальный экземпляр сервиса
_lotte_service = None


def get_lotte_service() -> LotteService:
    """Dependency для получения сервиса Lotte"""
    global _lotte_service
    if _lotte_service is None:
        _lotte_service = LotteService()
    return _lotte_service


@router.get("/auction-date", response_model=LotteAuctionDate)
async def get_auction_date(service: LotteService = Depends(get_lotte_service)):
    """
    Получение даты ближайшего аукциона Lotte

    Возвращает:
    - Дату аукциона
    - Информацию о том, сегодня ли аукцион
    - Является ли дата будущей
    """
    try:
        auction_date = await service.get_auction_date()

        if not auction_date:
            raise HTTPException(
                status_code=404, detail="Не удалось получить дату аукциона"
            )

        return auction_date

    except Exception as e:
        logger.error(f"Ошибка при получении даты аукциона Lotte: {e}")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/cars", response_model=LotteResponse)
async def get_cars(
    limit: int = Query(
        20, ge=1, le=100, description="Количество автомобилей на странице"
    ),
    offset: int = Query(0, ge=0, description="Смещение для пагинации"),
    service: LotteService = Depends(get_lotte_service),
):
    """
    Основной endpoint для получения автомобилей с аукциона Lotte

    Проверяет дату аукциона:
    - Если аукцион сегодня - возвращает список автомобилей
    - Если аукцион не сегодня - возвращает информацию о ближайшей дате

    Параметры:
    - limit: количество автомобилей на странице (1-100)
    - offset: смещение для пагинации
    """
    try:
        logger.info(f"Запрос автомобилей Lotte: limit={limit}, offset={offset}")

        # Deduplicate concurrent identical requests via SingleFlight
        flight_key = f"lotte:cars:{limit}:{offset}"
        response = await _lotte_flight.do(
            flight_key,
            lambda: service.get_cars_response_with_date_check(limit=limit, offset=offset),
        )

        if not response.success:
            return JSONResponse(
                status_code=200,  # Не ошибка, просто нет данных
                content=response.model_dump(),
            )

        logger.info(f"Успешно получено {len(response.cars)} автомобилей Lotte")
        return response

    except Exception as e:
        error_msg = str(e)
        is_auth_error = "аутентифицироваться" in error_msg or "Authentication" in error_msg or "Session" in error_msg

        if is_auth_error:
            logger.warning(f"Lotte auth unavailable: {e}")
            error_response = LotteError(
                error_code="AUTH_UNAVAILABLE",
                message="Lotte auction service temporarily unavailable, please retry",
                timestamp=datetime.now().isoformat(),
            )
            return JSONResponse(
                status_code=503,
                content=error_response.model_dump(),
                headers={"Retry-After": "60"},
            )

        logger.error(f"Ошибка при получении автомобилей Lotte: {e}")
        error_response = LotteError(
            error_code="INTERNAL_ERROR",
            message=f"Внутренняя ошибка сервера: {str(e)}",
            timestamp=datetime.now().isoformat(),
        )
        return JSONResponse(status_code=500, content=error_response.model_dump())


@router.get("/cars/test", response_model=LotteResponse)
async def get_test_cars(service: LotteService = Depends(get_lotte_service)):
    """
    Тестовый endpoint для получения данных из локальных HTML файлов
    Использует примеры HTML файлов для демонстрации работы парсера
    """
    try:
        logger.info("Запрос тестовых данных Lotte")

        # Читаем тестовые файлы
        test_cars = []
        test_date = None

        # Пытаемся прочитать файлы с примерами
        try:
            with open("lotte-home-example.html", "r", encoding="utf-8") as f:
                home_content = f.read()
                test_date = service.parser.parse_auction_date(home_content)
        except FileNotFoundError:
            logger.warning("Файл lotte-home-example.html не найден")

        try:
            with open("lotte-cars-example.html", "r", encoding="utf-8") as f:
                cars_content = f.read()
                cars_data = service.parser.parse_cars_list(cars_content)

                # Берем первые 10 автомобилей для теста
                for car_data in cars_data[:10]:
                    try:
                        # Пытаемся прочитать детальную страницу
                        with open(
                            "lotte-car-example.html", "r", encoding="utf-8"
                        ) as detail_f:
                            detail_content = detail_f.read()
                            detailed_car = service.parser.parse_car_details(
                                detail_content, car_data
                            )
                            if detailed_car:
                                test_cars.append(detailed_car)
                    except:
                        # Если детальная страница не найдена, создаем базовый объект
                        from app.models.lotte import (
                            LotteCar,
                            FuelType,
                            TransmissionType,
                            GradeType,
                        )

                        brand, model = service.parser._parse_brand_model(
                            car_data["name"]
                        )
                        test_car = LotteCar(
                            id=car_data["id"],
                            auction_number=car_data["auction_number"],
                            lane=car_data["lane"],
                            license_plate=car_data["license_plate"],
                            name=car_data["name"],
                            model=model,
                            brand=brand,
                            year=car_data["year"],
                            mileage=car_data["mileage"],
                            color=car_data["color"],
                            grade=car_data["grade"],
                            starting_price=car_data["starting_price"],
                            searchMngDivCd=car_data.get("searchMngDivCd"),
                            searchMngNo=car_data.get("searchMngNo"),
                            searchExhiRegiSeq=car_data.get("searchExhiRegiSeq"),
                        )
                        test_cars.append(test_car)

        except FileNotFoundError:
            logger.warning("Файл lotte-cars-example.html не найден")

        response = LotteResponse(
            success=True,
            message=f"Тестовые данные Lotte: {len(test_cars)} автомобилей",
            auction_date_info=test_date,
            cars=test_cars,
            total_count=len(test_cars),
            page=1,
            per_page=len(test_cars),
            total_pages=1,
            timestamp=datetime.now().isoformat(),
        )

        logger.info(f"Возвращено {len(test_cars)} тестовых автомобилей Lotte")
        return response

    except Exception as e:
        logger.error(f"Ошибка при получении тестовых данных Lotte: {e}")
        error_response = LotteError(
            error_code="TEST_ERROR",
            message=f"Ошибка при получении тестовых данных: {str(e)}",
            timestamp=datetime.now().isoformat(),
        )
        return JSONResponse(status_code=500, content=error_response.model_dump())


@router.get("/total-count", response_model=LotteCountResponse)
async def get_total_count(service: LotteService = Depends(get_lotte_service)):
    """
    Get total count of cars available at Lotte auction
    
    Returns:
    - Total number of cars
    - Success status
    - Response message with auction date
    """
    try:
        logger.info("Fetching Lotte auction total car count")
        count_response = await service.fetch_total_count()
        
        if not count_response.success:
            logger.warning(f"Failed to fetch Lotte count: {count_response.message}")
            
        return count_response
        
    except Exception as e:
        logger.error(f"Error fetching Lotte total count: {e}")
        return LotteCountResponse(
            success=False,
            total_count=0,
            message=f"Ошибка при получении количества: {str(e)}",
            timestamp=datetime.now()
        )


@router.get("/cars/upcoming", response_model=LotteResponse)
async def get_upcoming_cars(
    limit: int = Query(
        20, ge=1, le=100, description="Количество автомобилей на странице"
    ),
    offset: int = Query(0, ge=0, description="Смещение для пагинации"),
    service: LotteService = Depends(get_lotte_service),
):
    """
    Получение автомобилей предстоящего аукциона (независимо от даты)

    Этот endpoint возвращает автомобили из списка предстоящего аукциона,
    не проверяя, является ли дата аукциона сегодняшней.
    Полезно для предварительного просмотра лотов.

    Параметры:
    - limit: количество автомобилей на странице (1-100)
    - offset: смещение для пагинации
    """
    try:
        start_time = time.time()
        logger.info(
            f"Запрос автомобилей предстоящего аукциона Lotte: limit={limit}, offset={offset}"
        )

        # Service methods handle auth internally via _ensure_session()
        # No pre-auth needed — the coordinator prevents race conditions

        # Получаем дату аукциона для информации
        auction_date = await service.get_auction_date()

        # Получаем автомобили без проверки даты
        cars = await service.get_cars(limit, offset)

        # Получаем общее количество для правильной пагинации
        total_count = await service.get_total_cars_count()

        response = LotteResponse(
            success=True,
            message=f"Автомобили предстоящего аукциона: {len(cars)} на странице {(offset // limit) + 1} из {total_count} общих",
            auction_date_info=auction_date,
            cars=cars,
            total_count=total_count,
            page=(offset // limit) + 1,
            per_page=limit,
            total_pages=(total_count + limit - 1) // limit if total_count > 0 else 1,
            timestamp=datetime.now().isoformat(),
            request_duration=time.time() - start_time,
        )

        logger.info(f"Возвращено {len(cars)} автомобилей предстоящего аукциона Lotte")
        return response

    except Exception as e:
        error_msg = str(e)
        is_auth_error = "аутентифицироваться" in error_msg or "Authentication" in error_msg or "Session" in error_msg

        if is_auth_error:
            logger.warning(f"Lotte auth unavailable: {e}")
            error_response = LotteError(
                error_code="AUTH_UNAVAILABLE",
                message="Lotte auction service temporarily unavailable, please retry",
                timestamp=datetime.now().isoformat(),
            )
            return JSONResponse(
                status_code=503,
                content=error_response.model_dump(),
                headers={"Retry-After": "60"},
            )

        logger.error(
            f"Ошибка при получении автомобилей предстоящего аукциона Lotte: {e}"
        )
        error_response = LotteError(
            error_code="INTERNAL_ERROR",
            message=f"Ошибка при получении автомобилей предстоящего аукциона: {str(e)}",
            timestamp=datetime.now().isoformat(),
        )
        return JSONResponse(status_code=500, content=error_response.model_dump())


@router.get("/cars/demo", response_model=LotteResponse)
async def get_demo_cars(
    count: int = Query(
        10, ge=1, le=100, description="Количество демонстрационных автомобилей"
    )
):
    """
    Демонстрационный endpoint с сгенерированными данными автомобилей
    Показывает структуру ответа API без реальных запросов к сайту
    """
    try:
        from app.models.lotte import (
            LotteCar,
            LotteAuctionDate,
            FuelType,
            TransmissionType,
            GradeType,
        )

        demo_cars = []
        demo_date = LotteAuctionDate(
            auction_date="2025-06-16",
            year=2025,
            month=6,
            day=16,
            is_today=False,
            is_future=True,
            raw_text="경매예정일2025년 06월 16일",
        )

        # Примеры корейских автомобилей
        demo_data = [
            (
                "GRANDEUR HG (H) 2.4 PREMIUM",
                "HYUNDAI",
                "GRANDEUR",
                2014,
                160246,
                "기타",
                GradeType.D_D,
            ),
            (
                "THE NEW GRAND STAREX(D)2.5 밴 스마트 5인",
                "HYUNDAI",
                "STAREX",
                2021,
                130034,
                "기타",
                GradeType.D_D,
            ),
            (
                "SPORTAGE NQ5 (H) 1.6 터보 노블레스",
                "KIA",
                "SPORTAGE",
                2022,
                96187,
                "스노우화이트펄",
                GradeType.D_B,
            ),
            (
                "THE NEW K5 (G) 2.0 프레스티지",
                "KIA",
                "K5",
                2020,
                95937,
                "스노우화이트펄",
                GradeType.A_D,
            ),
            (
                "K8 (H) 1.6 시그니처",
                "KIA",
                "K8",
                2023,
                93183,
                "오로라블랙펄",
                GradeType.A_C,
            ),
        ]

        for i, (name, brand, model, year, mileage, color, grade) in enumerate(
            demo_data[:count]
        ):
            demo_car = LotteCar(
                id=f"DEMO_{i+1:04d}",
                auction_number=f"{i+3:04d}",
                lane=["A", "B", "C", "D"][i % 4],
                license_plate=f"{41}로{9525+i}",
                name=name,
                model=model,
                brand=brand,
                year=year,
                mileage=mileage,
                fuel_type=(
                    FuelType.HYBRID if "하이브리드" in name else FuelType.GASOLINE
                ),
                transmission=TransmissionType.AUTOMATIC,
                color=color,
                grade=grade,
                starting_price=0,
                first_registration_date=f"{year}.02.14",
                inspection_valid_until="2026.02.13",
                usage_type="자사 - 자가 - 법인",
                owner_info="롯데렌탈(주)",
                vin_number=f"KMHFG413BEA00167{i}",
                engine_model="G4KK",
                images=[
                    f"https://imgmk.lotteautoauction.net/AU_CAR_IMG_ORG_HP/202506/SA2025060200012{i+1}.JPG",
                    f"https://imgmk.lotteautoauction.net/AU_CAR_IMG_ORG_HP/202506/SA2025060200012{i+2}.JPG",
                ],
                searchMngDivCd="SA",
                searchMngNo=f"SA2025060200{i+1:02d}",
                searchExhiRegiSeq="1",
            )
            demo_cars.append(demo_car)

        response = LotteResponse(
            success=True,
            message=f"Демонстрационные данные Lotte: {len(demo_cars)} автомобилей",
            auction_date_info=demo_date,
            cars=demo_cars,
            total_count=len(demo_cars),
            page=1,
            per_page=count,
            total_pages=1,
            timestamp=datetime.now().isoformat(),
            request_duration=0.1,
        )

        logger.info(f"Возвращено {len(demo_cars)} демонстрационных автомобилей Lotte")
        return response

    except Exception as e:
        logger.error(f"Ошибка при генерации демо данных Lotte: {e}")
        error_response = LotteError(
            error_code="DEMO_ERROR",
            message=f"Ошибка при генерации демо данных: {str(e)}",
            timestamp=datetime.now().isoformat(),
        )
        return JSONResponse(status_code=500, content=error_response.model_dump())


@router.get("/cars/stats")
async def get_cars_stats(service: LotteService = Depends(get_lotte_service)):
    """
    Статистика по автомобилям и состоянию сервиса Lotte
    """
    try:
        cache_stats = service.get_cache_stats()

        stats = {
            "service_status": "active",
            "authenticated": cache_stats["authenticated"],
            "cache_size": cache_stats["cache_size"],
            "cache_keys": cache_stats["cache_keys"],
            "base_url": service.base_url,
            "available_endpoints": [
                "/api/v1/lotte/auction-date - Дата аукциона",
                "/api/v1/lotte/cars - Основной endpoint с автомобилями",
                "/api/v1/lotte/cars/test - Тестовые данные из HTML файлов",
                "/api/v1/lotte/cars/demo - Демонстрационные данные",
                "/api/v1/lotte/cars/stats - Статистика сервиса",
            ],
            "timestamp": datetime.now().isoformat(),
        }

        return stats

    except Exception as e:
        logger.error(f"Ошибка при получении статистики Lotte: {e}")
        return {
            "service_status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


@router.post("/cache/clear", response_model=Dict[str, Any])
async def clear_cache(service: LotteService = Depends(get_lotte_service)):
    """Очистка кеша"""
    try:
        service.clear_cache()
        return {
            "success": True,
            "message": "Кеш Lotte успешно очищен",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Ошибка при очистке кеша: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка при очистке кеша: {e}")


@router.post("/auth/reset", response_model=Dict[str, Any])
async def reset_authentication(service: LotteService = Depends(get_lotte_service)):
    """Сброс аутентификации"""
    try:
        service.reset_authentication()
        service.clear_cache()
        return {
            "success": True,
            "message": "Аутентификация и кеш Lotte сброшены",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Ошибка при сбросе аутентификации: {e}")
        raise HTTPException(
            status_code=500, detail=f"Ошибка при сбросе аутентификации: {e}"
        )


@router.get("/debug/auth", response_model=Dict[str, Any])
async def debug_authentication(service: LotteService = Depends(get_lotte_service)):
    """Отладочный endpoint для тестирования аутентификации"""
    try:
        logger.info("=== ОТЛАДКА АУТЕНТИФИКАЦИИ LOTTE ===")

        # Сбрасываем аутентификацию для чистого теста
        service.reset_authentication()

        # Пробуем аутентифицироваться
        auth_result = service._authenticate()

        return {
            "authentication_successful": auth_result,
            "authenticated_status": service.authenticated,
            "base_url": service.base_url,
            "login_url": service.base_url + service.urls["login"],
            "login_check_url": service.base_url + service.urls["login_check"],
            "login_action_url": service.base_url + service.urls["login_action"],
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Ошибка при отладке аутентификации: {e}")
        return {
            "error": str(e),
            "authentication_successful": False,
            "authenticated_status": False,
            "timestamp": datetime.now().isoformat(),
        }


@router.get("/debug/urls", response_model=Dict[str, Any])
async def debug_urls(service: LotteService = Depends(get_lotte_service)):
    """Отладочный endpoint для тестирования доступных URL'ов"""
    try:
        logger.info("=== ОТЛАДКА URL'ОВ LOTTE ===")

        # Убеждаемся, что аутентифицированы
        if not service.authenticated:
            auth_result = service._authenticate()
            if not auth_result:
                return {"error": "Не удалось аутентифицироваться"}

        session = service._init_session()

        # Список URL'ов для тестирования
        test_urls = [
            "/hp/auct/main/viewMain.do",
            "/hp/auct/myp/viewMyp.do",
            "/hp/auct/cmm/viewMain.do",
            "/hp/auct/",
            "/hp/pub/cmm/viewMain.do",
            "/hp/auct/main/viewAuctMng.do",
            "/hp/auct/myp/entry/selectMypEntryList.do",
            "/hp/cmm/actionMenuLinkPage.do",
            "/",
        ]

        results = {}

        for url_path in test_urls:
            try:
                full_url = service.base_url + url_path
                logger.info(f"Тестируем URL: {full_url}")

                response = session.get(full_url, timeout=10, verify=False)

                results[url_path] = {
                    "status_code": response.status_code,
                    "content_length": len(response.text),
                    "content_type": response.headers.get("Content-Type", "unknown"),
                    "has_korean": "경매" in response.text or "롯데" in response.text,
                    "has_auction_date": "경매예정일" in response.text,
                    "redirect_location": response.headers.get("Location"),
                }

                if response.status_code == 200:
                    # Ищем ключевые слова в контенте
                    content_preview = (
                        response.text[:200].replace("\n", " ").replace("\r", " ")
                    )
                    results[url_path]["content_preview"] = content_preview

            except Exception as e:
                results[url_path] = {
                    "error": str(e),
                    "status_code": None,
                }

        return {
            "authenticated": service.authenticated,
            "base_url": service.base_url,
            "test_results": results,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Ошибка при отладке URL'ов: {e}")
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


@router.get("/debug/page-content", response_model=Dict[str, Any])
async def debug_page_content(service: LotteService = Depends(get_lotte_service)):
    """Отладочный endpoint для просмотра содержимого страницы с датой аукциона"""
    try:
        logger.info("=== ОТЛАДКА СОДЕРЖИМОГО СТРАНИЦЫ LOTTE ===")

        # Убеждаемся, что аутентифицированы
        if not service.authenticated:
            auth_result = service._authenticate()
            if not auth_result:
                return {"error": "Не удалось аутентифицироваться"}

        session = service._init_session()

        # Получаем страницу с датой аукциона
        home_url = service.base_url + service.urls["home"]
        response = session.get(home_url, timeout=30, verify=False)

        if response.status_code != 200:
            return {
                "error": f"HTTP {response.status_code}",
                "url": home_url,
                "timestamp": datetime.now().isoformat(),
            }

        # Ищем ключевые фразы
        content = response.text
        has_auction_date = "경매예정일" in content
        has_korean = "경매" in content or "롯데" in content

        # Пытаемся найти дату через парсер
        try:
            parsed_date = service.parser.parse_auction_date(content)
        except Exception as e:
            parsed_date = None
            parse_error = str(e)
        else:
            parse_error = None

        # Ищем все вхождения ключевых слов
        import re

        auction_matches = re.findall(r"경매예정일[^<]*", content)
        date_matches = re.findall(r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일", content)

        return {
            "url": home_url,
            "status_code": response.status_code,
            "content_length": len(content),
            "content_type": response.headers.get("Content-Type"),
            "has_korean": has_korean,
            "has_auction_date": has_auction_date,
            "auction_matches": auction_matches[:5],  # Первые 5 совпадений
            "date_matches": date_matches[:10],  # Первые 10 дат
            "parsed_date": parsed_date.model_dump() if parsed_date else None,
            "parse_error": parse_error,
            "content_preview": content[:1000],  # Первые 1000 символов
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Ошибка при отладке содержимого страницы: {e}")
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


@router.get("/debug/auction-date-direct", response_model=Dict[str, Any])
async def debug_auction_date_direct(service: LotteService = Depends(get_lotte_service)):
    """Прямой вызов метода get_auction_date для отладки"""
    try:
        logger.info("=== ПРЯМОЙ ВЫЗОВ GET_AUCTION_DATE ===")

        # Убеждаемся, что аутентифицированы
        if not service.authenticated:
            auth_result = service._authenticate()
            if not auth_result:
                return {"error": "Не удалось аутентифицироваться"}

        # Прямой вызов метода
        auction_date = await service.get_auction_date()

        return {
            "method_result": auction_date.model_dump() if auction_date else None,
            "is_none": auction_date is None,
            "authenticated": service.authenticated,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Ошибка при прямом вызове get_auction_date: {e}")
        import traceback

        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "timestamp": datetime.now().isoformat(),
        }


@router.get("/debug/auction-date-verbose", response_model=Dict[str, Any])
async def debug_auction_date_verbose(
    service: LotteService = Depends(get_lotte_service),
):
    """Подробная отладка метода get_auction_date с пошаговым логированием"""
    try:
        logger.info("=== ПОДРОБНАЯ ОТЛАДКА GET_AUCTION_DATE ===")

        # Убеждаемся, что аутентифицированы
        if not service.authenticated:
            auth_result = service._authenticate()
            if not auth_result:
                return {"error": "Не удалось аутентифицироваться"}

        # Пошаговое выполнение метода get_auction_date
        cache_key = "lotte_auction_date"

        # Проверяем кеш
        cached_data = service._get_from_cache(cache_key)
        if cached_data:
            return {
                "step": "cache_hit",
                "result": cached_data.model_dump(),
                "timestamp": datetime.now().isoformat(),
            }

        # Инициализируем сессию
        session = service._init_session()

        # Получаем главную страницу
        from urllib.parse import urljoin

        home_url = urljoin(service.base_url, service.urls["home"])

        try:
            response = session.get(home_url, timeout=30, verify=False)
        except Exception as e:
            return {
                "step": "http_request_failed",
                "error": str(e),
                "url": home_url,
                "timestamp": datetime.now().isoformat(),
            }

        if response.status_code != 200:
            return {
                "step": "http_status_error",
                "status_code": response.status_code,
                "url": home_url,
                "timestamp": datetime.now().isoformat(),
            }

        # Пытаемся парсить дату
        try:
            auction_date = service.parser.parse_auction_date(response.text)
        except Exception as e:
            import traceback

            return {
                "step": "parser_error",
                "error": str(e),
                "traceback": traceback.format_exc(),
                "content_length": len(response.text),
                "content_preview": response.text[:500],
                "timestamp": datetime.now().isoformat(),
            }

        if auction_date:
            # Сохраняем в кеш
            service._save_to_cache(cache_key, auction_date)
            return {
                "step": "success",
                "result": auction_date.model_dump(),
                "timestamp": datetime.now().isoformat(),
            }
        else:
            return {
                "step": "parser_returned_none",
                "content_length": len(response.text),
                "content_preview": response.text[:500],
                "timestamp": datetime.now().isoformat(),
            }

    except Exception as e:
        import traceback

        return {
            "step": "unexpected_error",
            "error": str(e),
            "traceback": traceback.format_exc(),
            "timestamp": datetime.now().isoformat(),
        }


@router.get("/debug/pagination", response_model=Dict[str, Any])
async def debug_pagination(
    limit: int = Query(5, ge=1, le=50, description="Размер страницы"),
    offset: int = Query(0, ge=0, description="Смещение"),
    service: LotteService = Depends(get_lotte_service),
):
    """
    Debug endpoint для тестирования пагинации
    Показывает детальную информацию о пагинации
    """
    try:
        start_time = time.time()
        logger.info(f"Debug пагинации: limit={limit}, offset={offset}")

        # Вычисляем номер страницы
        page_number = (offset // limit) + 1

        # Получаем дату аукциона
        auction_date = await service.get_auction_date()
        auction_date_str = ""
        if auction_date:
            auction_date_str = auction_date.auction_date.replace("-", "")

        # Получаем автомобили
        cars = await service.get_cars(limit, offset)

        # Получаем общее количество
        total_count = await service.get_total_cars_count()

        # Вычисляем общее количество страниц
        total_pages = (total_count + limit - 1) // limit if total_count > 0 else 1

        response_data = {
            "pagination_info": {
                "requested_limit": limit,
                "requested_offset": offset,
                "calculated_page": page_number,
                "actual_cars_returned": len(cars),
                "total_count": total_count,
                "total_pages": total_pages,
                "has_next_page": page_number < total_pages,
                "has_previous_page": page_number > 1,
            },
            "auction_info": {
                "auction_date": auction_date_str,
                "auction_date_formatted": (
                    auction_date.auction_date if auction_date else None
                ),
            },
            "sample_cars": [
                {
                    "id": car.id,
                    "name": car.name,
                    "year": car.year,
                    "mileage": car.mileage,
                }
                for car in cars[:3]  # Показываем только первые 3 автомобиля
            ],
            "request_timing": {
                "duration_seconds": time.time() - start_time,
                "timestamp": datetime.now().isoformat(),
            },
        }

        return response_data

    except Exception as e:
        logger.error(f"Ошибка в debug пагинации: {e}")
        return {
            "error": str(e),
            "pagination_info": {
                "requested_limit": limit,
                "requested_offset": offset,
                "error": "Не удалось получить данные",
            },
            "timestamp": datetime.now().isoformat(),
        }


@router.get("/car-detail", response_model=LotteCarResponse)
async def get_car_detail(
    search_mng_div_cd: str = Query(
        ..., description="Код подразделения управления (например, KS)"
    ),
    search_mng_no: str = Query(
        ..., description="Номер управления (например, KS202506090099)"
    ),
    search_exhi_regi_seq: str = Query(
        ..., description="Последовательность регистрации выставки (например, 2)"
    ),
    service: LotteService = Depends(get_lotte_service),
):
    """
    Получение детальной информации об автомобиле Lotte

    Возвращает максимально полную информацию об автомобиле:
    - Основную информацию (название, номер, цена, статус)
    - Информацию о владельце
    - Технические характеристики (год, пробег, трансмиссия, топливо и т.д.)
    - Состояние автомобиля (оценки всех систем)
    - Правовой статус (аресты, залоги)
    - Медиа файлы (фотографии, видео)
    - Записи об осмотре

    Параметры:
    - search_mng_div_cd: Код подразделения (обычно "KS")
    - search_mng_no: Управленческий номер автомобиля
    - search_exhi_regi_seq: Порядковый номер выставки
    """
    try:
        logger.info(
            f"Запрос детальной информации Lotte: div={search_mng_div_cd}, no={search_mng_no}, seq={search_exhi_regi_seq}"
        )

        # 🔧 ИСПРАВЛЕНИЕ: Принудительная аутентификация перед получением деталей
        logger.info("Проверка аутентификации перед получением деталей автомобиля...")
        auth_result = service._authenticate()
        if not auth_result:
            logger.error("Не удалось аутентифицироваться в Lotte для получения деталей")
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "message": "Ошибка аутентификации в системе Lotte",
                    "error": "Authentication failed",
                },
            )

        logger.info("✅ Аутентификация для деталей автомобиля успешна")

        # Вызываем сервис для получения детальной информации
        response = service.get_car_detail(
            search_mng_div_cd=search_mng_div_cd,
            search_mng_no=search_mng_no,
            search_exhi_regi_seq=search_exhi_regi_seq,
        )

        if not response.success:
            logger.warning(
                f"Не удалось получить детальную информацию: {response.message}"
            )
            return JSONResponse(
                status_code=404 if "не найден" in response.message.lower() else 500,
                content=response.model_dump(),
            )

        logger.info(
            f"Успешно получена детальная информация об автомобиле: {response.data.basic_info.title if response.data else 'N/A'}"
        )
        return response

    except Exception as e:
        logger.error(f"Ошибка при получении детальной информации Lotte: {e}")
        error_response = LotteCarResponse(
            success=False, message=f"Внутренняя ошибка сервера: {str(e)}", error=str(e)
        )
        return JSONResponse(status_code=500, content=error_response.model_dump())


@router.get("/car-history/{search_mng_no}", response_model=LotteCarHistoryResponse)
async def get_car_history(
    search_mng_no: str = Path(
        ..., description="Номер управления автомобиля (например, KS202507090027)"
    ),
    car_number: str = Query(
        None, description="Номерной знак автомобиля (например, 176하2567)"
    ),
    service: LotteService = Depends(get_lotte_service),
):
    """
    Получение истории автомобиля из CarHistory
    
    Возвращает:
    - Общую информацию об автомобиле (производитель, модель, год)
    - Историю использования (аренда, коммерческое использование)
    - Количество смен владельцев и номерных знаков
    - Особые происшествия (полная потеря, затопление, угон)
    - Страховые случаи с детализацией по стоимости
    - Подробные записи об авариях с датами и суммами ущерба
    
    Параметры:
    - search_mng_no: Номер управления (из детальной информации автомобиля)
    - car_number: Номерной знак (опционально, но рекомендуется для лучших результатов)
    """
    try:
        logger.info(f"Запрос истории автомобиля: search_mng_no={search_mng_no}, car_number={car_number}")
        
        # Получаем историю автомобиля
        history_response = await service.get_car_history(search_mng_no, car_number)
        
        if not history_response.success:
            logger.warning(f"Не удалось получить историю автомобиля: {history_response.message}")
            return JSONResponse(
                status_code=404 if "не найд" in history_response.message.lower() else 500,
                content=history_response.model_dump()
            )
        
        logger.info(f"Успешно получена история автомобиля: {history_response.data.car_number if history_response.data else 'N/A'}")
        return history_response
        
    except Exception as e:
        logger.error(f"Ошибка при получении истории автомобиля Lotte: {e}")
        error_response = LotteCarHistoryResponse(
            success=False,
            message=f"Внутренняя ошибка сервера: {str(e)}",
            error=str(e)
        )
        return JSONResponse(status_code=500, content=error_response.model_dump())
