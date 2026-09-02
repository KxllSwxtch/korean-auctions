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


# ═══ Failover pool and per-call egress override ═══════════════════════════════
#
# Since 2026-08-29 api.encar.com's CloudFront edge refuses Render's egress
# addresses. USE_PROXY stays "false" in production (it would put every
# AsyncHttpClient consumer on metered proxy bandwidth), so a proxy-optional
# caller needs a way to say "keep going direct, but hold the pool in reserve
# and let me pick the leg per request".


def _pick(client: AsyncHttpClient, egress: str):
    return client._pick_proxy(egress)  # type: ignore[arg-type]


def test_failover_armed_when_gate_off_and_credentials_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch)
    monkeypatch.setenv("USE_PROXY", "false")

    client = AsyncHttpClient(use_proxy=True, proxy_failover=True)

    assert client.egress_mode == "direct", "the gate still decides the primary leg"
    assert client.failover_armed is True
    assert client.failover_pool_size == 1
    assert client._pick_proxy() is None, "auto egress stays direct while the gate is off"


def test_failover_unarmed_without_credentials_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unconfigured pool degrades to plain direct egress, never a boot failure."""
    monkeypatch.setenv("USE_PROXY", "false")

    client = AsyncHttpClient(use_proxy=True, proxy_failover=True)

    assert client.egress_mode == "direct"
    assert client.failover_armed is False
    assert client.failover_pool_size == 0


def test_failover_flag_is_inert_when_gate_is_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """USE_PROXY=true already routes every request through the pool."""
    _configure(monkeypatch)
    monkeypatch.setenv("USE_PROXY", "true")

    client = AsyncHttpClient(use_proxy=True, proxy_failover=True)

    assert client.egress_mode == "proxy"
    assert client.failover_armed is False
    assert client.failover_pool_size == 0


def test_failover_is_off_by_default_for_existing_consumers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """encar_service, encar_truck_service and green_equipment_service keep today's behaviour."""
    _configure(monkeypatch)
    monkeypatch.setenv("USE_PROXY", "false")

    client = AsyncHttpClient(use_proxy=True)

    assert client.failover_armed is False
    assert client.failover_pool_size == 0
    with pytest.raises(ProxyConfigurationError):
        _pick(client, "proxy")


def test_explicit_proxy_egress_uses_failover_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch)
    monkeypatch.setenv("USE_PROXY", "false")
    client = AsyncHttpClient(use_proxy=True, proxy_failover=True)

    proxy_url = _pick(client, "proxy")

    assert proxy_url is not None
    assert "proxy.example.test:8080" in proxy_url
    assert client.egress_mode == "direct", "an explicit leg does not flip the mode"


def test_explicit_proxy_egress_without_any_pool_raises_proxy_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USE_PROXY", "false")
    client = AsyncHttpClient(use_proxy=True, proxy_failover=True)

    with pytest.raises(ProxyConfigurationError) as excinfo:
        _pick(client, "proxy")

    assert "proxy egress requested but no auction proxy pool is configured" in str(excinfo.value)


def test_explicit_direct_egress_bypasses_pool_in_proxy_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch)
    monkeypatch.setenv("USE_PROXY", "true")
    client = AsyncHttpClient(use_proxy=True)

    assert client.egress_mode == "proxy"
    assert _pick(client, "direct") is None
    assert _pick(client, "auto") is not None


def test_partial_triple_leaves_failover_unarmed_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A half-set AUCTION_PROXY_* triple is a ProxyConfigurationError from
    get_proxy_pool(); a proxy-optional caller must absorb it, not die at boot."""
    monkeypatch.setenv("AUCTION_PROXY_HOST", "proxy.example.test:8080")
    monkeypatch.setenv("USE_PROXY", "false")

    client = AsyncHttpClient(use_proxy=True, proxy_failover=True)

    assert client.egress_mode == "direct"
    assert client.failover_armed is False


class _FakeAiohttpResponse:
    status = 200
    headers: dict[str, str] = {}
    url = "https://api.encar.com/"
    cookies: dict[str, str] = {}

    async def text(self) -> str:
        return "ok"


class _FakeSession:
    """Records the kwargs AsyncHttpClient hands to aiohttp for each request."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def get(self, url, **kwargs):
        self.calls.append(kwargs)
        response = _FakeAiohttpResponse()

        class _Ctx:
            async def __aenter__(self_inner):
                return response

            async def __aexit__(self_inner, *exc):
                return False

        return _Ctx()


def test_get_forwards_explicit_egress_to_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The per-call override must reach aiohttp's `proxy=` kwarg, not just _pick_proxy."""
    _configure(monkeypatch)
    monkeypatch.setenv("USE_PROXY", "false")
    client = AsyncHttpClient(use_proxy=True, proxy_failover=True)
    fake = _FakeSession()

    async def fake_session(self):
        return fake

    monkeypatch.setattr(AsyncHttpClient, "session", property(fake_session))

    async def exercise() -> None:
        await client.get("https://api.encar.com/x", egress="direct")
        await client.get("https://api.encar.com/x", egress="proxy")
        await client.get("https://api.encar.com/x")

    asyncio.run(exercise())

    assert fake.calls[0]["proxy"] is None
    assert "proxy.example.test:8080" in fake.calls[1]["proxy"]
    assert fake.calls[2]["proxy"] is None, "auto egress follows the gate (off)"
