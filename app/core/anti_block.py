"""
Модуль защиты от блокировок и обхода анти-бот систем
"""

import asyncio
import random
import time
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass
from urllib.parse import urljoin
import aiohttp
import requests
from fake_useragent import UserAgent
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import logging

from app.core.logging import logger


@dataclass
class ProxyConfig:
    """Конфигурация прокси"""

    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: str = "http"

    @property
    def url(self) -> str:
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol}://{self.host}:{self.port}"


class UserAgentRotator:
    """Ротация User-Agent для каждого запроса"""

    def __init__(self):
        self.ua = UserAgent()
        # Набор проверенных User-Agent для корейских сайтов
        self.korean_optimized_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0",
        ]

    def get_random_agent(self) -> str:
        """Получить случайный User-Agent"""
        # 70% вероятность использовать оптимизированный для Кореи
        if random.random() < 0.7:
            return random.choice(self.korean_optimized_agents)
        # 30% вероятность использовать случайный из библиотеки
        try:
            return self.ua.random
        except:
            # Fallback если библиотека не работает
            return random.choice(self.korean_optimized_agents)


class ProxyManager:
    """Управление пулом прокси серверов"""

    def __init__(self, proxy_list: Optional[List[ProxyConfig]] = None):
        self.proxy_list = proxy_list or []
        self.failed_proxies = set()
        self.current_proxy_index = 0

    def add_proxy(self, proxy: ProxyConfig):
        """Добавить прокси в пул"""
        self.proxy_list.append(proxy)

    def get_next_proxy(self) -> Optional[ProxyConfig]:
        """Получить следующий рабочий прокси"""
        if not self.proxy_list:
            return None

        available_proxies = [
            p for p in self.proxy_list if p.url not in self.failed_proxies
        ]
        if not available_proxies:
            # Если все прокси упали, сбрасываем счетчик неудач
            self.failed_proxies.clear()
            available_proxies = self.proxy_list

        if available_proxies:
            proxy = available_proxies[self.current_proxy_index % len(available_proxies)]
            self.current_proxy_index += 1
            return proxy
        return None

    def mark_proxy_failed(self, proxy: ProxyConfig):
        """Отметить прокси как неработающий"""
        self.failed_proxies.add(proxy.url)
        logger.warning(f"Прокси {proxy.url} отмечен как неработающий")


