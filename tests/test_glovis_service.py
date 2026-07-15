from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
import threading
from typing import Any

import pytest

from app.models.glovis import GlovisCarsQuery
from app.services.glovis_service import (
    AUCTIONS_PATH,
    AUCTIONS_TTL,
    BRANDS_PATH,
    CACHE_MAX_ENTRIES,
    CARS_PATH,
    CARS_TTL,
    DETAIL_PATH,
    DETAIL_HEALTH_TTL,
    DETAIL_TTL,
    HEALTH_TTL,
    METADATA_TTL,
    MODELS_PATH,
    SEARCH_FORM_PATH,
    SUBMODELS_PATH,
    GlovisCarUnavailableError,
    GlovisService,
    validate_gn,
    validate_provider_id,
)
from app.services.glovis_transport import (
    GlovisTransportResult,
    GlovisUpstreamInvalidResponseError,
)
from tests.glovis_fixtures import (
    GN_RAW,
    placeholder_detail,
    raw_auctions,
    valid_detail,
    valid_filter_items,
    valid_list,
    valid_list_car,
    valid_search_form,
)


@dataclass(frozen=True)
class RecordedCall:
    path: str
    params: list[tuple[str, str]]
    operation: str
    deadline_at: float | None


class StubTransport:
    def __init__(self, responses: dict[str, Any], egress: str = "kr-test"):
        self.responses = responses
        self.egress = egress
        self.calls: list[RecordedCall] = []
        self.closed = False
        self.close_calls = 0

    def get_json(self, path, params, operation, deadline_at=None):
        self.calls.append(RecordedCall(path, list(params), operation, deadline_at))
        response = self.responses[path]
        if isinstance(response, deque):
            response = response.popleft()
        if isinstance(response, BaseException):
            raise response
        return GlovisTransportResult(
            value=deepcopy(response),
            egress=self.egress,
            status_code=200,
            elapsed_ms=1,
        )

    def call_count(self, path: str) -> int:
        return sum(call.path == path for call in self.calls)

    def close(self) -> None:
        self.closed = True
        self.close_calls += 1


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
        page_size=changes.pop("page_size", 15),
        **changes,
    )


def successful_transport() -> StubTransport:
    return StubTransport({CARS_PATH: valid_list(total=1)})


def assert_invalid_response(call) -> None:
    with pytest.raises(GlovisUpstreamInvalidResponseError):
        call()


def test_auctions_forward_english_only_and_normalize_sorted_provider_ids():
    payload = list(reversed(raw_auctions()))
    transport = StubTransport({AUCTIONS_PATH: payload})

    result = GlovisService(transport=transport).get_auctions()

    assert [auction.number for auction in result.auctions] == ["1102", "1103"]
    assert result.auctions[0].acc == "20"
    assert result.auctions[0].title == "Glovis July A"
    assert result.auctions[0].date.isoformat() == "2026-07-16"
    assert transport.calls == [
        RecordedCall(AUCTIONS_PATH, [("lang", "en")], "auctions", None)
    ]


def test_auctions_reject_duplicate_or_missing_identity():
    duplicate = raw_auctions()
    duplicate.append(deepcopy(duplicate[0]))
    missing = raw_auctions()
    missing[0].pop("atn")

    for payload in (duplicate, missing):
        service = GlovisService(transport=StubTransport({AUCTIONS_PATH: payload}))
        assert_invalid_response(service.get_auctions)


def test_cars_forwards_complete_allowlisted_query_and_exact_pagination():
    transport = StubTransport({
        CARS_PATH: {"total": 31, "items": [valid_list_car()]}
    })
    service = GlovisService(transport=transport)

    result = service.get_cars(
        GlovisCarsQuery(
            atn="1102",
            acc="20",
            page=2,
            page_size=15,
            brand="146",
            model="1171",
            submodel="2852",
            usage_history=["rental", "commercial"],
            sort_order="02",
        )
    )

    assert result.total == 31
    assert result.has_next_page is True
    assert transport.calls[0] == RecordedCall(
        CARS_PATH,
        [
            ("atn", "1102"),
            ("acc", "20"),
            ("page", "2"),
            ("page_size", "15"),
            ("lang", "en"),
            ("brand", "146"),
            ("model", "1171"),
            ("submodel", "2852"),
            ("usage_history", "rental"),
            ("usage_history", "commercial"),
            ("sort_order", "02"),
        ],
        "cars",
        None,
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(total="1"),
        lambda payload: payload.update(total=-1),
        lambda payload: payload.update(items={}),
        lambda payload: payload["items"].append(deepcopy(payload["items"][0])),
        lambda payload: payload["items"][0].update(atn="1103"),
        lambda payload: payload["items"][0].update(acc="21"),
        lambda payload: payload["items"][0].update(title=" "),
        lambda payload: payload["items"][0].update(lot_number=""),
        lambda payload: payload["items"][0].update(thumbnail="http://images.invalid/a.jpg"),
        lambda payload: payload["items"][0].update(
            thumbnail="https://user:secret@images.invalid/a.jpg"
        ),
    ],
    ids=[
        "string-total",
        "negative-total",
        "non-list-items",
        "duplicate-identity",
        "auction-mismatch",
        "account-mismatch",
        "empty-title",
        "empty-lot",
        "non-https-thumbnail",
        "credentialed-thumbnail",
    ],
)
def test_cars_reject_semantically_invalid_payloads(mutate):
    payload = valid_list()
    mutate(payload)
    service = GlovisService(transport=StubTransport({CARS_PATH: payload}))

    assert_invalid_response(lambda: service.get_cars(base_query()))


