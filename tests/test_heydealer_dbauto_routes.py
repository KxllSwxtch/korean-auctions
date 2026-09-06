"""Route tests: envelope shapes, status mapping, and path-ordering.

The response envelopes are load-bearing. `autobazaapp` nests these flat rows into
`detail{}`/`auction{}` itself, so a renamed key here is an empty card there rather
than a type error, and the Next proxy forwards the whole prefix without validating
anything. These tests pin the shapes the frontend transforms actually read.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import heydealer_dbauto
from app.services.dbauto_transport import (
    DbautoGeoBlockedError,
    DbautoProxyUnavailableError,
    DbautoUpstreamTimeoutError,
    DbautoUpstreamUnavailableError,
)

CAR = {
    "id": "lD6m16Jn",
    "hash_id": "lD6m16Jn",
    "lot_number": "lD6m16Jn",
    "title": "The New Ray Prestige",
    "main_image": "https://img.example/a.jpg",
    "main_image_url": "https://img.example/a.jpg",
    "is_inspected": True,
    "is_pre_inspected": True,
    "tags": ["No accident"],
    "desired_price": 1057,
    "price": 1057,
    "current_price": 1057,
}

DIAGRAM = {
    "views": [{"type": "top", "image_url": "u", "image_width": 200, "accident_repairs": []}],
    "type": "top",
    "image_url": "u",
    "image_width": 200,
    "accident_repairs": [],
    "total_damages": 0,
    "damage_summary": {"exchange": 0, "weld": 0, "painted": 0, "none": 1},
}


class StubService:
    def __init__(self):
        self.raise_on_detail: Exception | None = None
        self.raise_on_list: Exception | None = None
        self.healthy = True
        self.seen_lang: list[str] = []
        self.known = {"lD6m16Jn"}

    async def list_cars(self, *, page=1, page_size=20, order=None, filters=None, lang="en"):
        self.seen_lang.append(lang)
        if self.raise_on_list:
            raise self.raise_on_list
        return {"cars": [CAR], "total_count": 137, "page": page, "page_size": page_size}

    async def get_car(self, hash_id, *, lang="en"):
        self.seen_lang.append(lang)
        if self.raise_on_detail:
            raise self.raise_on_detail
        return dict(CAR) if hash_id in self.known else None

    async def get_diagram(self, hash_id, *, lang="en"):
        if self.raise_on_detail:
            raise self.raise_on_detail
        return dict(DIAGRAM) if hash_id in self.known else None

    async def get_brands(self, *, lang="en", filters=None):
        return [{"hash_id": "b1", "value": "b1", "name": "Hyundai", "label": "Hyundai", "count": 5}]

    async def get_models(self, *, brand, model_group=None, model=None, lang="en", filters=None):
        if not brand:
            raise ValueError("brand is required")
        return [{"hash_id": "m1", "value": "m1", "name": "Grandeur", "label": "Grandeur", "count": 2}]

    async def get_section(self, section, *, lang="en", filters=None, deadline_at=None):
        return [{"hash_id": "gasoline", "value": "gasoline", "name": "Petrol", "label": "Petrol", "count": 9}]

    async def get_sections(self, sections=(), *, lang="en", filters=None, budget_seconds=25.0):
        return {name: [{"hash_id": "x", "value": "x", "name": "X", "label": "X", "count": 1}] for name in sections}

    async def health(self):
        return (
            {"status": "ok", "source": "dbauto", "total_cars": 137, "egress": ["jp-primary"]}
            if self.healthy
            else {"status": "error", "source": "dbauto", "code": "egress_geo_blocked", "egress": ["jp-primary"]}
        )

    def feed_recently_healthy(self, within_seconds=120.0):
        return self.healthy


@pytest.fixture
def stub(monkeypatch):
    service = StubService()
    monkeypatch.setattr(heydealer_dbauto, "get_service", lambda: service)
    return service


@pytest.fixture
def client(stub):
    app = FastAPI()
    app.include_router(heydealer_dbauto.router, prefix="/api/v1")
    app.include_router(heydealer_dbauto.filters_router, prefix="/api/v1/heydealer/filters")
    return TestClient(app)


B = "/api/v1/heydealer"


# --------------------------------------------------------------------------- #
# Envelopes
# --------------------------------------------------------------------------- #


def test_list_envelope_matches_the_frontend_contract(client):
    body = client.get(f"{B}/cars?page=1").json()
    assert body["success"] is True
    assert body["data"]["cars"][0]["hash_id"] == "lD6m16Jn"
    assert body["data"]["total_count"] == 137
    assert body["data"]["page"] == 1
    # Mirrored at the top level; both are read in different places.
    assert body["total_count"] == 137
    assert body["current_page"] == 1
    assert body["pagination"] == {
        "current_page": 1,
        "total_count": 137,
        "page_size": 20,
        "has_next": True,
    }


def test_has_next_is_false_on_the_last_page(client):
    body = client.get(f"{B}/cars?page=7&page_size=20").json()
    assert body["pagination"]["has_next"] is False


def test_filtered_list_uses_the_same_envelope(client):
    body = client.get(f"{B}/cars/filtered?page=1&fuel=electric,hybrid").json()
    assert body["success"] is True
    assert body["data"]["cars"][0]["hash_id"] == "lD6m16Jn"


def test_filtered_is_not_swallowed_by_the_car_id_route(client):
    """Declaration order matters: `/cars/{id}` would otherwise match "filtered".
    Four routes in the legacy module were unreachable for exactly this reason."""
    assert client.get(f"{B}/cars/filtered").json()["data"]["cars"]


def test_detail_envelope_carries_the_tech_sheet_flags(client):
    body = client.get(f"{B}/cars/lD6m16Jn").json()
    assert body["success"] is True
    assert body["data"]["hash_id"] == "lD6m16Jn"
    assert body["data"]["accident_repairs_available"] is True
    assert body["data"]["accident_repairs_data"]["views"]
    assert body["car_request_success"] is True
    assert body["accident_repairs_request_success"] is True


def test_diagram_envelope_exposes_views_and_legacy_keys(client):
    body = client.get(f"{B}/cars/lD6m16Jn/accident-diagram").json()
    assert body["success"] is True
    assert body["data"]["views"][0]["type"] == "top"
    # Legacy single-view keys stay populated so an older client keeps rendering.
    assert body["data"]["image_url"] == "u"
    assert body["data"]["damage_summary"]["none"] == 1


def test_brands_envelope(client):
    body = client.get(f"{B}/filters/brands").json()
    assert body["success"] is True
    assert body["data"][0]["hash_id"] == "b1"


def test_brand_models_envelope_has_both_aliases(client):
    """The taxonomy hook reads `data.model_groups`; older code read `data.models`."""
    body = client.get(f"{B}/filters/brands/b1/models").json()
    assert body["data"]["model_groups"][0]["name"] == "Grandeur"
    assert body["data"]["models"] == body["data"]["model_groups"]


def test_generations_envelope(client):
    body = client.get(f"{B}/filters/model-groups/g1/generations?brand=b1").json()
    assert body["data"]["models"][0]["hash_id"] == "m1"


def test_configurations_envelope(client):
    body = client.get(f"{B}/filters/models/m1/configurations?brand=b1&model_group=g1").json()
    assert body["data"]["grades"][0]["hash_id"] == "m1"


def test_filters_reports_which_groups_are_missing(client):
    body = client.get(f"{B}/filters").json()
    assert body["success"] is True
    assert body["degraded"] is False
    assert body["stale_groups"] == []
    assert body["data"]["brands"]
    assert body["data"]["years"]["min"] == 1990


def test_stats_and_status(client):
    stats = client.get(f"{B}/stats").json()
    assert stats["data"]["total_cars"] == 137
    status = client.get(f"{B}/status").json()
    assert status["status"] == "online"
    assert status["cars_count"] == 137


def test_health_is_200_even_when_upstream_is_broken(client, stub):
    """A polling frontend must not render a hard error on a blip."""
    stub.healthy = False
    response = client.get(f"{B}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert response.json()["code"] == "egress_geo_blocked"


# --------------------------------------------------------------------------- #
# Language
# --------------------------------------------------------------------------- #


def test_explicit_lang_wins(client, stub):
    client.get(f"{B}/cars?lang=es", headers={"Accept-Language": "ru"})
    assert stub.seen_lang[-1] == "es"


def test_accept_language_is_used_when_no_param_is_given(client, stub):
    client.get(f"{B}/cars", headers={"Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"})
    assert stub.seen_lang[-1] == "ru"


def test_an_unsupported_language_falls_back_to_english(client, stub):
    client.get(f"{B}/cars", headers={"Accept-Language": "de-DE,de;q=0.9"})
    assert stub.seen_lang[-1] == "en"


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


def test_a_malformed_id_is_a_404_without_touching_upstream(client):
    response = client.get(f"{B}/cars/nope")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "car_unavailable"


def test_an_unknown_id_is_404_while_the_feed_is_healthy(client, stub):
    """dbauto has no 404 -- it answers 500 for a lot it does not have. With the
    catalog answering, that means the lot is gone, not that dbauto is down."""
    stub.raise_on_detail = DbautoUpstreamUnavailableError(status_code=500)
    response = client.get(f"{B}/cars/QrqO9Nen")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "car_unavailable"


def test_the_same_failure_is_502_when_the_feed_is_down(client, stub):
    stub.healthy = False
    stub.raise_on_detail = DbautoUpstreamUnavailableError(status_code=500)
    response = client.get(f"{B}/cars/QrqO9Nen")
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "upstream_unavailable"


def test_a_timeout_is_never_mistaken_for_a_missing_car(client, stub):
    stub.raise_on_detail = DbautoUpstreamTimeoutError()
    response = client.get(f"{B}/cars/QrqO9Nen")
    assert response.status_code == 504


@pytest.mark.parametrize(
    "error,status",
    [
        (DbautoUpstreamUnavailableError(), 502),
        (DbautoUpstreamTimeoutError(), 504),
        (DbautoProxyUnavailableError(), 503),
        (DbautoGeoBlockedError(), 503),
    ],
)
def test_upstream_errors_map_to_stable_codes(client, stub, error, status):
    stub.raise_on_list = error
    response = client.get(f"{B}/cars")
    assert response.status_code == status
    detail = response.json()["detail"]
    assert detail["code"] == error.code
    assert "retryable" in detail


def test_error_bodies_never_echo_upstream_text(client, stub):
    """A requests/proxy exception string embeds http://user:pass@host, and the
    legacy routes returned str(e) straight to unauthenticated callers."""
    stub.raise_on_list = DbautoUpstreamUnavailableError()
    stub.raise_on_list.args = ("http://user:hunter2@proxy.example.com:2312 failed",)
    body = client.get(f"{B}/cars").text
    assert "hunter2" not in body
    assert "proxy.example.com" not in body


def test_errors_are_not_cached_by_the_edge(client, stub):
    stub.raise_on_list = DbautoUpstreamUnavailableError()
    assert client.get(f"{B}/cars").headers["cache-control"] == "no-store"


def test_the_cascade_refuses_to_guess_a_brand(client):
    """Without a brand dbauto returns the whole tree, which would quietly fill a
    Model dropdown with every model of every make."""
    for url in (
        f"{B}/filters/model-groups/g1/generations",
        f"{B}/filters/models/m1/configurations",
    ):
        response = client.get(url)
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "brand_required"


def test_an_unknown_facet_section_is_404(client):
    assert client.get(f"{B}/filters/sections/nonsense").status_code == 404


def test_a_known_facet_section_is_served(client):
    body = client.get(f"{B}/filters/sections/fuel").json()
    assert body["data"][0]["hash_id"] == "gasoline"
