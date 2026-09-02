"""Readiness probe covering egress, credentials and admin gates.

Deliberately separate from `/health`:

* `/health` is liveness. It is Render's `healthCheckPath`, so it must stay a
  static 200 — a health check that fails on missing configuration makes a
  misconfigured deploy unrollbackable, which is the failure this whole module
  exists to avoid trading one outage for a worse one.
* `/healthz/ready` is readiness. It answers 503 when a required provisioning
  group is absent, so a monitor or a developer gets a machine-readable answer
  to "why is every Lotte route 503ing" instead of grepping the boot log.

Variable NAMES only. No value is ever read into the response.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.core.startup_checks import (
    ADMIN_TOKEN_GROUPS,
    CREDENTIAL_GROUPS,
    EGRESS_GROUPS,
    ConfigGroup,
    missing_variables,
    proxy_gate_enabled,
    render_git_commit,
)
from app.models.diagnostics import ConfigGroupStatus, ReadinessResponse

router = APIRouter()


def _status(group: ConfigGroup, kind: str) -> ConfigGroupStatus:
    missing = missing_variables(group)
    return ConfigGroupStatus(
        service=group.service,
        kind=kind,
        required=group.required,
        configured=not missing,
        missing=missing,
        note=group.note,
    )


def build_readiness() -> ReadinessResponse:
    """Collect readiness across every provisioning group."""
    groups = [
        *(_status(group, "egress") for group in EGRESS_GROUPS),
        *(_status(group, "credentials") for group in CREDENTIAL_GROUPS),
        *(_status(group, "token") for group in ADMIN_TOKEN_GROUPS),
    ]

    # Deduplicate while preserving order: a provider can appear under both an
    # egress and a credentials group (HappyCar needs both), and reporting it
    # once per unmet requirement would overstate how many services are down.
    unready: list[str] = []
    for group in groups:
        if group.required and not group.configured and group.service not in unready:
            unready.append(group.service)

    return ReadinessResponse(
        status="degraded" if unready else "ready",
        degraded=bool(unready),
        commit=render_git_commit(),
        use_proxy_gate=proxy_gate_enabled(),
        unready_services=unready,
        groups=groups,
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(response: Response) -> ReadinessResponse:
    """Report provisioning readiness; 503 when a required group is missing."""
    payload = build_readiness()
    if payload.degraded:
        response.status_code = 503
    return payload
