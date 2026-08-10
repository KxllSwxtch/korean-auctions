"""A logged-out Lotte service must never be reported as an empty auction.

`fetch_total_count` returned `success=True, total_count=0` whenever
authentication failed, because three layers swallowed the failure and returned
0 (`_fetch_total_count_from_home_page`, `get_total_cars_count`, and the caller
itself). The route then returned that model bare, which FastAPI serialised as
HTTP 200.

The result was a backend that could not authenticate advertising "0 cars
available" as a normal, cacheable answer — visible in production, not just
locally. "The auction is empty" and "we could not log in" are different facts
and must stay distinguishable.

Async tests use asyncio.run(scenario()) to match tests/test_async_cache.py;
this suite does not install pytest-asyncio.
"""

from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest

from app.core.auth_errors import AuthConfigurationError, AuthError
from app.core.config import settings
from app.services.lotte_service import LotteService


def _service() -> LotteService:
    svc = object.__new__(LotteService)
    svc.session = None
    svc.authenticated = False
    svc._cached_total_count = 0
    svc._cached_total_count_time = 0.0
    return svc


def test_home_page_count_raises_instead_of_returning_zero() -> None:
    service = _service()
    service._ensure_session = Mock(return_value=False)

    async def scenario() -> None:
        with pytest.raises(AuthError):
            await service._fetch_total_count_from_home_page()

    asyncio.run(scenario())


def test_ajax_count_raises_instead_of_returning_zero() -> None:
    service = _service()
    service._ensure_session = Mock(return_value=False)

    async def scenario() -> None:
        with pytest.raises(AuthError):
            await service.get_total_cars_count()

    asyncio.run(scenario())


def test_fetch_total_count_does_not_report_success_when_logged_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The headline regression: no success=True/total_count=0 on auth failure."""
    monkeypatch.setattr(settings, "lotte_username", None)
    monkeypatch.setattr(settings, "lotte_password", None)
    service = _service()
    service._ensure_session = Mock(return_value=False)

    async def scenario() -> None:
        with pytest.raises(AuthError):
            await service.fetch_total_count()

    asyncio.run(scenario())


def test_config_error_propagates_with_variable_names() -> None:
    service = _service()
    service._ensure_session = Mock(
        side_effect=AuthConfigurationError(
            "Lotte", ["LOTTE_USERNAME", "LOTTE_PASSWORD"]
        )
    )

    async def scenario() -> None:
        with pytest.raises(AuthConfigurationError) as excinfo:
            await service.fetch_total_count()
        assert set(excinfo.value.missing) == {"LOTTE_USERNAME", "LOTTE_PASSWORD"}
        assert excinfo.value.retriable is False

    asyncio.run(scenario())


def test_genuinely_empty_auction_still_reports_success() -> None:
    """Guards the fix against over-reach: zero cars is a valid, successful answer."""
    service = _service()
    service._ensure_session = Mock(return_value=True)

    async def _zero() -> int:
        return 0

    service._fetch_total_count_from_home_page = _zero
    service.get_total_cars_count = _zero

    async def scenario() -> None:
        response = await service.fetch_total_count()
        assert response.success is True
        assert response.total_count == 0

    asyncio.run(scenario())
