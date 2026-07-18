"""Boot-time egress configuration reporting.

Reports which secret-managed variable NAMES are absent so a missing Render
dashboard value appears in the first lines of the deploy log instead of
surfacing days later as a 502 on a customer-facing route. Values are never
read into the log.

This module warns and never raises: a boot-time hard failure on Render
produces a dead service with no rollback signal, which would turn a
two-route outage into a total one.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger("startup_checks")

AUCTION_PROXY_VARIABLES = (
    "AUCTION_PROXY_HOST",
    "AUCTION_PROXY_USERNAME",
    "AUCTION_PROXY_PASSWORD",
)


@dataclass(frozen=True)
class EgressGroup:
    """One provider's egress requirement, described by variable names only."""

    service: str
    variables: tuple[str, ...]
    required: bool
    note: str


EGRESS_GROUPS: tuple[EgressGroup, ...] = (
    EgressGroup(
        service="glovis",
        variables=(
            "GLOVIS_PROXY_HOST",
            "GLOVIS_PROXY_USERNAME",
            "GLOVIS_PROXY_PASSWORD",
            "GLOVIS_PROXY_COUNTRY",
            "GLOVIS_PROXY_EGRESS_LABEL",
        ),
        required=True,
        note="Korean egress is mandatory; Glovis fails closed without it",
    ),
    EgressGroup(
        service="happycar",
        variables=AUCTION_PROXY_VARIABLES,
        required=True,
        note="HappyCar is login-gated and fails closed without the proxy",
    ),
    EgressGroup(
        service="encar",
        variables=AUCTION_PROXY_VARIABLES,
        required=False,
        note="api.encar.com answers non-Korean IPs; direct egress is supported",
    ),
)


def proxy_gate_enabled() -> bool:
    """Report the USE_PROXY gate honoured by AsyncHttpClient consumers."""
    return os.getenv("USE_PROXY", "false").strip().lower() == "true"


def missing_variables(group: EgressGroup) -> list[str]:
    """Return the names of unset or blank variables for one egress group."""
    return [name for name in group.variables if not os.getenv(name, "").strip()]


def log_egress_configuration() -> None:
    """Log one line per egress group at startup. Names only, never values."""
    logger.info(
        f"Egress check: USE_PROXY={'true' if proxy_gate_enabled() else 'false'}"
    )
    for group in EGRESS_GROUPS:
        missing = missing_variables(group)
        if not missing:
            logger.info(f"Egress check: {group.service} proxy configured")
            continue
        message = (
            f"Egress check: {group.service} proxy NOT configured; missing "
            f"{', '.join(missing)} — {group.note}"
        )
        if group.required:
            logger.error(message)
        else:
            logger.warning(message)
