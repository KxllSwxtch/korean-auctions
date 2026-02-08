"""
Улучшенный сервис Lotte с продвинутыми возможностями
"""

import re
from datetime import datetime
from typing import Dict, Any, Optional, List
from urllib.parse import urljoin
import json

from app.core.base_service import BaseAuctionService, AuthenticationError, ParsingError
from app.core.logging import logger
from app.models.lotte import (
    LotteCar,
    LotteAuctionDate,
    FuelType,
    TransmissionType,
    GradeType,
)
from app.parsers.lotte_parser import LotteParser


class EnhancedLotteService(BaseAuctionService):
    """
    Улучшенный сервис для работы с аукционом Lotte

    Возможности:
    - Продвинутая защита от блокировок
    - Асинхронная работа (опционально)
    - Интеллектуальное кэширование
    - Автоматическое обновление сессий
    - Подробная статистика и мониторинг
    """

    def __init__(self, use_async: bool = False, proxy_list: Optional[List] = None):
        # Учетные данные из конфигурации
        credentials = {"username": "119102", "password": "for1234@"}

        super().__init__(
            auction_name="lotte",
            base_url="https://www.lotteautoauction.net",
            credentials=credentials,
            use_async=use_async,
            proxy_list=proxy_list,
        )

        # Инициализируем парсер
        self.parser = LotteParser()

        # Специфичные для Lotte настройки
        self.login_attempts_limit = 3
        self.current_login_attempts = 0

        logger.info("Инициализирован улучшенный сервис Lotte")

    def get_urls(self) -> Dict[str, str]:
        """Получить словарь URL для Lotte"""
        return {
            "home": "/hp/auct/myp/entry/selectMypEntryList.do",
            "login": "/hp/auct/cmm/viewLoginUsr.do?loginMode=redirect",
            "login_check": "/hp/auct/cmm/selectAuctMemLoginCheckAjax.do",
            "login_action": "/hp/auct/cmm/actionLogin.do",
            "cars_list": "/hp/auct/myp/entry/selectMypEntryList.do",
            "car_details": "/hp/auct/myp/entry/selectMypEntryCarDetPop.do",
        }

    async def _perform_authentication(self) -> bool:
        """Выполнить двухэтапную аутентификацию в Lotte"""
        if self.current_login_attempts >= self.login_attempts_limit:
            logger.error("Превышен лимит попыток входа в Lotte")
            return False

        self.current_login_attempts += 1

        try:
            urls = self.get_urls()

            # Шаг 1: Получаем страницу логина для инициализации сессии
            login_page_url = urljoin(self.base_url, urls["login"])

            logger.info("Получаем страницу логина Lotte...")

            if self.use_async:
                response, content = await self.get_page(login_page_url)
                status_code = response.status
            else:
                response = await self.get_page(login_page_url)
                content = response.text
                status_code = response.status_code

            if status_code != 200:
                logger.error(f"Не удалось получить страницу логина: {status_code}")
                return False

            logger.info("Страница логина получена, cookies установлены")

            # Шаг 2: AJAX проверка логина
            login_check_url = urljoin(self.base_url, urls["login_check"])

            check_data = {
                "userId": self.credentials["username"],
                "userPwd": self.credentials["password"],
                "resultCd": "",
            }

            check_headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": login_page_url,
                "Accept": "application/json, text/javascript, */*; q=0.01",
            }

            logger.info("Выполняем AJAX проверку логина...")

            if self.use_async:
                response, content = await self.post_data(
                    login_check_url, data=check_data, headers=check_headers
                )
                status_code = response.status
            else:
                response = await self.post_data(
                    login_check_url, data=check_data, headers=check_headers
                )
                content = response.text
                status_code = response.status_code

            if status_code != 200:
                logger.error(f"Ошибка при проверке логина: HTTP {status_code}")
                return False

            # Анализируем ответ
            try:
                result = json.loads(content)
                logger.info(f"Ответ проверки логина: {result}")

                result_code = result.get("resultCd")

                if result_code is None or result_code == "":
                    logger.info("AJAX проверка логина прошла успешно")

                    # Шаг 3: Финальный логин
                    login_action_url = urljoin(self.base_url, urls["login_action"])

                    final_data = {
                        "userId": self.credentials["username"],
                        "userPwd": self.credentials["password"],
                    }

                    final_headers = {
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Referer": login_page_url,
                    }

                    logger.info("Выполняем финальный логин...")

                    if self.use_async:
                        response, content = await self.post_data(
                            login_action_url, data=final_data, headers=final_headers
                        )
                        final_status = response.status
                    else:
                        response = await self.post_data(
                            login_action_url, data=final_data, headers=final_headers
                        )
                        final_status = response.status_code

                    if final_status in [200, 302, 303]:
                        self.current_login_attempts = 0  # Сбрасываем счетчик при успехе
                        logger.info("✅ Аутентификация Lotte успешно завершена")
                        return True
                    else:
                        logger.error(f"Ошибка финального логина: HTTP {final_status}")
                        return False
                else:
                    # Обрабатываем коды ошибок
                    error_messages = {
                        "errUserAuth": "Неверные логин или пароль",
                        "errOverPassCnt": "Превышено количество попыток входа",
                        "feeInactive": "Проблемы с оплатой аккаунта",
                    }

                    error_msg = error_messages.get(
                        result_code, f"Неизвестная ошибка: {result_code}"
                    )
                    logger.error(f"Ошибка аутентификации Lotte: {error_msg}")
                    return False

            except json.JSONDecodeError as e:
                logger.error(f"Не удалось разобрать JSON ответ: {e}")
                logger.error(f"Содержимое ответа: {content[:500]}")
                return False

        except Exception as e:
            logger.error(f"Общая ошибка аутентификации Lotte: {e}")
            return False

    async def _parse_auction_date(self, html_content: str) -> Optional[Dict[str, Any]]:
        """Парсинг даты аукциона Lotte"""
        try:
            auction_date = self.parser.parse_auction_date(html_content)

            if auction_date:
                return {
                    "auction_date": auction_date.auction_date,
                    "year": auction_date.year,
                    "month": auction_date.month,
                    "day": auction_date.day,
                    "is_today": auction_date.is_today,
                    "is_future": auction_date.is_future,
                    "raw_text": auction_date.raw_text,
                    "formatted_date": auction_date.auction_date,
                    "status": (
                        "today"
                        if auction_date.is_today
                        else ("future" if auction_date.is_future else "past")
                    ),
                }

            return None

        except Exception as e:
            logger.error(f"Ошибка парсинга даты аукциона Lotte: {e}")
            return None

    async def _parse_cars_list(self, html_content: str) -> List[Dict[str, Any]]:
        """Парсинг списка автомобилей Lotte"""
        try:
            cars_data = self.parser.parse_cars_list(html_content)

            # Добавляем дополнительную информацию
            for car in cars_data:
                car["auction_name"] = "lotte"
                car["parsed_at"] = datetime.now().isoformat()

                # Нормализуем данные
                if "starting_price" in car and isinstance(car["starting_price"], str):
                    car["starting_price"] = self.parser._parse_price(
                        car["starting_price"]
                    )

                if "mileage" in car and isinstance(car["mileage"], str):
                    car["mileage"] = self.parser._parse_mileage(car["mileage"])

            logger.info(f"Спарсено {len(cars_data)} автомобилей Lotte")
            return cars_data

        except Exception as e:
            logger.error(f"Ошибка парсинга списка автомобилей Lotte: {e}")
            return []

    async def _parse_car_details(
        self, html_content: str, car_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Парсинг деталей автомобиля Lotte"""
        try:
            detailed_car = self.parser.parse_car_details(html_content, car_data)

            if detailed_car:
                # Преобразуем в словарь для кэширования
                car_dict = detailed_car.model_dump()
                car_dict["auction_name"] = "lotte"
                car_dict["detailed_parsed_at"] = datetime.now().isoformat()
                return car_dict

            return None

        except Exception as e:
            logger.error(f"Ошибка парсинга деталей автомобиля Lotte: {e}")
            return None

    # === Специфичные для Lotte методы ===

    async def get_cars_with_date_check(
        self, limit: int = 20, offset: int = 0
    ) -> Dict[str, Any]:
        """
        Получить автомобили с проверкой даты аукциона

        Если аукцион сегодня - вернет список автомобилей
        Если не сегодня - вернет информацию о ближайшей дате
        """
        try:
            # Сначала получаем дату аукциона
            auction_date_info = await self.get_auction_date()

            if not auction_date_info:
                return {
                    "success": False,
                    "message": "Не удалось получить дату аукциона",
                    "auction_date_info": None,
                    "cars": [],
                    "error": "DATE_FETCH_ERROR",
                }

            # Проверяем, сегодня ли аукцион
            if not auction_date_info.get("is_today", False):
                return {
                    "success": False,
                    "message": f"Аукцион не сегодня. Следующий аукцион: {auction_date_info.get('auction_date')}",
                    "auction_date_info": auction_date_info,
                    "cars": [],
                    "status": auction_date_info.get("status", "unknown"),
                }

            # Аукцион сегодня, получаем список автомобилей
            cars_data = await self.get_cars(limit=limit, offset=offset)

            return {
                "success": True,
                "message": f"Получено {len(cars_data)} автомобилей с аукциона Lotte",
                "auction_date_info": auction_date_info,
                "cars": cars_data,
                "total_count": len(cars_data),
                "limit": limit,
                "offset": offset,
            }

        except Exception as e:
            logger.error(f"Ошибка получения автомобилей с проверкой даты Lotte: {e}")
            return {
                "success": False,
                "message": f"Внутренняя ошибка: {str(e)}",
                "auction_date_info": None,
                "cars": [],
                "error": "INTERNAL_ERROR",
            }

    async def get_cars_with_details(
        self, limit: int = 10, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Получить автомобили с детальной информацией"""
        try:
            # Получаем базовый список
            cars_basic = await self.get_cars(limit=limit, offset=offset)

            detailed_cars = []

            # Параллельно получаем детали для каждого автомобиля
            if self.use_async:
                # Асинхронный способ - параллельные запросы
                import asyncio

                async def get_car_detail(car_data):
                    try:
                        car_id = car_data.get("id") or car_data.get("auction_number")
                        if car_id:
                            details = await self.get_car_details(str(car_id), car_data)
                            return details or car_data
                        return car_data
                    except Exception as e:
                        logger.error(
                            f"Ошибка получения деталей для {car_data.get('id', 'unknown')}: {e}"
                        )
                        return car_data

                tasks = [get_car_detail(car) for car in cars_basic]
                detailed_cars = await asyncio.gather(*tasks, return_exceptions=True)

                # Фильтруем исключения
                detailed_cars = [
                    car for car in detailed_cars if not isinstance(car, Exception)
                ]
            else:
                # Parallel detail fetching with semaphore to limit concurrency
                import asyncio

                semaphore = asyncio.Semaphore(5)

                async def _limited_detail(car_data):
                    async with semaphore:
                        try:
                            car_id = car_data.get("id") or car_data.get("auction_number")
                            if car_id:
                                details = await self.get_car_details(str(car_id), car_data)
                                return details or car_data
                            return car_data
                        except Exception as e:
                            logger.error(
                                f"Ошибка получения деталей для {car_data.get('id', 'unknown')}: {e}"
                            )
                            return car_data

                tasks = [_limited_detail(car) for car in cars_basic]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                detailed_cars = [
                    car for car in results if not isinstance(car, Exception)
                ]

            logger.info(f"Получено {len(detailed_cars)} автомобилей с деталями")
            return detailed_cars

        except Exception as e:
            logger.error(f"Ошибка получения автомобилей с деталями: {e}")
            raise ParsingError(f"Не удалось получить детальную информацию: {e}")

    async def get_total_cars_count(self) -> int:
        """Получить общее количество автомобилей на аукционе"""
        try:
            # Сначала получаем первую страницу
            if self.use_async:
                response, content = await self.get_page(
                    urljoin(self.base_url, self.get_urls()["cars_list"])
                )
            else:
                response = await self.get_page(
                    urljoin(self.base_url, self.get_urls()["cars_list"])
                )
                content = response.text

            # Используем парсер для подсчета
            total_count = self.parser.parse_total_count(content)

            logger.info(f"Общее количество автомобилей Lotte: {total_count}")
            return total_count

        except Exception as e:
            logger.error(f"Ошибка получения общего количества автомобилей: {e}")
            return 0

    def reset_login_attempts(self):
        """Сбросить счетчик попыток входа"""
        self.current_login_attempts = 0
        logger.info("Счетчик попыток входа Lotte сброшен")

    def get_enhanced_stats(self) -> Dict[str, Any]:
        """Получить расширенную статистику сервиса"""
        base_stats = self.get_stats()

        # Добавляем специфичную для Lotte информацию
        base_stats.update(
            {
                "login_attempts_current": self.current_login_attempts,
                "login_attempts_limit": self.login_attempts_limit,
                "parser_info": {
                    "class": self.parser.__class__.__name__,
                    "methods": [
                        method
                        for method in dir(self.parser)
                        if not method.startswith("_")
                    ],
                },
            }
        )

        return base_stats
