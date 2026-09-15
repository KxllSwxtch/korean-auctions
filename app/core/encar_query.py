"""Escaping for values placed into an Encar upstream query string.

Both app/routes/encar_proxy.py and app/services/encar_service.py build their
Encar URL by hand — `f"{ENCAR_API}/search/car/list/premium?q={q}&sr={sr}…"`
— instead of handing `q`/`sr`/`inav` to aiohttp's `params=` mapping, because
Encar rejects a percent-encoded query (letting yarl double-encode Korean and
`|` silently returns Count: 0). That hand-built string still passes through
yarl once, when aiohttp parses it to make the actual request, and yarl's
rules for three ASCII characters do not match what Encar expects on the
wire:

  - `+` survives yarl unescaped, and Encar's query grammar reads a literal
    `+` the same as a real space. `가솔린+전기` (a hybrid fuel-type/trim
    value) silently becomes `가솔린 전기` and the search returns 0 results
    instead of thousands.
  - `&` is the query-parameter separator; a raw `&` inside a value (for
    example a free-text keyword) splits the parameter and can smuggle in a
    new one.
  - `#` starts the URL fragment; anything after a raw `#` never reaches
    Encar as part of the query string at all.

This module exists so both callers escape those three characters the same
way, in one place, before building the URL.

Left alone on purpose:
  - `%`: legacy callers pre-encode Korean (the default `q` in
    encar_service.py and app/routes/encar.py), and yarl keeps a valid `%XX`
    escape as-is (fixing up only a lone, invalid `%` to `%25`). The frontend
    is responsible for stripping `%` from free-text keyword/plate input.
  - Space: yarl encodes a literal space as `+`, which is exactly what Encar
    expects for a space — this is why `2.5 가솔린 2WD`-style values with
    real spaces already work today.
  - Korean and `|`: yarl percent-encodes them exactly once, which is what
    Encar wants (see test_upstream_url_keeps_raw_korean_and_pipes).
  - `(`, `)` and `.`: Encar's own grammar escaping (`.` → `_.`, `)` → `_)`)
    is the caller's job, applied before a value reaches this function.
"""

from __future__ import annotations

_ENCAR_QUERY_ESCAPES = str.maketrans({"+": "%2B", "&": "%26", "#": "%23"})


def encode_encar_query_param(value: str) -> str:
    """Percent-escape `+`, `&` and `#` in a value bound for an Encar query
    string parameter (`q`, `sr` or `inav`).

    Idempotent: the output never contains a raw `+`, `&` or `#`, so it is
    safe to apply more than once (both the proxy route and the legacy
    service call it on user-supplied values). Every other character is
    left untouched — see the module docstring for why.
    """
    return value.translate(_ENCAR_QUERY_ESCAPES)
