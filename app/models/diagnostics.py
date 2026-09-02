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


class CacheStats(BaseModel):
    """Counters of one SwrCache, as `SwrCache.stats()` reports them."""

    entries: int = Field(description="Distinct keys currently held")
    inflight: int = Field(description="Loads running right now")
    hits: int = Field(description="Callers served a fresh value")
    stale_hits: int = Field(description="Callers served a stale value while refreshing")
    misses: int = Field(description="Callers that found no usable value")
    loads: int = Field(description="Loader invocations (misses minus single-flight savings)")


class EncarEgressDiagnostics(BaseModel):
    """State of Encar's direct-then-proxy failover. Contains no proxy value.

    Since 2026-08-29 api.encar.com's CloudFront edge refuses Render's egress
    addresses. This is how an operator tells "failover is armed and serving
    through the proxy" from "we are still relaying 403s" in one request.
    """

    commit: str | None = Field(
        description="RENDER_GIT_COMMIT of the running process; None outside Render"
    )
    egress_mode: Literal["proxy", "direct"] = Field(
        description="Primary leg: 'proxy' when the USE_PROXY gate is on"
    )
    failover_enabled: bool = Field(description="ENCAR_PROXY_FAILOVER is not false")
    failover_armed: bool = Field(
        description="Direct is primary and a proxy pool is held in reserve"
    )
    proxy_pool_size: int = Field(description="Entries in the reserve pool; 0 when unarmed")
    breaker_open: bool = Field(description="Direct egress is currently skipped")
    breaker_seconds_remaining: float = Field(description="Seconds left in the cooldown")
    breaker_trips: int = Field(description="Times direct egress was found blocked")
    cooldown_seconds: int = Field(description="ENCAR_DIRECT_BLOCK_COOLDOWN_SECONDS in effect")
    last_direct_status: int | None = Field(description="Last HTTP status on the direct leg")
    last_proxy_status: int | None = Field(description="Last HTTP status on the proxy leg")
    last_block_at: str | None = Field(description="ISO-8601 UTC time of the last block")
    caches: dict[str, CacheStats] = Field(description="nav and catalog cache counters")


class ReadinessResponse(BaseModel):
    """Provisioning readiness across egress, credentials and admin gates.

    Reports variable NAMES only. `status` is "ready" when every required group
    is configured, "degraded" when at least one required group is missing —
    the condition that otherwise surfaces as an unexplained 503 on a provider
    route while /health still reports ok.
    """

    status: Literal["ready", "degraded"] = Field(description="Aggregate readiness")
    degraded: bool = Field(description="True when any required group is unconfigured")
    commit: str | None = Field(
        default=None,
        description="RENDER_GIT_COMMIT of the running process; None outside Render",
    )
    use_proxy_gate: bool = Field(description="Value of the USE_PROXY gate")
    unready_services: list[str] = Field(
        default_factory=list,
        description="Services with at least one required group unconfigured",
    )
    groups: list[ConfigGroupStatus] = Field(description="Per-group status")
