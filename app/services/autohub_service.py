import asyncio
import time
import json
import hashlib
from typing import List, Optional, Dict, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fake_useragent import UserAgent
from urllib.parse import urljoin

from app.models.autohub import (
    AutohubCar,
    AutohubResponse,
    AutohubError,
    AutohubCarDetail,
    AutohubCarDetailRequest,
    AutohubCarDetailResponse,
)
from app.models.autohub_filters import (
    AutohubSearchRequest,
    AutohubManufacturer,
    AutohubModel,
    AutohubGeneration,
    AutohubConfiguration,
    AutohubAuctionSession,
    AutohubManufacturersResponse,
    AutohubModelsResponse,
    AutohubGenerationsResponse,
    AutohubConfigurationsResponse,
    AutohubAuctionSessionsResponse,
    AUTOHUB_MANUFACTURERS,
)
from app.parsers.autohub_parser import parse_car_detail, parse_car_diagram
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("autohub_service")


class AutohubService:
    """Сервис для работы с Autohub auction"""

    def __init__(self):
        self.settings = get_settings()
        self.ua = UserAgent()
        self._session = None
        self.base_url = "https://www.autohubauction.co.kr"

        # Инициализируем парсер
        from app.parsers.autohub_parser import AutohubParser

        self.parser = AutohubParser(self.base_url)

        # Cache for auction code (valid for 24 hours)
        self._cached_auction_code: Optional[str] = None
        self._cache_timestamp: Optional[float] = None
        self._CACHE_DURATION = 86400  # 24 hours in seconds

        # In-memory cache with tiered TTL
        self._cache: Dict[str, tuple] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    @property
    def session(self) -> requests.Session:
        """Получить настроенную сессию для HTTP запросов"""
        if self._session is None:
            self._session = self._create_session()
        return self._session

    def _get_from_cache(self, key: str, ttl: int = 300) -> Optional[Any]:
        """Get data from in-memory cache with per-key TTL."""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if time.time() - timestamp < ttl:
                self._cache_hits += 1
                return data
            del self._cache[key]
        self._cache_misses += 1
        return None

    def _save_to_cache(self, key: str, data: Any) -> None:
        """Save data to in-memory cache."""
        self._cache[key] = (data, time.time())

    def _make_cache_key(self, prefix: str, params: Optional[Dict] = None) -> str:
        """Create a cache key from prefix and optional params dict."""
        if params:
            param_str = json.dumps(params, sort_keys=True, default=str)
            param_hash = hashlib.md5(param_str.encode()).hexdigest()[:12]
            return f"autohub:{prefix}:{param_hash}"
        return f"autohub:{prefix}"

    def _get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0
        return {
            "service": "Autohub",
            "cache_entries": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate_percent": round(hit_rate, 2),
        }

    def _create_session(self) -> requests.Session:
        """Создает настроенную сессию с retry стратегией"""
        session = requests.Session()

        # Настройка retry стратегии
        retry_strategy = Retry(
            total=self.settings.max_retries,
            backoff_factor=self.settings.retry_delay,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Настройка headers (соответствуют cURL примеру)
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
                "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
            }
        )

        # Отключаем проверку SSL сертификатов для проблемных сайтов
        session.verify = False

        # Подавляем предупреждения о незащищённых запросах
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        return session

    async def _initialize_session(self) -> bool:
        """
        Инициализирует сессию, получая необходимые cookies с главной страницы

        Returns:
            bool: True если инициализация прошла успешно
        """
        try:
            logger.info("Инициализируем сессию с Autohub")

            # Сначала заходим на главную страницу для получения cookies
            response = self.session.get(
                self.settings.autohub_base_url,
                timeout=self.settings.request_timeout,
                allow_redirects=True,
            )
            response.raise_for_status()

            logger.info(f"Получены базовые cookies: {len(self.session.cookies)} штук")

            # Добавляем дополнительные headers для выглядеть как браузер
            self.session.headers.update(
                {
                    "Referer": "https://www.autohubauction.co.kr/newfront/index.do",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-User": "?1",
                    "Sec-Fetch-Dest": "document",
                }
            )

            # Выполняем авторизацию
            auth_success = await self._authenticate()
            if not auth_success:
                logger.error("Авторизация не удалась")
                return False

            return True

        except Exception as e:
            logger.error(f"Ошибка при инициализации сессии: {e}")
            return False

    async def _authenticate(self) -> bool:
        """
        Выполняет авторизацию на сайте Autohub с повторными попытками

        Returns:
            bool: True если авторизация прошла успешно
        """
        max_retries = 3
        retry_delay = 2.0

        for attempt in range(max_retries):
            try:
                logger.info(
                    f"🔐 Попытка авторизации на Autohub ({attempt + 1}/{max_retries})"
                )

                # Данные для авторизации
                login_data = {
                    "i_sUserId": self.settings.autohub_username,
                    "i_sPswd": self.settings.autohub_password,
                    "i_sLoginGubun": "001",  # Тип пользователя: 001 = участник аукциона
                }

                logger.debug(f"Используем логин: {self.settings.autohub_username}")

                # Обновляем headers для AJAX запроса
                auth_headers = {
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Referer": self.settings.autohub_base_url,
                }

                # Добавляем задержку перед авторизацией
                await asyncio.sleep(1.0)

                # Выполняем POST запрос для авторизации
                response = self.session.post(
                    self.settings.autohub_login_url,
                    data=login_data,
                    headers=auth_headers,
                    timeout=self.settings.request_timeout,
                    allow_redirects=False,
                )

                logger.info(f"📡 Ответ авторизации: статус {response.status_code}")

                # Проверяем ответ
                if response.status_code == 200:
                    try:
                        auth_response = response.json()
                        logger.debug(f"JSON ответ: {auth_response}")

                        if auth_response.get("status") == "succ":
                            logger.info("✅ Авторизация успешна!")

                            # Обновляем cookies после авторизации
                            logger.info(
                                f"🍪 Cookies после авторизации: {len(self.session.cookies)} штук"
                            )

                            # Добавляем дополнительные cookies как в cURL примере
                            self.session.cookies.set("gubun", "on")
                            self.session.cookies.set(
                                "userid", self.settings.autohub_username
                            )

                            # Логируем важные cookies для отладки
                            important_cookies = [
                                "JSESSIONID",
                                "WMONID",
                                "userid",
                                "gubun",
                            ]
                            for cookie_name in important_cookies:
                                if cookie_name in self.session.cookies:
                                    logger.debug(
                                        f"  - {cookie_name}: {self.session.cookies.get(cookie_name)}"
                                    )

                            return True
                        else:
                            error_msg = auth_response.get(
                                "message", "Неизвестная ошибка"
                            )
                            logger.error(f"❌ Авторизация не удалась: {error_msg}")

                            # Если это ошибка с паролем/логином, не повторяем
                            if (
                                "password" in error_msg.lower()
                                or "userid" in error_msg.lower()
                            ):
                                logger.error(
                                    "🚫 Неверный логин или пароль - прекращаем попытки"
                                )
                                return False

                    except Exception as json_error:
                        logger.error(f"Ошибка при парсинге JSON ответа: {json_error}")
                        logger.debug(f"Текст ответа: {response.text[:500]}...")
                else:
                    logger.error(
                        f"❌ Неожиданный статус авторизации: {response.status_code}"
                    )

                    if response.status_code >= 500:
                        logger.warning("🔄 Ошибка сервера, повторим попытку")
                    else:
                        logger.debug(f"Заголовки ответа: {dict(response.headers)}")

            except requests.exceptions.Timeout:
                logger.error(f"⏱️ Таймаут при авторизации (попытка {attempt + 1})")
            except requests.exceptions.ConnectionError as e:
                logger.error(f"🔌 Ошибка соединения при авторизации: {e}")
            except Exception as e:
                logger.error(f"❌ Неожиданная ошибка при авторизации: {e}")

            # Если не последняя попытка, ждем перед повтором
            if attempt < max_retries - 1:
                logger.info(
                    f"⏳ Ожидание {retry_delay} сек перед повторной попыткой..."
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= 1.5  # Увеличиваем задержку с каждой попыткой

        logger.error(f"❌ Не удалось авторизоваться после {max_retries} попыток")
        return False

    async def get_car_list(
        self, params: Optional[Dict[str, Any]] = None
    ) -> AutohubResponse:
        """
        Получает список автомобилей с Autohub

        Args:
            params: Дополнительные параметры для запроса

        Returns:
            AutohubResponse: Ответ с данными об автомобилях
        """
        try:
            logger.info("Начинаем получение списка автомобилей с Autohub")

            # Сначала инициализируем сессию
            session_initialized = await self._initialize_session()
            if not session_initialized:
                return AutohubResponse(
                    success=False,
                    error="Не удалось инициализировать сессию с Autohub",
                    data=[],
                )

            # Выполняем HTTP запрос
            html_content = await self._fetch_html(
                self.settings.autohub_list_url, params
            )

            if not html_content:
                return AutohubResponse(
                    success=False, error="Не удалось получить HTML контент", data=[]
                )

            # Парсим HTML
            cars = self.parser.parse_car_list(html_content)

            logger.info(f"Успешно получено {len(cars)} автомобилей")

            # Если автомобили не найдены, это может быть нормальным результатом
            if len(cars) == 0:
                # Проверяем, действительно ли это проблема с авторизацией
                # Более надежная проверка: ищем явные признаки страницы входа
                if (
                    'location.href="/newfront/user/login/user_login.do"' in html_content
                    or 'alert("로그인이 필요합니다")' in html_content
                    or "<title>로그인</title>" in html_content
                ):
                    return AutohubResponse(
                        success=False,
                        error="Для доступа к списку автомобилей требуется авторизация на сайте Autohub. Используйте endpoint /cars/test для демонстрации функциональности парсера.",
                        total_count=0,
                        data=[],
                    )
                # Если это не проблема авторизации, то просто нет результатов
                logger.info("Список автомобилей пуст, но это не ошибка авторизации")

            # Формируем информацию о пагинации
            current_page = params.get("page", 1) if params else 1
            # Autohub использует фиксированный размер страницы ~10 записей на страницу
            autohub_page_size = 10  # Фактический размер страницы на Autohub
            requested_limit = params.get("limit", 20) if params else 20

            # Пытаемся извлечь общее количество записей из HTML (если есть)
            total_cars_from_page = self._extract_total_count_from_html(html_content)

            # Определяем пагинацию
            total_pages = None
            has_next_page = False
            has_prev_page = current_page > 1

            if total_cars_from_page:
                # Вычисляем общее количество страниц на основе фактического размера страницы Autohub
                total_pages = (
                    total_cars_from_page + autohub_page_size - 1
                ) // autohub_page_size
                has_next_page = current_page < total_pages
                logger.info(
                    f"📊 Пагинация: всего {total_cars_from_page} автомобилей, {total_pages} страниц, текущая {current_page}"
                )
            else:
                # Если не смогли извлечь общее количество, определяем эвристически
                if len(cars) == autohub_page_size:
                    has_next_page = (
                        True  # Если получили полную страницу, скорее всего есть еще
                    )
                logger.info(
                    f"📊 Эвристическая пагинация: получено {len(cars)} автомобилей на странице {current_page}"
                )

            # Логируем результат пагинации
            logger.info(
                f"🔄 Страница {current_page}: {len(cars)} автомобилей, prev={has_prev_page}, next={has_next_page}"
            )

            # Формируем сообщение с информацией о пагинации
            if total_pages:
                message = f"Страница {current_page} из {total_pages}: загружено {len(cars)} автомобилей"
            else:
                message = f"Страница {current_page}: загружено {len(cars)} автомобилей"

            return AutohubResponse(
                success=True,
                data=cars,
                total_count=total_cars_from_page or len(cars),
                page=current_page,
                limit=autohub_page_size,  # Используем фактический размер страницы Autohub
            )

        except Exception as e:
            error_msg = f"Ошибка при получении списка автомобилей: {str(e)}"
            logger.error(error_msg)

            return AutohubResponse(success=False, error=error_msg, data=[])

    async def _fetch_html(
        self, url: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Выполняет HTTP запрос и возвращает HTML контент

        Args:
            url: URL для запроса
            params: Дополнительные параметры (включая пагинацию)

        Returns:
            str: HTML контент или None в случае ошибки
        """
        try:
            # Определяем, это полные параметры поиска или только пагинация
            if params and "i_iNowPageNo" in params:
                # Это уже преобразованные параметры от search_cars
                request_data = params
                logger.info(
                    f"Используем полные параметры поиска: {len(request_data)} параметров"
                )
            else:
                # Это обычный запрос с пагинацией
                request_data = {}

                if params:
                    # Преобразуем наш параметр page в параметр Autohub i_iNowPageNo
                    if "page" in params:
                        request_data["i_iNowPageNo"] = params["page"]
                        logger.info(
                            f"Запрос страницы {params['page']} (i_iNowPageNo={params['page']})"
                        )

                # Если не указана страница, по умолчанию первая
                if "i_iNowPageNo" not in request_data:
                    request_data["i_iNowPageNo"] = 1

            logger.info(f"Выполняем запрос к {url} с {len(request_data)} параметрами")

            # Добавляем случайную задержку для имитации человеческого поведения
            await asyncio.sleep(0.5)

            # Обновляем User-Agent для каждого запроса
            self.session.headers.update({"User-Agent": self.ua.random})

            # Для пагинации Autohub может требоваться POST запрос
            # Проверим, нужно ли использовать POST или GET
            # Если есть много параметров (фильтры), всегда используем POST
            if len(request_data) > 2 or request_data.get("i_iNowPageNo", 1) > 1:
                # Для страниц больше 1 или с фильтрами используем POST
                response = self.session.post(
                    url,
                    data=request_data,
                    timeout=self.settings.request_timeout,
                    allow_redirects=True,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Referer": self.settings.autohub_base_url,
                    },
                )
            else:
                # Для первой страницы используем GET
                response = self.session.get(
                    url,
                    params=request_data,
                    timeout=self.settings.request_timeout,
                    allow_redirects=True,
                )

            # Проверяем статус ответа
            response.raise_for_status()

            # Проверяем кодировку
            if response.encoding is None or response.encoding == "ISO-8859-1":
                response.encoding = "utf-8"

            logger.info(f"Успешно получен ответ. Размер: {len(response.text)} символов")

            # Для отладки сохраняем полученный HTML
            with open("debug_response.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            logger.info("HTML ответ сохранён в debug_response.html для анализа")

            return response.text

        except requests.exceptions.Timeout:
            logger.error(f"Таймаут при запросе к {url}")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Ошибка соединения при запросе к {url}: {e}")
        except requests.exceptions.HTTPError as e:
            logger.error(
                f"HTTP ошибка при запросе к {url}: {e} - Status: {e.response.status_code if e.response else 'Unknown'}"
            )
        except Exception as e:
            logger.error(f"Неожиданная ошибка при запросе к {url}: {e}")

        return None

    async def _fetch_html_simple(self, url: str) -> Optional[str]:
        """
        Выполняет простой GET запрос без параметров (как в рабочем примере)

        Args:
            url: URL для запроса

        Returns:
            str: HTML контент или None в случае ошибки
        """
        try:
            logger.info(f"Выполняем простой GET запрос к {url}")

            # Добавляем случайную задержку для имитации человеческого поведения
            await asyncio.sleep(0.5)

            # Обновляем User-Agent для каждого запроса
            self.session.headers.update({"User-Agent": self.ua.random})

            # Простой GET запрос без параметров
            response = self.session.get(
                url,
                timeout=self.settings.request_timeout,
                allow_redirects=True,
            )

            # Проверяем статус ответа
            response.raise_for_status()

            # Проверяем кодировку
            if response.encoding is None or response.encoding == "ISO-8859-1":
                response.encoding = "utf-8"

            logger.info(f"Успешно получен ответ. Размер: {len(response.text)} символов")

            # Для отладки сохраняем полученный HTML
            with open("debug_response_simple.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            logger.info("HTML ответ сохранён в debug_response_simple.html для анализа")

            return response.text

        except requests.exceptions.Timeout:
            logger.error(f"Таймаут при запросе к {url}")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Ошибка соединения при запросе к {url}: {e}")
        except requests.exceptions.HTTPError as e:
            logger.error(
                f"HTTP ошибка при запросе к {url}: {e} - Status: {e.response.status_code if e.response else 'Unknown'}"
            )
        except Exception as e:
            logger.error(f"Неожиданная ошибка при запросе к {url}: {e}")

        return None

    def _extract_total_count_from_html(self, html_content: str) -> Optional[int]:
        """
        Извлекает общее количество автомобилей из HTML страницы

        Args:
            html_content: HTML контент страницы

        Returns:
            int: Общее количество автомобилей или None если не найдено
        """
        try:
            from bs4 import BeautifulSoup
            import re

            soup = BeautifulSoup(html_content, "html.parser")

            # 1. Ищем специфичный для Autohub элемент "검색결과: 총 1761건"
            search_result_elements = soup.find_all(
                text=re.compile(r"검색결과.*총.*\d+.*건")
            )
            for element in search_result_elements:
                match = re.search(r"총\s*(\d+)\s*건", element)
                if match:
                    total = int(match.group(1))
                    logger.info(f"✅ Найдено общее количество из 검색결과: {total}")
                    return total

            # 2. Ищем в span с классом "text_style7 i_comm_main_txt" (где отображается число записей)
            span_elements = soup.find_all("span", class_="text_style7 i_comm_main_txt")
            for span in span_elements:
                text = span.get_text().strip()
                if text.isdigit():
                    total = int(text)
                    logger.info(f"✅ Найдено общее количество в span: {total}")
                    return total

            # 3. Ищем общий текст с паттерном "총 XXX 건"
            all_text = soup.get_text()
            matches = re.findall(r"총\s*(\d+)\s*건", all_text)
            if matches:
                # Берем наибольшее число (скорее всего общее количество)
                totals = [int(match) for match in matches]
                total = max(totals)
                logger.info(f"✅ Найдено общее количество через regex: {total}")
                return total

            # 4. Ищем паттерн "결과: 총 XXX건"
            result_matches = re.findall(r"결과.*총\s*(\d+)\s*건", all_text)
            if result_matches:
                total = int(result_matches[0])
                logger.info(f"✅ Найдено общее количество в результатах: {total}")
                return total

            # 5. Альтернативные способы поиска
            for pattern in [
                r"전체\s*(\d+)\s*건",
                r"total\s*:\s*(\d+)",
                r"count\s*:\s*(\d+)",
            ]:
                matches = re.findall(pattern, all_text, re.IGNORECASE)
                if matches:
                    total = int(matches[0])
                    logger.info(
                        f"✅ Найдено общее количество через паттерн {pattern}: {total}"
                    )
                    return total

            logger.debug("❌ Общее количество записей не найдено в HTML")
            return None

        except Exception as e:
            logger.error(f"Ошибка при извлечении общего количества из HTML: {e}")
            return None

    def get_test_data(self) -> AutohubResponse:
        """
        Возвращает тестовые данные для проверки API

        Returns:
            AutohubResponse: Тестовые данные
        """
        try:
            # Возвращаем пустые тестовые данные
            return AutohubResponse(
                success=True, data=[], total_count=0, page=1, limit=50
            )

        except Exception as e:
            logger.error(f"Ошибка при загрузке тестовых данных: {e}")
            return AutohubResponse(
                success=False,
                data=[],
                error=f"Ошибка при загрузке тестовых данных: {str(e)}",
                total_count=0,
                page=1,
                limit=50,
            )

    def close(self):
        """Закрывает сессию"""
        if hasattr(self, "_session") and self._session:
            self._session.close()
            self._session = None

    def __del__(self):
        """Деструктор для закрытия сессии"""
        try:
            self.close()
        except AttributeError:
            # Игнорируем ошибки при удалении объекта
            pass

    def get_cars(self, page: int = 1, limit: int = 50) -> AutohubResponse:
        """Получение списка автомобилей"""
        try:
            # URL для получения списка автомобилей
            url = urljoin(self.base_url, "/newfront/receive/rc/receive_rc_list.do")

            # Базовые параметры запроса
            data = {"page": page, "limit": limit, "sort": "entry_date desc"}

            logger.info(f"Запрос к Autohub: {url} с параметрами {data}")

            response = self.session.get(
                url, params=data, timeout=self.settings.request_timeout
            )
            response.raise_for_status()

            # Пока что возвращаем пустой список, так как парсинг списка автомобилей
            # не реализован в новой архитектуре
            cars = []

            return AutohubResponse(
                success=True, data=cars, total_count=len(cars), page=page, limit=limit
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка HTTP запроса к Autohub: {e}")
            return AutohubResponse(
                success=False,
                data=[],
                error=f"Ошибка подключения к серверу: {str(e)}",
                total_count=0,
                page=page,
                limit=limit,
            )
        except Exception as e:
            logger.error(f"Неожиданная ошибка в get_cars: {e}")
            return AutohubResponse(
                success=False,
                data=[],
                error=f"Внутренняя ошибка сервера: {str(e)}",
                total_count=0,
                page=page,
                limit=limit,
            )

    def get_car_detail(
        self, request_params: AutohubCarDetailRequest
    ) -> AutohubCarDetailResponse:
        """Получение детальной информации об автомобиле"""
        try:
            # URL для получения детальной информации
            url = urljoin(
                self.base_url, "/newfront/onlineAuc/on/onlineAuc_on_detail.do"
            )

            # Подготовка данных запроса на основе параметров
            # Используем формат данных из рабочего примера
            data = {
                "i_iNowPageNo": str(request_params.page_number),
                "i_sReturnUrl": "/newfront/receive/rc/receive_rc_list.do",
                "i_sReturnParam": "",
                "i_sActionFlag": "",
                "i_sReceiveCd": "",
                "pageFlag": "Y",
                "i_sAucNo": request_params.auction_number,
                "i_sStartDt": request_params.auction_date,
                "i_sAucTitle": request_params.auction_title,
                "i_sAucCode": request_params.auction_code,
                "i_sSortFlag": request_params.sort_flag,
                "i_sMainModel": "",
                "i_sMakerCodeD": "",
                "i_sCarName1CodeD": "",
                "tabActiveIdx": "",
                "listTabActiveIdx": "",
                "receivecd": request_params.receive_code,
                "i_sAucNoTempStr": "",
                "i_sMakerCodeD1": "",
                "i_sCarName1CodeD1": "",
                "i_sAucNoTemp1": f"{request_params.auction_number}@@{request_params.auction_date}@@{request_params.auction_code}",
                "i_entryNoYn": "ALL",
                "i_parkingNoYn": "Y",
                "noSelect": "E",
                "i_sNo": "",
                "i_sMakerCode": "",
                "i_sCarName1Code": "",
                "i_sCarName2Code": "",
                "i_sCarName3Code": "",
                "i_sFueltypecode": "",
                "i_bojeongYn": "ALL",
                "i_sCarYearStr": "",
                "i_sCarYearEnd": "",
                "i_sDriveKmShortDescStr": "",
                "i_sDriveKmShortDescEnd": "",
                "i_sPricecStr": "",
                "i_sPricecEnd": "",
                "i_sAucResult": "",
                "i_sAucLane": "",
                "i_sEntryNo": "",
                "i_sParkingNo": "",
                "i_entryNoYn0": "ALL",
                "i_parkingNoYn0": "Y",
                "i_sAucNoTemp2": f"{request_params.auction_number}@@{request_params.auction_date}@@{request_params.auction_code}",
                "i_sohYn": "ALL",
                "entrySort": request_params.sort_flag,
                "i_iPageSize": str(request_params.page_size),
            }

            # Добавляем необходимые headers для корректной работы
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
                "Cache-Control": "max-age=0",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://www.autohubauction.co.kr",
                "Referer": "https://www.autohubauction.co.kr/newfront/receive/rc/receive_rc_list.do",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            }

            logger.info(f"POST запрос к Autohub detail: {url}")
            logger.debug(f"Параметры запроса: {data}")

            response = self.session.post(
                url, data=data, headers=headers, timeout=self.settings.request_timeout
            )
            response.raise_for_status()

            # Сохраняем HTML для отладки
            with open("debug_car_detail_response.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            logger.info(
                f"HTML ответ сохранён в debug_car_detail_response.html для анализа"
            )

            # Парсинг детальной информации
            car_detail = parse_car_detail(response.text)

            if car_detail:
                # Добавляем схему деталей автомобиля
                try:
                    from bs4 import BeautifulSoup

                    soup = BeautifulSoup(response.text, "html.parser")
                    car_diagram = parse_car_diagram(soup)

                    if car_diagram:
                        # Создаем расширенный объект с схемой деталей
                        from app.models.autohub import AutohubCarDetailExtended

                        extended_detail = AutohubCarDetailExtended(
                            **car_detail.dict(), car_diagram=car_diagram
                        )
                        logger.info(
                            f"✅ Схема деталей добавлена: {car_diagram.total_parts} частей"
                        )

                        return AutohubCarDetailResponse(
                            success=True,
                            data=extended_detail,
                            request_params=request_params,
                        )
                    else:
                        logger.warning(
                            "Схема деталей не найдена, возвращаем базовые данные"
                        )
                except Exception as e:
                    logger.error(f"Ошибка при добавлении схемы деталей: {e}")

                return AutohubCarDetailResponse(
                    success=True, data=car_detail, request_params=request_params
                )
            else:
                return AutohubCarDetailResponse(
                    success=False,
                    error="Не удалось извлечь информацию об автомобиле из ответа",
                    request_params=request_params,
                )

        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка HTTP запроса к Autohub detail: {e}")
            return AutohubCarDetailResponse(
                success=False,
                error=f"Ошибка подключения к серверу: {str(e)}",
                request_params=request_params,
            )
        except Exception as e:
            logger.error(f"Неожиданная ошибка в get_car_detail: {e}")
            return AutohubCarDetailResponse(
                success=False,
                error=f"Внутренняя ошибка сервера: {str(e)}",
                request_params=request_params,
            )

    def set_auth_cookies(self, cookies: dict):
        """Установка cookies для аутентификации"""
        self.session.cookies.update(cookies)
        logger.info("Установлены cookies для аутентификации в Autohub")

    async def search_cars(self, search_params: AutohubSearchRequest) -> AutohubResponse:
        """
        Расширенный поиск автомобилей с фильтрами

        Args:
            search_params: Параметры поиска и фильтрации

        Returns:
            AutohubResponse: Ответ с найденными автомобилями
        """
        try:
            logger.info("Начинаем расширенный поиск автомобилей с фильтрами")

            # Инициализируем сессию (ВАЖНО: делаем это перед любыми запросами)
            session_initialized = await self._initialize_session()
            if not session_initialized:
                logger.error("❌ Ошибка инициализации сессии Autohub")
                return AutohubResponse(
                    success=False,
                    error="Не удалось инициализировать сессию с Autohub. Проверьте настройки авторизации.",
                    data=[],
                )

            logger.info("✅ Сессия успешно инициализирована")

            # Check if this is a simple request without filters
            has_filters = (
                search_params.manufacturer_code
                or search_params.model_code
                or search_params.generation_code
                or search_params.fuel_type
                or search_params.year_from
                or search_params.year_to
                or search_params.mileage_from
                or search_params.mileage_to
                or search_params.price_from
                or search_params.price_to
                or search_params.auction_result
                or search_params.lane
                or search_params.search_number
                or search_params.entry_number
                or search_params.parking_number
            )

            # Get current auction session info only if not already provided
            if (
                not search_params.auction_code
                or not search_params.auction_no
                or not search_params.auction_date
            ):
                logger.info("📋 Получаем информацию о текущей сессии аукциона")
                sessions_response = await self.get_auction_sessions()
                if sessions_response.success and sessions_response.current_session:
                    current_session = sessions_response.current_session
                    # Only set auction info if not already set
                    if not search_params.auction_code:
                        search_params.auction_code = current_session.auction_code
                    if not search_params.auction_no:
                        search_params.auction_no = current_session.auction_no
                    if not search_params.auction_date:
                        search_params.auction_date = current_session.auction_date
                    logger.info(
                        f"📍 Используем сессию аукциона: код={current_session.auction_code}, номер={current_session.auction_no}, дата={current_session.auction_date}"
                    )
                else:
                    logger.warning(
                        "⚠️ Не удалось получить информацию о текущей сессии аукциона"
                    )
                    # Use empty auction params if we can't get session info
                    # This allows search to work without auction-specific filtering
                    logger.info(
                        "📍 Используем поиск без привязки к конкретному аукциону"
                    )

            # Подготавливаем параметры для POST запроса к Autohub
            # ИСПРАВЛЕНО: Используем правильные поля как в рабочих cURL примерах
            # i_sMakerCode - код производителя
            # i_sCarName1Code - код модели
            # i_sCarName2Code - код поколения
            # i_sCarName3Code - код детализации/конфигурации

            # Форматируем auction temp параметр
            auction_temp_value = ""
            if search_params.auction_no and search_params.auction_date and search_params.auction_code:
                auction_temp_value = f"{search_params.auction_no}@@{search_params.auction_date}@@{search_params.auction_code}"

            post_data = {
                "i_iNowPageNo": str(search_params.page),
                "i_sReturnUrl": "/newfront/receive/rc/receive_rc_list.do",
                "i_sReturnParam": "",
                "i_sActionFlag": "",
                "i_sReceiveCd": "",
                "pageFlag": "Y",
                "i_sAucNo": search_params.auction_no or "",
                "i_sStartDt": search_params.auction_date or "",
                "i_sAucTitle": search_params.auction_title or "",
                "i_sAucCode": search_params.auction_code or "",
                "i_sSortFlag": "entry",
                "i_sMainModel": "",
                # Очищаем поля для Tab 1 (не используем)
                "i_sMakerCodeD": "",
                "i_sCarName1CodeD": "",
                # ИСПРАВЛЕНО: Tab index должен быть "2" для фильтрации (как в рабочих примерах)
                "tabActiveIdx": "2",
                "listTabActiveIdx": "1",
                "receivecd": "",
                # Название аукциона
                "i_sAucNoTempStr": search_params.auction_title or "",
                # Удалены дубликаты полей (не нужны для Tab 2)
                "i_sCarName1CodeD1": "",
                # Форматированный параметр аукциона
                "i_sAucNoTemp2": auction_temp_value,
                "i_entryNoYn": "ALL",
                "i_parkingNoYn": "Y",
                "noSelect": "E",
                "i_sNo": "",
                # ИСПРАВЛЕНО: Основные поля фильтров (как в рабочих cURL примерах)
                "i_sMakerCode": search_params.manufacturer_code or "",
                "i_sCarName1Code": search_params.model_code or "",
                # Поколение и детализация
                "i_sCarName2Code": search_params.generation_code or "",
                "i_sCarName3Code": search_params.detail_code or "",
                "i_sFueltypecode": (
                    search_params.fuel_type.value if search_params.fuel_type else ""
                ),
                "i_bojeongYn": (
                    search_params.extended_warranty.value
                    if search_params.extended_warranty
                    else "ALL"
                ),
                "i_sCarYearStr": (
                    str(search_params.year_from) if search_params.year_from else ""
                ),
                "i_sCarYearEnd": (
                    str(search_params.year_to) if search_params.year_to else ""
                ),
                "i_sDriveKmShortDescStr": (
                    str(search_params.mileage_from)
                    if search_params.mileage_from
                    else ""
                ),
                "i_sDriveKmShortDescEnd": (
                    str(search_params.mileage_to) if search_params.mileage_to else ""
                ),
                "i_sPricecStr": (
                    str(search_params.price_from) if search_params.price_from else ""
                ),
                "i_sPricecEnd": (
                    str(search_params.price_to) if search_params.price_to else ""
                ),
                "i_sAucResult": (
                    search_params.auction_result.value
                    if search_params.auction_result
                    else ""
                ),
                "i_sAucLane": search_params.lane.value if search_params.lane else "",
                "i_sEntryNo": search_params.entry_number or "",
                "i_sParkingNo": search_params.parking_number or "",
                "i_entryNoYn0": "Y" if search_params.entry_number else "ALL",
                "i_parkingNoYn0": "Y" if search_params.parking_number else "Y",
                "i_sAucNoTemp2": "",
                "i_sohYn": (
                    search_params.soh_diagnosis.value
                    if search_params.soh_diagnosis
                    else "ALL"
                ),
                "entrySort": "entry",
                "i_iPageSize": str(search_params.page_size),
            }

            # Логируем ключевые параметры
            logger.info(f"📊 Параметры поиска Autohub:")
            logger.info(f"  - Страница: {search_params.page}")
            logger.info(
                f"  - Производитель: {search_params.manufacturer_code or 'Все'}"
            )
            logger.info(f"  - Модель: {search_params.model_code or 'Все'}")
            logger.info(f"  - Поколение: {search_params.generation_code or 'Все'}")

            # Для первой страницы без фильтров используем простой GET
            if search_params.page == 1 and not has_filters:
                logger.info(
                    "🔍 Выполняем простой GET запрос к Autohub (первая страница без фильтров)"
                )
                html_content = await self._fetch_html_simple(
                    self.settings.autohub_list_url
                )
            else:
                # Выполняем POST запрос с параметрами
                logger.info("🔍 Выполняем POST запрос к Autohub с фильтрами")

                # Логируем важные параметры для отладки
                logger.debug(f"POST параметры:")
                for key, value in post_data.items():
                    if value:  # Только непустые значения
                        logger.debug(f"  {key}: {value}")

                html_content = await self._fetch_html(
                    self.settings.autohub_list_url, params=post_data
                )

            if not html_content:
                logger.error("❌ Не удалось получить HTML контент от Autohub")
                return AutohubResponse(
                    success=False,
                    error="Не удалось получить данные от Autohub. Сервер не отвечает.",
                    data=[],
                )

            # Для отладки сохраняем полученный HTML
            debug_filename = "debug_search_response.html"
            if has_filters:
                debug_filename = "debug_search_response_filtered.html"
            with open(debug_filename, "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info(f"HTML ответ сохранён в {debug_filename} для анализа")

            # Проверяем размер HTML для отладки
            html_size = len(html_content)
            logger.info(f"📏 Размер HTML ответа: {html_size} символов")

            # Проверяем наличие маркеров контента
            has_tbody = "tbody" in html_content
            has_car_info = "carInfo" in html_content
            has_no_results = (
                "검색결과가 없습니다" in html_content
                or "조회된 데이터가 없습니다" in html_content
            )

            logger.info(
                f"🔍 Маркеры контента: tbody={has_tbody}, carInfo={has_car_info}, no_results={has_no_results}"
            )

            # Парсим результаты
            cars = self.parser.parse_car_list(html_content)

            logger.info(f"🚗 Найдено {len(cars)} автомобилей")

            # Если автомобили не найдены, но есть маркеры контента, логируем предупреждение
            if len(cars) == 0 and has_tbody and has_car_info and not has_no_results:
                logger.warning(
                    "⚠️ Парсер не смог извлечь автомобили, хотя HTML содержит данные"
                )

            # Поскольку мы теперь отправляем фильтры напрямую в Autohub,
            # клиентская фильтрация больше не нужна
            # Autohub уже вернул отфильтрованные результаты

            # Сохраняем общее количество
            total_filtered_count = len(cars)

            # Пагинация уже применена на стороне Autohub
            # Мы отправили номер страницы и размер в POST запросе
            logger.info(
                f"🚗 Получено {len(cars)} автомобилей на странице {search_params.page}"
            )

            # Если автомобили не найдены, это может быть нормальным результатом поиска
            if len(cars) == 0:
                # Проверяем, действительно ли это проблема с авторизацией
                # Более надежная проверка: ищем явные признаки страницы входа
                if (
                    'location.href="/newfront/user/login/user_login.do"' in html_content
                    or 'alert("로그인이 필요합니다")' in html_content
                    or "<title>로그인</title>" in html_content
                ):
                    logger.error("❌ Обнаружена страница входа - требуется авторизация")
                    return AutohubResponse(
                        success=False,
                        error="Требуется авторизация на сайте Autohub. Проверьте логин и пароль.",
                        total_count=0,
                        data=[],
                    )

                # Проверяем наличие сообщения "нет результатов"
                if (
                    "검색결과가 없습니다" in html_content
                    or "조회된 데이터가 없습니다" in html_content
                    or "no results" in html_content.lower()
                ):
                    logger.info("ℹ️ Поиск не вернул результатов (сообщение от Autohub)")
                else:
                    logger.warning("⚠️ Пустой результат без явного сообщения")

                # Сохраним HTML для отладки
                try:
                    with open(
                        "debug_empty_search_result.html", "w", encoding="utf-8"
                    ) as f:
                        f.write(html_content)
                    logger.debug(
                        "📄 HTML с пустым результатом сохранен в debug_empty_search_result.html"
                    )

                    # Логируем первые 500 символов HTML для быстрой диагностики
                    logger.debug(f"📋 Начало HTML ответа: {html_content[:500]}...")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось сохранить HTML для отладки: {e}")

            # Пытаемся извлечь общее количество записей
            total_count = self._extract_total_count_from_html(html_content)
            if total_count:
                logger.info(
                    f"📊 Общее количество автомобилей в результатах: {total_count}"
                )
            else:
                logger.info("📊 Не удалось определить общее количество автомобилей")

            # Используем общее количество из HTML или количество найденных автомобилей
            final_total_count = total_count or total_filtered_count

            return AutohubResponse(
                success=True,
                data=cars,
                total_count=final_total_count,
                page=search_params.page,
                limit=search_params.page_size,
            )

        except Exception as e:
            error_msg = f"Ошибка при поиске автомобилей: {str(e)}"
            logger.error(error_msg)
            return AutohubResponse(success=False, error=error_msg, data=[])

    def get_manufacturers(self) -> AutohubManufacturersResponse:
        """
        Получает список производителей

        Returns:
            AutohubManufacturersResponse: Список производителей
        """
        try:
            logger.info("Получение списка производителей AutoHub")

            return AutohubManufacturersResponse(
                success=True,
                message="Список производителей получен успешно",
                manufacturers=AUTOHUB_MANUFACTURERS,
                total_count=len(AUTOHUB_MANUFACTURERS),
            )

        except Exception as e:
            logger.error(f"Ошибка при получении производителей: {e}")
            return AutohubManufacturersResponse(
                success=False,
                message=f"Ошибка: {str(e)}",
                manufacturers=[],
                total_count=0,
            )

    async def get_models(self, manufacturer_code: str) -> AutohubModelsResponse:
        """
        Получает список моделей для производителя

        Args:
            manufacturer_code: Код производителя

        Returns:
            AutohubModelsResponse: Список моделей
        """
        # Check cache (24h TTL for static metadata)
        cache_key = self._make_cache_key("models", {"mfr": manufacturer_code})
        cached = self._get_from_cache(cache_key, ttl=86400)
        if cached is not None:
            logger.debug(f"📦 Autohub models cache hit for {manufacturer_code}")
            return cached

        try:
            logger.info(f"Получение моделей для производителя {manufacturer_code}")

            # Инициализируем сессию если нужно
            if not hasattr(self, "_session") or self._session is None:
                logger.info("Инициализация сессии для получения моделей")
                session_initialized = await self._initialize_session()
                if not session_initialized:
                    logger.error(
                        "Не удалось инициализировать сессию для получения моделей"
                    )
                    return AutohubModelsResponse(
                        success=False,
                        message="Ошибка инициализации сессии",
                        models=[],
                        manufacturer_code=manufacturer_code,
                        total_count=0,
                    )

            # Получаем текущую сессию аукциона для кода аукциона
            sessions_response = await self.get_auction_sessions()
            
            # Use the generated auction code from the current session
            if sessions_response.success and sessions_response.current_session:
                auction_code = sessions_response.current_session.auction_code
                logger.info(f"✅ Using auction code from current session: {auction_code}")
            else:
                # Fallback: generate auction code based on current logic
                auction_date = self._get_current_auction_date()
                auction_code = self._generate_auction_code(auction_date)
                logger.warning(f"⚠️ Using generated auction code: {auction_code}")

            # Подготавливаем данные для запроса
            # Пробуем разные варианты параметров для отладки
            data = {
                "i_sType": "mdl",
                "i_sAucCode": auction_code,
                "i_sMakerCode": manufacturer_code,
                "isMultiInit": "false",
            }

            # Альтернативный набор параметров (как в старой версии)
            alt_data = {
                "i_sMakerCode": manufacturer_code,
                "mode": "maker",
            }

            # Логируем оба варианта
            logger.info(f"Основные параметры запроса: {data}")
            logger.info(f"Альтернативные параметры: {alt_data}")

            # Заголовки для AJAX запроса
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.settings.autohub_list_url,
            }

            # Выполняем запрос
            url = urljoin(self.base_url, "/comm/comm_Ajcarmodel_ajax.do")
            logger.info(f"Запрос моделей: {url} с параметрами {data}")
            logger.debug(f"Заголовки запроса: {headers}")
            logger.debug(f"Cookies сессии: {self.session.cookies.get_dict()}")

            # Дополнительное логирование для отладки
            logger.info(f"=== Отладка запроса моделей для {manufacturer_code} ===")
            logger.info(f"URL: {url}")
            logger.info(f"Метод: POST")
            logger.info(f"Данные: {data}")
            logger.info(
                f"Cookies: JSESSIONID={self.session.cookies.get('JSESSIONID', 'НЕТ')}, WMONID={self.session.cookies.get('WMONID', 'НЕТ')}"
            )
            logger.info(f"User-Agent: {headers.get('User-Agent', 'НЕТ')}")
            logger.info(f"Referer: {headers.get('Referer', 'НЕТ')}")

            response = self.session.post(
                url,
                data=data,
                headers=headers,
                timeout=self.settings.request_timeout,
            )
            logger.info(f"Статус ответа: {response.status_code}")
            response.raise_for_status()

            # Парсим JSON ответ
            try:
                response_data = response.json()
                logger.info(f"Получен ответ с моделями: {response_data.get('status')}")
                logger.debug(f"Полный ответ API: {response_data}")

                # Сохраняем сырой ответ в файл для отладки
                import os
                from datetime import datetime

                debug_dir = "logs/autohub_debug"
                os.makedirs(debug_dir, exist_ok=True)

                debug_filename = f"{debug_dir}/models_response_{manufacturer_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

                try:
                    with open(debug_filename, "w", encoding="utf-8") as f:
                        json.dump(
                            {
                                "request_info": {
                                    "manufacturer_code": manufacturer_code,
                                    "url": url,
                                    "method": "POST",
                                    "headers": dict(response.request.headers),
                                    "data": data,
                                    "cookies": self.session.cookies.get_dict(),
                                    "timestamp": datetime.now().isoformat(),
                                },
                                "response_info": {
                                    "status_code": response.status_code,
                                    "headers": dict(response.headers),
                                    "raw_data": response_data,
                                    "raw_text": (
                                        response.text
                                        if len(response.text) < 10000
                                        else response.text[:10000] + "... (truncated)"
                                    ),
                                },
                            },
                            f,
                            ensure_ascii=False,
                            indent=2,
                        )
                    logger.info(f"Сохранен отладочный файл: {debug_filename}")
                except Exception as e:
                    logger.error(f"Не удалось сохранить отладочный файл: {e}")

            except json.JSONDecodeError as e:
                logger.error(f"Ошибка парсинга JSON ответа: {e}")
                logger.error(f"Текст ответа: {response.text[:500]}")
                return AutohubModelsResponse(
                    success=False,
                    message="Ошибка парсинга ответа от сервера",
                    models=[],
                    manufacturer_code=manufacturer_code,
                    total_count=0,
                )

            if response_data.get("status") == "succ":
                # Преобразуем данные в наш формат
                models = []
                raw_models = response_data.get("object", [])
                logger.info(
                    f"API вернул {len(raw_models)} моделей для {manufacturer_code}"
                )

                # Логируем первые несколько моделей для отладки
                if raw_models:
                    logger.debug(
                        f"Пример модели: {raw_models[0] if raw_models else 'Нет данных'}"
                    )

                for item in raw_models:
                    model = AutohubModel(
                        manufacturer_code=manufacturer_code,
                        model_code=item.get("carname1code", ""),
                        name=item.get("carname1name", ""),
                    )
                    models.append(model)

                logger.info(
                    f"Успешно получено {len(models)} моделей для {manufacturer_code}"
                )

                # Дополнительная проверка для пустого ответа
                if len(models) == 0:
                    logger.warning(
                        f"API вернул успешный статус, но список моделей пуст для {manufacturer_code}"
                    )
                    logger.debug(f"Полный ответ API для отладки: {response_data}")

                    # Пробуем альтернативный подход с другими параметрами
                    logger.info(
                        "Пробуем альтернативный запрос с параметрами mode=maker"
                    )

                    try:
                        alt_response = self.session.post(
                            url,
                            data=alt_data,
                            headers=headers,
                            timeout=self.settings.request_timeout,
                        )
                        alt_response.raise_for_status()

                        alt_response_data = alt_response.json()
                        if alt_response_data.get("status") == "succ":
                            alt_raw_models = alt_response_data.get("object", [])
                            logger.info(
                                f"Альтернативный запрос вернул {len(alt_raw_models)} моделей"
                            )

                            if alt_raw_models:
                                models = []
                                for item in alt_raw_models:
                                    model = AutohubModel(
                                        manufacturer_code=manufacturer_code,
                                        model_code=item.get("carname1code", ""),
                                        name=item.get("carname1name", ""),
                                    )
                                    models.append(model)
                                logger.info(
                                    f"Успешно получено {len(models)} моделей через альтернативный метод"
                                )
                    except Exception as e:
                        logger.error(f"Ошибка при альтернативном запросе: {e}")

                    # Если все способы не сработали, используем резервные данные
                    if len(models) == 0:
                        logger.warning(
                            "Используем резервные статические данные для моделей"
                        )
                        models = self._get_fallback_models(manufacturer_code)
                        if models:
                            logger.info(
                                f"Загружено {len(models)} моделей из резервных данных"
                            )

                result = AutohubModelsResponse(
                    success=True,
                    message=f"Список моделей для {manufacturer_code} получен успешно",
                    models=models,
                    manufacturer_code=manufacturer_code,
                    total_count=len(models),
                )
                if models:
                    self._save_to_cache(cache_key, result)
                return result
            else:
                logger.error(f"Ошибка от API: {response_data.get('message')}")
                return AutohubModelsResponse(
                    success=False,
                    message=response_data.get("message", "Неизвестная ошибка"),
                    models=[],
                    manufacturer_code=manufacturer_code,
                    total_count=0,
                )

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP ошибка при получении моделей: {e}")
            # Пытаемся использовать резервные данные
            fallback_models = self._get_fallback_models(manufacturer_code)
            if fallback_models:
                logger.warning(
                    f"Используем резервные данные из-за ошибки сети: {len(fallback_models)} моделей"
                )
                return AutohubModelsResponse(
                    success=True,
                    message=f"Список моделей для {manufacturer_code} получен из резервных данных",
                    models=fallback_models,
                    manufacturer_code=manufacturer_code,
                    total_count=len(fallback_models),
                )
            return AutohubModelsResponse(
                success=False,
                message=f"Ошибка соединения: {str(e)}",
                models=[],
                manufacturer_code=manufacturer_code,
                total_count=0,
            )
        except Exception as e:
            logger.error(f"Ошибка при получении моделей: {e}")
            # Пытаемся использовать резервные данные
            fallback_models = self._get_fallback_models(manufacturer_code)
            if fallback_models:
                logger.warning(
                    f"Используем резервные данные из-за ошибки: {len(fallback_models)} моделей"
                )
                return AutohubModelsResponse(
                    success=True,
                    message=f"Список моделей для {manufacturer_code} получен из резервных данных",
                    models=fallback_models,
                    manufacturer_code=manufacturer_code,
                    total_count=len(fallback_models),
                )
            return AutohubModelsResponse(
                success=False,
                message=f"Ошибка: {str(e)}",
                models=[],
                manufacturer_code=manufacturer_code,
                total_count=0,
            )

    def _get_fallback_models(self, manufacturer_code: str) -> List[AutohubModel]:
        """
        Возвращает статический список моделей для производителя в качестве резервного варианта

        Args:
            manufacturer_code: Код производителя

        Returns:
            List[AutohubModel]: Список моделей
        """
        # Статические данные для основных производителей
        fallback_models = {
            "KA": [  # Kia
                AutohubModel(manufacturer_code="KA", model_code="KA01", name="K3"),
                AutohubModel(manufacturer_code="KA", model_code="KA02", name="K5"),
                AutohubModel(manufacturer_code="KA", model_code="KA03", name="K7"),
                AutohubModel(manufacturer_code="KA", model_code="KA04", name="K8"),
                AutohubModel(manufacturer_code="KA", model_code="KA05", name="K9"),
                AutohubModel(
                    manufacturer_code="KA", model_code="KA06", name="스포티지"
                ),
                AutohubModel(manufacturer_code="KA", model_code="KA07", name="쏘렌토"),
                AutohubModel(manufacturer_code="KA", model_code="KA08", name="카니발"),
                AutohubModel(manufacturer_code="KA", model_code="KA09", name="셀토스"),
                AutohubModel(manufacturer_code="KA", model_code="KA10", name="모하비"),
                AutohubModel(manufacturer_code="KA", model_code="KA11", name="니로"),
                AutohubModel(manufacturer_code="KA", model_code="KA12", name="EV6"),
                AutohubModel(manufacturer_code="KA", model_code="KA13", name="EV9"),
            ],
            "HD": [  # Hyundai
                AutohubModel(manufacturer_code="HD", model_code="HD01", name="아반떼"),
                AutohubModel(manufacturer_code="HD", model_code="HD02", name="쏘나타"),
                AutohubModel(manufacturer_code="HD", model_code="HD03", name="그랜저"),
                AutohubModel(manufacturer_code="HD", model_code="HD04", name="투싼"),
                AutohubModel(manufacturer_code="HD", model_code="HD05", name="싼타페"),
                AutohubModel(
                    manufacturer_code="HD", model_code="HD06", name="팰리세이드"
                ),
                AutohubModel(manufacturer_code="HD", model_code="HD07", name="코나"),
                AutohubModel(manufacturer_code="HD", model_code="HD08", name="베뉴"),
                AutohubModel(
                    manufacturer_code="HD", model_code="HD09", name="아이오닉5"
                ),
                AutohubModel(
                    manufacturer_code="HD", model_code="HD10", name="아이오닉6"
                ),
            ],
            "GN": [  # Genesis
                AutohubModel(manufacturer_code="GN", model_code="GN01", name="G70"),
                AutohubModel(manufacturer_code="GN", model_code="GN02", name="G80"),
                AutohubModel(manufacturer_code="GN", model_code="GN03", name="G90"),
                AutohubModel(manufacturer_code="GN", model_code="GN04", name="GV60"),
                AutohubModel(manufacturer_code="GN", model_code="GN05", name="GV70"),
                AutohubModel(manufacturer_code="GN", model_code="GN06", name="GV80"),
                AutohubModel(manufacturer_code="GN", model_code="GN07", name="GV90"),
            ],
        }

        return fallback_models.get(manufacturer_code, [])

    async def get_generations(self, model_code: str) -> AutohubGenerationsResponse:
        """
        Получает список поколений для модели

        Примечание: Большинство моделей в системе Autohub не имеют поколений.
        Это нормальное поведение, и UI автоматически скрывает выбор поколений
        когда они недоступны.

        Args:
            model_code: Код модели

        Returns:
            AutohubGenerationsResponse: Список поколений (часто пустой)
        """
        # Check cache (24h TTL for static metadata)
        cache_key = self._make_cache_key("generations", {"model": model_code})
        cached = self._get_from_cache(cache_key, ttl=86400)
        if cached is not None:
            logger.debug(f"📦 Autohub generations cache hit for {model_code}")
            return cached

        try:
            logger.info(f"Получение поколений для модели {model_code}")

            # Инициализируем сессию если нужно
            if not self.session:
                session_initialized = await self._initialize_session()
                if not session_initialized:
                    logger.error(
                        "Не удалось инициализировать сессию для получения поколений"
                    )
                    return AutohubGenerationsResponse(
                        success=False,
                        message="Ошибка инициализации сессии",
                        generations=[],
                        model_code=model_code,
                        total_count=0,
                    )

            # Получаем текущую сессию аукциона для кода аукциона
            sessions_response = await self.get_auction_sessions()

            # Use the generated auction code from the current session
            if sessions_response.success and sessions_response.current_session:
                auction_code = sessions_response.current_session.auction_code
                logger.info(
                    f"✅ Используется код аукциона из текущей сессии: {auction_code}"
                )
            else:
                # Fallback: generate auction code based on current logic
                auction_date = self._get_current_auction_date()
                auction_code = self._generate_auction_code(auction_date)
                logger.warning(
                    f"⚠️ Используется сгенерированный код аукциона: {auction_code}"
                )

            # Нам нужен код производителя для запроса поколений
            # Предполагаем, что код модели содержит код производителя (например, HD03 -> HD)
            manufacturer_code = model_code[:2] if len(model_code) >= 2 else ""

            # Подготавливаем данные для запроса
            data = {
                "i_sType": "clsHead",
                "i_sAucCode": auction_code,
                "i_sMakerCode": manufacturer_code,
                "i_sCarName1Code": model_code,
                "isMultiInit": "false",
            }

            # Заголовки для AJAX запроса
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": "https://www.autohubauction.co.kr",
                "Referer": self.settings.autohub_list_url,
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }

            # Добавляем cookies из рабочего примера если их нет
            if not self.session.cookies.get("userid"):
                logger.info("Добавляем рабочие cookies в сессию")
                working_cookies = {
                    "gubun": "on",
                    "userid": "785701",
                    "notToday_PU202506260001": "Y",
                    "notToday_PU202507100004": "Y",
                }
                for key, value in working_cookies.items():
                    self.session.cookies.set(key, value)

            # Выполняем запрос
            url = urljoin(self.base_url, "/comm/comm_Ajcarmodel_ajax.do")
            logger.info(f"Запрос поколений: {url} с параметрами {data}")

            # Дополнительное логирование для отладки
            logger.info(f"=== Отладка запроса поколений для {model_code} ===")
            logger.info(f"URL: {url}")
            logger.info(f"Метод: POST")
            logger.info(f"Данные: {data}")
            logger.info(
                f"Cookies: JSESSIONID={self.session.cookies.get('JSESSIONID', 'НЕТ')}, WMONID={self.session.cookies.get('WMONID', 'НЕТ')}"
            )

            response = self.session.post(
                url,
                data=data,
                headers=headers,
                timeout=self.settings.request_timeout,
            )
            logger.info(f"Статус ответа: {response.status_code}")
            response.raise_for_status()

            # Парсим JSON ответ
            try:
                response_data = response.json()
                logger.info(
                    f"Получен ответ с поколениями: {response_data.get('status')}"
                )
                logger.debug(f"Полный ответ: {response_data}")

                # Сохраняем сырой ответ в файл для отладки
                import os
                from datetime import datetime

                debug_dir = "logs/autohub_debug"
                os.makedirs(debug_dir, exist_ok=True)

                debug_filename = f"{debug_dir}/generations_response_{model_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

                try:
                    with open(debug_filename, "w", encoding="utf-8") as f:
                        json.dump(
                            {
                                "request_info": {
                                    "model_code": model_code,
                                    "manufacturer_code": manufacturer_code,
                                    "url": url,
                                    "method": "POST",
                                    "headers": dict(response.request.headers),
                                    "data": data,
                                    "cookies": self.session.cookies.get_dict(),
                                    "timestamp": datetime.now().isoformat(),
                                },
                                "response_info": {
                                    "status_code": response.status_code,
                                    "headers": dict(response.headers),
                                    "raw_data": response_data,
                                    "raw_text": (
                                        response.text
                                        if len(response.text) < 10000
                                        else response.text[:10000] + "... (truncated)"
                                    ),
                                },
                            },
                            f,
                            ensure_ascii=False,
                            indent=2,
                        )
                    logger.info(f"Сохранен отладочный файл: {debug_filename}")
                except Exception as e:
                    logger.error(f"Не удалось сохранить отладочный файл: {e}")

            except json.JSONDecodeError as e:
                logger.error(f"Ошибка парсинга JSON ответа: {e}")
                logger.error(f"Текст ответа: {response.text[:500]}")
                return AutohubGenerationsResponse(
                    success=False,
                    message="Ошибка парсинга ответа от сервера",
                    generations=[],
                    model_code=model_code,
                    total_count=0,
                )

            if response_data.get("status") == "succ":
                # Проверяем наличие поля object
                if "object" not in response_data:
                    logger.info(
                        f"API вернул успех, но без данных поколений для {model_code} - это ожидаемое поведение для большинства моделей Autohub"
                    )
                    # Возвращаем пустой успешный ответ - для большинства моделей Autohub поколения недоступны
                    return AutohubGenerationsResponse(
                        success=True,
                        message=f"Для модели {model_code} поколения не найдены",
                        generations=[],
                        model_code=model_code,
                        total_count=0,
                    )

                # Преобразуем данные в наш формат
                generations = []
                for item in response_data.get("object", []):
                    generation = AutohubGeneration(
                        model_code=model_code,
                        generation_code=item.get("carname2code", ""),
                        detail_code="",  # Будет заполнено при выборе конфигурации
                        name=item.get("carname2name", ""),
                    )
                    generations.append(generation)

                if len(generations) > 0:
                    logger.warning(
                        f"ВНИМАНИЕ: Найдено {len(generations)} поколений для модели {model_code} - это редкий случай, требующий внимания!"
                    )
                    logger.info(
                        f"Поколения для {model_code}: {[g.name for g in generations]}"
                    )
                else:
                    logger.info(
                        f"Получено 0 поколений для {model_code} - ожидаемое поведение"
                    )

                    # Fallback для известных моделей с поколениями
                    if model_code in [
                        "HD02",
                        "HD20",
                    ]:  # Hyundai Sonata (HD02 in models list, HD20 in working example)
                        logger.info(f"Применяем fallback для {model_code}")
                        generations = self._get_fallback_generations(model_code)

                result = AutohubGenerationsResponse(
                    success=True,
                    message=f"Список поколений для {model_code} получен успешно",
                    generations=generations,
                    model_code=model_code,
                    total_count=len(generations),
                )
                self._save_to_cache(cache_key, result)
                return result
            else:
                logger.error(f"Ошибка от API: {response_data.get('message')}")
                return AutohubGenerationsResponse(
                    success=False,
                    message=response_data.get("message", "Неизвестная ошибка"),
                    generations=[],
                    model_code=model_code,
                    total_count=0,
                )

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP ошибка при получении поколений: {e}")
            return AutohubGenerationsResponse(
                success=False,
                message=f"Ошибка соединения: {str(e)}",
                generations=[],
                model_code=model_code,
                total_count=0,
            )
        except Exception as e:
            logger.error(f"Ошибка при получении поколений: {e}")
            return AutohubGenerationsResponse(
                success=False,
                message=f"Ошибка: {str(e)}",
                generations=[],
                model_code=model_code,
                total_count=0,
            )

    def _get_fallback_generations(self, model_code: str) -> List[AutohubGeneration]:
        """
        Возвращает fallback поколения для известных моделей

        Args:
            model_code: Код модели

        Returns:
            Список поколений из рабочего примера
        """
        fallback_generations = {
            "HD02": [  # Hyundai Sonata (model code in our system)
                AutohubGeneration(
                    model_code="HD02",
                    generation_code="004",
                    name="NF 쏘나타 트랜스폼 (07년~12년)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD02",
                    generation_code="005",
                    name="YF 쏘나타 (09년~12년)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD02",
                    generation_code="007",
                    name="쏘나타 더 브릴리언트 (12년~16년)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD02",
                    generation_code="008",
                    name="쏘나타 하이브리드 (11년~14년)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD02",
                    generation_code="011",
                    name="LF 쏘나타 (14년~현재)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD02",
                    generation_code="013",
                    name="LF 쏘나타 하이브리드 (14년~현재)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD02",
                    generation_code="015",
                    name="쏘나타 뉴 라이즈 하이브리드 (17년~현재)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD02",
                    generation_code="017",
                    name="쏘나타(DN8) (19년~현재)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD02",
                    generation_code="018",
                    name="쏘나타 하이브리드 (DN8)(19년~현재)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD02",
                    generation_code="019",
                    name="쏘나타 디 엣지(DN8)(23년~현재)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD02",
                    generation_code="14",
                    name="쏘나타 뉴 라이즈 (17년~현재)",
                    detail_code="",
                ),
            ],
            "HD20": [  # Hyundai Sonata (model code from working example)
                AutohubGeneration(
                    model_code="HD20",
                    generation_code="004",
                    name="NF 쏘나타 트랜스폼 (07년~12년)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD20",
                    generation_code="005",
                    name="YF 쏘나타 (09년~12년)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD20",
                    generation_code="007",
                    name="쏘나타 더 브릴리언트 (12년~16년)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD20",
                    generation_code="008",
                    name="쏘나타 하이브리드 (11년~14년)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD20",
                    generation_code="011",
                    name="LF 쏘나타 (14년~현재)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD20",
                    generation_code="013",
                    name="LF 쏘나타 하이브리드 (14년~현재)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD20",
                    generation_code="015",
                    name="쏘나타 뉴 라이즈 하이브리드 (17년~현재)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD20",
                    generation_code="017",
                    name="쏘나타(DN8) (19년~현재)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD20",
                    generation_code="018",
                    name="쏘나타 하이브리드 (DN8)(19년~현재)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD20",
                    generation_code="019",
                    name="쏘나타 디 엣지(DN8)(23년~현재)",
                    detail_code="",
                ),
                AutohubGeneration(
                    model_code="HD20",
                    generation_code="14",
                    name="쏘나타 뉴 라이즈 (17년~현재)",
                    detail_code="",
                ),
            ],
        }

        return fallback_generations.get(model_code, [])

    async def get_configurations(
        self, generation_code: str, model_code: str
    ) -> AutohubConfigurationsResponse:
        """
        Получает список конфигураций для поколения

        Args:
            generation_code: Код поколения
            model_code: Код модели (нужен для правильного запроса)

        Returns:
            AutohubConfigurationsResponse: Список конфигураций
        """
        # Check cache (24h TTL for static metadata)
        cache_key = self._make_cache_key("configurations", {"gen": generation_code, "model": model_code})
        cached = self._get_from_cache(cache_key, ttl=86400)
        if cached is not None:
            logger.debug(f"📦 Autohub configurations cache hit for {generation_code}")
            return cached

        try:
            logger.info(
                f"Получение конфигураций для поколения {generation_code} модели {model_code}"
            )

            # Инициализируем сессию если нужно
            if not self.session:
                session_initialized = await self._initialize_session()
                if not session_initialized:
                    logger.error(
                        "Не удалось инициализировать сессию для получения конфигураций"
                    )
                    return AutohubConfigurationsResponse(
                        success=False,
                        message="Ошибка инициализации сессии",
                        configurations=[],
                        generation_code=generation_code,
                        total_count=0,
                    )

            # Получаем текущую сессию аукциона для кода аукциона
            sessions_response = await self.get_auction_sessions()
            auction_code = "AC202507090001"  # Значение по умолчанию
            if sessions_response.success and sessions_response.current_session:
                auction_code = sessions_response.current_session.auction_code

            # Нам нужен код производителя для запроса конфигураций
            manufacturer_code = model_code[:2] if len(model_code) >= 2 else ""

            # Подготавливаем данные для запроса
            data = {
                "i_sType": "clsDetail",
                "i_sAucCode": auction_code,
                "i_sMakerCode": manufacturer_code,
                "i_sCarName1Code": model_code,
                "i_sCarName2Code": generation_code,
                "isMultiInit": "false",
            }

            # Заголовки для AJAX запроса
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.settings.autohub_list_url,
            }

            # Выполняем запрос
            url = urljoin(self.base_url, "/comm/comm_Ajcarmodel_ajax.do")
            logger.info(f"Запрос конфигураций: {url} с параметрами {data}")

            # Дополнительное логирование для отладки
            logger.info(
                f"=== Отладка запроса конфигураций для поколения {generation_code} модели {model_code} ==="
            )
            logger.info(f"URL: {url}")
            logger.info(f"Метод: POST")
            logger.info(f"Данные: {data}")
            logger.info(
                f"Cookies: JSESSIONID={self.session.cookies.get('JSESSIONID', 'НЕТ')}, WMONID={self.session.cookies.get('WMONID', 'НЕТ')}"
            )

            response = self.session.post(
                url,
                data=data,
                headers=headers,
                timeout=self.settings.request_timeout,
            )
            logger.info(f"Статус ответа: {response.status_code}")
            response.raise_for_status()

            # Парсим JSON ответ
            try:
                response_data = response.json()
                logger.info(
                    f"Получен ответ с конфигурациями: {response_data.get('status')}"
                )
                logger.debug(f"Полный ответ: {response_data}")

                # Сохраняем сырой ответ в файл для отладки
                import os
                from datetime import datetime

                debug_dir = "logs/autohub_debug"
                os.makedirs(debug_dir, exist_ok=True)

                debug_filename = f"{debug_dir}/configurations_response_{model_code}_{generation_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

                try:
                    with open(debug_filename, "w", encoding="utf-8") as f:
                        json.dump(
                            {
                                "request_info": {
                                    "generation_code": generation_code,
                                    "model_code": model_code,
                                    "manufacturer_code": manufacturer_code,
                                    "url": url,
                                    "method": "POST",
                                    "headers": dict(response.request.headers),
                                    "data": data,
                                    "cookies": self.session.cookies.get_dict(),
                                    "timestamp": datetime.now().isoformat(),
                                },
                                "response_info": {
                                    "status_code": response.status_code,
                                    "headers": dict(response.headers),
                                    "raw_data": response_data,
                                    "raw_text": (
                                        response.text
                                        if len(response.text) < 10000
                                        else response.text[:10000] + "... (truncated)"
                                    ),
                                },
                            },
                            f,
                            ensure_ascii=False,
                            indent=2,
                        )
                    logger.info(f"Сохранен отладочный файл: {debug_filename}")
                except Exception as e:
                    logger.error(f"Не удалось сохранить отладочный файл: {e}")

            except json.JSONDecodeError as e:
                logger.error(f"Ошибка парсинга JSON ответа: {e}")
                logger.error(f"Текст ответа: {response.text[:500]}")
                return AutohubConfigurationsResponse(
                    success=False,
                    message="Ошибка парсинга ответа от сервера",
                    configurations=[],
                    generation_code=generation_code,
                    total_count=0,
                )

            if response_data.get("status") == "succ":
                # Преобразуем данные в наш формат
                configurations = []
                for item in response_data.get("object", []):
                    configuration = AutohubConfiguration(
                        generation_code=generation_code,
                        configuration_code=item.get("carname3code", ""),
                        name=item.get("carname3name", ""),
                    )
                    configurations.append(configuration)

                logger.info(
                    f"Успешно получено {len(configurations)} конфигураций для поколения {generation_code}"
                )

                result = AutohubConfigurationsResponse(
                    success=True,
                    message=f"Список конфигураций для поколения {generation_code} получен успешно",
                    configurations=configurations,
                    generation_code=generation_code,
                    total_count=len(configurations),
                )
                self._save_to_cache(cache_key, result)
                return result
            else:
                logger.error(f"Ошибка от API: {response_data.get('message')}")
                return AutohubConfigurationsResponse(
                    success=False,
                    message=response_data.get("message", "Неизвестная ошибка"),
                    configurations=[],
                    generation_code=generation_code,
                    total_count=0,
                )

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP ошибка при получении конфигураций: {e}")
            return AutohubConfigurationsResponse(
                success=False,
                message=f"Ошибка соединения: {str(e)}",
                configurations=[],
                generation_code=generation_code,
                total_count=0,
            )
        except Exception as e:
            logger.error(f"Ошибка при получении конфигураций: {e}")
            return AutohubConfigurationsResponse(
                success=False,
                message=f"Ошибка: {str(e)}",
                configurations=[],
                generation_code=generation_code,
                total_count=0,
            )

    async def _fetch_real_auction_code_from_web(self) -> Optional[str]:
        """
        Fetch the actual auction code from Autohub website by scraping

        This method scrapes the live auction listing page to get the real
        auction code that Autohub is currently using, eliminating the need
        to generate/guess the code.

        Returns:
            str: Auction code (e.g., 'AC202510010001') or None if failed
        """
        try:
            url = "https://www.autohubauction.co.kr/newfront/receive/rc/receive_rc_list.do"

            logger.info("🌐 Fetching real auction code from Autohub website...")

            # Fetch the page HTML
            html = await self._fetch_html_simple(url)
            if not html:
                logger.warning("Failed to fetch HTML for auction code extraction")
                return None

            # Parse HTML to extract auction code
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")

            # Strategy 1: Find the hidden input field with auction code
            auction_code_input = soup.find(
                "input", {"id": "i_sAucCode", "name": "i_sAucCode"}
            )

            if auction_code_input and auction_code_input.get("value"):
                auction_code = auction_code_input["value"]

                # Validate the code format
                if self._validate_auction_code(auction_code):
                    logger.info(
                        f"✅ Fetched real auction code from hidden input: {auction_code}"
                    )
                    return auction_code
                else:
                    logger.warning(
                        f"⚠️ Fetched auction code has invalid format: {auction_code}"
                    )

            # Strategy 2: Fallback - try to extract from dropdown option
            select_option = soup.find("select", {"id": "i_sAucNoTemp2"})
            if select_option:
                option = select_option.find("option", selected=True)
                if option and option.get("value"):
                    # Format: "1345@@2025-10-15@@AC202510010001"
                    parts = option["value"].split("@@")
                    if len(parts) == 3:
                        auction_code = parts[2]

                        # Validate the code format
                        if self._validate_auction_code(auction_code):
                            logger.info(
                                f"✅ Fetched auction code from dropdown: {auction_code}"
                            )
                            return auction_code
                        else:
                            logger.warning(
                                f"⚠️ Dropdown auction code has invalid format: {auction_code}"
                            )

            logger.warning("❌ Could not extract valid auction code from HTML")
            return None

        except Exception as e:
            logger.error(f"❌ Error fetching real auction code from web: {e}")
            return None

    async def _fetch_real_auction_code(self) -> Optional[str]:
        """
        Fetch the actual auction code with 24-hour caching

        This method first checks if we have a cached auction code that's
        still valid (less than 24 hours old). If not, it fetches a fresh
        code from the Autohub website.

        Returns:
            str: Auction code (e.g., 'AC202510010001') or None if failed
        """
        import time

        # Check cache first
        if self._cached_auction_code and self._cache_timestamp:
            age = time.time() - self._cache_timestamp
            if age < self._CACHE_DURATION:
                logger.info(
                    f"📦 Using cached auction code: {self._cached_auction_code} (age: {int(age)}s / {self._CACHE_DURATION}s)"
                )
                return self._cached_auction_code
            else:
                logger.info(
                    f"⏰ Cached auction code expired (age: {int(age)}s > {self._CACHE_DURATION}s)"
                )

        # Cache miss or expired - fetch fresh code from web
        logger.info("🔄 Cache miss or expired, fetching fresh auction code...")
        auction_code = await self._fetch_real_auction_code_from_web()

        if auction_code:
            # Update cache
            self._cached_auction_code = auction_code
            self._cache_timestamp = time.time()
            logger.info(f"💾 Cached new auction code: {auction_code}")
        else:
            logger.warning("⚠️ Failed to fetch fresh auction code from web")

        return auction_code

    async def get_auction_sessions(self) -> AutohubAuctionSessionsResponse:
        """
        Получает список активных сессий аукциона

        Returns:
            AutohubAuctionSessionsResponse: Список сессий
        """
        try:
            logger.info("Получение списка сессий аукциона")

            # Get current auction date with 6PM cutoff logic
            auction_date = self._get_current_auction_date()

            # Try to fetch real auction code from Autohub first (PRIMARY)
            auction_code = await self._fetch_real_auction_code()

            # Fallback: generate if fetch fails (BACKUP)
            if not auction_code:
                logger.warning(
                    "⚠️ Failed to fetch real auction code, using generated fallback"
                )
                auction_code = self._generate_auction_code(auction_date)
                logger.info(f"📝 Using generated fallback auction code: {auction_code}")
            else:
                logger.info(
                    f"✅ Using real auction code from Autohub: {auction_code}"
                )

            # Calculate auction number
            auction_no = self._calculate_auction_number(auction_date)

            # Format auction title
            date_parts = auction_date.split("-")
            auction_title = f"안성 {date_parts[0]}/{date_parts[1]}/{date_parts[2]} {auction_no}회차 경매"

            logger.info(
                f"📅 Generated auction session: date={auction_date}, no={auction_no}, code={auction_code}"
            )

            sessions = [
                AutohubAuctionSession(
                    auction_no=auction_no,
                    auction_date=auction_date,
                    auction_code=auction_code,
                    auction_title=auction_title,
                    is_active=True,
                )
            ]

            return AutohubAuctionSessionsResponse(
                success=True,
                message="Список сессий аукциона получен успешно",
                sessions=sessions,
                current_session=sessions[0] if sessions else None,
                total_count=len(sessions),
            )

        except Exception as e:
            logger.error(f"Ошибка при получении сессий аукциона: {e}")
            return AutohubAuctionSessionsResponse(
                success=False,
                message=f"Ошибка: {str(e)}",
                sessions=[],
                total_count=0,
            )

    def _get_current_auction_date(self) -> str:
        """
        Get current auction date based on Wednesday auction schedule

        Autohub auctions are held every Wednesday.
        Cars are viewable from Tuesday 6PM Seoul time.

        Returns:
            str: Auction date in YYYY-MM-DD format (always a Wednesday)
        """
        from datetime import datetime, timedelta
        import pytz

        # Get current Seoul time
        seoul_tz = pytz.timezone("Asia/Seoul")
        seoul_time = datetime.now(seoul_tz)

        # Get current day of week (0=Monday, 6=Sunday)
        current_weekday = seoul_time.weekday()
        current_hour = seoul_time.hour
        today_str = seoul_time.strftime("%Y-%m-%d")

        logger.info(
            f"📅 Current Seoul time: {seoul_time.strftime('%Y-%m-%d %H:%M:%S')} (weekday: {current_weekday})"
        )

        # ONE-TIME EXCEPTION: Dec 30, 2025 (Tuesday) - Autohub runs on Tuesday instead of Wednesday
        # Auto-reverts after this date
        if today_str == "2025-12-30":
            logger.info("📅 SPECIAL: Dec 30, 2025 - Autohub auction on Tuesday (one-time exception)")
            return "2025-12-30"

        # Dec 29, 2025 (Monday) after 6PM - show tomorrow's Tuesday auction
        if today_str == "2025-12-29" and current_hour >= 18:
            logger.info("📅 SPECIAL: Showing Dec 30, 2025 Tuesday auction (after 6PM)")
            return "2025-12-30"

        # Normal Wednesday logic (auto-reverts after Dec 30)
        if current_weekday == 2:  # Wednesday
            # If it's Wednesday, use today's date
            auction_date = seoul_time
        elif current_weekday == 1 and current_hour >= 18:  # Tuesday after 6PM
            # If it's Tuesday after 6PM, use next day (Wednesday)
            auction_date = seoul_time + timedelta(days=1)
        elif current_weekday < 2:  # Monday or Tuesday before 6PM
            # Find this week's Wednesday
            days_until_wednesday = 2 - current_weekday
            auction_date = seoul_time + timedelta(days=days_until_wednesday)
        else:  # Thursday, Friday, Saturday, Sunday
            # Find next week's Wednesday
            days_until_wednesday = (7 - current_weekday) + 2
            auction_date = seoul_time + timedelta(days=days_until_wednesday)

        auction_date_str = auction_date.strftime("%Y-%m-%d")

        logger.info(
            f"📅 Using auction date: {auction_date_str} (Wednesday) - viewable from Tuesday 6PM"
        )

        return auction_date_str

    def _validate_auction_code(self, code: str) -> bool:
        """
        Validate auction code format

        Expected format: ACYYYYMMDD0001
        Example: AC202510010001

        Args:
            code: Auction code to validate

        Returns:
            bool: True if valid format, False otherwise
        """
        import re

        pattern = r'^AC\d{8}0001$'

        if not re.match(pattern, code):
            logger.warning(f"⚠️ Invalid auction code format: {code}")
            return False

        logger.debug(f"✅ Valid auction code format: {code}")
        return True

    def _generate_auction_code(self, auction_date: str) -> str:
        """
        Generate auction code based on date

        The auction code uses the first day of the auction month.
        Format: ACYYYYMM010001 (always uses day 01)

        Args:
            auction_date: Date in YYYY-MM-DD format (should be a Wednesday)

        Returns:
            str: Auction code in format ACYYYYMM010001
        """
        from datetime import datetime

        # Parse the auction date
        date_obj = datetime.strptime(auction_date, "%Y-%m-%d")

        # Verify it's a Wednesday (weekday = 2)
        if date_obj.weekday() != 2:
            logger.warning(
                f"⚠️ Auction date {auction_date} is not a Wednesday (weekday={date_obj.weekday()})"
            )

        # The auction code uses the first day of the auction month
        # Autohub uses ACYYYYMM010001 format for all auctions in a given month
        code_date = date_obj.replace(day=1)

        # Format as YYYYMMDD (will always end with 01 for day)
        date_no_hyphens = code_date.strftime("%Y%m%d")

        # Generate code - AC + date + 0001
        auction_code = f"AC{date_no_hyphens}0001"

        logger.info(
            f"📝 Generated auction code: {auction_code} (for auction on {auction_date})"
        )

        return auction_code

    def _calculate_auction_number(self, auction_date: str) -> str:
        """
        Calculate auction number (회차) based on date
        
        Since Autohub runs weekly auctions on Wednesdays, we calculate
        the auction number based on weeks since the start of the year.

        Args:
            auction_date: Date in YYYY-MM-DD format (should be a Wednesday)

        Returns:
            str: Auction number (e.g., "1332" for the 32nd auction of the year)
        """
        from datetime import datetime, timedelta

        # Parse the auction date
        date_obj = datetime.strptime(auction_date, "%Y-%m-%d")
        
        # Find the first Wednesday of the year
        year_start = datetime(date_obj.year, 1, 1)
        # Find the first Wednesday
        days_until_first_wednesday = (2 - year_start.weekday()) % 7
        if days_until_first_wednesday == 0 and year_start.weekday() != 2:
            days_until_first_wednesday = 7
        first_wednesday = year_start + timedelta(days=days_until_first_wednesday)
        
        # Calculate weeks since first Wednesday
        if date_obj < first_wednesday:
            # If auction date is before first Wednesday of the year, it's auction #1
            weeks_since_start = 0
        else:
            days_diff = (date_obj - first_wednesday).days
            weeks_since_start = days_diff // 7
        
        # Autohub uses a base number around 1300+ for auction numbers
        # Adding week number to base (1300 + week number)
        auction_number = 1300 + weeks_since_start + 1
        
        logger.info(
            f"📊 Calculated auction number: {auction_number} (week {weeks_since_start + 1} of year {date_obj.year})"
        )

        return str(auction_number)


# Глобальный экземпляр сервиса
autohub_service = AutohubService()
