"""Live acceptance for the Encar egress failover, against the deployed API.

tests/test_encar_proxy_routes.py proves the routing logic with a stubbed
transport. It cannot prove the one thing that took the catalog down on
2026-08-29: that api.encar.com's CloudFront edge accepts what the *deployed*
process sends, through whichever leg it ends up using. Only the live
internet can answer that, so this file is network-gated exactly like
tests/test_cors_live.py and never runs in a normal `pytest`:

    RUN_ENCAR_LIVE=1 python -m pytest tests/test_encar_live.py -q

Sanity gate: run it BEFORE the fix is deployed and confirm it fails (403 on
catalog/nav, 404 on readside and diagnostics). A live test that is green
before the fix is not testing anything. Optionally pin the expected commit:

    ENCAR_LIVE_EXPECTED_COMMIT=<sha> RUN_ENCAR_LIVE=1 python -m pytest tests/test_encar_live.py -q
"""

from __future__ import annotations

import os

import pytest
import requests


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_ENCAR_LIVE") != "1",
    reason="set RUN_ENCAR_LIVE=1 to exercise the deployed Encar proxy routes",
)

API_BASE = os.getenv("ENCAR_LIVE_API_BASE", "https://korean-auctions-1.onrender.com")
TIMEOUT = 45

CATALOG_QUERY = "(And.Hidden.N._.CarType.A._.SellType.일반.)"
DIAGNOSTICS_KEYS = {
    "commit",
    "egress_mode",
    "failover_enabled",
    "failover_armed",
    "proxy_pool_size",
    "breaker_open",
    "breaker_seconds_remaining",
    "breaker_trips",
    "cooldown_seconds",
    "last_direct_status",
    "last_proxy_status",
    "last_block_at",
    "caches",
}


def _get(path: str, **params: str) -> requests.Response:
    return requests.get(f"{API_BASE}{path}", params=params, timeout=TIMEOUT)


def _catalog() -> requests.Response:
    return _get("/api/catalog", count="true", q=CATALOG_QUERY, sr="|ModifiedDate|0|1")


def _describe(response: requests.Response) -> str:
    return f"HTTP {response.status_code}: {response.text.strip()[:160]!r}"


def test_catalog_returns_json_with_positive_count() -> None:
    response = _catalog()
    assert response.status_code == 200, _describe(response)
    body = response.json()
    assert body["Count"] > 0, body
    assert len(body["SearchResults"]) == 1, body


def test_nav_returns_facets() -> None:
    response = _get("/api/nav", q=CATALOG_QUERY, inav="|Metadata|Sort", count="true")
    assert response.status_code == 200, _describe(response)
    assert "iNav" in response.json()


def test_readside_vehicle_for_a_live_catalog_id() -> None:
    catalog = _catalog()
    assert catalog.status_code == 200, _describe(catalog)
    vehicle_id = catalog.json()["SearchResults"][0]["Id"]

    response = _get(f"/api/readside/vehicle/{vehicle_id}")
    assert response.status_code == 200, _describe(response)
    assert "vehicleId" in response.json()


def test_readside_rejects_non_numeric_id_live() -> None:
    response = _get("/api/readside/vehicle/not-a-vehicle-id")
    assert response.status_code == 400, _describe(response)
    assert response.json()["error"] == "invalid_vehicle_id"


def test_encar_diagnostics_is_reachable() -> None:
    response = _get("/api/v1/diagnostics/encar")
    assert response.status_code == 200, _describe(response)
    assert DIAGNOSTICS_KEYS <= set(response.json())


def test_deployed_commit_matches_expected() -> None:
    expected = os.getenv("ENCAR_LIVE_EXPECTED_COMMIT", "").strip()
    if not expected:
        pytest.skip("set ENCAR_LIVE_EXPECTED_COMMIT=<sha> to assert which commit is live")
    response = _get("/healthz/ready")
    commit = response.json().get("commit")
    assert commit, f"/healthz/ready reports no commit ({_describe(response)})"
    assert commit.startswith(expected), f"live commit {commit} is not {expected}"
