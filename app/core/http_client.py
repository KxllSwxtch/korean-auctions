"""
Асинхронный HTTP клиент для выполнения запросов
"""

import asyncio
import aiohttp
from typing import Optional, Dict, Any, Union
from urllib.parse import urljoin

from app.core.logging import get_logger

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
    """Асинхронный HTTP клиент"""

    def __init__(self, timeout: int = 30):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    async def session(self) -> aiohttp.ClientSession:
        """Получение или создание сессии"""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                ssl=False, limit=100, limit_per_host=30  # Отключаем проверку SSL
            )
            self._session = aiohttp.ClientSession(
                connector=connector, timeout=self.timeout
            )
        return self._session

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
            logger.debug(f"🌐 GET запрос к {url}")

            async with session.get(
                url,
                headers=headers,
                cookies=cookies,
                params=params,
                timeout=request_timeout,
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
            logger.debug(f"🌐 POST запрос к {url}")

            async with session.post(
                url,
                data=data,
                json=json,
                headers=headers,
                cookies=cookies,
                timeout=request_timeout,
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
        if hasattr(self, "_session") and self._session and not self._session.closed:
            try:
                asyncio.create_task(self.close())
            except:
                pass
