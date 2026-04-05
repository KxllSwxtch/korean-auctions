import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import logger
from loguru import logger as base_logger
from app.models.lotte import (
    LotteCar,
    LotteResponse,
    LotteAuctionDate,
    LotteError,
    LotteCarResponse,
    LotteCarDetail,
    LotteCarHistory,
    LotteCarHistoryResponse,
    LotteCountResponse,
)
from app.parsers.lotte_parser import (
    LotteParser,
    parse_lotte_car_detail,
    parse_car_history,
)
from app.core.session_manager import SessionManager
from app.services.base_auction_service import BaseAuctionService


class LotteService(BaseAuctionService):
    """Сервис для работы с аукционом Lotte с робастным управлением сессиями"""

    def __init__(self):
        super().__init__("Lotte Service")
        self.base_url = "https://www.lotteautoauction.net"
        self.parser = LotteParser()
        self.cache = {}
        self.cache_ttl = 300  # 5 минут
        self.session_manager = SessionManager()  # Для сохранения сессий
        self._cached_total_count: int = 0
        self._cached_total_count_time: float = 0

        # URLs для различных страниц
        self.urls = {
            "home": "/hp/auct/myp/entry/selectMypEntryList.do",  # Страница с датой аукциона
            "login": "/hp/auct/cmm/viewLoginUsr.do?loginMode=redirect",
            "login_check": "/hp/auct/cmm/selectAuctMemLoginCheckAjax.do",
            "login_action": "/hp/auct/cmm/actionLogin.do",
            "cars_list": "/hp/auct/myp/entry/selectMypEntryList.do",  # Та же страница со списком авто
            "car_details": "/hp/auct/myp/entry/selectMypEntryCarDetPop.do",
            "car_history": "/hp/cmm/entry/selectMypEntryAccdHistPop.do",  # История автомобиля
        }

        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
        ]

        logger.info("Инициализирован сервис Lotte")
        
        # Пытаемся восстановить сессию
        self._restore_session()

    def _init_session(self) -> requests.Session:
        """Инициализация HTTP сессии с настройками"""
        if self.session is None:
            self.session = requests.Session()

            # Настройка retry стратегии
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
            )

            adapter = HTTPAdapter(max_retries=retry_strategy)
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)

            # Базовые заголовки
            self.session.headers.update(
                {
                    "User-Agent": self.user_agents[0],
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                }
            )

        return self.session

    def _authenticate(self) -> bool:
        """Authenticate using cross-worker coordinator to prevent race conditions."""
        from app.core.auth_coordinator import ensure_authenticated
        return ensure_authenticated(self)

    def _ensure_session(self) -> bool:
        """Single entry point for ensuring we have a valid authenticated session.
        Replaces scattered _authenticate() + _refresh_session_if_needed() calls.
        """
        if self.authenticated and not self._is_session_expired():
            return True
        return self._authenticate()

    def _do_authenticate(self) -> bool:
        """Core 3-step Lotte login flow. Called by auth_coordinator under file lock.

        Returns True on success, False on non-retriable failure.
        Raises exceptions on retriable failures (network errors, unexpected responses).
        """
        # Force fresh session for clean headers/cookies
        self.session = None
        session = self._init_session()

        login = settings.lotte_username
        password = settings.lotte_password

        logger.info(f"Начинаем аутентификацию в Lotte для пользователя: {login}")

        # Step 1: Get login page for cookies/session
        login_page_url = urljoin(self.base_url, self.urls["login"])
        response = session.get(login_page_url, timeout=30, verify=False)

        if response.status_code != 200:
            logger.error(f"Не удалось получить страницу логина: {response.status_code}")
            raise Exception(f"Login page fetch failed: HTTP {response.status_code}")

        logger.info(f"Страница логина получена (статус: {response.status_code})")
        logger.debug(f"Cookies после получения страницы логина: {session.cookies.get_dict()}")

        # Step 2: Validate credentials via AJAX
        login_check_url = urljoin(self.base_url, self.urls["login_check"])
        login_check_data = {
            "userId": login,
            "userPwd": password,
            "resultCd": "",
        }

        session.headers.update(
            {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": login_page_url,
                "Accept": "application/json, text/javascript, */*; q=0.01",
            }
        )

        check_response = session.post(
            login_check_url, data=login_check_data, timeout=30, verify=False
        )

        if check_response.status_code != 200:
            logger.error(f"Ошибка при проверке логина: HTTP {check_response.status_code}")
            raise Exception(f"Login check failed: HTTP {check_response.status_code}")

        try:
            result = check_response.json()
        except Exception as json_err:
            logger.error(f"Ошибка при разборе JSON ответа проверки логина: {json_err}")
            logger.error(f"Текст ответа: {check_response.text[:500]}")
            raise Exception(f"Login check returned non-JSON response: {json_err}")

        logger.info(f"Ответ проверки логина: {result}")

        # Check for login errors
        error_code = result.get("resultCd")
        if error_code is not None and error_code != "":
            logger.error(f"Ошибка логина: {error_code}")
            if error_code == "errUserAuth":
                logger.error("Неверные логин или пароль")
                return False
            elif error_code == "errOverPassCnt":
                logger.error("Превышено количество попыток входа — активируем 15-мин cooldown")
                from app.core.auth_coordinator import set_lockout
                set_lockout(900)
                return False
            elif error_code == "feeInactive":
                logger.error("Проблемы с оплатой аккаунта")
                return False
            else:
                logger.error(f"Неизвестная ошибка логина: {error_code}")
                return False

        logger.info("Проверка логина прошла успешно")

        # Step 3: Final login POST with allow_redirects=False to detect failures
        login_action_url = urljoin(self.base_url, self.urls["login_action"])
        final_login_data = {
            "userId": login,
            "userPwd": password,
            "resultCd": "",
        }

        session.headers.update(
            {
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": login_page_url,
            }
        )
        if "X-Requested-With" in session.headers:
            del session.headers["X-Requested-With"]

        final_response = session.post(
            login_action_url,
            data=final_login_data,
            timeout=30,
            verify=False,
            allow_redirects=False,
        )

        # Restore browser-like headers after login flow
        session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1",
        })
        session.headers.pop("Content-Type", None)

        logger.info(f"Финальный логин статус: {final_response.status_code}")

        if final_response.status_code in [302, 303]:
            # Inspect redirect target to detect failed login
            location = final_response.headers.get("Location", "")
            logger.info(f"Login redirect location: {location}")

            if "viewLoginUsr" in location or "login" in location.lower():
                logger.error(f"Login redirected back to login page: {location}")
                raise Exception("Login redirected back to login page — session not established")

            # Follow redirect manually to capture cookies properly
            redirect_url = urljoin(self.base_url, location)
            session.get(redirect_url, timeout=15, verify=False)

        elif final_response.status_code == 200:
            # Direct 200 — check if it's actually the login page
            if self._is_login_page(final_response.text):
                logger.error("Login POST returned 200 but response is login page")
                raise Exception("Login POST returned login page — auth not established")
        else:
            logger.error(f"Ошибка финального логина: HTTP {final_response.status_code}")
            raise Exception(f"Final login failed: HTTP {final_response.status_code}")

        # Validate session by hitting a protected page
        if self._validate_session():
            logger.info("✅ Аутентификация в Lotte успешна и проверена!")
            return True
        else:
            logger.error("Login POST succeeded but session validation failed")
            raise Exception("Session validation failed after successful login POST")

    def _load_shared_session(self) -> bool:
        """Load session cookies from shared file written by another worker."""
        try:
            session_data = self.session_manager.load_session('lotte')
            if not session_data:
                return False

            age = self.session_manager.get_session_age('lotte')
            if age and age > timedelta(minutes=self.session_max_age_minutes):
                logger.debug(f"Shared session too old ({age.total_seconds()/60:.1f} min)")
                return False

            self.session = None
            self.session = self._init_session()

            cookies = session_data if isinstance(session_data, dict) else {}
            if 'cookies' in cookies and isinstance(cookies.get('cookies'), dict):
                cookies = cookies['cookies']
            for name, value in cookies.items():
                if isinstance(value, str):
                    self.session.cookies.set(name, value)

            if self._validate_session():
                self.authenticated = True
                self.session_created_at = datetime.now()
                logger.info("✅ Shared session loaded and validated")
                return True

            logger.debug("Shared session failed validation")
            self.session = None
            return False
        except Exception as e:
            logger.debug(f"Error loading shared session: {e}")
            return False

    def _validate_session(self) -> bool:
        """Validate current session by making a test request to a protected page."""
        try:
            session = self._init_session()
            test_url = urljoin(self.base_url, self.urls["home"])
            response = session.get(test_url, timeout=15, verify=False)
            logger.debug(f"Session validation status: {response.status_code}")
            if response.status_code != 200:
                logger.warning(f"Session validation: unexpected status {response.status_code}")
                return False
            if self._is_login_page(response.text):
                logger.warning(f"Session validation: response is login page (title snippet: {response.text[:200]})")
                return False
            logger.debug("Session validation: OK")
            return True
        except Exception as e:
            logger.warning(f"Session validation error: {e}")
            return False

    def _is_login_page(self, html: str) -> bool:
        """Detect if response is a login page redirect instead of actual content."""
        login_indicators = [
            "<title>로그인 | 롯데오토옥션</title>",
            "경매회원전용 로그인",
        ]
        return any(indicator in html for indicator in login_indicators)

    def _get_from_cache(self, key: str, ttl: int = None) -> Optional[Any]:
        """Получение данных из кеша с поддержкой per-key TTL"""
        if key in self.cache:
            cached_data, timestamp = self.cache[key]
            effective_ttl = ttl if ttl is not None else self.cache_ttl
            if time.time() - timestamp < effective_ttl:
                logger.info(f"Данные получены из кеша: {key}")
                return cached_data
            else:
                del self.cache[key]
        return None

    def _save_to_cache(self, key: str, data: Any):
        """Сохранение данных в кеш"""
        self.cache[key] = (data, time.time())
        logger.info(f"Данные сохранены в кеш: {key}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def get_auction_date(self) -> Optional[LotteAuctionDate]:
        """Получение даты аукциона"""
        cache_key = "lotte_auction_date"

        # Проверяем кеш (auction date: 12h TTL)
        cached_data = self._get_from_cache(cache_key, ttl=43200)
        if cached_data:
            return cached_data

        try:
            if not self._ensure_session():
                logger.error("Не удалось аутентифицироваться")
                self._record_failure(Exception("Authentication failed"))
                return None

            session = self._init_session()

            # Получаем главную страницу с датой аукциона
            home_url = urljoin(self.base_url, self.urls["home"])
            response = session.get(home_url, timeout=30, verify=False)

            if response.status_code != 200:
                logger.error(
                    f"Не удалось получить главную страницу: {response.status_code}"
                )
                self._record_failure(Exception(f"HTTP {response.status_code}"))
                return None

            logger.info(
                f"✅ Получена главная страница, размер: {len(response.text)} символов"
            )

            # Проверяем на ошибку аутентификации (login page redirect или JSON fail)
            if self._is_login_page(response.text):
                logger.error("🔐 Login page detected - session is invalid")
                self.authenticated = False
                self.session = None
                self._record_failure(Exception("Session expired - login page detected"))
                raise Exception("Session expired - need re-authentication")

            # Парсим дату
            auction_date = self.parser.parse_auction_date(response.text)

            # Also extract total count from the full-page GET response
            # The full page contains .total-carnum with "총 등록대수 1,257"
            total_from_home = self.parser.parse_total_count(response.text)
            if total_from_home > 0:
                self._cached_total_count = total_from_home
                self._cached_total_count_time = time.time()
                logger.info(f"✅ Total count extracted from home page: {total_from_home}")

            if auction_date:
                self._save_to_cache(cache_key, auction_date)
                logger.info(f"✅ Дата аукциона получена: {auction_date.auction_date}")
                # Record success
                self._record_success()
            else:
                logger.warning("Не удалось найти дату аукциона на странице")
                logger.info(f"Начало контента страницы: {response.text[:500]}...")
                self._record_failure(Exception("Failed to parse auction date"))

            return auction_date

        except Exception as e:
            logger.error(f"Ошибка при получении даты аукциона: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            # Record failure
            self._record_failure(e)
            return None

    async def get_cars(self, limit: int = 20, offset: int = 0) -> List[LotteCar]:
        """Получить автомобили из списка предстоящего аукциона (без проверки даты)"""
        logger.info(
            f"Запрос автомобилей предстоящего аукциона: limit={limit}, offset={offset}"
        )

        try:
            if not self._ensure_session():
                raise Exception("Не удалось аутентифицироваться")

            # Получаем страницу с автомобилями с пагинацией
            cars_response = await self._fetch_cars_page(limit, offset)

            if not cars_response:
                logger.error("Не удалось получить ответ от сервера")
                return []

            # Парсим автомобили (пагинация уже применена на сервере)
            cars = self._parse_cars(cars_response.text)
            logger.info(
                f"Найдено {len(cars)} автомобилей на странице (пагинация на сервере)"
            )

            return cars

        except Exception as e:
            logger.error(f"Ошибка при получении автомобилей: {e}")
            raise e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def _get_car_details(
        self, car_basic_data: Dict[str, Any]
    ) -> Optional[LotteCar]:
        """Получение детальной информации об автомобиле"""
        try:
            # Re-check auth on each retry attempt (session may have been invalidated)
            if not self._ensure_session():
                self._record_failure(Exception("Authentication failed"))
                return None

            session = self._init_session()

            # Формируем URL для получения деталей
            details_url = urljoin(self.base_url, self.urls["car_details"])
            params = {
                "searchMngDivCd": car_basic_data["searchMngDivCd"],
                "searchMngNo": car_basic_data["searchMngNo"],
                "searchExhiRegiSeq": car_basic_data["searchExhiRegiSeq"],
            }

            response = session.get(details_url, params=params, timeout=30, verify=False)

            if response.status_code != 200:
                logger.warning(
                    f"Не удалось получить детали автомобиля {car_basic_data['id']}: {response.status_code}"
                )
                self._record_failure(Exception(f"HTTP {response.status_code}"))
                return None

            if self._is_login_page(response.text):
                logger.error("🔐 Login page detected - session is invalid")
                self.authenticated = False
                self._record_failure(Exception("Session expired - login page detected"))
                raise Exception("Session expired - need re-authentication")

            # Парсим детальную информацию
            detailed_car = self.parser.parse_car_details(response.text, car_basic_data)

            if detailed_car:
                logger.info(f"Получены детали для автомобиля: {detailed_car.name}")
                # Record success
                self._record_success()
            else:
                self._record_failure(Exception("Failed to parse car details"))

            return detailed_car

        except Exception as e:
            logger.error(f"Ошибка при получении деталей автомобиля: {e}")
            self._record_failure(e)
            return None

    async def get_cars_with_date_check(
        self, limit: int = 20, offset: int = 0
    ) -> List[LotteCar]:
        """Получение списка автомобилей с проверкой даты аукциона"""
        cache_key = f"lotte_cars_{limit}_{offset}"

        # Проверяем кеш (car list: 3min TTL)
        cached_data = self._get_from_cache(cache_key, ttl=180)
        if cached_data:
            return cached_data

        try:
            if not self._ensure_session():
                logger.error("Не удалось аутентифицироваться")
                return []

            session = self._init_session()

            # Получаем список автомобилей с пагинацией
            cars_response = await self._fetch_cars_page(limit, offset)

            if not cars_response:
                logger.error("Не удалось получить список автомобилей")
                return []

            # Парсим список автомобилей (пагинация уже применена на сервере)
            cars_data = self.parser.parse_cars_list(cars_response.text)
            logger.info(f"Найдено {len(cars_data)} автомобилей на странице")

            # Получаем детальную информацию для каждого автомобиля
            detailed_cars = []
            for car_data in cars_data:
                try:
                    detailed_car = await self._get_car_details(car_data)
                    if detailed_car:
                        detailed_cars.append(detailed_car)

                    # Небольшая задержка между запросами
                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.error(
                        f"Ошибка при получении деталей автомобиля {car_data.get('id', 'unknown')}: {e}"
                    )
                    continue

            self._save_to_cache(cache_key, detailed_cars)
            return detailed_cars

        except Exception as e:
            logger.error(f"Ошибка при получении списка автомобилей: {e}")
            return []

    async def get_cars_response_with_date_check(
        self, limit: int = 20, offset: int = 0
    ) -> LotteResponse:
        """
        Получение автомобилей с проверкой даты аукциона
        Если дата аукциона не сегодня, возвращает информацию о ближайшей дате
        """
        start_time = time.time()

        try:
            # Получаем дату аукциона
            auction_date = await self.get_auction_date()

            response = LotteResponse(
                success=True,
                message="Данные получены успешно",
                timestamp=datetime.now().isoformat(),
                auction_date_info=auction_date,
            )

            if not auction_date:
                response.success = False
                response.message = "Не удалось получить дату аукциона"
                response.request_duration = time.time() - start_time
                return response

            # Информация о дате аукциона (не блокирует получение автомобилей)
            date_note = ""
            if not auction_date.is_today:
                if auction_date.is_future:
                    date_note = f" (ближайший аукцион: {auction_date.auction_date})"
                else:
                    date_note = f" (дата аукциона прошла: {auction_date.auction_date})"

            # Всегда получаем автомобили
            cars = await self.get_cars_with_date_check(limit, offset)

            # Получаем общее количество автомобилей для правильной пагинации
            total_count = await self.get_total_cars_count()

            response.cars = cars
            response.total_count = total_count
            response.page = (offset // limit) + 1
            response.per_page = limit
            response.total_pages = (
                (total_count + limit - 1) // limit if total_count > 0 else 1
            )
            response.message = f"Найдено {len(cars)} автомобилей на странице {response.page} из {total_count} общих{date_note}"

            response.request_duration = time.time() - start_time
            return response

        except Exception as e:
            logger.error(f"Ошибка в get_cars_response_with_date_check: {e}")
            return LotteResponse(
                success=False,
                message=f"Ошибка при получении данных: {str(e)}",
                timestamp=datetime.now().isoformat(),
                request_duration=time.time() - start_time,
            )

    def clear_cache(self):
        """Очистка кеша"""
        self.cache.clear()
        logger.info("Кеш Lotte очищен")

    def reset_authentication(self):
        """Сброс состояния аутентификации"""
        self.authenticated = False
        self.session = None
        logger.info("Аутентификация Lotte сброшена")

    async def _fetch_total_count_from_home_page(self) -> int:
        """Fetch total registered car count from full-page GET response.
        The full page contains .total-carnum with the true total (e.g. 1,257).
        """
        try:
            if not self._ensure_session():
                logger.error("Authentication failed for total count fetch")
                return 0

            session = self._init_session()
            home_url = urljoin(self.base_url, self.urls["home"])
            response = session.get(home_url, timeout=30, verify=False)

            if response.status_code != 200:
                logger.error(f"Failed to fetch home page for total count: {response.status_code}")
                return 0

            if self._is_login_page(response.text):
                logger.error("Login page detected - session invalid")
                self.authenticated = False
                self.session = None
                return 0

            total_count = self.parser.parse_total_count(response.text)
            if total_count > 0:
                self._cached_total_count = total_count
                self._cached_total_count_time = time.time()
                logger.info(f"✅ Total count from home page: {total_count}")
                self._record_success()
            return total_count

        except Exception as e:
            logger.error(f"Error fetching total count from home page: {e}")
            self._record_failure(e)
            return 0

    async def fetch_total_count(self) -> LotteCountResponse:
        """Fetch total car count with layered fallback strategy:
        1. Cached value from recent get_auction_date() call (< 5 min)
        2. Full-page GET (contains .total-carnum with true total)
        3. AJAX fallback via get_total_cars_count() (date-filtered, better than 0)
        """
        try:
            total_count = 0

            # Strategy 1: Use cached total (from get_auction_date or previous fetch)
            cache_age = time.time() - self._cached_total_count_time
            if self._cached_total_count > 0 and cache_age < 300:  # 5 min TTL
                total_count = self._cached_total_count
                logger.info(f"Using cached total count: {total_count} (age: {cache_age:.0f}s)")

            # Strategy 2: Full-page GET (contains .total-carnum with true total)
            if total_count == 0:
                total_count = await self._fetch_total_count_from_home_page()

            # Strategy 3: AJAX fallback (date-filtered count, better than 0)
            if total_count == 0:
                total_count = await self.get_total_cars_count()

            date_for_display = "предстоящего аукциона"
            if total_count > 0:
                return LotteCountResponse(
                    success=True,
                    total_count=total_count,
                    message=f"Всего {total_count} автомобилей на аукционе {date_for_display}",
                    timestamp=datetime.now()
                )

            return LotteCountResponse(
                success=True,
                total_count=0,
                message=f"Нет доступных автомобилей на аукционе {date_for_display}",
                timestamp=datetime.now()
            )

        except Exception as e:
            logger.error(f"Error fetching Lotte total count: {e}")
            return LotteCountResponse(
                success=False,
                total_count=0,
                message=f"Ошибка: {str(e)}",
                timestamp=datetime.now()
            )

    def get_cache_stats(self) -> Dict[str, Any]:
        """Статистика кеша"""
        return {
            "cache_size": len(self.cache),
            "cache_keys": list(self.cache.keys()),
            "authenticated": self.authenticated,
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def _fetch_cars_page(self, limit: int = 20, offset: int = 0):
        """Получение страницы с автомобилями с пагинацией"""
        try:
            # Re-check auth on each retry attempt (session may have been invalidated)
            if not self._ensure_session():
                self._record_failure(Exception("Authentication failed"))
                return None

            session = self._init_session()
            cars_url = urljoin(self.base_url, self.urls["cars_list"])

            # Вычисляем номер страницы (pageIndex начинается с 1)
            page_index = (offset // limit) + 1

            # Получаем дату аукциона для запроса
            auction_date = await self.get_auction_date()
            auction_date_str = ""
            if auction_date:
                # Форматируем дату в формат YYYYMMDD
                auction_date_str = auction_date.auction_date.replace("-", "")
                logger.info(f"Используем дату аукциона: {auction_date.auction_date} -> {auction_date_str}")
            else:
                # Если не удалось получить дату, используем сегодняшнюю
                from datetime import datetime
                today = datetime.now()
                auction_date_str = today.strftime("%Y%m%d")
                logger.warning(f"Не удалось получить дату аукциона, используем сегодня: {auction_date_str}")

            # Формируем payload для POST запроса
            payload = {
                "searchPageUnit": str(limit),  # Количество элементов на странице
                "pageIndex": str(page_index),  # Номер страницы (начинается с 1)
                "search_grntVal": "",  # Поиск по гаранции
                "search_concVal": "",  # Поиск по состоянию
                "search_preVal": "",  # Поиск по предварительной цене
                "set_search_maker": "",  # Поиск по производителю
                "set_search_mdl": "",  # Поиск по модели
                "searchAuctDt": auction_date_str,  # Дата аукциона в формате YYYYMMDD
                "excelDiv": "",  # Разделитель Excel
                "search_startPrice": "",  # Начальная цена поиска
                "search_endPrice": "",  # Конечная цена поиска
                "searchLaneDiv": "",  # Поиск по полосе
                "search_doimCd": "",  # Код района
                "search_exhiNo": "",  # Номер выставки
                "search_startYyyy": "",  # Начальный год
                "search_endYyyy": "",  # Конечный год
                "search_startPrice_s": "",  # Начальная цена продажи
                "search_endPrice_s": "",  # Конечная цена продажи
                "search_fuelCd": "",  # Код топлива
                "search_trnsCd": "",  # Код трансмиссии
            }

            logger.info(
                f"POST запрос к {cars_url} с пагинацией: page={page_index}, limit={limit}"
            )
            logger.info(f"Дата аукциона для запроса: {auction_date_str}")
            logger.debug(f"Полный payload запроса: {payload}")

            response = session.post(
                cars_url,
                data=payload,
                timeout=30,
                verify=False,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )

            logger.info(f"Статус ответа: {response.status_code}")

            if response.status_code == 200:
                logger.info(f"✅ Получен ответ: {len(response.text)} символов")

                # Проверяем на ошибку аутентификации (login page redirect или JSON fail)
                if self._is_login_page(response.text):
                    logger.error("🔐 Login page detected - session is invalid")
                    self.authenticated = False
                    self.session = None
                    self._record_failure(Exception("Session expired - login page detected"))
                    raise Exception("Session expired - need re-authentication")

                # Проверяем, содержит ли ответ таблицу с автомобилями
                if 'tbl-t02' in response.text:
                    logger.info("✅ Найдена таблица с автомобилями")
                    # Record success
                    self._record_success()
                else:
                    logger.warning("⚠️ Таблица с автомобилями не найдена в ответе")
                    if len(response.text) < 5000:
                        logger.debug(f"Начало ответа: {response.text[:1000]}")
                    self._record_failure(Exception("No car table found in response"))

                return response
            else:
                logger.error(
                    f"Ошибка получения страницы автомобилей: {response.status_code}"
                )
                logger.error(f"Response text: {response.text[:500]}")
                self._record_failure(Exception(f"HTTP {response.status_code}"))
                return None
        except Exception as e:
            logger.error(f"Ошибка при запросе страницы автомобилей: {e}")
            self._record_failure(e)
            return None

    def _parse_cars(self, html: str) -> List[LotteCar]:
        """Парсинг списка автомобилей из HTML"""
        try:
            cars_data = self.parser.parse_cars_list(html)
            logger.info(f"Распарсено {len(cars_data)} автомобилей")

            # Преобразуем в объекты LotteCar
            cars = []
            for car_data in cars_data:
                try:
                    from app.models.lotte import LotteCar

                    brand, model = self.parser._parse_brand_model(car_data["name"])
                    car = LotteCar(
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
                    cars.append(car)
                except Exception as e:
                    logger.error(f"Ошибка создания объекта автомобиля: {e}")
                    continue

            return cars

        except Exception as e:
            logger.error(f"Ошибка парсинга автомобилей: {e}")
            return []

    async def get_total_cars_count(self) -> int:
        """Получение общего количества автомобилей на аукционе"""
        try:
            if not self._ensure_session():
                logger.error("Authentication failed for total cars count")
                return 0

            cars_response = await self._fetch_cars_page(limit=1, offset=0)

            if not cars_response:
                logger.warning(
                    "Не удалось получить данные для подсчета общего количества"
                )
                return 0

            # Парсим общее количество из HTML
            total_count = self.parser.parse_total_count(cars_response.text)
            logger.info(f"Общее количество автомобилей на аукционе: {total_count}")

            return total_count

        except Exception as e:
            logger.error(f"Ошибка при получении общего количества автомобилей: {e}")
            return 0

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def get_car_detail(
        self, search_mng_div_cd: str, search_mng_no: str, search_exhi_regi_seq: str
    ) -> LotteCarResponse:
        """
        Получает детальную информацию об автомобиле

        Args:
            search_mng_div_cd: Код подразделения управления (например, "KS")
            search_mng_no: Номер управления (например, "KS202506090099")
            search_exhi_regi_seq: Последовательность регистрации выставки (например, "2")

        Returns:
            LotteCarResponse: Ответ с детальной информацией об автомобиле
        """
        try:
            if not self._ensure_session():
                return LotteCarResponse(
                    success=False,
                    message="Authentication failed",
                    error="Could not authenticate"
                )

            # Парам��тры запроса для детальной страницы
            params = {
                "searchMngDivCd": search_mng_div_cd,
                "searchMngNo": search_mng_no,
                "searchExhiRegiSeq": search_exhi_regi_seq,
            }

            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "max-age=0",
                "Connection": "keep-alive",
                "Referer": f"{self.base_url}/hp/cmm/actionMenuLinkPage.do?baseMenuNo=1010000&link=forward%3A%2Fhp%2Fauct%2Fmyp%2Fentry%2FselectMypEntryList.do&redirectMode=&popHeight=&popWidth=&subMenuNo=1010200&subSubMenuNo=",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
            }

            # URL для детальной страницы автомобиля
            url = f"{self.base_url}/hp/auct/myp/entry/selectMypEntryCarDetPop.do"

            response = self._init_session().get(
                url, params=params, headers=headers, timeout=30
            )
            response.raise_for_status()

            if self._is_login_page(response.text):
                logger.error("🔐 Login page detected - session is invalid")
                self.authenticated = False
                self._record_failure(Exception("Session expired - login page detected"))
                raise Exception("Session expired - need re-authentication")

            # Формируем source URL для отслеживания
            source_url = f"{url}?{requests.compat.urlencode(params)}"

            # Парсим детальную информацию
            car_detail = parse_lotte_car_detail(response.text, source_url)

            # Record success
            self._record_success()

            return LotteCarResponse(
                success=True,
                message="Детальная информация об автомобиле успешно получена",
                data=car_detail,
            )

        except requests.RequestException as e:
            logger.error(f"Ошибка HTTP запроса к Lotte car detail: {e}")
            self._record_failure(e)
            return LotteCarResponse(
                success=False, message=f"Ошибка сети: {str(e)}", error=str(e)
            )
        except Exception as e:
            logger.error(f"Ошибка получения детальной информации Lotte: {e}")
            self._record_failure(e)
            return LotteCarResponse(
                success=False, message=f"Внутренняя ошибка: {str(e)}", error=str(e)
            )
    
    def _save_session(self):
        """Save current session cookies to file."""
        try:
            if self.session and self.authenticated:
                cookies = dict(self.session.cookies)
                metadata = {
                    'authenticated': self.authenticated,
                    'base_url': self.base_url,
                }
                self.session_manager.save_session('lotte', cookies, metadata=metadata)
                logger.info("✅ Lotte session saved")
        except Exception as e:
            logger.error(f"Error saving Lotte session: {e}")
    
    def _restore_session(self):
        """Restore session from file and validate it."""
        try:
            session_data = self.session_manager.load_session('lotte')
            if not session_data:
                return

            # Reject sessions older than max age
            age = self.session_manager.get_session_age('lotte')
            if age and age > timedelta(minutes=self.session_max_age_minutes):
                logger.warning(f"Saved Lotte session too old ({age.total_seconds()/60:.1f} min), discarding")
                return

            self.session = self._init_session()

            # Handle both old double-nested and new flat cookie formats
            cookies = session_data if isinstance(session_data, dict) else {}
            # Old format: session_data = {'cookies': {...}, 'authenticated': True, ...}
            if 'cookies' in cookies and isinstance(cookies.get('cookies'), dict):
                cookies = cookies['cookies']
            for name, value in cookies.items():
                if isinstance(value, str):
                    self.session.cookies.set(name, value)

            # Validate the restored session actually works
            if self._validate_session():
                self.authenticated = True
                self.session_created_at = datetime.now()
                logger.info("✅ Lotte session restored and validated")
            else:
                logger.warning("Restored Lotte session is invalid, will re-authenticate")
                self.authenticated = False
                self.session = None
        except Exception as e:
            logger.error(f"Error restoring Lotte session: {e}")
            self.authenticated = False
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def get_car_history(self, search_mng_no: str, car_number: str = None) -> LotteCarHistoryResponse:
        """
        Получает историю автомобиля из Lotte

        Args:
            search_mng_no: Номер управления (например, "KS202507090027")
            car_number: Номерной знак автомобиля (опционально)

        Returns:
            LotteCarHistoryResponse: История автомобиля
        """
        try:
            if not self._ensure_session():
                self._record_failure(Exception("Authentication failed"))
                return LotteCarHistoryResponse(
                    success=False,
                    message="Не удалось аутентифицироваться",
                    error="Authentication failed"
                )

            session = self._init_session()
            
            # URL для истории автомобиля
            history_url = urljoin(self.base_url, self.urls["car_history"])
            
            # Подготовка данных для POST запроса
            # Извлекаем номер автомобиля из search_mng_no если не передан
            if not car_number:
                # Сначала нужно получить детали автомобиля чтобы узнать номерной знак
                logger.warning("Номерной знак не передан, получение истории может не работать")
                car_number = ""
            
            data = {
                "searchCarNo": car_number,  # Номерной знак
                "search_oldCarNo": "",  # Старый номерной знак
                "searchMngNo": search_mng_no,  # Номер управления
                "searchDocGubun": "",  # Тип документа
            }
            
            # Заголовки для POST запроса
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
                "Cache-Control": "max-age=0",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/hp/auct/myp/entry/selectMypEntryCarDetPop.do",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            }
            
            logger.info(f"Запрос истории автомобиля: search_mng_no={search_mng_no}, car_number={car_number}")
            logger.debug(f"POST данные: {data}")
            
            # Выполняем POST запрос
            response = session.post(
                history_url,
                data=data,
                headers=headers,
                timeout=30,
                verify=False
            )
            
            logger.info(f"Статус ответа истории: {response.status_code}")

            if response.status_code == 200 and self._is_login_page(response.text):
                logger.error("🔐 Login page detected - session is invalid")
                self.authenticated = False
                self._record_failure(Exception("Session expired - login page detected"))
                raise Exception("Session expired - need re-authentication")

            if response.status_code != 200:
                logger.error(f"Ошибка получения истории: HTTP {response.status_code}")
                logger.error(f"Response text: {response.text[:500]}")
                self._record_failure(Exception(f"HTTP {response.status_code}"))
                return LotteCarHistoryResponse(
                    success=False,
                    message=f"Ошибка получения истории: HTTP {response.status_code}",
                    error=f"HTTP {response.status_code}"
                )
            
            # Парсим историю
            car_history = parse_car_history(response.text)

            if car_history:
                logger.info(f"✅ История автомобиля успешно получена: {car_history.car_number}")
                # Record success
                self._record_success()
                return LotteCarHistoryResponse(
                    success=True,
                    message="История автомобиля успешно получена",
                    data=car_history
                )
            else:
                logger.error("Не удалось распарсить историю автомобиля")
                # Логируем часть ответа для отладки
                if len(response.text) < 1000:
                    logger.debug(f"Полный ответ: {response.text}")
                else:
                    logger.debug(f"Начало ответа: {response.text[:1000]}")

                self._record_failure(Exception("Parse error"))
                return LotteCarHistoryResponse(
                    success=False,
                    message="Не удалось распарсить историю автомобиля",
                    error="Parse error"
                )

        except Exception as e:
            logger.error(f"Ошибка при получении истории автомобиля: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

            self._record_failure(e)
            return LotteCarHistoryResponse(
                success=False,
                message=f"Внутренняя ошибка: {str(e)}",
                error=str(e)
            )
