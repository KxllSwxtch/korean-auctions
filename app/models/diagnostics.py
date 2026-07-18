"""Pydantic contracts for read-only deployment diagnostics."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EgressGroupStatus(BaseModel):
    """Per-provider egress readiness. Contains no configuration values."""

    service: str = Field(description="Provider identifier")
    required: bool = Field(description="Whether the proxy is mandatory")
    configured: bool = Field(description="Whether every variable is present")
    missing: list[str] = Field(
        default_factory=list, description="Names of absent variables"
    )
    mode: Literal["proxy", "direct", "unavailable"] = Field(
        description="Effective egress mode for this provider"
    )


class EgressDiagnosticsResponse(BaseModel):
    """Deployment-time egress readiness across every provider."""

    use_proxy_gate: bool = Field(description="Value of the USE_PROXY gate")
    groups: list[EgressGroupStatus] = Field(description="Per-provider status")
