"""Public HTTP contract tests for SK Auction routes (no live network).

Eight of the ten SK routes carry `except AuthError: raise` and correctly answer
503 during an auth failure. Two did not, and both were verified answering
HTTP 200 during the total outage of 2026-08-10:

* ``GET /total-count`` -> ``200 {"success": false, "total_count": 0,
  "message": "Error: session is not authenticated"}`` — the route's bare
  ``except Exception`` swallowed the AuthError the service correctly re-raised.
* ``GET /next-auction-date`` -> ``200 {"success": false,
  "auction_date": "20260810", "is_today": true}`` — a syntactically valid,
  entirely fabricated auction date handed to the storefront mid-outage. Here
  the swallow was one layer lower, in the service wrapper, so the route's
  AuthError branch was dead code.

The frontend cannot tell an outage from an empty auction when the status code
says 200, so these are pinned as 503 and an AST guard keeps route number
eleven from repeating the mistake.
"""

from __future__ import annotations

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.core.auth_errors import AuthConfigurationError, AuthError, AuthUnavailableError
from app.routes import sk_auction as sk_routes
from app.routes.sk_auction import router


REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTES_PATH = REPO_ROOT / "app" / "routes" / "sk_auction.py"

# Documented exceptions, both with the reason written at the call site: these
# two endpoints exist to *explain* an auth failure, so they report it in their
# body rather than becoming a 503 themselves.
REPORTING_HANDLERS = {"health_check", "get_info"}


class StubSKService:
    """Raises the given AuthError from whichever method the route calls."""

    def __init__(self, error: AuthError) -> None:
        self.error = error

    def __getattr__(self, name: str):
        def _raise(*args, **kwargs):
            raise self.error

        return _raise


@pytest.fixture
def client() -> TestClient:
    from main import auth_error_handler

    app = FastAPI()
    app.include_router(router)
    # The routes re-raise; main.py's handler is what turns that into the 503.
    app.add_exception_handler(AuthError, auth_error_handler)
    return TestClient(app, raise_server_exceptions=False)


def _install(monkeypatch, error: AuthError) -> None:
    monkeypatch.setattr(sk_routes, "sk_auction_service", StubSKService(error))


def test_total_count_propagates_auth_error_as_503(monkeypatch, client) -> None:
    """An outage must not be reported as an auction with zero cars."""
    _install(
        monkeypatch,
        AuthConfigurationError("SK Auction", ["SK_AUCTION_USERNAME", "SK_AUCTION_PASSWORD"]),
    )

    response = client.get("/api/v1/sk-auction/total-count?auction_date=20260811")

    assert response.status_code == 503
    body = response.json()
    assert body["error_code"] == "AUTH_MISCONFIGURED"
    assert "SK_AUCTION_USERNAME" in body["message"]


def test_next_auction_date_propagates_auth_error_instead_of_inventing_one(
    monkeypatch, client
) -> None:
    """A fabricated date is worse than an error: it looks authoritative."""
    _install(monkeypatch, AuthUnavailableError("SK Auction", "login rejected"))

    response = client.get("/api/v1/sk-auction/next-auction-date")

    assert response.status_code == 503
    body = response.json()
    assert body["error_code"] == "AUTH_UNAVAILABLE"
    assert "auction_date" not in body
    assert response.headers.get("Retry-After") == "60"


def test_misconfiguration_carries_no_retry_after(monkeypatch, client) -> None:
    """No amount of retrying sets an environment variable."""
    _install(
        monkeypatch,
        AuthConfigurationError("SK Auction", ["SK_AUCTION_PASSWORD"]),
    )

    response = client.get("/api/v1/sk-auction/brands")

    assert response.status_code == 503
    assert "Retry-After" not in response.headers


def _handlers_missing_auth_branch() -> list[str]:
    """Route handlers whose `except Exception` is not preceded by AuthError."""
    tree = ast.parse(ROUTES_PATH.read_text(encoding="utf-8"))
    offenders: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name in REPORTING_HANDLERS:
            continue

        for handler_parent in ast.walk(node):
            if not isinstance(handler_parent, ast.Try):
                continue

            names = []
            for handler in handler_parent.handlers:
                if handler.type is None:
                    names.append("Exception")
                elif isinstance(handler.type, ast.Name):
                    names.append(handler.type.id)
                else:
                    names.append(ast.dump(handler.type))

            if "Exception" not in names:
                continue
            if "AuthError" not in names[: names.index("Exception")]:
                offenders.append(node.name)
                break

    return sorted(set(offenders))


def test_every_sk_route_has_an_auth_error_branch() -> None:
    """A bare `except Exception` in a route silently downgrades a 503 to a 200.

    The nine-times-copied `except AuthError: raise` block is exactly the kind
    of convention that gets missed on the tenth route — it was, twice.
    """
    offenders = _handlers_missing_auth_branch()

    assert not offenders, (
        "these SK route handlers catch Exception without re-raising AuthError "
        f"first, so an auth failure becomes a 200: {offenders}"
    )
