"""
Сервис автоматической авторизации для HeyDealer с обновлением cookies и user token
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
        }

        # Базовые headers
        self.base_headers = {
            "Accept": "*/*",
            "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "App-Os": "pc",
            "App-Type": "dealer",
            "App-Version": "1.9.0",
            "Connection": "keep-alive",
            "Origin": "https://dealer.heydealer.com",
            "Referer": "https://dealer.heydealer.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

        # Создаем директорию для кэша если не существует
        os.makedirs(os.path.dirname(self.session_file), exist_ok=True)

    def get_csrf_token(self) -> Optional[str]:
        """Получает CSRF токен для авторизации"""
        try:
            # Сначала пробуем получить через главную страницу
            response = requests.get(
                "https://dealer.heydealer.com/",
                cookies=self.base_cookies,
                headers=self.base_headers,
                timeout=30,
            )

            if response.status_code == 200:
                # Извлекаем CSRF токен из cookies
                csrf_token = response.cookies.get("csrftoken")
                if csrf_token:
                    logger.info(f"CSRF токен получен: {csrf_token[:8]}...")
                    return csrf_token

            # Если не получилось, пробуем через API endpoint
            logger.warning(
                "Не удалось получить CSRF через главную страницу, пробую через API..."
            )

            # Создаем новые cookies с временным CSRF
            temp_cookies = self.base_cookies.copy()
            temp_headers = self.base_headers.copy()

            # Делаем запрос к API для получения CSRF
            api_response = requests.get(
                "https://api.heydealer.com/v2/dealers/web/",
                cookies=temp_cookies,
                headers=temp_headers,
                timeout=30,
            )

            if api_response.status_code in [200, 403]:  # 403 тоже может содержать CSRF
                csrf_token = api_response.cookies.get("csrftoken")
                if csrf_token:
                    logger.info(f"CSRF токен получен через API: {csrf_token[:8]}...")
                    return csrf_token

            # Fallback - используем известный рабочий токен
            logger.warning("Используем fallback CSRF токен")
            return "86vF233dOdoOCeznt8rwfXkVlwacieWi"

        except Exception as e:
            logger.error(f"Исключение при получении CSRF токена: {e}")
            # Fallback токен
            logger.warning("Используем fallback CSRF токен из-за исключения")
            return "86vF233dOdoOCeznt8rwfXkVlwacieWi"

    def login(self) -> Optional[Dict]:
        """Выполняет логин и возвращает данные сессии"""
        try:
            logger.info("Начинаю процесс авторизации HeyDealer...")

            # Получаем CSRF токен
            csrf_token = self.get_csrf_token()
            if not csrf_token:
                logger.error("Не удалось получить CSRF токен")
                return None

            # Подготавливаем cookies и headers для логина
            login_cookies = self.base_cookies.copy()
            login_cookies["csrftoken"] = csrf_token

            login_headers = self.base_headers.copy()
            login_headers["Content-Type"] = "application/json"
            login_headers["X-CSRFToken"] = csrf_token

            # Данные для логина
            login_data = {
                "username": self.username,
                "password": self.password,
                "device_type": "pc",
            }

            # Выполняем логин
            logger.info("Отправляю запрос авторизации...")
            response = requests.post(
                self.login_url,
                cookies=login_cookies,
                headers=login_headers,
                json=login_data,
                timeout=30,
            )

            if response.status_code == 200:
                login_response = response.json()
                user_hash_id = login_response.get("user", {}).get("hash_id")

                if not user_hash_id:
                    logger.error("User hash_id не найден в ответе логина")
                    return None

                logger.info(f"✅ Авторизация успешна! User hash_id: {user_hash_id}")

                # Получаем все cookies из ответа
                session_cookies = login_cookies.copy()
                for cookie in response.cookies:
                    session_cookies[cookie.name] = cookie.value

                # Подготавливаем данные сессии
                session_data = {
                    "user_hash_id": user_hash_id,
                    "cookies": session_cookies,
                    "headers": login_headers,
                    "created_at": datetime.now().isoformat(),
                    "expires_at": (datetime.now() + timedelta(hours=12)).isoformat(),
                }

                # Сохраняем сессию
                self.save_session(session_data)

                return session_data

            else:
                logger.error(
                    f"Ошибка авторизации: {response.status_code} - {response.text}"
                )
                return None

        except Exception as e:
            logger.error(f"Исключение при авторизации: {e}")
            return None

    def validate_session(self, session_data: Dict) -> bool:
        """Проверяет валидность сессии через user endpoint"""
        try:
            user_hash_id = session_data.get("user_hash_id")
            cookies = session_data.get("cookies", {})
            headers = session_data.get("headers", {})

            if not user_hash_id:
                logger.error("User hash_id отсутствует в данных сессии")
                return False

            # Проверяем сессию через user endpoint
            user_url = f"https://api.heydealer.com/v2/dealers/web/users/{user_hash_id}/"

            response = requests.get(
                user_url, cookies=cookies, headers=headers, timeout=30
            )

            if response.status_code == 200:
                logger.info("✅ Сессия валидна")
                return True
            else:
                logger.warning(f"Сессия невалидна: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Ошибка валидации сессии: {e}")
            return False

    def load_session(self) -> Optional[Dict]:
        """Загружает сохраненную сессию"""
        try:
            if not os.path.exists(self.session_file):
                logger.info("Файл сессии не найден")
                return None

            with open(self.session_file, "r", encoding="utf-8") as f:
                session_data = json.load(f)

            # Проверяем срок действия
            expires_at = datetime.fromisoformat(session_data.get("expires_at", ""))
            if datetime.now() > expires_at:
                logger.warning("Сохраненная сессия истекла")
                return None

            logger.info("Сохраненная сессия загружена")
            return session_data

        except Exception as e:
            logger.error(f"Ошибка загрузки сессии: {e}")
            return None

    def save_session(self, session_data: Dict):
        """Сохраняет данные сессии"""
        try:
            with open(self.session_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            logger.info("Сессия сохранена")
        except Exception as e:
            logger.error(f"Ошибка сохранения сессии: {e}")

    def get_valid_session(self) -> Tuple[Optional[Dict], Optional[Dict]]:
        """
        Возвращает валидную сессию (cookies, headers)

        Returns:
            Tuple[cookies, headers] или (None, None) при ошибке
        """
        try:
            # Пытаемся загрузить сохраненную сессию
            session_data = self.load_session()

            # Если сессия есть, проверяем её валидность
            if session_data and self.validate_session(session_data):
                logger.info("Используем сохраненную валидную сессию")
                return session_data.get("cookies"), session_data.get("headers")

            # Если сессии нет или она невалидна, создаем новую
            logger.info("Создаю новую сессию...")
            session_data = self.login()

            if session_data:
                logger.info("✅ Новая сессия создана успешно")
                return session_data.get("cookies"), session_data.get("headers")
            else:
                logger.error("❌ Не удалось создать новую сессию")
                return None, None

        except Exception as e:
            logger.error(f"Ошибка получения валидной сессии: {e}")
            return None, None


# Глобальный экземпляр сервиса
heydealer_auth = HeyDealerAuthService()
