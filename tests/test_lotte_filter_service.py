"""Tests for LotteFilterService after the Option-A refactor.

The filter service no longer owns any auth/session code — it delegates to the
proven LotteService (constructor-injected). These tests guard:
  * the tuple contract of `_make_request` -> (json, error_code)
  * stale-session detection + single re-auth-and-retry on the combo endpoint
  * the manufacturers static-fallback branch (and that it does NOT cache a stale
    fallback response)
  * error_code propagation on the models/car-groups/mprice responses
  * the regression that search reuses the shared main-service session
"""
import json
from unittest.mock import MagicMock

import pytest

from app.services.lotte_service import LotteService
from app.services.lotte_filter_service import (
    LotteFilterService,
    _load_manufacturers_fallback,
)


def _make_main_service() -> MagicMock:
    """A mock LotteService whose session/auth hooks we control."""
    main = MagicMock(spec=LotteService)
    main._ensure_session.return_value = True
    main._init_session.return_value = MagicMock()
    return main


def _resp(status: int = 200, text: str = "", json_body=None) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.text = text
    if json_body is not None:
        r.json.return_value = json_body
    else:
        r.json.side_effect = json.JSONDecodeError("no json", "doc", 0)
    return r


@pytest.fixture
def main():
    return _make_main_service()


@pytest.fixture
def svc(main) -> LotteFilterService:
    return LotteFilterService(main)


# ---------------------------------------------------------------------------
# Static fallback data file
# ---------------------------------------------------------------------------

def test_fallback_file_loads_all_manufacturers():
    fb = _load_manufacturers_fallback()
    assert len(fb) == 38
    assert fb[0] == {"code": "HD", "name": "현대자동차"}
    # every entry must have a non-empty code + name (codes feed the models call)
    assert all(e["code"] and e["name"] for e in fb)


# ---------------------------------------------------------------------------
# get_manufacturers
# ---------------------------------------------------------------------------

def test_get_manufacturers_success_live(svc):
    svc._make_request = MagicMock(
        return_value=({"result": [{"code": "HD", "name": "현대자동차"}]}, None)
    )
    resp = svc.get_manufacturers()
    assert resp.success is True
    assert resp.source == "live"
    assert resp.stale is False
    assert resp.total_count == 1
    assert resp.manufacturers[0].code == "HD"
    # live responses ARE cached
    assert "manufacturers" in svc.cache


def test_get_manufacturers_reauth_failed_uses_static_fallback(svc):
    # Live call fails; the real bundled fallback (38 makers) must kick in.
    svc._make_request = MagicMock(return_value=(None, "SESSION_REAUTH_FAILED"))
    resp = svc.get_manufacturers()
    assert resp.success is True
    assert resp.source == "static_fallback"
    assert resp.stale is True
    assert resp.error_code == "SESSION_REAUTH_FAILED"
    assert resp.total_count == 38
    # a stale fallback must NOT be cached (would pin stale data for the TTL)
    assert "manufacturers" not in svc.cache


def test_get_manufacturers_no_fallback_returns_error(svc):
    svc._make_request = MagicMock(return_value=(None, "SESSION_REAUTH_FAILED"))
    svc._static_manufacturers_fallback = MagicMock(return_value=[])
    resp = svc.get_manufacturers()
    assert resp.success is False
    assert resp.error_code == "SESSION_REAUTH_FAILED"
    assert resp.total_count == 0
    assert "manufacturers" not in svc.cache


# ---------------------------------------------------------------------------
# error_code propagation (models / car-groups / mprice have no fallback)
# ---------------------------------------------------------------------------

def test_get_models_propagates_error_code(svc):
    svc._make_request = MagicMock(return_value=(None, "UPSTREAM_HTTP_ERROR"))
    resp = svc.get_models("HD")
    assert resp.success is False
    assert resp.error_code == "UPSTREAM_HTTP_ERROR"
    assert resp.manufacturer_code == "HD"


def test_get_car_groups_propagates_error_code(svc):
    svc._make_request = MagicMock(return_value=(None, "PARSE_ERROR"))
    resp = svc.get_car_groups("HD005")
    assert resp.success is False
    assert resp.error_code == "PARSE_ERROR"


def test_get_mprice_cars_propagates_error_code(svc):
    svc._make_request = MagicMock(return_value=(None, "SESSION_REAUTH_FAILED"))
    resp = svc.get_mprice_cars("HD005016")
    assert resp.success is False
    assert resp.error_code == "SESSION_REAUTH_FAILED"


# ---------------------------------------------------------------------------
# _make_request contract + stale-session recovery
# ---------------------------------------------------------------------------

