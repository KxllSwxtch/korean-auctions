"""
Сервис автоматической авторизации для HeyDealer с обновлением cookies и user token
"""

import requests
import json
import os
import secrets
import string
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from loguru import logger

from app.core.proxy_config import get_heydealer_proxies


class HeyDealerAuthService:
    """Сервис для управления авторизацией в HeyDealer"""

    def __init__(self):
        self.session_file = "cache/sessions/heydealer_session.json"
        self.login_url = "https://api.heydealer.com/v2/dealers/web/login/"
        self.test_url = "https://api.heydealer.com/v2/dealers/web/cars/"

        # Данные для авторизации из auctions-auth.txt
        self.username = "arman97"
        self.password = "for1657721@"

        # Базовые headers для запросов к HeyDealer API
        self.base_headers = {
            "Accept": "*/*",
            "Accept-Language": "en,ru;q=0.9,ko;q=0.8",
            "App-Os": "pc",
            "App-Type": "dealer",
            "App-Version": "1.9.0",
            "Connection": "keep-alive",
            "Origin": "https://dealer.heydealer.com",
            "Referer": "https://dealer.heydealer.com/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
        }

        # Создаем директорию для кэша если не существует
        os.makedirs(os.path.dirname(self.session_file), exist_ok=True)

        # In-process single-flight + короткий кэш валидации, чтобы под нагрузкой
        # параллельные запросы не устраивали login-storm и не делали живой
        # validate_session round-trip на КАЖДЫЙ запрос (это и приводит к тому,
        # что часть пользователей видит пустой список).
        self._login_lock = threading.Lock()
        self._cached_session: Optional[Dict] = None
        self._validated_until: Optional[datetime] = None
        self._validation_ttl = timedelta(seconds=60)

    def _create_session(self) -> requests.Session:
        """Создает requests.Session с базовыми headers для автоматического управления cookies."""
        session = requests.Session()
        session.headers.update(self.base_headers)
        # Весь HeyDealer-трафик идёт через выделенный корейский проксирующий
        # egress (анти-throttle на единственном аккаунте/IP). Sticky-сессия в
        # username гарантирует один exit IP на всю сессию, иначе cookie логина,
        # привязанный к IP, будет отклонён при ротации.
        proxies = get_heydealer_proxies()
        if proxies:
            session.proxies.update(proxies)
        return session

    def get_csrf_token(self) -> Optional[str]:
        """Получает CSRF токен для авторизации через requests.Session для корректной цепочки cookies."""
        session = self._create_session()

        # Попытка 1: Получить CSRF через главную страницу dealer.heydealer.com
        try:
            logger.info("Попытка получить CSRF через главную страницу...")
            response = session.get("https://dealer.heydealer.com/", timeout=30)
            logger.info(f"Главная страница: status={response.status_code}, cookies={list(session.cookies.keys())}")

            csrf_token = session.cookies.get("csrftoken")
            if csrf_token:
                logger.info(f"CSRF токен получен через главную страницу: {csrf_token[:8]}...")
                return csrf_token
        except Exception as e:
            logger.warning(f"Ошибка при запросе главной страницы: {e}")

        # Попытка 2: Получить CSRF через API endpoint (Django часто ставит csrftoken на любом GET)
        try:
            logger.warning("Не удалось получить CSRF через главную страницу, пробую через API...")
            api_response = session.get(
                "https://api.heydealer.com/v2/dealers/web/",
                timeout=30,
            )
            logger.info(f"API endpoint: status={api_response.status_code}, cookies={list(session.cookies.keys())}")

            csrf_token = session.cookies.get("csrftoken")
            if not csrf_token:
                csrf_token = api_response.cookies.get("csrftoken")
            if csrf_token:
                logger.info(f"CSRF токен получен через API: {csrf_token[:8]}...")
                return csrf_token
        except Exception as e:
            logger.warning(f"Ошибка при запросе API endpoint: {e}")

        # Попытка 3: Получить через login page напрямую
        try:
            logger.warning("Пробую получить CSRF через login endpoint...")
            login_response = session.get(self.login_url, timeout=30)
            logger.info(f"Login endpoint: status={login_response.status_code}, cookies={list(session.cookies.keys())}")

            csrf_token = session.cookies.get("csrftoken")
            if not csrf_token:
                csrf_token = login_response.cookies.get("csrftoken")
            if csrf_token:
                logger.info(f"CSRF токен получен через login endpoint: {csrf_token[:8]}...")
                return csrf_token
        except Exception as e:
            logger.warning(f"Ошибка при запросе login endpoint: {e}")

        logger.error("Все методы получения CSRF провалились — авторизация невозможна")
        return None

    def login(self) -> Optional[Dict]:
        """Выполняет логин через requests.Session и возвращает данные сессии."""
        try:
            logger.info("Начинаю процесс авторизации HeyDealer...")

            # Создаем сессию для полного auth flow (CSRF → login)
            session = self._create_session()

            # Шаг 1: Получаем CSRF через сессию
            csrf_token = None

            # Попытка 1: Пробуем GET к API endpoints чтобы получить CSRF cookie от Django
            csrf_urls = [
                "https://dealer.heydealer.com/",
                "https://api.heydealer.com/v2/dealers/web/cars/",
                "https://api.heydealer.com/v2/dealers/web/",
                self.login_url,
            ]
            for url in csrf_urls:
                if csrf_token:
                    break
                try:
                    resp = session.get(url, timeout=15)
                    csrf_token = session.cookies.get("csrftoken")
                    logger.info(f"[CSRF] GET {url}: status={resp.status_code}, cookies={list(session.cookies.keys())}, csrf={'OK' if csrf_token else 'НЕТ'}")
                except Exception as e:
                    logger.warning(f"[CSRF] GET {url} failed: {e}")

            # Попытка 2: Если CSRF не получен, генерируем свой токен (Django double-submit pattern)
            if not csrf_token:
                csrf_token = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
                logger.warning(f"[CSRF] Сервер не вернул csrftoken, используем сгенерированный: {csrf_token[:8]}...")

            logger.info(f"CSRF токен для логина: {csrf_token[:8]}...")

            # Шаг 2: Устанавливаем CSRF в сессию и выполняем логин
            session.cookies.set("csrftoken", csrf_token)
            session.headers.update({
                "Content-Type": "application/json",
                "X-CSRFToken": csrf_token,
            })

            login_data = {
                "username": self.username,
                "password": self.password,
                "device_type": "pc",
            }

            logger.info("Отправляю запрос авторизации...")
            response = session.post(self.login_url, json=login_data, timeout=30)

            if response.status_code == 200:
                login_response = response.json()
                user_hash_id = login_response.get("user", {}).get("hash_id")

                if not user_hash_id:
                    logger.error("User hash_id не найден в ответе логина")
                    return None

                logger.info(f"✅ Авторизация успешна! User hash_id: {user_hash_id}")

                # Собираем все cookies из сессии (последний побеждает при дубликатах)
                session_cookies = {}
                for cookie in session.cookies:
                    session_cookies[cookie.name] = cookie.value

                # Собираем headers для дальнейших запросов
                session_headers = dict(self.base_headers)
                session_headers["Content-Type"] = "application/json"
                session_headers["X-CSRFToken"] = csrf_token

                session_data = {
                    "user_hash_id": user_hash_id,
                    "cookies": session_cookies,
                    "headers": session_headers,
                    "created_at": datetime.now().isoformat(),
                    "expires_at": (datetime.now() + timedelta(hours=12)).isoformat(),
                }

                self.save_session(session_data)
                return session_data

            else:
                logger.error(
                    f"Ошибка авторизации: {response.status_code} - {response.text[:500]}"
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
                user_url,
                cookies=cookies,
                headers=headers,
                timeout=30,
                proxies=get_heydealer_proxies(),
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
        """Атомарно сохраняет данные сессии.

        Пишем во временный файл и делаем os.replace: параллельные воркеры,
        читающие session_file, никогда не увидят усечённый JSON (частичная
        запись раньше приводила к json.load -> None -> лишний повторный логин).
        """
        try:
            os.makedirs(os.path.dirname(self.session_file), exist_ok=True)
            tmp_path = f"{self.session_file}.{os.getpid()}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.session_file)
            # Обновляем in-memory кэш и помечаем сессию как только что валидную.
            self._cached_session = session_data
            self._validated_until = datetime.now() + self._validation_ttl
            logger.info("Сессия сохранена (атомарно)")
        except Exception as e:
            logger.error(f"Ошибка сохранения сессии: {e}")

    def get_valid_session(self) -> Tuple[Optional[Dict], Optional[Dict]]:
        """
        Возвращает валидную сессию (cookies, headers)

        Returns:
            Tuple[cookies, headers] или (None, None) при ошибке
        """
        try:
            # Быстрый путь: недавно провалидированная сессия из памяти — без сети.
            if (
                self._cached_session
                and self._validated_until
                and datetime.now() < self._validated_until
            ):
                return (
                    self._cached_session.get("cookies"),
                    self._cached_session.get("headers"),
                )

            # Пытаемся загрузить сохраненную сессию (с диска — свежая межпроцессно)
            session_data = self.load_session()

            # Если сессия есть, проверяем её валидность
            if session_data and self.validate_session(session_data):
                logger.info("Используем сохраненную валидную сессию")
                self._cached_session = session_data
                self._validated_until = datetime.now() + self._validation_ttl
                return session_data.get("cookies"), session_data.get("headers")

            # Сессии нет или она невалидна — логинимся под single-flight локом,
            # чтобы параллельные запросы не устраивали login-storm и не ротировали
            # cookie друг у друга.
            with self._login_lock:
                # Пока ждали лок, другой поток мог уже создать валидную сессию.
                session_data = self.load_session()
                if session_data and self.validate_session(session_data):
                    self._cached_session = session_data
                    self._validated_until = datetime.now() + self._validation_ttl
                    return session_data.get("cookies"), session_data.get("headers")

                logger.info("Создаю новую сессию...")
                session_data = self.login()  # save_session внутри обновит кэш

            if session_data:
                logger.info("✅ Новая сессия создана успешно")
                return session_data.get("cookies"), session_data.get("headers")

            logger.error("❌ Не удалось создать новую сессию")
            return None, None

        except Exception as e:
            logger.error(f"Ошибка получения валидной сессии: {e}")
            return None, None

    def get_headers_and_cookies(
        self,
    ) -> Tuple[Optional[Dict], Optional[Dict]]:
        """Как get_valid_session, но в порядке (headers, cookies).

        Именно так его ожидают вызовы в HeyDealerService (например, при запросе
        технического листа). Раньше метод отсутствовал — вызов падал с
        AttributeError, из-за чего технический лист через сервис всегда 404'ил.
        """
        cookies, headers = self.get_valid_session()
        return headers, cookies


# Глобальный экземпляр сервиса
heydealer_auth = HeyDealerAuthService()
