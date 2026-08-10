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


class ConfigGroupStatus(BaseModel):
    """One provisioning group's readiness. Contains no configuration values."""

    service: str = Field(description="Provider or subsystem identifier")
    kind: Literal["egress", "credentials", "token"] = Field(
        description="What this group provisions"
    )
    required: bool = Field(
        description="Whether the provider is unusable without this group"
    )
    configured: bool = Field(description="Whether every variable is present")
    missing: list[str] = Field(
        default_factory=list, description="Names of absent variables"
    )
    note: str = Field(description="What breaks when this group is absent")


class ReadinessResponse(BaseModel):
    """Provisioning readiness across egress, credentials and admin gates.

    Reports variable NAMES only. `status` is "ready" when every required group
    is configured, "degraded" when at least one required group is missing —
    the condition that otherwise surfaces as an unexplained 503 on a provider
    route while /health still reports ok.
    """

    status: Literal["ready", "degraded"] = Field(description="Aggregate readiness")
    degraded: bool = Field(description="True when any required group is unconfigured")
    use_proxy_gate: bool = Field(description="Value of the USE_PROXY gate")
    unready_services: list[str] = Field(
        default_factory=list,
        description="Services with at least one required group unconfigured",
    )
    groups: list[ConfigGroupStatus] = Field(description="Per-group status")
