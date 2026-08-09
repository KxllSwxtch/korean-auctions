"""Shared admin authorization for destructive/diagnostic endpoints.

Background
----------
Cache-clear, session-reset and token-overwrite endpoints were reachable
anonymously. Combined with the permissive CORS configuration that used to be in
main.py, a page in a visitor's browser could call them and read the response.

The concrete risks were:

* ``POST /api/v1/cache/clear`` and the per-provider variants — repeatedly
  flushing every cache forces a stampede of upstream scrapes against six Korean
  auction sites, which gets our IP or accounts banned.
* ``POST /api/v1/lotte/auth/reset`` / ``GET /api/v1/lotte/debug/auth`` — destroy
  the shared Lotte session and force a re-login; looped, this locks the account.
* ``POST /api/v1/autohub/auth/set-token`` — overwrites the JWT shared by every
  user of the process, so a garbage value is a full Autohub outage.

Usage
-----
Add as a route dependency::

    from app.core.admin_auth import require_admin_token

    @router.post("/cache/clear", dependencies=[Depends(require_admin_token)])
    async def clear_cache() -> dict[str, str]:
        ...

When ``ADMIN_API_TOKEN`` is unset the dependency fails closed with 503 rather
than allowing the call, so a missing configuration can never silently reopen
these endpoints.
"""

from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException

#: Environment variable holding the shared admin token.
ADMIN_TOKEN_ENV = "ADMIN_API_TOKEN"


def require_admin_token(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    """Reject the request unless a valid ``X-Admin-Token`` header is present.

    Raises:
        HTTPException: 503 when no token is configured (fail closed),
            403 when the supplied token does not match.
    """
    expected = os.getenv(ADMIN_TOKEN_ENV, "")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Administrative endpoints are not configured",
        )

    # compare_digest, not ==, so the comparison does not leak the token
    # prefix through response timing.
    provided = (x_admin_token or "").encode("utf-8")
    if not secrets.compare_digest(provided, expected.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Forbidden")
