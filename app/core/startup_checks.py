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
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.egress_breaker import cooldown_from_env
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
        note=(
            "api.encar.com blocks Render/AWS egress (since 2026-08-29); direct "
            "first, automatic proxy failover when AUCTION_PROXY_* is set and "
            "ENCAR_PROXY_FAILOVER is not false"
        ),
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


# Kill switch for Encar's direct-then-proxy failover. Default ON: since
# 2026-08-29 a direct request to api.encar.com from Render is a 403, so
# "off" is the outage. Only an explicit falsey value disables it — a typo
# in the dashboard must not silently take the catalog down again.
ENCAR_FAILOVER_ENV = "ENCAR_PROXY_FAILOVER"
_FALSEY = {"false", "0", "no", "off"}


def encar_failover_enabled() -> bool:
    """Whether Encar may retry a blocked direct request through the proxy pool."""
    return os.getenv(ENCAR_FAILOVER_ENV, "").strip().lower() not in _FALSEY


def render_git_commit() -> str | None:
    """The deployed SHA Render injects as RENDER_GIT_COMMIT; None elsewhere.

    A runtime platform variable like PORT, so it is read here rather than
    declared on Settings.
    """
    return os.getenv("RENDER_GIT_COMMIT", "").strip() or None


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
    logger.info(
        f"Egress check: {ENCAR_FAILOVER_ENV}="
        f"{'true' if encar_failover_enabled() else 'false'} "
        f"cooldown={cooldown_from_env()}s commit={render_git_commit() or 'unknown'}"
    )
    _log_groups(EGRESS_GROUPS, "Egress check", "proxy")


def log_credential_configuration() -> None:
    """Log one line per login-gated provider and admin gate at startup."""
    _log_groups(CREDENTIAL_GROUPS, "Credential check", "credentials")
    _log_groups(ADMIN_TOKEN_GROUPS, "Credential check", "token")


def log_cors_configuration(origins: list[str], origin_regex: str | None) -> None:
    """Print the effective browser allowlist at boot.

    The one configuration group whose VALUES belong in the log. Every other
    check in this module reports names, because a name is all you need when the
    failure is "unset". CORS_ALLOWED_ORIGINS was set the entire time — it was
    just set to the previous brand's domains — so no name-only check could ever
    have seen it, and the resulting site-wide outage went three days unnoticed.
    Origins are public hostnames, not secrets.

    Takes the values the middleware was actually constructed with rather than
    re-reading settings, so a regex that failed to compile is reported as the
    None it became and not as the string somebody typed.
    """
    if not origins:
        logger.error(
            "CORS check: the allowed-origin list is empty; every browser "
            "request will fail its preflight — set CORS_ALLOWED_ORIGINS"
        )
    else:
        logger.info(f"CORS check: allowed origins: {', '.join(origins)}")
        _warn_about_unmatchable_origins(origins)
        if not any(o.startswith("https://") for o in origins):
            logger.error(
                "CORS check: the allowed-origin list contains no https origin "
                f"({', '.join(origins)}); this is the local-development "
                "allowlist, and a deployment running it refuses every request "
                "from the real site — set CORS_ALLOWED_ORIGINS"
            )

    if origin_regex:
        logger.info(f"CORS check: allow_origin_regex={origin_regex}")
    else:
        logger.info(
            "CORS check: CORS_ALLOWED_ORIGIN_REGEX unset; Vercel preview "
            "deployments will be refused"
        )

    _log_cors_self_check(origins, origin_regex)


# An Origin header is scheme + host + port and never carries a path, a trailing
# slash, or an uppercase letter that was not in the registered name. Starlette
# compares it to the allowlist with `==` (and to the regex with re.fullmatch),
# so any of these makes an entry unmatchable — dead configuration that reads in
# the log exactly like live configuration.
_SELF_CHECK_KNOWN_BAD = "https://cors-selfcheck.invalid"


def _describe_unmatchable(origin: str) -> str | None:
    """Return why this origin can never match an Origin header, or None."""
    parts = urlsplit(origin)
    if parts.scheme not in ("http", "https"):
        return "no http/https scheme"
    if not parts.netloc:
        return "no host"
    if origin.endswith("/"):
        return "trailing slash"
    if parts.path:
        return f"path component {parts.path!r}"
    if parts.query or parts.fragment:
        return "query or fragment"
    if origin != origin.lower():
        return "uppercase characters"
    if origin != origin.strip():
        return "surrounding whitespace"
    return None


def _warn_about_unmatchable_origins(origins: list[str]) -> None:
    """Name every entry that is present but can never match anything."""
    for origin in origins:
        reason = _describe_unmatchable(origin)
        if reason is not None:
            logger.warning(
                f"CORS check: allowed origin {origin!r} can never match a "
                f"browser Origin header ({reason}); it is dead configuration"
            )


def _log_cors_self_check(origins: list[str], origin_regex: str | None) -> None:
    """Run the installed allowlist against a real origin and a known-bad one.

    "The string looks right" and "the matcher accepts it" are different claims,
    and only the second one keeps the site up. This exercises the same two
    checks Starlette does — exact membership, then re.fullmatch — so a regex
    that compiled but matches nothing, or an allowlist whose entries are all
    unmatchable, is visible in the deploy log rather than in a support ticket.

    Reports and never raises, in keeping with the module contract above.
    """
    # Guarded even though configure_cors only ever passes a regex that
    # resolve_origin_regex already compiled successfully. This module is called
    # from the lifespan, so raising here would trade a CORS misconfiguration for
    # a service that never starts — the exact failure app/core/cors.py exists to
    # avoid. A reporting routine must not be the thing that takes the app down.
    compiled = None
    if origin_regex:
        try:
            compiled = re.compile(origin_regex)
        except re.error as exc:
            logger.error(
                f"CORS check: self-check SKIPPED — CORS_ALLOWED_ORIGIN_REGEX is "
                f"not a valid regular expression ({exc})"
            )
            return

    def allowed(origin: str) -> bool:
        return origin in origins or bool(compiled and compiled.fullmatch(origin))

    # Probe with an origin that is *itself* well-formed. Picking the first https
    # entry regardless would let a list of nothing but unmatchable entries
    # (trailing slash, uppercase, a path) report PASS on the strength of an
    # exact-membership hit that no browser could ever produce.
    probe = next(
        (
            o
            for o in origins
            if o.startswith("https://") and _describe_unmatchable(o) is None
        ),
        None,
    )
    if probe is None:
        logger.error(
            "CORS check: self-check FAIL — no well-formed https origin to probe "
            "with, so no browser request from the live site can be accepted"
        )
        return

    if allowed(probe) and not allowed(_SELF_CHECK_KNOWN_BAD):
        logger.info(f"CORS check: self-check PASS (probed {probe})")
    else:
        logger.error(
            f"CORS check: self-check FAIL — the installed matcher "
            f"{'rejects' if not allowed(probe) else 'accepts'} "
            f"{probe if not allowed(probe) else _SELF_CHECK_KNOWN_BAD}; "
            "browser requests will not behave as the allowlist above implies"
        )


def log_startup_configuration() -> None:
    """Report egress and credential provisioning together at boot."""
    log_egress_configuration()
    log_credential_configuration()
