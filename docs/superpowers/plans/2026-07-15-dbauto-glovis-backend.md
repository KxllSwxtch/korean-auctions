# DB Auto Glovis Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the production Glovis data source with a validated DB Auto provider exposed through `/api/v1/glovis`, with every upstream request pinned to Korean proxy egress.

**Architecture:** A dedicated transport owns short-lived fingerprint/token sessions and Korean proxy rotation; a service builds allowlisted DB Auto queries, performs semantic validation, and caches validated results; a FastAPI router exposes stable normalized contracts and structured errors. The existing SSANCAR modules remain registered for rollback compatibility but are never called by the new provider.

**Tech Stack:** Python 3.11+, FastAPI 0.115.12, Pydantic 2.11.5, Requests 2.32.3, Loguru, pytest, FastAPI TestClient.

## Global Constraints

- Every DB Auto catalog, token, API, retry, health, and live-smoke request must use Korean proxy egress; direct egress and SSANCAR fallback are forbidden.
- Use `https://cars.dbauto.kr` as the only upstream host and `lang=en` as the only upstream language.
- Keep token acquisition, the `x-api-token` cookie, and `X-Fingerprint` on the same `requests.Session` and proxy.
- Refresh tokens after 110 seconds and refresh exactly once after an API 401 or 403.
- Use no more than four concurrent provider sessions, Requests timeouts `(3.0, 8.0)`, and a 24-second hard wall-clock deadline.
- Never log or return proxy URLs, credentials, fingerprints, cookies, token values, raw authentication headers, or raw `gn` values from health probes.
- Public list pagination is one-based, defaults to 15, caps at 60, and computes `has_next_page` as `page * page_size < total`.
- Cache only semantically validated successes in a 512-entry LRU: auctions/cars/health 30 seconds, metadata 120 seconds, details/detail-health 300 seconds.
- Unknown DB Auto detail placeholders must become terminal `car_unavailable`, never HTTP-200 vehicle data.
- Preserve all meaningful provider detail fields and future keys in dynamic detail sections.
- Keep `/api/v1/ssancar` code and tests green; do not add automatic runtime fallback.
- No captured token, cookie, fingerprint, proxy URL, or credential may appear in source or fixtures.

---

## File Map

- Create `app/models/glovis.py`: normalized public models, provider query model, and extensible detail sections.
- Create `app/services/glovis_transport.py`: Korean proxy session pool, fingerprint/token lifecycle, hard deadline, rotation, and safe diagnostics.
- Create `app/services/glovis_service.py`: endpoint operations, query construction, semantic validation, bounded TTL/LRU caching, and health probes.
- Create `app/routes/glovis.py`: FastAPI query validation, dependency injection, response contracts, and structured error mapping.
- Modify `main.py`: import/register the Glovis router and expose its cache in shared cache stats/clear endpoints.
- Modify `app/core/config.py`: remove the unused legacy Glovis URL and credential fields.
- Create `tests/test_glovis_models.py`: model and identifier contract tests.
- Create `tests/glovis_fixtures.py`: synthetic raw provider fixtures and reusable builders; no captured production identity or authentication data.
- Create `tests/test_glovis_transport.py`: deterministic proxy/token/retry/deadline/redaction/concurrency tests.
- Create `tests/test_glovis_service.py`: endpoint parameters, semantic validation, pagination, cache, and health tests.
- Create `tests/test_glovis_routes.py`: public HTTP contract and error mapping tests.
- Create `tests/test_glovis_live.py`: opt-in Korean-egress auctions/list/detail smoke test with secret-safe output.
- Modify `tests/run_glovis_tests.sh`: run the real DB Auto suites through the repository virtual environment instead of missing legacy test files.

### Task 1: Freeze the normalized provider models and identifiers

**Files:**
- Create: `app/models/glovis.py`
- Create: `tests/test_glovis_models.py`
- Create: `tests/glovis_fixtures.py`

**Interfaces:**
- Produces: `GlovisAuction`, `GlovisAuctionsResponse`, `GlovisOption`, `GlovisFilterItemsResponse`, `GlovisSearchForm`, `GlovisFilterOptionsResponse`, `GlovisCar`, `GlovisCarsQuery`, `GlovisCarsResponse`, `GlovisCarDetail`, `GlovisCarDetailResponse`, `GlovisHealthResponse`, and `GlovisDetailHealthResponse`.
- `GlovisCarsQuery.upstream_params(page: int | None = None) -> list[tuple[str, str]]` must preserve repeated `options` and `usage_history` values.
- Detail section models use `ConfigDict(extra="allow")` so future provider keys survive validation and serialization.

- [ ] **Step 1: Add synthetic fixtures and write failing model contract tests**

Create `tests/glovis_fixtures.py` with reusable, non-production data:

