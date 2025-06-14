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

        # Добавляем cookies из примера (они необходимы для авторизации)
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
            "JSESSIONID": "NdPgk57bazPJlaomopbX3xyC9IG3oIYIZ514rPlhzR2qBLXKlGjCM1cGB7i4BeX0.QXV0b0F1Y3Rpb24vQXV0b0F1Y3Rpb24y",
            "_ga_H9G80S9QWN": "GS2.1.s1749872843$o4$g1$t1749873569$j60$l0$h0",
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
                "atn": "944",
                "acc": "20",
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
                "auctstardt": "20250617130000",
                "auctenddt": "",
                "primeAuctionChk": "",
                "primeauctionyn": "",
                "primeauctionAlertMessage": "",
                "searchInput": "",
                "exceptEmptYn": "Y",
                "sprice": "",
                "eprice": "",
                "syearcd": "",
                "eyearcd": "",
                "searchAuctno": "944",
                "auctroomcd": "",
                "searchLanecd": "",
                "auctListStat": "",
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
                "Referer": f"{self.base_url}/auction/exhibitList.do?acc=20&atn=&flag=Y",
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
                logger.info(
                    f"✅ Успешно получили HTML (размер: {len(response.text)} символов)"
                )
                return response.text
            else:
                logger.error(f"❌ HTTP ошибка: {response.status_code}")
                logger.error(f"Ответ: {response.text[:1000]}...")
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

    def close(self):
        """Закрывает сессию"""
        if self._session:
            self._session.close()
            self._session = None

    def __del__(self):
        """Деструктор"""
        self.close()
