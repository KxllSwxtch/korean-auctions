import requests
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from urllib.parse import urljoin
import warnings

from app.core.config import settings
from app.core.logging import logger
from app.core.session_manager import SessionManager
from app.models.lotte_filters import (
    LotteManufacturer,
    LotteModel,
    LotteCarGroup,
    LotteMPriceCar,
    LotteFilterRequest,
    LotteManufacturersResponse,
    LotteModelsResponse,
    LotteCarGroupsResponse,
    LotteMPriceCarsResponse,
    LotteFilterError,
    LotteSearchRequest,
    LotteSearchResponse,
    LotteCarResult,
)
from app.parsers.lotte_filter_parser import LotteFilterParser


# Indicators that Lotte returned a login page (or its JSON equivalent) instead
# of the requested resource — used to detect a silently-expired session.
_LOTTE_LOGIN_PAGE_MARKERS = (
    "<title>로그인 | 롯데오토옥션</title>",
    "경매회원전용 로그인",
    '"result":"fail_notAuctLogin"',
    "fail_notAuctLogin",
)


def _normalize_exhibition_number(raw: Optional[str]) -> str:
    """Lotte's search_exhiNo expects zero-padded 4-digit format (e.g. '0034', not '34').
    Defense-in-depth normalization for any caller that bypasses the frontend padding."""
    s = (raw or "").strip()
    if s.isdigit() and len(s) < 4:
        return s.zfill(4)
    return s


