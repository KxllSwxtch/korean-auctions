import json
from unittest.mock import Mock

import pytest

from app.core import auth_coordinator
from app.core.auth_errors import AuthConfigurationError
from app.core.config import settings
from app.services.lotte_service import LotteService


def _service_without_credentials(monkeypatch) -> LotteService:
    """A LotteService whose network entry point fails loudly if reached."""
    service = object.__new__(LotteService)
    service.session = None
    service._init_session = Mock(
        side_effect=AssertionError("missing credentials must not reach the network")
    )
    monkeypatch.setattr(settings, "lotte_username", None)
    monkeypatch.setattr(settings, "lotte_password", None)
    return service


def test_missing_lotte_credentials_fail_before_network(monkeypatch) -> None:
    """Missing credentials raise, naming both variables, without any I/O.

    This used to return False, which the coordinator could not tell apart from
    a rejected password and recorded as a failed attempt.
    """
    service = _service_without_credentials(monkeypatch)

    with pytest.raises(AuthConfigurationError) as excinfo:
        service._do_authenticate()

    service._init_session.assert_not_called()
    assert set(excinfo.value.missing) == {"LOTTE_USERNAME", "LOTTE_PASSWORD"}
    assert excinfo.value.retriable is False
    assert excinfo.value.error_code == "AUTH_MISCONFIGURED"


def test_missing_credentials_named_in_message_without_values(monkeypatch) -> None:
    """The message names variables so a log line is diagnosable on its own."""
    service = _service_without_credentials(monkeypatch)

    with pytest.raises(AuthConfigurationError) as excinfo:
        service._do_authenticate()

    message = str(excinfo.value)
    assert "LOTTE_USERNAME" in message
    assert "LOTTE_PASSWORD" in message


def test_config_error_does_not_burn_auth_cooldown(monkeypatch, tmp_path) -> None:
    """A misconfiguration must not be recorded as a failed attempt.

    Writing failure state opened a 30-second cross-worker cooldown, so every
    subsequent request reported "Auth cooldown active" instead of the real
    cause — and suppressed the first genuine attempt after the variables were
    finally set.
    """
    state_path = tmp_path / "lotte_auth_state.json"
    lock_path = tmp_path / "lotte_auth.lock"
    monkeypatch.setattr(auth_coordinator, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(auth_coordinator, "STATE_PATH", state_path)
    monkeypatch.setattr(auth_coordinator, "LOCK_PATH", lock_path)

    service = _service_without_credentials(monkeypatch)
    service.authenticated = False
    service._do_authenticate = Mock(
        side_effect=AssertionError("must short-circuit before attempting login")
    )

    with pytest.raises(AuthConfigurationError):
        auth_coordinator.ensure_authenticated(service)

    service._do_authenticate.assert_not_called()
    assert not state_path.exists(), "config error wrote auth failure state"
    assert not lock_path.exists(), "config error acquired the cross-worker lock"


def test_transient_failure_still_records_cooldown(monkeypatch, tmp_path) -> None:
    """The cooldown must survive for the case it was built for.

    Guards the fix above against over-reach: a rejected login is retriable and
    should still throttle every worker.
    """
    state_path = tmp_path / "lotte_auth_state.json"
    monkeypatch.setattr(auth_coordinator, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(auth_coordinator, "STATE_PATH", state_path)
    monkeypatch.setattr(auth_coordinator, "LOCK_PATH", tmp_path / "lotte_auth.lock")

    service = object.__new__(LotteService)
    service.session = None
    service.authenticated = False
    service.session_max_age_minutes = 25
    monkeypatch.setattr(settings, "lotte_username", "configured-user")
    monkeypatch.setattr(settings, "lotte_password", "configured-secret")
    service._do_authenticate = Mock(return_value=False)
    service._load_shared_session = Mock(return_value=False)

    assert auth_coordinator.ensure_authenticated(service) is False

    service._do_authenticate.assert_called_once()
    state = json.loads(state_path.read_text())
    assert state["last_attempt_time"] > state.get("last_success_time", 0)
