"""Boot-time configuration reporting for egress and provider credentials.

Reports which secret-managed variable NAMES are absent so a missing Render
dashboard value appears in the first lines of the deploy log instead of
surfacing days later as a 502 on a customer-facing route. Values are never
read into the log.

Credentials were originally outside this check, which is how an unset
LOTTE_USERNAME/LOTTE_PASSWORD pair produced a silent boot followed by a 503
on every /api/v1/lotte/* request, with nothing in the startup log connecting
the two. Egress and credentials are the same class of provisioning mistake
and are now reported the same way.

This module warns and never raises: a boot-time hard failure on Render
produces a dead service with no rollback signal, which would turn a
two-route outage into a total one. `/healthz/ready` is where a caller gets a
non-200 for the same condition.
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
class ConfigGroup:
    """One provisioning requirement, described by variable names only."""

    service: str
    variables: tuple[str, ...]
    required: bool
    note: str


# Historical name: this dataclass described egress groups before credentials
# reused it. Kept so app/routes/diagnostics.py and its response model stay
# valid imports.
EgressGroup = ConfigGroup


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


# Login-gated providers. `required` means the provider cannot serve a single
# request without these — not that the application should refuse to boot.
CREDENTIAL_GROUPS: tuple[ConfigGroup, ...] = (
    ConfigGroup(
        service="lotte",
        variables=("LOTTE_USERNAME", "LOTTE_PASSWORD"),
        required=True,
        note="every /api/v1/lotte/* route authenticates before it can list cars",
    ),
    ConfigGroup(
        service="enhanced_lotte",
        variables=("ENHANCED_LOTTE_USERNAME", "ENHANCED_LOTTE_PASSWORD"),
        required=False,
        note="/api/v2/lotte second account; falls back to LOTTE_* when unset",
    ),
    ConfigGroup(
        service="autohub",
        variables=("AUTOHUB_USERNAME", "AUTOHUB_PASSWORD"),
        required=True,
        note="Autohub signin; AUTOHUB_JWT_TOKEN can pre-seed the session instead",
    ),
    ConfigGroup(
        service="kcar",
        variables=("KCAR_USERNAME", "KCAR_PASSWORD"),
        required=True,
        note="KCar is login-gated",
    ),
    ConfigGroup(
        service="happycar",
        variables=("HAPPYCAR_USERNAME", "HAPPYCAR_PASSWORD"),
        required=True,
        note="HappyCar needs both these credentials and the shared auction proxy",
    ),
    ConfigGroup(
        service="sk_auction",
        variables=("SK_AUCTION_USERNAME", "SK_AUCTION_PASSWORD"),
        required=True,
        note="SK Auction is login-gated",
    ),
    ConfigGroup(
        service="heydealer",
        variables=("HEYDEALER_USERNAME", "HEYDEALER_PASSWORD"),
        required=True,
        note="shared HeyDealer dealer account",
    ),
)

# Admin gates. Unset is a valid deployment choice — it just means those routes
# fail closed with 503, which reads as an outage if you do not know the gate
# is what answered.
ADMIN_TOKEN_GROUPS: tuple[ConfigGroup, ...] = (
    ConfigGroup(
        service="admin_api",
        variables=("ADMIN_API_TOKEN",),
        required=False,
        note="unset -> cache clear, auth reset and /debug/* return 503",
    ),
    ConfigGroup(
        service="glovis_cache_admin",
        variables=("GLOVIS_CACHE_ADMIN_TOKEN",),
        required=False,
        note="unset -> POST /api/v1/internal/glovis/cache/clear returns 503",
    ),
)


def proxy_gate_enabled() -> bool:
    """Report the USE_PROXY gate honoured by AsyncHttpClient consumers."""
    return os.getenv("USE_PROXY", "false").strip().lower() == "true"


def missing_variables(group: ConfigGroup) -> list[str]:
    """Return the names of unset or blank variables for one group."""
    return [name for name in group.variables if not os.getenv(name, "").strip()]


def _log_groups(groups: tuple[ConfigGroup, ...], label: str, subject: str) -> None:
    """Log one line per group. Names only, never values."""
    for group in groups:
        missing = missing_variables(group)
        if not missing:
            logger.info(f"{label}: {group.service} {subject} configured")
            continue
        message = (
            f"{label}: {group.service} {subject} NOT configured; missing "
            f"{', '.join(missing)} — {group.note}"
        )
        if group.required:
            logger.error(message)
        else:
            logger.warning(message)


def log_egress_configuration() -> None:
    """Log one line per egress group at startup. Names only, never values."""
    logger.info(
        f"Egress check: USE_PROXY={'true' if proxy_gate_enabled() else 'false'}"
    )
    _log_groups(EGRESS_GROUPS, "Egress check", "proxy")


def log_credential_configuration() -> None:
    """Log one line per login-gated provider and admin gate at startup."""
    _log_groups(CREDENTIAL_GROUPS, "Credential check", "credentials")
    _log_groups(ADMIN_TOKEN_GROUPS, "Credential check", "token")


def log_startup_configuration() -> None:
    """Report egress and credential provisioning together at boot."""
    log_egress_configuration()
    log_credential_configuration()
