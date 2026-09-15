"""Pure-function tests for app.core.encar_query — no network.

Pins why `+`, `&` and `#` (and only those three) are pre-escaped before an
Encar query-string parameter is built: yarl (the library behind aiohttp,
which builds every outgoing Encar URL) leaves these three characters
unescaped on the wire, and Encar reads each of them with the wrong meaning.
See the module docstring on app/core/encar_query.py for the full
explanation.
"""

from __future__ import annotations

import pytest
import yarl

from app.core.encar_query import encode_encar_query_param


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("가솔린+전기", "가솔린%2B전기"),
        ("a&b", "a%26b"),
        ("a#b", "a%23b"),
    ],
)
def test_escapes_plus_ampersand_hash(raw: str, expected: str) -> None:
    assert encode_encar_query_param(raw) == expected


@pytest.mark.parametrize(
    "value",
    [
        "(And.Hidden.N._.SellType.일반._.(C.Model.그랜저 (GN7_)._.Badge.2_.5 가솔린 2WD.))",
        "|ModifiedDate|0|20",
        "|Metadata|Sort",
    ],
)
def test_leaves_encar_grammar_untouched(value: str) -> None:
    """Must not break Encar's own `_.`/`_)` escaping, spaces, pipes or Korean."""
    assert encode_encar_query_param(value) == value


@pytest.mark.parametrize("value", ["%EC%9D%BC%EB%B0%98", "100%"])
def test_does_not_touch_percent(value: str) -> None:
    """Legacy callers pre-encode Korean (encar_service.py's default `q`);
    a bare `%` must also survive so yarl's own %25 fixup stays in charge."""
    assert encode_encar_query_param(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "가솔린+전기",
        "a&b#c",
        "(And.FuelType.가솔린+전기.)",
        "plain text",
    ],
)
def test_idempotent(value: str) -> None:
    """Safe if both the route and the legacy service apply it."""
    once = encode_encar_query_param(value)
    assert encode_encar_query_param(once) == once


def test_yarl_wire_contract() -> None:
    """Pins the yarl behaviour the fix depends on; breaks loudly on an
    aiohttp/yarl upgrade that changes how `+`, `#` or `%` are handled."""
    q = "(And.FuelType.가솔린+전기#x.)"
    sr = "|ModifiedDate|0|20"
    url = (
        "https://api.encar.com/search/car/list/premium"
        f"?q={encode_encar_query_param(q)}&sr={encode_encar_query_param(sr)}&count=true"
    )

    parsed = yarl.URL(url)

    assert "%2B" in parsed.raw_query_string
    assert "%25EC" not in parsed.raw_query_string, "Korean must not be double-encoded"
    assert parsed.query["q"] == q, "q round-trips, `+` included"
    assert "sr" in parsed.query, "the escaped # must not swallow sr into a fragment"


def test_unescaped_plus_reaches_encar_as_space() -> None:
    """Documents the bug this module fixes: without escaping, yarl leaves a
    literal `+` in place on the wire, and Encar reads it as a space."""
    q = "(And.FuelType.가솔린+전기.)"
    url = f"https://api.encar.com/search/car/list/premium?q={q}&sr=|ModifiedDate|0|20&count=true"

    parsed = yarl.URL(url)

    assert "가솔린 전기" in parsed.query["q"]
