import requests
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from urllib3.exceptions import InsecureRequestWarning
from urllib3 import disable_warnings
from loguru import logger
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.models.kcar import KCarResponse
from app.parsers.kcar_parser import KCarParser

# Отключаем предупреждения SSL
disable_warnings(InsecureRequestWarning)


class KCarService:
    """Сервис для работы с KCar API"""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = "https://www.kcarauction.com"
        self.parser = KCarParser()
        self.session = requests.Session()
        self.ua = UserAgent()
        self.authenticated = False

        # Учетные данные из конфигурации
        self.username = "autobaza"
        self.password = "for1657721@"

        logger.info("🔧 KCar Service инициализирован")
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
                    logger.debug(f"🔍 Ответ авторизации: {response_data}")

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
                    logger.debug(f"🔍 Ответ согласия: {response_data}")

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
        Получение списка автомобилей с KCar

        Args:
            params: Параметры запроса

        Returns:
            KCarResponse: Ответ с автомобилями
        """
        try:
            logger.info("🚗 Получаю список автомобилей с KCar...")

            # Проверяем авторизацию
            if not self.authenticated:
                logger.warning("⚠️ Нет авторизации, пытаюсь авторизоваться...")
                if not self._authenticate():
                    raise Exception("Не удалось авторизоваться")

            # Подготавливаем параметры запроса
            today = datetime.now().strftime("%Y-%m-%d")

            default_params = {
                "AUC_TYPE": "daily",
                "MNUFTR_CD": "",
                "MODEL_GRP_CD": "",
                "MODEL_CD": "",
                "PAGE_CNT": "50",  # Увеличиваем количество результатов
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
                "SRC_OPT": "daily",
                "CAR_TYPE": "",
                "CARMD_CD": "",
                "PAGE_TYPE": "dCfm",
                "LANE_TYPE": "A",
                "TO_DATE": "",
                "FROM_DATE": "",
                "CAR_STAT_CD": "",
                "AUC_SEQ": "",
                "TODAY": "",
                "IPTCAR_DCD": "",
                "START_DATE": today,
                "END_DATE": today,
                "AUC_PLC_CD": "",
            }

            # Объединяем с переданными параметрами
            if params:
                default_params.update(params)

            # URL для получения списка автомобилей
            cars_url = f"{self.base_url}/kcar/auction/getAuctionCarList_ajax.do"

            # Заголовки для AJAX запроса
            ajax_headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/kcar/auction/daily_auction/colAuction.do?PAGE_TYPE=dCfm",
            }

            logger.info(f"📡 Отправляю запрос к: {cars_url}")
            logger.debug(f"🔍 Параметры: {default_params}")

            # Выполняем запрос
            response = self.session.post(
                cars_url, data=default_params, headers=ajax_headers
            )

            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")

            # Парсим JSON ответ
            try:
                json_data = response.json()
                logger.info("✅ Получен JSON ответ от KCar")

                # Обрабатываем данные через парсер
                result = self.parser.parse_cars_json(json_data)

                if result.success and result.car_list:
                    logger.success(
                        f"✅ Успешно получено {len(result.car_list)} автомобилей KCar"
                    )
                else:
                    logger.warning("⚠️ Получен пустой список автомобилей")

                return result

            except json.JSONDecodeError as e:
                logger.error(f"❌ Ошибка парсинга JSON: {e}")
                logger.debug(f"Response content: {response.text[:500]}...")

                # Сохраняем ответ для отладки
                debug_file = "debug_kcar_response.html"
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write(response.text)
                logger.info(f"💾 Ответ сохранен в {debug_file} для анализа")

                # Возвращаем ошибку парсинга
                return KCarResponse(
                    car_list=[],
                    total_count=0,
                    success=False,
                    message=f"Ошибка парсинга JSON ответа: {str(e)}",
                )

        except Exception as e:
            logger.error(f"❌ Ошибка получения автомобилей KCar: {e}")
            return KCarResponse(
                car_list=[],
                total_count=0,
                success=False,
                message=f"Ошибка получения данных: {str(e)}",
            )

    def get_test_cars(self, count: int = 10) -> KCarResponse:
        """
        Получение тестовых данных автомобилей

        Args:
            count: Количество тестовых автомобилей

        Returns:
            KCarResponse: Тестовые данные
        """
        logger.info(f"🧪 Генерация {count} тестовых автомобилей KCar")
        return self.parser.generate_test_data(count)

    def get_car_count(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Получение количества автомобилей

        Args:
            params: Параметры запроса

        Returns:
            Dict с информацией о количестве
        """
        try:
            logger.info("📊 Получаю количество автомобилей KCar...")

            if not self.authenticated:
                if not self._authenticate():
                    raise Exception("Не удалось авторизоваться")

            # Подготавливаем параметры
            today = datetime.now().strftime("%Y-%m-%d")

            count_params = {
                "MNUFTR_CD": "",
                "MODEL_GRP_CD": "",
                "MODEL_CD": "",
                "AUC_TYPE": "daily",
                "SRC_OPT": "daily",
                "PAGE_TYPE": "dCfm",
                "LANE_TYPE": "A",
                "TO_DATE": "",
                "FROM_DATE": "",
                "AUC_SEQ": "",
                "CAR_STAT_CD": "",
                "TODAY": "",
                "CAR_TYPE": "",
                "CARMD_CD": "",
                "IPTCAR_DCD": "",
                "START_DATE": today,
                "END_DATE": today,
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
                    return response.json()
                except:
                    return {"count": 0, "message": "Не удалось получить количество"}
            else:
                return {"count": 0, "message": f"HTTP {response.status_code}"}

        except Exception as e:
            logger.error(f"❌ Ошибка получения количества: {e}")
            return {"count": 0, "message": str(e)}

    def close(self):
        """Закрытие сессии"""
        if self.session:
            self.session.close()
            logger.info("🔒 KCar сессия закрыта")
