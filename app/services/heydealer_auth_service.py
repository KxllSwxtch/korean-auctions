"""
Сервис автоматической авторизации для HeyDealer
"""

import requests
import aiohttp
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class HeyDealerAuthService:
    """Сервис для управления авторизацией в HeyDealer"""

    def __init__(self):
        self.session_file = "cache/sessions/heydealer_session.json"
        self.login_url = "https://api.heydealer.com/v2/dealers/auth/login/"
        self.test_url = "https://api.heydealer.com/v2/dealers/web/cars/"

        # Данные для авторизации из auctions-auth.txt
        self.username = "arman97"
        self.password = "for1657721@"

        self._session_data = None
        self._session_expires = None

    def _load_session_from_file(self) -> Optional[Dict]:
        """Загружает сессию из файла"""
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, "r") as f:
                    data = json.load(f)

                # Проверяем срок действия
                expires_str = data.get("expires_at")
                if expires_str:
                    expires_at = datetime.fromisoformat(expires_str)
                    if datetime.now() < expires_at:
                        logger.info("Загружена действующая сессия HeyDealer из файла")
                        return data
                    else:
                        logger.info(
                            "Сессия HeyDealer устарела, требуется новая авторизация"
                        )

        except Exception as e:
            logger.error(f"Ошибка загрузки сессии HeyDealer: {e}")

        return None

    def _save_session_to_file(self, session_data: Dict):
        """Сохраняет сессию в файл"""
        try:
            os.makedirs(os.path.dirname(self.session_file), exist_ok=True)

            # Добавляем время истечения (24 часа)
            session_data["expires_at"] = (
                datetime.now() + timedelta(hours=24)
            ).isoformat()

            with open(self.session_file, "w") as f:
                json.dump(session_data, f, indent=2)

            logger.info("Сессия HeyDealer сохранена в файл")

        except Exception as e:
            logger.error(f"Ошибка сохранения сессии HeyDealer: {e}")

    async def _perform_login_async(self) -> Optional[Dict]:
        """Выполняет авторизацию в HeyDealer (асинхронно)"""
        try:
            logger.info("Выполняю авторизацию в HeyDealer...")

            async with aiohttp.ClientSession() as session:
                # Получаем страницу логина для CSRF токена
                async with session.get(
                    "https://dealer.heydealer.com/auth/login/"
                ) as response:
                    # Извлекаем CSRF токен из cookies
                    csrf_token = None
                    for cookie in response.cookies:
                        if cookie.key == "csrftoken":
                            csrf_token = cookie.value
                            break

                if not csrf_token:
                    logger.error("Не удалось получить CSRF токен")
                    return None

                # Данные для авторизации
                login_data = {
                    "username": self.username,
                    "password": self.password,
                    "device_type": "pc",
                }

                # Headers для авторизации
                headers = {
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
                    "App-Os": "pc",
                    "App-Type": "dealer",
                    "App-Version": "1.9.0",
                    "Content-Type": "application/json",
                    "Origin": "https://dealer.heydealer.com",
                    "Referer": "https://dealer.heydealer.com/auth/login/",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
                    "X-CSRFToken": csrf_token,
                }

                # Выполняем авторизацию
                async with session.post(
                    self.login_url, json=login_data, headers=headers, timeout=30
                ) as response:

                    if response.status == 200:
                        # Получаем все cookies из сессии
                        cookies_dict = {}
                        for cookie in session.cookie_jar:
                            cookies_dict[cookie.key] = cookie.value

                        # Обновляем headers с новым sessionid
                        session_id = cookies_dict.get("sessionid")
                        if session_id:
                            headers_dict = {
                                "Accept": "*/*",
                                "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
                                "App-Os": "pc",
                                "App-Type": "dealer",
                                "App-Version": "1.9.0",
                                "Connection": "keep-alive",
                                "Origin": "https://dealer.heydealer.com",
                                "Referer": "https://dealer.heydealer.com/",
                                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
                                "X-CSRFToken": csrf_token,
                            }

                            session_data = {
                                "cookies": cookies_dict,
                                "headers": headers_dict,
                                "login_time": datetime.now().isoformat(),
                                "username": self.username,
                            }

                            logger.info("✅ Успешная авторизация в HeyDealer")
                            return session_data
                        else:
                            logger.error("Не получен sessionid после авторизации")
                    else:
                        response_text = await response.text()
                        logger.error(
                            f"Ошибка авторизации: {response.status} - {response_text}"
                        )

        except Exception as e:
            logger.error(f"Исключение при авторизации в HeyDealer: {e}")

        return None

    def _perform_login(self) -> Optional[Dict]:
        """Выполняет авторизацию в HeyDealer"""
        try:
            logger.info("Выполняю авторизацию в HeyDealer...")

            # Сначала получаем CSRF токен
            session = requests.Session()

            # Получаем страницу логина для CSRF токена
            login_page = session.get("https://dealer.heydealer.com/auth/login/")

            # Извлекаем CSRF токен из cookies
            csrf_token = session.cookies.get("csrftoken")

            if not csrf_token:
                logger.error("Не удалось получить CSRF токен")
                return None

            # Данные для авторизации
            login_data = {
                "username": self.username,
                "password": self.password,
                "device_type": "pc",
            }

            # Headers для авторизации
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
                "App-Os": "pc",
                "App-Type": "dealer",
                "App-Version": "1.9.0",
                "Content-Type": "application/json",
                "Origin": "https://dealer.heydealer.com",
                "Referer": "https://dealer.heydealer.com/auth/login/",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
                "X-CSRFToken": csrf_token,
            }

            # Выполняем авторизацию
            response = session.post(
                self.login_url, json=login_data, headers=headers, timeout=30
            )

            if response.status_code == 200:
                # Получаем все cookies из сессии
                cookies_dict = {}
                for cookie in session.cookies:
                    cookies_dict[cookie.name] = cookie.value

                # Обновляем headers с новым sessionid
                session_id = cookies_dict.get("sessionid")
                if session_id:
                    headers_dict = {
                        "Accept": "*/*",
                        "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
                        "App-Os": "pc",
                        "App-Type": "dealer",
                        "App-Version": "1.9.0",
                        "Connection": "keep-alive",
                        "Origin": "https://dealer.heydealer.com",
                        "Referer": "https://dealer.heydealer.com/",
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
                        "X-CSRFToken": csrf_token,
                    }

                    session_data = {
                        "cookies": cookies_dict,
                        "headers": headers_dict,
                        "login_time": datetime.now().isoformat(),
                        "username": self.username,
                    }

                    logger.info("✅ Успешная авторизация в HeyDealer")
                    return session_data
                else:
                    logger.error("Не получен sessionid после авторизации")
            else:
                logger.error(
                    f"Ошибка авторизации: {response.status_code} - {response.text}"
                )

        except Exception as e:
            logger.error(f"Исключение при авторизации в HeyDealer: {e}")

        return None

    async def _test_session_async(self, session_data: Dict) -> bool:
        """Тестирует действительность сессии (асинхронно)"""
        try:
            headers = session_data.get("headers", {})
            cookies = session_data.get("cookies", {})

            async with aiohttp.ClientSession(cookies=cookies) as session:
                async with session.get(
                    self.test_url,
                    params={"page": 1, "type": "auction", "is_subscribed": "false"},
                    headers=headers,
                    timeout=10,
                ) as response:

                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, list) and len(data) > 0:
                            logger.info("✅ Сессия HeyDealer действительна")
                            return True

                    logger.warning(f"Сессия недействительна: {response.status}")
                    return False

        except Exception as e:
            logger.error(f"Ошибка тестирования сессии: {e}")
            return False

    def _test_session(self, session_data: Dict) -> bool:
        """Тестирует действительность сессии"""
        try:
            headers = session_data.get("headers", {})
            cookies = session_data.get("cookies", {})

            response = requests.get(
                self.test_url,
                params={"page": 1, "type": "auction", "is_subscribed": "false"},
                headers=headers,
                cookies=cookies,
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    logger.info("✅ Сессия HeyDealer действительна")
                    return True

            logger.warning(f"Сессия недействительна: {response.status_code}")
            return False

        except Exception as e:
            logger.error(f"Ошибка тестирования сессии: {e}")
            return False

    async def get_valid_session_async(
        self, force_refresh: bool = False
    ) -> Optional[Dict]:
        """Получает действующую сессию (из кэша или создает новую) - асинхронно"""

        # Если принудительное обновление не требуется, пробуем загрузить из кэша
        if not force_refresh:
            # Сначала проверяем память
            if (
                self._session_data
                and self._session_expires
                and datetime.now() < self._session_expires
            ):
                logger.info("Используется сессия HeyDealer из памяти")
                return self._session_data

            # Затем проверяем файл
            session_data = self._load_session_from_file()
            if session_data and await self._test_session_async(session_data):
                # Кэшируем в память
                self._session_data = session_data
                self._session_expires = datetime.now() + timedelta(
                    hours=23
                )  # Немного меньше 24 часов
                return session_data

        # Создаем новую сессию
        logger.info("Создание новой сессии HeyDealer...")
        session_data = await self._perform_login_async()

        if session_data:
            # Тестируем новую сессию
            if await self._test_session_async(session_data):
                # Сохраняем в файл и память
                self._save_session_to_file(session_data)
                self._session_data = session_data
                self._session_expires = datetime.now() + timedelta(hours=23)
                return session_data
            else:
                logger.error("Новая сессия не прошла тест")

        logger.error("❌ Не удалось получить действующую сессию HeyDealer")
        return None

    def get_valid_session(self, force_refresh: bool = False) -> Optional[Dict]:
        """Получает действующую сессию (из кэша или создает новую)"""

        # Если принудительное обновление не требуется, пробуем загрузить из кэша
        if not force_refresh:
            # Сначала проверяем память
            if (
                self._session_data
                and self._session_expires
                and datetime.now() < self._session_expires
            ):
                logger.info("Используется сессия HeyDealer из памяти")
                return self._session_data

            # Затем проверяем файл
            session_data = self._load_session_from_file()
            if session_data and self._test_session(session_data):
                # Кэшируем в память
                self._session_data = session_data
                self._session_expires = datetime.now() + timedelta(
                    hours=23
                )  # Немного меньше 24 часов
                return session_data

        # Создаем новую сессию
        logger.info("Создание новой сессии HeyDealer...")
        session_data = self._perform_login()

        if session_data:
            # Тестируем новую сессию
            if self._test_session(session_data):
                # Сохраняем в файл и память
                self._save_session_to_file(session_data)
                self._session_data = session_data
                self._session_expires = datetime.now() + timedelta(hours=23)
                return session_data
            else:
                logger.error("Новая сессия не прошла тест")

        logger.error("❌ Не удалось получить действующую сессию HeyDealer")
        return None

    async def get_headers_and_cookies_async(
        self, force_refresh: bool = False
    ) -> tuple[Optional[Dict], Optional[Dict]]:
        """Возвращает headers и cookies для запросов (асинхронно)"""
        session_data = await self.get_valid_session_async(force_refresh)

        if session_data:
            return session_data.get("headers"), session_data.get("cookies")

        return None, None

    def get_headers_and_cookies(
        self, force_refresh: bool = False
    ) -> tuple[Optional[Dict], Optional[Dict]]:
        """Возвращает headers и cookies для запросов"""
        session_data = self.get_valid_session(force_refresh)

        if session_data:
            return session_data.get("headers"), session_data.get("cookies")

        return None, None


# Глобальный экземпляр сервиса
heydealer_auth = HeyDealerAuthService()
