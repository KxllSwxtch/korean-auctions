import asyncio
import time
import json
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

    @property
    def session(self) -> requests.Session:
        """Получить настроенную сессию для HTTP запросов"""
        if self._session is None:
            self._session = self._create_session()
        return self._session

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

        # Настройка headers
        session.headers.update(
            {
                "User-Agent": self.ua.random,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Cache-Control": "max-age=0",
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
                    "Referer": self.settings.autohub_base_url,
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
        Выполняет авторизацию на сайте Autohub

        Returns:
            bool: True если авторизация прошла успешно
        """
        try:
            logger.info("Выполняем авторизацию на Autohub")

            # Данные для авторизации
            login_data = {
                "i_sUserId": self.settings.autohub_username,
                "i_sPswd": self.settings.autohub_password,
                "i_sLoginGubun": "001",  # Тип пользователя: 001 = участник аукциона
            }

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

            logger.info(f"Ответ авторизации: статус {response.status_code}")

            # Проверяем ответ
            if response.status_code == 200:
                try:
                    auth_response = response.json()
                    logger.info(f"Ответ авторизации: {auth_response}")

                    if auth_response.get("status") == "succ":
                        logger.info("✅ Авторизация успешна!")

                        # Обновляем cookies после авторизации
                        logger.info(
                            f"Cookies после авторизации: {len(self.session.cookies)} штук"
                        )

                        return True
                    else:
                        logger.error(
                            f"❌ Авторизация не удалась: {auth_response.get('message', 'Неизвестная ошибка')}"
                        )
                        return False

                except Exception as json_error:
                    logger.error(f"Ошибка при парсинге JSON ответа: {json_error}")
                    logger.info(f"Текст ответа: {response.text[:500]}...")
                    return False
            else:
                logger.error(
                    f"❌ Неожиданный статус авторизации: {response.status_code}"
                )
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка при авторизации: {e}")
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
                if ('location.href="/newfront/user/login/user_login.do"' in html_content or
                    'alert("로그인이 필요합니다")' in html_content or
                    '<title>로그인</title>' in html_content):
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
                logger.info(f"Используем полные параметры поиска: {len(request_data)} параметров")
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
                return AutohubResponse(
                    success=False,
                    error="Не удалось инициализировать сессию с Autohub",
                    data=[],
                )
            
            # Если нет информации об аукционе, получаем текущую активную сессию
            if not search_params.auction_code or not search_params.auction_no or not search_params.auction_date:
                logger.info("Информация об аукционе не полная, получаем активную сессию")
                sessions_response = await self.get_auction_sessions()
                if sessions_response.success and sessions_response.current_session:
                    current_session = sessions_response.current_session
                    search_params.auction_code = current_session.auction_code
                    search_params.auction_no = current_session.auction_no
                    search_params.auction_date = current_session.auction_date
                    logger.info(f"Используем активную сессию: {current_session.auction_code}, номер: {current_session.auction_no}, дата: {current_session.auction_date}")
            
            # Преобразуем параметры в формат AutoHub
            autohub_params = search_params.to_autohub_params()
            
            logger.info(f"Параметры поиска: {autohub_params}")
            
            # Используем _fetch_html метод который правильно обрабатывает сессию
            # Передаем параметры как словарь для POST запроса
            html_content = await self._fetch_html(
                self.settings.autohub_list_url, 
                autohub_params
            )
            
            if not html_content:
                return AutohubResponse(
                    success=False, 
                    error="Не удалось получить HTML контент", 
                    data=[]
                )
                
            # Для отладки сохраняем полученный HTML
            with open("debug_search_response.html", "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info("HTML ответ сохранён в debug_search_response.html для анализа")
            
            # Парсим результаты
            cars = self.parser.parse_car_list(html_content)
            
            logger.info(f"Найдено {len(cars)} автомобилей с фильтрами")
            
            # Если автомобили не найдены, это может быть нормальным результатом поиска
            if len(cars) == 0:
                # Проверяем, действительно ли это проблема с авторизацией
                # Более надежная проверка: ищем явные признаки страницы входа
                if ('location.href="/newfront/user/login/user_login.do"' in html_content or
                    'alert("로그인이 필요합니다")' in html_content or
                    '<title>로그인</title>' in html_content):
                    return AutohubResponse(
                        success=False,
                        error="Для доступа к списку автомобилей требуется авторизация на сайте Autohub",
                        total_count=0,
                        data=[],
                    )
                # Если это не проблема авторизации, то просто нет результатов
                logger.info("Поиск не вернул результатов, но это не ошибка авторизации")
                # Сохраним HTML для отладки
                try:
                    with open("debug_empty_search_result.html", "w", encoding="utf-8") as f:
                        f.write(html_content)
                    logger.debug("HTML с пустым результатом сохранен в debug_empty_search_result.html")
                except Exception as e:
                    logger.warning(f"Не удалось сохранить HTML для отладки: {e}")
            
            # Пытаемся извлечь общее количество записей
            total_count = self._extract_total_count_from_html(html_content)
            
            return AutohubResponse(
                success=True,
                data=cars,
                total_count=total_count or len(cars),
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
        try:
            logger.info(f"Получение моделей для производителя {manufacturer_code}")
            
            # Инициализируем сессию если нужно
            if not self.session:
                session_initialized = await self._initialize_session()
                if not session_initialized:
                    logger.error("Не удалось инициализировать сессию для получения моделей")
                    return AutohubModelsResponse(
                        success=False,
                        message="Ошибка инициализации сессии",
                        models=[],
                        manufacturer_code=manufacturer_code,
                        total_count=0,
                    )
            
            # Получаем текущую сессию аукциона для кода аукциона
            sessions_response = await self.get_auction_sessions()
            auction_code = "AC202507090001"  # Значение по умолчанию
            if sessions_response.success and sessions_response.current_session:
                auction_code = sessions_response.current_session.auction_code
            
            # Подготавливаем данные для запроса
            data = {
                "i_sType": "mdl",
                "i_sAucCode": auction_code,
                "i_sMakerCode": manufacturer_code,
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
            logger.info(f"Запрос моделей: {url} с параметрами {data}")
            logger.debug(f"Заголовки запроса: {headers}")
            logger.debug(f"Cookies сессии: {self.session.cookies.get_dict()}")
            
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
                for item in response_data.get("object", []):
                    model = AutohubModel(
                        manufacturer_code=manufacturer_code,
                        model_code=item.get("carname1code", ""),
                        name=item.get("carname1name", ""),
                    )
                    models.append(model)
                
                logger.info(f"Успешно получено {len(models)} моделей для {manufacturer_code}")
                
                return AutohubModelsResponse(
                    success=True,
                    message=f"Список моделей для {manufacturer_code} получен успешно",
                    models=models,
                    manufacturer_code=manufacturer_code,
                    total_count=len(models),
                )
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
            return AutohubModelsResponse(
                success=False,
                message=f"Ошибка соединения: {str(e)}",
                models=[],
                manufacturer_code=manufacturer_code,
                total_count=0,
            )
        except Exception as e:
            logger.error(f"Ошибка при получении моделей: {e}")
            return AutohubModelsResponse(
                success=False,
                message=f"Ошибка: {str(e)}",
                models=[],
                manufacturer_code=manufacturer_code,
                total_count=0,
            )

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
        try:
            logger.info(f"Получение поколений для модели {model_code}")
            
            # Инициализируем сессию если нужно
            if not self.session:
                session_initialized = await self._initialize_session()
                if not session_initialized:
                    logger.error("Не удалось инициализировать сессию для получения поколений")
                    return AutohubGenerationsResponse(
                        success=False,
                        message="Ошибка инициализации сессии",
                        generations=[],
                        model_code=model_code,
                        total_count=0,
                    )
            
            # Получаем текущую сессию аукциона для кода аукциона
            sessions_response = await self.get_auction_sessions()
            auction_code = "AC202507090001"  # Значение по умолчанию
            if sessions_response.success and sessions_response.current_session:
                auction_code = sessions_response.current_session.auction_code
            
            # Нам нужен код производителя для запроса поколений
            # Предполагаем, что код модели содержит код производителя (например, HD03 -> HD)
            manufacturer_code = model_code[:2] if len(model_code) >= 2 else ""
            
            # Подготавливаем данные для запроса
            data = {
                "i_sType": "dmdl",
                "i_sAucCode": auction_code,
                "i_sMakerCode": manufacturer_code,
                "i_sCarName1Code": model_code,
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
            logger.info(f"Запрос поколений: {url} с параметрами {data}")
            
            response = self.session.post(
                url,
                data=data,
                headers=headers,
                timeout=self.settings.request_timeout,
            )
            response.raise_for_status()
            
            # Парсим JSON ответ
            response_data = response.json()
            logger.info(f"Получен ответ с поколениями: {response_data.get('status')}")
            logger.debug(f"Полный ответ: {response_data}")
            
            if response_data.get("status") == "succ":
                # Проверяем наличие поля object
                if "object" not in response_data:
                    logger.info(f"API вернул успех, но без данных поколений для {model_code} - это ожидаемое поведение для большинства моделей Autohub")
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
                    logger.warning(f"ВНИМАНИЕ: Найдено {len(generations)} поколений для модели {model_code} - это редкий случай, требующий внимания!")
                    logger.info(f"Поколения для {model_code}: {[g.name for g in generations]}")
                else:
                    logger.info(f"Получено 0 поколений для {model_code} - ожидаемое поведение")
                
                return AutohubGenerationsResponse(
                    success=True,
                    message=f"Список поколений для {model_code} получен успешно",
                    generations=generations,
                    model_code=model_code,
                    total_count=len(generations),
                )
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

    async def get_configurations(self, generation_code: str, model_code: str) -> AutohubConfigurationsResponse:
        """
        Получает список конфигураций для поколения
        
        Args:
            generation_code: Код поколения
            model_code: Код модели (нужен для правильного запроса)
            
        Returns:
            AutohubConfigurationsResponse: Список конфигураций
        """
        try:
            logger.info(f"Получение конфигураций для поколения {generation_code} модели {model_code}")
            
            # Инициализируем сессию если нужно
            if not self.session:
                session_initialized = await self._initialize_session()
                if not session_initialized:
                    logger.error("Не удалось инициализировать сессию для получения конфигураций")
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
                "i_sType": "ddmdl",
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
            
            response = self.session.post(
                url,
                data=data,
                headers=headers,
                timeout=self.settings.request_timeout,
            )
            response.raise_for_status()
            
            # Парсим JSON ответ
            response_data = response.json()
            logger.info(f"Получен ответ с конфигурациями: {response_data.get('status')}")
            
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
                
                logger.info(f"Успешно получено {len(configurations)} конфигураций для поколения {generation_code}")
                
                return AutohubConfigurationsResponse(
                    success=True,
                    message=f"Список конфигураций для поколения {generation_code} получен успешно",
                    configurations=configurations,
                    generation_code=generation_code,
                    total_count=len(configurations),
                )
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

    async def get_auction_sessions(self) -> AutohubAuctionSessionsResponse:
        """
        Получает список активных сессий аукциона
        
        Returns:
            AutohubAuctionSessionsResponse: Список сессий
        """
        try:
            logger.info("Получение списка сессий аукциона")
            
            # Здесь должен быть реальный запрос к AutoHub для получения сессий
            # Пока возвращаем примерные данные
            sessions = [
                AutohubAuctionSession(
                    auction_no="1332",
                    auction_date="2025-07-09",
                    auction_code="AC202507020001",
                    auction_title="안성 2025/07/09 1332회차 경매",
                    is_active=True,
                )
            ]
            
            # TODO: Реализовать парсинг сессий с сайта AutoHub
            
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


# Глобальный экземпляр сервиса
autohub_service = AutohubService()
