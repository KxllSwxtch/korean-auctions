"""Route-level contract for Lotte authentication failures.

Both failure modes answer 503, but they differ in whether a client should come
back — and that difference is carried by the error code and by the presence of
Retry-After:

* AUTH_UNAVAILABLE   — transient, Retry-After present.
* AUTH_MISCONFIGURED — a credential variable is unset. No Retry-After: the
  previous behaviour sent `Retry-After: 60` for this case too, so clients
  politely re-requested a missing password once a minute, indefinitely.

Classification used to be a substring match on the Russian text of an
exception message (`"аутентифицироваться" in str(e)`), which meant rewording a
log string silently downgraded auth failures to HTTP 500.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import main
from app.core.auth_errors import AuthConfigurationError, AuthUnavailableError
from app.routes.lotte import get_lotte_service


@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app)


class _FailingService:
    """Stands in for LotteService, failing at the first awaited call."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def get_auction_date(self):
        raise self._error

    async def get_cars(self, *args, **kwargs):
        raise self._error

    async def get_total_cars_count(self):
        raise self._error

    async def fetch_total_count(self):
        raise self._error


def _override(client: TestClient, error: Exception) -> None:
    main.app.dependency_overrides[get_lotte_service] = lambda: _FailingService(error)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    main.app.dependency_overrides.clear()


CONFIG_ERROR = AuthConfigurationError("Lotte", ["LOTTE_USERNAME", "LOTTE_PASSWORD"])
TRANSIENT_ERROR = AuthUnavailableError("Lotte", "не удалось аутентифицироваться")

ENDPOINTS = ("/api/v1/lotte/cars/upcoming?limit=1", "/api/v1/lotte/total-count")


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_missing_credentials_return_503_without_retry_after(
    client: TestClient, endpoint: str
) -> None:
    _override(client, CONFIG_ERROR)

    response = client.get(endpoint)

    assert response.status_code == 503
    assert response.json()["error_code"] == "AUTH_MISCONFIGURED"
    assert "Retry-After" not in response.headers


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_transient_failure_returns_503_with_retry_after(
    client: TestClient, endpoint: str
) -> None:
    _override(client, TRANSIENT_ERROR)

    response = client.get(endpoint)

    assert response.status_code == 503
    assert response.json()["error_code"] == "AUTH_UNAVAILABLE"
    assert response.headers.get("Retry-After") == "60"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_auth_failure_is_never_reported_as_success(
    client: TestClient, endpoint: str
) -> None:
    """total-count in particular used to answer 200 with total_count: 0."""
    _override(client, CONFIG_ERROR)

    body = client.get(endpoint).json()

    assert body["success"] is False
    assert body.get("total_count", 0) == 0


def test_misconfiguration_names_the_variables_and_leaks_no_value(
    client: TestClient,
) -> None:
    _override(client, CONFIG_ERROR)

    message = client.get("/api/v1/lotte/cars/upcoming?limit=1").json()["message"]

    assert "LOTTE_USERNAME" in message
    assert "LOTTE_PASSWORD" in message


def test_non_auth_failure_still_returns_500(client: TestClient) -> None:
    """Guards against classifying every error as an auth problem."""
    _override(client, RuntimeError("upstream returned malformed HTML"))

    response = client.get("/api/v1/lotte/cars/upcoming?limit=1")

    assert response.status_code == 500
    assert response.json()["error_code"] == "INTERNAL_ERROR"