@pytest.mark.parametrize(
    ("method", "path", "params"),
    [
        ("get_brands", BRANDS_PATH, [("atn", "1102"), ("acc", "20"), ("lang", "en")]),
        (
            "get_models",
            MODELS_PATH,
            [("brand", "146"), ("atn", "1102"), ("acc", "20"), ("lang", "en")],
        ),
        (
            "get_submodels",
            SUBMODELS_PATH,
            [
                ("brand", "146"),
                ("model", "1171"),
                ("atn", "1102"),
                ("acc", "20"),
                ("lang", "en"),
            ],
        ),
    ],
)
def test_metadata_operations_forward_exact_identifiers(method, path, params):
    transport = StubTransport({path: valid_filter_items()})
    service = GlovisService(transport=transport)

    if method == "get_brands":
        result = service.get_brands(atn="1102", acc="20")
    elif method == "get_models":
        result = service.get_models(brand="146", atn="1102", acc="20")
    else:
        result = service.get_submodels(
            brand="146", model="1171", atn="1102", acc="20"
        )

    assert result.items[0].model_dump() == {
        "value": "146",
        "label": "Genesis",
        "count": 72,
    }
    assert transport.calls == [RecordedCall(path, params, method[4:], None)]


@pytest.mark.parametrize(
    "payload",
    [
        {"value": "146", "label": "Genesis", "count": 1},
        [{"value": "146", "count": 1}],
        [{"value": "146", "label": "Genesis", "count": True}],
        [["146", "Genesis", 1]],
    ],
)
def test_metadata_rejects_malformed_option_containers(payload):
    service = GlovisService(transport=StubTransport({BRANDS_PATH: payload}))
    assert_invalid_response(lambda: service.get_brands(atn="1102", acc="20"))


def test_filter_options_maps_all_search_form_fields_and_exact_params():
    transport = StubTransport({SEARCH_FORM_PATH: valid_search_form()})
    service = GlovisService(transport=transport)

    result = service.get_filter_options(atn="1102", acc="20")

    assert result.filters.colors[0].value == "White"
    assert result.filters.bid_statuses[0].value == "open"
    assert set(result.filters.model_dump()) == {
        "colors",
        "options",
        "lanes",
        "transmissions",
        "fuels",
        "insurance_damage",
        "usage_history",
        "accident_history",
        "sort_orders",
        "rooms",
        "bid_statuses",
    }
    assert transport.calls == [
        RecordedCall(
            SEARCH_FORM_PATH,
            [("atn", "1102"), ("acc", "20"), ("lang", "en")],
            "filter_options",
            None,
        )
    ]


def test_filter_options_rejects_missing_or_wrong_shape_fields():
    missing = valid_search_form()
    missing.pop("colors")
    wrong_shape = valid_search_form()
    wrong_shape["colors"] = {}

    for payload in (missing, wrong_shape):
        service = GlovisService(
            transport=StubTransport({SEARCH_FORM_PATH: payload})
        )
        assert_invalid_response(
            lambda: service.get_filter_options(atn="1102", acc="20")
        )


def test_detail_forwards_exact_identity_and_preserves_extensible_sections():
    transport = StubTransport({DETAIL_PATH: valid_detail()})
    service = GlovisService(transport=transport)

    result = service.get_car_detail(
        gn=GN_RAW, rc="3100", acc="20", atn="1102"
    )

    assert result.data.properties["future_property"] == "kept"
    assert result.data.total_table["future_total"] == 17
    assert transport.calls == [
        RecordedCall(
            DETAIL_PATH,
            [
                ("gn", GN_RAW),
                ("rc", "3100"),
                ("acc", "20"),
                ("atn", "1102"),
                ("lang", "en"),
            ],
            "car_detail",
            None,
        )
    ]


