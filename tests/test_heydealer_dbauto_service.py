"""Service and route tests against a stubbed transport -- no network."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.services.heydealer_dbauto_service import (
    FILTER_SECTIONS,
    ORDERING,
    SECTIONS,
    UPSTREAM_PAGE_SIZE,
    HeyDealerDbautoService,
    build_config,
    filter_params,
    is_valid_hash_id,
    normalize_lang,
)

FIXTURES = Path(__file__).parent / "fixtures" / "heydealer"
CARDS = json.loads((FIXTURES / "cars.json").read_text(encoding="utf-8"))
DETAIL = json.loads((FIXTURES / "detail-rich.json").read_text(encoding="utf-8"))
ATLAS = json.loads((FIXTURES / "accident-atlas.json").read_text(encoding="utf-8"))


class StubTransport:
    """Answers the six dbauto paths from fixtures and records every call."""

    def __init__(self, total: int = 137):
        self.calls: list[tuple[str, list[tuple[str, str]], str]] = []
        self.total = total
        self.egress_labels = ("jp-primary",)
        self.fail_with: Exception | None = None

    def get_json(self, path, params, operation, *, lane="interactive", lang="en",
                 deadline_at=None, max_attempts=None):
        self.calls.append((path, [(k, str(v)) for k, v in params], lang))
        if self.fail_with is not None:
            raise self.fail_with

        class Result:
            pass

        result = Result()
        result.egress = "jp-primary"
        result.status_code = 200
        result.elapsed_ms = 1

        if path == "/cars":
            page = int(dict(params).get("page", 1))
            # The fixture holds 30 rows but dbauto pages are 20, so rows are
            # cycled with a page-unique hash_id. That keeps every page full and
            # every id distinct, which is what the windowing assertions need.
            window = [
                {
                    **CARDS[(((page - 1) * UPSTREAM_PAGE_SIZE) + i) % len(CARDS)],
                    "hash_id": f"p{page}c{i}",
                }
                for i in range(UPSTREAM_PAGE_SIZE)
            ]
            result.value = {
                "total": self.total,
                "page": page,
                "page_size": UPSTREAM_PAGE_SIZE,
                "items": window,
            }
        elif path == "/car":
            result.value = dict(DETAIL)
        elif path == "/accident_repairs":
            result.value = ATLAS
        else:
            result.value = {
                "options": [{"value": "v1", "label": "One", "count": 3}]
            }
        return result

    def close(self):
        pass


@pytest.fixture
def service():
    return HeyDealerDbautoService(transport=StubTransport())


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def test_comma_joined_values_become_repeated_keys():
    """The frontend joins multi-selects with commas; dbauto wants repeated keys."""
    assert filter_params({"fuel": "gasoline,diesel"}) == [
        ("fuel", "gasoline"),
        ("fuel", "diesel"),
    ]


def test_scalar_filters_are_passed_through_renamed():
    assert filter_params({"min_year": 2018, "max_mileage": 50_000}) == [
        ("year_min", "2018"),
        ("mileage_max", "50000"),
    ]


def test_unknown_filter_keys_are_ignored():
    assert filter_params({"totally_made_up": "x"}) == []


def test_blank_and_none_values_are_dropped():
    assert filter_params({"brand": "", "model": None, "fuel": "lpg"}) == [("fuel", "lpg")]


def test_drop_removes_a_dimension_for_contextual_faceting():
    """A facet must not be narrowed by its own dimension."""
    assert filter_params({"brand": "b1", "fuel": "lpg"}, drop=("brand",)) == [
        ("fuel", "lpg")
    ]


@pytest.mark.parametrize(
    "given,expected",
    [("ru", "ru"), ("es", "es"), ("en", "en"), ("ko", "ko"),
     ("RU", "ru"), ("de", "en"), ("", "en"), (None, "en")],
)
def test_language_falls_back_to_english(given, expected):
    assert normalize_lang(given) == expected


@pytest.mark.parametrize(
    "value,ok",
    [("lD6m16Jn", True), ("zzzzzzzz", True), ("nope", False), ("", False),
     (None, False), ("../../etc", False), ("a" * 40, False), ("has space", False)],
)
def test_hash_id_shape_guard(value, ok):
    assert is_valid_hash_id(value) is ok


def test_only_orderings_dbauto_honours_are_offered():
    """Verified live: price and end-time orderings are accepted and ignored, so
    offering them would silently lie to the user."""
    assert set(ORDERING) == {"mileage_asc", "year_desc"}
    assert set(ORDERING.values()) == {"mileage", "year"}


def test_filter_sections_are_a_subset_of_the_known_sections():
    assert set(FILTER_SECTIONS) <= set(SECTIONS)


def test_config_prefers_the_shared_dbauto_egress_then_falls_back():
    config = build_config()
    assert config.proxy_env_prefixes[0] == "DBAUTO_PROXY"
    assert "GLOVIS_PROXY" in config.proxy_env_prefixes
    assert "KR" not in config.allowed_countries, "dbauto geo-blocks Korea"


# --------------------------------------------------------------------------- #
# Catalog
#
# Async tests follow the convention already used in tests/test_event_loop_blocking.py
# and tests/test_async_cache.py: a sync test driving one asyncio.run(). Each
# scenario runs inside a single loop so the cache's in-flight tasks stay valid.
# --------------------------------------------------------------------------- #


def test_a_default_page_is_one_upstream_call(service):
    result = asyncio.run(service.list_cars(page=1, page_size=20))
    assert len(result["cars"]) == 20
    assert result["total_count"] == 137
    assert [c[0] for c in service._transport.calls] == ["/cars"]


def test_a_wide_page_is_assembled_from_several_upstream_pages(service):
    result = asyncio.run(service.list_cars(page=1, page_size=50))
    assert len(result["cars"]) == 50
    assert len({c["hash_id"] for c in result["cars"]}) == 50
    assert len(service._transport.calls) == 3, "50 rows spans three 20-row pages"


def test_repeated_reads_are_served_from_cache(service):
    async def scenario():
        await service.list_cars(page=1)
        await service.list_cars(page=1)

    asyncio.run(scenario())
    assert len(service._transport.calls) == 1


def test_language_is_part_of_the_cache_key(service):
    async def scenario():
        await service.list_cars(page=1, lang="ru")
        await service.list_cars(page=1, lang="es")

    asyncio.run(scenario())
    assert [c[2] for c in service._transport.calls] == ["ru", "es"]


def test_ordering_is_forwarded_only_when_supported(service):
    asyncio.run(service.list_cars(page=1, order="mileage_asc"))
    assert ("ordering", "mileage") in service._transport.calls[0][1]

    service._transport.calls.clear()
    asyncio.run(service.list_cars(page=1, order="price_desc"))
    assert not any(k == "ordering" for k, _ in service._transport.calls[0][1])


def test_a_page_dbauto_echoes_differently_is_discarded():
    """A mismatched echo means the rows belong to another window."""

    class Drifting(StubTransport):
        def get_json(self, path, params, operation, **kwargs):
            result = super().get_json(path, params, operation, **kwargs)
            if path == "/cars":
                result.value["page"] = 999
            return result

    drifting = HeyDealerDbautoService(transport=Drifting())
    result = asyncio.run(drifting.list_cars(page=1))
    assert result["cars"] == []


# --------------------------------------------------------------------------- #
# Detail and diagram
# --------------------------------------------------------------------------- #


def test_malformed_ids_never_reach_the_network(service):
    assert asyncio.run(service.get_car("nope")) is None
    assert service._transport.calls == []


def test_detail_is_mapped_and_cached(service):
    async def scenario():
        car = await service.get_car("lD6m16Jn")
        await service.get_car("lD6m16Jn")
        return car

    car = asyncio.run(scenario())
    assert car["full_name"] == DETAIL["full_name"]
    assert len(service._transport.calls) == 1


def test_diagram_joins_detail_repairs_onto_the_atlas(service):
    diagram = asyncio.run(service.get_diagram("lD6m16Jn"))
    assert [v["type"] for v in diagram["views"]] == [
        "top", "side_driver", "side_passenger", "bottom"
    ]
    assert diagram["total_damages"] == len(DETAIL["accident_repairs"])


def test_the_atlas_is_fetched_once_for_every_car(service):
    """It is byte-identical across cars, so caching it per car would multiply a
    constant by the size of the catalog."""

    async def scenario():
        await service.get_diagram("lD6m16Jn")
        await service.get_diagram("QrqO9Nen")

    asyncio.run(scenario())
    atlas_calls = [c for c in service._transport.calls if c[0] == "/accident_repairs"]
    assert len(atlas_calls) == 1


def test_feed_health_tracks_the_last_success(service):
    assert service.feed_recently_healthy() is False
    asyncio.run(service.list_cars(page=1))
    assert service.feed_recently_healthy() is True
    assert service.feed_recently_healthy(within_seconds=-1) is False


# --------------------------------------------------------------------------- #
# Taxonomy
# --------------------------------------------------------------------------- #


def test_brand_facets_drop_every_cascade_dimension(service):
    asyncio.run(
        service.get_brands(
            filters={"brand": "b1", "model_group": "g1", "fuel": "lpg"}
        )
    )
    params = service._transport.calls[0][1]
    assert ("fuel", "lpg") in params
    assert not any(k in {"brand", "model_group", "model", "grade"} for k, _ in params)


def test_the_model_cascade_requires_a_brand(service):
    with pytest.raises(ValueError):
        asyncio.run(service.get_models(brand=""))


def test_the_model_cascade_sends_its_parents(service):
    asyncio.run(service.get_models(brand="b1", model_group="g1", model="m1"))
    params = dict(service._transport.calls[0][1])
    assert params["brand"] == "b1"
    assert params["model_group"] == "g1"
    assert params["model"] == "m1"


def test_a_section_is_not_narrowed_by_itself(service):
    asyncio.run(
        service.get_section("fuel", filters={"fuel": "lpg", "transmission": "auto"})
    )
    params = service._transport.calls[0][1]
    assert ("transmission", "auto") in params
    assert not any(k == "fuel" for k, _ in params)


def test_the_region_section_drops_its_differently_named_filter_key(service):
    """Section id is `location_first_part`; the /cars filter key is `location`."""
    asyncio.run(
        service.get_section("location_first_part", filters={"location": "9"})
    )
    params = service._transport.calls[0][1]
    assert not any(k == "location" for k, _ in params)
    assert ("section", "location_first_part") in params


def test_an_unknown_section_is_rejected(service):
    with pytest.raises(ValueError):
        asyncio.run(service.get_section("not_a_section"))


def test_a_failed_section_is_omitted_rather_than_returned_empty():
    """`[]` is a claim that upstream has zero options, and it gets cached."""

    class Broken(StubTransport):
        def get_json(self, path, params, operation, **kwargs):
            if path == "/section-counts" and dict(params).get("section") == "fuel":
                raise RuntimeError("boom")
            return super().get_json(path, params, operation, **kwargs)

    broken = HeyDealerDbautoService(transport=Broken())
    sections = asyncio.run(broken.get_sections(("fuel", "transmission")))
    assert "fuel" not in sections
    assert sections["transmission"] == [
        {"hash_id": "v1", "value": "v1", "name": "One", "label": "One", "count": 3}
    ]


def test_health_reports_the_egress_and_survives_an_outage(service):
    from app.services.dbauto_transport import DbautoGeoBlockedError

    healthy = asyncio.run(service.health())
    assert healthy["status"] == "ok"
    assert healthy["egress"] == ["jp-primary"]

    service._transport.fail_with = DbautoGeoBlockedError(status_code=403)
    service._list_cache.clear()
    degraded = asyncio.run(service.health())
    assert degraded["status"] == "error"
    assert degraded["code"] == "egress_geo_blocked"


def test_warming_never_raises(service):
    service._transport.fail_with = RuntimeError("upstream down")
    asyncio.run(service.warm(langs=("ru",)))


def test_the_section_fan_out_overlaps_its_upstream_calls():
    """Facet calls must run concurrently, not one after another.

    A cold `/section-counts` is seconds of round trip on its own; six of them in
    series is a page nobody waits for. This replaces the guard that used to cover
    the old per-generation fan-out, whose code is gone.

    The transport's own lane budget is exercised in tests/test_dbauto_transport.py;
    what is under test here is that the service actually gathers.
    """
    import time

    class Slow(StubTransport):
        DELAY = 0.1

        def get_json(self, path, params, operation, **kwargs):
            time.sleep(self.DELAY)
            return super().get_json(path, params, operation, **kwargs)

    sections = SECTIONS[:6]
    service = HeyDealerDbautoService(transport=Slow())

    started = time.monotonic()
    result = asyncio.run(service.get_sections(sections))
    elapsed = time.monotonic() - started

    assert set(result) == set(sections)
    serial = Slow.DELAY * len(sections)
    assert elapsed < serial * 0.6, (
        f"{len(sections)} facet calls took {elapsed:.2f}s; "
        f"serial would be ~{serial:.2f}s"
    )
