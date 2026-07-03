"""Tests for SSANCARService.get_car_detail.

Specifically guards against the cache-poisoning failure mode: prior to the
fix, a single bad parse stored an empty SSANCARCarDetail in the in-memory
cache for 30 minutes, so subsequent requests for the same car returned the
same broken response even after the upstream issue was fixed.
"""
from unittest.mock import patch, MagicMock

import pytest

from app.parsers.ssancar_parser import (
    PARSE_STATUS_VALID,
    PARSE_STATUS_SESSION_EXPIRED,
    PARSE_STATUS_INVALID_DATA,
)
from app.services.ssancar_service import SSANCARService


@pytest.fixture
def service() -> SSANCARService:
    """Use a real service but stub out network and cookie loading."""
    with patch.object(SSANCARService, "_create_session", return_value=MagicMock()), \
         patch.object(SSANCARService, "_load_or_set_cookies", return_value=None):
        svc = SSANCARService()
    svc._cache.clear()
    return svc


def _stub_response(html: str = "") -> MagicMock:
    resp = MagicMock()
    resp.text = html
    resp.raise_for_status = MagicMock()
    return resp


def test_invalid_parse_does_not_poison_cache(service: SSANCARService):
    """A bad parse must NOT cache the empty result.

    Old behavior: empty object was cached for cache_ttl_car_detail (30 min).
    New behavior: only PARSE_STATUS_VALID results are cached.
    """
    car_no = "1820158"
    cache_key = service._make_cache_key("detail", {"car_no": car_no})

    service.session = MagicMock()
    service.session.get.return_value = _stub_response("")  # empty → invalid

    detail, status = service.get_car_detail(car_no)
    assert detail is None
    assert status != PARSE_STATUS_VALID
    assert cache_key not in service._cache, (
        "empty/invalid responses must not be cached — that was the bug"
    )


def test_session_expired_status_propagates(service: SSANCARService):
    """A login-redirect response must propagate session_expired upward so
    the route can return a 404 with code='session_expired' (the frontend
    surfaces a retry button for this branch only)."""
    body = "<html><body>" + ("padding " * 100) + (
        '<form name="loginForm"></form>'
    ) + "</body></html>"
    service.session = MagicMock()
    service.session.get.return_value = _stub_response(body)

    detail, status = service.get_car_detail("9999999")
    assert detail is None
    assert status == PARSE_STATUS_SESSION_EXPIRED


def test_valid_parse_is_cached_and_returned(service: SSANCARService):
    car_no = "1820158"
    cache_key = service._make_cache_key("detail", {"car_no": car_no})
    valid_html = f"""
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
    service.session = MagicMock()
    service.session.get.return_value = _stub_response(valid_html)

    detail, status = service.get_car_detail(car_no)
    assert status == PARSE_STATUS_VALID
    assert detail is not None
    assert detail.car_no == car_no
    assert cache_key in service._cache, "valid result should populate the cache"

    # Second call should not re-fetch (cache hit).
    service.session.get.reset_mock()
    detail2, status2 = service.get_car_detail(car_no)
    assert status2 == PARSE_STATUS_VALID
    assert detail2 is not None
    service.session.get.assert_not_called()


def test_request_error_does_not_cache(service: SSANCARService):
    import requests
    car_no = "1820158"
    cache_key = service._make_cache_key("detail", {"car_no": car_no})
    service.session = MagicMock()
    service.session.get.side_effect = requests.RequestException("boom")

    detail, status = service.get_car_detail(car_no)
    assert detail is None
    assert status == "request_error"
    assert cache_key not in service._cache