def test_placeholder_detail_is_terminal_unavailable():
    service = GlovisService(
        transport=StubTransport({DETAIL_PATH: placeholder_detail()})
    )

    with pytest.raises(GlovisCarUnavailableError) as raised:
        service.get_car_detail(
            gn=GN_RAW, rc="3100", acc="20", atn="1102"
        )

    assert raised.value.code == "car_unavailable"
    assert raised.value.retryable is False


def test_detail_rejects_identity_mismatch():
    payload = valid_detail()
    payload["main"]["gn"] = "AAAAAAAAAAAAAAAAAAAAAA=="
    service = GlovisService(transport=StubTransport({DETAIL_PATH: payload}))

    assert_invalid_response(
        lambda: service.get_car_detail(
            gn=GN_RAW, rc="3100", acc="20", atn="1102"
        )
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(options={}),
        lambda payload: payload.update(options=[{"name": "Navigation", "enabled": 1}]),
        lambda payload: payload.update(images="https://images.invalid/a.jpg"),
        lambda payload: payload.update(images=["http://images.invalid/a.jpg"]),
        lambda payload: payload.update(inspection_images=[17]),
        lambda payload: payload.update(
            performance_image="https://user:secret@images.invalid/a.jpg"
        ),
        lambda payload: payload.update(properties=[]),
        lambda payload: payload.update(accident_records={}),
    ],
    ids=[
        "options-container",
        "option-scalar",
        "images-container",
        "image-scheme",
        "image-scalar",
        "image-credentials",
        "properties-container",
        "accidents-container",
    ],
)
def test_detail_rejects_malformed_options_images_and_containers(mutate):
    payload = valid_detail()
    mutate(payload)
    service = GlovisService(transport=StubTransport({DETAIL_PATH: payload}))

    assert_invalid_response(
        lambda: service.get_car_detail(
            gn=GN_RAW, rc="3100", acc="20", atn="1102"
        )
    )


@pytest.mark.parametrize("value", ["", "abc", "1102&host=evil", "１２３", "1" * 13])
def test_provider_ids_accept_only_one_to_twelve_ascii_digits(value):
    with pytest.raises(ValueError, match="atn must contain"):
        validate_provider_id(value, "atn")


def test_provider_id_validator_returns_valid_value_unchanged():
    assert validate_provider_id("001102", "atn") == "001102"


@pytest.mark.parametrize(
    "value",
    ["", "not-base64", "YQ", "YQ===", "=YQ==", "A" * 129],
)
def test_gn_accepts_only_bounded_canonical_base64(value):
    with pytest.raises(ValueError, match="gn must be canonical base64"):
        validate_gn(value)


def test_gn_validator_returns_canonical_value_unchanged():
    assert validate_gn(GN_RAW) == GN_RAW


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
    assert service.get_cache_stats()["misses"] == 2
    assert service.get_cache_stats()["hits"] == 1


def test_cache_key_includes_full_normalized_query():
    service = GlovisService(transport=successful_transport(), clock=FakeClock())

    service.get_cars(base_query(color="White"))
    service.get_cars(base_query(color="Black"))

    assert service.get_cache_stats()["misses"] == 2


def test_cars_cache_hits_then_expires_at_exact_ttl():
    clock = FakeClock()
    transport = successful_transport()
    service = GlovisService(transport=transport, clock=clock)

    first = service.get_cars(base_query())
    clock.advance(CARS_TTL - 0.01)
    cached = service.get_cars(base_query())
    clock.advance(0.01)
    refreshed = service.get_cars(base_query())

    assert first is cached
    assert refreshed is not first
    assert transport.call_count(CARS_PATH) == 2


def test_auctions_cache_uses_exact_thirty_second_ttl():
    clock = FakeClock()
    transport = StubTransport({AUCTIONS_PATH: raw_auctions()})
    service = GlovisService(transport=transport, clock=clock)

    service.get_auctions()
    clock.advance(AUCTIONS_TTL - 0.01)
    service.get_auctions()
    clock.advance(0.01)
    service.get_auctions()

    assert transport.call_count(AUCTIONS_PATH) == 2


def test_metadata_cache_uses_exact_one_hundred_twenty_second_ttl():
    clock = FakeClock()
    transport = StubTransport({BRANDS_PATH: valid_filter_items()})
    service = GlovisService(transport=transport, clock=clock)

    service.get_brands(atn="1102", acc="20")
    clock.advance(METADATA_TTL - 0.01)
    service.get_brands(atn="1102", acc="20")
    clock.advance(0.01)
    service.get_brands(atn="1102", acc="20")

    assert transport.call_count(BRANDS_PATH) == 2


