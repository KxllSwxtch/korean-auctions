"""Deterministic tests for the SSANCAR-specific outbound transport."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from loguru import logger
import pytest
import requests

from app.services.ssancar_transport import (
    PayloadValidation,
    SSANCARTransport,
    SSANCARUpstreamAuthError,
    SSANCARUpstreamInvalidResponseError,
    SSANCARUpstreamTimeoutError,
    SSANCARUpstreamUnavailableError,
)


@dataclass
class StubResponse:
    status_code: int = 200
    text: str = "ok"
    headers: dict[str, str] = field(default_factory=dict)
    url: str = "https://www.ssancar.com/ajax/ajax_car_list.php"
    history: list[Any] = field(default_factory=list)


class StubSession:
    def __init__(self, outcomes: list[Any] | None = None) -> None:
        self.outcomes = list(outcomes or [])
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


def session_factory_for(*sessions: StubSession) -> Callable[[], StubSession]:
    queue = list(sessions)

    def factory() -> StubSession:
        return queue.pop(0)

    return factory


def accept_text(response: StubResponse) -> PayloadValidation[str]:
    return PayloadValidation(value=response.text, selector_count=1)


def test_direct_and_proxy_candidates_have_isolated_sessions_and_cookies():
    transport = SSANCARTransport(
        proxy_urls=[
            "http://user:secret@proxy-one.example:8000",
            "https://user:secret@proxy-two.example:8443",
        ]
    )

    candidates = transport.candidates
    assert [candidate.name for candidate in candidates] == [
        "direct",
        "proxy-1",
        "proxy-2",
    ]
    assert len({id(candidate.session) for candidate in candidates}) == 3
    assert all(candidate.session.trust_env is False for candidate in candidates)
    assert candidates[0].session.proxies == {}
    assert candidates[1].session.proxies == {
        "http": "http://user:secret@proxy-one.example:8000",
        "https": "http://user:secret@proxy-one.example:8000",
    }

    candidates[0].session.cookies.set("PHPSESSID", "direct-only")
    assert candidates[1].session.cookies.get("PHPSESSID") is None
    assert candidates[2].session.cookies.get("PHPSESSID") is None


def test_proxy_urls_are_loaded_from_json_in_configured_order(monkeypatch):
    monkeypatch.setenv(
        "SSANCAR_PROXY_URLS",
        '["http://first.example:8000", "http://second.example:8000"]',
    )
    transport = SSANCARTransport()

    assert [candidate.name for candidate in transport.candidates] == [
        "direct",
        "proxy-1",
        "proxy-2",
    ]
    assert transport.candidates[1].session.proxies["https"] == (
        "http://first.example:8000"
    )
    assert transport.candidates[2].session.proxies["https"] == (
        "http://second.example:8000"
    )


def test_obviously_korean_proxy_is_not_added():
    transport = SSANCARTransport(
        proxy_urls=[
            "http://user_area-KR:secret@proxy.example:8000",
            "http://non-kr-proxy.example:8000",
        ]
    )

    assert [candidate.name for candidate in transport.candidates] == [
        "direct",
        "proxy-1",
    ]
    assert transport.candidates[1].session.proxies["https"] == (
        "http://non-kr-proxy.example:8000"
    )


def test_login_redirect_is_auth_failure_and_redirects_are_disabled():
    direct = StubSession(
        [StubResponse(status_code=302, headers={"Location": "/bbs/login.php"})]
    )
    transport = SSANCARTransport(
        session_factory=session_factory_for(direct),
        proxy_urls=[],
    )

    with pytest.raises(SSANCARUpstreamAuthError):
        transport.request("POST", "https://www.ssancar.com/ajax/list", accept_text)

    assert len(direct.calls) == 1
    assert direct.calls[0]["allow_redirects"] is False
    assert direct.calls[0]["timeout"] == (3.0, 8.0)


@pytest.mark.parametrize(
    ("response"),
    [
        StubResponse(
            text='<html><form name="loginForm" action="/bbs/login.php"></form></html>'
        ),
        StubResponse(
            text="<html>account page</html>",
            url="https://www.ssancar.com/bbs/login.php",
        ),
    ],
)
def test_http_200_login_page_or_login_final_url_is_auth_failure(response):
    direct = StubSession([response])
    transport = SSANCARTransport(
        session_factory=session_factory_for(direct),
        proxy_urls=[],
    )

    with pytest.raises(SSANCARUpstreamAuthError):
        transport.request("GET", "https://www.ssancar.com/page/car", accept_text)


def test_direct_connection_failure_falls_back_to_proxy_once():
    direct = StubSession([requests.ConnectionError("direct down")])
    proxy = StubSession([StubResponse(text="15 cars")])
    transport = SSANCARTransport(
        session_factory=session_factory_for(direct, proxy),
        proxy_urls=["http://fallback.example:8000"],
    )

    result = transport.request(
        "POST", "https://www.ssancar.com/ajax/list", accept_text
    )

    assert result.value == "15 cars"
    assert result.egress == "proxy-1"
    assert len(direct.calls) == 1
    assert len(proxy.calls) == 1


def test_semantically_invalid_payload_advances_to_next_candidate():
    direct = StubSession([StubResponse(text="<html>redesigned markup</html>")])
    proxy = StubSession([StubResponse(text="recognized")])
    transport = SSANCARTransport(
        session_factory=session_factory_for(direct, proxy),
        proxy_urls=["http://fallback.example:8000"],
    )

    def validate(response: StubResponse) -> PayloadValidation[str]:
        if response.text != "recognized":
            raise SSANCARUpstreamInvalidResponseError(selector_count=0)
        return PayloadValidation(value=response.text, selector_count=1)

    result = transport.request(
        "POST", "https://www.ssancar.com/ajax/list", validate
    )

    assert result.value == "recognized"
    assert result.egress == "proxy-1"
    assert len(direct.calls) == len(proxy.calls) == 1


def test_complete_candidate_exhaustion_raises_unavailable():
    direct = StubSession([requests.ConnectionError("direct down")])
    proxy = StubSession([StubResponse(status_code=503, text="maintenance")])
    transport = SSANCARTransport(
        session_factory=session_factory_for(direct, proxy),
        proxy_urls=["http://fallback.example:8000"],
    )

    with pytest.raises(SSANCARUpstreamUnavailableError):
        transport.request("POST", "https://www.ssancar.com/ajax/list", accept_text)

    assert len(direct.calls) == len(proxy.calls) == 1


def test_overall_deadline_stops_before_another_candidate():
    now = [0.0]

    def slow_failure() -> StubResponse:
        now[0] = 25.0
        return StubResponse(status_code=503, text="maintenance")

    direct = StubSession([slow_failure])
    proxy = StubSession([StubResponse(text="too late")])
    transport = SSANCARTransport(
        session_factory=session_factory_for(direct, proxy),
        proxy_urls=["http://fallback.example:8000"],
        clock=lambda: now[0],
    )

    with pytest.raises(SSANCARUpstreamTimeoutError):
        transport.request("GET", "https://www.ssancar.com/page/car", accept_text)

    assert len(direct.calls) == 1
    assert proxy.calls == []


def test_request_errors_do_not_leak_proxy_credentials_to_logs():
    secret = "DO-NOT-LOG-THIS"
    direct = StubSession([requests.ConnectionError(secret)])
    proxy = StubSession([requests.ConnectionError(secret)])
    transport = SSANCARTransport(
        session_factory=session_factory_for(direct, proxy),
        proxy_urls=[f"http://user:{secret}@fallback.example:8000"],
    )
    captured: list[str] = []
    sink = logger.add(captured.append, format="{message}")
    try:
        with pytest.raises(SSANCARUpstreamUnavailableError):
            transport.request(
                "POST", "https://www.ssancar.com/ajax/list", accept_text
            )
    finally:
        logger.remove(sink)

    output = "".join(captured)
    assert secret not in output
    assert "fallback.example" not in output
    assert "direct" in output
    assert "proxy-1" in output