```python
from __future__ import annotations

from copy import deepcopy

GN_RAW = "mJDbMQgcohK+3EAebGNDAg=="
GN_PATH = "mJDbMQgcohK-3EAebGNDAg~~"


def raw_auctions() -> list[dict[str, object]]:
    return [
        {"atn": "1102", "acc": "20", "title": "Glovis July A", "date": "2026-07-16"},
        {"atn": "1103", "acc": "20", "title": "Glovis July B", "date": "2026-07-18"},
    ]


def valid_list_car() -> dict[str, object]:
    return {
        "gn": GN_RAW,
        "rc": "3100",
        "acc": "20",
        "atn": "1102",
        "title": "[ Chevrolet ] IMPALA 2.5 LT",
        "lot_number": "1001",
        "thumbnail": "https://img-auction.autobell.co.kr/example-list.jpg",
        "room": "Yangsan",
        "lane": "A",
        "plate_number": "TEST-1001",
        "year": 2016,
        "mileage": 193_512,
        "displacement": 2_457,
        "start_price": 1_600_000,
        "fuel_type": "Gasoline",
        "transmission": "A/T",
        "color": "Gray",
        "rating": "A/1",
        "brand_code": "1",
        "brand": "Chevrolet",
        "model_code": "26",
        "model": "Impala",
        "submodel_code": "1568",
        "submodel": "Impala",
        "configuration": "2.5 LT",
        "status": None,
    }


def valid_list(total: int = 1) -> dict[str, object]:
    return {"total": total, "items": [valid_list_car()] if total else []}


def valid_filter_items() -> list[dict[str, object]]:
    return [{"value": "146", "label": "Genesis", "count": 72}]


def valid_search_form() -> dict[str, object]:
    item = {"value": "sample", "label": "Sample", "count": 1}
    return {
        "colors": [dict(item, value="White", label="White")],
        "options": [dict(item, value="navigation", label="Navigation")],
        "lanes": [dict(item, value="A", label="A")],
        "transmissions": [dict(item, value="A/T", label="A/T")],
        "fuels": [dict(item, value="Gasoline", label="Gasoline")],
        "insurance_damage": [dict(item, value="none", label="None")],
        "usage_history": [dict(item, value="rental", label="Rental")],
        "accident_history": [dict(item, value="none", label="None")],
        "sort_orders": [dict(item, value="01", label="Lot number")],
        "rooms": [dict(item, value="Yangsan", label="Yangsan")],
        "bid_statuses": [dict(item, value="open", label="Open")],
    }


def valid_detail() -> dict[str, object]:
    return {
        "main": {
            **valid_list_car(),
            "vin": "SYNTHETICVIN00001",
            "vehicle_type": "Personal/Passenger",
            "first_registration_date": "2015-10-30",
            "registration_date": None,
            "sold_price": None,
            "hope_price": None,
            "auction_start_time": None,
            "absentee_bid_start_time": None,
            "rating": {"frame": "None"},
        },
        "properties": {
            "product_type": "Own Company",
            "seating_capacity": "5-seater",
            "usage_type": "Personal/Corporate",
            "engine_model": "LCV",
            "storage_items": "None",
            "inspection_date": "Not Checked",
            "lot_position": "C38",
            "documents_complete": "Synthetic registration packet",
            "documents_missing": "-",
            "future_property": "kept",
        },
        "performance": {
            "engine": "Maintenance required",
            "brakes": "Normal",
            "steering": "Normal",
            "electrical": "Good",
            "Shifting": "Maintenance required",
            "hvac": "Normal",
            "power": "Normal",
            "interior": "Normal",
            "lighting": "Good",
            "Remarks": "-",
            "Changes": "-",
        },
        "total_table": {"future_total": 17},
        "summary_table": {"future_summary": "visible"},
        "options": [
            {"name": "Navigation", "enabled": True},
            {"name": "Sunroof", "enabled": False},
        ],
        "legal_status": {"seizures": 0, "mortgages": 0},
        "insurance_history": {
            "special_accidents": {
                "total_loss": 0,
                "theft": 0,
                "flood_total": 0,
                "flood_partial": 0,
            },
            "plate_changes": 0,
            "owner_changes": 1,
            "commercial_history": 0,
        },
        "accident_records": [
            {
                "date": "2025.07.20",
                "status": "Confirmed",
                "type": "Own insurance",
                "parts_cost": 10,
                "labor_cost": 20,
                "paint_cost": 30,
                "repair_cost": 60,
                "insurance_paid": 50,
            }
        ],
        "inspection_record": {
            "vehicle": {"usage": "Personal/Corporate", "engine_type": "LCV"},
            "future_inspection": {"value": "kept"},
        },
        "images": ["https://img-auction.autobell.co.kr/example-main.jpg"],
        "inspection_images": ["https://img-auction.autobell.co.kr/example-inspection.jpg"],
        "performance_image": "https://auction.autobell.co.kr/example-performance.jpg",
        "registration_certificate_image": "https://auction.autobell.co.kr/example-certificate.jpg",
        "remarks": "Synthetic provider remark",
    }


def placeholder_detail() -> dict[str, object]:
    payload = deepcopy(valid_detail())
    payload["main"] = {
        "gn": GN_RAW,
        "rc": "3100",
        "acc": "20",
        "atn": "1102",
        "title": "",
    }
    payload["images"] = []
    payload["performance_image"] = None
    payload["registration_certificate_image"] = None
    return payload
```

```python
from pydantic import ValidationError
import pytest

from app.models.glovis import (
    GlovisCarDetailResponse,
    GlovisCarsQuery,
    GlovisCarsResponse,
)


def test_query_serializes_repeated_filters_without_losing_order():
    query = GlovisCarsQuery(
        atn="1102",
        acc="20",
        page=2,
        page_size=15,
        brand="146",
        model="1171",
        submodel="2852",
        usage_history=["rental", "commercial"],
        options=["navigation", "sunroof"],
        sort_order="01",
    )

    assert query.upstream_params() == [
        ("atn", "1102"),
        ("acc", "20"),
        ("page", "2"),
        ("page_size", "15"),
        ("lang", "en"),
        ("brand", "146"),
        ("model", "1171"),
        ("submodel", "2852"),
        ("options", "navigation"),
        ("options", "sunroof"),
        ("usage_history", "rental"),
        ("usage_history", "commercial"),
        ("sort_order", "01"),
    ]


def test_list_response_uses_exact_provider_total_for_next_page():
    response = GlovisCarsResponse(
        total=31,
        items=[],
        page=2,
        page_size=15,
        atn="1102",
        acc="20",
    )
    assert response.success is True
    assert response.has_next_page is True


def test_detail_preserves_unknown_future_section_keys():
    response = GlovisCarDetailResponse.model_validate(
        {
            "data": {
                "main": {
                    "gn": "mJDbMQgcohK+3EAebGNDAg==",
                    "rc": "3100",
                    "acc": "20",
                    "atn": "1102",
                    "title": "[ Chevrolet ] IMPALA 2.5 LT",
                    "start_price": 1_600_000,
                },
                "properties": {"lot_position": "C38", "future_property": "kept"},
                "performance": {"engine": "Maintenance required"},
                "total_table": {"future_total": 17},
                "summary_table": {},
                "options": [{"name": "Navigation", "enabled": True}],
                "legal_status": {"seizures": 0, "mortgages": 0},
                "insurance_history": {
                    "special_accidents": {"total_loss": 0, "theft": 0},
                    "owner_changes": 1,
                },
                "accident_records": [],
                "inspection_record": {"vehicle": {"engine_type": "LCV"}},
                "images": ["https://img-auction.autobell.co.kr/example.jpg"],
                "inspection_images": [],
            }
        }
    )

    dumped = response.model_dump()
    assert dumped["data"]["properties"]["future_property"] == "kept"
    assert dumped["data"]["total_table"]["future_total"] == 17


def test_query_rejects_invalid_ranges_and_page_size():
    with pytest.raises(ValidationError):
        GlovisCarsQuery(
            atn="1102",
            acc="20",
            page=1,
            page_size=61,
            year_from=2024,
            year_to=2020,
        )
```

- [ ] **Step 2: Run the tests and confirm the module is missing**

Run: `venv/bin/python -m pytest tests/test_glovis_models.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'app.models.glovis'`.

- [ ] **Step 3: Implement the complete public model contract**

Use these exact public fields and defaults in `app/models/glovis.py`:

