"""Public HTTP contract tests for KCar listing routes (no live network).

Regression context: ``GET /api/v1/kcar/cars`` used to answer *any* upstream
failure with HTTP 200 plus generated demo rows. An outage was therefore
indistinguishable from real inventory — the storefront rendered fabricated cars
with fixture image URLs, and the CDN cached the 200. These tests pin the
fail-closed contract so synthetic inventory can never reach a live listing again.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.models.kcar import KCarResponse
from app.parsers.kcar_parser import KCarParser
from app.routes import kcar as kcar_routes
from app.routes.kcar import router


REPO_ROOT = Path(__file__).resolve().parents[1]


class StubKCarService:
    """Records calls so a test can prove the demo generator was never reached."""

    def __init__(self, result: KCarResponse, *, username="u", password="p") -> None:
        self.result = result
        self.username = username
        self.password = password
        self.get_cars_params: list[dict] = []
        self.test_cars_calls = 0

    def get_cars(self, params):
        self.get_cars_params.append(params)
        return self.result

    def get_test_cars(self, count):
        self.test_cars_calls += 1
        raise AssertionError(
            "get_test_cars must never be reached from a live listing handler"
        )


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _install(monkeypatch, stub: StubKCarService) -> None:
    monkeypatch.setattr(kcar_routes, "kcar_service", stub)


def test_upstream_failure_returns_typed_error_not_demo_data(monkeypatch, client):
    stub = StubKCarService(
        KCarResponse(car_list=[], success=False, message="upstream exploded")
    )
    _install(monkeypatch, stub)

    response = client.get("/api/v1/kcar/cars", params={"page_size": 3})

    assert response.status_code == 502
    assert response.json() == {
        "detail": {
            "code": "upstream_unavailable",
            # The upstream message may carry internals, so it is logged, not returned.
            "message": "KCar provider is temporarily unavailable",
            "retryable": True,
        }
    }
    assert response.headers["cache-control"] == "no-store"
    # The regression lock: no synthetic substitution on the failure path.
    assert stub.test_cars_calls == 0


def test_missing_credentials_fail_closed_as_unconfigured(monkeypatch, client):
    stub = StubKCarService(
        KCarResponse(car_list=[], success=False, message="not authenticated"),
        username=None,
        password=None,
    )
    _install(monkeypatch, stub)

    response = client.get("/api/v1/kcar/cars", params={"page_size": 3})

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "provider_unconfigured"
    # Retrying a missing environment variable only adds latency, so the UI must
    # not offer a retry affordance for this code.
    assert detail["retryable"] is False
    assert stub.test_cars_calls == 0


def test_auth_failure_is_classified_as_upstream_auth(monkeypatch, client):
    stub = StubKCarService(
        KCarResponse(car_list=[], success=False, message="Ошибка авторизации KCar")
    )
    _install(monkeypatch, stub)

    response = client.get("/api/v1/kcar/cars", params={"page_size": 3})

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "upstream_auth"


def test_empty_lane_is_a_successful_empty_page(monkeypatch, client):
    """An auction that has ended is NOT an error — guards over-correcting."""
    stub = StubKCarService(
        KCarResponse(car_list=[], success=True, message="торги завершены")
    )
    _install(monkeypatch, stub)

    response = client.get("/api/v1/kcar/cars", params={"page_size": 3})

    assert response.status_code == 200
    assert response.json()["CAR_LIST"] == []


def test_lane_type_is_forwarded_to_the_service(monkeypatch, client):
    stub = StubKCarService(KCarResponse(car_list=[], success=True, message="ok"))
    _install(monkeypatch, stub)

    client.get("/api/v1/kcar/cars", params={"page_size": 3, "lane_type": "A"})

    # Without this the service fans out across lanes A and B, so the Tuesday
    # Sejong card could preview Thursday's Osan lots.
    assert stub.get_cars_params[0]["lane_type"] == "A"


def test_generated_demo_rows_contain_no_unformatted_specs():
    """The demo templates used "KCA2025{:04d}" while the formatter tested for
    the literal "{}", so every generated CAR_ID leaked the raw format spec."""
    result = KCarParser().generate_test_data(6)

    assert result.car_list
    for car in result.car_list:
        for value in car.model_dump().values():
            if isinstance(value, str):
                assert not re.search(r"\{[^{}]*\}", value), (
                    f"unformatted template leaked into demo data: {value!r}"
                )


def test_synthetic_generator_is_unreachable_from_live_handlers():
    """AST guard, in the style of tests/test_release_security.py.

    Only the explicitly-named demo endpoints may reach the synthetic generator.
    """
    tree = ast.parse((REPO_ROOT / "app/routes/kcar.py").read_text(encoding="utf-8"))
    allowed = {"get_kcar_test_cars", "get_kcar_demo_cars", "get_test_cars_endpoint"}
    synthetic = {"get_test_cars", "generate_test_data"}

    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name in allowed:
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Attribute) and inner.attr in synthetic:
                offenders.append(f"{node.name}() at line {inner.lineno}")

    assert not offenders, (
        "live KCar handlers must fail closed, but these reach the synthetic "
        f"generator: {offenders}"
    )
