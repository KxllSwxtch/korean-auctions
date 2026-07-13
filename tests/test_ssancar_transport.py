"""Deterministic tests for the SSANCAR-specific outbound transport."""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time
from typing import Any, Callable

from loguru import logger
import pytest
import requests

from app.parsers.ssancar_auth import is_ssancar_login_html
from app.services import ssancar_transport as transport_module
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


def test_http_200_login_final_url_is_auth_failure():
    response = StubResponse(
        text="<html>account page</html>",
        url="https://www.ssancar.com/bbs/login.php",
    )
    direct = StubSession([response])
    transport = SSANCARTransport(
        session_factory=session_factory_for(direct),
        proxy_urls=[],
    )

    with pytest.raises(SSANCARUpstreamAuthError):
        transport.request("GET", "https://www.ssancar.com/page/car", accept_text)


def test_passive_login_script_in_valid_html_is_not_auth():
    body = """
    <html><body>
      <p class="name"><span>[BMW] 330e</span></p>
      <script>
        if (confirm('Log in to comment?')) {
          location.href = 'https://www.ssancar.com/bbs/login.php';
        }
      </script>
    </body></html>
    """
    direct = StubSession([StubResponse(text=body)])
    transport = SSANCARTransport(
        session_factory=session_factory_for(direct),
        proxy_urls=[],
    )

    result = transport.request(
        "GET",
        "https://www.ssancar.com/page/car_view.php",
        accept_text,
        operation="detail",
    )

    assert result.value == body


@pytest.mark.parametrize("status_code", [401, 403])
def test_http_auth_status_is_auth_failure(status_code):
    direct = StubSession([StubResponse(status_code=status_code)])
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


def test_structural_login_validator_falls_back_to_valid_proxy():
    login_html = """
    <html><head><title>Login</title></head><body>
      <form name="flogin" action="/bbs/login_check.php">
        <input name="mb_id"><input type="password" name="mb_password">
      </form>
    </body></html>
    """
    direct = StubSession([StubResponse(text=login_html)])
    proxy = StubSession([StubResponse(text="valid payload")])
    transport = SSANCARTransport(
        session_factory=session_factory_for(direct, proxy),
        proxy_urls=["http://fallback.example:8000"],
    )

    def validate(response: StubResponse) -> PayloadValidation[str]:
        if is_ssancar_login_html(response.text):
            raise SSANCARUpstreamAuthError(selector_count=0)
        return PayloadValidation(value=response.text, selector_count=1)

    result = transport.request(
        "GET",
        "https://www.ssancar.com/page/car",
        validate,
        operation="detail",
    )

    assert result.value == "valid payload"
    assert result.egress == "proxy-1"
    assert len(direct.calls) == len(proxy.calls) == 1


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


def test_semaphore_acquisition_is_bounded_by_overall_deadline(monkeypatch):
    class ExhaustedSemaphore:
        def __init__(self) -> None:
            self.acquire_calls: list[float] = []
            self.release_calls = 0

        def acquire(self, *, timeout: float) -> bool:
            self.acquire_calls.append(timeout)
            return False

        def release(self) -> None:
            self.release_calls += 1

    semaphore = ExhaustedSemaphore()
    monkeypatch.setattr(transport_module, "_OUTBOUND_LIMIT", semaphore)
    direct = StubSession([StubResponse(text="must not be requested")])
    transport = SSANCARTransport(
        session_factory=session_factory_for(direct),
        proxy_urls=[],
        clock=lambda: 10.0,
    )

    with pytest.raises(SSANCARUpstreamTimeoutError):
        transport.request("GET", "https://www.ssancar.com/page/car", accept_text)

    assert semaphore.acquire_calls == [24.0]
    assert semaphore.release_calls == 0
    assert direct.calls == []


