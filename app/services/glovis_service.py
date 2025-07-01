"""
Сервис для работы с аукционом SSANCAR (используем имя Glovis для API совместимости)
"""

import asyncio
import time
from typing import List, Optional, Dict, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fake_useragent import UserAgent
from datetime import datetime, timedelta

from app.models.glovis import GlovisCar, GlovisResponse, GlovisError, SSANCARFilters
from app.parsers.glovis_parser import GlovisParser
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("ssancar_service")


class GlovisService:
    """Сервис для работы с аукционом SSANCAR (сохраняем имя для совместимости)"""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = "https://www.ssancar.com"
        self.api_url = "https://www.ssancar.com/ajax/ajax_car_list.php"
        self.parser = GlovisParser(self.base_url)
        self.ua = UserAgent()
        self._session = None
        self._authenticated = False
        self._session_created_at = None
        self._session_timeout = 3600  # 1 час

        # SSANCAR специфичные cookies и headers
        self._default_cookies = {
            "PHPSESSID": "oiamilkeh5lc9lf3p7eoce7due",
            "2a0d2363701f23f8a75028924a3af643": "Mi4xMzQuMTA5Ljky",
            "_gcl_au": "1.1.78877594.1751338453",
            "e1192aefb64683cc97abb83c71057733": "bGlzdA%3D%3D",
        }

        self._default_headers = {
            "Accept": "*/*",
            "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://www.ssancar.com",
            "Referer": "https://www.ssancar.com/bbs/board.php?bo_table=list",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

    # Убираем зависимости от старого менеджера сессий

    def _is_session_expired(self) -> bool:
        """Проверяет, истекла ли сессия"""
        if self._session_created_at is None:
            return True

        elapsed = datetime.now() - self._session_created_at
        return elapsed.total_seconds() > self._session_timeout

    @property
    def session(self) -> requests.Session:
        """Получить настроенную сессию для HTTP запросов"""
        if self._session is None or self._is_session_expired():
            if self._session:
                logger.info("⏰ Сессия истекла по времени, создаю новую")
                self._session.close()
            self._session = self._create_session()
            self._session_created_at = datetime.now()
        return self._session

    def _create_session(self) -> requests.Session:
        """Создает настроенную сессию для SSANCAR"""
        logger.info("🔧 Создание новой сессии для SSANCAR")

        session = requests.Session()

        # Настройка retry стратегии
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "OPTIONS"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Настройка headers
        session.headers.update(self._default_headers)

        # Устанавливаем cookies
        for name, value in self._default_cookies.items():
            session.cookies.set(name, value)

        # Отключаем проверку SSL сертификатов для стабильности
        session.verify = False

        logger.info("✅ Сессия SSANCAR создана успешно")
        return session

    async def get_car_list(self, params: Dict[str, Any]) -> GlovisResponse:
        """
        Получает список автомобилей с SSANCAR

        Args:
            params: Параметры запроса (адаптированные под Glovis API)

        Returns:
            GlovisResponse: Ответ с автомобилями
        """
        try:
            logger.info(f"📥 Запрос списка автомобилей SSANCAR с параметрами: {params}")

            # Конвертируем параметры Glovis в параметры SSANCAR
            ssancar_filters = self._convert_glovis_params_to_ssancar(params)

            # Выполняем запрос к SSANCAR
            response = await self._fetch_car_list(ssancar_filters)

            if response is None:
                return GlovisResponse(
                    success=False,
                    message="Не удалось получить данные от SSANCAR",
                    total_count=0,
                    cars=[],
                    current_page=int(ssancar_filters.pages),
                    page_size=int(ssancar_filters.list_size),
                    week_number=ssancar_filters.week_no,
                    source="SSANCAR",
                )

            # Парсим полученный HTML
            result = self.parser.parse_car_list(
                response,
                page=int(ssancar_filters.pages),
                week_no=ssancar_filters.week_no,
            )

            logger.info(f"✅ Получено {len(result.cars)} автомобилей от SSANCAR")
            return result

        except Exception as e:
            logger.error(f"❌ Ошибка при получении списка автомобилей SSANCAR: {e}")
            return GlovisResponse(
                success=False,
                message=f"Ошибка при получении данных: {str(e)}",
                total_count=0,
                cars=[],
                current_page=params.get("page", 0),
                page_size=15,
                week_number="2",
                source="SSANCAR",
            )

    def _convert_glovis_params_to_ssancar(
        self, params: Dict[str, Any]
    ) -> SSANCARFilters:
        """Конвертирует параметры Glovis API в параметры SSANCAR"""
        try:
            # Извлекаем параметры из Glovis запроса
            page = params.get("page", 1)
            # SSANCAR использует нумерацию с 0, Glovis с 1
            ssancar_page = max(0, page - 1) if isinstance(page, int) else 0

            return SSANCARFilters(
                week_no=str(params.get("auction_number", "2")),
                maker=params.get("car_manufacturer", ""),
                model=params.get("search_text", ""),
                fuel="",
                color="",
                year_from="2000",
                year_to="2024",
                price_from="0",
                price_to="200000",
                list_size="15",
                pages=str(ssancar_page),
                no="",
            )
        except Exception as e:
            logger.warning(
                f"⚠️ Ошибка конвертации параметров: {e}, используем значения по умолчанию"
            )
            return SSANCARFilters()

    async def _fetch_car_list(self, filters: SSANCARFilters) -> Optional[str]:
        """Выполняет HTTP запрос к SSANCAR для получения списка автомобилей"""
        try:
            logger.info(f"🌐 Запрос к SSANCAR API: {self.api_url}")

            # Подготавливаем данные для POST запроса
            data = {
                "weekNo": filters.week_no,
                "maker": filters.maker,
                "model": filters.model,
                "fuel": filters.fuel,
                "color": filters.color,
                "yearFrom": filters.year_from,
                "yearTo": filters.year_to,
                "priceFrom": filters.price_from,
                "priceTo": filters.price_to,
                "list": filters.list_size,
                "pages": filters.pages,
                "no": filters.no,
            }

            logger.debug(f"📊 Данные запроса: {data}")

            # Выполняем запрос
            response = self.session.post(self.api_url, data=data, timeout=30)

            if response.status_code == 200:
                logger.info("✅ Данные от SSANCAR получены успешно")
                return response.text
            else:
                logger.error(f"❌ Ошибка HTTP {response.status_code}: {response.text}")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка сетевого запроса к SSANCAR: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при запросе к SSANCAR: {e}")
            return None

    async def get_car_details(self, car_gn: str) -> Optional[Dict[str, Any]]:
        """
        Получает детальную информацию об автомобиле (эмуляция для совместимости)

        Args:
            car_gn: Идентификатор автомобиля (в SSANCAR это car_no)

        Returns:
            Optional[Dict]: Детальная информация или None
        """
        try:
            logger.info(f"📥 Запрос деталей автомобиля SSANCAR car_no={car_gn}")

            # В SSANCAR детальная информация доступна по отдельной странице
            detail_url = f"{self.base_url}/page/car_view.php?car_no={car_gn}"

            response = self.session.get(detail_url, timeout=30)

            if response.status_code == 200:
                logger.info(f"✅ Детальная страница получена для автомобиля {car_gn}")
                # Здесь можно добавить парсинг детальной страницы
                return {
                    "car_no": car_gn,
                    "detail_url": detail_url,
                    "status": "success",
                    "message": "Детальная информация доступна по URL",
                    "raw_html": (
                        response.text[:1000] + "..."
                        if len(response.text) > 1000
                        else response.text
                    ),
                }
            else:
                logger.warning(
                    f"⚠️ Детальная страница недоступна для автомобиля {car_gn}"
                )
                return None

        except Exception as e:
            logger.error(f"❌ Ошибка при получении деталей автомобиля SSANCAR: {e}")
            return None

    def get_test_data(self) -> GlovisResponse:
        """Возвращает тестовые данные для отладки"""
        logger.info("🧪 Возвращаем тестовые данные SSANCAR")
        return self.parser.get_test_data()

    def get_regions(self) -> Dict[str, Any]:
        """Возвращает список регионов SSANCAR (эмуляция для совместимости)"""
        logger.info("📍 Возвращаем регионы SSANCAR")

        return {
            "success": True,
            "message": "Регионы SSANCAR",
            "regions": [
                {
                    "code": "SSANCAR",
                    "name": "SSANCAR Auction",
                    "description": "Главный аукцион SSANCAR",
                }
            ],
            "source": "SSANCAR",
        }

    def get_auctions(self) -> Dict[str, Any]:
        """Возвращает список аукционов SSANCAR"""
        logger.info("🏛️ Возвращаем аукционы SSANCAR")

        return {
            "success": True,
            "message": "Аукционы SSANCAR",
            "auctions": [
                {"number": "1", "name": "Неделя 1", "status": "active"},
                {"number": "2", "name": "Неделя 2", "status": "active"},
                {"number": "3", "name": "Неделя 3", "status": "active"},
                {"number": "4", "name": "Неделя 4", "status": "active"},
            ],
            "source": "SSANCAR",
        }

    async def health_check(self) -> Dict[str, Any]:
        """Проверка состояния сервиса SSANCAR"""
        try:
            logger.info("🏥 Проверка состояния сервиса SSANCAR")

            # Проверяем доступность главной страницы
            response = self.session.get(
                f"{self.base_url}/bbs/board.php?bo_table=list", timeout=10
            )

            status = "healthy" if response.status_code == 200 else "unhealthy"

            return {
                "service": "SSANCAR Service",
                "status": status,
                "base_url": self.base_url,
                "api_url": self.api_url,
                "response_code": response.status_code,
                "timestamp": datetime.now().isoformat(),
                "features": {
                    "car_list": True,
                    "car_details": True,
                    "pagination": True,
                    "filters": True,
                    "weeks": ["1", "2", "3", "4"],
                },
            }

        except Exception as e:
            logger.error(f"❌ Ошибка проверки состояния SSANCAR: {e}")
            return {
                "service": "SSANCAR Service",
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def __del__(self):
        """Деструктор для очистки ресурсов"""
        try:
            if hasattr(self, "_session") and self._session:
                self._session.close()
                logger.info("🧹 Сессия SSANCAR закрыта")
        except:
            pass
