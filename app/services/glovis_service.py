"""
Сервис для работы с аукционом SSANCAR (используем имя Glovis для API совместимости)
"""

import asyncio
import time
import json
import os
from typing import List, Optional, Dict, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fake_useragent import UserAgent
from datetime import datetime, timedelta

from app.models.glovis import (
    GlovisCar,
    GlovisResponse,
    GlovisError,
    SSANCARFilters,
    SSANCARManufacturersResponse,
    SSANCARModelsResponse,
    SSANCARFilterOptionsResponse,
    SSANCARFilteredCarsResponse,
    SSANCARAdvancedFilters,
    SSANCARCarDetail,
    SSANCARCarDetailResponse,
)
from app.parsers.glovis_parser import GlovisParser
from app.parsers.ssancar_detail_parser import parse_ssancar_car_detail
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

        # Загружаем данные carList из SSANCAR
        self._carlist_data = self._load_carlist_data()

        # SSANCAR специфичные cookies и headers (обновлено 2025-07-07)
        self._default_cookies = {
            "_gcl_au": "1.1.78877594.1751338453",
            "PHPSESSID": "lqqfmskmrn3m0sgdqjh8vnblbk",
            "2a0d2363701f23f8a75028924a3af643": "Mi4xMzUuNjYuODA%3D",
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
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

    # Убираем зависимости от старого менеджера сессий

    def _get_current_week_number(self) -> str:
        """
        Определяет номер недели аукциона в зависимости от текущего дня недели:
        - Понедельник (0) и Вторник (1) → weekNo = 1
        - Четверг (3) и Пятница (4) → weekNo = 2
        - Остальные дни → weekNo = 1 (по умолчанию)
        """
        now = datetime.now()
        weekday = now.weekday()  # 0=Понедельник, 1=Вторник, ..., 6=Воскресенье

        if weekday in [0, 1]:  # Понедельник или Вторник
            week_no = "1"
        elif weekday in [3, 4]:  # Четверг или Пятница
            week_no = "2"
        else:  # Остальные дни (Среда, Суббота, Воскресенье)
            week_no = "1"  # По умолчанию

        logger.info(
            f"📅 Текущий день недели: {now.strftime('%A')} ({weekday}), используем weekNo: {week_no}"
        )
        return week_no

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

        # Очищаем существующие cookies перед установкой новых
        session.cookies.clear()
        
        # Устанавливаем cookies
        for name, value in self._default_cookies.items():
            session.cookies.set(name, value, domain=".ssancar.com", path="/")

        # Отключаем проверку SSL сертификатов для стабильности
        session.verify = False

        logger.info("✅ Сессия SSANCAR создана успешно")
        return session
    
    def _update_cookies_from_response(self, response: requests.Response) -> None:
        """Безопасно обновляет cookies из ответа сервера"""
        try:
            # Requests автоматически обрабатывает Set-Cookie заголовки
            # Но мы добавим дополнительную проверку на дубликаты
            if hasattr(response, 'cookies') and response.cookies:
                for cookie in response.cookies:
                    # Удаляем старую версию cookie если она есть
                    self.session.cookies.set(cookie.name, cookie.value, 
                                           domain=cookie.domain or ".ssancar.com",
                                           path=cookie.path or "/")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при обновлении cookies из ответа: {e}")

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
            
            # Логируем преобразованные параметры
            logger.info(f"🔧 Преобразованные параметры SSANCAR: {ssancar_filters.model_dump()}")

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
            logger.info(f"🔄 Конвертация параметров Glovis в SSANCAR: {params}")
            
            # Извлекаем параметры из Glovis запроса
            page = params.get("page", 1)
            # SSANCAR использует нумерацию с 0, Glovis с 1
            ssancar_page = max(0, page - 1) if isinstance(page, int) else 0

            # Определяем weekNo: используем переданный параметр или автоматически определяем по дню недели
            week_no = params.get("auction_number")
            if week_no is None:
                week_no = self._get_current_week_number()
            else:
                week_no = str(week_no)

            # Конвертируем производителя в корейский
            manufacturer = params.get("car_manufacturer", "")
            if manufacturer:
                manufacturer = self._convert_manufacturer_to_korean(manufacturer)

            # Обрабатываем модель
            model = ""
            if params.get("car_model"):
                # Если передана модель, конвертируем в код
                model_name = params.get("car_model")
                if params.get("car_manufacturer") and not model_name.isdigit():
                    model_code = self.convert_model_to_code(
                        params.get("car_manufacturer"), model_name
                    )
                    model = model_code if model_code else model_name
                else:
                    model = model_name
            elif params.get("search_text"):
                # Fallback на search_text для обратной совместимости
                model = params.get("search_text", "")

            # Build filters with default values
            filter_params = {
                "week_no": week_no,
                "maker": manufacturer,
                "model": model,
                "fuel": "",
                "color": "",
                "year_from": "2000",  # Default year from
                "year_to": "2025",    # Default year to
                "price_from": "0",    # Default price from
                "price_to": "200000", # Default price to
                "list_size": "15",
                "pages": str(ssancar_page),
                "no": "",
            }
            
            # Add optional filters if provided
            if params.get("fuel_type"):
                filter_params["fuel"] = self._convert_fuel_to_korean(params.get("fuel_type"))
            
            if params.get("color"):
                filter_params["color"] = self._convert_color_to_korean(params.get("color"))
            
            if params.get("year_from"):
                filter_params["year_from"] = str(params.get("year_from"))
                
            if params.get("year_to"):
                filter_params["year_to"] = str(params.get("year_to"))
                
            if params.get("price_from"):
                filter_params["price_from"] = str(params.get("price_from"))
                
            if params.get("price_to"):
                filter_params["price_to"] = str(params.get("price_to"))
            
            logger.info(f"📋 Финальные параметры фильтров SSANCAR: {filter_params}")
            return SSANCARFilters(**filter_params)
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

            logger.info(f"📊 Данные запроса: {data}")
            
            # Безопасное логирование cookies с обработкой дубликатов
            try:
                cookie_dict = {}
                for cookie in self.session.cookies:
                    # Если есть дубликаты, берем последнее значение
                    cookie_dict[cookie.name] = cookie.value
                logger.info(f"📋 Cookies: {cookie_dict}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось вывести cookies: {e}")
                
            logger.info(f"📋 Headers: {self.session.headers}")

            # Выполняем запрос с обработкой возможных ошибок cookies
            try:
                response = self.session.post(self.api_url, data=data, timeout=30)
            except requests.exceptions.RequestException as e:
                # Если ошибка связана с cookies, пытаемся пересоздать сессию
                if "multiple cookies" in str(e).lower():
                    logger.warning("⚠️ Обнаружены дублирующиеся cookies, пересоздаю сессию")
                    self._session = None
                    response = self.session.post(self.api_url, data=data, timeout=30)
                else:
                    raise
            
            # Обновляем cookies из ответа
            self._update_cookies_from_response(response)

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

        # Получаем текущую неделю динамически
        current_week = self._get_current_week_number()

        # Создаем список аукционов с отметкой текущей недели
        auctions = []
        for i in range(1, 5):  # Недели 1-4
            week_str = str(i)
            auction = {
                "number": week_str,
                "name": f"Неделя {i}",
                "status": "active",
            }
            # Отмечаем текущую неделю как default
            if week_str == current_week:
                auction["default"] = True
            auctions.append(auction)

        return {
            "success": True,
            "message": "Аукционы SSANCAR",
            "auctions": auctions,
            "source": "SSANCAR",
            "current_week": current_week,
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

    def _load_carlist_data(self) -> Dict[str, Any]:
        """Загружает данные carList из извлеченного JSON файла"""
        try:
            # Путь к файлу с данными carList
            carlist_path = os.path.join(os.getcwd(), "ssancar_carlist.json")

            if not os.path.exists(carlist_path):
                logger.warning(
                    f"⚠️ Файл {carlist_path} не найден, используем пустые данные"
                )
                return self._get_fallback_carlist_data()

            with open(carlist_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            logger.info(
                f"✅ Загружены данные carList: {len(data.get('korean_to_english_manufacturers', {}))} производителей"
            )
            return data

        except Exception as e:
            logger.error(f"❌ Ошибка при загрузке carList: {e}")
            return self._get_fallback_carlist_data()

    def _get_fallback_carlist_data(self) -> Dict[str, Any]:
        """Возвращает fallback данные если основные не загрузились"""
        return {
            "korean_to_english_manufacturers": {
                "현대": "HYUNDAI",
                "기아": "KIA",
                "BMW": "BMW",
                "벤츠": "BENZ",
                "아우디": "AUDI",
            },
            "english_to_korean_manufacturers": {
                "HYUNDAI": "현대",
                "KIA": "기아",
                "BMW": "BMW",
                "BENZ": "벤츠",
                "AUDI": "아우디",
            },
            "english_model_to_code": {},
            "korean_model_to_code": {},
            "full_carlist": {},
        }

    # =============================================================================
    # МАППИНГ ДАННЫХ ДЛЯ SSANCAR
    # =============================================================================

    def _convert_manufacturer_to_korean(self, english_code: str) -> str:
        """Конвертируем английский код производителя в корейский для SSANCAR"""
        # Используем данные из carList
        mapping = self._carlist_data.get("english_to_korean_manufacturers", {})
        korean_name = mapping.get(english_code, english_code)
        logger.debug(f"🔄 Маппинг производителя: {english_code} -> {korean_name}")
        return korean_name

    def _convert_fuel_to_korean(self, english_fuel: str) -> str:
        """Конвертируем английское название топлива в корейское для SSANCAR"""
        mapping = {
            "Gasoline": "휘발유",
            "Diesel": "경유",
            "LPG": "LPG",
            "Gasol/Hybrid": "하이브리드",
            "Electric": "전기",
            "Hydrogen": "수소",
        }
        korean_fuel = mapping.get(english_fuel, english_fuel)
        logger.debug(f"🔄 Маппинг топлива: {english_fuel} -> {korean_fuel}")
        return korean_fuel

    def _convert_color_to_korean(self, english_color: str) -> str:
        """Конвертируем английское название цвета в корейское для SSANCAR"""
        mapping = {
            "Black": "검정",
            "White": "흰",
            "Gray": "회",
            "Silver": "은",
            "Pearl": "펄",
            "Blue": "파란",
            "Sky": "하늘",
            "Red": "빨강",
            "Yellow": "노란색",
            "Orange": "오렌지",
            "Brown": "갈",
            "Gold": "금",
            "Green": "녹",
        }
        korean_color = mapping.get(english_color, english_color)
        logger.debug(f"🔄 Маппинг цвета: {english_color} -> {korean_color}")
        return korean_color

    def _convert_model_to_code(self, manufacturer: str, model_name: str) -> str:
        """Конвертируем название модели в код для SSANCAR API"""
        # Используем данные из carList
        models_mapping = self._carlist_data.get("english_model_to_code", {}).get(
            manufacturer, {}
        )
        model_code = models_mapping.get(model_name, "")
        logger.debug(f"🔄 Маппинг модели {manufacturer}/{model_name} -> {model_code}")
        return model_code

    def get_models_for_manufacturer(self, manufacturer: str) -> List[Dict[str, str]]:
        """Получает список моделей для указанного производителя из carList"""
        try:
            # Получаем корейское название производителя
            korean_manufacturer = self._convert_manufacturer_to_korean(manufacturer)

            # Получаем модели из carList
            carlist = self._carlist_data.get("full_carlist", {})
            models_data = carlist.get(korean_manufacturer, [])

            # Формируем ответ в формате API
            models = []
            for model in models_data:
                models.append(
                    {
                        "code": model.get("no", ""),
                        "name": model.get("e_name", ""),
                        "name_en": model.get("e_name", ""),
                        "name_kr": model.get("name", ""),
                        "manufacturer_code": manufacturer,
                        "count": 0,  # Значение по умолчанию для совместимости
                    }
                )

            logger.debug(f"🏭 Найдено {len(models)} моделей для {manufacturer}")
            return models

        except Exception as e:
            logger.error(f"❌ Ошибка получения моделей для {manufacturer}: {e}")
            return []

    def get_all_manufacturers_from_carlist(self) -> List[Dict[str, str]]:
        """Получает все производители из carList"""
        try:
            korean_to_english = self._carlist_data.get(
                "korean_to_english_manufacturers", {}
            )
            manufacturers = []

            for korean_name, english_name in korean_to_english.items():
                # Получаем количество моделей для производителя
                carlist = self._carlist_data.get("full_carlist", {})
                model_count = len(carlist.get(korean_name, []))

                manufacturers.append(
                    {
                        "code": english_name,
                        "name": english_name,
                        "name_en": english_name,
                        "name_kr": korean_name,
                        "model_count": model_count,
                        "count": 0,  # Значение по умолчанию для совместимости
                        "enabled": True,  # Значение по умолчанию для совместимости
                    }
                )

            logger.debug(f"🏭 Найдено {len(manufacturers)} производителей в carList")
            return manufacturers

        except Exception as e:
            logger.error(f"❌ Ошибка получения производителей из carList: {e}")
            return []

    # =============================================================================
    # SSANCAR FILTER METHODS
    # =============================================================================

    async def get_ssancar_manufacturers(self) -> dict:
        """
        Получить список производителей SSANCAR из carList данных
        """
        from app.models.glovis import SSANCARManufacturersResponse

        try:
            logger.info("🏭 Получение списка производителей SSANCAR из carList")

            # Получаем производителей из carList
            manufacturers = self.get_all_manufacturers_from_carlist()

            response = SSANCARManufacturersResponse(
                success=True,
                message=f"Получено {len(manufacturers)} производителей SSANCAR из carList",
                manufacturers=manufacturers,
                total_count=len(manufacturers),
            )

            logger.info(
                f"✅ Возвращено {len(manufacturers)} производителей SSANCAR из carList"
            )
            return response.model_dump()

        except Exception as e:
            logger.error(f"❌ Ошибка получения производителей SSANCAR: {e}")

            return SSANCARManufacturersResponse(
                success=False,
                message=f"Ошибка получения производителей: {str(e)}",
                manufacturers=[],
                total_count=0,
            ).model_dump()

    async def get_ssancar_models(self, manufacturer_code: str) -> dict:
        """
        Получить список моделей для указанного производителя SSANCAR из carList
        """
        try:
            from app.models.glovis import SSANCARModelsResponse

            logger.info(
                f"🚗 Получение моделей SSANCAR для производителя {manufacturer_code} из carList"
            )

            # Получаем модели из carList
            models = self.get_models_for_manufacturer(manufacturer_code)

            response = SSANCARModelsResponse(
                success=True,
                message=f"Получено {len(models)} моделей для {manufacturer_code} из carList",
                models=models,
                manufacturer_code=manufacturer_code,
                total_count=len(models),
            )

            logger.info(
                f"✅ Возвращено {len(models)} моделей для {manufacturer_code} из carList"
            )
            return response.model_dump()

        except Exception as e:
            logger.error(f"❌ Ошибка получения моделей SSANCAR: {e}")
            from app.models.glovis import SSANCARModelsResponse

            return SSANCARModelsResponse(
                success=False,
                message=f"Ошибка получения моделей: {str(e)}",
                models=[],
                manufacturer_code=manufacturer_code,
                total_count=0,
            ).model_dump()

    async def get_ssancar_filter_options(self) -> dict:
        """
        Получить все доступные опции фильтрации SSANCAR
        """
        try:
            from app.models.glovis import SSANCARFilterOptionsResponse

            logger.info("🔧 Получение опций фильтрации SSANCAR")

            # Получаем статические данные
            manufacturers = self.parser.get_static_manufacturers()
            fuel_types = self.parser.get_static_fuel_types()
            colors = self.parser.get_static_colors()
            transmissions = self.parser.get_static_transmissions()
            condition_grades = self.parser.get_static_condition_grades()
            weeks = self.parser.get_static_weeks()

            # Анализируем доступные данные для определения диапазонов
            year_range = {"min": 1990, "max": 2025}
            price_range = {"min": 0, "max": 100000}

            try:
                # Получаем данные для анализа диапазонов
                params = {"weekNo": "1", "list": "100", "pages": "0"}
                api_data = await self._make_request_to_ssancar(params)

                if api_data and "cars" in api_data:
                    analysis = self.parser.analyze_car_data_for_filters(
                        api_data["cars"]
                    )

                    if analysis["years"]["min"] != 9999:
                        year_range = analysis["years"]

                    if analysis["prices"]["min"] != float("inf"):
                        price_range = analysis["prices"]

                    # Обновляем счетчики производителей
                    updated_manufacturers = self.parser.parse_manufacturers_from_cars(
                        api_data["cars"]
                    )
                    if updated_manufacturers:
                        manufacturers = updated_manufacturers

            except Exception as e:
                logger.warning(
                    f"⚠️ Не удалось проанализировать данные для фильтров: {e}"
                )

            response = SSANCARFilterOptionsResponse(
                success=True,
                message="Опции фильтрации SSANCAR получены",
                manufacturers=manufacturers,
                fuel_types=fuel_types,
                colors=colors,
                transmissions=transmissions,
                condition_grades=condition_grades,
                weeks=weeks,
                year_range=year_range,
                price_range=price_range,
            )

            logger.info("✅ Опции фильтрации SSANCAR получены")
            return response.model_dump()

        except Exception as e:
            logger.error(f"❌ Ошибка получения опций фильтрации SSANCAR: {e}")
            from app.models.glovis import SSANCARFilterOptionsResponse

            return SSANCARFilterOptionsResponse(
                success=False,
                message=f"Ошибка получения опций фильтрации: {str(e)}",
                manufacturers=[],
                fuel_types=[],
                colors=[],
                transmissions=[],
                condition_grades=[],
                weeks=[],
                year_range={"min": 1990, "max": 2025},
                price_range={"min": 0, "max": 100000},
            ).model_dump()

    async def search_ssancar_cars_with_filters(self, filters: dict) -> dict:
        """
        Поиск автомобилей SSANCAR с применением фильтров
        """
        import time

        start_time = time.time()

        try:
            from app.models.glovis import (
                SSANCARFilteredCarsResponse,
                SSANCARAdvancedFilters,
            )

            logger.info(f"🔍 Поиск автомобилей SSANCAR с фильтрами: {filters}")

            # Преобразуем фильтры в модель для валидации
            filter_model = SSANCARAdvancedFilters(**filters)

            # Подготавливаем параметры для API SSANCAR
            api_params = self._convert_filters_to_ssancar_params(filter_model)

            # Выполняем запрос к SSANCAR API
            api_data = await self._make_request_to_ssancar(api_params)

            cars = []
            total_count = 0

            if api_data and api_data.get("success"):
                cars = api_data.get("cars", [])
                total_count = api_data.get("total_count", len(cars))

            # Вычисляем пагинацию
            page_size = filter_model.page_size or 15
            current_page = filter_model.page or 1
            total_pages = max(1, (total_count + page_size - 1) // page_size)

            response = SSANCARFilteredCarsResponse(
                success=True,
                message=f"Найдено {total_count} автомобилей",
                applied_filters=filter_model,
                cars=cars,
                total_count=total_count,
                current_page=current_page,
                page_size=page_size,
                total_pages=total_pages,
                has_next_page=current_page < total_pages,
                has_prev_page=current_page > 1,
                request_duration=time.time() - start_time,
            )

            logger.info(
                f"✅ Найдено {total_count} автомобилей "
                f"(страница {current_page}/{total_pages})"
            )

            return response.model_dump()

        except Exception as e:
            logger.error(f"❌ Ошибка поиска автомобилей SSANCAR с фильтрами: {e}")
            from app.models.glovis import (
                SSANCARFilteredCarsResponse,
                SSANCARAdvancedFilters,
            )

            # Создаем пустые фильтры при ошибке
            empty_filters = SSANCARAdvancedFilters()

            return SSANCARFilteredCarsResponse(
                success=False,
                message=f"Ошибка поиска: {str(e)}",
                applied_filters=empty_filters,
                cars=[],
                total_count=0,
                current_page=1,
                page_size=15,
                total_pages=1,
                has_next_page=False,
                has_prev_page=False,
                request_duration=time.time() - start_time,
            ).model_dump()

    def _convert_filters_to_ssancar_params(self, filters) -> dict:
        """
        Преобразует фильтры в параметры API SSANCAR
        """
        params = {
            "list": str(filters.page_size or 15),
            "pages": str(
                (filters.page or 1) - 1
            ),  # SSANCAR использует 0-based pagination
        }

        # Основные фильтры
        if filters.week_number:
            params["weekNo"] = str(filters.week_number)
        else:
            params["weekNo"] = "1"  # По умолчанию 1-я неделя

        if filters.manufacturer:
            # Конвертируем английский код в корейский для SSANCAR
            korean_manufacturer = self._convert_manufacturer_to_korean(
                filters.manufacturer
            )
            params["maker"] = korean_manufacturer

        if filters.model:
            # Если модель передается как название, конвертируем в код
            if filters.manufacturer and not filters.model.isdigit():
                model_code = self.convert_model_to_code(
                    filters.manufacturer, filters.model
                )
                params["model"] = model_code if model_code else filters.model
            else:
                params["model"] = filters.model

        if filters.fuel:
            # Конвертируем английское название топлива в корейское
            korean_fuel = self._convert_fuel_to_korean(filters.fuel)
            params["fuel"] = korean_fuel

        if filters.color:
            # Конвертируем английское название цвета в корейское
            korean_color = self._convert_color_to_korean(filters.color)
            params["color"] = korean_color

        # Диапазоны
        if filters.year_from:
            params["yearFrom"] = str(filters.year_from)

        if filters.year_to:
            params["yearTo"] = str(filters.year_to)

        if filters.price_from:
            params["priceFrom"] = str(filters.price_from)

        if filters.price_to:
            params["priceTo"] = str(filters.price_to)

        # Дополнительные фильтры
        if hasattr(filters, "transmission") and filters.transmission:
            params["transmission"] = filters.transmission

        if hasattr(filters, "condition_grade") and filters.condition_grade:
            params["condition"] = filters.condition_grade

        if hasattr(filters, "search_text") and filters.search_text:
            params["searchText"] = filters.search_text

        logger.info(f"🔧 Преобразованы параметры SSANCAR: {params}")
        return params

    async def _make_request_to_ssancar(self, params: dict) -> Optional[dict]:
        """
        Выполняет запрос к SSANCAR API и возвращает результат

        Args:
            params: Параметры запроса

        Returns:
            Optional[dict]: Результат запроса или None при ошибке
        """
        try:
            logger.info(f"🌐 Запрос к SSANCAR API с параметрами: {params}")

            # Выполняем запрос к SSANCAR
            response = await self._fetch_car_list(SSANCARFilters(**params))

            if response:
                # Парсим ответ
                result = self.parser.parse_car_list(
                    response,
                    page=int(params.get("pages", 0)),
                    week_no=params.get("weekNo", "1"),
                )

                if result.success:
                    return {
                        "success": True,
                        "cars": [car.model_dump() for car in result.cars],
                        "total_count": result.total_count,
                    }

                return None

        except Exception as e:
            logger.error(f"❌ Ошибка запроса к SSANCAR API: {e}")
            return None

    # =============================================================================
    # CARLIST METHODS - Working with real SSANCAR data
    # =============================================================================

    def convert_model_to_code(self, manufacturer: str, model_name: str) -> str:
        """Конвертируем название модели в код для SSANCAR API"""
        models_mapping = self._carlist_data.get("english_model_to_code", {}).get(
            manufacturer, {}
        )
        model_code = models_mapping.get(model_name, "")
        logger.debug(f"🔄 Маппинг модели {manufacturer}/{model_name} -> {model_code}")
        return model_code

    # =============================================================================
    # SSANCAR CAR DETAIL METHODS
    # =============================================================================

    async def get_ssancar_car_detail(self, car_no: str) -> SSANCARCarDetailResponse:
        """
        Получает детальную информацию об автомобиле SSANCAR

        Args:
            car_no: Номер автомобиля SSANCAR

        Returns:
            SSANCARCarDetailResponse: Детальная информация об автомобиле
        """
        try:
            logger.info(f"🚗 Получение детальной информации для автомобиля {car_no}")

            # Формируем URL для детальной страницы
            detail_url = f"{self.base_url}/page/car_view.php"

            # Параметры запроса
            params = {"car_no": car_no}

            # Устанавливаем специальные headers для GET запроса
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
                "Cache-Control": "max-age=0",
                "Connection": "keep-alive",
                "Referer": "https://www.ssancar.com/bbs/board.php?bo_table=list",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": self._default_headers["User-Agent"],
                "sec-ch-ua": self._default_headers["sec-ch-ua"],
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": self._default_headers["sec-ch-ua-platform"],
            }

            # Выполняем запрос
            response = self.session.get(
                detail_url, params=params, headers=headers, timeout=30
            )

            if response.status_code != 200:
                logger.error(
                    f"❌ HTTP ошибка {response.status_code} при запросе детальной страницы"
                )
                return SSANCARCarDetailResponse(
                    success=False,
                    message=f"HTTP ошибка {response.status_code}",
                    car_detail=None,
                )

            # Парсим HTML
            car_detail = parse_ssancar_car_detail(response.text, car_no)

            if car_detail:
                logger.info(f"✅ Успешно получена детальная информация для {car_no}")
                logger.info(f"   📝 Название: {car_detail.car_name}")
                logger.info(f"   📸 Изображений: {len(car_detail.images)}")
                logger.info(f"   💰 Цена: {car_detail.starting_price}")

                return SSANCARCarDetailResponse(
                    success=True,
                    message="Детальная информация получена успешно",
                    car_detail=car_detail,
                )
            else:
                logger.warning(
                    f"⚠️ Не удалось распарсить детальную страницу для {car_no}"
                )
                return SSANCARCarDetailResponse(
                    success=False,
                    message="Не удалось распарсить детальную страницу",
                    car_detail=None,
                )

        except requests.exceptions.Timeout:
            logger.error(f"⏰ Таймаут при запросе детальной страницы для {car_no}")
            return SSANCARCarDetailResponse(
                success=False, message="Таймаут запроса", car_detail=None
            )

        except requests.exceptions.RequestException as e:
            logger.error(
                f"🌐 Ошибка сети при запросе детальной страницы для {car_no}: {e}"
            )
            return SSANCARCarDetailResponse(
                success=False, message=f"Ошибка сети: {str(e)}", car_detail=None
            )

        except Exception as e:
            logger.error(
                f"🚫 Неожиданная ошибка при получении деталей для {car_no}: {e}"
            )
            return SSANCARCarDetailResponse(
                success=False, message=f"Неожиданная ошибка: {str(e)}", car_detail=None
            )
