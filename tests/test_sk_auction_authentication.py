"""Regression tests for the SK Auction credential and session state machine.

The outage these guard against: SK_AUCTION_USERNAME/PASSWORD were unset in
production, and only the first request per 25-minute window said so.

`_create_session()` stamped `_session_created_at` *before* calling
`_authenticate()`, so the timestamp survived a failed login.
`_needs_session_refresh()` then returned False for the next 1500 seconds, so
`_ensure_authenticated()` skipped the login retry entirely and raised the
generic retriable `AuthUnavailableError("session is not authenticated")`
instead of the truthful non-retriable `AuthConfigurationError` naming the two
missing variables. The Render log was a wall of the misleading message and the
actionable one appeared once per 25 minutes per worker.
"""

from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from app.core.auth_errors import AuthConfigurationError, AuthUnavailableError
from app.core.config import settings
from app.services.sk_auction_service import SKAuctionService


def _service(monkeypatch, username=None, password=None) -> SKAuctionService:
    """A service with credentials controlled through both config sources.

    Credentials are read at call time from os.environ with the Settings object
    as fallback, so a test has to pin both to be deterministic regardless of
    what a developer happens to have exported.
    """
    for name, value in (
        ("SK_AUCTION_USERNAME", username),
        ("SK_AUCTION_PASSWORD", password),
    ):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)

    monkeypatch.setattr(settings, "sk_auction_username", username, raising=False)
    monkeypatch.setattr(settings, "sk_auction_password", password, raising=False)
    return SKAuctionService()


def test_configuration_error_is_raised_on_every_request_not_just_the_first(
    monkeypatch,
) -> None:
    """Unset credentials must fail the same way on the 1st and 2nd request.

    This is the regression test for the outage. Before the fix the first call
    raised AuthConfigurationError (correct, names the variables) and every
    later call inside the 25-minute window raised
    AuthUnavailableError("session is not authenticated") — retriable, and
    naming nothing an operator could act on.
    """
    service = _service(monkeypatch)

    for attempt in ("first", "second"):
        with pytest.raises(AuthConfigurationError) as excinfo:
            service._ensure_authenticated()

        assert set(excinfo.value.missing) == {
            "SK_AUCTION_USERNAME",
            "SK_AUCTION_PASSWORD",
        }, f"{attempt} call did not name both missing variables"
        assert excinfo.value.retriable is False
        assert excinfo.value.error_code == "AUTH_MISCONFIGURED"


def test_missing_credentials_never_enter_the_failure_backoff(monkeypatch) -> None:
    """A missing variable is not a failed login attempt.

    Recording it as one would suppress the next genuine attempt for a full
    backoff window after an operator finally sets the variables — and would
    re-hide the truthful error behind the generic one, which is the bug.
    """
    service = _service(monkeypatch)

    with pytest.raises(AuthConfigurationError):
        service._ensure_authenticated()

    assert service._last_auth_attempt_at is None
    assert service._session_created_at is None


def test_missing_credentials_reach_no_network(monkeypatch) -> None:
    """require_credentials() must short-circuit before any socket is opened."""
    service = _service(monkeypatch)
    service._authenticate = Mock(wraps=service._authenticate)

    fake_session = Mock()
    fake_session.get.side_effect = AssertionError(
        "missing credentials must not reach the network"
    )
    fake_session.post.side_effect = AssertionError(
        "missing credentials must not reach the network"
    )
    monkeypatch.setattr(
        "app.services.sk_auction_service.requests.Session",
        Mock(return_value=fake_session),
    )

    with pytest.raises(AuthConfigurationError):
        service._ensure_authenticated()

    fake_session.get.assert_not_called()
    fake_session.post.assert_not_called()


def test_failed_login_leaves_session_created_at_unset(monkeypatch) -> None:
    """The timestamp means 'age of the authenticated session', nothing else.

    Stamping it before the login attempt is what made a failure look like a
    healthy 25-minute-old session to _needs_session_refresh().
    """
    service = _service(monkeypatch, "configured-user", "configured-secret")
    service._authenticate = Mock(return_value=False)

    with pytest.raises(AuthUnavailableError):
        service._ensure_authenticated()

    assert service._session_created_at is None
    assert service._authenticated is False
    assert service._last_auth_attempt_at is not None
    assert service._needs_session_refresh() is True


