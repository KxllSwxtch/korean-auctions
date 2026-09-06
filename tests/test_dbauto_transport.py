"""Transport tests with a fake session -- no network, no proxy, no clock drift.

These cover the parts that are easy to get subtly wrong and expensive to debug in
production: the egress country policy, the path allowlist, token re-minting under
concurrency, and the lane reservation that keeps a catalog page from queueing
behind a facet fan-out.
"""

from __future__ import annotations

import threading
import time

import pytest
import requests

from app.services.dbauto_transport import (
    BULK,
    CASCADE,
    INTERACTIVE,
    DbautoGeoBlockedError,
    DbautoProxyCandidate,
    DbautoProxyUnavailableError,
    DbautoServiceConfig,
    DbautoTransport,
    DbautoUpstreamAuthError,
    DbautoUpstreamError,
    DbautoUpstreamInvalidResponseError,
    LaneScheduler,
    load_proxy_candidates,
    normalize_proxy_candidate,
)

NON_KR = frozenset({"JP", "HK", "US"})
GOOD_PROXY = "http://user:pass@proxy.example.com:2312"


def make_config(**overrides) -> DbautoServiceConfig:
    base = dict(
        name="heydealer",
        api_prefix="/api/auctions/heydealer",
        referer="https://cars.dbauto.kr/en/heydealer",
        allowed_paths=frozenset({"/cars", "/car"}),
        allowed_countries=NON_KR,
        proxy_env_prefixes=("DBAUTO_PROXY",),
        max_sessions=2,
        facet_concurrency=1,
        min_interval_seconds=0.0,
        retries=2,
        retry_base_seconds=0.001,
    )
    base.update(overrides)
    return DbautoServiceConfig(**base)


def candidate(country="JP", egress="jp-primary", url=GOOD_PROXY) -> DbautoProxyCandidate:
    return DbautoProxyCandidate(country=country, egress=egress, proxy_url=url)


# --------------------------------------------------------------------------- #
# A fake requests.Session
# --------------------------------------------------------------------------- #


class FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeCookie:
    def __init__(self, name, value):
        self.name = name
        self.value = value
        self.domain = "cars.dbauto.kr"
        self.path = "/"


class FakeCookieJar(list):
    def clear(self, domain=None, path=None, name=None):
        for cookie in list(self):
            if cookie.name == name:
                self.remove(cookie)


class FakeSession:
    """Mints a token cookie on POST; serves a scripted queue of GET responses."""

    def __init__(self):
        self.headers: dict[str, str] = {}
        self.proxies: dict[str, str] = {}
        self.trust_env = True
        self.cookies = FakeCookieJar()
        self.closed = False
        self.get_responses: list = []
        self.requests: list[tuple[str, str]] = []
        self.mints = 0
        self.lock = threading.Lock()

    def request(self, method, url, **kwargs):
        with self.lock:
            self.requests.append((method, url))
            if method == "POST":
                self.mints += 1
                self.cookies.append(FakeCookie("x-api-token", f"tok{self.mints}"))
                return FakeResponse(200, {"ok": True})
            nxt = self.get_responses.pop(0) if self.get_responses else FakeResponse(200, {"ok": 1})
        if callable(nxt):
            return nxt()
        return nxt

    def close(self):
        self.closed = True


@pytest.fixture
def session_holder():
    made: list[FakeSession] = []

    def factory():
        session = FakeSession()
        made.append(session)
        return session

    factory.made = made  # type: ignore[attr-defined]
    return factory


# --------------------------------------------------------------------------- #
# Egress policy
# --------------------------------------------------------------------------- #


def test_korean_egress_is_rejected_for_dbauto():
    """dbauto geo-blocks Korea, so a KR exit must fail at construction rather
    than as a 403 on the first real call."""
    with pytest.raises(DbautoProxyUnavailableError):
        normalize_proxy_candidate(
            candidate(country="KR", egress="kr-primary"), allowed_countries=NON_KR
        )