class LotteFilterService:
    """Сервис для работы с фильтрами Lotte"""

    def __init__(self):
        self.base_url = "https://www.lotteautoauction.net"
        self.parser = LotteFilterParser()
        self.session = None
        self.authenticated = False
        self.cache = {}
        self.cache_ttl = 3600  # 1 час для фильтров

        # Session lifecycle state — mirrors LotteService so we can reuse
        # SessionManager and the cross-worker auth_coordinator.
        self.session_manager = SessionManager()
        self.session_max_age_minutes = 25
        self.session_created_at: Optional[datetime] = None
        self.consecutive_failures = 0

        # Disable SSL warnings
        warnings.filterwarnings('ignore', message='Unverified HTTPS request')

        # URL для API фильтров и аутентификации
        self.filter_url = "/hp/auct/myp/entry/selectMultiComboVehi.do"
        self.search_url = "/hp/auct/myp/entry/selectMypEntryList.do"
        # Lightweight protected page used by _validate_session.
        self.session_probe_url = "/hp/auct/myp/entry/selectMypEntryList.do"

        # URLs для аутентификации (такие же как в LotteService)
        self.login_url = "/hp/auct/cmm/viewLoginUsr.do?loginMode=redirect"
        self.login_check_url = "/hp/auct/cmm/selectAuctMemLoginCheckAjax.do"
        self.login_action_url = "/hp/auct/cmm/actionLogin.do"

        # Default headers
        self.headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://www.lotteautoauction.net",
            "Referer": "https://www.lotteautoauction.net/hp/cmm/actionMenuLinkPage.do",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

        # Pick up cookies persisted by LotteService or a previous Filter run.
        # Mirrors LotteService.__init__ → _restore_session().
        self._restore_session()

    def _init_session(self) -> requests.Session:
        """Инициализация сессии с retry стратегией"""
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

            # Устанавливаем default headers
            self.session.headers.update(self.headers)

        return self.session
    
    def _is_login_page(self, html: str) -> bool:
        """Detect a Lotte login redirect / fail_notAuctLogin marker in a response body."""
        if not html:
            return False
        return any(marker in html for marker in _LOTTE_LOGIN_PAGE_MARKERS)

    def _validate_session(self) -> bool:
        """Validate current cookies by hitting a protected page; True if not the login page."""
        try:
            if self.session is None:
                return False
            probe_url = urljoin(self.base_url, self.session_probe_url)
            response = self.session.get(probe_url, timeout=15, verify=False)
            if response.status_code != 200:
                logger.warning(
                    f"[lotte-filter] session probe HTTP {response.status_code}"
                )
                return False
            if self._is_login_page(response.text):
                logger.warning("[lotte-filter] session probe returned login page")
                return False
            return True
        except Exception as e:
            logger.warning(f"[lotte-filter] session validation error: {e}")
            return False

    def _is_session_expired(self) -> bool:
        """Tell auth_coordinator whether to refresh based on age."""
        if self.session_created_at is None:
            return True
        age = datetime.now() - self.session_created_at
        return age > timedelta(minutes=self.session_max_age_minutes)

    def _record_failure(self, _err: Exception) -> None:
        """Track consecutive failures (used by auth_coordinator-style flows)."""
        self.consecutive_failures += 1

    def _save_session(self) -> None:
        """Persist current cookies to disk so other workers/services can reuse them."""
        try:
            if self.session is None or not self.authenticated:
                return
            cookies = dict(self.session.cookies)
            metadata = {
                "authenticated": True,
                "base_url": self.base_url,
                "saved_by": "LotteFilterService",
            }
            self.session_manager.save_session("lotte", cookies, metadata=metadata)
            logger.info("✅ Lotte filter session saved (shared with LotteService)")
        except Exception as e:
            logger.error(f"Error saving Lotte filter session: {e}")

    def _restore_session(self) -> None:
        """Load cookies persisted by LotteService (or a previous run) and validate them."""
        try:
            session_data = self.session_manager.load_session("lotte")
            if not session_data:
                return

            age = self.session_manager.get_session_age("lotte")
            if age and age > timedelta(minutes=self.session_max_age_minutes):
                logger.warning(
                    f"[lotte-filter] saved session too old "
                    f"({age.total_seconds() / 60:.1f} min), discarding"
                )
                return

            self.session = None  # force a fresh _init_session
            session = self._init_session()

            cookies = session_data if isinstance(session_data, dict) else {}
            if "cookies" in cookies and isinstance(cookies.get("cookies"), dict):
                cookies = cookies["cookies"]
            for name, value in cookies.items():
                if isinstance(value, str):
                    session.cookies.set(name, value)

            if self._validate_session():
                self.authenticated = True
                self.session_created_at = datetime.now()
                logger.info("✅ Lotte filter session restored from shared store")
            else:
                logger.warning(
                    "[lotte-filter] restored session failed validation, will re-auth on demand"
                )
                self.authenticated = False
                self.session = None
        except Exception as e:
            logger.error(f"[lotte-filter] error restoring session: {e}")
            self.authenticated = False

    def _load_shared_session(self) -> bool:
        """Hook called by auth_coordinator when another worker just authenticated."""
        try:
            session_data = self.session_manager.load_session("lotte")
            if not session_data:
                return False

            age = self.session_manager.get_session_age("lotte")
            if age and age > timedelta(minutes=self.session_max_age_minutes):
                return False

            self.session = None
            session = self._init_session()
            cookies = session_data if isinstance(session_data, dict) else {}
            if "cookies" in cookies and isinstance(cookies.get("cookies"), dict):
                cookies = cookies["cookies"]
            for name, value in cookies.items():
                if isinstance(value, str):
                    session.cookies.set(name, value)

            if self._validate_session():
                self.authenticated = True
                self.session_created_at = datetime.now()
                return True
            self.session = None
            return False
        except Exception as e:
            logger.debug(f"[lotte-filter] error loading shared session: {e}")
            return False

    def _authenticate(self) -> bool:
        """Cross-worker-safe re-auth via the shared auth_coordinator."""
        from app.core.auth_coordinator import ensure_authenticated
        return ensure_authenticated(self)

    def _ensure_session(self) -> bool:
        """Single entry point: returns True iff we have a valid authenticated session."""
        if self.authenticated and self.session and not self._is_session_expired():
            return True
        return self._authenticate()

    def _do_authenticate(self) -> bool:
        """Core 3-step Lotte login. Called by auth_coordinator under cross-worker lock.

        Returns True on success, False on non-retriable failure. Raises on retriable
        network/protocol failures so the coordinator can record state correctly.
        """
        # Force a fresh session so previous broken cookies don't poison the login flow.
        self.session = None
        session = self._init_session()

        login = settings.lotte_username
        password = settings.lotte_password

        logger.info(
            f"[lotte-filter] начинаем аутентификацию для пользователя: {login}"
        )

        # Step 1: GET login page (collect cookies + JSESSIONID).
        login_page_url = urljoin(self.base_url, self.login_url)
        response = session.get(login_page_url, timeout=30, verify=False)
        if response.status_code != 200:
            raise Exception(
                f"Lotte login page fetch failed: HTTP {response.status_code}"
            )
        logger.debug(
            f"[lotte-filter] login page fetched ({len(response.text)} chars)"
        )

        # Step 2: AJAX credential check.
        login_check_url = urljoin(self.base_url, self.login_check_url)
        login_check_data = {
            "userId": login,
            "userPwd": password,
            "resultCd": "",
        }
        session.headers.update({
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": login_page_url,
            "Accept": "application/json, text/javascript, */*; q=0.01",
        })
        check_response = session.post(
            login_check_url, data=login_check_data, timeout=30, verify=False
        )
        if check_response.status_code != 200:
            raise Exception(
                f"Lotte login check failed: HTTP {check_response.status_code}"
            )
        try:
            check_result = check_response.json()
        except json.JSONDecodeError as json_error:
            logger.error(
                f"[lotte-filter] login check non-JSON body[:500]={check_response.text[:500]!r}"
            )
            raise Exception(f"Lotte login check returned non-JSON: {json_error}")

        ok = check_result.get("resultCd") == "0000" or (
            not check_result.get("error")
            and not check_result.get("fail")
            and "auPswdUptEndYn" in check_result
        )
        if not ok:
            logger.error(f"[lotte-filter] login check rejected: {check_result}")
            return False

        # Step 3: final POST that actually establishes the auth cookie.
        login_action_url = urljoin(self.base_url, self.login_action_url)
        final_login_data = {"userId": login, "userPwd": password}
        session.headers.update({
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": login_page_url,
        })
        session.headers.pop("X-Requested-With", None)

        final_response = session.post(
            login_action_url,
            data=final_login_data,
            timeout=30,
            verify=False,
            allow_redirects=False,
        )
        if final_response.status_code not in (200, 302, 303):
            raise Exception(
                f"Lotte final login failed: HTTP {final_response.status_code}"
            )

        # Restore AJAX header for subsequent filter requests.
        session.headers["X-Requested-With"] = "XMLHttpRequest"

        # Validate cookies actually unlock protected pages.
        if not self._validate_session():
            raise Exception("Lotte login POST succeeded but session validation failed")

        logger.info("✅ Lotte filter authentication validated")
        return True

    def _make_request(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Выполнение POST запроса к API фильтров с аутентификацией"""
        try:
            if not self._ensure_session():
                logger.error("Не удалось аутентифицироваться для API фильтров")
                return None

            session = self._init_session()
            url = self.base_url + self.filter_url

            logger.info(f"Запрос к API фильтров: {data}")

            response = session.post(url, data=data, timeout=30, verify=False)

            if response.status_code == 200:
                try:
                    json_data = response.json()
                    logger.info(f"Получен ответ от API: {len(str(json_data))} символов")

                    # Detect a stale-session response and re-auth once.
                    if (
                        isinstance(json_data, dict)
                        and json_data.get("result") == "fail_notAuctLogin"
                    ):
                        logger.warning(
                            "Сессия истекла, требуется повторная аутентификация"
                        )
                        self.authenticated = False
                        self.session_created_at = None

                        if self._authenticate():
                            session = self._init_session()
                            response = session.post(
                                url, data=data, timeout=30, verify=False
                            )
                            if response.status_code == 200:
                                json_data = response.json()
                                logger.info(
                                    f"Повторный запрос успешен: {len(str(json_data))} символов"
                                )
                            else:
                                logger.error(
                                    f"Повторный запрос неудачен: HTTP {response.status_code}"
                                )
                                return None
                        else:
                            logger.error("Не удалось повторно аутентифицироваться")
                            return None

                    return json_data
                except json.JSONDecodeError:
                    logger.error("Ошибка декодирования JSON ответа")
                    return None
            else:
                logger.error(f"Ошибка HTTP {response.status_code}: {response.text}")
                return None

        except Exception as e:
            logger.error(f"Ошибка запроса к API фильтров: {e}")
            return None

    def get_manufacturers(self) -> LotteManufacturersResponse:
        """Получение списка производителей"""
        try:
            # Проверяем кэш
            cache_key = "manufacturers"
            if cache_key in self.cache:
                logger.info("Возвращаем производителей из кэша")
                return self.cache[cache_key]

            # Данные запроса для получения производителей
            data = {
                "searchFlag": "maker",
                "search_doimCd": "",
            }

            json_response = self._make_request(data)

            if json_response is None:
                return LotteManufacturersResponse(
                    success=False,
                    message="Не удалось получить данные от API",
                    manufacturers=[],
                    total_count=0,
                )

            manufacturers = self.parser.parse_manufacturers(json_response)

            response = LotteManufacturersResponse(
                success=True,
                message=f"Получено {len(manufacturers)} производителей",
                manufacturers=manufacturers,
                total_count=len(manufacturers),
            )

            # Сохраняем в кэш
            self.cache[cache_key] = response

            return response

        except Exception as e:
            logger.error(f"Ошибка получения производителей: {e}")
            return LotteManufacturersResponse(
                success=False,
                message=f"Ошибка: {str(e)}",
                manufacturers=[],
                total_count=0,
            )

    def get_models(self, manufacturer_code: str) -> LotteModelsResponse:
        """Получение списка моделей для производителя"""
        try:
            # Проверяем кэш
            cache_key = f"models_{manufacturer_code}"
            if cache_key in self.cache:
                logger.info(f"Возвращаем модели для {manufacturer_code} из кэша")
                return self.cache[cache_key]

            # Данные запроса для получения моделей
            data = {
                "searchFlag": "mdl",
                "searchCode": manufacturer_code,
            }

            json_response = self._make_request(data)

            if json_response is None:
                return LotteModelsResponse(
                    success=False,
                    message="Не удалось получить данные от API",
                    models=[],
                    manufacturer_code=manufacturer_code,
                    total_count=0,
                )

            models = self.parser.parse_models(json_response, manufacturer_code)

            response = LotteModelsResponse(
                success=True,
                message=f"Получено {len(models)} моделей для {manufacturer_code}",
                models=models,
                manufacturer_code=manufacturer_code,
                total_count=len(models),
            )

            # Сохраняем в кэш
            self.cache[cache_key] = response

            return response

        except Exception as e:
            logger.error(f"Ошибка получения моделей для {manufacturer_code}: {e}")
            return LotteModelsResponse(
                success=False,
                message=f"Ошибка: {str(e)}",
                models=[],
                manufacturer_code=manufacturer_code,
                total_count=0,
            )

    def get_car_groups(self, model_code: str) -> LotteCarGroupsResponse:
        """Получение списка групп автомобилей для модели"""
        try:
            # Проверяем кэш
            cache_key = f"car_groups_{model_code}"
            if cache_key in self.cache:
                logger.info(f"Возвращаем группы для {model_code} из кэша")
                return self.cache[cache_key]

            # Данные запроса для получения групп
            data = {
                "searchFlag": "carGrp",
                "searchCode": model_code,
            }

            json_response = self._make_request(data)

            if json_response is None:
                return LotteCarGroupsResponse(
                    success=False,
                    message="Не удалось получить данные от API",
                    car_groups=[],
                    model_code=model_code,
                    total_count=0,
                )

            car_groups = self.parser.parse_car_groups(json_response, model_code)

            response = LotteCarGroupsResponse(
                success=True,
                message=f"Получено {len(car_groups)} групп для {model_code}",
                car_groups=car_groups,
                model_code=model_code,
                total_count=len(car_groups),
            )

            # Сохраняем в кэш
            self.cache[cache_key] = response

            return response

        except Exception as e:
            logger.error(f"Ошибка получения групп для {model_code}: {e}")
            return LotteCarGroupsResponse(
                success=False,
                message=f"Ошибка: {str(e)}",
                car_groups=[],
                model_code=model_code,
                total_count=0,
            )

    def get_mprice_cars(self, car_group_code: str) -> LotteMPriceCarsResponse:
        """Получение списка подмоделей с ценами для группы"""
        try:
            # Проверяем кэш
            cache_key = f"mprice_cars_{car_group_code}"
            if cache_key in self.cache:
                logger.info(f"Возвращаем подмодели для {car_group_code} из кэша")
                return self.cache[cache_key]

            # Данные запроса для получения подмоделей
            data = {
                "searchFlag": "mpriceCar",
                "searchCode": car_group_code,
            }

            json_response = self._make_request(data)

            if json_response is None:
                return LotteMPriceCarsResponse(
                    success=False,
                    message="Не удалось получить данные от API",
                    mprice_cars=[],
                    car_group_code=car_group_code,
                    total_count=0,
                )

            mprice_cars = self.parser.parse_mprice_cars(json_response, car_group_code)

            response = LotteMPriceCarsResponse(
                success=True,
                message=f"Получено {len(mprice_cars)} подмоделей для {car_group_code}",
                mprice_cars=mprice_cars,
                car_group_code=car_group_code,
                total_count=len(mprice_cars),
            )

            # Сохраняем в кэш
            self.cache[cache_key] = response

            return response

        except Exception as e:
            logger.error(f"Ошибка получения подмоделей для {car_group_code}: {e}")
            return LotteMPriceCarsResponse(
                success=False,
                message=f"Ошибка: {str(e)}",
                mprice_cars=[],
                car_group_code=car_group_code,
                total_count=0,
            )

    def clear_cache(self):
        """Очистка кэша"""
        self.cache.clear()
        logger.info("Кэш фильтров очищен")
    
    def reset_authentication(self):
        """Сброс состояния аутентификации"""
        self.authenticated = False
        self.session = None
        logger.info("Аутентификация Lotte Filter Service сброшена")

    def search_cars(self, filter_request: LotteFilterRequest) -> Dict[str, Any]:
        """
        Поиск автомобилей с применением фильтров

        Args:
            filter_request: Параметры фильтрации

        Returns:
            Dict с результатами поиска или ошибкой
        """
        try:
            logger.info(f"Поиск автомобилей с фильтрами: {filter_request.model_dump()}")

            exhi_norm = _normalize_exhibition_number(filter_request.exhibition_number)
            if filter_request.exhibition_number and filter_request.exhibition_number != exhi_norm:
                logger.info(
                    f"[lotte] exhibition_number normalized: '{filter_request.exhibition_number}' -> '{exhi_norm}'"
                )

            # Подготовка данных для поиска — всегда включаем все поля (как реальная форма Lotte)
            search_data = {
                "searchPageUnit": str(filter_request.per_page),
                "pageIndex": str(filter_request.page),
                "search_grntVal": "",
                "search_concVal": "",
                "search_preVal": "",
                "excelDiv": "",
                "searchLaneDiv": filter_request.lane_division or "",
                "search_doimCd": filter_request.production_origin or "",
                "search_exhiNo": exhi_norm,
                "set_search_maker": filter_request.manufacturer_code or "",
                "set_search_mdl": filter_request.model_code or "",
                "searchAuctDt": filter_request.auction_date or "",
                "search_startPrice": str(filter_request.min_price) if filter_request.min_price is not None else "",
                "search_endPrice": str(filter_request.max_price) if filter_request.max_price is not None else "",
                "search_startYyyy": str(filter_request.min_year) if filter_request.min_year is not None else "",
                "search_endYyyy": str(filter_request.max_year) if filter_request.max_year is not None else "",
                "search_fuelCd": filter_request.fuel_code or "",
                "search_trnsCd": filter_request.transmission_code or "",
            }

            # Группа автомобилей (одиночный выбор)
            if filter_request.car_group_code:
                search_data["set_search_chk_carGrp"] = filter_request.car_group_code

            # Подмодели с ценами (множественный выбор — список для requests)
            if filter_request.mprice_car_codes:
                search_data["set_search_chk_mpriceCar"] = filter_request.mprice_car_codes

            # Выполняем поиск
            session = self._init_session()

            # Обновляем headers для поиска (отличаются от фильтров)
            search_headers = self.headers.copy()
            search_headers.update(
                {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-User": "?1",
                    "Upgrade-Insecure-Requests": "1",
                }
            )

            search_url = self.base_url + self.search_url

            logger.info(f"Выполняем поиск по URL: {search_url}")
            logger.info(f"Данные поиска: {search_data}")

            response = session.post(
                search_url,
                data=search_data,
                headers=search_headers,
                timeout=30,
                verify=False,
            )

            if response.status_code == 200:
                # Возвращаем HTML для дальнейшего парсинга
                return {
                    "success": True,
                    "html_content": response.text,
                    "search_params": search_data,
                    "total_length": len(response.text),
                    "message": f"Поиск выполнен успешно. Получено {len(response.text)} символов HTML",
                }
            else:
                logger.error(
                    f"Ошибка поиска HTTP {response.status_code}: {response.text[:500]}"
                )
                return {
                    "success": False,
                    "error_code": "SEARCH_HTTP_ERROR",
                    "message": f"HTTP ошибка {response.status_code}",
                    "search_params": search_data,
                }

        except Exception as e:
            logger.error(f"Ошибка поиска автомобилей: {e}")
            return {
                "success": False,
                "error_code": "SEARCH_EXCEPTION",
                "message": f"Ошибка поиска: {str(e)}",
                "search_params": filter_request.model_dump() if filter_request else {},
            }

    def search_cars_with_parsing(
        self, filter_request: LotteFilterRequest
    ) -> LotteSearchResponse:
        """
        Поиск автомобилей с полным парсингом результатов

        Args:
            filter_request: Параметры фильтрации и поиска

        Returns:
            LotteSearchResponse с результатами поиска
        """
        try:
            logger.info(f"Поиск автомобилей с парсингом: {filter_request.model_dump()}")

            exhi_norm = _normalize_exhibition_number(filter_request.exhibition_number)
            if filter_request.exhibition_number and filter_request.exhibition_number != exhi_norm:
                logger.info(
                    f"[lotte] exhibition_number normalized: '{filter_request.exhibition_number}' -> '{exhi_norm}'"
                )

            # Подготовка данных для поиска — всегда включаем все поля (как реальная форма Lotte)
            search_data = {
                "searchPageUnit": str(filter_request.per_page),
                "pageIndex": str(filter_request.page),
                "search_grntVal": "",
                "search_concVal": "",
                "search_preVal": "",
                "excelDiv": "",
                "searchLaneDiv": filter_request.lane_division or "",
                "search_doimCd": filter_request.production_origin or "",
                "search_exhiNo": exhi_norm,
                "set_search_maker": filter_request.manufacturer_code or "",
                "set_search_mdl": filter_request.model_code or "",
                "searchAuctDt": filter_request.auction_date or "",
                "search_startPrice": str(filter_request.min_price) if filter_request.min_price is not None else "",
                "search_endPrice": str(filter_request.max_price) if filter_request.max_price is not None else "",
                "search_startYyyy": str(filter_request.min_year) if filter_request.min_year is not None else "",
                "search_endYyyy": str(filter_request.max_year) if filter_request.max_year is not None else "",
                "search_fuelCd": filter_request.fuel_code or "",
                "search_trnsCd": filter_request.transmission_code or "",
            }

            # Группа автомобилей (одиночный выбор)
            if filter_request.car_group_code:
                search_data["set_search_chk_carGrp"] = filter_request.car_group_code

            # Подмодели с ценами (множественный выбор — список для requests)
            if filter_request.mprice_car_codes:
                search_data["set_search_chk_mpriceCar"] = filter_request.mprice_car_codes

            # Ensure a valid session up front. _ensure_session re-auths only if
            # cookies are stale; cheap on the warm path.
            if not self._ensure_session():
                logger.error("[lotte-filter] pre-search authentication failed")
                return LotteSearchResponse(
                    success=False,
                    message=(
                        "Сессия Lotte истекла, идёт восстановление. "
                        "Попробуйте через минуту."
                    ),
                    error_code="SESSION_REAUTH_FAILED",
                    cars=[],
                    total_count=0,
                    page=filter_request.page,
                    per_page=filter_request.per_page,
                    filters_applied=filter_request.model_dump(),
                )
            session = self._init_session()

            # Обновляем headers для поиска
            search_headers = self.headers.copy()
            search_headers.update(
                {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-User": "?1",
                    "Upgrade-Insecure-Requests": "1",
                }
            )

            search_url = self.base_url + self.search_url

            logger.info(f"Выполняем поиск по URL: {search_url}")

            def _do_post():
                return session.post(
                    search_url,
                    data=search_data,
                    headers=search_headers,
                    timeout=30,
                    verify=False,
                )

            response = _do_post()

            if response.status_code != 200:
                logger.error(
                    f"[lotte-filter] search HTTP {response.status_code}, "
                    f"body[:500]={response.text[:500]!r}"
                )
                return LotteSearchResponse(
                    success=False,
                    message=(
                        f"Сервер Lotte вернул ошибку (HTTP {response.status_code}). "
                        "Попробуйте позже."
                    ),
                    error_code="UPSTREAM_HTTP_ERROR",
                    cars=[],
                    total_count=0,
                    page=filter_request.page,
                    per_page=filter_request.per_page,
                    filters_applied=filter_request.model_dump(),
                )

            # Парсим HTML результаты + получаем статус, чтобы отличить
            # реальный пустой ответ от поломки разметки/протухшей сессии.
            html_content = response.text
            cars, parse_status = self.parser.parse_car_search_html_with_status(html_content)

            # Detect a silently-expired Lotte session: either the parser couldn't
            # find tbl-t02 OR the body explicitly looks like the login redirect /
            # `fail_notAuctLogin` JSON. Re-auth once and retry — this is the single
            # most common production failure mode (shared-backend cookie aging,
            # parallel worker invalidation, etc.). Applies to ALL filter searches,
            # not just lot-number lookups.
            looks_like_login = self._is_login_page(html_content)
            if parse_status == "no_table" or looks_like_login:
                logger.warning(
                    f"[lotte-filter] stale-session signature detected "
                    f"(parse_status={parse_status}, login_page={looks_like_login}); "
                    f"attempting re-auth + retry"
                )
                self.authenticated = False
                self.session_created_at = None
                if self._authenticate():
                    session = self._init_session()
                    response = _do_post()
                    if response.status_code == 200:
                        html_content = response.text
                        cars, parse_status = self.parser.parse_car_search_html_with_status(
                            html_content
                        )
                        looks_like_login = self._is_login_page(html_content)
                    else:
                        logger.error(
                            f"[lotte-filter] post-reauth retry HTTP {response.status_code}"
                        )

            if parse_status != "ok":
                # Distinguish a still-stale session (login page) from a true markup
                # change so the frontend can show different copy / retry behaviour.
                if looks_like_login or parse_status == "no_table":
                    final_code = "SESSION_EXPIRED" if looks_like_login else "PARSE_NO_TABLE"
                    user_msg = (
                        "Сессия Lotte истекла, идёт восстановление. "
                        "Попробуйте через минуту."
                        if final_code == "SESSION_EXPIRED"
                        else "Lotte изменил разметку страницы. Мы уже разбираемся."
                    )
                elif parse_status == "no_tbody":
                    final_code = "PARSE_NO_TBODY"
                    user_msg = "Lotte изменил разметку страницы. Мы уже разбираемся."
                else:
                    final_code = "PARSE_ERROR"
                    user_msg = "Не удалось обработать ответ Lotte. Попробуйте позже."

                logger.error(
                    f"[lotte-filter] search parse failed status={parse_status} "
                    f"final_code={final_code} body[:500]={response.text[:500]!r}"
                )
                return LotteSearchResponse(
                    success=False,
                    message=user_msg,
                    error_code=final_code,
                    cars=[],
                    total_count=0,
                    page=filter_request.page,
                    per_page=filter_request.per_page,
                    filters_applied=filter_request.model_dump(),
                )

            total_count = self.parser.extract_total_count(html_content)

            # Рассчитываем пагинацию
            total_pages = (
                total_count + filter_request.per_page - 1
            ) // filter_request.per_page
            has_next = filter_request.page < total_pages
            has_previous = filter_request.page > 1

            response_data = LotteSearchResponse(
                success=True,
                message=f"Найдено {len(cars)} автомобилей из {total_count} общих",
                cars=cars,
                total_count=total_count,
                page=filter_request.page,
                per_page=filter_request.per_page,
                total_pages=total_pages,
                has_next=has_next,
                has_previous=has_previous,
                filters_applied=filter_request.model_dump(),
            )

            logger.info(f"Поиск завершен: {len(cars)} автомобилей, всего {total_count}")
            return response_data

        except Exception as e:
            logger.error(f"Ошибка поиска автомобилей с парсингом: {e}")
            return LotteSearchResponse(
                success=False,
                message=f"Ошибка поиска: {str(e)}",
                error_code="SEARCH_EXCEPTION",
                cars=[],
                total_count=0,
                page=filter_request.page,
                per_page=filter_request.per_page,
                filters_applied=filter_request.model_dump(),
            )
