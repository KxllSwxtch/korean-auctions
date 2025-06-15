"""
Асинхронный HTTP клиент для высокопроизводительного парсинга
"""

import asyncio
import random
import time
from typing import List, Optional, Dict, Any, Set
import aiohttp
import ssl
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

from app.core.anti_block import UserAgentRotator, ProxyConfig
from app.core.logging import logger


@dataclass
class AsyncSessionConfig:
    """Конфигурация асинхронной сессии"""

    connector_limit: int = 100
    connector_limit_per_host: int = 30
    timeout_total: int = 300
    timeout_connect: int = 30
    timeout_sock_read: int = 60
    max_redirects: int = 10
    retry_attempts: int = 3
    retry_delay: float = 1.0
    use_ssl: bool = False


class AsyncSessionManager:
    """Менеджер асинхронных HTTP сессий"""

    def __init__(
        self,
        config: AsyncSessionConfig = None,
        proxy_list: Optional[List[ProxyConfig]] = None,
    ):
        self.config = config or AsyncSessionConfig()
        self.proxy_list = proxy_list or []
        self.ua_rotator = UserAgentRotator()

        self._sessions: Dict[str, aiohttp.ClientSession] = {}
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._proxy_index = 0

    async def _create_session(
        self, session_id: str, proxy: Optional[ProxyConfig] = None
    ) -> aiohttp.ClientSession:
        """Создать новую асинхронную сессию"""

        # SSL контекст
        ssl_context = None
        if not self.config.use_ssl:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        # Настройка коннектора
        connector = aiohttp.TCPConnector(
            limit=self.config.connector_limit,
            limit_per_host=self.config.connector_limit_per_host,
            ssl=ssl_context,
            use_dns_cache=True,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )

        # Таймауты
        timeout = aiohttp.ClientTimeout(
            total=self.config.timeout_total,
            connect=self.config.timeout_connect,
            sock_read=self.config.timeout_sock_read,
        )

        # Заголовки
        headers = {
            "User-Agent": self.ua_rotator.get_random_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }

        # Создаем сессию
        session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=headers,
            max_redirects=self.config.max_redirects,
        )

        logger.info(f"Создана асинхронная сессия {session_id}")
        return session

    async def get_session(self, session_id: str = "default") -> aiohttp.ClientSession:
        """Получить асинхронную сессию"""
        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()

        async with self._session_locks[session_id]:
            if session_id not in self._sessions or self._sessions[session_id].closed:
                # Выбираем прокси если есть
                proxy = None
                if self.proxy_list:
                    proxy = self.proxy_list[self._proxy_index % len(self.proxy_list)]
                    self._proxy_index += 1

                self._sessions[session_id] = await self._create_session(
                    session_id, proxy
                )

            return self._sessions[session_id]

    async def close_session(self, session_id: str):
        """Закрыть конкретную сессию"""
        if session_id in self._sessions:
            await self._sessions[session_id].close()
            del self._sessions[session_id]
            logger.info(f"Сессия {session_id} закрыта")

    async def close_all_sessions(self):
        """Закрыть все сессии"""
        for session_id, session in self._sessions.items():
            if not session.closed:
                await session.close()
                logger.info(f"Сессия {session_id} закрыта")
        self._sessions.clear()
        self._session_locks.clear()


