"""CORS wiring, kept out of main.py so it can be tested without importing it.

The outage this module exists to prevent: the allowlist read
`https://www.autobaza.vip,https://autobaza.vip` for three days after the product
moved to nonstop-motors.com, so every client-side fetch from the live frontend
was refused at the preflight with 400 "Disallowed CORS origin". The API was
healthy throughout — /health answered 200 and every route answered curl normally
— because CORS is enforced by the browser, not by the server. Nothing in the
deploy log printed the effective allowlist and no test touched CORS, so the only
symptom was a frontend that rendered with no data.

Importing main.py drags in every router and provider service. Putting the wiring
here lets tests/test_cors.py apply the real configuration to a three-line app and
assert the header behaviour a browser would actually see.
"""

from __future__ import annotations

import re
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger("cors")

# The verbs the frontend actually issues. Explicit rather than "*" so adding one
# is a deliberate change; Starlette expands "*" to every method, DELETE and PUT
# included.
ALLOWED_METHODS = ["GET", "POST", "OPTIONS"]

# Preflight cache lifetime, in seconds.
PREFLIGHT_MAX_AGE = 600


def resolve_origin_regex(settings: Settings) -> Optional[str]:
    """The configured allow_origin_regex, or None when unset or unusable.

    CORSMiddleware.__init__ calls re.compile() on this value, so a typo in
    CORS_ALLOWED_ORIGIN_REGEX raises at import and leaves Render with a process
    that never starts — the failure app/core/startup_checks.py exists to avoid,
    where a partial outage is traded for a total one with no rollback signal.
    Falling back to None keeps the exact allowlist serving the production domain
    and loses only preview deployments, which is by far the smaller loss. The
    log line names the variable so the cause is one grep away.
    """
    pattern = settings.cors_origin_regex
    if pattern is None:
        return None
    try:
        re.compile(pattern)
    except re.error as exc:
        logger.error(
            f"CORS_ALLOWED_ORIGIN_REGEX is not a valid regular expression ({exc}); "
            "preview origins are disabled and the exact allowlist still applies"
        )
        return None
    return pattern


def configure_cors(
    app: FastAPI, settings: Settings
) -> tuple[list[str], Optional[str]]:
    """Install CORSMiddleware and return the values it was actually given.

    allow_credentials is False on purpose. No frontend call sets `credentials:`
    — this API has no session cookie and takes no cross-origin Authorization
    header — so Access-Control-Allow-Credentials grants a capability nothing
    uses. It is also the switch that makes every other CORS mistake expensive:
    the spec refuses Access-Control-Allow-Origin: * on a credentialed request,
    but Starlette routes around that by reflecting the caller's exact Origin
    whenever allow_credentials is set (starlette/middleware/cors.py —
    preflight_explicit_allow_origin), which is exactly how allow_origins=["*"]
    became a credentialed free-for-all here before commit 2ec4540. With it
    False, a too-broad allowlist leaks only public, unauthenticated data.

    Turning it back on is a deliberate act that belongs in the same change as
    whatever authentication needs it.

    Returns the effective (origins, origin_regex) so the caller can log what was
    really installed rather than what was configured — a regex that failed to
    compile is reported as the None it became.
    """
    origins = settings.cors_origin_list
    origin_regex = resolve_origin_regex(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=origin_regex,
        allow_credentials=False,
        allow_methods=ALLOWED_METHODS,
        allow_headers=["*"],
        max_age=PREFLIGHT_MAX_AGE,
    )
    return origins, origin_regex
