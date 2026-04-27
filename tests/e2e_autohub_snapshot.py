"""
E2E tests for the Autohub read path through FastAPI's full HTTP stack.

Exercises:
    1. Health endpoint
    2. /snapshot/status endpoint (live + snapshot mode + disabled)
    3. /cars listing (snapshot mode, zero outbound)
    4. /search with filters (snapshot mode, zero outbound)
    5. /car-detail/{id} (snapshot mode, zero outbound)
    6. /brands (snapshot mode, zero outbound)
    7. Snapshot-unavailable scenario (snapshot enabled but no DB content)
    8. Live-mode bypass (snapshot disabled → live path used)
    9. /snapshot/run admin auth + concurrent-lock semantics

Run:  source venv/bin/activate && python tests/e2e_autohub_snapshot.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Test environment must be set BEFORE importing the FastAPI app, since the
# AutohubService instantiates at module load and reads settings.
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

E2E_DB = "/tmp/e2e_autohub_snapshot.db"
E2E_EMPTY_DB = "/tmp/e2e_autohub_snapshot_empty.db"
E2E_LOCK = "/tmp/e2e_autohub_snapshot.run.lock"
E2E_EMPTY_LOCK = "/tmp/e2e_autohub_snapshot_empty.run.lock"

# Cleanup any leftovers from previous runs
for p in (
    E2E_DB, E2E_DB + "-wal", E2E_DB + "-shm",
    E2E_EMPTY_DB, E2E_EMPTY_DB + "-wal", E2E_EMPTY_DB + "-shm",
    E2E_LOCK, E2E_EMPTY_LOCK,
):
    if os.path.exists(p):
        os.unlink(p)

os.environ["AUTOHUB_SNAPSHOT_ENABLED"] = "true"
os.environ["AUTOHUB_SNAPSHOT_DAYS"] = "0,1,2,3,4,5,6"  # all days for tests
os.environ["AUTOHUB_SNAPSHOT_DB_PATH"] = E2E_DB
os.environ["AUTOHUB_SNAPSHOT_ADMIN_TOKEN"] = "e2e-admin-token-secret"
os.environ["AUTOHUB_SNAPSHOT_TIMEZONE"] = "Asia/Seoul"

# Now import — settings will be picked up from env.
from fastapi.testclient import TestClient

# Pre-import & patch _authenticate so the service singleton's __init__ doesn't
# hit Autohub during test bootstrap. Using a fake-valid JWT trips _is_token_valid
# (proper JWT format with future exp). Easier: patch _authenticate.
import app.services.autohub_service as svc_mod

_orig_authenticate = svc_mod.AutohubService._authenticate
svc_mod.AutohubService._authenticate = lambda self: True
svc_mod.AutohubService._is_token_valid = lambda self: True

from main import app  # noqa: E402
import app.services.autohub_snapshot_job as job_mod  # noqa: E402
from app.core.config import get_settings  # noqa: E402


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

# Track passed/failed results so we can summarise at the end and exit with
# a non-zero code on any failure.
results: list[tuple[str, bool, str]] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    """Append a test result. Print live progress."""
    status = "PASS" if condition else "FAIL"
    line = f"  [{status}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    results.append((label, condition, detail))


def header(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def reset_caches(db_path: str) -> None:
    """Reset module-level caches between scenarios (changing DBs)."""
    os.environ["AUTOHUB_SNAPSHOT_DB_PATH"] = db_path
    get_settings.cache_clear()
    job_mod._repo_singleton = None
    if hasattr(svc_mod.autohub_service, "_snap_src_cache"):
        delattr(svc_mod.autohub_service, "_snap_src_cache")


def fake_listing_page(params):
    base = (params.page - 1) * 10
    return {
        "code": "1",
        "data": {
            "totalPages": 2,
            "totalCount": 20,
            "list": [
                {
                    "carId": f"GC{base + i:04d}",
                    "entryNo": str(base + i + 100),
                    "entryId": f"E{base + i:04d}",
                    "carNm": "현대 소나타",
                    "carNmEn": f"Sonata {2020 + (base + i) % 5}",
                    "carYear": 2020 + (base + i) % 5,
                    "mileage": 10000 + (base + i) * 1000,
                    "fuelCode": "01" if (base + i) % 2 else "02",
                    "startAmt": 1000 + (base + i) * 50,
                    "hopeAmt": 1500 + (base + i) * 50,
                    "perfId": f"IP{base + i:04d}",
                    "mainFileUrl": f"img_{base + i}",
                    "aucDate": "2026-04-29",
                    "aucLaneCode": "A",
                    "soh": 90.0,
                    "inspGrade": "A",
                }
                for i in range(10) if params.page <= 2
            ],
        },
    }


def fake_brands_response():
    return {
        "code": "1",
        "data": [
            {
                "carOrigin": "KR",
                "brandList": [
                    {"brandId": "B1", "brandNm": "현대", "brandNmEn": "Hyundai",
                     "brandCnt": 10, "modelList": []}
                ],
            }
        ],
    }


def fake_detail_bundle(car_id, perf_id):
    return {
        "detail": {
            "vin": f"VIN_{car_id}",
            "carYear": 2024,
            "carNmEn": f"Test Car {car_id}",
            "carNm": "테스트",
            "carNo": "01가1234",
            "mileage": 50000,
            "displacement": 2000,
        },
        "inspection": None,
        "diagram": None,
        "legend": None,
        "perf_frame": None,
    }


# ---------------------------------------------------------------------------
# Bootstrap: build a populated snapshot DB
# ---------------------------------------------------------------------------

header("Bootstrap: build populated snapshot DB via mocked snapshot job")
reset_caches(E2E_DB)

with patch.object(svc_mod.autohub_service, "fetch_listing_page_raw", side_effect=fake_listing_page), \
     patch.object(svc_mod.autohub_service, "fetch_brands_raw", side_effect=fake_brands_response), \
     patch.object(svc_mod.autohub_service, "fetch_car_detail_raw", side_effect=fake_detail_bundle):
    summary = asyncio.run(job_mod.run_snapshot_job(triggered_by="e2e_bootstrap"))

check("bootstrap snapshot job completed", summary.get("car_count") == 20,
      f"car_count={summary.get('car_count')}")


# ---------------------------------------------------------------------------
# TestClient — wrapping the app, no lifespan (we don't need the scheduler)
# ---------------------------------------------------------------------------

# IMPORTANT: do NOT use `with TestClient(app)` because that triggers the
# lifespan handler which starts the APScheduler — we don't want background
# warming jobs spawning during tests.
client = TestClient(app)


# ---------------------------------------------------------------------------
# Scenario 1: Health endpoint
# ---------------------------------------------------------------------------

header("Scenario 1: Health endpoint sanity")
r = client.get("/health")
check("GET /health returns 200", r.status_code == 200,
      f"status={r.status_code}")


# ---------------------------------------------------------------------------
# Scenario 2: /snapshot/status with snapshot mode active
# ---------------------------------------------------------------------------

header("Scenario 2: /snapshot/status — mode reflects env + active snapshot metadata")
r = client.get("/api/v1/autohub/snapshot/status")
check("GET /snapshot/status returns 200", r.status_code == 200,
      f"status={r.status_code}, body={r.text[:200]}")
data = r.json() if r.status_code == 200 else {}
check("snapshot_enabled=true", data.get("snapshot_enabled") is True)
check("mode_today=snapshot", data.get("mode_today") == "snapshot")
check("active_snapshot has 20 cars", (data.get("active_snapshot") or {}).get("car_count") == 20)
check("active_snapshot has age_hours", isinstance((data.get("active_snapshot") or {}).get("age_hours"), (int, float)))


# ---------------------------------------------------------------------------
# Scenario 3-6: Read endpoints in snapshot mode — verify cache_mode + zero outbound
# ---------------------------------------------------------------------------

header("Scenario 3-6: Read endpoints in snapshot mode (must NOT call Autohub)")

outbound_calls = {"count": 0}
def must_not_call_autohub(*args, **kwargs):
    outbound_calls["count"] += 1
    raise AssertionError("snapshot mode hit live Autohub — defeats the purpose")

with patch.object(svc_mod.autohub_service, "_api_get", side_effect=must_not_call_autohub), \
     patch.object(svc_mod.autohub_service, "_api_post", side_effect=must_not_call_autohub), \
     patch.object(svc_mod.autohub_service, "_fetch_car_page", side_effect=must_not_call_autohub):

    # Scenario 3: GET /cars (backward-compat listing)
    r = client.get("/api/v1/autohub/cars?page=1&page_size=10")
    body = r.json() if r.status_code == 200 else {}
    check("GET /cars returns 200", r.status_code == 200, f"status={r.status_code}")
    check("/cars cache_mode='snapshot'", body.get("cache_mode") == "snapshot")
    check("/cars total_count=20", body.get("total_count") == 20)
    check("/cars data has 10 cars (page_size)", len(body.get("data", [])) == 10)
    check("/cars first car has carId", bool(body.get("data", [{}])[0].get("car_id") if body.get("data") else False))

    # Scenario 4: POST /search with filters
    payload = {
        "page": 1,
        "page_size": 20,
        "fuel_type": "01",  # gasoline
        "year_from": 2022,
        "year_to": 2024,
    }
    r = client.post("/api/v1/autohub/search", json=payload)
    body = r.json() if r.status_code == 200 else {}
    check("POST /search returns 200", r.status_code == 200, f"status={r.status_code}")
    check("/search cache_mode='snapshot'", body.get("cache_mode") == "snapshot")
    # Filter: gasoline (01) cars from 2022-2024 — should match a subset
    check("/search filter narrowed results (>0, <20)",
          0 < body.get("total_count", 0) < 20,
          f"total_count={body.get('total_count')}")
    # Verify each returned car actually meets the filter
    if body.get("data"):
        sample = body["data"][0]
        check("/search filter applied: year in range",
              2022 <= sample.get("year", 0) <= 2024,
              f"year={sample.get('year')}")

    # Scenario 4b: entry-number lookup (the formerly-30-page-scan now O(log n))
    r = client.post("/api/v1/autohub/search", json={"entry_number": "105", "page": 1, "page_size": 20})
    body = r.json()
    check("/search entry_number=105 returns 1 result",
          body.get("total_count") == 1,
          f"total_count={body.get('total_count')}")

    # Scenario 5: GET /car-detail/{car_id}
    r = client.get("/api/v1/autohub/car-detail/GC0005?perf_id=IP0005")
    body = r.json()
    check("GET /car-detail returns 200", r.status_code == 200, f"status={r.status_code}")
    check("/car-detail cache_mode='snapshot'", body.get("cache_mode") == "snapshot")
    check("/car-detail success=True", body.get("success") is True)
    check("/car-detail data not null", body.get("data") is not None)
    if body.get("data"):
        check("/car-detail VIN populated from snapshot",
              body["data"].get("vin", "").startswith("VIN_GC"),
              f"vin={body['data'].get('vin')}")

    # Scenario 5b: detail for a car NOT in snapshot
    r = client.get("/api/v1/autohub/car-detail/UNKNOWN_CAR")
    body = r.json()
    check("/car-detail for missing car returns success=False",
          body.get("success") is False,
          f"error={body.get('error')!r}")
    check("/car-detail missing has cache_mode='snapshot'",
          body.get("cache_mode") == "snapshot")

    # Scenario 6: GET /brands
    r = client.get("/api/v1/autohub/brands")
    body = r.json()
    check("GET /brands returns 200", r.status_code == 200)
    check("/brands cache_mode='snapshot'", body.get("cache_mode") == "snapshot")
    check("/brands data has groups", len(body.get("data", [])) > 0)

check("ZERO outbound calls during snapshot-mode reads",
      outbound_calls["count"] == 0,
      f"actual outbound count={outbound_calls['count']}")


# ---------------------------------------------------------------------------
# Scenario 7: Snapshot enabled, but DB is empty → 503-style error, NOT live
# ---------------------------------------------------------------------------

header("Scenario 7: Snapshot enabled, no snapshot in DB → safe error (NOT live fallthrough)")
reset_caches(E2E_EMPTY_DB)

unwanted = {"count": 0}
def boom(*a, **kw):
    unwanted["count"] += 1
    raise AssertionError("snapshot_unavailable should NOT fall through to live")

with patch.object(svc_mod.autohub_service, "_api_get", side_effect=boom), \
     patch.object(svc_mod.autohub_service, "_api_post", side_effect=boom), \
     patch.object(svc_mod.autohub_service, "_fetch_car_page", side_effect=boom):

    r = client.get("/api/v1/autohub/cars")
    body = r.json()
    check("/cars empty-DB success=False", body.get("success") is False)
    check("/cars empty-DB cache_mode='snapshot'", body.get("cache_mode") == "snapshot")
    check("/cars empty-DB friendly error",
          "preparing" in (body.get("error") or "").lower() or "shortly" in (body.get("error") or "").lower(),
          f"error={body.get('error')!r}")

    r = client.get("/api/v1/autohub/brands")
    body = r.json()
    check("/brands empty-DB success=False", body.get("success") is False)

    r = client.get("/api/v1/autohub/car-detail/X")
    body = r.json()
    check("/car-detail empty-DB success=False", body.get("success") is False)

check("ZERO outbound calls when snapshot-unavailable",
      unwanted["count"] == 0,
      f"actual outbound count={unwanted['count']}")


# ---------------------------------------------------------------------------
# Scenario 8: Snapshot DISABLED (current production state) → live path used
# ---------------------------------------------------------------------------

header("Scenario 8: Snapshot DISABLED → live path is used, response shape preserved")
os.environ["AUTOHUB_SNAPSHOT_ENABLED"] = "false"
reset_caches(E2E_DB)  # path doesn't matter; resolver bails on the flag

# Stub the live path internals so we don't actually call Autohub
from app.models.autohub import AutohubResponse, AutohubCarDetailResponse
from app.models.autohub_filters import AutohubBrandsResponse, AutohubBrandsGroup

def fake_live_listings(params):
    return AutohubResponse(success=True, data=[], total_count=42,
                           current_page=params.page, page_size=params.page_size)

def fake_live_brands_payload(*args, **kwargs):
    return {"code": "1", "data": []}  # raw API shape — caller calls map_brands

with patch.object(svc_mod.autohub_service, "_fetch_car_page", side_effect=fake_live_listings), \
     patch.object(svc_mod.autohub_service, "_api_get", side_effect=fake_live_brands_payload):

    r = client.get("/api/v1/autohub/snapshot/status")
    body = r.json()
    check("/snapshot/status when disabled has snapshot_enabled=false",
          body.get("snapshot_enabled") is False)
    check("/snapshot/status when disabled mode_today='live'",
          body.get("mode_today") == "live")

    r = client.get("/api/v1/autohub/cars?page=1&page_size=20")
    body = r.json()
    check("/cars in live mode returns 200", r.status_code == 200, f"status={r.status_code}")
    check("/cars in live mode cache_mode='live'", body.get("cache_mode") == "live",
          f"cache_mode={body.get('cache_mode')!r}")
    check("/cars in live mode used live fetcher (total=42 from stub)",
          body.get("total_count") == 42)


# ---------------------------------------------------------------------------
# Scenario 9: /snapshot/run admin endpoint — auth + concurrent-lock semantics
# ---------------------------------------------------------------------------

header("Scenario 9: /snapshot/run admin auth + concurrent-run lock")
os.environ["AUTOHUB_SNAPSHOT_ENABLED"] = "true"
reset_caches(E2E_DB)

# 9a: no admin token in header → 403
r = client.post("/api/v1/autohub/snapshot/run")
check("POST /snapshot/run without token → 403", r.status_code == 403,
      f"status={r.status_code}")

# 9b: wrong token → 403
r = client.post("/api/v1/autohub/snapshot/run", headers={"X-Admin-Token": "wrong"})
check("POST /snapshot/run with wrong token → 403", r.status_code == 403)

# 9c: correct token, no run in progress → 202
# Patch run_snapshot_job to a fast no-op so we don't actually execute one
async def fast_noop(*args, **kwargs):
    return {"snapshot_id": 999, "car_count": 0, "detail_count": 0, "elapsed_secs": 0}

with patch.object(job_mod, "run_snapshot_job", side_effect=fast_noop):
    r = client.post(
        "/api/v1/autohub/snapshot/run",
        headers={"X-Admin-Token": "e2e-admin-token-secret"},
    )
check("POST /snapshot/run with correct token → 202",
      r.status_code == 202, f"status={r.status_code}, body={r.text[:200]}")

# 9d: concurrent run — manually hold the lock then trigger
from filelock import FileLock
lock_path = job_mod._run_lock_path()
held = FileLock(lock_path, timeout=0)
held.acquire()
try:
    r = client.post(
        "/api/v1/autohub/snapshot/run",
        headers={"X-Admin-Token": "e2e-admin-token-secret"},
    )
    check("POST /snapshot/run while lock held → 409 Conflict",
          r.status_code == 409, f"status={r.status_code}, body={r.text[:200]}")
finally:
    held.release()

# 9e: missing admin token in env → 503
saved_token = os.environ.pop("AUTOHUB_SNAPSHOT_ADMIN_TOKEN")
get_settings.cache_clear()
try:
    r = client.post(
        "/api/v1/autohub/snapshot/run",
        headers={"X-Admin-Token": "anything"},
    )
    check("POST /snapshot/run with no AUTOHUB_SNAPSHOT_ADMIN_TOKEN env → 503",
          r.status_code == 503, f"status={r.status_code}")
finally:
    os.environ["AUTOHUB_SNAPSHOT_ADMIN_TOKEN"] = saved_token
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

header("E2E SUMMARY")
total = len(results)
passed = sum(1 for _, ok, _ in results if ok)
failed = total - passed
print(f"  {passed}/{total} checks passed, {failed} failed")
if failed:
    print("\n  FAILURES:")
    for label, ok, detail in results:
        if not ok:
            print(f"    - {label}: {detail}")

# Cleanup test DBs
for p in (E2E_DB, E2E_DB + "-wal", E2E_DB + "-shm",
          E2E_EMPTY_DB, E2E_EMPTY_DB + "-wal", E2E_EMPTY_DB + "-shm",
          E2E_LOCK, E2E_EMPTY_LOCK):
    if os.path.exists(p):
        os.unlink(p)

# Restore patched _authenticate just in case we're imported elsewhere
svc_mod.AutohubService._authenticate = _orig_authenticate

sys.exit(0 if failed == 0 else 1)