class AsyncAntiBlockClient:
    """Асинхронный клиент с защитой от блокировок"""

    def __init__(
        self,
        config: AsyncSessionConfig = None,
        proxy_list: Optional[List[ProxyConfig]] = None,
        min_delay: float = 0.5,
        max_delay: float = 2.0,
        concurrent_limit: int = 10,
    ):

        self.session_manager = AsyncSessionManager(config, proxy_list)
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.concurrent_limit = concurrent_limit

        self._semaphore = asyncio.Semaphore(concurrent_limit)
        self._last_request_times: Dict[str, float] = {}
        self._request_counts: Dict[str, int] = {}
        self._blocked_domains: Set[str] = set()

    async def _add_random_delay(self, domain: str = "default"):
        """Добавить случайную задержку между запросами для домена"""
        current_time = time.time()
        last_request = self._last_request_times.get(domain, 0)

        delay = random.uniform(self.min_delay, self.max_delay)
        elapsed = current_time - last_request

        if elapsed < delay:
            sleep_time = delay - elapsed
            logger.debug(f"Задержка {sleep_time:.2f}s для домена {domain}")
            await asyncio.sleep(sleep_time)

        self._last_request_times[domain] = time.time()

    def _extract_domain(self, url: str) -> str:
        """Извлечь домен из URL"""
        try:
            return urlparse(url).netloc
        except:
            return "unknown"

    def _is_blocked_response(
        self, response: aiohttp.ClientResponse, content: str
    ) -> bool:
        """Проверить, заблокирован ли ответ"""
        # Проверяем статус код
        if response.status in [403, 429, 503, 520, 521, 522, 523, 524]:
            return True

        # Проверяем содержимое
        content_lower = content.lower()
        block_indicators = [
            "blocked",
            "captcha",
            "bot",
            "access denied",
            "rate limit",
            "차단",
            "봇",
            "접근 거부",
            "보안",
            "verification",
            "cloudflare",
        ]

        return any(indicator in content_lower for indicator in block_indicators)

    async def _make_request_with_retry(
        self, method: str, url: str, session: aiohttp.ClientSession, **kwargs
    ) -> tuple[aiohttp.ClientResponse, str]:
        """Выполнить запрос с повторными попытками"""
        domain = self._extract_domain(url)

        # Проверяем, не заблокирован ли домен
        if domain in self._blocked_domains:
            logger.warning(f"Домен {domain} в черном списке, пропускаем запрос")
            raise aiohttp.ClientError(f"Домен {domain} заблокирован")

        for attempt in range(self.session_manager.config.retry_attempts):
            try:
                await self._add_random_delay(domain)

                # Добавляем рефerer если его нет
                if "headers" not in kwargs:
                    kwargs["headers"] = {}

                if "Referer" not in kwargs["headers"]:
                    parsed = urlparse(url)
                    kwargs["headers"]["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

                # Ротация User-Agent каждые 10 запросов
                request_count = self._request_counts.get(domain, 0) + 1
                self._request_counts[domain] = request_count

                if request_count % 10 == 0:
                    kwargs["headers"][
                        "User-Agent"
                    ] = self.session_manager.ua_rotator.get_random_agent()

                async with session.request(method, url, **kwargs) as response:
                    content = await response.text()

                    # Проверяем на блокировку
                    if self._is_blocked_response(response, content):
                        logger.warning(
                            f"Блокировка обнаружена на {url} (попытка {attempt + 1})"
                        )

                        if attempt == self.session_manager.config.retry_attempts - 1:
                            # Последняя попытка, добавляем домен в черный список
                            self._blocked_domains.add(domain)
                            logger.error(f"Домен {domain} добавлен в черный список")

                        # Увеличиваем задержку при блокировке
                        await asyncio.sleep(
                            self.session_manager.config.retry_delay * (attempt + 1)
                        )
                        continue

                    logger.debug(
                        f"Успешный запрос: {method} {url} -> {response.status}"
                    )
                    return response, content

            except asyncio.TimeoutError:
                logger.warning(f"Таймаут запроса {url} (попытка {attempt + 1})")
                if attempt < self.session_manager.config.retry_attempts - 1:
                    await asyncio.sleep(
                        self.session_manager.config.retry_delay * (attempt + 1)
                    )
                else:
                    raise

            except Exception as e:
                logger.error(f"Ошибка запроса {url} (попытка {attempt + 1}): {e}")
                if attempt < self.session_manager.config.retry_attempts - 1:
                    await asyncio.sleep(
                        self.session_manager.config.retry_delay * (attempt + 1)
                    )
                else:
                    raise

        raise aiohttp.ClientError(
            f"Не удалось выполнить запрос после {self.session_manager.config.retry_attempts} попыток"
        )

    async def request(
        self, method: str, url: str, session_id: str = "default", **kwargs
    ) -> tuple[aiohttp.ClientResponse, str]:
        """Выполнить HTTP запрос с защитой от блокировок"""
        async with self._semaphore:
            session = await self.session_manager.get_session(session_id)
            return await self._make_request_with_retry(method, url, session, **kwargs)

    async def get(
        self, url: str, session_id: str = "default", **kwargs
    ) -> tuple[aiohttp.ClientResponse, str]:
        """GET запрос"""
        return await self.request("GET", url, session_id=session_id, **kwargs)

    async def post(
        self, url: str, session_id: str = "default", **kwargs
    ) -> tuple[aiohttp.ClientResponse, str]:
        """POST запрос"""
        return await self.request("POST", url, session_id=session_id, **kwargs)

    async def get_multiple(
        self, urls: List[str], session_id: str = "default", **kwargs
    ) -> List[tuple[str, aiohttp.ClientResponse, str]]:
        """Параллельные GET запросы"""
        tasks = []
        for url in urls:
            task = asyncio.create_task(self._get_with_url(url, session_id, **kwargs))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Обрабатываем результаты
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Ошибка при запросе {urls[i]}: {result}")
                processed_results.append((urls[i], None, ""))
            else:
                processed_results.append((urls[i], result[0], result[1]))

        return processed_results

    async def _get_with_url(
        self, url: str, session_id: str, **kwargs
    ) -> tuple[aiohttp.ClientResponse, str]:
        """Вспомогательный метод для get_multiple"""
        return await self.get(url, session_id=session_id, **kwargs)

    def clear_blocked_domains(self):
        """Очистить список заблокированных доменов"""
        self._blocked_domains.clear()
        logger.info("Список заблокированных доменов очищен")

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику клиента"""
        return {
            "blocked_domains": list(self._blocked_domains),
            "request_counts": dict(self._request_counts),
            "active_sessions": len(self.session_manager._sessions),
            "concurrent_limit": self.concurrent_limit,
        }

    async def close(self):
        """Закрыть все сессии"""
        await self.session_manager.close_all_sessions()


# Глобальные экземпляры
async_client = AsyncAntiBlockClient()


@asynccontextmanager
async def get_async_client(
    config: AsyncSessionConfig = None, proxy_list: Optional[List[ProxyConfig]] = None
):
    """Контекстный менеджер для создания клиента"""
    client = AsyncAntiBlockClient(config=config, proxy_list=proxy_list)
    try:
        yield client
    finally:
        await client.close()