def test_semaphore_is_released_when_request_fails(monkeypatch):
    class GrantedSemaphore:
        def __init__(self) -> None:
            self.acquire_calls: list[float] = []
            self.release_calls = 0

        def acquire(self, *, timeout: float) -> bool:
            self.acquire_calls.append(timeout)
            return True

        def release(self) -> None:
            self.release_calls += 1

    semaphore = GrantedSemaphore()
    monkeypatch.setattr(transport_module, "_OUTBOUND_LIMIT", semaphore)
    direct = StubSession([requests.ConnectionError("direct down")])
    transport = SSANCARTransport(
        session_factory=session_factory_for(direct),
        proxy_urls=[],
        clock=lambda: 10.0,
    )

    with pytest.raises(SSANCARUpstreamUnavailableError):
        transport.request("GET", "https://www.ssancar.com/page/car", accept_text)

    assert semaphore.acquire_calls == [24.0]
    assert semaphore.release_calls == 1
    assert len(direct.calls) == 1


def test_request_timeout_uses_budget_remaining_after_semaphore_wait(monkeypatch):
    now = [10.0]

    class DelayedSemaphore:
        def __init__(self) -> None:
            self.release_calls = 0

        def acquire(self, *, timeout: float) -> bool:
            assert timeout == 24.0
            now[0] = 30.0
            return True

        def release(self) -> None:
            self.release_calls += 1

    semaphore = DelayedSemaphore()
    monkeypatch.setattr(transport_module, "_OUTBOUND_LIMIT", semaphore)
    direct = StubSession([StubResponse(text="within remaining budget")])
    transport = SSANCARTransport(
        session_factory=session_factory_for(direct),
        proxy_urls=[],
        clock=lambda: now[0],
    )

    result = transport.request(
        "GET",
        "https://www.ssancar.com/page/car",
        accept_text,
    )

    assert result.value == "within remaining budget"
    assert direct.calls[0]["timeout"] == (2.0, 2.0)
    assert semaphore.release_calls == 1


@pytest.mark.parametrize("blocked_stage", ["request", "validator"])
def test_overall_deadline_returns_while_attempt_work_is_still_blocked(
    monkeypatch,
    blocked_stage,
):
    work_started = threading.Event()
    release_work = threading.Event()
    limiter_released = threading.Event()

    class GrantedSemaphore:
        def acquire(self, *, timeout: float) -> bool:
            return True

        def release(self) -> None:
            limiter_released.set()

    monkeypatch.setattr(
        transport_module,
        "_OUTBOUND_LIMIT",
        GrantedSemaphore(),
    )

    def slow_response() -> StubResponse:
        if blocked_stage == "request":
            work_started.set()
            release_work.wait(timeout=1.0)
        return StubResponse(text="validated")

    def slow_validator(response: StubResponse) -> PayloadValidation[str]:
        if blocked_stage == "validator":
            work_started.set()
            release_work.wait(timeout=1.0)
        return PayloadValidation(value=response.text, selector_count=1)

    direct = StubSession([slow_response])
    transport = SSANCARTransport(
        session_factory=session_factory_for(direct),
        proxy_urls=[],
        overall_deadline_seconds=0.05,
    )

    started_at = time.monotonic()
    try:
        with pytest.raises(SSANCARUpstreamTimeoutError):
            transport.request(
                "GET",
                "https://www.ssancar.com/page/car",
                slow_validator,
            )
        elapsed = time.monotonic() - started_at
        assert work_started.is_set()
        assert elapsed < 0.25
        assert not limiter_released.is_set()
    finally:
        release_work.set()

    assert limiter_released.wait(timeout=0.5)


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


def test_logs_include_only_sanitized_operation_label():
    direct = StubSession([StubResponse(text="ok"), StubResponse(text="ok")])
    transport = SSANCARTransport(
        session_factory=session_factory_for(direct),
        proxy_urls=[],
    )
    captured: list[str] = []
    sink = logger.add(captured.append, format="{message}")
    try:
        transport.request(
            "GET",
            "https://www.ssancar.com/page/car",
            accept_text,
            operation="detail",
        )
        transport.request(
            "GET",
            "https://www.ssancar.com/page/car",
            accept_text,
            operation="detail secret\ncredential",
        )
    finally:
        logger.remove(sink)

    output = "".join(captured)
    assert "operation=detail" in output
    assert "operation=unknown" in output
    assert "credential" not in output