```python
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, computed_field, model_validator


class ExtensibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class GlovisAuction(BaseModel):
    number: str
    acc: str
    title: str
    date: date


class GlovisAuctionsResponse(BaseModel):
    success: Literal[True] = True
    auctions: list[GlovisAuction]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GlovisOption(BaseModel):
    value: str
    label: str
    count: StrictInt = Field(default=0, ge=0)


class GlovisFilterItemsResponse(BaseModel):
    success: Literal[True] = True
    items: list[GlovisOption]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GlovisSearchForm(BaseModel):
    colors: list[GlovisOption] = Field(default_factory=list)
    options: list[GlovisOption] = Field(default_factory=list)
    lanes: list[GlovisOption] = Field(default_factory=list)
    transmissions: list[GlovisOption] = Field(default_factory=list)
    fuels: list[GlovisOption] = Field(default_factory=list)
    insurance_damage: list[GlovisOption] = Field(default_factory=list)
    usage_history: list[GlovisOption] = Field(default_factory=list)
    accident_history: list[GlovisOption] = Field(default_factory=list)
    sort_orders: list[GlovisOption] = Field(default_factory=list)
    rooms: list[GlovisOption] = Field(default_factory=list)
    bid_statuses: list[GlovisOption] = Field(default_factory=list)


class GlovisFilterOptionsResponse(BaseModel):
    success: Literal[True] = True
    filters: GlovisSearchForm
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GlovisCar(BaseModel):
    gn: str
    rc: str
    acc: str
    atn: str
    title: str
    lot_number: str
    thumbnail: str | None = None
    room: str | None = None
    lane: str | None = None
    plate_number: str | None = None
    year: StrictInt | None = Field(default=None, ge=1900, le=2200)
    mileage: StrictInt | None = Field(default=None, ge=0)
    displacement: StrictInt | None = Field(default=None, ge=0)
    start_price: StrictInt | None = Field(default=None, ge=0)
    fuel_type: str | None = None
    transmission: str | None = None
    color: str | None = None
    rating: str | None = None
    brand_code: str | None = None
    brand: str | None = None
    model_code: str | None = None
    model: str | None = None
    submodel_code: str | None = None
    submodel: str | None = None
    configuration: str | None = None
    status: str | None = None


class GlovisCarsQuery(BaseModel):
    atn: str
    acc: str
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=15, ge=1, le=60)
    brand: str | None = None
    model: str | None = None
    submodel: str | None = None
    year_from: int | None = Field(default=None, ge=1900, le=2200)
    year_to: int | None = Field(default=None, ge=1900, le=2200)
    mileage_from: int | None = Field(default=None, ge=0)
    mileage_to: int | None = Field(default=None, ge=0)
    price_from: int | None = Field(default=None, ge=0)
    price_to: int | None = Field(default=None, ge=0)
    transmission: str | None = None
    fuel_type: str | None = None
    color: str | None = None
    options: list[str] = Field(default_factory=list)
    insurance_damage: str | None = None
    usage_history: list[str] = Field(default_factory=list)
    accident_history: str | None = None
    room: str | None = None
    lane: str | None = None
    bid_status: str | None = None
    sort_order: str = "01"

    @model_validator(mode="after")
    def validate_relationships(self) -> "GlovisCarsQuery":
        if self.model and not self.brand:
            raise ValueError("model requires brand")
        if self.submodel and not (self.brand and self.model):
            raise ValueError("submodel requires brand and model")
        for lower, upper, label in (
            (self.year_from, self.year_to, "year"),
            (self.mileage_from, self.mileage_to, "mileage"),
            (self.price_from, self.price_to, "price"),
        ):
            if lower is not None and upper is not None and lower > upper:
                raise ValueError(f"{label}_from must be <= {label}_to")
        return self

    def upstream_params(self, page: int | None = None) -> list[tuple[str, str]]:
        values: list[tuple[str, str]] = [
            ("atn", self.atn),
            ("acc", self.acc),
            ("page", str(page or self.page)),
            ("page_size", str(self.page_size)),
            ("lang", "en"),
        ]
        for name in (
            "brand", "model", "submodel", "year_from", "year_to",
            "mileage_from", "mileage_to", "price_from", "price_to",
            "transmission", "fuel_type", "color", "insurance_damage",
            "accident_history", "room", "lane", "bid_status",
        ):
            value = getattr(self, name)
            if value is not None and value != "":
                values.append((name, str(value)))
        values.extend(("options", value) for value in self.options if value)
        values.extend(
            ("usage_history", value) for value in self.usage_history if value
        )
        values.append(("sort_order", self.sort_order))
        return values


class GlovisCarsResponse(BaseModel):
    success: Literal[True] = True
    total: StrictInt = Field(ge=0)
    items: list[GlovisCar]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=60)
    atn: str
    acc: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @computed_field
    @property
    def has_next_page(self) -> bool:
        return self.page * self.page_size < self.total


class GlovisMain(ExtensibleModel):
    gn: str
    rc: str
    acc: str
    atn: str
    title: str
    lot_number: str | None = None
    lane: str | None = None
    room: str | None = None
    plate_number: str | None = None
    vin: str | None = None
    year: StrictInt | None = None
    mileage: StrictInt | None = None
    displacement: StrictInt | None = None
    fuel_type: str | None = None
    transmission: str | None = None
    color: str | None = None
    vehicle_type: str | None = None
    brand_code: str | None = None
    brand: str | None = None
    model_code: str | None = None
    model: str | None = None
    submodel_code: str | None = None
    submodel: str | None = None
    configuration: str | None = None
    first_registration_date: date | None = None
    registration_date: date | None = None
    start_price: StrictInt | None = None
    sold_price: StrictInt | None = None
    hope_price: StrictInt | None = None
    auction_start_time: datetime | str | None = None
    absentee_bid_start_time: datetime | str | None = None
    rating: dict[str, Any] | str | None = None
    status: str | None = None


class GlovisEquipmentOption(ExtensibleModel):
    name: str
    enabled: bool


class GlovisLegalStatus(ExtensibleModel):
    seizures: StrictInt | None = Field(default=None, ge=0)
    mortgages: StrictInt | None = Field(default=None, ge=0)


class GlovisSpecialAccidents(ExtensibleModel):
    total_loss: StrictInt | None = Field(default=None, ge=0)
    theft: StrictInt | None = Field(default=None, ge=0)
    flood_total: StrictInt | None = Field(default=None, ge=0)
    flood_partial: StrictInt | None = Field(default=None, ge=0)


class GlovisInsuranceHistory(ExtensibleModel):
    special_accidents: GlovisSpecialAccidents | None = None
    plate_changes: StrictInt | None = Field(default=None, ge=0)
    owner_changes: StrictInt | None = Field(default=None, ge=0)


class GlovisAccidentRecord(ExtensibleModel):
    date: str | None = None
    status: str | None = None
    type: str | None = None
    parts_cost: StrictInt | None = Field(default=None, ge=0)
    labor_cost: StrictInt | None = Field(default=None, ge=0)
    paint_cost: StrictInt | None = Field(default=None, ge=0)
    repair_cost: StrictInt | None = Field(default=None, ge=0)
    insurance_paid: StrictInt | None = Field(default=None, ge=0)


class GlovisCarDetail(ExtensibleModel):
    main: GlovisMain
    properties: dict[str, Any] = Field(default_factory=dict)
    performance: dict[str, Any] = Field(default_factory=dict)
    total_table: dict[str, Any] = Field(default_factory=dict)
    summary_table: dict[str, Any] = Field(default_factory=dict)
    options: list[GlovisEquipmentOption] = Field(default_factory=list)
    legal_status: GlovisLegalStatus | None = None
    insurance_history: GlovisInsuranceHistory | None = None
    accident_records: list[GlovisAccidentRecord] = Field(default_factory=list)
    inspection_record: dict[str, Any] = Field(default_factory=dict)
    images: list[str] = Field(default_factory=list)
    inspection_images: list[str] = Field(default_factory=list)
    performance_image: str | None = None
    registration_certificate_image: str | None = None
    remarks: str | None = None


class GlovisCarDetailResponse(BaseModel):
    success: Literal[True] = True
    data: GlovisCarDetail
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GlovisHealthResponse(BaseModel):
    status: Literal["healthy"] = "healthy"
    provider: Literal["dbauto"] = "dbauto"
    auction_count: StrictInt = Field(ge=0)
    list_count: StrictInt = Field(ge=0)
    egress: str
    checked_at: datetime


class GlovisDetailHealthResponse(GlovisHealthResponse):
    detail_checked: Literal[True] = True
```