def test_transient_failure_retries_only_after_backoff_expires(monkeypatch) -> None:
    """A failed login throttles retries without silencing them for 25 minutes.

    Guards both halves: the backoff must actually suppress an immediate retry
    (or a rejected shared dealer account gets hammered by every request), and
    it must actually expire (or we have reinvented the original bug with a
    smaller constant).
    """
    service = _service(monkeypatch, "configured-user", "configured-secret")
    service._authenticate = Mock(return_value=False)

    with pytest.raises(AuthUnavailableError):
        service._ensure_authenticated()
    assert service._authenticate.call_count == 1

    with pytest.raises(AuthUnavailableError):
        service._ensure_authenticated()
    assert service._authenticate.call_count == 1, "backoff did not suppress the retry"

    service._last_auth_attempt_at = datetime.now() - timedelta(
        seconds=SKAuctionService._AUTH_FAILURE_BACKOFF_SECONDS + 1
    )

    with pytest.raises(AuthUnavailableError):
        service._ensure_authenticated()
    assert service._authenticate.call_count == 2, "backoff never expired"


def test_successful_login_stamps_created_at_and_clears_backoff(monkeypatch) -> None:
    """Success is the only thing that starts the session clock."""
    service = _service(monkeypatch, "configured-user", "configured-secret")

    def _succeed() -> bool:
        service._authenticated = True
        return True

    service._authenticate = Mock(side_effect=_succeed)
    # An expired marker from an earlier failure: past the backoff, so it must
    # not block this attempt, and success must clear it rather than leave a
    # stale failure recorded against a healthy session.
    service._last_auth_attempt_at = datetime.now() - timedelta(
        seconds=SKAuctionService._AUTH_FAILURE_BACKOFF_SECONDS + 1
    )

    assert service._ensure_authenticated() is True
    assert service._session_created_at is not None
    assert service._last_auth_attempt_at is None
    assert service._needs_session_refresh() is False

    # Second call is served from state, without a second login.
    assert service._ensure_authenticated() is True
    assert service._authenticate.call_count == 1


def test_health_check_names_the_missing_variables(monkeypatch) -> None:
    """/api/v1/sk-auction/health must explain the failure it reports.

    It answered {"authenticated": false, "session_age": 650.0} during the
    outage — three fields, none of which said why, and a session_age for a
    session that never existed.
    """
    service = _service(monkeypatch)

    result = service.health_check()

    assert result["authenticated"] is False
    assert result["status"] == "degraded"
    assert result["session_age"] is None
    assert result["auth"]["error_code"] == "AUTH_MISCONFIGURED"
    assert result["auth"]["retriable"] is False
    assert set(result["auth"]["missing"]) == {
        "SK_AUCTION_USERNAME",
        "SK_AUCTION_PASSWORD",
    }


def test_health_check_never_leaks_a_credential_value(monkeypatch) -> None:
    """Diagnosis carries variable NAMES only, never their values."""
    import json

    service = _service(monkeypatch, "configured-user", "s3cret-sentinel-value")
    service._authenticate = Mock(return_value=False)

    body = json.dumps(service.health_check(), default=str)

    assert "s3cret-sentinel-value" not in body
    assert "configured-user" not in body


def test_credentials_are_read_at_call_time(monkeypatch) -> None:
    """Setting the Render variables must not require a code deploy.

    __init__ snapshotted them into instance attributes from an lru_cache'd
    Settings object built at import, inside the gunicorn --preload master.
    """
    service = _service(monkeypatch)
    # Unset resolves to something falsy; require_credentials() treats "" and
    # None identically, so the exact empty value is not part of the contract.
    assert not any(service._credentials())

    monkeypatch.setenv("SK_AUCTION_USERNAME", "late-user")
    monkeypatch.setenv("SK_AUCTION_PASSWORD", "late-secret")

    assert service._credentials() == ("late-user", "late-secret")
