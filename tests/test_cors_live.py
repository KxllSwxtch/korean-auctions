"""The only CORS assertion that can go red with nobody editing anything.

tests/test_cors.py checks that the shipped allowlist is well-formed, internally
consistent, and matched correctly by the middleware. All of that was already
true on both days this broke. `https://www.nonstop-motors.com` is a perfectly
well-formed https origin with no path, no wildcard and no typo — and it is 410
Gone. No amount of offline structure can tell a correct allowlist from a
correctly-shaped dead one; that distinction only exists on the live internet.

So this file asserts the two things a unit test provably cannot:

  1. every origin the API allows still resolves to a page we actually publish;
  2. the *deployed* process — not the repo — really does accept them.

(2) matters on its own: a value set in the Render dashboard silently shadows the
code default, so the repo can be perfectly correct while production is not. A
real preflight is the only way to see through that.

Network-gated exactly like tests/test_glovis_live.py, because a test that
depends on the internet must never be able to fail a normal `pytest` run. That
also means it protects nothing unless someone runs it — run it after any deploy
that touches CORS, and after any frontend domain change:

    RUN_CORS_LIVE=1 python -m pytest tests/test_cors_live.py -q

Sanity gate: run it *before* landing a CORS fix and confirm it fails. A live
test that is green before the fix is not testing anything.
"""

from __future__ import annotations

import os

import pytest
import requests

from app.core.config import Settings


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_CORS_LIVE") != "1",
    reason="set RUN_CORS_LIVE=1 to preflight the deployed API from the live frontend origins",
)

API_BASE = os.getenv("CORS_LIVE_API_BASE", "https://korean-auctions-1.onrender.com")

# Any always-on, unauthenticated route works; this one needs no query string and
# no provider credentials, so a preflight failure here is unambiguously CORS.
PROBE_PATH = "/api/v1/bikemart/brands"

# Must appear in the HTML of every origin we claim as ours. Still a literal, but
# asserted against the live internet rather than against another literal in the
# repo, so it fails when reality diverges from it in either direction: a dead
# domain (410/DNS failure) and a live domain serving the *previous product* both
# go red. That second case is not hypothetical — nonstopautoapp.vercel.app
# answers 200 to this day with the retired brand in its <title>.
BRAND_MARKER = "smmotors korea"

# Origins deliberately allowed that BRAND_MARKER cannot vouch for. Each needs a
# reason and a removal condition — an unexplained entry here is how a genuinely
# dead origin would hide from assertion (1).
LIVENESS_EXEMPT = {
    # Retired brand, kept in the allowlist on purpose. www is already 410 Gone
    # and the apex 307s to it. Delete these three from config.py, render.yaml,
    # env.example and this set together, once the old Vercel project is gone.
    "https://www.nonstop-motors.com",
    "https://nonstop-motors.com",
    "https://nonstopautoapp.vercel.app",
    # Vercel Deployment Protection 302s every *-dmitriy-shins-projects.vercel.app
    # host to vercel.com/sso-api, so an unauthenticated GET can never see our
    # HTML. The preflight assertion below still covers it.
    "https://smmotorskorea-dmitriy-shins-projects.vercel.app",
}

TIMEOUT = 30


def _shipped_https_origins() -> list[str]:
    """The https origins the deployed service reads (see tests/test_cors.py)."""
    default = Settings.model_fields["cors_allowed_origins"].default
    return [
        o.strip()
        for o in default.split(",")
        if o.strip().startswith("https://")
    ]


def _preflight(origin: str) -> requests.Response:
    return requests.options(
        f"{API_BASE}{PROBE_PATH}",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        timeout=TIMEOUT,
    )


LIVE_ORIGINS = [o for o in _shipped_https_origins() if o not in LIVENESS_EXEMPT]
ALL_HTTPS_ORIGINS = _shipped_https_origins()


def test_there_is_something_to_check() -> None:
    """Guards against the whole file passing vacuously if the parsing above
    silently yields an empty list."""
    assert ALL_HTTPS_ORIGINS, "no https origins found in the shipped allowlist"
    assert LIVE_ORIGINS, "every shipped origin is liveness-exempt; that is a bug"


@pytest.mark.parametrize("origin", LIVE_ORIGINS)
def test_every_allowed_origin_still_serves_our_product(origin: str) -> None:
    """Assertion (1). This is what would have caught both outages on day one.

    Verified to discriminate correctly today: the smmotorskorea hosts answer 200
    with 'SMMotors Korea' in the title; www.nonstop-motors.com answers 410; and
    nonstopautoapp.vercel.app answers 200 but titles itself 'Nonstop Motors'.
    """
    try:
        response = requests.get(origin, timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException as exc:
        pytest.fail(f"{origin} is in the CORS allowlist but unreachable: {exc}", pytrace=False)

    assert response.ok, (
        f"{origin} is in the CORS allowlist but answers HTTP {response.status_code}. "
        "Either the domain is retired and the allowlist was not updated, or the "
        "frontend is down."
    )
    assert BRAND_MARKER in response.text.lower(), (
        f"{origin} is in the CORS allowlist but does not serve this product "
        f"({BRAND_MARKER!r} absent from the HTML). A rename most likely left this "
        "entry pointing at a retired brand — the exact failure this file exists for."
    )


@pytest.mark.parametrize("origin", ALL_HTTPS_ORIGINS)
def test_the_deployed_api_accepts_every_allowed_origin(origin: str) -> None:
    """Assertion (2), against the running service rather than the repo."""
    response = _preflight(origin)
    assert response.status_code == 200, (
        f"the deployed API refuses {origin} at the preflight "
        f"(HTTP {response.status_code}: {response.text.strip()[:80]}). Every "
        "client-side fetch from that origin fails and the site renders with no "
        "data, while /health keeps answering 200."
    )
    assert response.headers.get("access-control-allow-origin") == origin


def test_the_deployed_api_accepts_a_preview_deployment() -> None:
    """Proves the preview regex is installed in the *deployed process*.

    A synthesized origin, not a real deployment: this must keep working when no
    preview happens to be live. It is also the only way to observe a dashboard
    CORS_ALLOWED_ORIGIN_REGEX that differs from render.yaml.
    """
    origin = "https://smmotorskorea-000000000-dmitriy-shins-projects.vercel.app"
    response = _preflight(origin)
    if response.status_code != 200:
        pytest.fail(
            f"the deployed API refuses the preview origin {origin} "
            f"(HTTP {response.status_code}). Vercel mints a hostname per branch "
            "and per commit, so no exact allowlist can cover previews — set "
            "CORS_ALLOWED_ORIGIN_REGEX in the Render dashboard to the pattern "
            "in render.yaml.",
            pytrace=False,
        )
    assert response.headers.get("access-control-allow-origin") == origin


def test_an_unrelated_origin_is_still_refused() -> None:
    """The negative control. Without it, every assertion above is also satisfied
    by allow_origins=["*"], which is what this configuration used to be."""
    response = _preflight("https://example.com")
    assert "access-control-allow-origin" not in response.headers
    assert response.status_code == 400


def test_a_lookalike_of_a_real_origin_is_refused() -> None:
    """`https://<ours>.evil.com` is registrable by anyone and is refused only
    because Starlette uses re.fullmatch and exact string comparison."""
    response = _preflight("https://www.smmotorskorea.com.evil.com")
    assert "access-control-allow-origin" not in response.headers
    assert response.status_code == 400
