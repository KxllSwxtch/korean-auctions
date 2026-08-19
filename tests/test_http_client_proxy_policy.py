"""Egress policy tests for AsyncHttpClient.

Encar is proxy-optional and HappyCar/Glovis are proxy-required. The client
must express that difference explicitly rather than failing closed for every
caller, which is what took /api/catalog and /api/nav down.
"""

from __future__ import annotations

import asyncio

import aiohttp
import pytest

from app.core.http_client import AsyncHttpClient
from app.core.proxy_config import ProxyConfigurationError


PROXY_ENV = (
    "AUCTION_PROXY_HOST",
    "AUCTION_PROXY_USERNAME",
    "AUCTION_PROXY_PASSWORD",
)


@pytest.fixture(autouse=True)
def _clear_proxy_env(monkeypatch: pytest.MonkeyPatch):
    for name in (*PROXY_ENV, "USE_PROXY"):
        monkeypatch.delenv(name, raising=False)


def _configure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUCTION_PROXY_HOST", "proxy.example.test:8080")
    monkeypatch.setenv("AUCTION_PROXY_USERNAME", "operator")
    monkeypatch.setenv("AUCTION_PROXY_PASSWORD", "secret")


def test_proxy_optional_degrades_to_direct(monkeypatch: pytest.MonkeyPatch) -> None:
    """USE_PROXY=true without credentials must not break a proxy-optional caller.

    get_proxy_pool() runs at module import for several service singletons and
    start.sh uses `gunicorn --preload`, so raising here would kill the whole
    service in the master process before it forks.
    """
    monkeypatch.setenv("USE_PROXY", "true")

    client = AsyncHttpClient(use_proxy=True, proxy_required=False)

    assert client.egress_mode == "direct"
    assert client._pick_proxy() is None


def test_proxy_required_still_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """HappyCar and Glovis must never silently egress from a non-Korean IP."""
    monkeypatch.setenv("USE_PROXY", "true")

    with pytest.raises(ProxyConfigurationError):
        AsyncHttpClient(use_proxy=True, proxy_required=True)


def test_gate_off_ignores_configured_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """USE_PROXY=false keeps high-volume Encar traffic off metered bandwidth."""
    _configure(monkeypatch)
    monkeypatch.setenv("USE_PROXY", "false")

    client = AsyncHttpClient(use_proxy=True)

    assert client.egress_mode == "direct"
    assert client._pick_proxy() is None


def test_gate_on_with_credentials_selects_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch)
    monkeypatch.setenv("USE_PROXY", "true")

    client = AsyncHttpClient(use_proxy=True)

    assert client.egress_mode == "proxy"
    proxy_url = client._pick_proxy()
    assert proxy_url is not None
    assert "proxy.example.test:8080" in proxy_url


def test_caller_without_use_proxy_never_builds_a_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch)
    monkeypatch.setenv("USE_PROXY", "true")

    client = AsyncHttpClient(use_proxy=False)

    assert client.egress_mode == "direct"


def test_tls_verification_is_on_by_default() -> None:
    """aiohttp verifies certificates by default; the client must not opt out.

    Every HTTPS upstream in this project presents a valid chain, so the secure
    default applies everywhere and no call site needs verify_ssl=False.
    """

    async def exercise() -> None:
        client = AsyncHttpClient()
        try:
            session = await client.session
            assert client.verify_ssl is True
            assert isinstance(session.connector, aiohttp.TCPConnector)
        finally:
            await client.close()

    asyncio.run(exercise())


def test_session_is_reused_across_calls() -> None:
    """One pooled session per client, per aiohttp's documented guidance.

    The previous encar_proxy built a fresh ClientSession and TCPConnector for
    every single request, paying a new TCP handshake each time.
    """

    async def exercise() -> None:
        client = AsyncHttpClient()
        try:
            first = await client.session
            second = await client.session
            assert first is second
        finally:
            await client.close()

    asyncio.run(exercise())