def test_detail_cache_uses_all_identity_values_and_exact_ttl():
    clock = FakeClock()
    second = valid_detail()
    second["main"]["acc"] = "21"
    transport = StubTransport({DETAIL_PATH: deque([valid_detail(), second, valid_detail()])})
    service = GlovisService(transport=transport, clock=clock)

    service.get_car_detail(gn=GN_RAW, rc="3100", acc="20", atn="1102")
    service.get_car_detail(gn=GN_RAW, rc="3100", acc="21", atn="1102")
    clock.advance(DETAIL_TTL)
    service.get_car_detail(gn=GN_RAW, rc="3100", acc="20", atn="1102")

    assert transport.call_count(DETAIL_PATH) == 3


def test_lru_never_exceeds_five_hundred_twelve_entries():
    service = GlovisService(transport=successful_transport(), clock=FakeClock())

    for page in range(1, CACHE_MAX_ENTRIES + 3):
        service.get_cars(base_query(page=page))

    stats = service.get_cache_stats()
    assert stats["size"] == 512
    assert stats["max_entries"] == 512
    assert stats["evictions"] == 2


def test_lru_hit_refreshes_recency_before_eviction():
    transport = successful_transport()
    service = GlovisService(transport=transport, clock=FakeClock())
    for page in range(1, CACHE_MAX_ENTRIES + 1):
        service.get_cars(base_query(page=page))

    service.get_cars(base_query(page=1))
    service.get_cars(base_query(page=CACHE_MAX_ENTRIES + 1))
    service.get_cars(base_query(page=2))
    service.get_cars(base_query(page=1))

    assert transport.call_count(CARS_PATH) == CACHE_MAX_ENTRIES + 2


def test_clear_cache_removes_entries_without_closing_transport():
    transport = successful_transport()
    service = GlovisService(transport=transport, clock=FakeClock())
    service.get_cars(base_query())

    service.clear_cache()

    assert service.get_cache_stats()["size"] == 0
    assert transport.closed is False
    service.get_cars(base_query())
    assert transport.call_count(CARS_PATH) == 2


class ConcurrentTransport(StubTransport):
    def __init__(self):
        super().__init__({CARS_PATH: valid_list()})
        self.barrier = threading.Barrier(2, timeout=2)

    def get_json(self, path, params, operation, deadline_at=None):
        self.barrier.wait()
        return super().get_json(path, params, operation, deadline_at)


