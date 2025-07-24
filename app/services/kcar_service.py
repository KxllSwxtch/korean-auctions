import requests
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List
from urllib3.exceptions import InsecureRequestWarning
from urllib3 import disable_warnings
from loguru import logger
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.models.kcar import (
    KCarCar,
    KCarResponse,
    KCarDetailResponse,
    KCarModelsResponse,
    KCarGenerationsResponse,
    KCarSearchResponse,
    KCarSearchFilters,
    KCAR_MANUFACTURERS,
    KCAR_API_MANUFACTURERS,
    KCAR_UI_TO_API_MAPPING,
    KCarManufacturer,
)
from app.parsers.kcar_parser import KCarParser

# Отключаем предупреждения SSL
disable_warnings(InsecureRequestWarning)


def convert_ui_to_api_code(ui_code: str) -> str:
    """Преобразует UI код производителя в API код"""
    return KCAR_UI_TO_API_MAPPING.get(ui_code, ui_code)


class KCarService:
    """Сервис для работы с KCar API - только weekly аукционы"""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = "https://www.kcarauction.com"
        self.image_base_url = "https://www.kcarauction.com/attachment/CAR_IMG"  # Базовый URL для изображений
        self.parser = KCarParser()
        self.session = requests.Session()
        self.ua = UserAgent()
        self.authenticated = False

        # Учетные данные из конфигурации
        self.username = "autobaza"
        self.password = "for1657721@"

        logger.info("🔧 KCar Service инициализирован (только weekly аукционы)")
        self._initialize_session()

    def _initialize_session(self):
        """Инициализация HTTP сессии"""
        try:
            # Настройка сессии
            self.session.verify = False  # Отключаем проверку SSL
            self.session.timeout = 30

            # Базовые заголовки
            self.session.headers.update(
                {
                    "User-Agent": self.ua.random,
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
                    "Connection": "keep-alive",
                    "X-Requested-With": "XMLHttpRequest",
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"macOS"',
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                }
            )

            logger.info("🔧 HTTP сессия инициализирована")

            # Выполняем авторизацию
            self._authenticate()

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации сессии: {e}")

    def _authenticate(self) -> bool:
        """
        Авторизация на сайте KCar

        Returns:
            bool: True если авторизация успешна
        """
        try:
            logger.info("🔐 Начинаю авторизацию на KCar...")

            # Получаем главную страницу для получения cookies
            main_page_url = f"{self.base_url}/kcar/user/user_login.do"

            response = self.session.get(main_page_url)
            if response.status_code != 200:
                logger.error(
                    f"❌ Не удалось загрузить страницу логина: {response.status_code}"
                )
                return False

            logger.info("✅ Страница логина загружена")

            # Подготавливаем данные для авторизации (как в JavaScript)
            login_data = {
                "user_id": self.username,
                "user_pw": self.password,
            }

            # Заголовки для AJAX запроса
            login_headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": self.base_url,
                "Referer": main_page_url,
                "X-Requested-With": "XMLHttpRequest",
            }

            # Выполняем авторизацию через AJAX endpoint
            login_url = f"{self.base_url}/kcar/user/user_logincheck_ajax.do"

            logger.info(f"📡 Отправляю запрос авторизации к: {login_url}")
            logger.debug(f"🔍 Данные логина: user_id={self.username}")

            response = self.session.post(
                login_url, data=login_data, headers=login_headers
            )

            if response.status_code == 200:
                try:
                    response_data = response.json()

                    # Проверяем успешность авторизации
                    if response_data.get("successYn") == "Y":
                        logger.success("✅ Авторизация KCar успешна!")

                        # Если есть дополнительные шаги (bid_agree), обрабатываем их
                        user_vo = response_data.get("userVo", {})
                        if user_vo:
                            logger.info(
                                "📋 Обрабатываю дополнительные параметры пользователя"
                            )
                            # Отправляем согласие на участие в торгах
                            if self._send_bid_agreement():
                                self.authenticated = True
                                return True
                            else:
                                logger.error(
                                    "❌ Не удалось подтвердить согласие на участие в торгах"
                                )
                                return False
                        else:
                            self.authenticated = True
                            return True
                    else:
                        error_message = response_data.get(
                            "message", "Неизвестная ошибка"
                        )
                        logger.error(f"❌ Ошибка авторизации KCar: {error_message}")
                        return False

                except json.JSONDecodeError as e:
                    logger.error(f"❌ Ошибка парсинга JSON ответа авторизации: {e}")
                    logger.debug(f"Response text: {response.text}")
                    return False
            else:
                logger.error(f"❌ HTTP ошибка авторизации KCar: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка авторизации KCar: {e}")
            return False

    def _send_bid_agreement(self) -> bool:
        """
        Отправка согласия на участие в торгах

        Returns:
            bool: True если согласие успешно отправлено
        """
        try:
            logger.info("📋 Отправляю согласие на участие в торгах...")

            # Данные для согласия
            agreement_data = {"bid_agree_modal": "Y"}  # Согласие на участие в торгах

            # Заголовки для AJAX запроса
            agreement_headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": self.base_url,
                "X-Requested-With": "XMLHttpRequest",
            }

            # URL для отправки согласия
            agreement_url = f"{self.base_url}/kcar/user/user_confirm_ajax.do"

            logger.info(f"📡 Отправляю согласие к: {agreement_url}")

            response = self.session.post(
                agreement_url, data=agreement_data, headers=agreement_headers
            )

            if response.status_code == 200:
                try:
                    response_data = response.json()

                    # Проверяем успешность
                    if response_data.get("S_USER_ID"):
                        logger.success(
                            "✅ Согласие на участие в торгах отправлено успешно!"
                        )
                        return True
                    else:
                        logger.error("❌ Не получен S_USER_ID в ответе согласия")
                        return False

                except json.JSONDecodeError as e:
                    logger.error(f"❌ Ошибка парсинга JSON ответа согласия: {e}")
                    logger.debug(f"Response text: {response.text}")
                    return False
            else:
                logger.error(
                    f"❌ HTTP ошибка отправки согласия: {response.status_code}"
                )
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка отправки согласия: {e}")
            return False

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def get_cars(self, params: Optional[Dict[str, Any]] = None) -> KCarResponse:
        """
        Получение списка автомобилей с KCar - только weekly аукционы

        Args:
            params: Параметры запроса

        Returns:
            KCarResponse: Ответ с автомобилями
        """
        try:
            logger.info(
                "🚗 Получаю список автомобилей с KCar (только weekly аукционы)..."
            )

            # Проверяем авторизацию
            if not self.authenticated:
                logger.warning("⚠️ Нет авторизации, пытаюсь авторизоваться...")
                if not self._authenticate():
                    raise Exception("Не удалось авторизоваться")

            # Сначала проверим доступность weekly аукционов
            logger.info("🔍 Проверяю доступность weekly аукционов...")

            # Попробуем загрузить страницу weekly аукционов
            weekly_page_url = f"{self.base_url}/kcar/auction/weekly_auction/colAuction.do?PAGE_TYPE=wCfm"

            try:
                page_response = self.session.get(weekly_page_url, timeout=30)
                if page_response.status_code == 200:
                    logger.info("✅ Страница weekly аукционов доступна")

                    # Проверим содержимое страницы на наличие информации о weekly аукционах
                    page_content = page_response.text
                    if "weekly" in page_content.lower() or "위클리" in page_content:
                        logger.info(
                            "✅ Найдены упоминания weekly аукционов на странице"
                        )
                    else:
                        logger.warning(
                            "⚠️ Не найдены упоминания weekly аукционов на странице"
                        )

                else:
                    logger.warning(
                        f"⚠️ Страница weekly аукционов недоступна: HTTP {page_response.status_code}"
                    )

            except Exception as e:
                logger.warning(f"⚠️ Ошибка загрузки страницы weekly аукционов: {e}")

            # Точно копируем параметры из примеров payload
            # Пример для Line A: AUC_TYPE=weekly&MNUFTR_CD=&MODEL_GRP_CD=&MODEL_CD=&PAGE_CNT=18&START_RNUM=1&ORDER=&OPTION_CD=&FORM_YR_ST=&FORM_YR_ED=&AUC_START_PRC_ST=&AUC_START_PRC_ED=&MILG_ST=&MILG_ED=&CNO=&FUEL_CD=&GBOX_DCD=&COLOR_CD=&SRC_OPT=weekly&CAR_TYPE=&CARMD_CD=&PAGE_TYPE=wCfm&LANE_TYPE=A&TO_DATE=&FROM_DATE=&CAR_STAT_CD=&AUC_SEQ=&TODAY=&IPTCAR_DCD=&AUC_PLC_CD=
            # В KCar START_RNUM = номер страницы, а не номер записи!
            page_number = params.get("page", 1) if params else 1
            default_params = {
                "AUC_TYPE": "weekly",
                "MNUFTR_CD": "",
                "MODEL_GRP_CD": "",
                "MODEL_CD": "",
                "PAGE_CNT": str(params.get("PAGE_CNT", 100)) if params else "100",
                "START_RNUM": str(page_number),
                "ORDER": "",
                "OPTION_CD": "",
                "FORM_YR_ST": "",
                "FORM_YR_ED": "",
                "AUC_START_PRC_ST": "",
                "AUC_START_PRC_ED": "",
                "MILG_ST": "",
                "MILG_ED": "",
                "CNO": "",
                "FUEL_CD": "",
                "GBOX_DCD": "",
                "COLOR_CD": "",
                "SRC_OPT": "weekly",
                "CAR_TYPE": "",
                "CARMD_CD": "",
                "PAGE_TYPE": "wCfm",
                "LANE_TYPE": "A",  # Будем менять на A и B
                "TO_DATE": "",
                "FROM_DATE": "",
                "CAR_STAT_CD": "",
                "AUC_SEQ": "",
                "TODAY": "",
                "IPTCAR_DCD": "",
                "AUC_PLC_CD": "",
            }

            # Детальное логирование входящих параметров
            logger.info("🔍 KCar Service: Анализирую переданные параметры")
            if params:
                logger.info(f"📋 Переданные параметры фильтрации:")
                for key, value in params.items():
                    logger.info(f"  {key}: {value}")

                # Специальная диагностика для параметров модели
                if "MNUFTR_CD" in params:
                    logger.info(f"🚗 Фильтр производителя: {params['MNUFTR_CD']}")
                if "MODEL_GRP_CD" in params:
                    logger.info(f"🔧 Фильтр модели: {params['MODEL_GRP_CD']}")

                # Проверяем маппинг UI параметров в API параметры
                ui_manufacturer = params.get("manufacturer")
                ui_model = params.get("model")
                if ui_manufacturer:
                    api_manufacturer = params.get("MNUFTR_CD", ui_manufacturer)
                    logger.info(
                        f"🔄 Маппинг manufacturer -> MNUFTR_CD: {ui_manufacturer} -> {api_manufacturer}"
                    )
                if ui_model:
                    api_model = params.get("MODEL_GRP_CD", ui_model)
                    logger.info(
                        f"🔄 Маппинг model -> MODEL_GRP_CD: {ui_model} -> {api_model}"
                    )
            else:
                logger.info(
                    "📋 Параметры фильтрации не переданы, используем значения по умолчанию"
                )

            # Объединяем с переданными параметрами
            if params:
                default_params.update(params)

            # Логируем финальные параметры для отправки
            logger.info("📋 Финальные параметры для API запроса:")
            for key, value in default_params.items():
                if value:  # Показываем только непустые значения
                    logger.info(f"  {key}: {value}")

            # URL для получения списка автомобилей
            cars_url = f"{self.base_url}/kcar/auction/getAuctionCarList_ajax.do"

            # Заголовки для AJAX запроса - точно как в примере с дополнительными заголовками
            ajax_headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/kcar/auction/weekly_auction/colAuction.do?PAGE_TYPE=wCfm",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            }

            # Определяем какие лейны нужно обработать
            requested_lane_type = params.get("lane_type") if params else None
            lanes_to_process = []
            
            if requested_lane_type and requested_lane_type in ["A", "B"]:
                # Если указан конкретный лейн, обрабатываем только его
                lanes_to_process = [requested_lane_type]
                logger.info(
                    f"📡 Получаю данные только из лейна {requested_lane_type} для weekly аукционов"
                )
            else:
                # Если лейн не указан или указан как "все", обрабатываем оба
                lanes_to_process = ["A", "B"]
                logger.info(
                    f"📡 Получаю данные из обоих лейнов (A и B) для weekly аукционов"
                )

            all_cars = []
            total_count = 0

            # Получаем данные из выбранных лейнов
            for lane_type in lanes_to_process:
                logger.info(f"🛣️ Обрабатываю LANE_TYPE: {lane_type}")

                # Копируем параметры и устанавливаем тип лейна
                lane_params = default_params.copy()
                lane_params["LANE_TYPE"] = lane_type

                logger.info(f"🔍 Отправляю POST запрос к: {cars_url}")
                logger.info(f"🔍 Параметры для {lane_type}:")
                for key, value in lane_params.items():
                    logger.debug(f"  {key}={value}")

                # Попробуем несколько способов отправки данных
                success = False

                # Способ 1: Стандартный POST с form data
                try:
                    logger.info(
                        f"🔄 Попытка 1: Стандартный POST для LANE_TYPE {lane_type}"
                    )
                    response = self.session.post(
                        cars_url, data=lane_params, headers=ajax_headers, timeout=30
                    )

                    if response.status_code == 200:
                        json_data = response.json()
                        if (
                            json_data.get("auctionReqVo", {}).get("AUC_TYPE")
                            == "weekly"
                        ):
                            logger.success(
                                f"✅ Способ 1 успешен для LANE_TYPE {lane_type}"
                            )
                            success = True
                        else:
                            logger.warning(
                                f"⚠️ Способ 1: сервер вернул AUC_TYPE={json_data.get('auctionReqVo', {}).get('AUC_TYPE')}"
                            )
                    else:
                        logger.warning(f"⚠️ Способ 1: HTTP {response.status_code}")

                except Exception as e:
                    logger.warning(f"⚠️ Способ 1 не удался: {e}")

                # Способ 2: POST с URL-encoded строкой
                if not success:
                    try:
                        logger.info(
                            f"🔄 Попытка 2: URL-encoded строка для LANE_TYPE {lane_type}"
                        )

                        # Создаем URL-encoded строку вручную
                        params_str = "&".join(
                            [f"{k}={v}" for k, v in lane_params.items()]
                        )

                        # Специальные заголовки для этого способа
                        special_headers = ajax_headers.copy()
                        special_headers["Content-Length"] = str(len(params_str))

                        response = self.session.post(
                            cars_url,
                            data=params_str,
                            headers=special_headers,
                            timeout=30,
                        )

                        if response.status_code == 200:
                            json_data = response.json()
                            if (
                                json_data.get("auctionReqVo", {}).get("AUC_TYPE")
                                == "weekly"
                            ):
                                logger.success(
                                    f"✅ Способ 2 успешен для LANE_TYPE {lane_type}"
                                )
                                success = True
                            else:
                                logger.warning(
                                    f"⚠️ Способ 2: сервер вернул AUC_TYPE={json_data.get('auctionReqVo', {}).get('AUC_TYPE')}"
                                )
                        else:
                            logger.warning(f"⚠️ Способ 2: HTTP {response.status_code}")

                    except Exception as e:
                        logger.warning(f"⚠️ Способ 2 не удался: {e}")

                # Способ 3: Попробуем с дополнительными параметрами из примера
                if not success:
                    try:
                        logger.info(
                            f"🔄 Попытка 3: С дополнительными параметрами для LANE_TYPE {lane_type}"
                        )

                        # Добавляем дополнительные параметры из успешного примера
                        enhanced_params = lane_params.copy()
                        enhanced_params.update(
                            {
                                "ORDER2": "T.EXBIT_SEQ ASC",
                                "SPECIAL_YN": "",
                                "s_USER_ID": "autobaza",
                                "s_USER_IP": "",
                                "searchChannel": "",
                                "setSearch": "",
                                "CAR_STATUS_CD_LIST": "C020",
                            }
                        )

                        response = self.session.post(
                            cars_url,
                            data=enhanced_params,
                            headers=ajax_headers,
                            timeout=30,
                        )

                        if response.status_code == 200:
                            json_data = response.json()
                            if (
                                json_data.get("auctionReqVo", {}).get("AUC_TYPE")
                                == "weekly"
                            ):
                                logger.success(
                                    f"✅ Способ 3 успешен для LANE_TYPE {lane_type}"
                                )
                                success = True
                            else:
                                logger.warning(
                                    f"⚠️ Способ 3: сервер вернул AUC_TYPE={json_data.get('auctionReqVo', {}).get('AUC_TYPE')}"
                                )
                        else:
                            logger.warning(f"⚠️ Способ 3: HTTP {response.status_code}")

                    except Exception as e:
                        logger.warning(f"⚠️ Способ 3 не удался: {e}")

                # Способ 4: Попробуем использовать данные из успешного примера
                if not success:
                    try:
                        logger.info(
                            f"🔄 Попытка 4: Точная копия успешного примера для LANE_TYPE {lane_type}"
                        )

                        # Используем точные данные из kcar-linea-response.json
                        exact_params = {
                            "AUC_TYPE": "weekly",
                            "MNUFTR_CD": "",
                            "MODEL_GRP_CD": "",
                            "MODEL_CD": "",
                            "PAGE_CNT": "100",
                            "START_RNUM": "1",
                            "ORDER": "",
                            "OPTION_CD": "",
                            "FORM_YR_ST": "",
                            "FORM_YR_ED": "",
                            "AUC_START_PRC_ST": "",
                            "AUC_START_PRC_ED": "",
                            "MILG_ST": "",
                            "MILG_ED": "",
                            "CNO": "",
                            "FUEL_CD": "",
                            "GBOX_DCD": "",
                            "COLOR_CD": "",
                            "SRC_OPT": "weekly",
                            "CAR_TYPE": "",
                            "CARMD_CD": "",
                            "PAGE_TYPE": "wCfm",
                            "LANE_TYPE": lane_type,
                            "TO_DATE": "",
                            "FROM_DATE": "",
                            "CAR_STAT_CD": "",
                            "AUC_SEQ": "",
                            "TODAY": "",
                            "IPTCAR_DCD": "",
                            "AUC_PLC_CD": "",
                            # Дополнительные поля из успешного примера
                            "ALARM_YN": "",
                            "AUC_CD": "",
                            "AUC_DIV_CD": "",
                            "BID_CRT_SEQ": "",
                            "BID_DCD": "",
                            "BID_PRC": "",
                            "CAR_ID": "",
                            "CAR_ID_CNT": "0",
                            "CHECK_AUC": "",
                            "CHNG_USR_ID": "",
                            "CMN_BAS_CD": "",
                            "CMN_CD": "",
                            "CMN_CD_NM": "",
                            "CRT_USR_ID": "",
                            "DEL_YN": "",
                            "END_DATE": "",
                            "EXBIT_SEQ": "",
                            "EXPECT_PRC": "",
                            "MOBILE": "",
                            "SN_SEQ": "",
                            "SPECIAL_COMPANY_TYPE_NM": "",
                            "SPECIAL_YN": "",
                            "START_DATE": "",
                            "STAT_DCD": "",
                            "TITLE": "",
                            "TRCK_YN": "",
                            "TYPE_DCD": "",
                            "USR_ID": "",
                            "s_USER_ID": "",
                            "s_USER_IP": "",
                            "searchChannel": "",
                            "setSearch": "",
                        }

                        response = self.session.post(
                            cars_url,
                            data=exact_params,
                            headers=ajax_headers,
                            timeout=30,
                        )

                        if response.status_code == 200:
                            json_data = response.json()
                            if (
                                json_data.get("auctionReqVo", {}).get("AUC_TYPE")
                                == "weekly"
                            ):
                                logger.success(
                                    f"✅ Способ 4 успешен для LANE_TYPE {lane_type}"
                                )
                                success = True
                            else:
                                logger.warning(
                                    f"⚠️ Способ 4: сервер вернул AUC_TYPE={json_data.get('auctionReqVo', {}).get('AUC_TYPE')}"
                                )
                        else:
                            logger.warning(f"⚠️ Способ 4: HTTP {response.status_code}")

                    except Exception as e:
                        logger.warning(f"⚠️ Способ 4 не удался: {e}")

                # Если ни один способ не сработал, используем последний ответ
                if not success:
                    logger.error(
                        f"❌ Все способы не удались для LANE_TYPE {lane_type}, используем последний ответ"
                    )

                logger.info(
                    f"📊 HTTP статус для LANE_TYPE {lane_type}: {response.status_code}"
                )

                if response.status_code != 200:
                    logger.error(
                        f"❌ Ошибка HTTP {response.status_code} для LANE_TYPE {lane_type}"
                    )
                    logger.debug(f"Response text: {response.text[:500]}...")
                    continue

                # Парсим JSON ответ
                try:
                    json_data = response.json()
                    logger.info(
                        f"✅ Получен JSON ответ от KCar для LANE_TYPE {lane_type}"
                    )

                    # Детальная диагностика ответа
                    if "CAR_LIST" in json_data:
                        car_count = len(json_data["CAR_LIST"])
                        logger.info(
                            f"🔍 Найдено {car_count} автомобилей в CAR_LIST для LANE_TYPE {lane_type}"
                        )

                        # Показываем информацию о запросе
                        if "auctionReqVo" in json_data:
                            req_vo = json_data["auctionReqVo"]
                            logger.info(
                                f"📋 Информация о запросе для LANE_TYPE {lane_type}:"
                            )
                            logger.info(
                                f"  AUC_TYPE: {req_vo.get('AUC_TYPE', 'не найден')}"
                            )
                            logger.info(
                                f"  AUC_STAT: {req_vo.get('AUC_STAT', 'не найден')}"
                            )
                            logger.info(
                                f"  LANE_TYPE: {req_vo.get('LANE_TYPE', 'не найден')}"
                            )
                            logger.info(
                                f"  PAGE_CNT: {req_vo.get('PAGE_CNT', 'не найден')}"
                            )
                            logger.info(
                                f"  START_RNUM: {req_vo.get('START_RNUM', 'не найден')}"
                            )
                            logger.info(
                                f"  END_RNUM: {req_vo.get('END_RNUM', 'не найден')}"
                            )
                            logger.info(
                                f"  SRC_OPT: {req_vo.get('SRC_OPT', 'не найден')}"
                            )
                            logger.info(
                                f"  PAGE_TYPE: {req_vo.get('PAGE_TYPE', 'не найден')}"
                            )
                            logger.info(
                                f"  ORDER2: {req_vo.get('ORDER2', 'не найден')}"
                            )

                        # Если нет автомобилей, сохраняем полный ответ для анализа
                        if car_count == 0:
                            debug_file = f"debug_kcar_weekly_{lane_type}_empty.json"
                            import json as json_lib

                            with open(debug_file, "w", encoding="utf-8") as f:
                                json_lib.dump(
                                    json_data, f, ensure_ascii=False, indent=2
                                )
                            logger.warning(
                                f"💾 Пустой ответ сохранен в {debug_file} для анализа"
                            )
                        else:
                            # Сохраняем успешный ответ для сравнения
                            debug_file = f"debug_kcar_weekly_{lane_type}_success.json"
                            import json as json_lib

                            with open(debug_file, "w", encoding="utf-8") as f:
                                json_lib.dump(
                                    json_data, f, ensure_ascii=False, indent=2
                                )
                            logger.info(f"💾 Успешный ответ сохранен в {debug_file}")
                    else:
                        logger.error(
                            f"❌ CAR_LIST не найден в ответе для LANE_TYPE {lane_type}"
                        )
                        logger.debug(f"🔍 Ключи в ответе: {list(json_data.keys())}")

                    # Нормализуем данные перед парсингом
                    normalized_data = self.normalize_response_data(json_data)

                    # Обрабатываем данные через парсер с параметрами пагинации
                    page_number = params.get("page", 1) if params else 1
                    page_size = int(params.get("PAGE_CNT", 50)) if params else 50
                    lane_result = self.parser.parse_cars_json(
                        normalized_data, page=page_number, page_size=page_size
                    )

                    if lane_result.success and lane_result.car_list:
                        # Добавляем информацию о лейне к каждому автомобилю
                        for car in lane_result.car_list:
                            # Создаем новый объект с lane_type
                            car_dict = car.dict()
                            car_dict['lane_type'] = lane_type
                            car_with_lane = KCarCar(**car_dict)
                            all_cars.append(car_with_lane)

                        logger.success(
                            f"✅ Получено {len(lane_result.car_list)} автомобилей из LANE_TYPE {lane_type}"
                        )
                        total_count += len(lane_result.car_list)
                    else:
                        logger.warning(f"⚠️ Пустой список для LANE_TYPE {lane_type}")
                        if not lane_result.success:
                            logger.error(f"❌ Ошибка парсера: {lane_result.message}")

                except json.JSONDecodeError as e:
                    logger.error(
                        f"❌ Ошибка парсинга JSON для LANE_TYPE {lane_type}: {e}"
                    )
                    logger.debug(f"Response text: {response.text[:500]}...")
                    continue

            # Параметры пагинации уже извлечены выше

            # Рассчитываем поля пагинации
            total_pages = None
            has_next_page = False
            has_prev_page = page_number > 1

            if total_count > 0:
                total_pages = (total_count + page_size - 1) // page_size
                has_next_page = page_number < total_pages

            # Создаем результат
            if all_cars:
                result = KCarResponse(
                    car_list=all_cars,
                    total_count=total_count,
                    current_page=page_number,
                    page_size=page_size,
                    total_pages=total_pages,
                    has_next_page=has_next_page,
                    has_prev_page=has_prev_page,
                    success=True,
                    message=f"Успешно получено {total_count} автомобилей из weekly аукционов (LANE {'+'.join(lanes_to_process)})",
                )

                logger.success(
                    f"✅ Объединено {total_count} автомобилей из лейнов {lanes_to_process} (страница {page_number}/{total_pages})"
                )
                return result
            else:
                # Пустой список - это нормально (торги закончились или нет активных аукционов)
                logger.info("ℹ️ Получен пустой список автомобилей из weekly аукционов")
                logger.info("💡 Возможные причины:")
                logger.info("  - Weekly аукционы уже завершились")
                logger.info("  - Нет активных weekly аукционов в данный момент")
                logger.info("  - Все автомобили были проданы")

                return KCarResponse(
                    car_list=[],
                    total_count=0,
                    current_page=page_number,
                    page_size=page_size,
                    total_pages=1,
                    has_next_page=False,
                    has_prev_page=has_prev_page,
                    success=True,  # Изменено на True - пустой список это успех
                    message="В данный момент нет доступных автомобилей в weekly аукционах. Торги могли завершиться или еще не начаться.",
                )

        except Exception as e:
            logger.error(f"❌ Ошибка получения автомобилей KCar: {e}")
            page_number = params.get("page", 1) if params else 1
            page_size = int(params.get("PAGE_CNT", 50)) if params else 50
            return KCarResponse(
                car_list=[],
                total_count=0,
                current_page=page_number,
                page_size=page_size,
                total_pages=1,
                has_next_page=False,
                has_prev_page=page_number > 1,
                success=False,
                message=f"Ошибка получения данных: {str(e)}",
            )

    def normalize_car_data(self, data: dict) -> dict:
        """
        Нормализация данных автомобиля для универсальной работы с разными API

        Поддерживает как реальные KCar данные (CAR_LIST, CAR_NM),
        так и демо данные (car_list, car_name)
        """
        try:
            # Словарь маппинга полей: стандартное_поле -> [возможные_источники]
            field_mapping = {
                "CAR_ID": ["CAR_ID", "car_id"],
                "CAR_NM": ["CAR_NM", "car_name"],
                "CNO": ["CNO", "car_number"],
                "THUMBNAIL": ["THUMBNAIL", "thumbnail"],
                "THUMBNAIL_MOBILE": ["THUMBNAIL_MOBILE", "thumbnail_mobile"],
                "AUC_STRT_PRC": ["AUC_STRT_PRC", "price", "auction_start_price"],
                "AUC_CD": ["AUC_CD", "auction_code"],
                "AUC_STAT_NM": ["AUC_STAT_NM", "auction_status_name"],
                "AUC_STRT_DT": ["AUC_STRT_DT", "auction_date"],
                "AUC_TYPE_DESC": ["AUC_TYPE_DESC", "auction_type_desc"],
                "FORM_YR": ["FORM_YR", "year"],
                "MILG": ["MILG", "mileage"],
                "ENGDISPMNT": ["ENGDISPMNT", "displacement"],
                "FUEL_CD": ["FUEL_CD", "fuel_type"],
                "GBOX_DCD": ["GBOX_DCD", "transmission"],
                "EXTERIOR_COLOR_NM": ["EXTERIOR_COLOR_NM", "exterior_color"],
                "CAR_POINT": ["CAR_POINT", "car_point"],
                "CAR_LOCT": ["CAR_LOCT", "car_location"],
                "AUC_PLC_NM": ["AUC_PLC_NM", "auction_place_name"],
                "EXBIT_SEQ": ["EXBIT_SEQ", "exhibit_seq"],
            }

            normalized = {}

            # Нормализуем каждое поле
            for target_field, source_fields in field_mapping.items():
                for source_field in source_fields:
                    if source_field in data and data[source_field] is not None:
                        normalized[target_field] = data[source_field]
                        break
                else:
                    # Если поле не найдено, используем None
                    normalized[target_field] = None

            # Копируем остальные поля как есть
            for key, value in data.items():
                if key not in [
                    field for fields in field_mapping.values() for field in fields
                ]:
                    normalized[key] = value

            return normalized

        except Exception as e:
            logger.warning(f"⚠️ Ошибка нормализации данных автомобиля: {e}")
            return data  # Возвращаем исходные данные при ошибке

    def normalize_response_data(self, response_data: dict) -> dict:
        """
        Нормализация ответа KCar API для универсальной работы

        Поддерживает разные форматы ответов от реального API и демо данных
        """
        try:
            # Получаем список автомобилей из разных возможных полей
            cars_data = response_data.get("CAR_LIST", response_data.get("car_list", []))

            # Нормализуем каждый автомобиль
            normalized_cars = []
            for car_data in cars_data:
                normalized_car = self.normalize_car_data(car_data)
                normalized_cars.append(normalized_car)

            # Создаем нормализованный ответ
            normalized_response = {
                "CAR_LIST": normalized_cars,
                "total_count": response_data.get("total_count", len(normalized_cars)),
                "auctionReqVo": response_data.get("auctionReqVo"),
                "success": response_data.get("success", True),
                "message": response_data.get("message", ""),
            }

            # Копируем дополнительные поля
            for key, value in response_data.items():
                if key not in [
                    "CAR_LIST",
                    "car_list",
                    "total_count",
                    "auctionReqVo",
                    "success",
                    "message",
                ]:
                    normalized_response[key] = value

            return normalized_response

        except Exception as e:
            logger.error(f"❌ Ошибка нормализации ответа: {e}")
            return response_data

    def get_test_cars(self, count: int = 10) -> KCarResponse:
        """
        Получение тестовых данных автомобилей (только weekly)

        Args:
            count: Количество тестовых автомобилей

        Returns:
            KCarResponse: Тестовые данные
        """
        logger.info(f"🧪 Генерация {count} тестовых weekly автомобилей KCar")
        return self.parser.generate_test_data(count)

    def get_car_count(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Получение количества автомобилей (только weekly)

        Args:
            params: Параметры запроса

        Returns:
            Dict с информацией о количестве
        """
        try:
            logger.info("📊 Получаю количество weekly автомобилей KCar...")

            if not self.authenticated:
                if not self._authenticate():
                    raise Exception("Не удалось авторизоваться")

            # Параметры для weekly аукционов
            count_params = {
                "AUC_TYPE": "weekly",
                "MNUFTR_CD": "",
                "MODEL_GRP_CD": "",
                "MODEL_CD": "",
                "SRC_OPT": "weekly",
                "PAGE_TYPE": "wCfm",
                "LANE_TYPE": "A",
                "TO_DATE": "",
                "FROM_DATE": "",
                "AUC_SEQ": "",
                "CAR_STAT_CD": "",
                "TODAY": "",
                "CAR_TYPE": "",
                "CARMD_CD": "",
                "IPTCAR_DCD": "",
                "AUC_PLC_CD": "",
            }

            if params:
                count_params.update(params)

            # URL для получения количества
            count_url = f"{self.base_url}/kcar/auction/auctionCarCount_ajax.do"

            response = self.session.post(
                count_url,
                data=count_params,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
                },
            )

            if response.status_code == 200:
                try:
                    result = response.json()
                    result["auction_type"] = "weekly"
                    return result
                except:
                    return {
                        "count": 0,
                        "message": "Не удалось получить количество",
                        "auction_type": "weekly",
                    }
            else:
                return {
                    "count": 0,
                    "message": f"HTTP {response.status_code}",
                    "auction_type": "weekly",
                }

        except Exception as e:
            logger.error(f"❌ Ошибка получения количества: {e}")
            return {"count": 0, "message": str(e), "auction_type": "weekly"}

    def get_image_url(self, thumbnail_path: Optional[str]) -> Optional[str]:
        """
        Формирует полный URL изображения из относительного пути

        Args:
            thumbnail_path: Относительный путь к изображению

        Returns:
            Полный URL изображения или None
        """
        if not thumbnail_path:
            return None

        # Если путь уже содержит полный URL
        if thumbnail_path.startswith("http"):
            return thumbnail_path

        # Формируем полный URL
        if thumbnail_path.startswith("/"):
            return f"{self.image_base_url}{thumbnail_path}"
        else:
            return f"{self.image_base_url}/{thumbnail_path}"

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def get_car_detail(
        self, car_id: str, auction_code: str, page_type: str = "wCfm"
    ) -> "KCarDetailResponse":
        """
        Получение детальной информации об автомобиле

        Args:
            car_id: ID автомобиля
            auction_code: Код аукциона
            page_type: Тип страницы (по умолчанию wCfm)

        Returns:
            KCarDetailResponse с детальной информацией об автомобиле
        """
        from app.models.kcar import KCarDetailResponse

        try:
            logger.info(f"🔍 Получение детальной информации для автомобиля {car_id}")

            if not self.authenticated:
                logger.warning("⚠️ Не авторизован, пытаюсь авторизоваться...")
                if not self._authenticate():
                    return KCarDetailResponse(
                        car=None, success=False, message="Ошибка авторизации"
                    )

            # URL для получения детальной информации
            detail_url = (
                f"{self.base_url}/kcar/auction/weekly_detail/auction_detail_view.do"
            )

            # Параметры запроса
            params = {
                "PAGE_TYPE": page_type,
                "CAR_ID": car_id,
                "AUC_CD": auction_code,
            }

            # Данные для POST запроса
            data = {
                "setSearch": "",
            }

            # Заголовки для запроса детальной страницы
            detail_headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
                "Cache-Control": "max-age=0",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/kcar/auction/weekly_auction/colAuction.do?PAGE_TYPE=wCfm&LANE_TYPE=A",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": self.ua.random,
                "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
            }

            logger.info(f"📡 Отправляю запрос детальной информации: {detail_url}")
            logger.debug(f"🔍 Параметры: {params}")

            response = self.session.post(
                detail_url, params=params, data=data, headers=detail_headers, timeout=30
            )

            if response.status_code == 200:
                logger.info(f"✅ Получена детальная страница автомобиля {car_id}")

                # Парсим HTML страницу
                detail_response = self.parser.parse_car_detail_html(
                    response.text, car_id, auction_code
                )

                if detail_response.success:
                    logger.success(
                        f"✅ Детальная информация успешно извлечена для {car_id}"
                    )
                    return detail_response
                else:
                    logger.error(
                        f"❌ Ошибка парсинга детальной информации: {detail_response.message}"
                    )
                    return detail_response

            else:
                error_msg = f"HTTP ошибка получения детальной информации: {response.status_code}"
                logger.error(f"❌ {error_msg}")
                return KCarDetailResponse(car=None, success=False, message=error_msg)

        except requests.exceptions.Timeout:
            error_msg = "Таймаут получения детальной информации"
            logger.error(f"⏱️ {error_msg}")
            return KCarDetailResponse(car=None, success=False, message=error_msg)

        except requests.exceptions.RequestException as e:
            error_msg = f"Ошибка запроса детальной информации: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return KCarDetailResponse(car=None, success=False, message=error_msg)

        except Exception as e:
            error_msg = f"Неожиданная ошибка получения детальной информации: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return KCarDetailResponse(car=None, success=False, message=error_msg)

    def close(self):
        """Закрытие сервиса"""
        if self.session:
            self.session.close()
            logger.info("🔒 KCar Service закрыт")

    def find_car_id_by_number(self, car_number: str, auction_code: str = None) -> dict:
        """
        Поиск автомобиля по номеру

        Args:
            car_number: Номер автомобиля для поиска
            auction_code: Код аукциона (опционально)

        Returns:
            dict: Информация о найденном автомобиле или ошибка
        """
        try:
            logger.info(f"🔍 Поиск автомобиля по номеру: {car_number}")

            if not self.authenticated:
                logger.warning("⚠️ Не авторизован, выполняю авторизацию...")
                if not self._authenticate():
                    return {
                        "success": False,
                        "message": "Ошибка авторизации",
                        "car": None,
                    }

            # Параметры для поиска всех автомобилей
            params = {"AUC_TYPE": "weekly", "PAGE_CNT": 100}

            if auction_code:
                params["AUC_CD"] = auction_code
                logger.info(f"🔍 Поиск в конкретном аукционе: {auction_code}")
            else:
                logger.info("🔍 Поиск во всех аукционах")

            # Получаем список автомобилей
            response = self.get_cars(params)

            if not response.success:
                return {
                    "success": False,
                    "message": "Ошибка получения списка автомобилей",
                    "car": None,
                }

            # Ищем автомобиль по номеру
            found_car = None
            search_number = car_number.strip().lower()

            # Сначала точное совпадение
            for car in response.car_list:
                if car.car_number and car.car_number.strip().lower() == search_number:
                    found_car = car
                    logger.info(f"🎯 Найдено точное совпадение: {car.car_number}")
                    break

            # Если точного совпадения нет, ищем частичное
            if not found_car:
                for car in response.car_list:
                    if car.car_number and (
                        search_number in car.car_number.lower()
                        or car.car_number.lower() in search_number
                    ):
                        found_car = car
                        logger.info(
                            f"🔍 Найдено частичное совпадение: {car.car_number}"
                        )
                        break

            if found_car:
                # Определяем тип совпадения
                match_type = (
                    "exact_match"
                    if found_car.car_number.strip().lower() == search_number
                    else "partial_match"
                )
                confidence = 1.0 if match_type == "exact_match" else 0.8

                logger.success(
                    f"✅ Найден автомобиль: {found_car.car_id} - {found_car.car_name}"
                )
                return {
                    "success": True,
                    "message": f"Найден автомобиль с номером {car_number}",
                    "car_id": found_car.car_id,
                    "car_number": found_car.car_number,
                    "match_type": match_type,
                    "confidence": confidence,
                    "searched_count": len(response.car_list),
                    "all_matches": [found_car.car_id],
                    "car": found_car,
                }
            else:
                logger.info(f"ℹ️ Автомобиль с номером {car_number} не найден")
                return {
                    "success": False,
                    "message": f"Автомобиль с номером {car_number} не найден",
                    "searched_count": (
                        len(response.car_list) if response and response.car_list else 0
                    ),
                    "car": None,
                }

        except Exception as e:
            logger.error(f"❌ Ошибка поиска автомобиля по номеру: {e}")
            return {
                "success": False,
                "message": f"Ошибка поиска: {str(e)}",
                "car": None,
            }

    # =============================================================================
    # МЕТОДЫ СИСТЕМЫ ФИЛЬТРАЦИИ
    # =============================================================================

    def get_manufacturers(self) -> List[Dict[str, str]]:
        """
        Получить статический список производителей

        Returns:
            List[Dict]: Список производителей
        """
        try:
            logger.info("📋 Получение списка производителей KCar")

            manufacturers = []
            for manufacturer in KCAR_MANUFACTURERS:
                manufacturers.append(manufacturer.model_dump())

            logger.success(f"✅ Возвращено {len(manufacturers)} производителей")
            return manufacturers

        except Exception as e:
            logger.error(f"❌ Ошибка получения списка производителей: {e}")
            return []

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def get_models(
        self, manufacturer_code: str, input_car_code: str = "001"
    ) -> KCarModelsResponse:
        """
        Получить список моделей для производителя

        Args:
            manufacturer_code: Код производителя
            input_car_code: Код типа автомобиля (по умолчанию "001")

        Returns:
            KCarModelsResponse: Ответ с списком моделей
        """
        try:
            logger.info(f"📋 Получение моделей для производителя {manufacturer_code}")

            if not self.authenticated:
                logger.warning("⚠️ Не авторизован, выполняю авторизацию...")
                if not self._authenticate():
                    return KCarModelsResponse(
                        models=[], success=False, message="Ошибка авторизации"
                    )

            # Преобразуем UI код в API код
            api_manufacturer_code = convert_ui_to_api_code(manufacturer_code)
            logger.info(
                f"🔄 Преобразование кода: {manufacturer_code} -> {api_manufacturer_code}"
            )

            # Подготовка данных запроса (как в models.py)
            data = {
                "MNUFTR_CD": api_manufacturer_code,
                "IPTCAR_DCD": input_car_code,
            }

            # Заголовки для AJAX запроса
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/kcar/auction/weekly_auction/colAuction.do?PAGE_TYPE=wCfm&LANE_TYPE=A",
                "X-Requested-With": "XMLHttpRequest",
            }

            # URL для получения моделей
            url = f"{self.base_url}/kcar/main/model_ajax.do"

            logger.info(f"📡 Отправляю запрос на получение моделей: {url}")
            logger.debug(f"🔍 Данные запроса: {data}")

            response = self.session.post(url, data=data, headers=headers)

            if response.status_code == 200:
                try:
                    json_data = response.json()
                    logger.debug(f"📥 Получен JSON ответ моделей")

                    # Парсим ответ
                    result = self.parser.parse_models_json(json_data)

                    logger.success(
                        f"✅ Получено {len(result.models)} моделей для производителя {manufacturer_code}"
                    )
                    return result

                except json.JSONDecodeError as e:
                    logger.error(f"❌ Ошибка парсинга JSON ответа моделей: {e}")
                    return KCarModelsResponse(
                        models=[],
                        success=False,
                        message=f"Ошибка парсинга ответа: {str(e)}",
                    )
            else:
                logger.error(
                    f"❌ HTTP ошибка получения моделей: {response.status_code}"
                )
                return KCarModelsResponse(
                    models=[],
                    success=False,
                    message=f"HTTP ошибка: {response.status_code}",
                )

        except Exception as e:
            logger.error(f"❌ Ошибка получения моделей: {e}")
            return KCarModelsResponse(
                models=[], success=False, message=f"Ошибка запроса: {str(e)}"
            )

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def get_generations(
        self, manufacturer_code: str, model_group_code: str, input_car_code: str = "001"
    ) -> KCarGenerationsResponse:
        """
        Получить список поколений для модели

        Args:
            manufacturer_code: Код производителя
            model_group_code: Код группы модели
            input_car_code: Код типа автомобиля (по умолчанию "001")

        Returns:
            KCarGenerationsResponse: Ответ с списком поколений
        """
        try:
            logger.info(
                f"📋 Получение поколений для модели {model_group_code} производителя {manufacturer_code}"
            )

            if not self.authenticated:
                logger.warning("⚠️ Не авторизован, выполняю авторизацию...")
                if not self._authenticate():
                    return KCarGenerationsResponse(
                        generations=[], success=False, message="Ошибка авторизации"
                    )

            # Преобразуем UI код в API код
            api_manufacturer_code = convert_ui_to_api_code(manufacturer_code)
            logger.info(
                f"🔄 Преобразование кода: {manufacturer_code} -> {api_manufacturer_code}"
            )

            # Подготовка данных запроса (как в generations.py)
            data = {
                "MNUFTR_CD": api_manufacturer_code,
                "MODEL_GRP_CD": model_group_code,
                "IPTCAR_DCD": input_car_code,
            }

            # Заголовки для AJAX запроса
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/kcar/auction/weekly_auction/colAuction.do?PAGE_TYPE=wCfm&LANE_TYPE=A",
                "X-Requested-With": "XMLHttpRequest",
            }

            # URL для получения поколений
            url = f"{self.base_url}/kcar/main/modelDetail_ajax.do"

            logger.info(f"📡 Отправляю запрос на получение поколений: {url}")
            logger.debug(f"🔍 Данные запроса: {data}")

            response = self.session.post(url, data=data, headers=headers)

            if response.status_code == 200:
                try:
                    json_data = response.json()
                    logger.debug(f"📥 Получен JSON ответ поколений")

                    # Парсим ответ
                    result = self.parser.parse_generations_json(json_data)

                    logger.success(
                        f"✅ Получено {len(result.generations)} поколений для модели {model_group_code}"
                    )
                    return result

                except json.JSONDecodeError as e:
                    logger.error(f"❌ Ошибка парсинга JSON ответа поколений: {e}")
                    return KCarGenerationsResponse(
                        generations=[],
                        success=False,
                        message=f"Ошибка парсинга ответа: {str(e)}",
                    )
            else:
                logger.error(
                    f"❌ HTTP ошибка получения поколений: {response.status_code}"
                )
                return KCarGenerationsResponse(
                    generations=[],
                    success=False,
                    message=f"HTTP ошибка: {response.status_code}",
                )

        except Exception as e:
            logger.error(f"❌ Ошибка получения поколений: {e}")
            return KCarGenerationsResponse(
                generations=[], success=False, message=f"Ошибка запроса: {str(e)}"
            )

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def search_cars(self, filters: KCarSearchFilters) -> KCarSearchResponse:
        """
        Расширенный поиск автомобилей с фильтрами

        Args:
            filters: Фильтры поиска

        Returns:
            KCarSearchResponse: Результаты поиска
        """
        try:
            logger.info(f"🔍 Расширенный поиск автомобилей KCar с фильтрами")
            logger.info(f"📊 Полученные фильтры в сервисе:")
            logger.info(f"  - manufacturer_code: {filters.manufacturer_code}")
            logger.info(f"  - model_group_code: {filters.model_group_code}")
            logger.info(f"  - model_code: {filters.model_code}")
            logger.debug(f"🔍 Все фильтры: {filters.model_dump()}")

            if not self.authenticated:
                logger.warning("⚠️ Не авторизован, выполняю авторизацию...")
                if not self._authenticate():
                    return KCarSearchResponse(
                        cars=[], success=False, message="Ошибка авторизации"
                    )

            # Подготовка данных запроса (как в filters-cars.py)
            data = {
                "AUC_TYPE": filters.auction_type,
                "PAGE_CNT": str(filters.page_size),
                "START_RNUM": str(filters.page),
                "ORDER": filters.sort_order or "",
                "OPTION_CD": "",
                "SRC_OPT": filters.auction_type,  # Добавляем недостающий параметр
                "CAR_TYPE": "",
                "CARMD_CD": "",
                "PAGE_TYPE": "wCfm",
                "LANE_TYPE": filters.lane_type or "",
                "TO_DATE": "",
                "FROM_DATE": "",
                "CAR_STAT_CD": "",
                "AUC_SEQ": "",
                "TODAY": "",
                "IPTCAR_DCD": "001",
                "AUC_PLC_CD": "",
            }

            # Добавляем все поля из примера с пустыми значениями по умолчанию
            data.update(
                {
                    "MNUFTR_CD": "",
                    "MODEL_GRP_CD": "",
                    "MODEL_CD": "",
                    "FORM_YR_ST": "",
                    "FORM_YR_ED": "",
                    "AUC_START_PRC_ST": "",
                    "AUC_START_PRC_ED": "",
                    "MILG_ST": "",
                    "MILG_ED": "",
                    "CNO": "",
                    "FUEL_CD": "",
                    "GBOX_DCD": "",
                    "COLOR_CD": "",
                }
            )

            # Добавляем фильтры если указаны
            if filters.manufacturer_code:
                api_manufacturer_code = convert_ui_to_api_code(
                    filters.manufacturer_code
                )
                logger.info(
                    f"🔄 Преобразование кода в поиске: {filters.manufacturer_code} -> {api_manufacturer_code}"
                )
                data["MNUFTR_CD"] = api_manufacturer_code
            if filters.model_group_code:
                logger.info(f"  - Установлен MODEL_GRP_CD: {filters.model_group_code}")
                data["MODEL_GRP_CD"] = filters.model_group_code
            if filters.model_code:
                logger.info(f"  - Установлен MODEL_CD: {filters.model_code}")
                data["MODEL_CD"] = filters.model_code
            if filters.year_from:
                data["FORM_YR_ST"] = filters.year_from
            if filters.year_to:
                data["FORM_YR_ED"] = filters.year_to
            if filters.price_from:
                data["AUC_START_PRC_ST"] = filters.price_from
            if filters.price_to:
                data["AUC_START_PRC_ED"] = filters.price_to
            if filters.mileage_from:
                data["MILG_ST"] = filters.mileage_from
            if filters.mileage_to:
                data["MILG_ED"] = filters.mileage_to
            if filters.fuel_type:
                data["FUEL_CD"] = filters.fuel_type
            if filters.transmission:
                data["GBOX_DCD"] = filters.transmission
            if filters.color_code:
                data["COLOR_CD"] = filters.color_code
            if filters.auction_location:
                data["AUC_PLC_CD"] = filters.auction_location
            if filters.car_number:
                data["CNO"] = filters.car_number

            # Определяем какие лейны нужно обработать
            requested_lane_type = filters.lane_type
            lanes_to_process = []
            
            if requested_lane_type and requested_lane_type in ["A", "B"]:
                # Если указан конкретный лейн, обрабатываем только его
                lanes_to_process = [requested_lane_type]
                logger.info(
                    f"📡 Поиск только в лейне {requested_lane_type}"
                )
            else:
                # Если лейн не указан, обрабатываем оба
                lanes_to_process = ["A", "B"]
                logger.info(
                    f"📡 Поиск в обоих лейнах (A и B)"
                )

            # Заголовки для AJAX запроса
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/kcar/auction/weekly_auction/colAuction.do?PAGE_TYPE=wCfm&LANE_TYPE=A",
                "X-Requested-With": "XMLHttpRequest",
            }

            # URL для расширенного поиска
            url = f"{self.base_url}/kcar/auction/getAuctionCarList_ajax.do"

            all_cars = []
            total_count = 0
            
            # Обрабатываем каждый лейн отдельно
            for lane_type in lanes_to_process:
                lane_data = data.copy()
                lane_data["LANE_TYPE"] = lane_type
                
                logger.info(f"📊 Поиск в лейне {lane_type}:")
                logger.info(f"  - MNUFTR_CD: {lane_data.get('MNUFTR_CD', '')}")
                logger.info(f"  - MODEL_GRP_CD: {lane_data.get('MODEL_GRP_CD', '')}")
                logger.info(f"  - MODEL_CD: {lane_data.get('MODEL_CD', '')}")
                logger.info(f"  - AUC_TYPE: {lane_data.get('AUC_TYPE', '')}")
                logger.info(f"  - LANE_TYPE: {lane_data.get('LANE_TYPE', '')}")
                logger.debug(f"🔍 Все параметры поиска для лейна {lane_type}: {lane_data}")
                
                response = self.session.post(url, data=lane_data, headers=headers)
                
                if response.status_code == 200:
                    try:
                        json_data = response.json()
                        logger.debug(f"📥 Получен JSON ответ поиска для лейна {lane_type}")
                        
                        # Проверяем что вернул API
                        if "CAR_LIST" in json_data:
                            car_count = len(json_data["CAR_LIST"])
                            logger.info(f"📥 API вернул {car_count} автомобилей из лейна {lane_type}")
                            
                            # Парсим ответ
                            result = self.parser.parse_search_json(json_data)
                            
                            if result.success and result.cars:
                                # Добавляем lane_type к каждому автомобилю
                                for car in result.cars:
                                    car_dict = car.dict()
                                    car_dict['lane_type'] = lane_type
                                    car_with_lane = KCarCar(**car_dict)
                                    all_cars.append(car_with_lane)
                                
                                lane_count = len(result.cars)
                                total_count += lane_count
                                logger.success(f"✅ Получено {lane_count} автомобилей из лейна {lane_type}")
                            else:
                                logger.warning(f"⚠️ Пустой результат для лейна {lane_type}")
                        else:
                            logger.warning(f"⚠️ CAR_LIST не найден в ответе API для лейна {lane_type}")
                    
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ Ошибка парсинга JSON ответа поиска для лейна {lane_type}: {e}")
                else:
                    logger.error(f"❌ HTTP ошибка {response.status_code} для лейна {lane_type}")
            
            logger.info(f"📊 Итого получено {total_count} автомобилей из лейнов {lanes_to_process}")

            # Создаем общий результат
            if all_cars or total_count > 0:
                # Используем значения из фильтров
                page_number = filters.page
                page_size = filters.page_size
                
                # Рассчитываем количество страниц
                if total_count > 0:
                    total_pages = (total_count + page_size - 1) // page_size
                else:
                    total_pages = 1

                has_next_page = len(all_cars) >= page_size  # Если получили полную страницу, возможно есть еще
                has_prev_page = page_number > 1

                final_result = KCarSearchResponse(
                    cars=all_cars,
                    total_count=total_count,
                    current_page=page_number,
                    page_size=page_size,
                    total_pages=total_pages,
                    has_next_page=has_next_page,
                    has_prev_page=has_prev_page,
                    success=True,
                    message=f"Найдено {total_count} автомобилей",
                )

                logger.success(
                    f"✅ Расширенный поиск завершен - найдено {total_count} автомобилей"
                )
                return final_result
            else:
                # Ошибка или пустой результат
                return KCarSearchResponse(
                    cars=[],
                    total_count=0,
                    current_page=filters.page,
                    page_size=filters.page_size,
                    total_pages=1,
                    has_next_page=False,
                    has_prev_page=filters.page > 1,
                    success=False,
                    message="Ошибка получения данных",
                )

        except Exception as e:
            logger.error(f"❌ Ошибка расширенного поиска: {e}")
            return KCarSearchResponse(
                cars=[], success=False, message=f"Ошибка запроса: {str(e)}"
            )
