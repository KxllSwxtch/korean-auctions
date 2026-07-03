"""Tests for SSANCAR parser detail-page validation.

The bug being guarded against: SSANCAR's car_view.php sometimes responds with
a login redirect, an archived-car page, or an effectively empty body. The
old parser silently produced a zero-filled SSANCARCarDetail in those cases
and the UI rendered "Unknown Car / N/A / TBA / $0". The parser must now
return None plus a status code so the route can raise a discriminated 404.
"""
from app.parsers.ssancar_parser import (
    SSANCARParser,
    PARSE_STATUS_VALID,
    PARSE_STATUS_SESSION_EXPIRED,
    PARSE_STATUS_NOT_FOUND,
    PARSE_STATUS_EMPTY,
    PARSE_STATUS_INVALID_DATA,
    PARSE_STATUS_EXCEPTION,
)


def _make_parser() -> SSANCARParser:
    return SSANCARParser()


def _valid_html(car_no: str = "1820158") -> str:
    """Build an HTML body that exercises every selector the parser uses."""
    return f"""
    <html>
      <head><title>SSANCAR</title></head>
      <body>
        <a href="/page/car_view.php?car_no={car_no}">Self link</a>
        <p class="num"><span>STK-001</span></p>
        <p class="name"><span>Hyundai Sonata 2.0</span></p>
        <ul class="detail">
          <li>
            <span>2020</span>
            <span>A/T</span>
            <span>Gasoline</span>
            <span>1999cc</span>
            <span>50,000 km</span>
            <span>A1</span>
          </li>
        </ul>
        <p class="money"><span>$15,000</span></p>
        <div class="swiper-slide"><img src="https://img/example/1.jpg" /></div>
        <div class="swiper-slide"><img src="https://img/example/2.jpg" /></div>
        <ul class="day_list">
          <li>
            <p class="detail">
              Upload : 2026-04-20 10:00AM
              Start : 2026-04-29 11:00AM
            </p>
          </li>
        </ul>
        <strong id="timer">2D 3H 4M</strong>
        {'X' * 600}
      </body>
    </html>
    """


def test_parses_valid_detail_page():
    parser = _make_parser()
    detail, status = parser.parse_car_detail(_valid_html())
    assert status == PARSE_STATUS_VALID
    assert detail is not None
    assert detail.car_no == "1820158"
    assert detail.full_name == "Hyundai Sonata 2.0"
    assert detail.year == 2020
    # Parser normalizes the raw string ("$15,000" → "$ 15,000")
    assert "15,000" in detail.starting_price
    assert detail.currency == "USD"
    assert detail.bid_price == 15000
    assert detail.images, "expected at least one image"


def test_empty_html_returns_empty_status():
    parser = _make_parser()
    detail, status = parser.parse_car_detail("")
    assert detail is None
    assert status == PARSE_STATUS_EMPTY


def test_short_body_returns_empty_status():
    parser = _make_parser()
    detail, status = parser.parse_car_detail("<html><body>oops</body></html>")
    assert detail is None
    assert status == PARSE_STATUS_EMPTY


def test_login_redirect_detected_as_session_expired():
    body = "<html><body>" + ("padding " * 100) + (
        '<form name="loginForm" action="/member/login.php"></form>'
    ) + "</body></html>"
    parser = _make_parser()
    detail, status = parser.parse_car_detail(body)
    assert detail is None
    assert status == PARSE_STATUS_SESSION_EXPIRED


def test_korean_login_marker_detected_as_session_expired():
    body = "<html><body>" + ("padding " * 100) + "로그인 해주세요" + "</body></html>"
    parser = _make_parser()
    detail, status = parser.parse_car_detail(body)
    assert detail is None
    assert status == PARSE_STATUS_SESSION_EXPIRED


def test_archived_car_detected_as_not_found():
    body = "<html><body>" + ("padding " * 100) + "차량을 찾을 수 없습니다" + "</body></html>"
    parser = _make_parser()
    detail, status = parser.parse_car_detail(body)
    assert detail is None
    assert status == PARSE_STATUS_NOT_FOUND


def test_long_html_without_real_data_returns_invalid_data():
    """A response that's long enough to bypass the empty/length gate but
    contains no SSANCAR detail markup must be flagged invalid_data — this
    is the exact failure mode that produced "Unknown Car / N/A / TBA / $0".
    """
    body = "<html><body>" + ("<p>filler</p>" * 200) + "</body></html>"
    parser = _make_parser()
    detail, status = parser.parse_car_detail(body)
    assert detail is None
    assert status == PARSE_STATUS_INVALID_DATA


