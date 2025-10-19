import requests
import json
from typing import List, Optional, Dict, Any
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from urllib.parse import urljoin
import warnings

from app.core.config import settings
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


class LotteFilterService:
    """Сервис для работы с фильтрами Lotte"""

    def __init__(self):
        self.base_url = "https://www.lotteautoauction.net"
        self.parser = LotteFilterParser()
        self.session = None
        self.authenticated = False
        self.cache = {}
        self.cache_ttl = 3600  # 1 час для фильтров
        
        # Disable SSL warnings
        warnings.filterwarnings('ignore', message='Unverified HTTPS request')

        # URL для API фильтров и аутентификации
        self.filter_url = "/hp/auct/myp/entry/selectMultiComboVehi.do"
        self.search_url = "/hp/auct/myp/entry/selectMypEntryList.do"
        
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
    
    def _authenticate(self) -> bool:
        """Аутентификация в системе Lotte (двухэтапный процесс)"""
        try:
            session = self._init_session()
            
            # Логин и пароль из конфига
            login = settings.lotte_username
            password = settings.lotte_password
            
            logger.info(f"Начинаем аутентификацию в Lotte Filter Service для пользователя: {login}")
            
            # Шаг 1: Получаем страницу логина для получения cookies и сессии
            login_page_url = urljoin(self.base_url, self.login_url)
            response = session.get(login_page_url, timeout=30, verify=False)
            
            if response.status_code != 200:
                logger.error(f"Не удалось получить страницу логина: HTTP {response.status_code}")
                return False
            
            logger.debug(f"Страница логина получена, размер: {len(response.text)} символов")
            
            # Шаг 2: Проверяем логин данные через AJAX
            login_check_url = urljoin(self.base_url, self.login_check_url)
            
            # Подготавливаем данные для проверки логина
            login_check_data = {
                "userId": login,
                "userPwd": password,
                "resultCd": "",
            }
            
            # Обновляем headers для AJAX запроса
            session.headers.update({
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": login_page_url,
                "Accept": "application/json, text/javascript, */*; q=0.01",
            })
            
            # Отправляем AJAX запрос для проверки логина
            check_response = session.post(
                login_check_url, data=login_check_data, timeout=30, verify=False
            )
            
            logger.debug(f"Проверка логина: HTTP {check_response.status_code}")
            
            if check_response.status_code != 200:
                logger.error(f"Ошибка проверки логина: HTTP {check_response.status_code}")
                return False
            
            # Проверяем результат
            try:
                check_result = check_response.json()
                logger.debug(f"Результат проверки логина: {check_result}")
                
                # Lotte возвращает пустой объект или специфичные поля при успехе
                # Проверяем отсутствие ошибок
                if check_result.get("resultCd") == "0000" or (
                    not check_result.get("error") and 
                    not check_result.get("fail") and
                    "auPswdUptEndYn" in check_result
                ):
                    logger.info("Проверка логина прошла успешно")
                    
                    # Шаг 3: Финальный логин
                    login_action_url = urljoin(self.base_url, self.login_action_url)
                    
                    # Данные для финального логина
                    final_login_data = {
                        "userId": login,
                        "userPwd": password,
                    }
                    
                    # Обновляем headers для финального логина
                    session.headers.update({
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Referer": login_page_url,
                    })
                    # Удаляем AJAX заголовок
                    if "X-Requested-With" in session.headers:
                        del session.headers["X-Requested-With"]
                    
                    final_response = session.post(
                        login_action_url,
                        data=final_login_data,
                        timeout=30,
                        verify=False,
                    )
                    
                    logger.debug(f"Финальный логин: HTTP {final_response.status_code}")
                    
                    if final_response.status_code in [200, 302, 303]:
                        self.authenticated = True
                        logger.info("✅ Аутентификация в Lotte Filter Service успешна!")
                        logger.debug(f"Cookies после аутентификации: {session.cookies.get_dict()}")
                        
                        # Восстанавливаем заголовок для последующих запросов
                        session.headers["X-Requested-With"] = "XMLHttpRequest"
                        
                        return True
                    else:
                        logger.error(f"Неожиданный статус финального логина: {final_response.status_code}")
                        return False
                else:
                    logger.error(f"Неверный результат проверки логина: {check_result}")
                    return False
                    
            except json.JSONDecodeError as json_error:
                logger.error(f"Ошибка при разборе ответа: {json_error}")
                logger.error(f"Текст ответа: {check_response.text[:500]}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка аутентификации: {e}")
            return False

    def _make_request(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Выполнение POST запроса к API фильтров с аутентификацией"""
        try:
            # Проверяем аутентификацию
            if not self.authenticated:
                logger.info("Требуется аутентификация для API фильтров")
                if not self._authenticate():
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
                    
                    # Проверяем, не истекла ли сессия
                    if isinstance(json_data, dict) and json_data.get("result") == "fail_notAuctLogin":
                        logger.warning("Сессия истекла, требуется повторная аутентификация")
                        self.authenticated = False
                        
                        # Пробуем аутентифицироваться заново
                        if self._authenticate():
                            # Повторяем запрос после успешной аутентификации
                            response = session.post(url, data=data, timeout=30, verify=False)
                            if response.status_code == 200:
                                json_data = response.json()
                                logger.info(f"Повторный запрос успешен: {len(str(json_data))} символов")
                            else:
                                logger.error(f"Повторный запрос неудачен: HTTP {response.status_code}")
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

            # Подготовка данных для поиска на основе примера results.py
            search_data = {
                "searchPageUnit": str(filter_request.per_page),
                "pageIndex": str(filter_request.page),
                "search_grntVal": "",
                "search_concVal": "",
                "search_preVal": "",
                "excelDiv": "",
                "searchLaneDiv": filter_request.lane_division or "",
                "search_doimCd": "",
                "search_exhiNo": filter_request.exhibition_number or "",
            }

            # Основные фильтры
            if filter_request.manufacturer_code:
                search_data["set_search_maker"] = filter_request.manufacturer_code

            if filter_request.model_code:
                search_data["set_search_mdl"] = filter_request.model_code

            # Дата аукциона
            if filter_request.auction_date:
                search_data["searchAuctDt"] = filter_request.auction_date

            # Ценовые фильтры
            if filter_request.min_price is not None:
                search_data["search_startPrice"] = str(filter_request.min_price)
                search_data["search_startPrice_s"] = str(filter_request.min_price)

            if filter_request.max_price is not None:
                search_data["search_endPrice"] = str(filter_request.max_price)
                search_data["search_endPrice_s"] = str(filter_request.max_price)

            # Год выпуска
            if filter_request.min_year is not None:
                search_data["search_startYyyy"] = str(filter_request.min_year)

            if filter_request.max_year is not None:
                search_data["search_endYyyy"] = str(filter_request.max_year)

            # Тип топлива и трансмиссия
            if filter_request.fuel_code:
                search_data["search_fuelCd"] = filter_request.fuel_code

            if filter_request.transmission_code:
                search_data["search_trnsCd"] = filter_request.transmission_code

            # Группа автомобилей (одиночный выбор)
            if filter_request.car_group_code:
                search_data["set_search_chk_carGrp"] = filter_request.car_group_code

            # Подмодели с ценами (множественный выбор)
            if filter_request.mprice_car_codes:
                search_data["set_search_chk_mpriceCar"] = (
                    filter_request.mprice_car_codes
                )

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

            # Подготовка данных для поиска
            search_data = {
                "searchPageUnit": str(filter_request.per_page),
                "pageIndex": str(filter_request.page),
                "search_grntVal": "",
                "search_concVal": "",
                "search_preVal": "",
                "excelDiv": "",
                "searchLaneDiv": filter_request.lane_division or "",
                "search_doimCd": "",
                "search_exhiNo": filter_request.exhibition_number or "",
            }

            # Основные фильтры
            if filter_request.manufacturer_code:
                search_data["set_search_maker"] = filter_request.manufacturer_code

            if filter_request.model_code:
                search_data["set_search_mdl"] = filter_request.model_code

            # Дата аукциона
            if filter_request.auction_date:
                search_data["searchAuctDt"] = filter_request.auction_date

            # Ценовые фильтры
            if filter_request.min_price is not None:
                search_data["search_startPrice"] = str(filter_request.min_price)
                search_data["search_startPrice_s"] = str(filter_request.min_price)

            if filter_request.max_price is not None:
                search_data["search_endPrice"] = str(filter_request.max_price)
                search_data["search_endPrice_s"] = str(filter_request.max_price)

            # Год выпуска
            if filter_request.min_year is not None:
                search_data["search_startYyyy"] = str(filter_request.min_year)

            if filter_request.max_year is not None:
                search_data["search_endYyyy"] = str(filter_request.max_year)

            # Тип топлива и трансмиссия
            if filter_request.fuel_code:
                search_data["search_fuelCd"] = filter_request.fuel_code

            if filter_request.transmission_code:
                search_data["search_trnsCd"] = filter_request.transmission_code

            # Группа автомобилей (одиночный выбор)
            if filter_request.car_group_code:
                search_data["set_search_chk_carGrp"] = filter_request.car_group_code

            # Подмодели с ценами (множественный выбор)
            if filter_request.mprice_car_codes:
                search_data["set_search_chk_mpriceCar"] = filter_request.mprice_car_codes

            # Выполняем поиск
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

            response = session.post(
                search_url,
                data=search_data,
                headers=search_headers,
                timeout=30,
                verify=False,
            )

            if response.status_code != 200:
                logger.error(f"Ошибка поиска HTTP {response.status_code}")
                return LotteSearchResponse(
                    success=False,
                    message=f"HTTP ошибка {response.status_code}",
                    cars=[],
                    total_count=0,
                    page=filter_request.page,
                    per_page=filter_request.per_page,
                    filters_applied=filter_request.model_dump(),
                )

            # Парсим HTML результаты
            html_content = response.text
            cars = self.parser.parse_car_search_html(html_content)
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
                cars=[],
                total_count=0,
                page=filter_request.page,
                per_page=filter_request.per_page,
                filters_applied=filter_request.model_dump(),
            )
