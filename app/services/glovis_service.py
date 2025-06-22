import asyncio
import time
from typing import List, Optional, Dict, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fake_useragent import UserAgent
from datetime import datetime, timedelta

from app.models.glovis import GlovisCar, GlovisResponse, GlovisError
from app.models.glovis_filters import (
    GlovisFilterOptions,
    GlovisManufacturer,
    GlovisModel,
    GlovisDetailModel,
    GlovisManufacturersResponse,
    GlovisModelsResponse,
    GlovisDetailModelsResponse,
    GlovisFilteredCarsResponse,
)
from app.parsers.glovis_parser import GlovisParser
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.session_manager import get_session_manager, get_glovis_monitor

logger = get_logger("glovis_service")


class GlovisService:
    """Сервис для работы с Hyundai Glovis auction"""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = "https://auction.autobell.co.kr"
        self.parser = GlovisParser(self.base_url)
        self.ua = UserAgent()
        self._session = None
        self._authenticated = False
        self._session_created_at = None
        self._session_ttl = timedelta(minutes=30)  # TTL сессии 30 минут
        self._last_cookie_update = None

        # Используем глобальный менеджер сессий
        self.session_manager = get_session_manager()
        self.glovis_monitor = get_glovis_monitor()

        # Запускаем мониторинг сессии
        self.glovis_monitor.start_monitoring()

        # Пытаемся загрузить сохраненную сессию при инициализации
        self._load_saved_session()

    def _get_fresh_cookies(self) -> Dict[str, str]:
        """Возвращает свежие cookies для Glovis"""
        # Сначала пытаемся загрузить из сохраненной сессии
        saved_cookies = self.session_manager.load_session("glovis")
        if saved_cookies and self.session_manager.is_session_fresh(
            "glovis", max_age_hours=12
        ):
            logger.info("✅ Используем сохраненные cookies из кэша")
            return saved_cookies

        # Если нет сохраненных или они устарели, используем дефолтные
        logger.warning(
            "⚠️ Используем дефолтные cookies (сохраненные устарели или отсутствуют)"
        )

        # Свежие cookies из рабочего примера (обновлено 2025-06-19)
        return {
            "SCOUTER": "z6d9hgnq5i09ho",
            "_gcl_au": "1.1.469301602.1749863933",
            "_fwb": "191nmCARVubatjoH72cRPm8.1749863933091",
            "_fbp": "fb.2.1749863933206.396345519817813213",
            "_gcl_aw": "GCL.1749867756.EAIaIQobChMI5I30r-3vjQMV9V4PAh1xVhhmEAAYASAAEgInMPD_BwE",
            "_gcl_gs": "2.1.k1$i1749867755$u107600402",
            "_gac_UA-163217058-4": "1.1749867756.EAIaIQobChMI5I30r-3vjQMV9V4PAh1xVhhmEAAYASAAEgInMPD_BwE",
            "_ga": "GA1.1.1367887267.1749863933",
            "_ga_WBXP3Q01TE": "GS2.1.s1749866209$o2$g1$t1749867760$j56$l0$h0",
            "JSESSIONID": "MnHMksSJtqnPpna3cTKG9ePodXjmil3aS6lP0bbN1hBIWcQwl60arHxOa2FFL798.QXV0b0F1Y3Rpb24vQXV0b0F1Y3Rpb24y",
            "_ga_H9G80S9QWN": "GS2.1.s1750316379$o17$g1$t1750316392$j47$l0$h0",
            # ⭐ НОВЫЕ: Windows-специфичные cookies для авторизации
            "idChk": "1",  # Флаг проверки идентичности
            "Chk": "7552",  # Код проверки (может меняться)
        }

    def _get_windows_cookies(self) -> Dict[str, str]:
        """Возвращает Windows-специфичные cookies из перехваченного запроса"""
        return {
            "_gcl_au": "1.1.982350429.1749522778",
            "_fwb": "19cGXz96Ifjpyk0wuJ5XI.1749522778595",
            "idChk": "1",  # ⭐ КРИТИЧНЫЙ - флаг проверки идентичности
            "Chk": "7552",  # ⭐ КРИТИЧНЫЙ - код проверки
            "SCOUTER": "zcsqd8tkmdiai",
            "_ga": "GA1.1.450054511.1749522779",
            "_ga_WBXP3Q01TE": "GS2.1.s1749793770$o3$g0$t1749793788$j42$l0$h0",
            "JSESSIONID": "qbVljRoxFc3oRHlXZC4Vo68nB5YJ3qaRQK0iqgrvwH3QxtZdlGVEbH9XrNqSJ9vi.QXV0b0F1Y3Rpb24vQXV0b0F1Y3Rpb24x",
            "_ga_H9G80S9QWN": "GS2.1.s1750551573$o1$g0$t1750551573$j60$l0$h0",
        }

    def _generate_auth_token(self) -> str:
        """
        Генерирует authToken на основе анализа Windows приложения

        ⚠️ ТРЕБУЕТ ДОПОЛНИТЕЛЬНОГО ИССЛЕДОВАНИЯ
        authToken из Windows приложения: xMWEaaBPpJmiteLCzigMIw==
        Base64 decoded: b'\xc4\xc5\x84i\xa0O\xa4\x99\xa2\xb5\xe2\xc2\xce(\x0c#'
        """
        import base64
        import os
        import time

        # Временное решение: используем известный рабочий токен
        # TODO: Исследовать алгоритм генерации authToken
        return "xMWEaaBPpJmiteLCzigMIw%3D%3D"

    def _create_session_with_auth_token(
        self, auth_token: str = None
    ) -> requests.Session:
        """
        Создает сессию с поддержкой authToken из Windows приложения

        Args:
            auth_token: authToken из Windows приложения
        """
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

        # Используем Windows-специфичные cookies
        windows_cookies = self._get_windows_cookies()

        # Обновляем cookies из кэша если они есть
        saved_cookies = self.session_manager.load_session("glovis")
        if saved_cookies:
            # Обновляем JSESSIONID и другие важные cookies
            for key in ["JSESSIONID", "_ga", "_ga_WBXP3Q01TE", "_ga_H9G80S9QWN"]:
                if key in saved_cookies:
                    windows_cookies[key] = saved_cookies[key]

        # Настройка headers с поддержкой authToken
        if not auth_token:
            auth_token = self._generate_auth_token()

        # Создаем Referer с authToken (как в Windows приложении)
        referer_with_token = f"https://auction.autobell.co.kr/auction/exhibitList.do?authToken={auth_token}&ABLE_LANGUAGE_SELECTION_PARAM=ko&flagHouse=W&acc=30&rc=&atn=749&searchListType=SHORTSELLING&bidcd=3&auctListStat="

        session.headers.update(
            {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
                "Cache-Control": "max-age=0",
                "Connection": "keep-alive",
                "Referer": referer_with_token,  # ⭐ КРИТИЧНЫЙ - с authToken
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
                "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
            }
        )

        # Устанавливаем cookies
        for name, value in windows_cookies.items():
            session.cookies.set(name, value)

        # Отключаем проверку SSL сертификатов
        session.verify = False

        # Подавляем предупреждения о незащищённых запросах
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        logger.info(f"🔐 Создана сессия с authToken: {auth_token[:20]}...")
        self._session_created_at = datetime.now()
        self._authenticated = True
        return session

    def get_session_with_auth_token(self, auth_token: str = None) -> requests.Session:
        """
        Публичный метод для получения сессии с authToken

        Args:
            auth_token: authToken из Windows приложения
        """
        return self._create_session_with_auth_token(auth_token)

    def _load_saved_session(self):
        """Загружает сохраненную сессию при старте"""
        try:
            saved_cookies = self.session_manager.load_session("glovis")
            if saved_cookies:
                age = self.session_manager.get_session_age("glovis")
                if age:
                    logger.info(
                        f"📂 Найдена сохраненная сессия Glovis (возраст: {age})"
                    )
                    if self.session_manager.is_session_fresh(
                        "glovis", max_age_hours=24
                    ):
                        logger.info("✅ Сохраненная сессия свежая, будет использована")
                    else:
                        logger.warning("⚠️ Сохраненная сессия устарела")
            else:
                logger.info("📂 Сохраненная сессия Glovis не найдена")
        except Exception as e:
            logger.error(f"❌ Ошибка при загрузке сохраненной сессии: {e}")

    def _is_session_expired(self) -> bool:
        """Проверяет, истекла ли сессия по времени"""
        if not self._session_created_at:
            return True
        return datetime.now() - self._session_created_at > self._session_ttl

    def update_cookies(self, new_cookies: Dict[str, str]) -> None:
        """Обновляет cookies в текущей сессии и сохраняет их"""
        if self._session:
            logger.info("🔄 Обновляю cookies в текущей сессии")
            for name, value in new_cookies.items():
                self._session.cookies.set(name, value)
            self._last_cookie_update = datetime.now()

            # Сохраняем обновленные cookies
            self.session_manager.save_session(
                "glovis",
                new_cookies,
                metadata={
                    "source": "manual_update",
                    "jsessionid": new_cookies.get("JSESSIONID"),
                },
            )

            logger.info("✅ Cookies успешно обновлены и сохранены")
        else:
            logger.warning("⚠️ Сессия не инициализирована, cookies не обновлены")

    @property
    def session(self) -> requests.Session:
        """Получить настроенную сессию для HTTP запросов"""
        if self._session is None or self._is_session_expired():
            if self._session:
                logger.info("⏰ Сессия истекла по времени, создаю новую")
                self._session.close()
            self._session = self._create_session()
        return self._session

    def _create_session(self) -> requests.Session:
        """Создает настроенную сессию с retry стратегией и cookies"""
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

        # Настройка headers для имитации браузера
        session.headers.update(
            {
                "Accept": "text/html, */*; q=0.01",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
                "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            }
        )

        # Обновленные cookies из рабочего примера (обновлено 2025-06-16)
        cookies = self._get_fresh_cookies()

        # Устанавливаем cookies
        for name, value in cookies.items():
            session.cookies.set(name, value)

        # Отключаем проверку SSL сертификатов
        session.verify = False

        # Подавляем предупреждения о незащищённых запросах
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self._session_created_at = datetime.now()
        self._authenticated = True
        return session

    async def get_car_list(
        self, params: Optional[Dict[str, Any]] = None
    ) -> GlovisResponse:
        """
        Получает список автомобилей с Glovis

        Args:
            params: Дополнительные параметры для запроса

        Returns:
            GlovisResponse: Ответ с данными о автомобилях
        """
        try:
            logger.info("Начинаем получение списка автомобилей Glovis")

            # Параметры по умолчанию
            page = params.get("page", 1) if params else 1

            # Получаем HTML
            html_content = await self._fetch_car_list_html(page, params)

            if not html_content:
                return GlovisResponse(
                    success=False,
                    message="Не удалось получить данные с сайта",
                    total_count=0,
                    cars=[],
                )

            # Парсим HTML
            result = self.parser.parse_car_list(html_content, page)

            logger.info(f"Получено {len(result.cars)} автомобилей на странице {page}")
            return result

        except Exception as e:
            logger.error(f"Ошибка при получении списка автомобилей: {e}")
            return GlovisResponse(
                success=False,
                message=f"Ошибка при получении данных: {str(e)}",
                total_count=0,
                cars=[],
            )

    async def _fetch_car_list_html(
        self, page: int = 1, params: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Получает HTML с данными об автомобилях"""
        try:
            url = f"{self.base_url}/auction/exhibitListInclude.do"

            # Проверяем валидность сессии перед запросом
            session_check = await self.check_session_validity()
            if not session_check.get("is_valid", False):
                logger.warning("⚠️ Сессия невалидна, обновляем...")
                self.refresh_session()
                # Повторная проверка после обновления
                session_check = await self.check_session_validity()
                if not session_check.get("is_valid", False):
                    logger.warning(
                        "⚠️ Стандартное обновление не помогло, пытаемся экстренное..."
                    )
                    if self._emergency_cookies_update():
                        # Проверяем после экстренного обновления
                        session_check = await self.check_session_validity()
                        if not session_check.get("is_valid", False):
                            logger.error("❌ Даже экстренное обновление не помогло")
                            return None
                        else:
                            logger.success(
                                "✅ Экстренное обновление cookies сработало!"
                            )
                    else:
                        logger.error("❌ Не удалось восстановить валидную сессию")
                        return None

            # Подготавливаем данные для POST запроса на основе glovis-new-curl.py
            row_from = str((page - 1) * 18 + 1)  # 18 автомобилей на страницу

            data = {
                "rowFrom": row_from,
                "page": str(page),
                "nowexhino": "",
                "flagHouse": "W",
                "flag": "Y",
                "bidcd": "",
                "exportAuctionYn": "N",
                "ac": "TQhYt3GD6GvgPdVw1QX+Wg==",
                "atn": "749",  # Обновлено из glovis-new-curl.py
                "acc": "30",  # Обновлено из glovis-new-curl.py
                "rc": "",
                "gn": "",
                "searchRc": "",
                "sdistancecd": "",
                "edistancecd": "",
                "missioncd": "",
                "carcd": "",
                "prodmancd": "",
                "prodmannm": "",
                "cargradcd": "",
                "cargradnm": "",
                "reprcarcd": "",
                "reprcarnm": "",
                "detacarcd": "",
                "detacarnm": "",
                "carPrice": "",
                "menuCd": "MCUA",
                "searchtype": "",
                "searchtext": "",
                "deviceType": "",
                "auctstardt": "20250621090000",  # Обновлено из glovis-new-curl.py
                "auctenddt": "20250623120000",  # Обновлено из glovis-new-curl.py
                "primeAuctionChk": "",
                "primeauctionyn": "N",  # Обновлено из glovis-new-curl.py
                "primeauctionAlertMessage": "",
                "searchInput": "",
                "exceptEmptYn": "Y",
                "sprice": "",
                "eprice": "",
                "syearcd": "",
                "eyearcd": "",
                "searchAuctno": "749",  # Обновлено из glovis-new-curl.py
                "auctroomcd": "",
                "searchLanecd": "",
                "auctListStat": "",  # Обновлено из glovis-new-curl.py (пустое)
                # Новые поля из glovis-new-curl.py
                "publicauctionsdt": "20250621090000",
                "publicauctionedt": "20250623120000",
                "publicauctionsday": "토",
                "publicauctioneday": "월",
                "rowLimit": "18",
                "searchorder": "01",
            }

            # Добавляем параметры из params если они есть
            if params:
                # Обновляем поля поиска если заданы
                if "search_rc" in params:
                    data["searchRc"] = str(params["search_rc"])
                if "search_type" in params:
                    data["searchtype"] = str(params["search_type"])
                if "search_text" in params:
                    data["searchtext"] = str(params["search_text"])
                if "car_manufacturer" in params:
                    data["prodmancd"] = str(params["car_manufacturer"])
                if "auction_number" in params:
                    auction_num = str(params["auction_number"])
                    data["searchAuctno"] = auction_num
                    data["atn"] = auction_num

            # Настраиваем headers для POST запроса (обновлено из glovis-new-curl.py)
            headers = {
                "Accept": "text/html, */*; q=0.01",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/auction/exhibitList.do?atn=749&acc=30&auctListStat=&flag=Y",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
                "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            }

            logger.info(f"Отправляем POST запрос на {url} для страницы {page}")

            # Выполняем POST запрос
            response = self.session.post(
                url, data=data, headers=headers, timeout=30, allow_redirects=True
            )

            if response.status_code == 200:
                # Дополнительная проверка на скрытые редиректы
                if "<script>location.href='/login.do';</script>" in response.text:
                    logger.error(
                        "❌ Получен JavaScript редирект на логин, сессия истекла"
                    )
                    # Попытка автоматического восстановления
                    logger.info("🔄 Попытка автоматического восстановления сессии...")
                    self.refresh_session()

                    # Повторный запрос после обновления сессии
                    response = self.session.post(
                        url,
                        data=data,
                        headers=headers,
                        timeout=30,
                        allow_redirects=True,
                    )

                    if (
                        response.status_code == 200
                        and "<script>location.href='/login.do';</script>"
                        not in response.text
                    ):
                        logger.info("✅ Сессия успешно восстановлена")
                        return response.text
                    else:
                        logger.warning(
                            "⚠️ Повторный запрос не сработал, пытаемся экстренное обновление..."
                        )
                        if self._emergency_cookies_update():
                            # Третья попытка после экстренного обновления
                            response = self.session.post(
                                url,
                                data=data,
                                headers=headers,
                                timeout=30,
                                allow_redirects=True,
                            )

                            if (
                                response.status_code == 200
                                and "<script>location.href='/login.do';</script>"
                                not in response.text
                            ):
                                logger.success(
                                    "✅ Экстренное обновление cookies помогло!"
                                )
                                return response.text
                            else:
                                logger.error("❌ Даже экстренное обновление не помогло")
                                return None
                        else:
                            logger.error("❌ Не удалось восстановить сессию")
                            return None

                logger.info(
                    f"✅ Успешно получили HTML (размер: {len(response.text)} символов)"
                )
                return response.text
            else:
                logger.error(f"❌ HTTP ошибка: {response.status_code}")
                logger.error(f"Ответ: {response.text[:1000]}...")

                # Если ошибка 401 - проблема с аутентификацией
                if response.status_code == 401:
                    logger.info("🔄 Ошибка 401, обновляем сессию...")
                    self.refresh_session()

                return None

        except Exception as e:
            logger.error(f"Ошибка при получении HTML: {e}")
            return None

    async def get_car_details(self, car_gn: str) -> Optional[Dict[str, Any]]:
        """
        Получает детальную информацию об автомобиле

        Args:
            car_gn: Идентификатор автомобиля (gn)

        Returns:
            Optional[Dict]: Детальная информация об автомобиле
        """
        try:
            # Здесь можно реализовать получение детальной информации
            # используя car_gn и другие параметры
            logger.info(f"Получение деталей автомобиля gn={car_gn}")

            # Пока возвращаем заглушку
            return {
                "gn": car_gn,
                "details": "Детальная информация будет реализована позже",
            }

        except Exception as e:
            logger.error(f"Ошибка при получении деталей автомобиля: {e}")
            return None

    def get_test_data(self) -> GlovisResponse:
        """Возвращает тестовые данные для отладки"""
        from app.models.glovis import (
            GlovisCar,
            GlovisResponse,
            GlovisLocation,
            GlovisCarCondition,
        )

        test_cars = [
            GlovisCar(
                entry_number="5001",
                car_name="[벤츠] 스프린터(3세대) 319 CDI 유로코치 화이트",
                location=GlovisLocation.BUNDANG,
                lane="레인 B",
                license_plate="103로1969",
                year=2020,
                transmission="A/T",
                engine_volume="2,987cc",
                mileage="120,470 km",
                color="검정",
                fuel_type="경유",
                usage_type="법인상품용",
                condition_grade=GlovisCarCondition.A4,
                auction_number="944",
                starting_price=5800,
                main_image_url="https://img-auction.autobell.co.kr/test.jpg",
                gn="teMUgP8zkuB4ZMgXXSZJdA==",
                rc="1100",
                acc="20",
                atn="944",
                prodmancd="68",
                reprcarcd="172",
                detacarcd="2838",
                cargradcd="9",
            ),
            GlovisCar(
                entry_number="5002",
                car_name="[아우디] Q7 3.6 FSI 콰트로 디럭스",
                location=GlovisLocation.BUNDANG,
                lane="레인 B",
                license_plate="62모3040",
                year=2008,
                transmission="A/T",
                engine_volume="3,597cc",
                mileage="153,746 km",
                color="회색",
                fuel_type="휘발유",
                usage_type="개인",
                condition_grade=GlovisCarCondition.A3,
                auction_number="944",
                starting_price=280,
                main_image_url="https://img-auction.autobell.co.kr/test2.jpg",
                gn="sMMnzvOGBo6z692ysIwhuA==",
                rc="1100",
                acc="20",
                atn="944",
                prodmancd="70",
                reprcarcd="185",
                detacarcd="356",
                cargradcd="8",
            ),
        ]

        return GlovisResponse(
            success=True,
            message="Тестовые данные Glovis",
            total_count=10,
            cars=test_cars,
            current_page=1,
            page_size=18,
            total_pages=1,
            has_next_page=False,
            has_prev_page=False,
        )

    async def check_session_validity(self) -> Dict[str, Any]:
        """Проверяет валидность текущей сессии"""
        try:
            logger.info("🔍 Проверка валидности сессии Glovis")

            # Делаем простой запрос для проверки сессии
            session = self.session
            test_url = f"{self.base_url}/auction/exhibitList.do?atn=946&acc=20&flag=Y"

            response = session.get(test_url, timeout=10, allow_redirects=False)

            # Проверяем различные сценарии
            is_valid = True
            issues = []

            if response.status_code == 401:
                is_valid = False
                issues.append("HTTP 401 - Неавторизован")
            elif response.status_code == 302 and "/login.do" in response.headers.get(
                "Location", ""
            ):
                is_valid = False
                issues.append("Редирект на страницу логина")
            elif response.status_code != 200:
                is_valid = False
                issues.append(f"HTTP {response.status_code}")
            elif "<script>location.href='/login.do';</script>" in response.text:
                is_valid = False
                issues.append("JavaScript редирект на логин")
            elif "login" in response.text.lower() and len(response.text) < 1000:
                is_valid = False
                issues.append("Страница содержит форму логина")

            # Получаем информацию о cookies
            cookies_info = {}
            for cookie in session.cookies:
                if cookie.name == "JSESSIONID":
                    cookies_info["JSESSIONID"] = {
                        "value": (
                            cookie.value[:20] + "..."
                            if len(cookie.value) > 20
                            else cookie.value
                        ),
                        "domain": cookie.domain,
                        "path": cookie.path,
                        "expires": cookie.expires,
                    }

            result = {
                "is_valid": is_valid,
                "status_code": response.status_code,
                "response_size": len(response.text),
                "cookies_info": cookies_info,
                "issues": issues,
                "redirect_location": response.headers.get("Location"),
                "content_preview": (
                    response.text[:200] + "..."
                    if len(response.text) > 200
                    else response.text
                ),
            }

            if is_valid:
                logger.info("✅ Сессия Glovis валидна")
            else:
                logger.warning(f"⚠️ Проблемы с сессией Glovis: {', '.join(issues)}")

            return result

        except Exception as e:
            logger.error(f"❌ Ошибка при проверке сессии: {e}")
            return {
                "is_valid": False,
                "error": str(e),
                "issues": [f"Ошибка запроса: {str(e)}"],
            }

    def refresh_session(self, force_new_cookies: bool = False):
        """Принудительно обновляет сессию и cookies"""
        logger.info("🔄 Принудительное обновление сессии Glovis")

        if force_new_cookies:
            logger.info("🆕 Запрошено принудительное обновление cookies")

        if self._session:
            self._session.close()
        self._session = None
        self._authenticated = False
        self._session_created_at = None
        # При следующем обращении сессия будет создана заново с новыми cookies

    async def ensure_valid_session(self) -> bool:
        """
        Убеждается, что сессия валидна и готова к использованию

        Returns:
            bool: True если сессия валидна, False в противном случае
        """
        try:
            # Проверяем валидность текущей сессии
            session_check = await self.check_session_validity()

            if session_check.get("is_valid", False):
                logger.debug("✅ Сессия валидна")
                return True

            # Если сессия невалидна, пытаемся её восстановить
            logger.info("🔄 Сессия невалидна, пытаемся восстановить...")
            self.refresh_session()

            # Проверяем после восстановления
            session_check = await self.check_session_validity()

            if session_check.get("is_valid", False):
                logger.info("✅ Сессия успешно восстановлена")
                return True
            else:
                logger.error("❌ Не удалось восстановить валидную сессию")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка при проверке валидности сессии: {str(e)}")
            return False

    def get_current_cookies(self) -> Dict[str, str]:
        """
        Возвращает текущие cookies из сессии

        Returns:
            Dict[str, str]: Словарь с cookies
        """
        try:
            if self._session and self._session.cookies:
                cookies_dict = {}
                for cookie in self._session.cookies:
                    cookies_dict[cookie.name] = cookie.value
                logger.debug(f"📋 Получены cookies: {list(cookies_dict.keys())}")
                return cookies_dict
            else:
                logger.warning(
                    "⚠️ Сессия не инициализирована, возвращаю базовые cookies"
                )
                return self._get_fresh_cookies()
        except Exception as e:
            logger.error(f"❌ Ошибка при получении cookies: {str(e)}")
            return self._get_fresh_cookies()

    async def health_check(self) -> Dict[str, Any]:
        """
        Проверка состояния сервиса Glovis

        Returns:
            Dict[str, Any]: Результат проверки состояния
        """
        try:
            logger.debug("🏥 Проверка состояния сервиса Glovis")

            # Проверяем валидность сессии
            session_valid = await self.check_session_validity()

            # Проверяем базовую доступность сайта
            try:
                response = self.session.get(
                    f"{self.base_url}/auction/exhibitList.do", timeout=10
                )
                site_accessible = response.status_code == 200
            except Exception:
                site_accessible = False

            # Проверяем актуальность cookies
            cookies_fresh = True
            if self._last_cookie_update:
                cookies_age = datetime.now() - self._last_cookie_update
                cookies_fresh = cookies_age < timedelta(hours=1)

            overall_health = (
                session_valid.get("is_valid", False)
                and site_accessible
                and cookies_fresh
            )

            return {
                "healthy": overall_health,
                "components": {
                    "session": {
                        "valid": session_valid.get("is_valid", False),
                        "jsessionid_present": session_valid.get(
                            "jsessionid_present", False
                        ),
                        "created_at": (
                            self._session_created_at.isoformat()
                            if self._session_created_at
                            else None
                        ),
                        "age_minutes": (
                            (datetime.now() - self._session_created_at).total_seconds()
                            / 60
                            if self._session_created_at
                            else None
                        ),
                    },
                    "site_access": {"accessible": site_accessible},
                    "cookies": {
                        "fresh": cookies_fresh,
                        "last_update": (
                            self._last_cookie_update.isoformat()
                            if self._last_cookie_update
                            else None
                        ),
                    },
                },
                "message": (
                    "Сервис работает корректно"
                    if overall_health
                    else "Обнаружены проблемы с сервисом"
                ),
            }

        except Exception as e:
            logger.error(f"❌ Ошибка при проверке состояния: {str(e)}")
            return {"healthy": False, "message": f"Ошибка проверки: {str(e)}"}

    async def get_manufacturers(self) -> GlovisManufacturersResponse:
        """
        Получает список производителей автомобилей

        Returns:
            GlovisManufacturersResponse: Список производителей с количеством доступных автомобилей
        """
        try:
            logger.info("🏭 Получение списка производителей Glovis")
            start_time = time.time()

            # Получаем страницу с фильтрами
            url = f"{self.base_url}/auction/exhibitList.do"
            params = {"atn": "747", "acc": "30", "auctListStat": "", "flag": "Y"}

            response = self.session.get(url, params=params, timeout=30)
            if response.status_code != 200:
                logger.error(f"❌ Ошибка HTTP: {response.status_code}")
                return GlovisManufacturersResponse(
                    success=False,
                    message=f"HTTP ошибка: {response.status_code}",
                    timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                )

            # Парсим список производителей из HTML
            manufacturers = self.parser.parse_manufacturers(response.text)

            duration = time.time() - start_time
            logger.info(
                f"✅ Получено {len(manufacturers)} производителей за {duration:.2f}с"
            )

            return GlovisManufacturersResponse(
                success=True,
                message=f"Получено {len(manufacturers)} производителей",
                manufacturers=manufacturers,
                total_count=len(manufacturers),
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            )

        except Exception as e:
            logger.error(f"❌ Ошибка при получении производителей: {e}")
            return GlovisManufacturersResponse(
                success=False,
                message=f"Ошибка: {str(e)}",
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            )

    async def get_models(self, manufacturer_code: str) -> GlovisModelsResponse:
        """
        Получает список моделей для выбранного производителя

        Args:
            manufacturer_code: Код производителя

        Returns:
            GlovisModelsResponse: Список моделей для производителя
        """
        try:
            logger.info(f"🚗 Получение моделей для производителя {manufacturer_code}")
            start_time = time.time()

            # Проверяем валидность сессии
            session_check = await self.check_session_validity()
            if not session_check.get("is_valid", False):
                logger.warning("⚠️ Обновляем сессию...")
                self.refresh_session()

            url = f"{self.base_url}/cmm/carCorpModelList.do"

            # Подготавливаем данные на основе примера
            data = {
                "rowFrom": "1",
                "page": "1",
                "nowexhino": "",
                "flagHouse": "W",
                "flag": "Y",
                "bidcd": "",
                "exportAuctionYn": "N",
                "ac": "TQhYt3GD6GvgPdVw1QX+Wg==",
                "atn": "747",
                "acc": "30",
                "rc": "",
                "gn": "",
                "searchRc": "",
                "sdistancecd": "",
                "edistancecd": "",
                "missioncd": "",
                "carcd": "",
                "prodmancd": manufacturer_code,
                "prodmannm": "",
                "cargradcd": "",
                "cargradnm": "",
                "reprcarcd": "",
                "reprcarnm": "",
                "detacarcd": "",
                "detacarnm": "",
                "carPrice": "",
                "menuCd": "MCUA",
                "searchtype": "",
                "searchtext": "",
                "deviceType": "",
                "auctstardt": "20250614090000",
                "auctenddt": "20250616120000",
                "primeAuctionChk": "",
                "primeauctionyn": "N",
                "primeauctionAlertMessage": "",
                "searchInput": "",
                "exceptEmptYn": "Y",
                "arrProdmancd": manufacturer_code,
                "sprice": "",
                "eprice": "",
                "syearcd": "",
                "eyearcd": "",
                "searchAuctno": "747",
                "auctroomcd": "",
                "publicauctionsdt": "20250614090000",
                "publicauctionedt": "20250616120000",
                "publicauctionsday": "토",
                "publicauctioneday": "월",
                "rowLimit": "18",
                "searchorder": "01",
                "searchArray": manufacturer_code,
            }

            # Устанавливаем правильные headers для AJAX запроса
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": "https://auction.autobell.co.kr",
                "Referer": "https://auction.autobell.co.kr/auction/exhibitList.do?atn=747&acc=30&auctListStat=&flag=Y",
                "X-Requested-With": "XMLHttpRequest",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }

            response = self.session.post(url, data=data, headers=headers, timeout=30)
            if response.status_code != 200:
                logger.error(f"❌ Ошибка HTTP: {response.status_code}")
                return GlovisModelsResponse(
                    success=False,
                    message=f"HTTP ошибка: {response.status_code}",
                    timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                )

            # Парсим JSON ответ
            models = self.parser.parse_models(response.json())

            duration = time.time() - start_time
            logger.info(f"✅ Получено {len(models)} моделей за {duration:.2f}с")

            return GlovisModelsResponse(
                success=True,
                message=f"Получено {len(models)} моделей",
                models=models,
                total_count=len(models),
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            )

        except Exception as e:
            logger.error(f"❌ Ошибка при получении моделей: {e}")
            return GlovisModelsResponse(
                success=False,
                message=f"Ошибка: {str(e)}",
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            )

    async def get_detail_models(
        self, manufacturer_code: str, model_codes: List[str]
    ) -> GlovisDetailModelsResponse:
        """
        Получает детальные модели для выбранных базовых моделей

        Args:
            manufacturer_code: Код производителя
            model_codes: Список кодов базовых моделей

        Returns:
            GlovisDetailModelsResponse: Список детальных моделей
        """
        try:
            logger.info(f"🔍 Получение детальных моделей для {model_codes}")
            start_time = time.time()

            # Проверяем валидность сессии
            session_check = await self.check_session_validity()
            if not session_check.get("is_valid", False):
                logger.warning("⚠️ Обновляем сессию...")
                self.refresh_session()

            url = f"{self.base_url}/cmm/carModelDetailList.do"

            # Подготавливаем массив для searchArray
            search_arrays = []
            for model_code in model_codes:
                search_arrays.append(f"{manufacturer_code}_{model_code}")

            # Подготавливаем данные формы
            data = [
                ("rowFrom", "1"),
                ("page", "1"),
                ("nowexhino", ""),
                ("flagHouse", "W"),
                ("flag", "Y"),
                ("bidcd", ""),
                ("exportAuctionYn", "N"),
                ("ac", "TQhYt3GD6GvgPdVw1QX+Wg=="),
                ("atn", "747"),
                ("acc", "30"),
                ("rc", ""),
                ("gn", ""),
                ("searchRc", ""),
                ("sdistancecd", ""),
                ("edistancecd", ""),
                ("missioncd", ""),
                ("carcd", ""),
                ("prodmancd", manufacturer_code),
                ("prodmannm", ""),
                ("cargradcd", ""),
                ("cargradnm", ""),
                ("reprcarcd", ""),
                ("reprcarnm", ""),
                ("detacarcd", ""),
                ("detacarnm", ""),
                ("carPrice", ""),
                ("menuCd", "MCUA"),
                ("searchtype", ""),
                ("searchtext", ""),
                ("deviceType", ""),
                ("auctstardt", "20250614090000"),
                ("auctenddt", "20250616120000"),
                ("primeAuctionChk", ""),
                ("primeauctionyn", "N"),
                ("primeauctionAlertMessage", ""),
                ("searchInput", ""),
                ("exceptEmptYn", "Y"),
                ("arrProdmancd", manufacturer_code),
                ("sprice", ""),
                ("eprice", ""),
                ("syearcd", ""),
                ("eyearcd", ""),
                ("searchAuctno", "747"),
                ("auctroomcd", ""),
                ("publicauctionsdt", "20250614090000"),
                ("publicauctionedt", "20250616120000"),
                ("publicauctionsday", "토"),
                ("publicauctioneday", "월"),
                ("rowLimit", "18"),
                ("searchorder", "01"),
            ]

            # Добавляем reprcarcd для каждой модели
            for model_code in model_codes:
                data.append(("arrReprcarcd", model_code))

            # Добавляем searchArray для каждой модели
            for search_array in search_arrays:
                data.append(("searchArray", search_array))

            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": "https://auction.autobell.co.kr",
                "Referer": "https://auction.autobell.co.kr/auction/exhibitList.do?atn=747&acc=30&auctListStat=&flag=Y",
                "X-Requested-With": "XMLHttpRequest",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }

            response = self.session.post(url, data=data, headers=headers, timeout=30)
            if response.status_code != 200:
                logger.error(f"❌ Ошибка HTTP: {response.status_code}")
                return GlovisDetailModelsResponse(
                    success=False,
                    message=f"HTTP ошибка: {response.status_code}",
                    timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                )

            # Парсим JSON ответ
            detail_models = self.parser.parse_detail_models(response.json())

            duration = time.time() - start_time
            logger.info(
                f"✅ Получено {len(detail_models)} детальных моделей за {duration:.2f}с"
            )

            return GlovisDetailModelsResponse(
                success=True,
                message=f"Получено {len(detail_models)} детальных моделей",
                detail_models=detail_models,
                total_count=len(detail_models),
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            )

        except Exception as e:
            logger.error(f"❌ Ошибка при получении детальных моделей: {e}")
            return GlovisDetailModelsResponse(
                success=False,
                message=f"Ошибка: {str(e)}",
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            )

    async def search_cars_with_filters(
        self, filters: GlovisFilterOptions
    ) -> GlovisFilteredCarsResponse:
        """
        Поиск автомобилей с применением фильтров

        Args:
            filters: Параметры фильтрации

        Returns:
            GlovisFilteredCarsResponse: Результаты поиска с применёнными фильтрами
        """
        try:
            logger.info(f"🔍 Поиск автомобилей с фильтрами: {filters.dict()}")
            start_time = time.time()

            # Проверяем валидность сессии
            session_check = await self.check_session_validity()
            if not session_check.get("is_valid", False):
                logger.warning("⚠️ Обновляем сессию...")
                self.refresh_session()

            url = f"{self.base_url}/auction/exhibitListInclude.do"

            # Подготавливаем данные для фильтрации
            row_from = str((filters.page - 1) * filters.page_size + 1)

            data = {
                "rowFrom": row_from,
                "page": str(filters.page),
                "nowexhino": "",
                "flagHouse": "W",
                "flag": "Y",
                "bidcd": "",
                "exportAuctionYn": "N",
                "ac": "TQhYt3GD6GvgPdVw1QX+Wg==",
                "atn": "747",
                "acc": "30",
                "rc": filters.location or "",
                "gn": "",
                "searchRc": "",
                "sdistancecd": filters.min_mileage or "",
                "edistancecd": filters.max_mileage or "",
                "missioncd": filters.transmission or "",
                "carcd": "",
                "prodmancd": "",
                "prodmannm": "",
                "cargradcd": filters.car_grade or "",
                "cargradnm": "",
                "reprcarcd": "",
                "reprcarnm": "",
                "detacarcd": "",
                "detacarnm": "",
                "carPrice": "",
                "menuCd": "MCUA",
                "searchtype": filters.search_type or "",
                "searchtext": filters.search_text or "",
                "deviceType": "",
                "auctstardt": "20250614090000",
                "auctenddt": "20250616120000",
                "primeAuctionChk": "",
                "primeauctionyn": "N",
                "primeauctionAlertMessage": "",
                "searchInput": "",
                "exceptEmptYn": "Y",
                "sprice": str(filters.min_price) if filters.min_price else "",
                "eprice": str(filters.max_price) if filters.max_price else "",
                "syearcd": str(filters.min_year) if filters.min_year else "",
                "eyearcd": str(filters.max_year) if filters.max_year else "",
                "searchAuctno": "747",
                "auctroomcd": "",
                "publicauctionsdt": "20250614090000",
                "publicauctionedt": "20250616120000",
                "publicauctionsday": "토",
                "publicauctioneday": "월",
                "rowLimit": str(filters.page_size),
                "searchorder": filters.sort_order or "01",
            }

            # Добавляем фильтры производителей
            if filters.manufacturers:
                for manufacturer in filters.manufacturers:
                    data["arrProdmancd"] = manufacturer

            # Добавляем фильтры моделей
            if filters.models:
                for model in filters.models:
                    data["arrReprcarcd"] = model

            # Добавляем фильтры детальных моделей
            if filters.detail_models:
                for detail_model in filters.detail_models:
                    data["arrDetacarcd"] = detail_model

            # Формируем searchArray
            search_arrays = []
            if filters.manufacturers:
                for manufacturer in filters.manufacturers:
                    if filters.models:
                        for model in filters.models:
                            if filters.detail_models:
                                for detail_model in filters.detail_models:
                                    search_arrays.append(
                                        f"{manufacturer}_{model}_{detail_model}"
                                    )
                            else:
                                search_arrays.append(f"{manufacturer}_{model}")
                    else:
                        search_arrays.append(manufacturer)

            if search_arrays:
                data["searchArray"] = "_".join(search_arrays)

            headers = {
                "Accept": "text/html, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": "https://auction.autobell.co.kr",
                "Referer": "https://auction.autobell.co.kr/auction/exhibitList.do?atn=747&acc=30&auctListStat=&flag=Y",
                "X-Requested-With": "XMLHttpRequest",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }

            response = self.session.post(url, data=data, headers=headers, timeout=30)
            if response.status_code != 200:
                logger.error(f"❌ Ошибка HTTP: {response.status_code}")
                return GlovisFilteredCarsResponse(
                    success=False,
                    message=f"HTTP ошибка: {response.status_code}",
                    applied_filters=filters,
                    timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                )

            # Парсим результаты
            result = self.parser.parse_car_list(response.text, filters.page)

            # Вычисляем пагинацию
            total_pages = (
                result.total_count + filters.page_size - 1
            ) // filters.page_size
            has_next_page = filters.page < total_pages
            has_prev_page = filters.page > 1

            duration = time.time() - start_time
            logger.info(
                f"✅ Найдено {result.total_count} автомобилей за {duration:.2f}с"
            )

            return GlovisFilteredCarsResponse(
                success=True,
                message=f"Найдено {result.total_count} автомобилей",
                applied_filters=filters,
                cars=result.cars,
                total_count=result.total_count,
                current_page=filters.page,
                page_size=filters.page_size,
                total_pages=total_pages,
                has_next_page=has_next_page,
                has_prev_page=has_prev_page,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                request_duration=duration,
            )

        except Exception as e:
            logger.error(f"❌ Ошибка при поиске с фильтрами: {e}")
            return GlovisFilteredCarsResponse(
                success=False,
                message=f"Ошибка: {str(e)}",
                applied_filters=filters,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            )

    def close(self):
        """Закрывает сессию"""
        if self._session:
            self._session.close()
            self._session = None

    def __del__(self):
        """Деструктор"""
        self.close()

    def _load_cookies_from_curl_file(self) -> Optional[Dict[str, str]]:
        """
        Загружает cookies из glovis-curl-request.py файла для восстановления сессии

        Returns:
            Optional[Dict[str, str]]: Cookies из curl файла или None если не найдены
        """
        try:
            import os
            import sys
            import importlib.util

            # Путь к curl файлу
            curl_file_path = os.path.join(os.getcwd(), "glovis-curl-request.py")

            if not os.path.exists(curl_file_path):
                logger.warning("⚠️ Файл glovis-curl-request.py не найден")
                return None

            # Импортируем модуль
            spec = importlib.util.spec_from_file_location("glovis_curl", curl_file_path)
            curl_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(curl_module)

            # Извлекаем cookies
            if hasattr(curl_module, "cookies"):
                logger.info("✅ Cookies успешно загружены из glovis-curl-request.py")
                return curl_module.cookies
            else:
                logger.warning("⚠️ Не найден объект cookies в glovis-curl-request.py")
                return None

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки cookies из curl файла: {e}")
            return None

    def _emergency_cookies_update(self) -> bool:
        """
        Экстренное обновление cookies при полном отказе сессии

        Returns:
            bool: True если cookies успешно обновлены
        """
        try:
            logger.info("🚨 Экстренное обновление cookies...")

            # Пытаемся загрузить из curl файла
            curl_cookies = self._load_cookies_from_curl_file()
            if curl_cookies:
                logger.info("🔄 Обновляю cookies из glovis-curl-request.py")
                self.update_cookies(curl_cookies)

                # Пересоздаем сессию с новыми cookies
                if self._session:
                    self._session.close()
                self._session = None
                self._authenticated = False

                logger.success("✅ Экстренное обновление cookies выполнено")
                return True
            else:
                logger.error("❌ Не удалось загрузить cookies из curl файла")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка экстренного обновления cookies: {e}")
            return False