class RequestsSessionManager:
    """Менеджер HTTP сессий с защитой от блокировок"""

    def __init__(
        self,
        max_sessions: int = 5,
        session_ttl: int = 300,
        use_proxy: bool = False,
        proxy_list: Optional[List[ProxyConfig]] = None,
    ):
        self.max_sessions = max_sessions
        self.session_ttl = session_ttl
        self.use_proxy = use_proxy

        self.sessions: Dict[str, requests.Session] = {}
        self.session_timestamps: Dict[str, float] = {}
        self.session_request_counts: Dict[str, int] = {}

        self.ua_rotator = UserAgentRotator()
        self.proxy_manager = ProxyManager(proxy_list)

    def _create_session(self, session_id: str) -> requests.Session:
        """Создать новую HTTP сессию с защитными механизмами"""
        session = requests.Session()

        # Настройка retry стратегии
        from requests.adapters import HTTPAdapter
        from requests.packages.urllib3.util.retry import Retry

        retry_strategy = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504, 520, 521, 522, 523, 524],
            respect_retry_after_header=True,
        )

        adapter = HTTPAdapter(
            max_retries=retry_strategy, pool_connections=10, pool_maxsize=20
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Базовые заголовки имитирующие реального пользователя
        session.headers.update(
            {
                "User-Agent": self.ua_rotator.get_random_agent(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Cache-Control": "max-age=0",
            }
        )

        # Настройка прокси если включено
        if self.use_proxy:
            proxy = self.proxy_manager.get_next_proxy()
            if proxy:
                session.proxies = {
                    "http": proxy.url,
                    "https": proxy.url,
                }
                logger.info(
                    f"Сессия {session_id} использует прокси: {proxy.host}:{proxy.port}"
                )

        # Настройка таймаутов
        session.timeout = (30, 60)  # connect timeout, read timeout

        logger.info(f"Создана новая сессия {session_id}")
        return session

    def get_session(self, session_id: Optional[str] = None) -> requests.Session:
        """Получить сессию с автоматической ротацией"""
        if session_id is None:
            session_id = f"session_{random.randint(1, self.max_sessions)}"

        current_time = time.time()

        # Проверяем, нужно ли обновить сессию
        if (
            session_id in self.sessions
            and session_id in self.session_timestamps
            and current_time - self.session_timestamps[session_id] > self.session_ttl
        ):

            # Сессия устарела, закрываем её
            self.sessions[session_id].close()
            del self.sessions[session_id]
            del self.session_timestamps[session_id]
            if session_id in self.session_request_counts:
                del self.session_request_counts[session_id]
            logger.info(f"Сессия {session_id} обновлена по TTL")

        # Создаем новую сессию если её нет
        if session_id not in self.sessions:
            self.sessions[session_id] = self._create_session(session_id)
            self.session_timestamps[session_id] = current_time
            self.session_request_counts[session_id] = 0

        # Ротация User-Agent каждые 10 запросов
        self.session_request_counts[session_id] += 1
        if self.session_request_counts[session_id] % 10 == 0:
            self.sessions[session_id].headers[
                "User-Agent"
            ] = self.ua_rotator.get_random_agent()
            logger.debug(f"User-Agent обновлен для сессии {session_id}")

        return self.sessions[session_id]

    def close_all_sessions(self):
        """Закрыть все активные сессии"""
        for session in self.sessions.values():
            session.close()
        self.sessions.clear()
        self.session_timestamps.clear()
        self.session_request_counts.clear()
        logger.info("Все сессии закрыты")


class AntiBlockClient:
    """Клиент с продвинутой защитой от блокировок"""

    def __init__(
        self,
        max_sessions: int = 5,
        session_ttl: int = 300,
        use_proxy: bool = False,
        proxy_list: Optional[List[ProxyConfig]] = None,
        min_delay: float = 1.0,
        max_delay: float = 5.0,
    ):

        self.session_manager = RequestsSessionManager(
            max_sessions=max_sessions,
            session_ttl=session_ttl,
            use_proxy=use_proxy,
            proxy_list=proxy_list,
        )

        self.min_delay = min_delay
        self.max_delay = max_delay
        self.last_request_time = 0

    def _add_random_delay(self):
        """Добавить случайную задержку между запросами"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time

        delay = random.uniform(self.min_delay, self.max_delay)

        if elapsed < delay:
            sleep_time = delay - elapsed
            logger.debug(f"Задержка {sleep_time:.2f}s перед следующим запросом")
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=30),
        retry=retry_if_exception_type((requests.RequestException, requests.Timeout)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def request(
        self, method: str, url: str, session_id: Optional[str] = None, **kwargs
    ) -> requests.Response:
        """Выполнить HTTP запрос с защитой от блокировок"""

        self._add_random_delay()

        session = self.session_manager.get_session(session_id)

        # Добавляем рефerer если его нет
        if "headers" not in kwargs:
            kwargs["headers"] = {}

        if "Referer" not in kwargs["headers"]:
            # Пытаемся установить разумный рефerer
            from urllib.parse import urlparse

            parsed = urlparse(url)
            kwargs["headers"]["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

        try:
            response = session.request(method, url, verify=False, **kwargs)

            # Проверяем на признаки блокировки
            if self._is_blocked(response):
                logger.warning(f"Обнаружена блокировка на {url}")
                # Пробуем сменить сессию и повторить
                session.close()
                if session_id and session_id in self.session_manager.sessions:
                    del self.session_manager.sessions[session_id]
                raise requests.RequestException("Обнаружена блокировка")

            logger.debug(f"Успешный запрос: {method} {url} -> {response.status_code}")
            return response

        except Exception as e:
            logger.error(f"Ошибка запроса {method} {url}: {e}")
            raise

    def _is_blocked(self, response: requests.Response) -> bool:
        """Проверить, заблокирован ли запрос"""
        # Проверяем статус код
        if response.status_code in [403, 429, 503]:
            return True

        # Проверяем содержимое на признаки блокировки
        content = response.text.lower()
        block_indicators = [
            "blocked",
            "captcha",
            "bot",
            "access denied",
            "차단",
            "봇",
            "접근 거부",
            "보안",
            "verification",
        ]

        return any(indicator in content for indicator in block_indicators)

    def get(
        self, url: str, session_id: Optional[str] = None, **kwargs
    ) -> requests.Response:
        """GET запрос с защитой"""
        return self.request("GET", url, session_id=session_id, **kwargs)

    def post(
        self, url: str, session_id: Optional[str] = None, **kwargs
    ) -> requests.Response:
        """POST запрос с защитой"""
        return self.request("POST", url, session_id=session_id, **kwargs)

    def close(self):
        """Закрыть все сессии"""
        self.session_manager.close_all_sessions()


# Глобальный экземпляр для использования в приложении
anti_block_client = AntiBlockClient()
