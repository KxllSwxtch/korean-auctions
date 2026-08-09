import os
import json
import warnings
from typing import List, Optional, Dict, Any, Tuple, TYPE_CHECKING

import requests

from app.core.logging import logger
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
from app.core.tls import REQUESTS_VERIFY

if TYPE_CHECKING:
    from app.services.lotte_service import LotteService


# Repo-root data file: verbatim manufacturers list captured from a live Lotte
# session, used as a resilience fallback when the live combo API is momentarily
# unavailable. Mirrors the SSANCAR `ssancar_carlist.json` static-data pattern.
_FALLBACK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "lotte_manufacturers_fallback.json",
)
_MANUFACTURERS_FALLBACK: Optional[List[Dict[str, str]]] = None


def _load_manufacturers_fallback() -> List[Dict[str, str]]:
    """Load (once, cached) the bundled manufacturers fallback list."""
    global _MANUFACTURERS_FALLBACK
    if _MANUFACTURERS_FALLBACK is not None:
        return _MANUFACTURERS_FALLBACK
    try:
        with open(_FALLBACK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("manufacturers", []) if isinstance(data, dict) else []
        _MANUFACTURERS_FALLBACK = [
            {"code": e["code"], "name": e["name"]}
            for e in entries
            if isinstance(e, dict) and e.get("code") and e.get("name")
        ]
        logger.info(
            f"[lotte-filter] loaded {len(_MANUFACTURERS_FALLBACK)} fallback manufacturers"
        )
    except Exception as e:
        logger.error(f"[lotte-filter] failed to load manufacturers fallback: {e}")
        _MANUFACTURERS_FALLBACK = []
    return _MANUFACTURERS_FALLBACK


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
    """Сервис для работы с фильтрами Lotte.

    Auth/session are NOT owned here — this service reuses the single authenticated
    session that LotteService already keeps valid (constructor-injected). One
    account → one session → one login path. This deletes the diverged auth copy
    that caused the filters 500 and removes the "two concurrent logins for one
    account" hazard.
    """

    def __init__(self, lotte_service: "LotteService"):
        # Reuse the proven, already-authenticated LotteService session/cookies.
        self.main_service = lotte_service

        self.base_url = "https://www.lotteautoauction.net"
        self.parser = LotteFilterParser()
        self.cache = {}
        self.cache_ttl = 3600  # 1 час для фильтров

        # Disable SSL warnings
        warnings.filterwarnings('ignore', message='Unverified HTTPS request')

        # Combo-filter + search endpoints.
        self.filter_url = "/hp/auct/myp/entry/selectMultiComboVehi.do"
        self.search_url = "/hp/auct/myp/entry/selectMypEntryList.do"

        # AJAX headers for the combo-filter endpoint. Passed EXPLICITLY on each
        # request (never mutated onto the shared session, which carries the main
        # service's navigation headers).
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

    # ---- Session/auth delegated to the proven LotteService ----
    def _init_session(self) -> requests.Session:
        """Reuse the main service's authenticated, connection-pooled session."""
        return self.main_service._init_session()

    def _ensure_session(self) -> bool:
        """True iff a valid authenticated Lotte session is available (delegated)."""
        return self.main_service._ensure_session()

    def _is_login_page(self, html: str) -> bool:
        """Detect a Lotte login redirect / fail_notAuctLogin marker in a response body."""
        if not html:
            return False
        return any(marker in html for marker in _LOTTE_LOGIN_PAGE_MARKERS)

    def _make_request(
        self, data: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """POST to the Lotte combo-filter endpoint on the shared session.

        Returns (json_data, None) on success, or (None, error_code) on failure.
        error_code ∈ {SESSION_REAUTH_FAILED, UPSTREAM_HTTP_ERROR, PARSE_ERROR}.
        Headers are passed explicitly per request so the shared (navigation-header)
        session is never mutated.
        """
        url = self.base_url + self.filter_url

        def _post() -> requests.Response:
            return self._init_session().post(
                url, data=data, headers=self.headers, timeout=30, verify=REQUESTS_VERIFY
            )

        try:
            if not self._ensure_session():
                logger.error("[lotte-filter] authentication failed for combo API")
                return None, "SESSION_REAUTH_FAILED"

            logger.info(f"[lotte-filter] combo request: {data}")
            response = _post()

            # Stale-session recovery. A dead Lotte session answers either with an
            # HTML login redirect OR a `fail_notAuctLogin` marker — `_is_login_page`
            # detects both. Invalidate the shared session, re-auth once, retry.
            if response.status_code == 200 and self._is_login_page(response.text):
                logger.warning(
                    "[lotte-filter] stale-session signature on combo API; re-auth + retry"
                )
                self.main_service.invalidate_session()
                if not self._ensure_session():
                    logger.error("[lotte-filter] re-auth failed after stale session")
                    return None, "SESSION_REAUTH_FAILED"
                response = _post()
                if response.status_code == 200 and self._is_login_page(response.text):
                    logger.error("[lotte-filter] combo API still stale after re-auth")
                    return None, "SESSION_REAUTH_FAILED"

            if response.status_code != 200:
                logger.error(
                    f"[lotte-filter] combo API HTTP {response.status_code}: "
                    f"{response.text[:300]!r}"
                )
                return None, "UPSTREAM_HTTP_ERROR"

            try:
                json_data = response.json()
            except json.JSONDecodeError:
                logger.error(
                    f"[lotte-filter] combo API returned non-JSON: {response.text[:300]!r}"
                )
                return None, "PARSE_ERROR"

            logger.info(f"[lotte-filter] combo API ok ({len(str(json_data))} chars)")
            return json_data, None

        except Exception as e:
            logger.error(f"[lotte-filter] combo API request error: {e}")
            return None, "UPSTREAM_HTTP_ERROR"

    def _static_manufacturers_fallback(self) -> List[LotteManufacturer]:
        """Bundled manufacturers list, served only when the live combo API is down.

        Names are cleaned with the same parser rule as the live path so the
        fallback is indistinguishable from a live response to the frontend.
        """
        return [
            LotteManufacturer(code=m["code"], name=self.parser._clean_name(m["name"]))
            for m in _load_manufacturers_fallback()
        ]

    def get_manufacturers(self) -> LotteManufacturersResponse:
        """Получение списка производителей (live, с резервным списком)."""
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

            json_response, error_code = self._make_request(data)

            if json_response is None:
                # Live session unavailable — serve the bundled list so the dropdown
                # always populates. Do NOT cache a stale fallback, or a brief outage
                # would pin the dropdown to stale data for the full TTL.
                fallback = self._static_manufacturers_fallback()
                if fallback:
                    logger.warning(
                        f"[lotte-filter] manufacturers live fetch failed "
                        f"({error_code}); serving {len(fallback)} from static fallback"
                    )
                    return LotteManufacturersResponse(
                        success=True,
                        message="Список производителей (резервные данные)",
                        manufacturers=fallback,
                        total_count=len(fallback),
                        error_code=error_code,
                        source="static_fallback",
                        stale=True,
                    )
                return LotteManufacturersResponse(
                    success=False,
                    message="Не удалось получить данные от API",
                    manufacturers=[],
                    total_count=0,
                    error_code=error_code,
                )

            manufacturers = self.parser.parse_manufacturers(json_response)

            response = LotteManufacturersResponse(
                success=True,
                message=f"Получено {len(manufacturers)} производителей",
                manufacturers=manufacturers,
                total_count=len(manufacturers),
                source="live",
            )

            # Cache LIVE responses only.
            self.cache[cache_key] = response

            return response

        except Exception as e:
            logger.error(f"Ошибка получения производителей: {e}")
            return LotteManufacturersResponse(
                success=False,
                message=f"Ошибка: {str(e)}",
                manufacturers=[],
                total_count=0,
                error_code="PARSE_ERROR",
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

            json_response, error_code = self._make_request(data)

            if json_response is None:
                return LotteModelsResponse(
                    success=False,
                    message="Не удалось получить данные от API",
                    models=[],
                    manufacturer_code=manufacturer_code,
                    total_count=0,
                    error_code=error_code,
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

            json_response, error_code = self._make_request(data)

            if json_response is None:
                return LotteCarGroupsResponse(
                    success=False,
                    message="Не удалось получить данные от API",
                    car_groups=[],
                    model_code=model_code,
                    total_count=0,
                    error_code=error_code,
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

            json_response, error_code = self._make_request(data)

            if json_response is None:
                return LotteMPriceCarsResponse(
                    success=False,
                    message="Не удалось получить данные от API",
                    mprice_cars=[],
                    car_group_code=car_group_code,
                    total_count=0,
                    error_code=error_code,
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
        """Drop the shared session so the next request re-authenticates (delegated)."""
        self.main_service.reset_authentication()
        logger.info("Аутентификация Lotte Filter Service сброшена (delegated)")

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
                verify=REQUESTS_VERIFY,
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
                    verify=REQUESTS_VERIFY,
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

            # Detect a silently-expired Lotte session and re-auth once. A stale
            # session returns the login page, which has no tbl-t02 → parse_status
            # == "no_table". A successfully-parsed results table (parse_status ==
            # "ok") is NEVER a login page: Lotte's list pages embed a login
            # link/modal in the markup even when authenticated, so `_is_login_page`
            # alone is a FALSE POSITIVE on valid (including zero-result) pages.
            # Gating on `parse_status != "ok"` stops an empty result from needlessly
            # churning the shared session.
            looks_like_login = self._is_login_page(html_content)
            stale_session = parse_status == "no_table" or (
                looks_like_login and parse_status != "ok"
            )
            if stale_session:
                logger.warning(
                    f"[lotte-filter] stale-session signature detected "
                    f"(parse_status={parse_status}, login_page={looks_like_login}); "
                    f"attempting re-auth + retry"
                )
                self.main_service.invalidate_session()
                if self._ensure_session():
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
