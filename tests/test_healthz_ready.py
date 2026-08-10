"""/healthz/ready reports provisioning without disclosing configuration values.

Exists because `/health` is a static literal that returns 200 on a deployment
with no credentials at all — so nothing distinguished a working instance from
one that 503s on every auction route.

The split is deliberate: `/health` stays liveness (it is Render's
healthCheckPath, and a config-sensitive health check would make a
misconfigured deploy unrollbackable), `/healthz/ready` is readiness and may
answer 503.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.startup_checks import ADMIN_TOKEN_GROUPS, CREDENTIAL_GROUPS, EGRESS_GROUPS
from app.routes.healthz import build_readiness


ALL_GROUPS = (*EGRESS_GROUPS, *CREDENTIAL_GROUPS, *ADMIN_TOKEN_GROUPS)


def _configure_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    for group in ALL_GROUPS:
        for name in group.variables:
            monkeypatch.setenv(name, "configured")


def _clear_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    for group in ALL_GROUPS:
        for name in group.variables:
            monkeypatch.delenv(name, raising=False)


def test_reports_degraded_and_names_missing_lotte_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_everything(monkeypatch)
    monkeypatch.delenv("LOTTE_USERNAME", raising=False)
    monkeypatch.delenv("LOTTE_PASSWORD", raising=False)

    payload = build_readiness()

    assert payload.degraded is True
    assert payload.status == "degraded"
    assert "lotte" in payload.unready_services

    lotte = next(
        g for g in payload.groups if g.service == "lotte" and g.kind == "credentials"
    )
    assert lotte.configured is False
    assert lotte.missing == ["LOTTE_USERNAME", "LOTTE_PASSWORD"]


def test_reports_ready_when_everything_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_everything(monkeypatch)

    payload = build_readiness()

    assert payload.degraded is False
    assert payload.status == "ready"
    assert payload.unready_services == []


def test_optional_groups_do_not_make_the_service_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset admin tokens and the enhanced-Lotte fallback are valid choices.

    Only variables no required group depends on are cleared: AUCTION_PROXY_* is
    shared between the optional `encar` group and the required `happycar` one,
    so clearing it "as optional" would unconfigure a required group and make
    this assert about something else entirely.
    """
    _configure_everything(monkeypatch)
    required_variables = {
        name for group in ALL_GROUPS if group.required for name in group.variables
    }
    for group in ALL_GROUPS:
        if group.required:
            continue
        for name in group.variables:
            if name not in required_variables:
                monkeypatch.delenv(name, raising=False)

    payload = build_readiness()

    assert payload.degraded is False
    assert payload.unready_services == []


def test_unready_services_are_not_double_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HappyCar needs both a credential group and an egress group."""
    _clear_everything(monkeypatch)

    payload = build_readiness()

    assert payload.unready_services.count("happycar") == 1


def test_response_never_contains_a_configuration_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "s3cr3t-value-that-must-not-appear"
    _configure_everything(monkeypatch)
    monkeypatch.setenv("LOTTE_PASSWORD", secret)

    body = build_readiness().model_dump_json()

    assert secret not in body


def test_endpoint_status_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    """503 when degraded, 200 when ready — and /health stays 200 regardless."""
    import main

    with TestClient(main.app) as client:
        _clear_everything(monkeypatch)
        degraded = client.get("/healthz/ready")
        assert degraded.status_code == 503
        assert degraded.json()["status"] == "degraded"

        # Liveness must not follow readiness: Render rolls back on it.
        assert client.get("/health").status_code == 200

        _configure_everything(monkeypatch)
        ready = client.get("/healthz/ready")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"