Use `StrictInt` (including optional `StrictInt`) for provider totals, counts, prices, mileage, displacement, and accident amounts after service normalization so JSON booleans cannot pass as integers. The emitted computed JSON key must remain exactly `has_next_page`.

- [ ] **Step 4: Run the model tests**

Run: `venv/bin/python -m pytest tests/test_glovis_models.py -q`

Expected: all model tests pass.

- [ ] **Step 5: Commit the model contract**

```bash
git add app/models/glovis.py tests/glovis_fixtures.py tests/test_glovis_models.py
git commit -m "feat: define DB Auto Glovis contracts"
```

### Task 2: Build Korean-only tokenized transport

**Files:**
- Create: `app/services/glovis_transport.py`
- Create: `tests/test_glovis_transport.py`

**Interfaces:**
- Consumes: `get_proxy_pool() -> ProxyPool` from `app.core.proxy_config`.
- Produces: `GlovisTransport.get_json(path, params, operation, deadline_at=None) -> GlovisTransportResult[dict[str, Any] | list[Any]]` and `GlovisTransport.close() -> None`.
- Produces structured exceptions `GlovisUpstreamAuthError`, `GlovisUpstreamInvalidResponseError`, `GlovisUpstreamUnavailableError`, `GlovisUpstreamTimeoutError`, and `GlovisProxyUnavailableError` with stable `.code` values.

- [ ] **Step 1: Write failing tests for fail-closed egress and session affinity**

Create deterministic `StubSession`, `StubResponse`, and `StubProxyPool` fixtures before the assertions:

```python
from dataclasses import dataclass, field
import threading
import time
from typing import Any

from loguru import logger
import pytest
import requests

from app.services.glovis_transport import (
    GlovisProxyUnavailableError,
    GlovisTransport,
    GlovisUpstreamTimeoutError,
    GlovisUpstreamUnavailableError,
)

AUCTIONS_PATH = "/api/auctions/glovis/auctions"
CARS_PATH = "/api/auctions/glovis/cars"


@dataclass
class StubResponse:
    status_code: int = 200
    json_data: Any = field(default_factory=dict)
    text: str = "{}"
    headers: dict[str, str] = field(default_factory=dict)
    set_cookie: tuple[str, str] | None = None

    def json(self):
        return self.json_data


class StubSession:
    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.calls: list[dict[str, Any]] = []
        self.headers: dict[str, str] = {}
        self.proxies: dict[str, str] = {}
        self.cookies = requests.cookies.RequestsCookieJar()
        self.trust_env = True

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            outcome = outcome()
        if outcome.set_cookie:
            self.cookies.set(*outcome.set_cookie)
        return outcome

    def close(self):
        return None


class StubProxyPool:
    def __init__(self, candidates):
        self.candidates = list(candidates)
        self.index = 0

    def __len__(self):
        return len(self.candidates)

    def current(self):
        return self.candidates[self.index]

    def advance(self):
        self.index = (self.index + 1) % len(self.candidates)
        return self.current()


def token_response(value: str) -> StubResponse:
    return StubResponse(
        json_data={"ok": True},
        set_cookie=("x-api-token", value),
    )


def make_transport(*sessions: StubSession, overall_deadline_seconds=24.0):
    queue = list(sessions)
    candidates = [
        (f"kr-{index}", f"http://proxy-{index}.invalid:8080")
        for index in range(1, len(sessions) + 1)
    ]
    return GlovisTransport(
        proxy_candidates=candidates,
        session_factory=lambda: queue.pop(0),
        fingerprint_factory=lambda: "fingerprint-a",
        overall_deadline_seconds=overall_deadline_seconds,
    )


def test_missing_proxy_pool_fails_closed_without_creating_direct_session():
    created = []
    with pytest.raises(GlovisProxyUnavailableError):
        GlovisTransport(
            proxy_candidates=[],
            session_factory=lambda: created.append(StubSession()) or created[-1],
        )
    assert created == []


def test_token_and_api_use_same_proxy_session_and_matching_fingerprint():
    session = StubSession([
        StubResponse(json_data={"ok": True}, set_cookie=("x-api-token", "token")),
        StubResponse(json_data={"total": 0, "items": []}),
    ])
    transport = GlovisTransport(
        proxy_candidates=[("kr-primary", "http://redacted.invalid:8080")],
        session_factory=lambda: session,
        fingerprint_factory=lambda: "fingerprint-a",
    )

    result = transport.get_json(
        "/api/auctions/glovis/cars",
        [("atn", "1102"), ("acc", "20")],
        operation="cars",
    )

    assert result.value == {"total": 0, "items": []}
    assert [call["url"] for call in session.calls] == [
        "https://cars.dbauto.kr/api/auth/token",
        "https://cars.dbauto.kr/api/auctions/glovis/cars",
    ]
    assert session.calls[0]["json"] == {"fingerprint": "fingerprint-a"}
    assert session.calls[1]["headers"]["X-Fingerprint"] == "fingerprint-a"
    assert session.proxies["https"] == "http://redacted.invalid:8080"
    assert session.trust_env is False
```

- [ ] **Step 2: Run the targeted tests and confirm they fail**

Run: `venv/bin/python -m pytest tests/test_glovis_transport.py -q`

Expected: collection fails because `app.services.glovis_transport` does not exist.

- [ ] **Step 3: Implement the session slots and token lifecycle**

Use these constants and public shapes:

```python
BASE_URL = "https://cars.dbauto.kr"
TOKEN_PATH = "/api/auth/token"
TOKEN_REFRESH_SECONDS = 110.0
CONNECT_TIMEOUT_SECONDS = 3.0
READ_TIMEOUT_SECONDS = 8.0
OVERALL_DEADLINE_SECONDS = 24.0
MAX_SESSIONS = 4


class GlovisUpstreamError(RuntimeError):
    code = "upstream_unavailable"
    retryable = True

    def __init__(self, *, status_code: int | None = None, egress: str | None = None):
        super().__init__(self.code)
        self.status_code = status_code
        self.egress = egress


class GlovisUpstreamAuthError(GlovisUpstreamError):
    code = "upstream_auth"


class GlovisUpstreamInvalidResponseError(GlovisUpstreamError):
    code = "upstream_invalid_response"


class GlovisUpstreamUnavailableError(GlovisUpstreamError):
    code = "upstream_unavailable"


class GlovisUpstreamTimeoutError(GlovisUpstreamError):
    code = "upstream_timeout"


class GlovisProxyUnavailableError(GlovisUpstreamError):
    code = "proxy_unavailable"


@dataclass
class _SessionSlot:
    egress: str
    session: requests.Session
    fingerprint: str
    token_acquired_at: float | None = None


@dataclass(frozen=True)
class GlovisTransportResult(Generic[T]):
    value: T
    egress: str
    status_code: int
    elapsed_ms: int
```

Constructor behavior:

```python
def __init__(
    self,
    *,
    proxy_candidates: list[tuple[str, str]] | None = None,
    session_factory: Callable[[], requests.Session] = requests.Session,
    fingerprint_factory: Callable[[], str] | None = None,
    clock: Callable[[], float] = time.monotonic,
    overall_deadline_seconds: float = OVERALL_DEADLINE_SECONDS,
) -> None:
    candidates = (
        self._proxy_candidates_from_pool()
        if proxy_candidates is None
        else proxy_candidates
    )
    if not candidates:
        raise GlovisProxyUnavailableError()
    self._clock = clock
    self._deadline_seconds = overall_deadline_seconds
    self._slots: Queue[_SessionSlot] = Queue(maxsize=min(MAX_SESSIONS, len(candidates)))
    for egress, proxy_url in candidates[:MAX_SESSIONS]:
        session = session_factory()
        session.trust_env = False
        session.proxies.update({"http": proxy_url, "https": proxy_url})
        session.headers.update(self._base_headers())
        self._slots.put(
            _SessionSlot(
                egress=egress,
                session=session,
                fingerprint=(fingerprint_factory or self._new_fingerprint)(),
            )
        )
```

`_base_headers()` returns only stable, non-secret browser-compatible headers:

```python
{
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://cars.dbauto.kr/en/glovis",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
}
```

Do not add browser client hints or a fingerprint header to the session defaults. Add `X-Fingerprint` only to API calls after token acquisition so the explicit token request remains identical to the verified production flow.

`_proxy_candidates_from_pool()` must call `get_proxy_pool()`, collect at most `min(len(pool), 4)` distinct `(entry.name, url)` pairs through `current()`/`advance()`, and never log/return the URLs. `_new_fingerprint()` returns `sha256(secrets.token_bytes(32)).hexdigest()`.

`_ensure_token(slot, deadline, force=False)` posts `{"fingerprint": slot.fingerprint}` on the slot session when no token exists, when its age is at least 110 seconds, or when forced. It accepts only HTTP 200 with JSON `{"ok": true}` and an `x-api-token` cookie present in `slot.session.cookies`; otherwise it raises the matching structured transport error.

`get_json()` must lease exactly one slot from the queue and hand ownership to the daemon attempt worker. That worker calls `_ensure_token`, issues the GET with the matching `X-Fingerprint`, and returns or discards the complete slot only after Requests actually finishes; a caller-side hard timeout must never put a still-busy session back into circulation. Redirects are disabled and only JSON objects/arrays are accepted. An API 401/403 calls `_ensure_token(slot, deadline, force=True)` once and retries the same request on the same slot.

- [ ] **Step 4: Add refresh, rotation, deadline, concurrency, and log-redaction tests**

Add deterministic tests with these assertions:

```python
@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_refreshes_once_on_same_slot(status):
    session = StubSession([
        token_response("first"),
        StubResponse(status_code=status, json_data={"detail": "expired"}),
        token_response("second"),
        StubResponse(json_data={"items": [], "total": 0}),
    ])
    transport = make_transport(session)
    transport.get_json(CARS_PATH, [], operation="cars")
    assert [call["method"] for call in session.calls] == ["POST", "GET", "POST", "GET"]


def test_token_is_reused_at_109_seconds_and_refreshed_at_110_seconds():
    now = [0.0]
    session = StubSession([
        token_response("first"),
        StubResponse(json_data=[]),
        StubResponse(json_data=[]),
        token_response("second"),
        StubResponse(json_data=[]),
    ])
    transport = GlovisTransport(
        proxy_candidates=[("kr-1", "http://proxy-1.invalid:8080")],
        session_factory=lambda: session,
        fingerprint_factory=lambda: "fingerprint-a",
        clock=lambda: now[0],
    )
    transport.get_json(AUCTIONS_PATH, [], operation="auctions")
    now[0] = 109.0
    transport.get_json(AUCTIONS_PATH, [], operation="auctions")
    now[0] = 110.0
    transport.get_json(AUCTIONS_PATH, [], operation="auctions")
    assert [call["method"] for call in session.calls] == [
        "POST", "GET", "GET", "POST", "GET",
    ]


def test_retryable_failure_rotates_complete_proxy_session():
    first = StubSession([token_response("one"), requests.ConnectionError("down")])
    second = StubSession([token_response("two"), StubResponse(json_data=[])])
    result = make_transport(first, second).get_json(AUCTIONS_PATH, [], operation="auctions")
    assert result.egress == "kr-2"
    assert len(first.calls) == 2
    assert len(second.calls) == 2


def test_hard_deadline_returns_24_second_timeout_even_if_worker_remains_blocked():
    release = threading.Event()

    def blocked_response():
        release.wait(5.0)
        return StubResponse(json_data=[])

    session = StubSession([
        token_response("one"),
        blocked_response,
    ])
    transport = make_transport(session, overall_deadline_seconds=0.05)
    started = time.monotonic()
    try:
        with pytest.raises(GlovisUpstreamTimeoutError):
            transport.get_json(CARS_PATH, [], operation="cars")
        assert time.monotonic() - started < 0.25
    finally:
        release.set()


def test_safe_logs_do_not_contain_transport_secrets():
    captured: list[str] = []
    sink = logger.add(captured.append, format="{message}")
    session = StubSession([
        token_response("token-a"),
        requests.ConnectionError("proxy-user:proxy-password fingerprint-a mJDb"),
    ])
    try:
        with pytest.raises(GlovisUpstreamUnavailableError):
            make_transport(session).get_json(CARS_PATH, [], operation="cars")
    finally:
        logger.remove(sink)
    joined = "\n".join(captured)
    for secret in ("proxy-user", "proxy-password", "fingerprint-a", "token-a", "mJDb"):
        assert secret not in joined
```

Use a bounded daemon-worker pattern matching `SSANCARTransport.request`: the caller waits only until the monotonic deadline while the worker retains the global bounded semaphore until Requests actually returns. Set the semaphore to four. Retryable 429/5xx/Requests failures rotate to the next slot; non-JSON HTTP 200 becomes `upstream_invalid_response`; redirects remain disabled.

