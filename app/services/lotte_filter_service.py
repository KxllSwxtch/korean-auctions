import requests
import json
from typing import List, Optional, Dict, Any
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

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

        # URL для API фильтров
        self.filter_url = "/hp/auct/myp/entry/selectMultiComboVehi.do"
        self.search_url = "/hp/auct/myp/entry/selectMypEntryList.do"

        # Cookies и headers из примеров - обновленные значения
        self.cookies = {
            "_xm_webid_1_": "-1226978328",
            "_gid": "GA1.2.346177550.1751701164",
            "hpAuctSaveid": "119102",
            "JSESSIONID": "jUEw5UsaMaAAMInWwGazuTRhV1LNbkgFlA2N1O14zgXGCgnOl2P8w23YFAgqhwpO.UlBBQV9kb21haW4vUlBBQV9IUEdfTjIx",
            "_gat_gtag_UA_118654321_1": "1",
            "_ga_BG67GSX5WV": "GS2.1.s1751707181$o12$g1$t1751708033$j59$l0$h0",
            "_ga": "GA1.1.1122542401.1749522854",
        }

        self.headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://www.lotteautoauction.net",
            "Referer": "https://www.lotteautoauction.net/hp/cmm/actionMenuLinkPage.do?baseMenuNo=1010000&link=forward%3A%2Fhp%2Fauct%2Fmyp%2Fentry%2FselectMypEntryList.do&redirectMode=&popHeight=&popWidth=&subMenuNo=1010200&subSubMenuNo=",
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

            # Устанавливаем cookies и headers
            self.session.cookies.update(self.cookies)
            self.session.headers.update(self.headers)

        return self.session

    def _make_request(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Выполнение POST запроса к API фильтров"""
        try:
            session = self._init_session()
            url = self.base_url + self.filter_url

            logger.info(f"Запрос к API фильтров: {data}")

            response = session.post(url, data=data, timeout=30, verify=False)

            if response.status_code == 200:
                try:
                    json_data = response.json()
                    logger.info(f"Получен ответ от API: {len(str(json_data))} символов")
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

            # Группы автомобилей (множественный выбор)
            if filter_request.car_group_codes:
                # Для одной группы
                if len(filter_request.car_group_codes) == 1:
                    search_data["set_search_chk_carGrp"] = (
                        filter_request.car_group_codes[0]
                    )
                else:
                    # Для множественных групп используем массив
                    search_data["set_search_chk_carGrp"] = (
                        filter_request.car_group_codes
                    )

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
        self, search_request: LotteSearchRequest
    ) -> LotteSearchResponse:
        """
        Поиск автомобилей с полным парсингом результатов

        Args:
            search_request: Параметры поиска

        Returns:
            LotteSearchResponse с результатами поиска
        """
        try:
            logger.info(f"Поиск автомобилей с парсингом: {search_request.model_dump()}")

            # Подготовка данных для поиска
            search_data = {
                "searchPageUnit": str(search_request.per_page),
                "pageIndex": str(search_request.page),
                "search_grntVal": search_request.grant_val or "",
                "search_concVal": search_request.conc_val or "",
                "search_preVal": search_request.pre_val or "",
                "excelDiv": search_request.excel_div or "",
                "searchLaneDiv": search_request.lane_division or "",
                "search_doimCd": search_request.doim_code or "",
                "search_exhiNo": search_request.exhibition_number or "",
                "search_fuelCd": search_request.fuel_code or "",
                "search_trnsCd": search_request.transmission_code or "",
                "search_startPrice": search_request.min_price or "",
                "search_endPrice": search_request.max_price or "",
                "search_startYyyy": search_request.min_year or "",
                "search_endYyyy": search_request.max_year or "",
                "search_startPrice_s": search_request.min_price or "",
                "search_endPrice_s": search_request.max_price or "",
            }

            # Основные фильтры
            if search_request.manufacturer_code:
                search_data["set_search_maker"] = search_request.manufacturer_code

            if search_request.model_code:
                search_data["set_search_mdl"] = search_request.model_code

            # Дата аукциона
            if search_request.auction_date:
                search_data["searchAuctDt"] = search_request.auction_date

            # Группа автомобилей
            if search_request.car_group_code:
                search_data["set_search_chk_carGrp"] = search_request.car_group_code

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
                    page=search_request.page,
                    per_page=search_request.per_page,
                    filters_applied=search_request.model_dump(),
                )

            # Парсим HTML результаты
            html_content = response.text
            cars = self.parser.parse_car_search_html(html_content)
            total_count = self.parser.extract_total_count(html_content)

            # Рассчитываем пагинацию
            total_pages = (
                total_count + search_request.per_page - 1
            ) // search_request.per_page
            has_next = search_request.page < total_pages
            has_previous = search_request.page > 1

            response_data = LotteSearchResponse(
                success=True,
                message=f"Найдено {len(cars)} автомобилей из {total_count} общих",
                cars=cars,
                total_count=total_count,
                page=search_request.page,
                per_page=search_request.per_page,
                total_pages=total_pages,
                has_next=has_next,
                has_previous=has_previous,
                filters_applied=search_request.model_dump(),
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
                page=search_request.page,
                per_page=search_request.per_page,
                filters_applied=search_request.model_dump(),
            )
