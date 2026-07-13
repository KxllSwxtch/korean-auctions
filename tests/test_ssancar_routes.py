"""Public HTTP contract tests for SSANCAR routes (no live network)."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.models.ssancar import SSANCARResponse
from app.parsers.ssancar_parser import PARSE_STATUS_NOT_FOUND
from app.routes.ssancar import get_ssancar_service, router
from app.services.ssancar_transport import (
    SSANCARUpstreamAuthError,
    SSANCARUpstreamInvalidResponseError,
    SSANCARUpstreamTimeoutError,
    SSANCARUpstreamUnavailableError,
)


class StubService:
    BASE_URL = "https://www.ssancar.com"

    def __init__(self) -> None:
        self.list_result = SSANCARResponse(
            success=True,
            message="ok",
            cars=[],
            total_count=0,
            current_page=1,
            page_size=15,
            week_number="2",
        )
        self.list_error = None
        self.search_error = None
        self.count_error = None
        self.detail_error = None
        self.health_error = None
        self.count = 1010
        self.last_filters = None
        self.cookie_mutated = False
        self.health_probe = SimpleNamespace(
            week_number="2",
            upstream_count=0,
            egress="direct",
            checked_at=datetime(2026, 7, 13, 12, 0, 0),
        )

    def fetch_cars(self, filters):
        self.last_filters = filters
        if self.list_error:
            raise self.list_error
        return self.list_result

    def search_cars(self, filters):
        self.last_filters = filters
        if self.search_error:
            raise self.search_error
        return self.list_result

    def fetch_total_count(self, filters):
        self.last_filters = filters
        if self.count_error:
            raise self.count_error
        return self.count

    def get_car_detail(self, car_no):
        if self.detail_error:
            raise self.detail_error
        return None, PARSE_STATUS_NOT_FOUND

    def check_health(self, week_number=None):
        if self.health_error:
            raise self.health_error
        return self.health_probe

    def update_cookies(self, cookies):
        self.cookie_mutated = True


def make_client(service: StubService) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_ssancar_service] = lambda: service
    return TestClient(app)


@pytest.mark.parametrize(
    ("method", "path", "error", "expected_status", "expected_code"),
    [
        (
            "get",
            "/api/v1/ssancar/cars?week_number=2",
            SSANCARUpstreamAuthError(),
            502,
            "upstream_auth",
        ),
        (
            "post",
            "/api/v1/ssancar/search",
            SSANCARUpstreamInvalidResponseError(),
            502,
            "upstream_invalid_response",
        ),
        (
            "get",
            "/api/v1/ssancar/total-count?week_number=2",
            SSANCARUpstreamUnavailableError(),
            502,
            "upstream_unavailable",
        ),
        (
            "get",
            "/api/v1/ssancar/cars?week_number=2",
            SSANCARUpstreamTimeoutError(),
            504,
            "upstream_timeout",
        ),
    ],
)
def test_upstream_failures_have_structured_non_cacheable_errors(
    method,
    path,
    error,
    expected_status,
    expected_code,
):
    service = StubService()
    if "/search" in path:
        service.search_error = error
    elif "/total-count" in path:
        service.count_error = error
    else:
        service.list_error = error
    client = make_client(service)
    kwargs = {"json": {"weekNo": "2"}} if method == "post" else {}

    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == expected_status
    assert response.json() == {
        "detail": {
            "code": expected_code,
            "message": "SSANCAR is temporarily unavailable",
            "retryable": True,
        }
    }
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (SSANCARUpstreamAuthError(), 502, "upstream_auth"),
        (
            SSANCARUpstreamInvalidResponseError(),
            502,
            "upstream_invalid_response",
        ),
        (SSANCARUpstreamUnavailableError(), 502, "upstream_unavailable"),
        (SSANCARUpstreamTimeoutError(), 504, "upstream_timeout"),
    ],
)
def test_detail_uses_same_structured_upstream_error_mapping(
    error,
    expected_status,
    expected_code,
):
    service = StubService()
    service.detail_error = error
    response = make_client(service).get("/api/v1/ssancar/car/123")

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == expected_code
    assert response.json()["detail"]["retryable"] is True
    assert response.headers["cache-control"] == "no-store"


def test_successful_list_and_count_echo_the_normalized_week():
    service = StubService()
    client = make_client(service)

    list_response = client.get("/api/v1/ssancar/cars?week_number=2")
    count_response = client.get("/api/v1/ssancar/total-count?week_number=2")

    assert list_response.status_code == 200
    assert list_response.json()["week_number"] == "2"
    assert count_response.status_code == 200
    assert count_response.json()["total_count"] == 1010
    assert count_response.json()["week_number"] == "2"


def test_total_count_normalizes_invalid_legacy_week_before_service_call():
    service = StubService()
    client = make_client(service)

    with patch("app.routes.ssancar.resolve_ssancar_week", return_value="5"):
        response = client.get(
            "/api/v1/ssancar/total-count?week_number=4"
        )

    assert response.status_code == 200
    assert service.last_filters.weekNo == "5"
    assert response.json()["week_number"] == "5"


def test_compat_search_response_includes_selected_week():
    service = StubService()
    response = make_client(service).post(
        "/api/v1/ssancar/filters/ssancar/search",
        json={"week_number": 2, "page": 1, "page_size": 15},
    )

    assert response.status_code == 200
    assert response.json()["week_number"] == "2"


def test_valid_zero_count_health_probe_is_healthy():
    service = StubService()
    response = make_client(service).get(
        "/api/v1/ssancar/health?week_number=2"
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "SSANCAR upstream is healthy",
        "service": "SSANCAR Auction",
        "status": "healthy",
        "base_url": "https://www.ssancar.com",
        "week_number": "2",
        "upstream_count": 0,
        "egress": "direct",
        "checked_at": "2026-07-13T12:00:00",
    }


def test_exhausted_health_probe_returns_non_cacheable_503():
    service = StubService()
    service.health_error = SSANCARUpstreamUnavailableError()
    response = make_client(service).get(
        "/api/v1/ssancar/health?week_number=2"
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "upstream_unavailable",
        "message": "SSANCAR readiness probe failed",
        "retryable": True,
    }
    assert response.headers["cache-control"] == "no-store"


def test_update_cookies_is_gone_and_does_not_mutate_transport_state():
    service = StubService()
    response = make_client(service).post(
        "/api/v1/ssancar/update-cookies",
        json={"PHPSESSID": "must-not-be-used"},
    )

    assert response.status_code == 410
    assert response.json()["detail"] == {
        "code": "manual_cookie_updates_removed",
        "message": "Manual SSANCAR cookie updates are no longer supported",
        "retryable": False,
    }
    assert response.headers["cache-control"] == "no-store"
    assert service.cookie_mutated is False


def test_update_cookies_returns_tombstone_even_without_a_body():
    service = StubService()

    response = make_client(service).post(
        "/api/v1/ssancar/update-cookies",
    )

    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "manual_cookie_updates_removed"
    assert service.cookie_mutated is False
