"""Deterministic tests for the Korean-only DB Auto transport."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import threading
import time
from typing import Any

from loguru import logger
import pytest
import requests

from app.services import glovis_transport as transport_module
from app.services.glovis_transport import (
    GlovisProxyUnavailableError,
    GlovisTransport,
    GlovisUpstreamAuthError,
    GlovisUpstreamInvalidResponseError,
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

    def json(self) -> Any:
        if isinstance(self.json_data, BaseException):
            raise self.json_data
        return self.json_data


class StubSession:
    def __init__(self, outcomes: list[Any] | None = None) -> None:
        self.outcomes = list(outcomes or [])
        self.calls: list[dict[str, Any]] = []
        self.headers: dict[str, str] = {}
        self.proxies: dict[str, str] = {}
        self.cookies = requests.cookies.RequestsCookieJar()
        self.trust_env = True
        self.close_calls = 0
        self.closed = threading.Event()

    def request(self, method: str, url: str, **kwargs: Any) -> StubResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            outcome = outcome()
        if outcome.set_cookie:
            self.cookies.set(*outcome.set_cookie)
        return outcome

    def close(self) -> None:
        self.close_calls += 1
        self.closed.set()


class StubProxyPool:
    def __init__(self, candidates: list[tuple[Any, str]]) -> None:
        self.candidates = list(candidates)
        self.index = 0

    def __len__(self) -> int:
        return len(self.candidates)

    def current(self) -> tuple[Any, str]:
        return self.candidates[self.index]

    def advance(self) -> tuple[Any, str]:
        self.index = (self.index + 1) % len(self.candidates)
        return self.current()


def token_response(value: str) -> StubResponse:
    return StubResponse(
        json_data={"ok": True},
        set_cookie=("x-api-token", value),
    )


def make_transport(
    *sessions: StubSession,
    overall_deadline_seconds: float = 24.0,
) -> GlovisTransport:
    queue = list(sessions)
    candidate_type = getattr(transport_module, "GlovisProxyCandidate", None)
    assert candidate_type is not None
    candidates = [
        candidate_type(
            country="JP",
            egress=f"jp-{index}",
            proxy_url=f"http://user-{index}:pass-{index}@proxy-{index}.invalid:8080",
        )
        for index in range(1, len(sessions) + 1)
    ]
    return GlovisTransport(
        proxy_candidates=candidates,
        session_factory=lambda: queue.pop(0),
        fingerprint_factory=lambda: "fingerprint-a",
        overall_deadline_seconds=overall_deadline_seconds,
    )


def test_missing_proxy_pool_fails_closed_without_creating_direct_session() -> None:
    created: list[StubSession] = []
    with pytest.raises(GlovisProxyUnavailableError):
        GlovisTransport(
            proxy_candidates=[],
            session_factory=lambda: created.append(StubSession()) or created[-1],
        )
    assert created == []


def test_glovis_proxy_configuration_is_loaded_only_from_dedicated_environment() -> None:
    loader = getattr(transport_module, "load_glovis_proxy_candidates", None)
    assert loader is not None

    candidates = loader(
        {
            "GLOVIS_PROXY_HOST": "proxy.example.invalid:8443",
            "GLOVIS_PROXY_USERNAME": "service-account",
            "GLOVIS_PROXY_PASSWORD": "managed-secret",
            "GLOVIS_PROXY_COUNTRY": "jp",
            "GLOVIS_PROXY_EGRESS_LABEL": " JP-Primary ",
        }
    )

    assert len(candidates) == 1
    assert candidates[0].country == "JP"
    assert candidates[0].egress == "jp-primary"
    assert candidates[0].proxy_url.startswith("http://")
    assert candidates[0].identity


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {
            "GLOVIS_PROXY_USERNAME": "service-account",
            "GLOVIS_PROXY_PASSWORD": "managed-secret",
            "GLOVIS_PROXY_COUNTRY": "JP",
            "GLOVIS_PROXY_EGRESS_LABEL": "jp-primary",
        },
        {
            "GLOVIS_PROXY_HOST": "proxy.example.invalid:8443",
            "GLOVIS_PROXY_PASSWORD": "managed-secret",
            "GLOVIS_PROXY_COUNTRY": "JP",
            "GLOVIS_PROXY_EGRESS_LABEL": "jp-primary",
        },
        {
            "GLOVIS_PROXY_HOST": "proxy.example.invalid:8443",
            "GLOVIS_PROXY_USERNAME": "service-account",
            "GLOVIS_PROXY_COUNTRY": "JP",
            "GLOVIS_PROXY_EGRESS_LABEL": "jp-primary",
        },
    ],
)
def test_incomplete_glovis_proxy_environment_fails_closed(environment) -> None:
    loader = getattr(transport_module, "load_glovis_proxy_candidates", None)
    assert loader is not None

    with pytest.raises(GlovisProxyUnavailableError):
        loader(environment)


def _candidate(*, country: str, egress: str, proxy_url: str):
    candidate_type = getattr(transport_module, "GlovisProxyCandidate", None)
    assert candidate_type is not None
    return candidate_type(country=country, egress=egress, proxy_url=proxy_url)


@pytest.mark.parametrize("country", ["", "KR", "KOREA", "KR-US"])
def test_korean_and_malformed_proxy_candidates_are_rejected_before_session_creation(
    country: str,
) -> None:
    """KR is the rejection case now, not the requirement.

    cars.dbauto.kr geo-blocks Korea, so a Korean egress is the one configuration
    guaranteed to 403 — and it used to be the only one this transport accepted,
    which is why Glovis served 502 in production."""
    created: list[StubSession] = []
    candidate = _candidate(
        country=country,
        egress="jp-primary",
        proxy_url="http://service:managed@proxy.example.invalid:8443",
    )

    with pytest.raises(GlovisProxyUnavailableError):
        GlovisTransport(
            proxy_candidates=[candidate],
            session_factory=lambda: created.append(StubSession()) or created[-1],
        )

    assert created == []


@pytest.mark.parametrize(
    "proxy_url",
    [
        "",
        "proxy.example.invalid:8443",
        "ftp://service:managed@proxy.example.invalid:8443",
        "http://proxy.example.invalid:8443",
        "http://:managed@proxy.example.invalid:8443",
        "http://service:@proxy.example.invalid:8443",
        "http://service:managed@proxy.example.invalid",
        "http://service:managed@proxy.example.invalid:8443/path",
        "http://service:managed@proxy.example.invalid:8443?region=kr",
    ],
)
def test_blank_or_malformed_proxy_urls_are_rejected_before_session_creation(
    proxy_url: str,
) -> None:
    created: list[StubSession] = []
    candidate = _candidate(country="JP", egress="jp-primary", proxy_url=proxy_url)

    with pytest.raises(GlovisProxyUnavailableError):
        GlovisTransport(
            proxy_candidates=[candidate],
            session_factory=lambda: created.append(StubSession()) or created[-1],
        )

    assert created == []


@pytest.mark.parametrize(
    "egress",
    [
        "",
        "primary",
        "http://proxy.example.invalid:8443",
        "jp-proxy.example.invalid",
        "jp-service-account",
        "jp-managed-secret",
        "jp-primary@proxy",
    ],
)
def test_unsafe_or_secret_bearing_egress_labels_are_rejected(
    egress: str,
) -> None:
    created: list[StubSession] = []
    candidate = _candidate(
        country="JP",
        egress=egress,
        proxy_url=(
            "http://service-account:managed-secret@proxy.example.invalid:8443"
        ),
    )

    with pytest.raises(GlovisProxyUnavailableError):
        GlovisTransport(
            proxy_candidates=[candidate],
            session_factory=lambda: created.append(StubSession()) or created[-1],
        )

    assert created == []


def test_duplicate_proxy_candidate_identity_is_rejected_before_sessions() -> None:
    created: list[StubSession] = []
    first = _candidate(
        country="JP",
        egress="jp-primary",
        proxy_url="http://service:managed@proxy.example.invalid:8443",
    )
    duplicate = _candidate(
        country="jp",
        egress="jp-secondary",
        proxy_url="http://service:changed@proxy.example.invalid:8443",
    )

    with pytest.raises(GlovisProxyUnavailableError):
        GlovisTransport(
            proxy_candidates=[first, duplicate],
            session_factory=lambda: created.append(StubSession()) or created[-1],
        )

    assert created == []


@pytest.mark.parametrize(
    "path",
    [
        "https://outside.invalid/api/auctions/glovis/cars",
        "//outside.invalid/api/auctions/glovis/cars",
        "/api/auctions/glovis/../cars",
        "/api/auctions/glovis/cars?lang=ko",
        "/api/auth/token",
    ],
)
def test_reviewer_rejects_non_allowlisted_api_destination(path: str) -> None:
    session = StubSession()
    transport = make_transport(session)

    with pytest.raises(ValueError, match="approved DB Auto Glovis endpoint"):
        transport.get_json(path, [], operation="cars")

    assert session.calls == []


@pytest.mark.parametrize(
    "params",
    [
        [("atn", "1102")],
        [("lang", "ko"), ("atn", "1102")],
        [("lang", "ko"), ("atn", "1102"), ("lang", "en")],
    ],
)
def test_reviewer_forces_exactly_one_english_language_parameter(
    params: list[tuple[str, str]],
) -> None:
    session = StubSession([token_response("token"), StubResponse(json_data=[])])
    transport = make_transport(session)

    transport.get_json(CARS_PATH, params, operation="cars")

    upstream_params = session.calls[-1]["params"]
    assert upstream_params.count(("lang", "en")) == 1
    assert [value for key, value in upstream_params if key == "lang"] == ["en"]
    assert ("atn", "1102") in upstream_params


def test_token_and_api_use_same_proxy_session_and_matching_fingerprint() -> None:
    session = StubSession(
        [
            StubResponse(
                json_data={"ok": True},
                set_cookie=("x-api-token", "token"),
            ),
            StubResponse(json_data={"total": 0, "items": []}),
        ]
    )
    transport = GlovisTransport(
        proxy_candidates=[
            _candidate(
                country="JP",
                egress="jp-primary",
                proxy_url="http://user:pass@redacted.invalid:8080",
            )
        ],
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
    assert session.proxies["https"] == "http://user:pass@redacted.invalid:8080"
    assert session.trust_env is False
    assert "X-Fingerprint" not in session.headers
    assert not any(key.lower().startswith("sec-ch-") for key in session.headers)
    assert all(call["allow_redirects"] is False for call in session.calls)


def test_validated_proxy_candidates_are_capped_at_four() -> None:
    sessions = [StubSession() for _ in range(4)]
    available = list(sessions)
    candidates = [
        _candidate(
            country="JP",
            egress=f"jp-{index}",
            proxy_url=(
                f"http://user-{index}:pass-{index}@pool-proxy-{index}.invalid:8080"
            ),
        )
        for index in range(1, 6)
    ]

    transport = GlovisTransport(
        proxy_candidates=candidates,
        session_factory=lambda: available.pop(0),
    )

    assert len(sessions) == 4
    assert [session.proxies["https"] for session in sessions] == [
        f"http://user-{index}:pass-{index}@pool-proxy-{index}.invalid:8080"
        for index in range(1, 5)
    ]
    assert all(session.trust_env is False for session in sessions)
    transport.close()


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_refreshes_once_on_same_slot(status: int) -> None:
    session = StubSession(
        [
            token_response("first"),
            StubResponse(status_code=status, json_data={"detail": "expired"}),
            token_response("second"),
            StubResponse(json_data={"items": [], "total": 0}),
        ]
    )
    transport = make_transport(session)

    transport.get_json(CARS_PATH, [], operation="cars")

    assert [call["method"] for call in session.calls] == [
        "POST",
        "GET",
        "POST",
        "GET",
    ]


def test_second_auth_failure_is_reported_after_one_refresh() -> None:
    session = StubSession(
        [
            token_response("first"),
            StubResponse(status_code=401, json_data={"detail": "expired"}),
            token_response("second"),
            StubResponse(status_code=403, json_data={"detail": "denied"}),
        ]
    )

    with pytest.raises(GlovisUpstreamAuthError) as raised:
        make_transport(session).get_json(CARS_PATH, [], operation="cars")

    assert raised.value.code == "upstream_auth"
    assert raised.value.status_code == 403
    assert raised.value.egress == "jp-1"
    assert len(session.calls) == 4


def test_reviewer_auth_refresh_is_once_across_rotated_slots() -> None:
    first = StubSession(
        [
            token_response("first"),
            StubResponse(status_code=401, json_data={"detail": "expired"}),
            token_response("refreshed"),
            requests.ConnectionError("retry request unavailable"),
        ]
    )
    second = StubSession(
        [
            token_response("second"),
            StubResponse(status_code=403, json_data={"detail": "denied"}),
        ]
    )

    with pytest.raises(GlovisUpstreamAuthError) as raised:
        make_transport(first, second).get_json(CARS_PATH, [], operation="cars")

    assert raised.value.status_code == 403
    assert [call["method"] for call in first.calls] == [
        "POST",
        "GET",
        "POST",
        "GET",
    ]
    assert [call["method"] for call in second.calls] == ["POST", "GET"]


def test_token_is_reused_at_109_seconds_and_refreshed_at_110_seconds() -> None:
    now = [0.0]
    session = StubSession(
        [
            token_response("first"),
            StubResponse(json_data=[]),
            StubResponse(json_data=[]),
            token_response("second"),
            StubResponse(json_data=[]),
        ]
    )
    transport = GlovisTransport(
        proxy_candidates=[
            _candidate(
                country="JP",
                egress="jp-1",
                proxy_url="http://user:pass@proxy-1.invalid:8080",
            )
        ],
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
        "POST",
        "GET",
        "GET",
        "POST",
        "GET",
    ]


def test_retryable_failure_rotates_complete_proxy_session() -> None:
    first = StubSession(
        [token_response("one"), requests.ConnectionError("unavailable")]
    )
    second = StubSession([token_response("two"), StubResponse(json_data=[])])

    result = make_transport(first, second).get_json(
        AUCTIONS_PATH,
        [],
        operation="auctions",
    )

    assert result.egress == "jp-2"
    assert len(first.calls) == 2
    assert len(second.calls) == 2


@pytest.mark.parametrize("status", [429, 500, 503])
def test_retryable_http_status_rotates_complete_proxy_session(status: int) -> None:
    first = StubSession(
        [
            token_response("one"),
            StubResponse(status_code=status, json_data={"detail": "unavailable"}),
        ]
    )
    second = StubSession([token_response("two"), StubResponse(json_data=[])])

    result = make_transport(first, second).get_json(
        AUCTIONS_PATH,
        [],
        operation="auctions",
    )

    assert result.egress == "jp-2"
    assert len(first.calls) == len(second.calls) == 2


@pytest.mark.parametrize(
    ("response", "error_type", "code"),
    [
        (
            StubResponse(status_code=401, json_data={"detail": "denied"}),
            GlovisUpstreamAuthError,
            "upstream_auth",
        ),
        (
            StubResponse(status_code=503, json_data={"detail": "unavailable"}),
            GlovisUpstreamUnavailableError,
            "upstream_unavailable",
        ),
        (
            StubResponse(json_data={"ok": False}),
            GlovisUpstreamInvalidResponseError,
            "upstream_invalid_response",
        ),
    ],
)
def test_token_failure_uses_structured_error(
    response: StubResponse,
    error_type: type[Exception],
    code: str,
) -> None:
    session = StubSession([response])

    with pytest.raises(error_type) as raised:
        make_transport(session).get_json(CARS_PATH, [], operation="cars")

    assert getattr(raised.value, "code") == code


@pytest.mark.parametrize(
    "response",
    [
        StubResponse(json_data=ValueError("not json"), text="not json"),
        StubResponse(json_data="scalar", text='"scalar"'),
    ],
)
def test_http_200_requires_json_object_or_array(response: StubResponse) -> None:
    session = StubSession([token_response("one"), response])

    with pytest.raises(GlovisUpstreamInvalidResponseError) as raised:
        make_transport(session).get_json(CARS_PATH, [], operation="cars")

    assert raised.value.code == "upstream_invalid_response"
    assert raised.value.status_code == 200


def test_expired_shared_deadline_stops_before_session_request() -> None:
    now = [50.0]
    session = StubSession([token_response("unused")])
    transport = GlovisTransport(
        proxy_candidates=[
            _candidate(
                country="JP",
                egress="jp-1",
                proxy_url="http://user:pass@proxy-1.invalid:8080",
            )
        ],
        session_factory=lambda: session,
        fingerprint_factory=lambda: "fingerprint-a",
        clock=lambda: now[0],
    )

    with pytest.raises(GlovisUpstreamTimeoutError):
        transport.get_json(
            CARS_PATH,
            [],
            operation="cars",
            deadline_at=50.0,
        )

    assert session.calls == []


def test_reviewer_every_request_uses_exact_connect_and_read_timeouts() -> None:
    session = StubSession(
        [
            token_response("first"),
            StubResponse(status_code=401, json_data={"detail": "expired"}),
            token_response("second"),
            StubResponse(json_data=[]),
        ]
    )
    transport = make_transport(session, overall_deadline_seconds=0.5)

    transport.get_json(CARS_PATH, [], operation="cars")

    # Against the module constants, not literals: this test exists to prove every
    # request carries the configured pair, and hardcoding the numbers made it
    # fail for the wrong reason when the read ceiling was raised to match the
    # host's real latency.
    expected = (
        transport_module.CONNECT_TIMEOUT_SECONDS,
        transport_module.READ_TIMEOUT_SECONDS,
    )
    assert [call["timeout"] for call in session.calls] == [expected] * 4


def test_global_worker_concurrency_is_bounded_at_four() -> None:
    release = threading.Event()
    four_active = threading.Event()
    lock = threading.Lock()
    active = 0
    maximum = 0

    def blocked_token() -> StubResponse:
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
            if active == 4:
                four_active.set()
        release.wait(timeout=2.0)
        with lock:
            active -= 1
        return token_response("test-token")

    sessions = [
        StubSession([blocked_token, StubResponse(json_data=[])])
        for _ in range(5)
    ]
    first = make_transport(*sessions[:4])
    second = make_transport(sessions[4])
    results: list[Any] = []
    errors: list[BaseException] = []

    def call(transport: GlovisTransport) -> None:
        try:
            results.append(
                transport.get_json(AUCTIONS_PATH, [], operation="auctions")
            )
        except BaseException as error:
            errors.append(error)

    threads = [
        threading.Thread(target=call, args=(first if index < 4 else second,))
        for index in range(5)
    ]
    try:
        for thread in threads:
            thread.start()
        assert four_active.wait(timeout=1.0)
        time.sleep(0.05)
        with lock:
            assert maximum == 4
            assert active == 4
    finally:
        release.set()
        for thread in threads:
            thread.join(timeout=1.0)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert len(results) == 5


def test_reviewer_rotation_waits_for_a_different_untried_egress() -> None:
    first_request_started = threading.Event()
    second_request_started = threading.Event()
    release_second = threading.Event()

    def fail_first_after_second_is_busy() -> StubResponse:
        first_request_started.set()
        assert second_request_started.wait(timeout=1.0)
        raise requests.ConnectionError("first egress unavailable")

    def block_second_request() -> StubResponse:
        second_request_started.set()
        assert release_second.wait(timeout=2.0)
        return StubResponse(json_data=[])

    first = StubSession(
        [
            token_response("first"),
            fail_first_after_second_is_busy,
            StubResponse(json_data=[]),
        ]
    )
    second = StubSession(
        [
            token_response("second"),
            block_second_request,
            StubResponse(json_data=[]),
        ]
    )
    transport = make_transport(first, second, overall_deadline_seconds=1.0)
    results: dict[str, Any] = {}
    errors: list[BaseException] = []

    def call(name: str) -> None:
        try:
            results[name] = transport.get_json(
                AUCTIONS_PATH,
                [],
                operation="auctions",
            )
        except BaseException as error:
            errors.append(error)

    primary = threading.Thread(target=call, args=("primary",))
    competing = threading.Thread(target=call, args=("competing",))
    try:
        primary.start()
        assert first_request_started.wait(timeout=0.5)
        competing.start()
        assert second_request_started.wait(timeout=0.5)
        time.sleep(0.05)

        assert primary.is_alive()
        assert len(first.calls) == 2
    finally:
        release_second.set()
        primary.join(timeout=1.0)
        competing.join(timeout=1.0)

    assert not primary.is_alive()
    assert not competing.is_alive()
    assert errors == []
    assert results["primary"].egress == "jp-2"
    assert results["competing"].egress == "jp-2"
    assert len(first.calls) == 2
    assert len(second.calls) == 3


def test_hard_deadline_does_not_reuse_session_while_worker_is_blocked() -> None:
    release = threading.Event()

    def blocked_response() -> StubResponse:
        release.wait(timeout=2.0)
        return StubResponse(json_data=[])

    session = StubSession(
        [
            token_response("one"),
            blocked_response,
            StubResponse(json_data=[]),
        ]
    )
    transport = make_transport(session, overall_deadline_seconds=0.05)
    started = time.monotonic()
    try:
        with pytest.raises(GlovisUpstreamTimeoutError):
            transport.get_json(CARS_PATH, [], operation="cars")
        assert time.monotonic() - started < 0.25

        with pytest.raises(GlovisUpstreamTimeoutError):
            transport.get_json(CARS_PATH, [], operation="cars")
        assert len(session.calls) == 2
    finally:
        release.set()

    result = transport.get_json(CARS_PATH, [], operation="cars")
    assert result.value == []
    assert len(session.calls) == 3


def test_close_closes_idle_sessions_and_rejects_later_calls() -> None:
    first = StubSession()
    second = StubSession()
    transport = make_transport(first, second)

    transport.close()
    transport.close()

    assert first.close_calls == second.close_calls == 1
    with pytest.raises(GlovisUpstreamUnavailableError):
        transport.get_json(CARS_PATH, [], operation="cars")
    assert first.calls == second.calls == []


def test_close_defers_in_flight_session_close_until_worker_finishes() -> None:
    release = threading.Event()

    def blocked_response() -> StubResponse:
        release.wait(timeout=2.0)
        return StubResponse(json_data=[])

    session = StubSession([token_response("one"), blocked_response])
    transport = make_transport(session, overall_deadline_seconds=0.05)
    try:
        with pytest.raises(GlovisUpstreamTimeoutError):
            transport.get_json(CARS_PATH, [], operation="cars")
        transport.close()
        assert session.close_calls == 0
        with pytest.raises(GlovisUpstreamUnavailableError):
            transport.get_json(CARS_PATH, [], operation="cars")
    finally:
        release.set()

    assert session.closed.wait(timeout=0.5)
    assert session.close_calls == 1


def test_reviewer_constructor_closes_prior_sessions_when_factory_fails() -> None:
    first = StubSession()
    factory_calls = 0

    def session_factory() -> StubSession:
        nonlocal factory_calls
        factory_calls += 1
        if factory_calls == 1:
            return first
        raise RuntimeError("synthetic factory failure")

    with pytest.raises(RuntimeError, match="synthetic factory failure"):
        GlovisTransport(
            proxy_candidates=[
                _candidate(
                    country="JP",
                    egress="jp-1",
                    proxy_url="http://user-1:pass-1@proxy-1.invalid:8080",
                ),
                _candidate(
                    country="JP",
                    egress="jp-2",
                    proxy_url="http://user-2:pass-2@proxy-2.invalid:8080",
                ),
            ],
            session_factory=session_factory,
            fingerprint_factory=lambda: "fingerprint-a",
        )

    assert first.close_calls == 1


def test_reviewer_constructor_closes_all_sessions_when_fingerprint_fails() -> None:
    first = StubSession()
    second = StubSession()
    sessions = [first, second]
    fingerprint_calls = 0

    def fingerprint_factory() -> str:
        nonlocal fingerprint_calls
        fingerprint_calls += 1
        if fingerprint_calls == 1:
            return "fingerprint-a"
        raise RuntimeError("synthetic fingerprint failure")

    with pytest.raises(RuntimeError, match="synthetic fingerprint failure"):
        GlovisTransport(
            proxy_candidates=[
                _candidate(
                    country="JP",
                    egress="jp-1",
                    proxy_url="http://user-1:pass-1@proxy-1.invalid:8080",
                ),
                _candidate(
                    country="JP",
                    egress="jp-2",
                    proxy_url="http://user-2:pass-2@proxy-2.invalid:8080",
                ),
            ],
            session_factory=lambda: sessions.pop(0),
            fingerprint_factory=fingerprint_factory,
        )

    assert first.close_calls == second.close_calls == 1


def test_safe_logs_do_not_contain_transport_secrets() -> None:
    captured: list[str] = []
    sink = logger.add(captured.append, format="{message}")
    session = StubSession(
        [
            token_response("token-a"),
            requests.ConnectionError(
                "proxy-user:proxy-password fingerprint-a opaque-value"
            ),
        ]
    )
    try:
        with pytest.raises(GlovisUpstreamUnavailableError):
            make_transport(session).get_json(CARS_PATH, [], operation="cars")
    finally:
        logger.remove(sink)

    joined = "\n".join(captured)
    for secret in (
        "proxy-user",
        "proxy-password",
        "fingerprint-a",
        "token-a",
        "opaque-value",
    ):
        assert secret not in joined
    assert "operation=cars" in joined
    assert "egress=jp-1" in joined
    assert "status=None" in joined
    assert "payload_length=0" in joined
    assert "payload_hash=-" in joined
    assert "error_code=upstream_unavailable" in joined


def test_response_logs_include_only_safe_payload_metadata() -> None:
    response_body = "sensitive-provider-body"
    response = StubResponse(
        status_code=503,
        json_data={"detail": "unavailable"},
        text=response_body,
    )
    captured: list[str] = []
    sink = logger.add(captured.append, format="{message}")
    try:
        with pytest.raises(GlovisUpstreamUnavailableError):
            make_transport(StubSession([token_response("token"), response])).get_json(
                CARS_PATH,
                [],
                operation="cars",
            )
    finally:
        logger.remove(sink)

    output = "".join(captured)
    digest = hashlib.sha256(response_body.encode()).hexdigest()[:12]
    assert response_body not in output
    assert "status=503" in output
    assert f"payload_length={len(response_body)}" in output
    assert f"payload_hash={digest}" in output


def test_a_korean_egress_is_refused_even_when_fully_configured() -> None:
    """The exact configuration that took Glovis down.

    `GLOVIS_PROXY_*` naming a Korean exit is complete and well-formed, so nothing
    upstream of the transport objects to it — and cars.dbauto.kr then answers 403
    on every data call while the token mint keeps succeeding, which surfaces as
    `upstream_auth`. Failing closed at load time turns a puzzling 502 into a
    startup-visible configuration error.
    """
    loader = getattr(transport_module, "load_glovis_proxy_candidates", None)
    assert loader is not None

    with pytest.raises(GlovisProxyUnavailableError):
        loader(
            {
                "GLOVIS_PROXY_HOST": "proxy.example.invalid:8443",
                "GLOVIS_PROXY_USERNAME": "service-account",
                "GLOVIS_PROXY_PASSWORD": "managed-secret",
                "GLOVIS_PROXY_COUNTRY": "KR",
                "GLOVIS_PROXY_EGRESS_LABEL": "kr-primary",
            }
        )


def test_the_shared_dbauto_egress_wins_over_the_legacy_glovis_one() -> None:
    """Both feeds on this host need the same exit, so one variable set governs.

    The old names stay as a fallback, but a deployment that has migrated must not
    keep silently using them.
    """
    loader = getattr(transport_module, "load_glovis_proxy_candidates", None)
    assert loader is not None

    candidates = loader(
        {
            "DBAUTO_PROXY_HOST": "proxy.example.invalid:8443",
            "DBAUTO_PROXY_USERNAME": "shared-account",
            "DBAUTO_PROXY_PASSWORD": "shared-secret",
            "DBAUTO_PROXY_COUNTRY": "JP",
            "DBAUTO_PROXY_EGRESS_LABEL": "jp-primary",
            "GLOVIS_PROXY_HOST": "legacy.example.invalid:8443",
            "GLOVIS_PROXY_USERNAME": "legacy-account",
            "GLOVIS_PROXY_PASSWORD": "legacy-secret",
            "GLOVIS_PROXY_COUNTRY": "HK",
            "GLOVIS_PROXY_EGRESS_LABEL": "hk-legacy",
        }
    )
    assert [c.egress for c in candidates] == ["jp-primary"]


def test_the_legacy_glovis_egress_still_works_alone() -> None:
    loader = getattr(transport_module, "load_glovis_proxy_candidates", None)
    assert loader is not None

    candidates = loader(
        {
            "GLOVIS_PROXY_HOST": "proxy.example.invalid:8443",
            "GLOVIS_PROXY_USERNAME": "service-account",
            "GLOVIS_PROXY_PASSWORD": "managed-secret",
            "GLOVIS_PROXY_COUNTRY": "JP",
            "GLOVIS_PROXY_EGRESS_LABEL": "jp-legacy",
        }
    )
    assert [c.egress for c in candidates] == ["jp-legacy"]
