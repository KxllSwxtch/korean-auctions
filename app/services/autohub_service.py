import asyncio
import time
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
from app.parsers.autohub_parser import parse_car_detail
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
                    message="Не удалось инициализировать сессию с Autohub",
                    cars=[],
                )

            # Выполняем HTTP запрос
            html_content = await self._fetch_html(
                self.settings.autohub_list_url, params
            )

            if not html_content:
                return AutohubResponse(
                    success=False, message="Не удалось получить HTML контент", cars=[]
                )

            # Парсим HTML (временная заглушка - парсер списка не реализован)
            cars = []  # TODO: Реализовать парсинг списка автомобилей

            logger.info(f"Успешно получено {len(cars)} автомобилей (заглушка)")

            # Если автомобили не найдены, проверяем причину
            if len(cars) == 0:
                # Проверяем, требуется ли авторизация
                if "loginFlag" in html_content and "login.do" in html_content:
                    return AutohubResponse(
                        success=False,
                        message="Для доступа к списку автомобилей требуется авторизация на сайте Autohub. Используйте endpoint /cars/test для демонстрации функциональности парсера.",
                        total_count=0,
                        cars=[],
                    )

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
                message=message,
                total_count=total_cars_from_page or len(cars),
                cars=cars,
                current_page=current_page,
                page_size=autohub_page_size,  # Используем фактический размер страницы Autohub
                total_pages=total_pages,
                has_next_page=has_next_page,
                has_prev_page=has_prev_page,
            )

        except Exception as e:
            error_msg = f"Ошибка при получении списка автомобилей: {str(e)}"
            logger.error(error_msg)

            return AutohubResponse(success=False, message=error_msg, cars=[])

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
            # Формируем параметры для пагинации Autohub
            pagination_data = {}

            if params:
                # Преобразуем наш параметр page в параметр Autohub i_iNowPageNo
                if "page" in params:
                    pagination_data["i_iNowPageNo"] = params["page"]
                    logger.info(
                        f"Запрос страницы {params['page']} (i_iNowPageNo={params['page']})"
                    )

                # Можно добавить другие параметры фильтрации для Autohub
                # if 'limit' in params:
                #     pagination_data['i_iPageSize'] = params['limit']  # если поддерживается

            # Если не указана страница, по умолчанию первая
            if "i_iNowPageNo" not in pagination_data:
                pagination_data["i_iNowPageNo"] = 1

            logger.info(f"Выполняем запрос к {url} с параметрами: {pagination_data}")

            # Добавляем случайную задержку для имитации человеческого поведения
            await asyncio.sleep(0.5)

            # Обновляем User-Agent для каждого запроса
            self.session.headers.update({"User-Agent": self.ua.random})

            # Для пагинации Autohub может требоваться POST запрос
            # Проверим, нужно ли использовать POST или GET
            if pagination_data.get("i_iNowPageNo", 1) > 1:
                # Для страниц больше 1 используем POST с данными пагинации
                response = self.session.post(
                    url,
                    data=pagination_data,
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
                    params=pagination_data,
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

            logger.info(f"POST запрос к Autohub detail: {url}")
            logger.debug(f"Параметры запроса: {data}")

            response = self.session.post(
                url, data=data, timeout=self.settings.request_timeout
            )
            response.raise_for_status()

            # Парсинг детальной информации
            car_detail = parse_car_detail(response.text)

            if car_detail:
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


# Глобальный экземпляр сервиса
autohub_service = AutohubService()