Keep an `_all_slots` tuple in addition to the availability queue and guard shutdown with a closing event. `close()` marks the transport closed, closes idle sessions immediately, and causes any in-flight worker to close its session instead of returning it to the queue after Requests finishes. Calls made after shutdown raise `GlovisUpstreamUnavailableError`; never close or re-lease an in-flight session from the caller-side timeout path.

Safe log fields are limited to event, operation, egress label, HTTP status, payload length, the first 12 characters of a SHA-256 payload digest, elapsed milliseconds, and structured error code.

- [ ] **Step 5: Run the transport suite**

Run: `venv/bin/python -m pytest tests/test_glovis_transport.py -q`

Expected: token/session, refresh, rotation, deadline, concurrency, and redaction tests pass without network access.

- [ ] **Step 6: Commit the transport**

```bash
git add app/services/glovis_transport.py tests/test_glovis_transport.py
git commit -m "feat: add Korean-only DB Auto transport"
```

### Task 3: Implement provider operations, semantic validation, and bounded caching

**Files:**
- Create: `app/services/glovis_service.py`
- Create: `tests/test_glovis_service.py`

**Interfaces:**
- Consumes: `GlovisTransport.get_json` and all models from Task 1.
- Produces: `get_auctions() -> GlovisAuctionsResponse`, `get_cars() -> GlovisCarsResponse`, metadata response envelopes, `get_car_detail() -> GlovisCarDetailResponse`, health responses, `get_cache_stats()`, `clear_cache()`, and `close()`.
- Produces validators `validate_provider_id(value, name) -> str` and `validate_gn(value) -> str` for route reuse.

- [ ] **Step 1: Write failing tests for exact forwarding and semantic validation**

```python
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from app.models.glovis import GlovisCarsQuery
from app.services.glovis_service import (
    CARS_PATH,
    DETAIL_PATH,
    GlovisCarUnavailableError,
    GlovisService,
    validate_provider_id,
)
from app.services.glovis_transport import (
    GlovisTransportResult,
    GlovisUpstreamInvalidResponseError,
)
from tests.glovis_fixtures import placeholder_detail, valid_detail, valid_list, valid_list_car


@dataclass(frozen=True)
class RecordedCall:
    path: str
    params: list[tuple[str, str]]
    operation: str
    deadline_at: float | None


class StubTransport:
    def __init__(self, responses: dict[str, Any]):
        self.responses = responses
        self.calls: list[RecordedCall] = []

    def get_json(self, path, params, operation, deadline_at=None):
        self.calls.append(RecordedCall(path, list(params), operation, deadline_at))
        response = self.responses[path]
        if isinstance(response, deque):
            response = response.popleft()
        if isinstance(response, BaseException):
            raise response
        return GlovisTransportResult(
            value=deepcopy(response),
            egress="kr-test",
            status_code=200,
            elapsed_ms=1,
        )

    def call_count(self, path: str) -> int:
        return sum(call.path == path for call in self.calls)


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def base_query(**changes: Any) -> GlovisCarsQuery:
    return GlovisCarsQuery(
        atn="1102",
        acc="20",
        page=changes.pop("page", 1),
        page_size=15,
        **changes,
    )


def successful_transport() -> StubTransport:
    return StubTransport({CARS_PATH: valid_list(total=1)})


def test_cars_forwards_complete_allowlisted_query_and_exact_pagination():
    transport = StubTransport({
        "/api/auctions/glovis/cars": {
            "total": 31,
            "items": [valid_list_car()],
        }
    })
    service = GlovisService(transport=transport)
    result = service.get_cars(
        GlovisCarsQuery(
            atn="1102", acc="20", page=2, page_size=15,
            brand="146", model="1171", submodel="2852",
            usage_history=["rental", "commercial"], sort_order="02",
        )
    )
    assert result.total == 31
    assert result.has_next_page is True
    assert transport.calls[0].params.count(("usage_history", "rental")) == 1
    assert transport.calls[0].params.count(("usage_history", "commercial")) == 1
    assert ("lang", "en") in transport.calls[0].params


def test_placeholder_detail_is_terminal_unavailable():
    transport = StubTransport({DETAIL_PATH: placeholder_detail()})
    service = GlovisService(transport=transport)
    with pytest.raises(GlovisCarUnavailableError):
        service.get_car_detail(
            gn="mJDbMQgcohK+3EAebGNDAg==", rc="3100", acc="20", atn="1102"
        )


def test_detail_rejects_identity_mismatch():
    payload = valid_detail()
    payload["main"]["gn"] = "AAAAAAAAAAAAAAAAAAAAAA=="
    service = GlovisService(transport=StubTransport({DETAIL_PATH: payload}))
    with pytest.raises(GlovisUpstreamInvalidResponseError):
        service.get_car_detail(
            gn="mJDbMQgcohK+3EAebGNDAg==", rc="3100", acc="20", atn="1102"
        )


@pytest.mark.parametrize("value", ["", "abc", "1102&host=evil", "１２３"])
def test_provider_ids_accept_only_ascii_digits(value):
    with pytest.raises(ValueError):
        validate_provider_id(value, "atn")
```

- [ ] **Step 2: Run and confirm the service module is missing**

Run: `venv/bin/python -m pytest tests/test_glovis_service.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'app.services.glovis_service'`.

- [ ] **Step 3: Implement identifiers, validators, and endpoint methods**

Use fixed paths and strict public validation:

```python
AUCTIONS_PATH = "/api/auctions/glovis/auctions"
CARS_PATH = "/api/auctions/glovis/cars"
BRANDS_PATH = "/api/auctions/glovis/brands"
MODELS_PATH = "/api/auctions/glovis/models"
SUBMODELS_PATH = "/api/auctions/glovis/submodels"
SEARCH_FORM_PATH = "/api/auctions/glovis/search-form"
DETAIL_PATH = "/api/auctions/glovis/car"
PROVIDER_ID_RE = re.compile(r"^[0-9]{1,12}$", re.ASCII)


class GlovisCarUnavailableError(RuntimeError):
    code = "car_unavailable"
    retryable = False


def validate_provider_id(value: str, name: str) -> str:
    if not PROVIDER_ID_RE.fullmatch(value or ""):
        raise ValueError(f"{name} must contain 1 to 12 ASCII digits")
    return value


def validate_gn(value: str) -> str:
    if not value or len(value) > 128:
        raise ValueError("gn must be canonical base64")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("gn must be canonical base64") from None
    if not decoded or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError("gn must be canonical base64")
    return value
```

Endpoint methods must call transport with these exact upstream parameter sets:

- `get_auctions`: `[('lang', 'en')]`, normalize provider auction number to `GlovisAuction.number`, preserve `acc`, title, and ISO date, sort by date then number, reject duplicate/missing identities, and wrap the array as `{success, auctions, timestamp}`.
- `get_cars`: `query.upstream_params()`, require non-negative integer `total`, list `items`, unique `(gn, rc)` identities, matching item `atn/acc`, non-empty title and lot number, HTTPS-or-null thumbnail.
- `get_brands`: `atn`, `acc`, `lang`; wrap normalized facets as `{success, items, timestamp}`.
- `get_models`: `brand`, `atn`, `acc`, `lang`; wrap normalized facets as `{success, items, timestamp}`.
- `get_submodels`: `brand`, `model`, `atn`, `acc`, `lang`; wrap normalized facets as `{success, items, timestamp}`.
- `get_filter_options`: `atn`, `acc`, `lang`; map upstream search-form keys into the exact `GlovisSearchForm` fields from Task 1 and return `{success, filters, timestamp}`.
- `get_car_detail`: `gn`, `rc`, `acc`, `atn`, `lang`; require exact identity equality, a non-empty title, and at least one of vehicle facts, price, gallery images, performance image, or registration certificate.

Validate every image string with `urlsplit`: only `https`, a non-empty hostname, and no embedded credentials. Reject malformed option objects and scalar/container type mismatches before model construction.

- [ ] **Step 4: Add bounded TTL/LRU cache tests**

```python
def test_only_valid_successes_are_cached():
    transport = StubTransport({
        CARS_PATH: deque([
            {"total": "not-an-integer", "items": []},
            valid_list(total=0),
        ])
    })
    service = GlovisService(transport=transport, clock=FakeClock())
    with pytest.raises(GlovisUpstreamInvalidResponseError):
        service.get_cars(base_query())
    service.get_cars(base_query())
    service.get_cars(base_query())
    assert transport.call_count(CARS_PATH) == 2


def test_cache_key_includes_full_normalized_query():
    service = GlovisService(transport=successful_transport(), clock=FakeClock())
    service.get_cars(base_query(color="White"))
    service.get_cars(base_query(color="Black"))
    assert service.get_cache_stats()["misses"] == 2


def test_lru_never_exceeds_512_entries():
    service = GlovisService(transport=successful_transport(), clock=FakeClock())
    for page in range(1, 515):
        service.get_cars(base_query(page=page))
    assert service.get_cache_stats()["size"] == 512
```

Implement an `OrderedDict[tuple[Any, ...], _CacheEntry]` guarded by `threading.RLock`. `_cached(key, ttl, loader)` removes expired entries, moves hits to the end, invokes `loader` outside the lock, stores only returned validated values, and evicts from the front until the size is at most 512. Cache keys contain operation plus every normalized parameter tuple; detail keys contain all four identity values.

Use exact TTL constants:

```python
AUCTIONS_TTL = 30.0
CARS_TTL = 30.0
METADATA_TTL = 120.0
DETAIL_TTL = 300.0
HEALTH_TTL = 30.0
DETAIL_HEALTH_TTL = 300.0
CACHE_MAX_ENTRIES = 512
```

- [ ] **Step 5: Implement and test health probes under a shared deadline**

Separate each operation into an uncached `_load_*` method that returns both the normalized value and its safe `GlovisTransportResult.egress`, then wrap normal public reads with `_cached`. On a health-cache miss, `check_health()` must call `_load_auctions(deadline_at)` and `_load_cars(page_size=1, deadline_at)` directly, bypassing ordinary auctions/cars caches so the probe actually validates token acquisition and provider I/O. It chooses the first auction and reports only safe egress labels/counts. `check_detail_health()` has its own 300-second cache, shares one `deadline_at = clock() + 24.0`, directly performs the list probe, returns healthy without a detail call when total is zero, otherwise calls `_load_car_detail` for the first car. It must never include `gn`, plate, VIN, or proxy address in the response/log. `close()` closes every transport session; a hard-deadline worker retains its leased slot until the worker exits.

Run: `venv/bin/python -m pytest tests/test_glovis_service.py -q`

Expected: all operation, validation, cache, and health tests pass.

- [ ] **Step 6: Commit the service**

```bash
git add app/services/glovis_service.py tests/test_glovis_service.py
git commit -m "feat: add validated DB Auto Glovis service"
```

### Task 4: Expose the canonical FastAPI contract

**Files:**
- Create: `app/routes/glovis.py`
- Create: `tests/test_glovis_routes.py`
- Modify: `main.py`
- Modify: `app/core/config.py`

**Interfaces:**
- Consumes every `GlovisService` method from Task 3.
- Produces `/api/v1/glovis/{auctions,cars,brands,models,submodels,filters/options,car-detail,health,health/detail}`.
- All failures use `{"detail":{"code": str,"message": str,"retryable": bool}}` and `Cache-Control: no-store`.

- [ ] **Step 1: Write failing route contract tests with dependency overrides**

```python
class StubGlovisService:
    def __init__(self):
        self.query = None
        self.detail_identity = None
        self.error = None

    def get_cars(self, query):
        if self.error:
            raise self.error
        self.query = query
        return GlovisCarsResponse(total=0, items=[], page=query.page,
            page_size=query.page_size, atn=query.atn, acc=query.acc)


def make_client(service):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_glovis_service] = lambda: service
    return TestClient(app)


def test_cars_accepts_repeated_filters_at_maximum_page_size():
    service = StubGlovisService()
    response = make_client(service).get(
        "/api/v1/glovis/cars",
        params=[
            ("atn", "1102"), ("acc", "20"), ("page", "2"),
            ("page_size", "60"), ("usage_history", "rental"),
            ("usage_history", "commercial"), ("options", "navigation"),
        ],
    )
    assert response.status_code == 200
    assert service.query.usage_history == ["rental", "commercial"]
    assert service.query.options == ["navigation"]
    assert response.json()["has_next_page"] is False


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (GlovisProxyUnavailableError(), 503, "proxy_unavailable"),
        (GlovisUpstreamTimeoutError(), 504, "upstream_timeout"),
        (GlovisUpstreamAuthError(), 502, "upstream_auth"),
        (GlovisUpstreamInvalidResponseError(), 502, "upstream_invalid_response"),
        (GlovisUpstreamUnavailableError(), 502, "upstream_unavailable"),
    ],
)
def test_structured_errors_are_never_cacheable(error, status, code):
    service = StubGlovisService()
    service.error = error
    response = make_client(service).get(
        "/api/v1/glovis/cars?atn=1102&acc=20"
    )
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert response.json()["detail"]["retryable"] is True
    assert response.headers["cache-control"] == "no-store"
```

Also test invalid `gn`/IDs return 422 without calling the service, placeholder detail returns 404/non-retryable, dependent query violations return 422, page size 61 returns 422, health failures return structured errors, and empty healthy lists remain HTTP 200.

- [ ] **Step 2: Run and confirm the router is missing**

Run: `venv/bin/python -m pytest tests/test_glovis_routes.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'app.routes.glovis'`.

- [ ] **Step 3: Implement the router and explicit query construction**

