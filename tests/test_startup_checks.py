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


# ═══ CORS reporting ══════════════════════════════════════════════════════════
#
# The allowlist broke twice, and both times the deploy log looked healthy. These
# tests pin the three ways that log is now allowed to disagree with reality:
# "no https origin at all", "an entry that can never match", and "the matcher
# does not behave the way the printed list implies". None of them can be caught
# by a name-only provisioning check, because the variable was always *set*.


def _captured_cors_log(
    monkeypatch: pytest.MonkeyPatch,
    origins: list[str],
    origin_regex: str | None = None,
) -> dict[str, list[str]]:
    """Run log_cors_configuration and return its output grouped by level."""
    captured: dict[str, list[str]] = {"info": [], "warning": [], "error": []}
    for level in captured:
        monkeypatch.setattr(
            startup_checks.logger,
            level,
            lambda message, *a, _l=level, **k: captured[_l].append(str(message)),
        )
    startup_checks.log_cors_configuration(origins, origin_regex)
    return captured


HEALTHY_ORIGINS = ["https://www.smmotorskorea.com", "http://localhost:3000"]


def test_cors_logging_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same contract as the rest of this module: report, never raise. This runs
    inside the lifespan, so an exception here is a dead service on Render."""
    for origins, regex in (
        ([], None),
        (["https://a.example"], "https://[unclosed"),
        (["not-an-origin"], None),
        ([""], ""),
    ):
        _captured_cors_log(monkeypatch, origins, regex)


def test_a_healthy_allowlist_logs_a_passing_self_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = _captured_cors_log(monkeypatch, HEALTHY_ORIGINS)
    assert not log["error"]
    assert not log["warning"]
    assert any("self-check PASS" in m for m in log["info"])


def test_an_allowlist_with_no_https_origin_is_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shipping the local-development allowlist refuses every real request, and
    until now nothing said so — the existing check only fired on an empty list."""
    log = _captured_cors_log(monkeypatch, ["http://localhost:3000"])
    assert any("no https origin" in m for m in log["error"])
    assert any("self-check FAIL" in m for m in log["error"])


def test_an_empty_allowlist_is_still_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _captured_cors_log(monkeypatch, [])
    assert any("allowed-origin list is empty" in m for m in log["error"])


@pytest.mark.parametrize(
    ("origin", "reason"),
    [
        ("https://www.smmotorskorea.com/", "trailing slash"),
        ("https://SMMotorsKorea.com", "uppercase"),
        ("https://smmotorskorea.com/api", "path component"),
        ("smmotorskorea.com", "no http/https scheme"),
    ],
)
def test_an_unmatchable_origin_is_named_in_a_warning(
    monkeypatch: pytest.MonkeyPatch, origin: str, reason: str
) -> None:
    """An Origin header is scheme + host + port and never carries a path, a
    trailing slash or an uppercase letter, and Starlette compares it with `==`.
    Each of these is therefore dead configuration that reads exactly like live
    configuration in a log."""
    log = _captured_cors_log(monkeypatch, [*HEALTHY_ORIGINS, origin])
    warnings = "\n".join(log["warning"])
    assert origin in warnings
    assert reason in warnings


def test_the_self_check_catches_an_over_broad_regex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`https://.*` is allow_origins=["*"] wearing a disguise. The printed
    allowlist looks correct; only running the matcher reveals it."""
    log = _captured_cors_log(monkeypatch, HEALTHY_ORIGINS, r"https://.*")
    assert any("self-check FAIL" in m for m in log["error"])


def test_the_self_check_is_not_satisfied_by_an_unmatchable_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probing the first https entry regardless of its shape would report PASS
    on an exact-membership hit no browser could ever produce."""
    log = _captured_cors_log(monkeypatch, ["https://a.example/", "https://b.example/"])
    assert any("self-check FAIL" in m for m in log["error"])
    assert not any("self-check PASS" in m for m in log["info"])


def test_the_cors_log_prints_the_effective_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Values, not names — the whole point of this group. CORS_ALLOWED_ORIGINS
    was set the entire time during both outages; it was just set to the previous
    brand. Origins are public hostnames, not secrets."""
    regex = r"https://smmotorskorea-git-[a-z0-9-]{1,40}-example\.vercel\.app"
    log = _captured_cors_log(monkeypatch, HEALTHY_ORIGINS, regex)
    joined = "\n".join(log["info"])
    assert "https://www.smmotorskorea.com" in joined
    assert regex in joined
