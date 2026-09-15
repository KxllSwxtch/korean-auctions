"""EncarService.get_catalog must escape `+` in `q` before it reaches Encar.

encar_service.py is the legacy Oxylabs-proxy client (see the module's own
docstring). It builds its upstream URL the same hand-written way as
app/routes/encar_proxy.py, so it inherits the same bug: a literal `+` left
in place reaches api.encar.com and is read as a space.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.http_client import AsyncHttpResponse
from app.services.encar_service import EncarService

UPSTREAM_BODY = '{"Count":564,"SearchResults":[]}'


@pytest.fixture(autouse=True)
def _no_proxy_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """USE_PROXY off: EncarService.__init__ builds no pool (proxy-optional)."""
    monkeypatch.delenv("USE_PROXY", raising=False)
    monkeypatch.delenv("AUCTION_PROXY_HOST", raising=False)
    monkeypatch.delenv("AUCTION_PROXY_USERNAME", raising=False)
    monkeypatch.delenv("AUCTION_PROXY_PASSWORD", raising=False)


def _stub_get(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    async def fake_get(self, url, headers=None, cookies=None, params=None, timeout=None, egress="auto"):
        calls.append(url)
        return AsyncHttpResponse(status_code=200, text=UPSTREAM_BODY, headers={}, url=url)

    monkeypatch.setattr("app.core.http_client.AsyncHttpClient.get", fake_get)
    return calls


def test_get_catalog_escapes_plus_in_q(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _stub_get(monkeypatch)
    service = EncarService()

    response = asyncio.run(
        service.get_catalog(q="(And.FuelType.가솔린+전기.)", use_cache=False)
    )

    assert response.success is True
    assert len(calls) == 1
    assert "FuelType.가솔린%2B전기." in calls[0]
    assert "+" not in calls[0].split("?", 1)[1]


def test_get_catalog_default_q_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """The legacy default `q` is already percent-encoded Korean (no +/&/#),
    so escaping must be a no-op for it."""
    calls = _stub_get(monkeypatch)
    service = EncarService()
    default_q = "(And.Hidden.N._.CarType.A._.SellType.%EC%9D%BC%EB%B0%98.)"

    asyncio.run(service.get_catalog(use_cache=False))

    assert len(calls) == 1
    assert f"q={default_q}&" in calls[0]