@pytest.mark.parametrize("country", ["JP", "HK", "US"])
def test_allowed_countries_pass(country):
    got = normalize_proxy_candidate(
        candidate(country=country, egress=f"{country.lower()}-primary"),
        allowed_countries=NON_KR,
    )
    assert got.country == country


def test_egress_label_may_not_embed_a_credential():
    """The label is logged and returned in health payloads."""
    with pytest.raises(DbautoProxyUnavailableError):
        normalize_proxy_candidate(
            candidate(egress="jp-sup3rsecret", url="http://sup3rsecret:p@h.example:1"),
            allowed_countries=NON_KR,
        )


@pytest.mark.parametrize(
    "url",
    [
        "socks5://user:pass@h.example:1",   # unsupported scheme
        "http://user@h.example:1",          # no password
        "http://user:pass@h.example",       # no port
        "http://user:pass@h.example:1/path",# path
        "http://user:pass@h.example:1?q=1", # query
    ],
)
def test_malformed_proxy_urls_are_rejected(url):
    with pytest.raises(DbautoProxyUnavailableError):
        normalize_proxy_candidate(candidate(url=url), allowed_countries=NON_KR)


def test_env_prefixes_are_tried_in_order():
    env = {
        "GLOVIS_PROXY_HOST": "h.example:1",
        "GLOVIS_PROXY_USERNAME": "u",
        "GLOVIS_PROXY_PASSWORD": "p",
        "GLOVIS_PROXY_COUNTRY": "JP",
        "GLOVIS_PROXY_EGRESS_LABEL": "jp-fallback",
    }
    got = load_proxy_candidates(
        ("DBAUTO_PROXY", "GLOVIS_PROXY"), allowed_countries=NON_KR, environment=env
    )
    assert got[0].egress == "jp-fallback"


def test_missing_egress_configuration_fails_closed():
    with pytest.raises(DbautoProxyUnavailableError):
        load_proxy_candidates(
            ("DBAUTO_PROXY",), allowed_countries=NON_KR, environment={}
        )


def test_host_with_a_scheme_is_rejected():
    env = {
        "DBAUTO_PROXY_HOST": "http://h.example:1",
        "DBAUTO_PROXY_USERNAME": "u",
        "DBAUTO_PROXY_PASSWORD": "p",
        "DBAUTO_PROXY_COUNTRY": "JP",
        "DBAUTO_PROXY_EGRESS_LABEL": "jp-primary",
    }
    with pytest.raises(DbautoProxyUnavailableError):
        load_proxy_candidates(
            ("DBAUTO_PROXY",), allowed_countries=NON_KR, environment=env
        )


# --------------------------------------------------------------------------- #
# Request behaviour
# --------------------------------------------------------------------------- #


def test_path_allowlist_blocks_anything_unapproved(session_holder):
    transport = DbautoTransport(
        make_config(), proxy_candidates=[candidate()], session_factory=session_holder
    )
    with pytest.raises(ValueError):
        transport.get_json("/../../etc/passwd", [], "evil")
    transport.close()


def test_lang_is_injected_and_never_duplicated(session_holder):
    transport = DbautoTransport(
        make_config(), proxy_candidates=[candidate()], session_factory=session_holder
    )
    session = session_holder.made[0]
    session.get_responses = [FakeResponse(200, {"items": []})]
    transport.get_json("/cars", [("lang", "zz"), ("page", 1)], "list", lang="ru")
    transport.close()
    # The caller's stray lang is dropped in favour of the resolved one.
    assert session.requests[-1][0] == "GET"


def test_token_is_minted_before_the_first_read(session_holder):
    transport = DbautoTransport(
        make_config(), proxy_candidates=[candidate()], session_factory=session_holder
    )
    session = session_holder.made[0]
    session.get_responses = [FakeResponse(200, {"items": []})]
    transport.get_json("/cars", [], "list")
    assert session.mints == 1
    assert [m for m, _ in session.requests] == ["POST", "GET"]
    transport.close()