def test_minimally_valid_predicate():
    from app.models.ssancar import SSANCARCarDetail

    def _detail(**overrides) -> SSANCARCarDetail:
        base = dict(
            car_no="",
            stock_no="",
            manufacturer="",
            model="",
            full_name="",
            year=0,
            mileage=None,
            mileage_formatted="",
            fuel="",
            fuel_type=None,
            transmission="",
            grade="",
            color=None,
            engine_size=None,
            engine_volume=None,
            vin=None,
            bid_price=0,
            buy_now_price=None,
            auction_date=None,
            auction_status="ended",
            inspection_sheet_url=None,
            condition_notes=None,
            starting_price="",
        )
        base.update(overrides)
        return SSANCARCarDetail(**base)

    assert SSANCARParser._is_minimally_valid(_detail()) is False, (
        "fully-empty record must be rejected"
    )

    name_only = _detail(car_no="1234", full_name="Sonata")
    assert SSANCARParser._is_minimally_valid(name_only) is False, (
        "name without any year/price/images is not enough signal"
    )

    name_and_year = _detail(car_no="1234", full_name="Sonata", year=2021)
    assert SSANCARParser._is_minimally_valid(name_and_year) is True

    # SSANCAR doesn't emit car_no in the HTML — service backfills from URL.
    # So the parser-level validator must NOT require car_no.
    no_car_no_but_real = _detail(full_name="Sonata", year=2021)
    assert SSANCARParser._is_minimally_valid(no_car_no_but_real) is True

    name_and_price = _detail(full_name="Sonata", starting_price="$15,000")
    assert SSANCARParser._is_minimally_valid(name_and_price) is True

    name_only = _detail(full_name="Sonata")
    assert SSANCARParser._is_minimally_valid(name_only) is False, (
        "name with no year/price/images is still empty signal"
    )

    # A scraped label with no digits (the 2026-markup "Bid" span) must not
    # count as a price signal — that exact string produced the "$0" bug.
    label_as_price = _detail(full_name="Sonata", starting_price="Bid")
    assert SSANCARParser._is_minimally_valid(label_as_price) is False


# ---------------------------------------------------------------------------
# 2026 upstream markup redesign: price moved to ₩/$/€ pr-cur spans and the
# year span became "YYYY.MM". These tests pin the new extraction plus the
# legacy-markup fallbacks.
# ---------------------------------------------------------------------------

def _new_markup_detail_html(car_no: str = "2120388387") -> str:
    return f"""
    <html>
      <body>
        <a href="/page/car_view.php?car_no={car_no}">Self link</a>
        <p class="num"><span>1001</span></p>
        <p class="name"><span>[Kia] The New K3 1.6 Gasoline Trendy</span></p>
        <ul class="detail">
          <li>
            <span>2022.03</span>
            <span> A/T</span>
            <span>Gasoline</span>
            <span>1,598cc</span>
            <span>75,984 Km</span>
            <span>A/4</span>
            <span>White</span>
          </li>
        </ul>
        <p class="money"><span class="pr-lbl">Bid</span><span class="pr-cur">₩ <b>10,400,000</b></span><span class="pr-cur">$ <b>6,797</b></span><span class="pr-cur">€ <b>5,936</b></span></p>
        <div class="swiper-slide"><img src="https://www.ssancar.com/data/auction_img/al_{car_no}_0.jpg" /></div>
        <strong id="timer">Time :DHms</strong>
        {'X' * 600}
      </body>
    </html>
    """


def test_parses_new_markup_detail():
    parser = _make_parser()
    detail, status = parser.parse_car_detail(_new_markup_detail_html())
    assert status == PARSE_STATUS_VALID
    assert detail is not None
    assert detail.bid_price == 10_400_000
    assert detail.currency == "KRW"
    assert "10,400,000" in detail.starting_price
    assert detail.starting_price != "Bid"
    assert detail.year == 2022
    assert detail.color == "White"


