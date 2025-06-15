import asyncio
import time
from typing import List, Optional, Dict, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fake_useragent import UserAgent

from app.models.glovis import GlovisCar, GlovisResponse, GlovisError
from app.parsers.glovis_parser import GlovisParser
from app.core.config import get_settings
from app.core.logging import get_logger

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

    @property
    def session(self) -> requests.Session:
        """Получить настроенную сессию для HTTP запросов"""
        if self._session is None:
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

        # Обновленные cookies из рабочего примера (необходимы для авторизации)
        cookies = {
            "SCOUTER": "z6d9hgnq5i09ho",
            "_gcl_au": "1.1.469301602.1749863933",
            "_fwb": "191nmCARVubatjoH72cRPm8.1749863933091",
            "_gid": "GA1.3.448482619.1749863933",
            "_fbp": "fb.2.1749863933206.396345519817813213",
            "_gcl_aw": "GCL.1749867756.EAIaIQobChMI5I30r-3vjQMV9V4PAh1xVhhmEAAYASAAEgInMPD_BwE",
            "_gcl_gs": "2.1.k1$i1749867755$u107600402",
            "_gac_UA-163217058-4": "1.1749867756.EAIaIQobChMI5I30r-3vjQMV9V4PAh1xVhhmEAAYASAAEgInMPD_BwE",
            "_ga": "GA1.1.1367887267.1749863933",
            "_ga_WBXP3Q01TE": "GS2.1.s1749866209$o2$g1$t1749867760$j56$l0$h0",
            "JSESSIONID": "rfrLu3sj9IRm4MoFMcfDvqaqAI9sxZAoHTvftMaVu4b54U82lm5TOqlZJSdsT1JI.QXV0b0F1Y3Rpb24vQXV0b0F1Y3Rpb24x",
            "_ga_H9G80S9QWN": "GS2.1.s1749948942$o5$g1$t1749948990$j12$l0$h0",
        }

        # Устанавливаем cookies
        for name, value in cookies.items():
            session.cookies.set(name, value)

        # Отключаем проверку SSL сертификатов
        session.verify = False

        # Подавляем предупреждения о незащищённых запросах
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
                    logger.error("❌ Не удалось восстановить валидную сессию")
                    return None

            # Подготавливаем данные для POST запроса на основе примера
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
                "atn": "747",
                "acc": "30",
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
                "auctstardt": "20250614090000",
                "auctenddt": "20250616120000",
                "primeAuctionChk": "",
                "primeauctionyn": "N",
                "primeauctionAlertMessage": "",
                "searchInput": "",
                "exceptEmptYn": "Y",
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
                    data["searchAuctno"] = str(params["auction_number"])

            # Настраиваем headers для POST запроса
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/auction/exhibitList.do?atn=747&acc=30&auctListStat=&flag=Y",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "X-Requested-With": "XMLHttpRequest",
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
            test_url = f"{self.base_url}/auction/exhibitList.do?atn=747&acc=30&flag=Y"

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

    def refresh_session(self):
        """Принудительно обновляет сессию и cookies"""
        logger.info("🔄 Принудительное обновление сессии Glovis")
        if self._session:
            self._session.close()
        self._session = None
        self._authenticated = False
        # При следующем обращении сессия будет создана заново

    def close(self):
        """Закрывает сессию"""
        if self._session:
            self._session.close()
            self._session = None

    def __del__(self):
        """Деструктор"""
        self.close()
