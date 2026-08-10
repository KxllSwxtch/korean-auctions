"""Boot-time provisioning reporting must name what is missing, and never raise.

A missing LOTTE_USERNAME/LOTTE_PASSWORD pair produced a silent, healthy-looking
boot followed by a 503 on every /api/v1/lotte/* request. Credentials are now
reported at startup alongside egress, and exposed by /healthz/ready.

The "never raise" half matters just as much: startup_checks is called from the
lifespan, so raising here would turn a two-route outage into a dead service
with no rollback signal on Render.
"""

from __future__ import annotations

import pytest

from app.core import startup_checks
from app.core.startup_checks import (
    ADMIN_TOKEN_GROUPS,
    CREDENTIAL_GROUPS,
    EGRESS_GROUPS,
    log_startup_configuration,
    missing_variables,
)


ALL_GROUPS = (*EGRESS_GROUPS, *CREDENTIAL_GROUPS, *ADMIN_TOKEN_GROUPS)


def _clear_all(monkeypatch: pytest.MonkeyPatch) -> None:
    for group in ALL_GROUPS:
        for name in group.variables:
            monkeypatch.delenv(name, raising=False)


def test_lotte_credentials_are_checked_at_startup() -> None:
    """The specific gap that caused the outage."""
    lotte = next(g for g in CREDENTIAL_GROUPS if g.service == "lotte")
    assert set(lotte.variables) == {"LOTTE_USERNAME", "LOTTE_PASSWORD"}
    assert lotte.required is True


def test_every_login_gated_provider_has_a_credential_group() -> None:
    services = {group.service for group in CREDENTIAL_GROUPS}
    assert {
        "lotte",
        "enhanced_lotte",
        "autohub",
        "kcar",
        "happycar",
        "sk_auction",
        "heydealer",
    } <= services


def test_enhanced_lotte_is_optional_because_it_falls_back() -> None:
    """It falls back to LOTTE_*, so an unset pair is not a provisioning error."""
    group = next(g for g in CREDENTIAL_GROUPS if g.service == "enhanced_lotte")
    assert group.required is False


def test_missing_variables_reports_names(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all(monkeypatch)
    lotte = next(g for g in CREDENTIAL_GROUPS if g.service == "lotte")
    assert missing_variables(lotte) == ["LOTTE_USERNAME", "LOTTE_PASSWORD"]


def test_blank_value_counts_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dashboard variable saved as whitespace is unset in every way that matters."""
    lotte = next(g for g in CREDENTIAL_GROUPS if g.service == "lotte")
    monkeypatch.setenv("LOTTE_USERNAME", "   ")
    monkeypatch.setenv("LOTTE_PASSWORD", "configured")
    assert missing_variables(lotte) == ["LOTTE_USERNAME"]


def test_configured_group_reports_nothing_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lotte = next(g for g in CREDENTIAL_GROUPS if g.service == "lotte")
    monkeypatch.setenv("LOTTE_USERNAME", "user")
    monkeypatch.setenv("LOTTE_PASSWORD", "secret")
    assert missing_variables(lotte) == []


def test_startup_logging_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Called from the lifespan: a raise here is a dead service, not a warning."""
    _clear_all(monkeypatch)
    log_startup_configuration()  # must not raise with nothing configured


def test_startup_logging_never_logs_a_value(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Names only. Deploy logs are widely readable."""
    secret = "s3cr3t-value-that-must-not-appear"
    monkeypatch.setenv("LOTTE_USERNAME", secret)
    monkeypatch.delenv("LOTTE_PASSWORD", raising=False)

    messages: list[str] = []
    monkeypatch.setattr(
        startup_checks.logger,
        "error",
        lambda message, *a, **k: messages.append(str(message)),
    )
    monkeypatch.setattr(
        startup_checks.logger,
        "warning",
        lambda message, *a, **k: messages.append(str(message)),
    )
    monkeypatch.setattr(
        startup_checks.logger,
        "info",
        lambda message, *a, **k: messages.append(str(message)),
    )

    log_startup_configuration()

    joined = "\n".join(messages)
    assert secret not in joined, "startup log leaked a configuration value"
    assert "LOTTE_PASSWORD" in joined, "startup log should name the missing variable"


def test_group_notes_explain_the_consequence() -> None:
    """The note is what makes a log line actionable rather than just alarming."""
    for group in ALL_GROUPS:
        assert group.note.strip(), f"{group.service} has no note"
