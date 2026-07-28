"""
Асинхронный HTTP клиент для выполнения запросов
"""

import asyncio
import os
import warnings
import aiohttp
from typing import Optional, Dict, Any, Union
from urllib.parse import urljoin

from app.core.logging import get_logger
from app.core.proxy_config import ProxyConfigurationError, ProxyPool, get_proxy_pool
from app.core.tls import SHARED_SSL_CONTEXT

logger = get_logger("async_http_client")


class AsyncHttpResponse:
    """Класс для представления HTTP ответа"""

    def __init__(
        self,
        status_code: int,
        text: str,
        headers: Dict[str, str],
        url: str,
        cookies: Optional[Dict[str, str]] = None,
    ):
        self.status_code = status_code
        self.text = text
        self.headers = headers
        self.url = url
        self.cookies = cookies or {}

    def json(self) -> Any:
        """Парсинг JSON ответа"""
        import json

        return json.loads(self.text)


class AsyncHttpClient:
    """Асинхронный HTTP клиент с поддержкой прокси"""

    def __init__(
        self,
        timeout: int = 30,
        use_proxy: bool = False,
        proxy_required: bool = False,
        verify_ssl: bool = True,
    ):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None
        self.use_proxy = use_proxy
        self.proxy_required = proxy_required
        self.verify_ssl = verify_ssl
        self._pool: Optional[ProxyPool] = None

        # Preserve the legacy USE_PROXY env gate: callers pass use_proxy=True,
        # but the pool is only built if USE_PROXY=true is also set.
        if not use_proxy or os.getenv("USE_PROXY", "false").lower() != "true":
            if use_proxy:
                logger.info("AsyncHttpClient egress=direct (USE_PROXY gate off)")
            return

        # Proxy-optional callers must degrade to direct egress instead of
        # failing closed. get_proxy_pool() runs at module import for several
        # service singletons, and start.sh uses `gunicorn --preload`, so an
        # unhandled raise here kills the whole service before it forks.
        try:
            self._pool = get_proxy_pool()
        except ProxyConfigurationError:
            if proxy_required:
                logger.error(
                    "AsyncHttpClient proxy is REQUIRED but unconfigured; set "
                    "AUCTION_PROXY_HOST, AUCTION_PROXY_USERNAME and "
                    "AUCTION_PROXY_PASSWORD in the deployment environment"
                )
                raise
            logger.warning(
                "AsyncHttpClient egress=direct: USE_PROXY=true but the auction "
                "proxy is unconfigured (missing AUCTION_PROXY_HOST, "
                "AUCTION_PROXY_USERNAME or AUCTION_PROXY_PASSWORD). This client "
                "is proxy-optional, so requests continue without a proxy."
            )
            return

        logger.info(
            f"🔐 AsyncHttpClient pool: {self._pool.names} "
            f"(round-robin per request)"
        )

    @property
    def egress_mode(self) -> str:
        """Report 'proxy' or 'direct' for diagnostics. Never exposes values."""
        return "proxy" if self._pool is not None else "direct"

    @property
    async def session(self) -> aiohttp.ClientSession:
        """Получение или создание сессии"""
        if self._session is None or self._session.closed:
            # Pass the shared context rather than ssl=True: aiohttp's own default
            # context reads OpenSSL's compiled-in CA paths, which are empty on
            # python.org macOS builds. See app/core/tls.py.
            connector = aiohttp.TCPConnector(
                ssl=SHARED_SSL_CONTEXT if self.verify_ssl else False,
                limit=100,
                limit_per_host=30,
                ttl_dns_cache=300,
            )
            self._session = aiohttp.ClientSession(
                connector=connector, timeout=self.timeout
            )
        return self._session

    def _pick_proxy(self) -> Optional[str]:
        """Pick the next proxy URL for a single request via round-robin pool."""
        if not self.use_proxy or self._pool is None:
            return None
        entry, url = self._pool.advance()
        logger.debug(f"🔁 Proxy rotated to {entry.name}")
        return url

    @property
    def proxy(self) -> Optional[str]:
        """Backwards-compatible read-only accessor (does not advance the pool)."""
        if not self.use_proxy or self._pool is None:
            return None
        return self._pool.current()[1]

    async def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> AsyncHttpResponse:
        """
        Выполнение GET запроса

        Args:
            url: URL для запроса
            headers: HTTP заголовки
            cookies: Cookies
            params: URL параметры
            timeout: Таймаут запроса

        Returns:
            AsyncHttpResponse: Ответ сервера
        """
        session = await self.session

        # Устанавливаем таймаут
        request_timeout = (
            aiohttp.ClientTimeout(total=timeout) if timeout else self.timeout
        )

        try:
            proxy_url = self._pick_proxy()
            proxy_info = f" via proxy" if proxy_url else ""
            logger.debug(f"🌐 GET запрос к {url}{proxy_info}")

            async with session.get(
                url,
                headers=headers,
                cookies=cookies,
                params=params,
                timeout=request_timeout,
                proxy=proxy_url,
            ) as response:
                text = await response.text()

                return AsyncHttpResponse(
                    status_code=response.status,
                    text=text,
                    headers=dict(response.headers),
                    url=str(response.url),
                    cookies={
                        cookie.key: cookie.value for cookie in response.cookies.values()
                    },
                )

        except asyncio.TimeoutError:
            logger.error(f"❌ Таймаут при запросе к {url}")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка при GET запросе к {url}: {str(e)}")
            raise

    async def post(
        self,
        url: str,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> AsyncHttpResponse:
        """
        Выполнение POST запроса

        Args:
            url: URL для запроса
            data: Данные для отправки (form data)
            json: JSON данные для отправки
            headers: HTTP заголовки
            cookies: Cookies
            timeout: Таймаут запроса

        Returns:
            AsyncHttpResponse: Ответ сервера
        """
        session = await self.session

        # Устанавливаем таймаут
        request_timeout = (
            aiohttp.ClientTimeout(total=timeout) if timeout else self.timeout
        )

        try:
            proxy_url = self._pick_proxy()
            proxy_info = f" via proxy" if proxy_url else ""
            logger.debug(f"🌐 POST запрос к {url}{proxy_info}")

            async with session.post(
                url,
                data=data,
                json=json,
                headers=headers,
                cookies=cookies,
                timeout=request_timeout,
                proxy=proxy_url,
            ) as response:
                text = await response.text()

                return AsyncHttpResponse(
                    status_code=response.status,
                    text=text,
                    headers=dict(response.headers),
                    url=str(response.url),
                    cookies={
                        cookie.key: cookie.value for cookie in response.cookies.values()
                    },
                )

        except asyncio.TimeoutError:
            logger.error(f"❌ Таймаут при POST запросе к {url}")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка при POST запросе к {url}: {str(e)}")
            raise

    async def close(self):
        """Закрытие сессии"""
        if self._session and not self._session.closed:
            logger.debug("🔄 Закрываю HTTP сессию")
            await self._session.close()

    async def __aenter__(self):
        """Вход в контекстный менеджер"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Выход из контекстного менеджера"""
        await self.close()

    def __del__(self):
        """Деструктор"""
        # asyncio.create_task() raises when no loop is running, which is the
        # normal case during interpreter teardown. Warn instead of scheduling
        # work that cannot run: the owning service must await close().
        session = getattr(self, "_session", None)
        if session is not None and not session.closed:
            warnings.warn(
                "AsyncHttpClient was garbage-collected with an open session; "
                "the owning service should await close() during shutdown",
                ResourceWarning,
                stacklevel=2,
            )
