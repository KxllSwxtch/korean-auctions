"""Typed authentication failures, split by whether retrying can help.

Provider auth fails for two fundamentally different reasons, and the whole
stack used to conflate them:

* **Configuration** — a credential variable is unset. No amount of retrying
  fixes this. It is an operator error, and the only useful response names the
  variables that are missing.
* **Unavailability** — credentials exist but the login did not complete:
  upstream is down, the network blipped, the session was rejected. Retrying is
  exactly the right move.

Before this split, `app/routes/lotte.py` classified failures by substring-
matching the Russian text of an exception message (`"аутентифицироваться" in
str(e)`), and both cases returned 503 with `Retry-After: 60` — telling clients
to retry a missing password once a minute, forever. The auth coordinator was
equally blind: a missing password burned the same cross-worker 30-second
cooldown as a transient network error.

`retriable` is the single property callers should branch on; the route layer
maps it to an error code and to the presence of a `Retry-After` header.
"""

from __future__ import annotations

from typing import Mapping, Optional, Sequence


class AuthError(Exception):
    """Base class for provider authentication failures."""

    #: Whether repeating the same request could plausibly succeed.
    retriable: bool = True

    #: Stable machine-readable code echoed to API clients.
    error_code: str = "AUTH_UNAVAILABLE"

    def __init__(self, service: str, message: str) -> None:
        self.service = service
        super().__init__(message)


class AuthUnavailableError(AuthError):
    """Credentials are present but the login did not complete.

    Transient by assumption: upstream outage, network failure, unexpected
    redirect, rejected session. Retrying is appropriate.
    """

    retriable = True
    error_code = "AUTH_UNAVAILABLE"


class AuthConfigurationError(AuthError):
    """A required credential variable is unset.

    Non-retriable. Carries the missing variable NAMES so both the log line and
    the API response can name them — never the values.
    """

    retriable = False
    error_code = "AUTH_MISCONFIGURED"

    def __init__(self, service: str, missing: Sequence[str]) -> None:
        self.missing = tuple(missing)
        names = ", ".join(self.missing)
        super().__init__(
            service,
            f"{service} credentials are not configured; set {names}",
        )


def missing_credential_names(credentials: Mapping[str, Optional[str]]) -> list[str]:
    """Return the names whose value is unset or blank.

    `credentials` maps the environment variable NAME to its resolved value, so
    callers pass e.g. ``{"LOTTE_USERNAME": settings.lotte_username}``. Values
    are only ever tested for emptiness, never logged or returned.
    """
    return [
        name
        for name, value in credentials.items()
        if not (value or "").strip()
    ]


def require_credentials(
    service: str, credentials: Mapping[str, Optional[str]]
) -> None:
    """Raise AuthConfigurationError if any credential is unset or blank.

    Call this at the top of a provider's authentication routine so a
    misconfiguration fails immediately and by name, rather than being POSTed
    upstream as a literal ``None`` password and coming back as an opaque
    parse error or a 500.
    """
    missing = missing_credential_names(credentials)
    if missing:
        raise AuthConfigurationError(service, missing)
