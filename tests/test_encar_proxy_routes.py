"""Regression tests for the transparent Encar proxy routes.

Context: on 2026-07-15 commit 1888b6a made the shared proxy pool fail closed.
/api/catalog and /api/nav called get_proxy_pool() with no fallback, so both
returned 502 "proxy configuration unavailable" in production for days — while
/api/v1/encar/catalog, which hits the identical upstream URL through the
USE_PROXY gate, kept serving 200s. These tests pin the corrected behaviour.
"""

from __future__ import annotations

import asyncio

import aiohttp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.http_client import AsyncHttpResponse
from app.core.proxy_config import ProxyConfigurationError
from app.routes import encar_proxy


PROXY_ENV = (
    "AUCTION_PROXY_HOST",
    "AUCTION_PROXY_USERNAME",
    "AUCTION_PROXY_PASSWORD",
)
UPSTREAM_BODY = '{"Count":214592,"SearchResults":[]}'
NAV_QUERY = "(And.Hidden.N._.CarType.A._.SellType.일반.)"


@pytest.fixture(autouse=True)
def _reset_client(monkeypatch: pytest.MonkeyPatch):
    """Drop the module-level client and proxy env between tests."""
    encar_proxy._client = None
    for name in (*PROXY_ENV, "USE_PROXY"):
        monkeypatch.delenv(name, raising=False)
    yield
    encar_proxy._client = None


@pytest.fixture
def client() -> TestClient:
    """Mount only the router under test.

    Importing main would construct several module-level service singletons,
    which is both slow and unrelated to this contract.
    """
    app = FastAPI()
    app.include_router(encar_proxy.router)
    return TestClient(app)


def _stub_get(monkeypatch: pytest.MonkeyPatch, *, status: int = 200, body: str = UPSTREAM_BODY):
    """Replace AsyncHttpClient.get with a recording stub."""
    calls: list[str] = []

    async def fake_get(self, url, headers=None, cookies=None, params=None, timeout=None):
        calls.append(url)
        return AsyncHttpResponse(
            status_code=status, text=body, headers={}, url=url
        )

    monkeypatch.setattr("app.core.http_client.AsyncHttpClient.get", fake_get)
    return calls


def _stub_raise(monkeypatch: pytest.MonkeyPatch, exc: BaseException):
    """Replace AsyncHttpClient.get with a stub that raises `exc`."""

    async def fake_get(self, url, headers=None, cookies=None, params=None, timeout=None):
        raise exc

    monkeypatch.setattr("app.core.http_client.AsyncHttpClient.get", fake_get)


# --- The outage regression -------------------------------------------------


def test_catalog_serves_200_when_proxy_unconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE regression test: no proxy credentials must not break Encar.

    Encar is proxy-OPTIONAL. Before the fix this returned
    502 {"error":"upstream_error","detail":"proxy configuration unavailable"}.
    """
    _stub_get(monkeypatch)

    response = client.get("/api/catalog", params={"sr": "|ModifiedDate|0|1"})

    assert response.status_code == 200
    assert response.text == UPSTREAM_BODY
    assert encar_proxy.get_encar_proxy_client().egress_mode == "direct"


def test_nav_serves_200_when_proxy_unconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_get(monkeypatch)

    response = client.get("/api/nav", params={"q": NAV_QUERY})

    assert response.status_code == 200
    assert response.text == UPSTREAM_BODY


def test_upstream_url_keeps_raw_korean_and_pipes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Encar rejects a percent-encoded query; double-encoding yields Count: 0."""
    calls = _stub_get(monkeypatch)

    client.get("/api/nav", params={"q": NAV_QUERY, "inav": "|Metadata|Sort"})

    assert len(calls) == 1
    assert "일반" in calls[0], "Korean must not be percent-encoded"
    assert "|Metadata|Sort" in calls[0], "pipes must not be percent-encoded"
    assert "%EC%9D%BC%EB%B0%98" not in calls[0]


# --- Egress policy ---------------------------------------------------------


def test_gate_off_ignores_configured_proxy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """USE_PROXY=false keeps Encar off metered proxy bandwidth."""
    for name in PROXY_ENV:
        monkeypatch.setenv(name, "configured")
    monkeypatch.setenv("USE_PROXY", "false")
    _stub_get(monkeypatch)

    client.get("/api/catalog")

    assert encar_proxy.get_encar_proxy_client().egress_mode == "direct"


def test_gate_on_with_credentials_uses_proxy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUCTION_PROXY_HOST", "proxy.example.test:8080")
    monkeypatch.setenv("AUCTION_PROXY_USERNAME", "operator")
    monkeypatch.setenv("AUCTION_PROXY_PASSWORD", "secret")
    monkeypatch.setenv("USE_PROXY", "true")
    _stub_get(monkeypatch)

    client.get("/api/catalog")

    assert encar_proxy.get_encar_proxy_client().egress_mode == "proxy"


def test_client_is_reused_across_requests(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One pooled client per process — not a fresh session per request."""
    _stub_get(monkeypatch)

    for _ in range(5):
        client.get("/api/catalog")

    assert encar_proxy.get_encar_proxy_client() is encar_proxy.get_encar_proxy_client()


# --- Error differentiation -------------------------------------------------


def test_timeout_returns_504(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_raise(monkeypatch, asyncio.TimeoutError())

    response = client.get("/api/catalog")

    assert response.status_code == 504
    assert response.json()["detail"]["code"] == "upstream_timeout"
    assert response.json()["detail"]["retryable"] is True


def test_proxy_connect_failure_returns_502_proxy_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    exc = aiohttp.ClientProxyConnectionError(None, OSError("refused"))
    _stub_raise(monkeypatch, exc)

    response = client.get("/api/catalog")

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "proxy_error"


def test_payload_error_returns_502_invalid_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_raise(monkeypatch, aiohttp.ClientPayloadError("truncated"))

    response = client.get("/api/catalog")

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "upstream_invalid_response"


def test_proxy_config_error_returns_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_raise(monkeypatch, ProxyConfigurationError("proxy configuration unavailable"))

    response = client.get("/api/catalog")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "proxy_unavailable"
    assert response.json()["detail"]["retryable"] is False


def test_upstream_500_maps_to_502_with_upstream_status(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An Encar 5xx must be distinguishable from our own 502."""
    _stub_get(monkeypatch, status=500, body="upstream exploded")

    response = client.get("/api/catalog")

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "upstream_error"
    assert response.json()["detail"]["upstream_status"] == 500


def test_upstream_404_passes_through(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Encar's own 4xx semantics stay intact for the frontend."""
    _stub_get(monkeypatch, status=404, body='{"message":"not found"}')

    response = client.get("/api/catalog")

    assert response.status_code == 404
    assert response.text == '{"message":"not found"}'


def test_error_body_never_leaks_proxy_credentials(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed AUCTION_PROXY_HOST must not publish the password.

    proxy_config.ProxyEntry.build_url does not validate `host` (contrast
    glovis_transport.py, which rejects / @ ? #), so a bad port yields an
    aiohttp.InvalidURL whose str() is the full proxy URL including the
    password. The previous handler serialized str(exc) straight into this
    public, unauthenticated response.
    """
    leaky = aiohttp.InvalidURL("http://operator:sup3rsecret@proxy.example.test:not_a_port")
    _stub_raise(monkeypatch, leaky)

    response = client.get("/api/catalog")

    assert response.status_code == 502
    assert b"sup3rsecret" not in response.content
    assert b"proxy.example.test" not in response.content
    assert b"operator" not in response.content