Use `router = APIRouter(prefix="/api/v1/glovis", tags=["Glovis Auction"])`, a module singleton `glovis_service = GlovisService()`, and `get_glovis_service()` for overrides.

The `/cars` signature must explicitly declare each scalar query and repeated `list[str] = Query(default_factory=list)` parameter, construct `GlovisCarsQuery`, and call `await asyncio.to_thread(service.get_cars, query)`. Metadata endpoints validate dependency relationships before network work. `/car-detail` validates all identifiers then calls `await asyncio.to_thread(service.get_car_detail, gn, rc, acc, atn)`.

Map failures exactly:

```python
ERROR_STATUS = {
    "proxy_unavailable": 503,
    "upstream_timeout": 504,
    "upstream_auth": 502,
    "upstream_invalid_response": 502,
    "upstream_unavailable": 502,
}


def raise_upstream(error: GlovisUpstreamError) -> NoReturn:
    raise HTTPException(
        status_code=ERROR_STATUS[error.code],
        detail={
            "code": error.code,
            "message": "Glovis provider is temporarily unavailable",
            "retryable": True,
        },
        headers={"Cache-Control": "no-store"},
    )
```

Map `ValueError` to `invalid_identifier`/422/non-retryable and `GlovisCarUnavailableError` to `car_unavailable`/404/non-retryable. Never interpolate sensitive values into public messages.

- [ ] **Step 4: Register the router and remove obsolete settings**

In `main.py`, import `glovis`, call `app.include_router(glovis.router, tags=["Glovis Auction"])`, add `get_glovis_service().get_cache_stats()` to cache stats, and invoke `clear_cache()` from the cache-clear endpoint. Eagerly create the service before scheduler startup and call `get_glovis_service().close()` during lifespan shutdown so pooled sessions close cleanly.

Delete only these unused `Settings` fields from `app/core/config.py`: `glovis_base_url`, `glovis_list_url`, `glovis_main_url`, `glovis_username`, and `glovis_password`. Confirm no runtime reference remains with:

Run: `rg -n 'glovis_(base_url|list_url|main_url|username|password)' app tests main.py`

Expected: no matches.

- [ ] **Step 5: Run route and full deterministic backend tests**

Run: `venv/bin/python -m pytest tests/test_glovis_models.py tests/test_glovis_transport.py tests/test_glovis_service.py tests/test_glovis_routes.py -q`

Expected: all new Glovis tests pass.

Run: `venv/bin/python -m pytest tests/test_ssancar_routes.py tests/test_ssancar_transport.py -q`

Expected: the existing SSANCAR suite remains green.

- [ ] **Step 6: Commit the public API**

```bash
git add app/routes/glovis.py main.py app/core/config.py tests/test_glovis_routes.py
git commit -m "feat: expose DB Auto Glovis API"
```

### Task 5: Add secret-safe opt-in live verification

**Files:**
- Create: `tests/test_glovis_live.py`
- Modify: `tests/run_glovis_tests.sh`

**Interfaces:**
- Consumes the real `GlovisService` only when `RUN_GLOVIS_LIVE=1`.
- Produces a single opt-in smoke that validates auctions, one list page, and one real detail through the configured Korean proxy.

- [ ] **Step 1: Write the opt-in smoke test**

```python
import os

import pytest

from app.models.glovis import GlovisCarsQuery
from app.services.glovis_service import GlovisService


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_GLOVIS_LIVE") != "1",
    reason="set RUN_GLOVIS_LIVE=1 to call DB Auto through configured KR proxy",
)


def test_live_auctions_list_and_detail_are_semantically_valid():
    service = GlovisService()
    auctions = service.get_auctions().auctions
    assert auctions
    auction = auctions[0]
    cars = service.get_cars(
        GlovisCarsQuery(
            atn=auction.number,
            acc=auction.acc,
            page=1,
            page_size=1,
        )
    )
    assert cars.total >= len(cars.items)
    if cars.items:
        car = cars.items[0]
        detail = service.get_car_detail(
            gn=car.gn, rc=car.rc, acc=car.acc, atn=car.atn
        )
        assert detail.data.main.gn == car.gn
        assert detail.data.main.title.strip()
```

The test must not print response bodies, vehicle identifiers, proxy configuration, cookies, or fingerprints.

- [ ] **Step 2: Replace the stale Glovis test runner**

Use this exact script so it works from any directory and performs no dependency mutation:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

exec venv/bin/python -m pytest \
  tests/test_glovis_models.py \
  tests/test_glovis_transport.py \
  tests/test_glovis_service.py \
  tests/test_glovis_routes.py \
  "$@"
```

- [ ] **Step 3: Verify default test runs never call the network**

Run: `venv/bin/python -m pytest tests/test_glovis_live.py -q`

Expected: one skipped test and zero network calls.

- [ ] **Step 4: Run the live smoke only with configured Korean proxy access**

Run: `RUN_GLOVIS_LIVE=1 venv/bin/python -m pytest tests/test_glovis_live.py -q -s`

Expected: one pass; logs contain only safe egress labels/status/count/latency. If provider access is unavailable, record the structured code and do not weaken validation or enable direct fallback.

- [ ] **Step 5: Commit live verification**

```bash
git add tests/test_glovis_live.py tests/run_glovis_tests.sh
git commit -m "test: add DB Auto Glovis live smoke"
```

### Task 6: Backend final verification and contract handoff

**Files:**
- Verify only; modify a failing file only after reproducing and diagnosing its root cause.

**Interfaces:**
- Produces a stable backend contract ready for `autobazaapp` consumption.

- [ ] **Step 1: Run all deterministic backend tests**

Run: `venv/bin/python -m pytest tests -q`

Expected: all deterministic tests pass and `test_glovis_live.py` is skipped unless explicitly enabled.

- [ ] **Step 2: Import and OpenAPI smoke**

Run: `venv/bin/python -c 'from main import app; paths=app.openapi()["paths"]; required=["/api/v1/glovis/auctions","/api/v1/glovis/cars","/api/v1/glovis/car-detail","/api/v1/glovis/health/detail"]; assert all(p in paths for p in required); print("glovis-openapi-ok")'`

Expected: `glovis-openapi-ok`.

- [ ] **Step 3: Check whitespace, secrets, and repository state**

Run: `git diff --check`

Expected: no output.

Run: `rg -n 'x-api-token=|X-Fingerprint.: .+|proxy://|glovis_password|glovis_username' app tests --glob '!tests/test_glovis_transport.py'`

Expected: no captured credential/token matches. The transport header *name* is allowed; literal secret values are not.

Run: `git status --short`

Expected: only intentional Glovis changes are present before the final task commit.

- [ ] **Step 4: Record the backend handoff contract**

Provide the frontend worker with these immutable facts: `/api/v1/glovis`, `GLOVIS_CONTRACT_VERSION=1`, one-based page, page size 15/cap 60, exact `total`, `has_next_page`, path-safe frontend `gn` transform, repeated query keys, structured error body, and complete detail response under `data`.
