"""Manufacturer resolution, and parity with the frontend's copy of the mapping.

app/parsers/lotte_parser.py used to call a list of MODEL names `brands`, so a
Kia Sorento was reported as `brand="SORENTO"`, a Hyundai Grandeur as
`brand="GRANDEUR"`, and anything outside that list (EV6, Palisade) as
`brand="UNKNOWN"`. The block that mapped models to real manufacturers sat after
the loop and was unreachable.

The mapping is duplicated in autobazaapp/lib/utils/resolveManufacturer.ts,
which the frontend uses to correct the API's output at display time. Duplication
is the price of not having a shared package here; the parity test below is what
keeps the two from drifting apart and disagreeing about the same car.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.manufacturers import RULES, UNKNOWN_BRAND, resolve_manufacturer


FRONTEND_RESOLVER = (
    Path(__file__).resolve().parents[2]
    / "autobazaapp"
    / "lib"
    / "utils"
    / "resolveManufacturer.ts"
)


# (model string as Lotte writes it, expected manufacturer)
REAL_LISTINGS = [
    ("EV6 (E) 롱레인지 에어 2WD", "Kia"),
    ("PALISADE (G) 3.8 익스클루시브 2WD 8인", "Hyundai"),
    ("THE NEW GRANDEUR (H) 2.4 프리미엄", "Hyundai"),
    ("SORENTO MQ4 (D) 2.2 트렌디 5인승 4WD", "Kia"),
    ("SPORTAGE NQ5 (G)1.6T 프레스티지 5인 2WD", "Kia"),
    ("G80 (G)3.5T AWD", "Genesis"),
    ("SANTA FE (D) 2.2 프레스티지", "Hyundai"),
    ("K5 (G) 2.0 럭셔리", "Kia"),
    ("TIVOLI (G) 1.6", "KG Mobility"),
    ("QM6 (G) 2.0", "Renault Korea"),
    ("BMW 523D", "BMW"),
    ("BENZ E 250", "Mercedes-Benz"),
    ("JEEP GRAND CHEROKEE", "Jeep"),
    ("TESLA MODEL 3", "Tesla"),
]


@pytest.mark.parametrize("name,expected", REAL_LISTINGS)
def test_resolves_real_listing_strings(name: str, expected: str) -> None:
    assert resolve_manufacturer(name) == expected


def test_model_name_is_never_returned_as_a_brand() -> None:
    """The headline bug: 'SORENTO'/'GRANDEUR' are models, not manufacturers."""
    brands = set(RULES)
    for name, _ in REAL_LISTINGS:
        resolved = resolve_manufacturer(name)
        assert resolved in brands, f"{name!r} resolved to a non-brand {resolved!r}"


def test_unknown_input_returns_none() -> None:
    assert resolve_manufacturer("SOMETHING UNRECOGNISED 1.6") is None
    assert resolve_manufacturer("") is None
    assert resolve_manufacturer(None) is None


def test_longest_keyword_wins() -> None:
    """'SANTA FE' must not be shadowed by a shorter overlapping keyword."""
    assert resolve_manufacturer("SANTA FE 2.2") == "Hyundai"
    assert resolve_manufacturer("GRAND KOLEOS") == "Renault Korea"
    assert resolve_manufacturer("GRAND CHEROKEE LIMITED") == "Jeep"


def test_keywords_do_not_match_inside_longer_tokens() -> None:
    """Boundaries are non-alphanumeric: K5 must not match K50 or AK5."""
    assert resolve_manufacturer("K50 SPECIAL") is None
    assert resolve_manufacturer("XK9 CONCEPT") is None
    assert resolve_manufacturer("I300 SPORT") is None


def test_parser_falls_back_to_unknown_not_none() -> None:
    """The API contract keeps a string; clients branch on 'UNKNOWN'."""
    from app.parsers.lotte_parser import LotteParser

    brand, model = LotteParser()._parse_brand_model("SOMETHING UNRECOGNISED 1.6")
    assert brand == UNKNOWN_BRAND
    assert model == "SOMETHING UNRECOGNISED 1.6"


def _frontend_pairs() -> set[tuple[str, str]]:
    """Extract (brand, keyword) pairs from the TypeScript resolver."""
    source = FRONTEND_RESOLVER.read_text(encoding="utf-8")
    # Only the RULES array, so the doc comment's examples are not scanned.
    body = source[source.index("const RULES"): source.index("// Precompute")]

    pairs: set[tuple[str, str]] = set()
    for match in re.finditer(
        r'brand:\s*"([^"]+)"\s*,\s*keywords:\s*\[(.*?)\]', body, re.DOTALL
    ):
        brand = match.group(1)
        for keyword in re.findall(r'"([^"]+)"', match.group(2)):
            pairs.add((brand, keyword))
    return pairs


@pytest.mark.skipif(
    not FRONTEND_RESOLVER.is_file(),
    reason="frontend checkout not present alongside this repo",
)
def test_mapping_matches_the_frontend_resolver() -> None:
    """Guards the one real risk of porting: silent divergence.

    If this fails, the two sides would classify some car differently — the API
    saying Kia while the page renders Hyundai. Update both, not just one.
    """
    backend = {
        (brand, keyword)
        for brand, keywords in RULES.items()
        for keyword in keywords
    }
    frontend = _frontend_pairs()

    assert frontend, "could not parse RULES out of resolveManufacturer.ts"
    assert backend == frontend, (
        "manufacturer mapping drifted from the frontend.\n"
        f"  only in backend : {sorted(backend - frontend)}\n"
        f"  only in frontend: {sorted(frontend - backend)}"
    )
