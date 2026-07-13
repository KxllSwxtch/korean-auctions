"""Semantic-validation, caching, and week tests for ``SSANCARService``."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.models.ssancar import SSANCARFilters
from app.parsers.ssancar_parser import PARSE_STATUS_VALID
from app.services.ssancar_service import (
    SSANCARService,
    resolve_ssancar_week,
)
from app.services.ssancar_transport import (
    SSANCARTransportResult,
    SSANCARUpstreamAuthError,
    SSANCARUpstreamInvalidResponseError,
    SSANCARUpstreamUnavailableError,
)


@dataclass
class StubResponse:
    text: str
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    url: str = "https://www.ssancar.com/ajax/fixture"
    history: list[Any] = field(default_factory=list)


class QueueTransport:
    """Small deterministic transport that still runs service validators."""

    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, validator, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        validation = validator(outcome)
        return SSANCARTransportResult(
            value=validation.value,
            egress="direct",
            status_code=outcome.status_code,
            selector_count=validation.selector_count,
            elapsed_ms=1,
        )


def valid_list_html(car_no: str = "2120388387") -> str:
    return f"""
    <ul>
      <li>
        <a href="/page/car_view.php?car_no={car_no}">
          <span class="num">1001</span>
          <span class="name">[Kia] The New K3 1.6 Gasoline Trendy</span>
          <ul class="detail"><li>
            <span>2022.03</span><span>A/T</span><span>Gasoline</span>
            <span>75,984 Km</span><span>A/4</span>
          </li></ul>
          <p class="money">₩ <span class="num">10,400,000</span></p>
          <img src="https://img.example/1.jpg" />
        </a>
      </li>
    </ul>
    """


def valid_detail_html(car_no: str = "1820158") -> str:
    return f"""
    <html><body>
      <a href="/page/car_view.php?car_no={car_no}">Self link</a>
      <p class="num"><span>STK-001</span></p>
      <p class="name"><span>Hyundai Sonata 2.0</span></p>
      <ul class="detail"><li>
        <span>2020</span><span>A/T</span><span>Gasoline</span>
      </li></ul>
      <p class="money"><span>$15,000</span></p>
      {'X' * 600}
    </body></html>
    """


def make_service(
    *outcomes: Any,
    now: datetime | None = None,
    cache_clock=None,
) -> tuple[SSANCARService, QueueTransport]:
    transport = QueueTransport(*outcomes)
    service = SSANCARService(
        transport=transport,
        now_provider=(lambda: now) if now is not None else None,
        cache_clock=cache_clock,
    )
    service._cache.clear()
    return service, transport


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 7, 13, 17, 59, 59, tzinfo=ZoneInfo("Asia/Seoul")), "5"),
        (datetime(2026, 7, 13, 18, 0, 0, tzinfo=ZoneInfo("Asia/Seoul")), "2"),
        (datetime(2026, 7, 14, 9, 0, 0, tzinfo=ZoneInfo("Asia/Seoul")), "2"),
        (datetime(2026, 7, 16, 17, 59, 59, tzinfo=ZoneInfo("Asia/Seoul")), "2"),
        (datetime(2026, 7, 16, 18, 0, 0, tzinfo=ZoneInfo("Asia/Seoul")), "5"),
        (datetime(2026, 7, 19, 23, 59, 0, tzinfo=ZoneInfo("Asia/Seoul")), "5"),
    ],
)
def test_seoul_week_boundaries(now: datetime, expected: str):
    assert resolve_ssancar_week(None, now=now) == expected


def test_supplied_valid_week_is_preserved_and_invalid_legacy_value_is_normalized():
    monday_morning = datetime(
        2026, 7, 13, 10, 0, tzinfo=ZoneInfo("Asia/Seoul")
    )
    assert resolve_ssancar_week("2", now=monday_morning) == "2"
    assert resolve_ssancar_week(5, now=monday_morning) == "5"
    assert resolve_ssancar_week("4", now=monday_morning) == "5"
    assert resolve_ssancar_week("garbage", now=monday_morning) == "5"


def test_whitespace_list_is_a_valid_empty_success_and_is_cached():
    service, transport = make_service(StubResponse(" \n\t "))
    filters = SSANCARFilters(weekNo="2", list="15", pages="0")

    first = service.fetch_cars(filters)
    second = service.fetch_cars(filters)

    assert first.success is True
    assert first.cars == []
    assert first.week_number == "2"
    assert second.cars == []
    assert len(transport.calls) == 1


def test_valid_list_markup_returns_cars_and_selected_week():
    service, transport = make_service(StubResponse(valid_list_html()))

    result = service.fetch_cars(
        SSANCARFilters(weekNo="2", list="15", pages="0")
    )

    assert result.success is True
    assert result.week_number == "2"
    assert [car.car_no for car in result.cars] == ["2120388387"]
    assert transport.calls[0]["data"]["weekNo"] == "2"


def test_non_empty_unrecognized_list_markup_is_failure_and_not_cached():
    service, _ = make_service(
        StubResponse("<html><body><h1>New design</h1></body></html>")
    )
    filters = SSANCARFilters(weekNo="2", list="15", pages="0")

    with pytest.raises(SSANCARUpstreamInvalidResponseError):
        service.fetch_cars(filters)

    assert not any(key.startswith("ssancar:cars:") for key in service._cache)


def test_recognized_nodes_that_parse_no_cars_are_failure_and_not_cached(monkeypatch):
    service, _ = make_service(StubResponse(valid_list_html()))
    monkeypatch.setattr(service.parser, "parse_car_list", lambda html: [])

    with pytest.raises(SSANCARUpstreamInvalidResponseError):
        service.fetch_cars(SSANCARFilters(weekNo="2"))

    assert not any(key.startswith("ssancar:cars:") for key in service._cache)


def test_recognized_node_with_unusable_identity_is_failure_and_not_cached():
    drifted_html = """
    <ul>
      <li>
        <a href="/page/car_view.php?car_no=not-numeric">
          <span class="num">1001</span>
          <span class="name">   </span>
          <ul class="detail"><li><span>2022</span></li></ul>
        </a>
      </li>
    </ul>
    """
    service, _ = make_service(StubResponse(drifted_html))

    with pytest.raises(SSANCARUpstreamInvalidResponseError):
        service.fetch_cars(SSANCARFilters(weekNo="2"))

    assert not any(key.startswith("ssancar:cars:") for key in service._cache)


def test_invalid_legacy_week_is_normalized_before_cache_and_request():
    now = datetime(2026, 7, 13, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    service, transport = make_service(StubResponse(" "), now=now)

    result = service.fetch_cars(SSANCARFilters(weekNo="4"))

    assert result.week_number == "5"
    assert transport.calls[0]["data"]["weekNo"] == "5"


def test_search_and_count_pass_all_ui_filters_to_upstream_without_overwrite():
    service, transport = make_service(
        StubResponse(valid_list_html()),
        StubResponse("17"),
    )
    filters = SSANCARFilters(
        weekNo="2",
        color="White",
        gearbox="A/T",
        kmFrom="12345",
        kmTo="67890",
        no="STK-900",
    )

    service.search_cars(filters)
    service.fetch_total_count(filters)

    expected = {
        "color": "White",
        "gearbox": "A/T",
        "kmFrom": "12345",
        "kmTo": "67890",
        "no": "STK-900",
    }
    assert len(transport.calls) == 2
    for call in transport.calls:
        assert {key: call["data"][key] for key in expected} == expected


def test_comma_formatted_count_is_normalized_and_cached():
    service, transport = make_service(StubResponse("1,010"))
    filters = SSANCARFilters(weekNo="2")

    assert service.fetch_total_count(filters) == 1010
    assert service.fetch_total_count(filters) == 1010
    assert len(transport.calls) == 1
    assert transport.calls[0]["data"]["weekNo"] == "2"


def test_numeric_zero_count_is_valid_and_cached():
    service, transport = make_service(StubResponse(" 0\n"))

    assert service.fetch_total_count(SSANCARFilters(weekNo="5")) == 0
    assert service.fetch_total_count(SSANCARFilters(weekNo="5")) == 0
    assert len(transport.calls) == 1


@pytest.mark.parametrize("payload", ["<html>0</html>", "1,01", "about 12", ""])
def test_invalid_count_payload_is_failure_and_not_cached(payload: str):
    service, _ = make_service(StubResponse(payload))

    with pytest.raises(SSANCARUpstreamInvalidResponseError):
        service.fetch_total_count(SSANCARFilters(weekNo="2"))

    assert not any(key.startswith("ssancar:total_count:") for key in service._cache)


def test_detail_login_payload_is_auth_failure_and_not_cached():
    body = "<html><body>" + ("padding " * 100) + (
        '<form name="loginForm" action="/bbs/login.php"></form>'
    ) + "</body></html>"
    service, _ = make_service(StubResponse(body))
    cache_key = service._make_cache_key("detail", {"car_no": "9999999"})

    with pytest.raises(SSANCARUpstreamAuthError):
        service.get_car_detail("9999999")

    assert cache_key not in service._cache


def test_invalid_detail_does_not_poison_cache():
    service, _ = make_service(StubResponse(""))
    cache_key = service._make_cache_key("detail", {"car_no": "1820158"})

    with pytest.raises(SSANCARUpstreamInvalidResponseError):
        service.get_car_detail("1820158")

    assert cache_key not in service._cache


def test_valid_detail_is_cached_and_returned():
    car_no = "1820158"
    service, transport = make_service(StubResponse(valid_detail_html(car_no)))

    detail, status = service.get_car_detail(car_no)
    detail_again, status_again = service.get_car_detail(car_no)

    assert status == status_again == PARSE_STATUS_VALID
    assert detail is not None and detail.car_no == car_no
    assert detail_again is detail
    assert len(transport.calls) == 1


def test_detail_transport_failure_does_not_cache():
    service, _ = make_service(SSANCARUpstreamUnavailableError())
    cache_key = service._make_cache_key("detail", {"car_no": "1820158"})

    with pytest.raises(SSANCARUpstreamUnavailableError):
        service.get_car_detail("1820158")

    assert cache_key not in service._cache


def test_health_uses_its_own_30_second_validated_probe_cache():
    cache_now = [100.0]
    service, transport = make_service(
        StubResponse("0"),
        StubResponse("7"),
        cache_clock=lambda: cache_now[0],
    )

    first = service.check_health("2")
    cache_now[0] += 29
    cached = service.check_health("2")
    cache_now[0] += 2
    refreshed = service.check_health("2")

    assert first.upstream_count == cached.upstream_count == 0
    assert refreshed.upstream_count == 7
    assert first.egress == cached.egress == refreshed.egress == "direct"
    assert len(transport.calls) == 2


def test_health_probe_does_not_reuse_normal_count_cache():
    service, transport = make_service(StubResponse("1,010"), StubResponse("0"))
    filters = SSANCARFilters(weekNo="2")

    assert service.fetch_total_count(filters) == 1010
    health = service.check_health("2")

    assert health.upstream_count == 0
    assert len(transport.calls) == 2


def test_invalid_health_probe_is_not_cached():
    service, transport = make_service(
        StubResponse("<html>login or drift</html>"),
        StubResponse("3"),
    )

    with pytest.raises(SSANCARUpstreamInvalidResponseError):
        service.check_health("2")

    assert service.check_health("2").upstream_count == 3
    assert len(transport.calls) == 2