def test_cache_loaders_for_different_keys_run_outside_global_lock():
    transport = ConcurrentTransport()
    service = GlovisService(transport=transport, clock=FakeClock())
    errors: list[BaseException] = []

    def load(color: str) -> None:
        try:
            service.get_cars(base_query(color=color))
        except BaseException as error:
            errors.append(error)

    threads = [
        threading.Thread(target=load, args=("White",)),
        threading.Thread(target=load, args=("Black",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    assert transport.call_count(CARS_PATH) == 2


def test_health_bypasses_ordinary_caches_and_has_its_own_exact_ttl():
    clock = FakeClock()
    transport = StubTransport({
        AUCTIONS_PATH: raw_auctions(),
        CARS_PATH: valid_list(total=1),
    })
    service = GlovisService(transport=transport, clock=clock)
    service.get_auctions()
    service.get_cars(base_query(page_size=1))

    first = service.check_health()
    cached = service.check_health()
    clock.advance(HEALTH_TTL)
    refreshed = service.check_health()

    assert first is cached
    assert refreshed is not first
    assert first.auction_count == 2
    assert first.list_count == 1
    assert transport.call_count(AUCTIONS_PATH) == 3
    assert transport.call_count(CARS_PATH) == 3


def test_health_chooses_first_sorted_auction_and_shares_one_deadline():
    clock = FakeClock()
    transport = StubTransport({
        AUCTIONS_PATH: list(reversed(raw_auctions())),
        CARS_PATH: valid_list(total=1),
    })
    service = GlovisService(transport=transport, clock=clock)

    probe = service.check_health()

    assert probe.egress == "kr-test"
    assert probe.checked_at.tzinfo is not None
    assert [call.deadline_at for call in transport.calls] == [24.0, 24.0]
    assert transport.calls[1].params == [
        ("atn", "1102"),
        ("acc", "20"),
        ("page", "1"),
        ("page_size", "1"),
        ("lang", "en"),
        ("sort_order", "01"),
    ]


def test_invalid_health_result_is_not_cached():
    transport = StubTransport({
        AUCTIONS_PATH: deque([[{"atn": "bad"}], raw_auctions()]),
        CARS_PATH: valid_list(total=1),
    })
    service = GlovisService(transport=transport, clock=FakeClock())

    with pytest.raises(GlovisUpstreamInvalidResponseError):
        service.check_health()
    probe = service.check_health()

    assert probe.auction_count == 2
    assert transport.call_count(AUCTIONS_PATH) == 2


def test_health_with_no_active_auction_is_healthy_without_list_request():
    transport = StubTransport({AUCTIONS_PATH: []})
    service = GlovisService(transport=transport, clock=FakeClock())

    probe = service.check_health()

    assert probe.auction_count == 0
    assert probe.list_count == 0
    assert transport.call_count(CARS_PATH) == 0


def test_detail_health_zero_count_skips_detail_and_caches_for_five_minutes():
    clock = FakeClock()
    transport = StubTransport({
        AUCTIONS_PATH: raw_auctions(),
        CARS_PATH: valid_list(total=0),
    })
    service = GlovisService(transport=transport, clock=clock)

    first = service.check_detail_health()
    clock.advance(DETAIL_HEALTH_TTL - 0.01)
    cached = service.check_detail_health()
    clock.advance(0.01)
    refreshed = service.check_detail_health()

    assert first is cached
    assert refreshed is not first
    assert first.detail_checked is True
    assert first.list_count == 0
    assert transport.call_count(AUCTIONS_PATH) == 2
    assert transport.call_count(CARS_PATH) == 2
    assert transport.call_count(DETAIL_PATH) == 0


def test_detail_health_bypasses_list_and_detail_caches_with_shared_deadline():
    clock = FakeClock()
    transport = StubTransport({
        AUCTIONS_PATH: raw_auctions(),
        CARS_PATH: valid_list(total=1),
        DETAIL_PATH: valid_detail(),
    })
    service = GlovisService(transport=transport, clock=clock)
    service.get_cars(base_query(page_size=1))
    service.get_car_detail(gn=GN_RAW, rc="3100", acc="20", atn="1102")

    probe = service.check_detail_health()
    cached = service.check_detail_health()

    assert probe is cached
    assert probe.detail_checked is True
    assert probe.auction_count == 2
    assert probe.list_count == 1
    health_calls = transport.calls[2:]
    assert [call.path for call in health_calls] == [
        AUCTIONS_PATH,
        CARS_PATH,
        DETAIL_PATH,
    ]
    assert [call.deadline_at for call in health_calls] == [24.0, 24.0, 24.0]
    assert transport.call_count(CARS_PATH) == 2
    assert transport.call_count(DETAIL_PATH) == 2


def test_failed_detail_health_is_not_cached():
    transport = StubTransport({
        AUCTIONS_PATH: raw_auctions(),
        CARS_PATH: valid_list(total=1),
        DETAIL_PATH: deque([placeholder_detail(), valid_detail()]),
    })
    service = GlovisService(transport=transport, clock=FakeClock())

    with pytest.raises(GlovisCarUnavailableError):
        service.check_detail_health()
    probe = service.check_detail_health()

    assert probe.detail_checked is True
    assert transport.call_count(AUCTIONS_PATH) == 2
    assert transport.call_count(CARS_PATH) == 2
    assert transport.call_count(DETAIL_PATH) == 2


def test_detail_health_rejects_positive_total_without_a_sample():
    transport = StubTransport({
        AUCTIONS_PATH: raw_auctions(),
        CARS_PATH: {"total": 1, "items": []},
    })
    service = GlovisService(transport=transport, clock=FakeClock())

    with pytest.raises(GlovisUpstreamInvalidResponseError):
        service.check_detail_health()


def test_health_response_never_exposes_identity_or_proxy_address():
    proxy_address = "https://proxy-user:proxy-secret@proxy.invalid:8443"
    transport = StubTransport(
        {
            AUCTIONS_PATH: raw_auctions(),
            CARS_PATH: valid_list(total=1),
            DETAIL_PATH: valid_detail(),
        },
        egress=proxy_address,
    )
    service = GlovisService(transport=transport, clock=FakeClock())

    dumped = service.check_detail_health().model_dump_json()

    assert '"egress":"unknown"' in dumped
    assert GN_RAW not in dumped
    assert "TEST-1001" not in dumped
    assert "SYNTHETICVIN00001" not in dumped
    assert proxy_address not in dumped


def test_close_delegates_to_transport_and_clears_cached_values():
    transport = successful_transport()
    service = GlovisService(transport=transport, clock=FakeClock())
    service.get_cars(base_query())

    service.close()

    assert transport.close_calls == 1
    assert service.get_cache_stats()["size"] == 0
