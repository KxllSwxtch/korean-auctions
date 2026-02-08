"""
Базовый сервис для всех парсеров аукционов с продвинутыми возможностями
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Type, Union
from datetime import datetime, timedelta
from urllib.parse import urljoin
import json
import pickle
from pathlib import Path

from app.core.anti_block import AntiBlockClient, ProxyConfig
from app.core.async_client import AsyncAntiBlockClient, AsyncSessionConfig
from app.core.logging import logger
from app.core.config import settings


class AuthenticationError(Exception):
    """Ошибка аутентификации"""

    pass


class ParsingError(Exception):
    """Ошибка парсинга"""

    pass


class BaseAuctionService(ABC):
    """
    Базовый класс для всех сервисов аукционов

    Предоставляет:
    - Управление сессиями и куками
    - Защиту от блокировок
    - Кэширование
    - Аутентификацию
    - Логирование и мониторинг
    - Retry логику
    """

    def __init__(
        self,
        auction_name: str,
        base_url: str,
        credentials: Dict[str, str],
        use_async: bool = False,
        proxy_list: Optional[List[ProxyConfig]] = None,
    ):

        self.auction_name = auction_name
        self.base_url = base_url
        self.credentials = credentials
        self.use_async = use_async

        # Состояние аутентификации
        self.authenticated = False
        self.auth_timestamp = 0
        self.auth_ttl = 3600  # 1 час

        # Кэш
        self.cache: Dict[str, Any] = {}
        self.cache_timestamps: Dict[str, float] = {}
        self.cache_ttl = settings.cache_ttl

        # Настройка HTTP клиентов
        if use_async:
            config = AsyncSessionConfig(
                retry_attempts=settings.max_retries,
                retry_delay=settings.retry_delay,
            )
            self.client = AsyncAntiBlockClient(
                config=config, proxy_list=proxy_list, min_delay=1.0, max_delay=3.0
            )
        else:
            self.client = AntiBlockClient(
                use_proxy=bool(proxy_list),
                proxy_list=proxy_list,
                min_delay=1.0,
                max_delay=3.0,
            )

        # Статистика
        self.stats = {
            "requests_made": 0,
            "requests_failed": 0,
            "auth_attempts": 0,
            "auth_failures": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "last_activity": None,
        }

        # Пути для кэша
        self.cache_dir = Path("cache") / auction_name
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Инициализирован сервис {auction_name} (async={use_async})")

    @abstractmethod
    def get_urls(self) -> Dict[str, str]:
        """Получить словарь URL для аукциона"""
        pass

    @abstractmethod
    async def _perform_authentication(self) -> bool:
        """Выполнить аутентификацию (должно быть реализовано в наследниках)"""
        pass

    @abstractmethod
    async def _parse_auction_date(self, html_content: str) -> Optional[Dict[str, Any]]:
        """Парсинг даты аукциона"""
        pass

    @abstractmethod
    async def _parse_cars_list(self, html_content: str) -> List[Dict[str, Any]]:
        """Парсинг списка автомобилей"""
        pass

    @abstractmethod
    async def _parse_car_details(
        self, html_content: str, car_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Парсинг деталей автомобиля"""
        pass

    # === Управление аутентификацией ===

    def _is_session_still_valid(self) -> bool:
        """
        Lightweight session validity check before full re-authentication.

        Tries a cheap HEAD request to verify the session is still alive,
        avoiding unnecessary multi-roundtrip re-auth when session is actually valid.

        Returns:
            True if session appears still valid
        """
        if not self.authenticated:
            return False

        # Async clients use aiohttp — can't do sync HEAD request here.
        # Fall back to checking if we have active sessions (cookie existence).
        if self.use_async:
            return bool(self.client.session_manager._sessions)

        try:
            session = self.client.session_manager.get_session()
            response = session.head(
                self.base_url, timeout=10, allow_redirects=False
            )
            # Redirect to login page means session expired
            if response.status_code in [301, 302, 303]:
                location = response.headers.get("Location", "").lower()
                if "login" in location or "signin" in location:
                    logger.debug(
                        f"{self.auction_name}: Lightweight check - redirect to login, session expired"
                    )
                    return False
            if response.status_code < 400:
                logger.debug(
                    f"{self.auction_name}: Lightweight check - session still valid (HTTP {response.status_code})"
                )
                return True
            if response.status_code in [401, 403]:
                return False
        except Exception as e:
            logger.debug(f"{self.auction_name}: Lightweight check failed: {e}")
            return False

        return False

    async def ensure_authenticated(self) -> bool:
        """Убедиться, что аутентификация актуальна"""
        current_time = time.time()

        # Проверяем, нужна ли повторная аутентификация
        if not self.authenticated or current_time - self.auth_timestamp > self.auth_ttl:
            # Before full re-auth, try lightweight validation
            if self._is_session_still_valid():
                logger.info(
                    f"{self.auction_name}: Сессия истекла по времени, но ещё работает - продлеваем"
                )
                self.auth_timestamp = time.time()
                return True

            logger.info(f"Требуется аутентификация для {self.auction_name}")
            return await self.authenticate()

        return True

    async def authenticate(self) -> bool:
        """Выполнить аутентификацию"""
        try:
            self.stats["auth_attempts"] += 1
            logger.info(f"Начинаем аутентификацию в {self.auction_name}")

            success = await self._perform_authentication()

            if success:
                self.authenticated = True
                self.auth_timestamp = time.time()
                logger.info(f"✅ Аутентификация в {self.auction_name} успешна")
            else:
                self.stats["auth_failures"] += 1
                logger.error(f"❌ Аутентификация в {self.auction_name} не удалась")

            return success

        except Exception as e:
            self.stats["auth_failures"] += 1
            logger.error(f"Ошибка аутентификации в {self.auction_name}: {e}")
            raise AuthenticationError(f"Не удалось аутентифицироваться: {e}")

    def reset_authentication(self):
        """Сбросить состояние аутентификации"""
        self.authenticated = False
        self.auth_timestamp = 0
        logger.info(f"Сброшена аутентификация для {self.auction_name}")

    # === Кэширование ===

    def _get_cache_key(self, prefix: str, params: Dict[str, Any] = None) -> str:
        """Сгенерировать ключ кэша"""
        if params:
            params_str = json.dumps(params, sort_keys=True)
            return f"{self.auction_name}:{prefix}:{hash(params_str)}"
        return f"{self.auction_name}:{prefix}"

    def get_from_cache(self, key: str) -> Optional[Any]:
        """Получить данные из кэша"""
        cache_key = self._get_cache_key(key)

        if cache_key in self.cache:
            # Проверяем TTL
            if time.time() - self.cache_timestamps.get(cache_key, 0) < self.cache_ttl:
                self.stats["cache_hits"] += 1
                logger.debug(f"Cache hit: {cache_key}")
                return self.cache[cache_key]
            else:
                # Кэш устарел
                del self.cache[cache_key]
                if cache_key in self.cache_timestamps:
                    del self.cache_timestamps[cache_key]

        self.stats["cache_misses"] += 1
        logger.debug(f"Cache miss: {cache_key}")
        return None

    def save_to_cache(self, key: str, data: Any):
        """Сохранить данные в кэш"""
        cache_key = self._get_cache_key(key)
        self.cache[cache_key] = data
        self.cache_timestamps[cache_key] = time.time()
        logger.debug(f"Cached: {cache_key}")

    def clear_cache(self):
        """Очистить кэш"""
        self.cache.clear()
        self.cache_timestamps.clear()
        logger.info(f"Кэш {self.auction_name} очищен")

    # === Персистентный кэш ===

    def load_persistent_cache(self, key: str) -> Optional[Any]:
        """Загрузить данные из персистентного кэша"""
        cache_file = self.cache_dir / f"{key}.pkl"

        if cache_file.exists():
            try:
                with open(cache_file, "rb") as f:
                    data = pickle.load(f)

                # Проверяем TTL
                if time.time() - cache_file.stat().st_mtime < self.cache_ttl:
                    logger.debug(f"Persistent cache hit: {key}")
                    return data
                else:
                    # Удаляем устаревший файл
                    cache_file.unlink()

            except Exception as e:
                logger.error(f"Ошибка загрузки персистентного кэша {key}: {e}")

        return None

    def save_persistent_cache(self, key: str, data: Any):
        """Сохранить данные в персистентный кэш"""
        cache_file = self.cache_dir / f"{key}.pkl"

        try:
            with open(cache_file, "wb") as f:
                pickle.dump(data, f)
            logger.debug(f"Persistent cached: {key}")
        except Exception as e:
            logger.error(f"Ошибка сохранения персистентного кэша {key}: {e}")

    # === HTTP запросы ===

    async def make_request(
        self, method: str, url: str, session_id: Optional[str] = None, **kwargs
    ) -> Union[tuple, Any]:
        """Выполнить HTTP запрос с учетом статистики"""
        try:
            self.stats["requests_made"] += 1
            self.stats["last_activity"] = datetime.now().isoformat()

            if self.use_async:
                response, content = await self.client.request(
                    method, url, session_id=session_id or self.auction_name, **kwargs
                )
                return response, content
            else:
                response = self.client.request(
                    method, url, session_id=session_id or self.auction_name, **kwargs
                )
                return response

        except Exception as e:
            self.stats["requests_failed"] += 1
            logger.error(f"Ошибка HTTP запроса {method} {url}: {e}")
            raise

    async def get_page(self, url: str, **kwargs) -> Union[tuple, Any]:
        """GET запрос страницы"""
        return await self.make_request("GET", url, **kwargs)

    async def post_data(self, url: str, **kwargs) -> Union[tuple, Any]:
        """POST запрос с данными"""
        return await self.make_request("POST", url, **kwargs)

    # === Основные методы API ===

    async def get_auction_date(self) -> Optional[Dict[str, Any]]:
        """Получить дату аукциона с кэшированием"""
        cache_key = "auction_date"

        # Проверяем кэш
        cached_date = self.get_from_cache(cache_key)
        if cached_date:
            return cached_date

        # Проверяем персистентный кэш
        persistent_date = self.load_persistent_cache(cache_key)
        if persistent_date:
            self.save_to_cache(cache_key, persistent_date)
            return persistent_date

        try:
            # Обеспечиваем аутентификацию
            await self.ensure_authenticated()

            # Получаем главную страницу
            urls = self.get_urls()
            home_url = urljoin(self.base_url, urls.get("home", "/"))

            if self.use_async:
                response, content = await self.get_page(home_url)
            else:
                response = await self.get_page(home_url)
                content = response.text

            # Парсим дату
            date_info = await self._parse_auction_date(content)

            if date_info:
                # Сохраняем в кэш
                self.save_to_cache(cache_key, date_info)
                self.save_persistent_cache(cache_key, date_info)

            return date_info

        except Exception as e:
            logger.error(f"Ошибка получения даты аукциона {self.auction_name}: {e}")
            raise ParsingError(f"Не удалось получить дату аукциона: {e}")

    async def get_cars(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """Получить список автомобилей"""
        cache_key = f"cars_list_{limit}_{offset}"

        # Проверяем кэш (короткий TTL для списков)
        cached_cars = self.get_from_cache(cache_key)
        if cached_cars:
            return cached_cars

        try:
            # Обеспечиваем аутентификацию
            await self.ensure_authenticated()

            # Получаем страницу со списком
            urls = self.get_urls()
            cars_url = urljoin(self.base_url, urls.get("cars_list", "/"))

            # Добавляем параметры пагинации если нужно
            params = {"limit": limit, "offset": offset}

            if self.use_async:
                response, content = await self.get_page(cars_url, params=params)
            else:
                response = await self.get_page(cars_url, params=params)
                content = response.text

            # Парсим список автомобилей
            cars_data = await self._parse_cars_list(content)

            # Кэшируем на короткое время (списки меняются часто)
            self.save_to_cache(cache_key, cars_data)

            return cars_data

        except Exception as e:
            logger.error(
                f"Ошибка получения списка автомобилей {self.auction_name}: {e}"
            )
            raise ParsingError(f"Не удалось получить список автомобилей: {e}")

    async def get_car_details(
        self, car_id: str, car_data: Dict[str, Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Получить детали автомобиля"""
        cache_key = f"car_details_{car_id}"

        # Проверяем кэш
        cached_details = self.get_from_cache(cache_key)
        if cached_details:
            return cached_details

        try:
            # Обеспечиваем аутентификацию
            await self.ensure_authenticated()

            # Получаем детальную страницу
            urls = self.get_urls()
            details_url = urljoin(self.base_url, urls.get("car_details", "/"))

            params = {"id": car_id}

            if self.use_async:
                response, content = await self.get_page(details_url, params=params)
            else:
                response = await self.get_page(details_url, params=params)
                content = response.text

            # Парсим детали
            car_details = await self._parse_car_details(content, car_data or {})

            if car_details:
                # Кэшируем на длительное время (детали меняются редко)
                self.save_to_cache(cache_key, car_details)
                self.save_persistent_cache(cache_key, car_details)

            return car_details

        except Exception as e:
            logger.error(
                f"Ошибка получения деталей автомобиля {car_id} в {self.auction_name}: {e}"
            )
            raise ParsingError(f"Не удалось получить детали автомобиля: {e}")

    # === Статистика и мониторинг ===

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику сервиса"""
        return {
            "auction_name": self.auction_name,
            "authenticated": self.authenticated,
            "auth_age": (
                time.time() - self.auth_timestamp if self.authenticated else None
            ),
            "cache_size": len(self.cache),
            "stats": self.stats.copy(),
            "client_stats": getattr(self.client, "get_stats", lambda: {})(),
        }

    def reset_stats(self):
        """Сбросить статистику"""
        self.stats = {
            "requests_made": 0,
            "requests_failed": 0,
            "auth_attempts": 0,
            "auth_failures": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "last_activity": None,
        }
        logger.info(f"Статистика {self.auction_name} сброшена")

    # === Очистка ресурсов ===

    async def close(self):
        """Закрыть все соединения и очистить ресурсы"""
        if hasattr(self.client, "close"):
            if self.use_async:
                await self.client.close()
            else:
                self.client.close()

        logger.info(f"Сервис {self.auction_name} закрыт")