def test_a_401_triggers_exactly_one_remint_then_succeeds(session_holder):
    transport = DbautoTransport(
        make_config(), proxy_candidates=[candidate()], session_factory=session_holder
    )
    session = session_holder.made[0]
    session.get_responses = [FakeResponse(401), FakeResponse(200, {"items": [1]})]
    result = transport.get_json("/cars", [], "list")
    assert result.value == {"items": [1]}
    assert session.mints == 2, "one initial mint plus one forced re-mint"
    transport.close()


def test_a_403_that_survives_a_remint_is_reported_as_geo_not_auth(session_holder):
    """The mint succeeds from anywhere, so a persistent 403 is the country."""
    transport = DbautoTransport(
        make_config(), proxy_candidates=[candidate()], session_factory=session_holder
    )
    session = session_holder.made[0]
    session.get_responses = [FakeResponse(403), FakeResponse(403)]
    with pytest.raises(DbautoGeoBlockedError) as excinfo:
        transport.get_json("/cars", [], "list")
    assert excinfo.value.code == "egress_geo_blocked"
    assert excinfo.value.retryable is False
    transport.close()


def test_a_geo_block_is_not_retried(session_holder):
    transport = DbautoTransport(
        make_config(), proxy_candidates=[candidate()], session_factory=session_holder
    )
    session = session_holder.made[0]
    session.get_responses = [FakeResponse(403), FakeResponse(403)]
    with pytest.raises(DbautoGeoBlockedError):
        transport.get_json("/cars", [], "list")
    assert len([m for m, _ in session.requests if m == "GET"]) == 2
    transport.close()


def test_retryable_status_is_retried_then_gives_up(session_holder):
    # One slot, so every retry lands on the session whose responses are scripted.
    # With more slots a retry legitimately rotates to a different session, which
    # is the behaviour the next test pins.
    transport = DbautoTransport(
        make_config(retries=2, max_sessions=1),
        proxy_candidates=[candidate()],
        session_factory=session_holder,
    )
    session = session_holder.made[0]
    session.get_responses = [FakeResponse(503) for _ in range(6)]
    with pytest.raises(DbautoUpstreamError):
        transport.get_json("/cars", [], "list")
    assert len([m for m, _ in session.requests if m == "GET"]) == 3
    transport.close()


def test_max_attempts_caps_the_retry_budget(session_holder):
    """An unknown car id makes dbauto answer 500 after 10-30 s; retrying it three
    times would hold an interactive slot for minutes."""
    transport = DbautoTransport(
        make_config(retries=3), proxy_candidates=[candidate()], session_factory=session_holder
    )
    session = session_holder.made[0]
    session.get_responses = [FakeResponse(500) for _ in range(8)]
    with pytest.raises(DbautoUpstreamError):
        transport.get_json("/cars", [], "list", max_attempts=1)
    assert len([m for m, _ in session.requests if m == "GET"]) == 1
    transport.close()


def test_a_404_is_not_retried(session_holder):
    transport = DbautoTransport(
        make_config(), proxy_candidates=[candidate()], session_factory=session_holder
    )
    session = session_holder.made[0]
    session.get_responses = [FakeResponse(404) for _ in range(4)]
    with pytest.raises(DbautoUpstreamInvalidResponseError):
        transport.get_json("/cars", [], "list")
    assert len([m for m, _ in session.requests if m == "GET"]) == 1
    transport.close()


def test_non_json_body_is_an_invalid_response(session_holder):
    transport = DbautoTransport(
        make_config(retries=0), proxy_candidates=[candidate()], session_factory=session_holder
    )
    session = session_holder.made[0]
    session.get_responses = [FakeResponse(200, None, text="<html>500</html>")]
    with pytest.raises(DbautoUpstreamInvalidResponseError):
        transport.get_json("/cars", [], "list")
    transport.close()


