"""
Сервис автоматической авторизации для HeyDealer с обновлением cookies
"""

import requests
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class HeyDealerAuthService:
    """Сервис для управления авторизацией в HeyDealer"""

    def __init__(self):
        self.session_file = "cache/sessions/heydealer_session.json"
        self.login_url = "https://api.heydealer.com/v2/dealers/web/login/"
        self.test_url = "https://api.heydealer.com/v2/dealers/web/cars/"

        # Данные для авторизации из auctions-auth.txt
        self.username = "arman97"
        self.password = "for1657721@"

        # Базовые cookies для начальной авторизации
        self.base_cookies = {
            "_ga": "GA1.2.225253972.1750804665",
            "_gid": "GA1.2.607092972.1750804665",
            "ga_dsi": "2f27c9738d9441acb3019f0388816973",
            "_gat": "1",
            "_ga_D0D36Y0VSC": "GS2.2.s1750804665$o1$g1$t1750805823$j45$l0$h0",
        }

        self._session_data = None
        self._session_expires = None

    def _get_csrf_token(self) -> Optional[str]:
        """Получает CSRF токен для авторизации"""
        try:
            # Делаем запрос на главную страницу чтобы получить CSRF токен
            response = requests.get(
                "https://dealer.heydealer.com/", cookies=self.base_cookies, timeout=10
            )

            if response.status_code == 200:
                # Ищем CSRF токен в cookies
                csrf_token = response.cookies.get("csrftoken")
                if csrf_token:
                    logger.info(f"Получен CSRF токен: {csrf_token[:10]}...")
                    return csrf_token

            logger.warning("Не удалось получить CSRF токен")
            return None

        except Exception as e:
            logger.error(f"Ошибка получения CSRF токена: {e}")
            return None

    def _perform_login(self) -> Optional[Dict]:
        """Выполняет авторизацию и возвращает новые cookies"""
        try:
            # Получаем CSRF токен
            csrf_token = self._get_csrf_token()
            if not csrf_token:
                # Используем fallback токен
                csrf_token = "oF1QX8pojFyAYw9J9yYO3JZgEHkxNEzB"

            # Подготавливаем cookies для авторизации
            login_cookies = self.base_cookies.copy()
            login_cookies["csrftoken"] = csrf_token

            headers = {
                "Accept": "*/*",
                "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
                "App-Os": "pc",
                "App-Type": "dealer",
                "App-Version": "1.9.0",
                "Connection": "keep-alive",
                "Content-Type": "application/json",
                "Origin": "https://dealer.heydealer.com",
                "Referer": "https://dealer.heydealer.com/",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
                "X-CSRFToken": csrf_token,
                "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
            }

            json_data = {
                "username": self.username,
                "password": self.password,
                "device_type": "pc",
            }

            # Выполняем авторизацию
            response = requests.post(
                self.login_url,
                cookies=login_cookies,
                headers=headers,
                json=json_data,
                timeout=15,
            )

            logger.info(f"Ответ авторизации: {response.status_code}")

            if response.status_code == 200:
                # Получаем новые cookies из ответа
                new_cookies = login_cookies.copy()

                # Обновляем cookies из ответа
                for cookie_name, cookie_value in response.cookies.items():
                    new_cookies[cookie_name] = cookie_value
                    logger.info(f"Обновлен cookie: {cookie_name}")

                # Проверяем что получили sessionid
                if "sessionid" in new_cookies:
                    logger.info("✅ Успешная авторизация! Получен sessionid")
                    return {
                        "cookies": new_cookies,
                        "headers": headers,
                        "expires_at": (datetime.now() + timedelta(hours=6)).isoformat(),
                    }
                else:
                    logger.warning("Авторизация прошла, но sessionid не получен")
                    return None
            else:
                logger.error(
                    f"Ошибка авторизации: {response.status_code} - {response.text}"
                )
                return None

        except Exception as e:
            logger.error(f"Ошибка при авторизации: {e}")
            return None

    def _save_session(self, session_data: Dict) -> None:
        """Сохраняет данные сессии в файл"""
        try:
            os.makedirs(os.path.dirname(self.session_file), exist_ok=True)
            with open(self.session_file, "w") as f:
                json.dump(session_data, f, indent=2)
            logger.info("Сессия сохранена")
        except Exception as e:
            logger.error(f"Ошибка сохранения сессии: {e}")

    def _load_session(self) -> Optional[Dict]:
        """Загружает данные сессии из файла"""
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки сессии: {e}")
        return None

    def _is_session_valid(self, session_data: Dict) -> bool:
        """Проверяет валидность сессии"""
        try:
            expires_at = datetime.fromisoformat(session_data.get("expires_at", ""))
            return datetime.now() < expires_at
        except:
            return False

    def _test_session(self, cookies: Dict, headers: Dict) -> bool:
        """Тестирует работоспособность сессии"""
        try:
            response = requests.get(
                self.test_url,
                params={"page": 1, "type": "auction", "is_subscribed": "false"},
                cookies=cookies,
                headers=headers,
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    logger.info("✅ Сессия валидна - получены данные")
                    return True

            logger.warning(f"Сессия невалидна: {response.status_code}")
            return False

        except Exception as e:
            logger.error(f"Ошибка тестирования сессии: {e}")
            return False

    def get_valid_session(self) -> Optional[Tuple[Dict, Dict]]:
        """Возвращает валидную сессию (cookies, headers)"""
        try:
            # Пробуем загрузить существующую сессию
            session_data = self._load_session()

            if session_data and self._is_session_valid(session_data):
                cookies = session_data.get("cookies", {})
                headers = session_data.get("headers", {})

                # Тестируем сессию
                if self._test_session(cookies, headers):
                    logger.info("Используем существующую валидную сессию")
                    return cookies, headers
                else:
                    logger.info("Существующая сессия не работает, обновляем...")

            # Выполняем новую авторизацию
            logger.info("Выполняем новую авторизацию...")
            session_data = self._perform_login()

            if session_data:
                # Сохраняем новую сессию
                self._save_session(session_data)

                cookies = session_data.get("cookies", {})
                headers = session_data.get("headers", {})

                logger.info("✅ Получена новая валидная сессия")
                return cookies, headers
            else:
                logger.error("Не удалось получить валидную сессию")
                return None, None

        except Exception as e:
            logger.error(f"Ошибка получения валидной сессии: {e}")
            return None, None


# Глобальный экземпляр сервиса
heydealer_auth = HeyDealerAuthService()
