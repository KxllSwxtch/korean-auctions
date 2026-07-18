"""Read-only deployment diagnostics.

Exposes which egress variable NAMES are configured, never their values, so a
provisioning mistake is a one-request check instead of a log investigation.

/api/v1/glovis/health reporting `egress: kr-primary` is what made the Glovis
subsystem verifiable in seconds during the 2026-07 Encar outage; this gives
every provider the same affordance.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.startup_checks import (
    EGRESS_GROUPS,
    missing_variables,
    proxy_gate_enabled,
)
from app.models.diagnostics import EgressDiagnosticsResponse, EgressGroupStatus

router = APIRouter()


@router.get("/egress", response_model=EgressDiagnosticsResponse)
async def egress_diagnostics() -> EgressDiagnosticsResponse:
    """Report per-provider egress readiness without disclosing any value."""
    gate = proxy_gate_enabled()
    groups: list[EgressGroupStatus] = []
    for group in EGRESS_GROUPS:
        missing = missing_variables(group)
        configured = not missing
        if group.required:
            mode = "proxy" if configured else "unavailable"
        else:
            mode = "proxy" if (configured and gate) else "direct"
        groups.append(
            EgressGroupStatus(
                service=group.service,
                required=group.required,
                configured=configured,
                missing=missing,
                mode=mode,
            )
        )
    return EgressDiagnosticsResponse(use_proxy_gate=gate, groups=groups)