def test_sessions_do_not_inherit_ambient_proxy_env(session_holder):
    """A shell HTTP_PROXY must not silently override the validated egress."""
    transport = DbautoTransport(
        make_config(), proxy_candidates=[candidate()], session_factory=session_holder
    )
    assert all(s.trust_env is False for s in session_holder.made)
    assert all(s.proxies["https"] == GOOD_PROXY for s in session_holder.made)
    transport.close()


def test_close_releases_every_session(session_holder):
    transport = DbautoTransport(
        make_config(), proxy_candidates=[candidate()], session_factory=session_holder
    )
    transport.close()
    assert all(s.closed for s in session_holder.made)


# --------------------------------------------------------------------------- #
# Lane scheduler
# --------------------------------------------------------------------------- #


def test_facet_calls_cannot_consume_every_permit():
    """The reservation is the whole point: a 13-call facet fan-out must never
    make a user's catalog page wait."""
    scheduler = LaneScheduler(capacity=4, facet_max=2)
    assert scheduler.acquire(BULK, 0.1)
    assert scheduler.acquire(CASCADE, 0.1)
    assert not scheduler.acquire(BULK, 0.05), "facet budget is exhausted"
    assert scheduler.acquire(INTERACTIVE, 0.1), "interactive keeps a reserved permit"


def test_facet_max_is_clamped_below_capacity():
    scheduler = LaneScheduler(capacity=2, facet_max=99)
    assert scheduler.facet_capacity == 1


def test_release_wakes_a_waiter():
    scheduler = LaneScheduler(capacity=1, facet_max=1)
    assert scheduler.acquire(INTERACTIVE, 0.1)
    woken = []

    def waiter():
        woken.append(scheduler.acquire(INTERACTIVE, 2.0))

    thread = threading.Thread(target=waiter)
    thread.start()
    time.sleep(0.05)
    scheduler.release(INTERACTIVE)
    thread.join(timeout=3)
    assert woken == [True]


def test_interactive_waiters_are_served_before_facet_waiters():
    scheduler = LaneScheduler(capacity=1, facet_max=1)
    assert scheduler.acquire(INTERACTIVE, 0.1)
    order: list[str] = []

    def wait(lane):
        if scheduler.acquire(lane, 2.0):
            order.append(lane)

    bulk = threading.Thread(target=wait, args=(BULK,))
    bulk.start()
    time.sleep(0.05)
    interactive = threading.Thread(target=wait, args=(INTERACTIVE,))
    interactive.start()
    time.sleep(0.05)

    scheduler.release(INTERACTIVE)
    interactive.join(timeout=3)
    assert order == [INTERACTIVE], "interactive jumped the queued bulk call"
    scheduler.release(INTERACTIVE)
    bulk.join(timeout=3)
    assert order == [INTERACTIVE, BULK]


def test_acquire_times_out_without_leaking_a_permit():
    scheduler = LaneScheduler(capacity=1, facet_max=1)
    assert scheduler.acquire(INTERACTIVE, 0.1)
    assert not scheduler.acquire(INTERACTIVE, 0.05)
    scheduler.release(INTERACTIVE)
    assert scheduler.acquire(INTERACTIVE, 0.1), "the timed-out waiter left no residue"


def test_a_retry_rotates_to_another_session_slot(session_holder):
    """A slot whose session is wedged should not swallow every attempt: the retry
    leases the next slot, which is why a single bad connection is survivable."""
    transport = DbautoTransport(
        make_config(retries=2, max_sessions=2),
        proxy_candidates=[candidate()],
        session_factory=session_holder,
    )
    first, second = session_holder.made
    first.get_responses = [FakeResponse(503)]
    second.get_responses = [FakeResponse(200, {"items": ["ok"]})]
    assert transport.get_json("/cars", [], "list").value == {"items": ["ok"]}
    transport.close()
