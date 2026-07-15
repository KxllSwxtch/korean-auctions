"""Public HTTP contract tests for DB Auto Glovis routes (no live network)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.models.glovis import (
    GlovisAuctionsResponse,
    GlovisCarDetailResponse,
    GlovisCarsResponse,
    GlovisDetailHealthResponse,
    GlovisFilterItemsResponse,
    GlovisFilterOptionsResponse,
    GlovisHealthResponse,
    GlovisSearchForm,
)
from app.routes import glovis
from app.routes.glovis import get_glovis_service, router
from app.services.glovis_service import GlovisCarUnavailableError
from app.services.glovis_transport import (
    GlovisProxyUnavailableError,
    GlovisUpstreamAuthError,
    GlovisUpstreamInvalidResponseError,
    GlovisUpstreamTimeoutError,
    GlovisUpstreamUnavailableError,
)
from glovis_fixtures import GN_RAW, valid_detail
import main


CHECKED_AT = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


class StubGlovisService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.error: Exception | None = None
        self.clear_calls = 0
        self.close_calls = 0

    def _record(self, operation: str, value: object = None) -> None:
        self.calls.append((operation, value))
        if self.error is not None:
            raise self.error

    def get_auctions(self) -> GlovisAuctionsResponse:
        self._record("auctions")
        return GlovisAuctionsResponse(auctions=[])

    def get_cars(self, query) -> GlovisCarsResponse:
        self._record("cars", query)
        return GlovisCarsResponse(
            total=0,
            items=[],
            page=query.page,
            page_size=query.page_size,
            atn=query.atn,
            acc=query.acc,
        )

    def get_brands(self, *, atn: str, acc: str) -> GlovisFilterItemsResponse:
        self._record("brands", {"atn": atn, "acc": acc})
        return GlovisFilterItemsResponse(items=[])

    def get_models(
        self,
        *,
        brand: str,
        atn: str,
        acc: str,
    ) -> GlovisFilterItemsResponse:
        self._record(
            "models",
            {"brand": brand, "atn": atn, "acc": acc},
        )
        return GlovisFilterItemsResponse(items=[])

    def get_submodels(
        self,
        *,
        brand: str,
        model: str,
        atn: str,
        acc: str,
    ) -> GlovisFilterItemsResponse:
        self._record(
            "submodels",
            {"brand": brand, "model": model, "atn": atn, "acc": acc},
        )
        return GlovisFilterItemsResponse(items=[])

    def get_filter_options(
        self,
        *,
        atn: str,
        acc: str,
    ) -> GlovisFilterOptionsResponse:
        self._record("filter_options", {"atn": atn, "acc": acc})
        return GlovisFilterOptionsResponse(filters=GlovisSearchForm())

    def get_car_detail(
        self,
        *,
        gn: str,
        rc: str,
        acc: str,
        atn: str,
    ) -> GlovisCarDetailResponse:
        self._record(
            "car_detail",
            {"gn": gn, "rc": rc, "acc": acc, "atn": atn},
        )
        return GlovisCarDetailResponse(data=valid_detail())

    def check_health(self) -> GlovisHealthResponse:
        self._record("health")
        return GlovisHealthResponse(
            auction_count=0,
            list_count=0,
            egress="kr-primary",
            checked_at=CHECKED_AT,
        )

    def check_detail_health(self) -> GlovisDetailHealthResponse:
        self._record("detail_health")
        return GlovisDetailHealthResponse(
            auction_count=0,
            list_count=0,
            egress="kr-primary",
            checked_at=CHECKED_AT,
        )

    def get_cache_stats(self) -> dict[str, int]:
        return {
            "size": 7,
            "max_entries": 512,
            "hits": 3,
            "misses": 2,
            "evictions": 0,
        }

    def clear_cache(self) -> None:
        self.clear_calls += 1

    def close(self) -> None:
        self.close_calls += 1


def make_client(service: StubGlovisService) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_glovis_service] = lambda: service
    return TestClient(app)


def assert_stable_error(
    response,
    *,
    status: int,
    code: str,
    retryable: bool,
) -> None:
    assert response.status_code == status
    assert response.json()["detail"] == {
        "code": code,
        "message": response.json()["detail"]["message"],
        "retryable": retryable,
    }
    assert response.json()["detail"]["message"]
    assert response.headers["cache-control"] == "no-store"


def test_cars_accepts_every_filter_and_preserves_repeated_values():
    service = StubGlovisService()
    response = make_client(service).get(
        "/api/v1/glovis/cars",
        params=[
            ("atn", "1102"),
            ("acc", "20"),
            ("page", "2"),
            ("page_size", "60"),
            ("brand", "1"),
            ("model", "26"),
            ("submodel", "1568"),
            ("year_from", "2015"),
            ("year_to", "2020"),
            ("mileage_from", "1000"),
            ("mileage_to", "200000"),
            ("price_from", "1000000"),
            ("price_to", "3000000"),
            ("transmission", "A/T"),
            ("fuel_type", "Gasoline"),
            ("color", "Gray"),
            ("options", "navigation"),
            ("options", "sunroof"),
            ("insurance_damage", "none"),
            ("usage_history", "rental"),
            ("usage_history", "commercial"),
            ("accident_history", "none"),
            ("room", "Yangsan"),
            ("lane", "A"),
            ("bid_status", "open"),
            ("sort_order", "02"),
        ],
    )

    assert response.status_code == 200
    query = service.calls[0][1]
    assert query.page == 2
    assert query.page_size == 60
    assert query.options == ["navigation", "sunroof"]
    assert query.usage_history == ["rental", "commercial"]
    assert query.submodel == "1568"
    assert query.sort_order == "02"
    assert response.json()["has_next_page"] is False


@pytest.mark.parametrize(
    "params",
    [
        {"atn": "1102", "acc": "20", "model": "26"},
        {"atn": "1102", "acc": "20", "brand": "1", "submodel": "1568"},
        {"atn": "1102", "acc": "20", "year_from": 2021, "year_to": 2020},
        {"atn": "1102", "acc": "20", "mileage_from": 2, "mileage_to": 1},
        {"atn": "1102", "acc": "20", "price_from": 2, "price_to": 1},
    ],
)
def test_cars_rejects_dependent_and_range_violations_before_service(params):
    service = StubGlovisService()
    response = make_client(service).get("/api/v1/glovis/cars", params=params)

    assert_stable_error(
        response,
        status=422,
        code="invalid_identifier",
        retryable=False,
    )
    assert service.calls == []


def test_page_size_above_contract_limit_is_a_stable_422():
    service = StubGlovisService()
    response = make_client(service).get(
        "/api/v1/glovis/cars?atn=1102&acc=20&page_size=61"
    )

    assert_stable_error(
        response,
        status=422,
        code="invalid_request",
        retryable=False,
    )
    assert service.calls == []


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/v1/glovis/cars"),
        ("delete", "/api/v1/glovis/health/detail"),
    ],
)
def test_known_glovis_paths_reject_unsupported_methods_with_stable_405(
    method,
    path,
):
    service = StubGlovisService()
    response = getattr(make_client(service), method)(path)

    assert response.status_code == 405
    assert response.json() == {
        "detail": {
            "code": "method_not_allowed",
            "message": "Method not allowed",
            "retryable": False,
        }
    }
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["allow"] == "GET"
    assert service.calls == []


def test_method_handling_does_not_claim_unknown_glovis_paths():
    response = make_client(StubGlovisService()).post(
        "/api/v1/glovis/not-a-route"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_glovis_method_handling_does_not_change_other_application_routes():
    response = TestClient(main.app).post("/health")

    assert response.status_code == 405
    assert response.json() == {"detail": "Method Not Allowed"}
    assert "cache-control" not in response.headers


def test_glovis_openapi_still_exposes_only_get_operations():
    response = make_client(StubGlovisService()).get("/openapi.json")

    assert response.status_code == 200
    assert set(response.json()["paths"]["/api/v1/glovis/cars"]) == {"get"}
    assert set(response.json()["paths"]["/api/v1/glovis/health/detail"]) == {
        "get"
    }


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/glovis/cars?atn=abc&acc=20",
        "/api/v1/glovis/brands?atn=1102&acc=１２",
        "/api/v1/glovis/models?brand=one&atn=1102&acc=20",
        "/api/v1/glovis/submodels?brand=1&model=bad&atn=1102&acc=20",
        "/api/v1/glovis/filters/options?atn=1102&acc=20%26other%3D1",
        "/api/v1/glovis/car-detail?gn=not-base64&rc=3100&acc=20&atn=1102",
    ],
)
def test_invalid_identifiers_are_rejected_before_service_work(path):
    service = StubGlovisService()
    response = make_client(service).get(path)

    assert_stable_error(
        response,
        status=422,
        code="invalid_identifier",
        retryable=False,
    )
    assert service.calls == []


@pytest.mark.parametrize(
    ("path", "operation"),
    [
        ("/api/v1/glovis/auctions", "auctions"),
        ("/api/v1/glovis/brands?atn=1102&acc=20", "brands"),
        ("/api/v1/glovis/models?brand=1&atn=1102&acc=20", "models"),
        (
            "/api/v1/glovis/submodels?brand=1&model=26&atn=1102&acc=20",
            "submodels",
        ),
        ("/api/v1/glovis/filters/options?atn=1102&acc=20", "filter_options"),
    ],
)
def test_empty_healthy_catalog_and_metadata_responses_remain_200(path, operation):
    service = StubGlovisService()
    response = make_client(service).get(path)

    assert response.status_code == 200
    assert service.calls[0][0] == operation


def test_valid_car_detail_identity_is_validated_and_delegated():
    service = StubGlovisService()
    response = make_client(service).get(
        "/api/v1/glovis/car-detail",
        params={"gn": GN_RAW, "rc": "3100", "acc": "20", "atn": "1102"},
    )

    assert response.status_code == 200
    assert service.calls == [
        (
            "car_detail",
            {"gn": GN_RAW, "rc": "3100", "acc": "20", "atn": "1102"},
        )
    ]
    assert response.json()["data"]["main"]["gn"] == GN_RAW


def test_placeholder_detail_is_a_non_retryable_non_cacheable_404():
    service = StubGlovisService()
    service.error = GlovisCarUnavailableError()
    response = make_client(service).get(
        "/api/v1/glovis/car-detail",
        params={"gn": GN_RAW, "rc": "3100", "acc": "20", "atn": "1102"},
    )

    assert_stable_error(
        response,
        status=404,
        code="car_unavailable",
        retryable=False,
    )
    assert GN_RAW not in response.text


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (GlovisProxyUnavailableError(), 503, "proxy_unavailable"),
        (GlovisUpstreamTimeoutError(), 504, "upstream_timeout"),
        (GlovisUpstreamAuthError(), 502, "upstream_auth"),
        (
            GlovisUpstreamInvalidResponseError(),
            502,
            "upstream_invalid_response",
        ),
        (GlovisUpstreamUnavailableError(), 502, "upstream_unavailable"),
    ],
)
def test_structured_upstream_errors_are_never_cacheable(error, status, code):
    service = StubGlovisService()
    service.error = error
    response = make_client(service).get(
        "/api/v1/glovis/cars?atn=1102&acc=20"
    )

    assert response.status_code == status
    assert response.json() == {
        "detail": {
            "code": code,
            "message": "Glovis provider is temporarily unavailable",
            "retryable": True,
        }
    }
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["health", "health/detail"])
def test_empty_health_probes_remain_healthy(path):
    service = StubGlovisService()
    response = make_client(service).get(f"/api/v1/glovis/{path}")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["auction_count"] == 0
    assert response.json()["list_count"] == 0


@pytest.mark.parametrize("path", ["health", "health/detail"])
def test_health_failures_use_the_shared_structured_error_contract(path):
    service = StubGlovisService()
    service.error = GlovisUpstreamAuthError()
    response = make_client(service).get(f"/api/v1/glovis/{path}")

    assert_stable_error(
        response,
        status=502,
        code="upstream_auth",
        retryable=True,
    )


def test_main_registers_every_canonical_glovis_route():
    paths = {route.path for route in main.app.routes}

    assert {
        "/api/v1/glovis/auctions",
        "/api/v1/glovis/cars",
        "/api/v1/glovis/brands",
        "/api/v1/glovis/models",
        "/api/v1/glovis/submodels",
        "/api/v1/glovis/filters/options",
        "/api/v1/glovis/car-detail",
        "/api/v1/glovis/health",
        "/api/v1/glovis/health/detail",
    }.issubset(paths)


def test_shared_cache_endpoints_include_and_clear_glovis(monkeypatch):
    service = StubGlovisService()
    monkeypatch.setattr(glovis, "glovis_service", service)
    client = TestClient(main.app)

    stats_response = client.get("/api/v1/cache/stats")
    clear_response = client.post("/api/v1/cache/clear")

    assert stats_response.status_code == 200
    assert service.get_cache_stats() in stats_response.json()["services"]
    assert clear_response.status_code == 200
    assert "Glovis" in clear_response.json()["cleared"]
    assert service.clear_calls == 1


def test_lifespan_initializes_glovis_before_scheduler_and_closes_after_stop(
    monkeypatch,
):
    service = StubGlovisService()
    events: list[str] = []

    def get_service():
        events.append("glovis.init")
        return service

    async def start_scheduler():
        events.append("scheduler.start")

    async def stop_scheduler():
        events.append("scheduler.stop")

    def close():
        events.append("glovis.close")
        service.close_calls += 1

    monkeypatch.setattr(glovis, "get_glovis_service", get_service)
    monkeypatch.setattr(main, "start_scheduler", start_scheduler)
    monkeypatch.setattr(main, "stop_scheduler", stop_scheduler)
    monkeypatch.setattr(service, "close", close)

    async def exercise_lifespan() -> None:
        async with main.lifespan(main.app):
            events.append("app.running")

    asyncio.run(exercise_lifespan())

    assert events == [
        "glovis.init",
        "scheduler.start",
        "app.running",
        "scheduler.stop",
        "glovis.close",
    ]
    assert service.close_calls == 1