def test_make_request_success(svc, main):
    session = main._init_session.return_value
    session.post.return_value = _resp(200, json_body={"result": []})
    json_data, err = svc._make_request({"searchFlag": "maker"})
    assert err is None
    assert json_data == {"result": []}


def test_make_request_auth_upfront_fails(svc, main):
    main._ensure_session.return_value = False
    json_data, err = svc._make_request({"searchFlag": "maker"})
    assert json_data is None
    assert err == "SESSION_REAUTH_FAILED"


def test_make_request_html_login_reauths_once(svc, main):
    session = main._init_session.return_value
    # First POST returns an HTML login page, retry returns valid JSON.
    session.post.side_effect = [
        _resp(200, text="<html>경매회원전용 로그인</html>"),
        _resp(200, json_body={"result": [{"code": "HD", "name": "현대자동차"}]}),
    ]
    json_data, err = svc._make_request({"searchFlag": "maker"})
    assert err is None
    assert json_data["result"][0]["code"] == "HD"
    main.invalidate_session.assert_called_once()


def test_make_request_fail_notauctlogin_marker_reauths_once(svc, main):
    session = main._init_session.return_value
    session.post.side_effect = [
        _resp(200, text='{"result":"fail_notAuctLogin"}'),
        _resp(200, json_body={"result": []}),
    ]
    json_data, err = svc._make_request({"searchFlag": "maker"})
    assert err is None
    assert json_data == {"result": []}
    main.invalidate_session.assert_called_once()


def test_make_request_still_stale_after_reauth(svc, main):
    session = main._init_session.return_value
    session.post.side_effect = [
        _resp(200, text="<html>경매회원전용 로그인</html>"),
        _resp(200, text="<html>경매회원전용 로그인</html>"),
    ]
    json_data, err = svc._make_request({"searchFlag": "maker"})
    assert json_data is None
    assert err == "SESSION_REAUTH_FAILED"


def test_make_request_reauth_call_fails(svc, main):
    session = main._init_session.return_value
    session.post.return_value = _resp(200, text="<html>경매회원전용 로그인</html>")
    main._ensure_session.side_effect = [True, False]  # upfront ok, re-auth fails
    json_data, err = svc._make_request({"searchFlag": "maker"})
    assert json_data is None
    assert err == "SESSION_REAUTH_FAILED"


def test_make_request_non_200(svc, main):
    session = main._init_session.return_value
    session.post.return_value = _resp(502, text="Bad Gateway")
    json_data, err = svc._make_request({"searchFlag": "maker"})
    assert json_data is None
    assert err == "UPSTREAM_HTTP_ERROR"


def test_make_request_bad_json(svc, main):
    session = main._init_session.return_value
    session.post.return_value = _resp(200, text="<html>not json, not login</html>")
    json_data, err = svc._make_request({"searchFlag": "maker"})
    assert json_data is None
    assert err == "PARSE_ERROR"


# ---------------------------------------------------------------------------
# regression: search reuses the shared main-service session
# ---------------------------------------------------------------------------

def test_search_cars_uses_shared_session(svc, main):
    from app.models.lotte_filters import LotteFilterRequest

    main._ensure_session.return_value = False  # force early return
    resp = svc.search_cars_with_parsing(LotteFilterRequest(page=1, per_page=5))
    main._ensure_session.assert_called()  # delegated to the shared session
    assert resp.success is False
    assert resp.error_code == "SESSION_REAUTH_FAILED"


def test_search_zero_results_does_not_false_reauth(svc, main):
    """A valid zero-result page (parse_status == 'ok') that happens to contain a
    login marker must NOT be treated as a stale session — no needless re-auth /
    shared-session churn. Regression for the empty-search false positive."""
    from app.models.lotte_filters import LotteFilterRequest

    session = main._init_session.return_value
    # Page contains a login-link marker (as Lotte's authenticated list pages do),
    # but the results table parses fine with zero rows.
    session.post.return_value = _resp(200, text="<html>경매회원전용 로그인 ... tbl-t02</html>")
    svc.parser.parse_car_search_html_with_status = MagicMock(return_value=([], "ok"))
    svc.parser.extract_total_count = MagicMock(return_value=0)

    resp = svc.search_cars_with_parsing(
        LotteFilterRequest(manufacturer_code="AD", model_code="AD004", page=1, per_page=20)
    )
    assert resp.success is True
    assert resp.total_count == 0
    assert resp.error_code is None
    main.invalidate_session.assert_not_called()  # no false-positive re-auth
    session.post.assert_called_once()  # exactly one request, no retry