def test_parse_car_list_new_markup():
    """Exact markup captured live from ajax_car_list.php on 2026-07-03:
    ₩/$/€ symbols sit as loose text BEFORE plain span.num elements. The ₩
    figure must win even though '$' is also present in the block.
    """
    html = """
    <ul>
      <li>
        <a href="/page/car_view.php?car_no=2120388387">
          <span class="num">1001</span>
          <span class="name">[Kia] The New K3 1.6 Gasoline Trendy</span>
          <ul class="detail"><li style="color:#BCBCBC;"><span>2022.03</span><span> A/T</span><span>Gasoline</span><br /><span>1,598cc</span><span>75,984 Km</span><span>A/4</span><span>White</span></li></ul>
          <p class="money"> <span style="margin-right:20px;">Bid</span> ₩ <span class="num">10,400,000</span>&nbsp; $ <span class="num">6,797</span>&nbsp; € <span class="num">5,936</span> </p>
          <img src="https://img/1.jpg" />
        </a>
      </li>
      <li>
        <a href="/page/car_view.php?car_no=2120388388">
          <span class="num">1002</span>
          <span class="name">[Hyundai] Avante MD M16 GDi Smart</span>
          <ul class="detail"><li><span>2013.05</span><span>A/T</span><span>Gasoline</span><span>156,882 Km</span><span>A/1</span></li></ul>
          <p class="money"><span class="pr-lbl">Bid</span><span class="pr-cur">₩ <b>1,850,000</b></span><span class="pr-cur">$ <b>1,360</b></span></p>
          <img src="https://img/2.jpg" />
        </a>
      </li>
    </ul>
    """
    parser = _make_parser()
    cars = parser.parse_car_list(html)
    assert len(cars) == 2

    first, second = cars
    assert first.car_no == "2120388387"
    assert first.stock_no == "1001"
    assert first.bid_price == 10_400_000
    assert first.currency == "KRW", "₩-adjacent amount must win over the $ one"
    assert first.year == 2022

    assert second.car_no == "2120388388"
    assert second.bid_price == 1_850_000
    assert second.currency == "KRW", "₩ pr-cur span must win over the $ one"
    assert second.year == 2013


def test_parse_money_block_bare_number_magnitude_heuristic():
    """No currency symbol at all: 7-digit amounts classify as KRW, small as USD."""
    from bs4 import BeautifulSoup

    krw_block = BeautifulSoup(
        '<p class="money"><span class="bid">Bid</span> <span class="num">10,400,000</span></p>',
        "html.parser",
    ).find("p")
    amount, currency, _ = SSANCARParser._parse_money_block(krw_block)
    assert (amount, currency) == (10_400_000, "KRW")

    usd_block = BeautifulSoup(
        '<p class="money"><span class="bid">Bid</span> <span class="num">3,083</span></p>',
        "html.parser",
    ).find("p")
    amount, currency, _ = SSANCARParser._parse_money_block(usd_block)
    assert (amount, currency) == (3083, "USD")


def test_old_markup_usd_price_fallback():
    """Sept-2025 markup carried a single pre-converted USD figure."""
    html = """
    <ul>
      <li>
        <a href="/page/car_view.php?car_no=1533998">
          <span class="num">1001</span>
          <span class="name">[HYUNDAI] GrandeurHG HG 240 Modern</span>
          <ul class="detail"><li><span>2016</span><span>A/T</span><span>Gasoline</span><span>250,445 Km</span><span>A/4</span></li></ul>
          <p class="money"><span class="bid">Bid</span> <span class="num">3,083</span>$~</p>
          <img src="https://img/1.jpg" />
        </a>
      </li>
    </ul>
    """
    parser = _make_parser()
    cars = parser.parse_car_list(html)
    assert len(cars) == 1
    assert cars[0].bid_price == 3083
    assert cars[0].currency == "USD"
    assert cars[0].year == 2016


def test_year_extraction_variants():
    assert SSANCARParser._extract_year("2016") == 2016
    assert SSANCARParser._extract_year("2022.03") == 2022
    assert SSANCARParser._extract_year("2022.3") == 2022
    assert SSANCARParser._extract_year("9000") == 0, "implausible year rejected"
    assert SSANCARParser._extract_year("1979") == 0, "pre-1980 rejected"
    assert SSANCARParser._extract_year("75,984") == 0
    assert SSANCARParser._extract_year("") == 0


def test_timer_template_junk_normalized():
    parser = _make_parser()

    junk = _new_markup_detail_html()  # carries <strong id="timer">Time :DHms</strong>
    detail, status = parser.parse_car_detail(junk)
    assert status == PARSE_STATUS_VALID
    assert detail.auction_time_remaining == ""
    assert detail.auction_status == "ended"

    real = junk.replace("Time :DHms", "Time : 2D 3H 4m 5s")
    detail, status = parser.parse_car_detail(real)
    assert status == PARSE_STATUS_VALID
    assert detail.auction_time_remaining == "Time : 2D 3H 4m 5s"
    assert detail.auction_status == "active"
