"""/api/v2/lotte must not serve an auth failure as an empty auction.

Two defects in the v2 stack (app/core/base_service.py + enhanced_lotte_service):

1. `ensure_authenticated()` returned a bool, and all three callers
   (get_auction_date, get_cars, get_car_details) wrote
   `await self.ensure_authenticated()` and discarded it. A failed login did not
   stop the request — the service fetched on, parsed the login page instead of
   data, and returned an empty list with HTTP 200.
2. `_perform_authentication` never checked that credentials existed, so unset
   ENHANCED_LOTTE_*/LOTTE_* reached the login POST as empty strings and came
   back as "wrong password" rather than "not configured".

`AuthenticationError` also inherited from bare Exception and was caught
nowhere, so the one place that raised it produced an unhandled 500.

Async tests use asyncio.run(scenario()) to match tests/test_async_cache.py.
"""

from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest

from app.core.auth_errors import AuthConfigurationError, AuthError, AuthUnavailableError
from app.core.base_service import AuthenticationError
from app.services.enhanced_lotte_service import EnhancedLotteService


def _service(username: str | None, password: str | None) -> EnhancedLotteService:
    svc = object.__new__(EnhancedLotteService)
    svc.auction_name = "lotte"
    svc.credentials = {"username": username, "password": password}
    svc.login_attempts_limit = 3
    svc.current_login_attempts = 0
    svc.authenticated = False
    svc.auth_timestamp = 0
    svc.auth_ttl = 3600
    svc.use_async = False
    svc.stats = {"auth_attempts": 0, "auth_failures": 0}
    return svc


def test_authentication_error_is_an_auth_error() -> None:
    """It used to be a bare Exception that no handler caught -> unhandled 500."""
    err = AuthenticationError("не удалось аутентифицироваться")
    assert isinstance(err, AuthError)
    assert err.retriable is True
    assert err.error_code == "AUTH_UNAVAILABLE"


def test_missing_credentials_raise_before_any_request() -> None:
    service = _service(None, None)
    service.get_page = Mock(
        side_effect=AssertionError("must not reach the network without credentials")
    )

    async def scenario() -> None:
        with pytest.raises(AuthConfigurationError) as excinfo:
            await service._perform_authentication()
        # Both pairs are named: ENHANCED_LOTTE_* falls back to LOTTE_*, so an
        # operator told only about one would set the wrong variable.
        message = str(excinfo.value)
        assert "ENHANCED_LOTTE_USERNAME" in message
        assert "LOTTE_USERNAME" in message
        assert excinfo.value.retriable is False

    asyncio.run(scenario())


def test_failed_login_stops_the_request() -> None:
    """The headline bug: callers ignored the bool, so the request continued."""
    service = _service("user", "secret")
    service._is_session_still_valid = Mock(return_value=False)

    async def _authenticate() -> bool:
        return False

    service.authenticate = _authenticate

    async def scenario() -> None:
        with pytest.raises(AuthUnavailableError):
            await service.ensure_authenticated()

    asyncio.run(scenario())


def test_successful_auth_still_returns_true() -> None:
    """Guards the fix against over-reach."""
    service = _service("user", "secret")
    service._is_session_still_valid = Mock(return_value=False)

    async def _authenticate() -> bool:
        return True

    service.authenticate = _authenticate

    async def scenario() -> None:
        assert await service.ensure_authenticated() is True

    asyncio.run(scenario())


def test_valid_session_short_circuits_without_reauth() -> None:
    service = _service("user", "secret")
    service._is_session_still_valid = Mock(return_value=True)
    service.authenticate = Mock(
        side_effect=AssertionError("a valid session must not re-authenticate")
    )

    async def scenario() -> None:
        assert await service.ensure_authenticated() is True

    asyncio.run(scenario())


def test_config_error_is_not_rewrapped_as_a_generic_auth_failure() -> None:
    """authenticate() must not erase the error code or the variable names."""
    service = _service(None, None)

    async def _perform() -> bool:
        raise AuthConfigurationError("Lotte v2", ["ENHANCED_LOTTE_USERNAME"])

    service._perform_authentication = _perform

    async def scenario() -> None:
        with pytest.raises(AuthConfigurationError):
            await service.authenticate()
        assert service.stats["auth_failures"] == 1

    asyncio.run(scenario())
