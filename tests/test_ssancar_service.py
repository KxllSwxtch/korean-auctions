"""Semantic-validation, caching, and week tests for ``SSANCARService``."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import requests

from app.models.ssancar import SSANCARFilters
from app.parsers.ssancar_parser import PARSE_STATUS_NOT_FOUND, PARSE_STATUS_VALID
from app.services.ssancar_service import (
    SSANCARService,
    resolve_ssancar_week,
)
from app.services.ssancar_transport import (
    PayloadValidation,
    SSANCARTransport,
    SSANCARTransportResult,
    SSANCARUpstreamAuthError,
    SSANCARUpstreamInvalidResponseError,
    SSANCARUpstreamTimeoutError,
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


class CandidateSession:
    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []
        self.headers: dict[str, str] = {}
        self.proxies: dict[str, str] = {}
        self.cookies = requests.cookies.RequestsCookieJar()
        self.trust_env = True

    def request(self, method: str, url: str, **kwargs: Any) -> StubResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            return outcome()
        return outcome


def make_failover_service(
    direct: CandidateSession,
    proxy: CandidateSession,
) -> SSANCARService:
    sessions = [direct, proxy]
    transport = SSANCARTransport(
        session_factory=lambda: sessions.pop(0),
        proxy_urls=["http://fallback.example:8000"],
    )
    service = SSANCARService(transport=transport)
    service._cache.clear()
    return service


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


def archived_detail_html() -> str:
    return (
        "<html><body>"
        + ("padding " * 100)
        + "차량을 찾을 수 없습니다"
        + "</body></html>"
    )


def passive_login_detail_html(car_no: str = "1820158") -> str:
    return valid_detail_html(car_no).replace(
        "</body>",
        """
        <script>
          if (confirm('You must log in to post a comment.')) {
            location.href = 'https://www.ssancar.com/bbs/login.php';
          }
        </script>
        </body>
        """,
    )


def actual_login_html() -> str:
    return """
    <html><head>
      <title>로그인 | Korean used car in Auction & Local market</title>
      <link rel="canonical" href="https://www.ssancar.com/bbs/login.php">
    </head><body>
      <form name="flogin" action="/bbs/login_check.php">
        <input name="mb_id">
        <input type="password" name="mb_password">
      </form>
      %s
    </body></html>
    """ % ("padding " * 100)


def make_service(
    *outcomes: Any,
    now: datetime | None = None,
    cache_clock=None,
    deadline_clock=None,
) -> tuple[SSANCARService, QueueTransport]:
    transport = QueueTransport(*outcomes)
    service_kwargs = dict(
        transport=transport,
        now_provider=(lambda: now) if now is not None else None,
        cache_clock=cache_clock,
    )
    if deadline_clock is not None:
        service_kwargs["deadline_clock"] = deadline_clock
    service = SSANCARService(**service_kwargs)
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


def test_login_html_is_auth_failure_for_list_and_count_validators():
    list_service, _ = make_service(StubResponse(actual_login_html()))
    count_service, _ = make_service(StubResponse(actual_login_html()))

    with pytest.raises(SSANCARUpstreamAuthError):
        list_service.fetch_cars(SSANCARFilters(weekNo="2"))
    with pytest.raises(SSANCARUpstreamAuthError):
        count_service.fetch_total_count(SSANCARFilters(weekNo="2"))


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


def test_list_service_drops_invalid_ids_from_mixed_parser_output(monkeypatch):
    response_html = valid_list_html("2120388387")
    service, transport = make_service(StubResponse(response_html))
    valid_car = service.parser.parse_car_list(response_html)[0]
    unicode_car = valid_car.model_copy(update={"car_no": "１２３"})
    overlong_car = valid_car.model_copy(update={"car_no": "1" * 21})
    monkeypatch.setattr(
        service.parser,
        "parse_car_list",
        lambda html: [unicode_car, valid_car, overlong_car],
    )
    filters = SSANCARFilters(weekNo="2", list="15", pages="0")

    result = service.fetch_cars(filters)
    cached = service.fetch_cars(filters)

    assert [car.car_no for car in result.cars] == ["2120388387"]
    assert cached is result
    assert len(transport.calls) == 1


@pytest.mark.parametrize("invalid_car_no", ["１２３", "1" * 21])
def test_list_with_only_invalid_id_is_failure_and_not_cached(invalid_car_no):
    service, _ = make_service(StubResponse(valid_list_html(invalid_car_no)))

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
    service, _ = make_service(StubResponse(actual_login_html()))
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


def test_valid_detail_with_passive_login_script_is_cached():
    car_no = "2120398967"
    service, transport = make_service(
        StubResponse(passive_login_detail_html(car_no))
    )

    detail, status = service.get_car_detail(car_no)
    cached, cached_status = service.get_car_detail(car_no)

    assert status == cached_status == PARSE_STATUS_VALID
    assert detail is not None and detail.car_no == car_no
    assert cached is detail
    assert len(transport.calls) == 1


def test_detail_rejects_returned_car_number_mismatch_without_caching():
    response_html = valid_detail_html("2222222").replace(
        "<html><body>",
        """
        <html><head>
          <link rel="canonical"
                href="https://www.ssancar.com/page/car_view.php?car_no=2222222">
        </head><body>
        """,
    )
    service, _ = make_service(StubResponse(response_html))
    cache_key = service._make_cache_key("detail", {"car_no": "1111111"})

    with pytest.raises(SSANCARUpstreamInvalidResponseError):
        service.get_car_detail("1111111")

    assert cache_key not in service._cache


def test_detail_unrelated_car_link_is_ignored_and_requested_id_is_backfilled():
    requested_car_no = "1111111"
    unrelated_html = valid_detail_html("2222222").replace(
        "Self link",
        "Recommended car",
    )
    service, _ = make_service(StubResponse(unrelated_html))

    detail, status = service.get_car_detail(requested_car_no)

    assert status == PARSE_STATUS_VALID
    assert detail is not None
    assert detail.car_no == requested_car_no


@pytest.mark.parametrize(
    "car_no",
    ["", "abc", "123&other=1", "1" * 21, "１２３"],
)
def test_detail_service_rejects_invalid_car_number_before_transport(car_no):
    service, transport = make_service(StubResponse(valid_detail_html()))

    with pytest.raises(ValueError):
        service.get_car_detail(car_no)

    assert transport.calls == []


def test_list_count_and_detail_use_endpoint_specific_headers_and_params():
    service, transport = make_service(
        StubResponse(valid_list_html()),
        StubResponse("1"),
        StubResponse(valid_detail_html("1820158")),
    )

    service.fetch_cars(SSANCARFilters(weekNo="2"))
    service.fetch_total_count(SSANCARFilters(weekNo="2"))
    service.get_car_detail("1820158")

    list_call, count_call, detail_call = transport.calls
    for call in (list_call, count_call):
        assert call["headers"]["X-Requested-With"] == "XMLHttpRequest"
        assert call["headers"]["Sec-Fetch-Dest"] == "empty"
    assert detail_call["url"] == service.CAR_VIEW_URL
    assert detail_call["params"] == {"car_no": "1820158"}
    assert detail_call["headers"]["Sec-Fetch-Dest"] == "document"
    assert "text/html" in detail_call["headers"]["Accept"]
    assert "X-Requested-With" not in detail_call["headers"]
    assert "Content-Type" not in detail_call["headers"]


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


def test_detail_health_zero_count_is_healthy_without_detail_probe():
    service, transport = make_service(StubResponse("0"))

    probe = service.check_detail_health("2")

    assert probe.week_number == "2"
    assert probe.upstream_count == 0
    assert probe.detail_checked is False
    assert probe.sample_car_no is None
    assert probe.egress == "direct"
    assert len(transport.calls) == 1


def test_detail_health_positive_count_validates_current_sample_and_caches_5_minutes():
    cache_now = [100.0]
    car_no = "2120398967"
    service, transport = make_service(
        StubResponse("1"),
        StubResponse(valid_list_html(car_no)),
        StubResponse(passive_login_detail_html(car_no)),
        cache_clock=lambda: cache_now[0],
    )

    first = service.check_detail_health("2")
    cache_now[0] += 299
    cached = service.check_detail_health("2")

    assert first is cached
    assert first.upstream_count == 1
    assert first.detail_checked is True
    assert first.sample_car_no == car_no
    assert first.egress == "direct"
    assert len(transport.calls) == 3


def test_detail_health_uses_one_absolute_deadline_for_all_three_requests():
    car_no = "2120398967"
    service, transport = make_service(
        StubResponse("1"),
        StubResponse(valid_list_html(car_no)),
        StubResponse(valid_detail_html(car_no)),
        deadline_clock=lambda: 100.0,
    )

    probe = service.check_detail_health("2")

    assert probe.detail_checked is True
    assert [call["deadline_at"] for call in transport.calls] == [
        124.0,
        124.0,
        124.0,
    ]


def test_detail_health_cannot_consume_three_independent_deadline_budgets():
    now = [0.0]
    car_no = "2120398967"

    def finish_at(value: float, response: StubResponse):
        def outcome() -> StubResponse:
            now[0] = value
            return response

        return outcome

    direct = CandidateSession(
        finish_at(8.0, StubResponse("1")),
        finish_at(16.0, StubResponse(valid_list_html(car_no))),
        finish_at(25.0, StubResponse(valid_detail_html(car_no))),
    )
    transport = SSANCARTransport(
        session_factory=lambda: direct,
        proxy_urls=[],
        clock=lambda: now[0],
    )
    service = SSANCARService(
        transport=transport,
        deadline_clock=lambda: now[0],
    )
    service._cache.clear()

    with pytest.raises(SSANCARUpstreamTimeoutError):
        service.check_detail_health("2")

    assert now[0] == 25.0
    assert len(direct.calls) == 3
    assert not any(
        key.startswith("ssancar:detail_health_probe:")
        for key in service._cache
    )


def test_detail_health_failure_is_not_cached():
    car_no = "2120398967"
    service, transport = make_service(
        StubResponse("1"),
        StubResponse(valid_list_html(car_no)),
        StubResponse("<html>broken detail</html>"),
        StubResponse("1"),
        StubResponse(valid_list_html(car_no)),
        StubResponse(valid_detail_html(car_no)),
    )

    with pytest.raises(SSANCARUpstreamInvalidResponseError):
        service.check_detail_health("2")
    probe = service.check_detail_health("2")

    assert probe.detail_checked is True
    assert len(transport.calls) == 6


def test_detail_health_bypasses_normal_detail_cache():
    car_no = "2120398967"
    service, transport = make_service(
        StubResponse(valid_detail_html(car_no)),
        StubResponse("1"),
        StubResponse(valid_list_html(car_no)),
        StubResponse(valid_detail_html(car_no)),
    )

    service.get_car_detail(car_no)
    probe = service.check_detail_health("2")

    assert probe.detail_checked is True
    assert len(transport.calls) == 4


def test_detail_health_empty_direct_list_fails_over_to_valid_proxy():
    car_no = "2120398967"
    direct = CandidateSession(
        StubResponse("1"),
        StubResponse(" \n\t "),
        StubResponse(valid_detail_html(car_no)),
    )
    proxy = CandidateSession(StubResponse(valid_list_html(car_no)))
    service = make_failover_service(direct, proxy)

    probe = service.check_detail_health("2")

    assert probe.detail_checked is True
    assert probe.sample_car_no == car_no
    assert len(direct.calls) == 3
    assert len(proxy.calls) == 1


def test_detail_health_bad_direct_sample_fails_over_to_valid_proxy(monkeypatch):
    car_no = "2120398967"
    direct = CandidateSession(
        StubResponse("1"),
        StubResponse("bad-sample"),
        StubResponse(valid_detail_html(car_no)),
    )
    proxy = CandidateSession(StubResponse("valid-sample"))
    service = make_failover_service(direct, proxy)

    def validate_list(response):
        sample = "not-a-number" if response.text == "bad-sample" else car_no
        return PayloadValidation(
            value=[SimpleNamespace(car_no=sample)],
            selector_count=1,
        )

    monkeypatch.setattr(service, "_validate_car_list_response", validate_list)

    probe = service.check_detail_health("2")

    assert probe.detail_checked is True
    assert probe.sample_car_no == car_no
    assert len(direct.calls) == 3
    assert len(proxy.calls) == 1


def test_detail_health_archived_direct_detail_fails_over_to_valid_proxy():
    car_no = "2120398967"
    direct = CandidateSession(
        StubResponse("1"),
        StubResponse(valid_list_html(car_no)),
        StubResponse(archived_detail_html()),
    )
    proxy = CandidateSession(StubResponse(valid_detail_html(car_no)))
    service = make_failover_service(direct, proxy)

    probe = service.check_detail_health("2")

    assert probe.detail_checked is True
    assert probe.sample_car_no == car_no
    assert len(direct.calls) == 3
    assert len(proxy.calls) == 1


def test_ordinary_archived_detail_remains_not_found_without_failover():
    car_no = "2120398967"
    direct = CandidateSession(StubResponse(archived_detail_html()))
    proxy = CandidateSession(StubResponse(valid_detail_html(car_no)))
    service = make_failover_service(direct, proxy)

    detail, status = service.get_car_detail(car_no)

    assert detail is None
    assert status == PARSE_STATUS_NOT_FOUND
    assert len(direct.calls) == 1
    assert proxy.calls == []


@pytest.mark.parametrize("sample_car_no", [None, "", "not-a-number"])
def test_detail_health_malformed_sample_is_structured_upstream_invalid(
    sample_car_no,
    monkeypatch,
):
    direct = CandidateSession(
        StubResponse("1"),
        StubResponse("bad-direct-sample"),
    )
    proxy = CandidateSession(StubResponse("bad-proxy-sample"))
    service = make_failover_service(direct, proxy)

    monkeypatch.setattr(
        service,
        "_validate_car_list_response",
        lambda response: PayloadValidation(
            value=[SimpleNamespace(car_no=sample_car_no)],
            selector_count=1,
        ),
    )

    with pytest.raises(SSANCARUpstreamInvalidResponseError):
        service.check_detail_health("2")

    assert len(direct.calls) == 2
    assert len(proxy.calls) == 1
