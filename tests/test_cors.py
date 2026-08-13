"""CORS is a deployment contract, and it broke without one test failing.

The allowlist read `https://www.autobaza.vip,https://autobaza.vip` for three days
after the product moved to nonstop-motors.com, so every client-side fetch from
the live frontend was refused at the preflight with 400 "Disallowed CORS origin".
The API looked healthy the whole time: /health answered 200 and every route
answered curl normally, because CORS is enforced by the browser and not by the
server. That is precisely why it needs a test — inspecting the running service
tells you nothing.

These tests apply the real wiring (app.core.cors.configure_cors) to a three-line
app rather than importing main, which drags in every router and provider service.
Settings is constructed directly: get_settings() is @lru_cache'd, so
monkeypatching the environment cannot change what it returns once anything has
imported it — and clearing that cache would not help either, because the object
under test is a CORSMiddleware instance already frozen inside main.app at import
time. Settings(...) is not cached and takes field overrides at the highest
pydantic-settings priority, which sidesteps the cache entirely instead of
fighting it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.cors import configure_cors, resolve_origin_regex


ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_ORIGIN = "https://www.nonstop-motors.com"
APEX_ORIGIN = "https://nonstop-motors.com"
VERCEL_ALIAS_ORIGIN = "https://nonstopautoapp.vercel.app"
DEFAULT_ORIGINS = f"{PRODUCTION_ORIGIN},{APEX_ORIGIN},{VERCEL_ALIAS_ORIGIN}"

# A stand-in team slug: these tests pin the SHAPE of the pattern, and the real
# slug lives in render.yaml. test_the_blueprint_preview_pattern_refuses_every_
# lookalike below is what holds the shipped value to the same properties.
TEAM = "nonstopauto"
PREVIEW_REGEX = rf"https://nonstopautoapp-[a-z0-9-]{{1,48}}-{TEAM}\.vercel\.app"
PREVIEW_BRANCH_ORIGIN = f"https://nonstopautoapp-git-main-{TEAM}.vercel.app"
PREVIEW_DEPLOY_ORIGIN = f"https://nonstopautoapp-9f3ab12cd-{TEAM}.vercel.app"

# Each entry is an origin an attacker can actually obtain, paired with the single
# pattern property that refuses it. Delete that property and the corresponding
# line starts passing — which is the point of listing them individually.
LOOKALIKE_ORIGINS = [
    # fullmatch (not .match / .search): nothing may follow vercel.app
    f"{VERCEL_ALIAS_ORIGIN}.evil.com",
    f"{PREVIEW_BRANCH_ORIGIN}.evil.com",
    f"{PRODUCTION_ORIGIN}.evil.com",
    # start anchor: nothing may precede the project name
    f"https://evil-nonstopautoapp-git-main-{TEAM}.vercel.app",
    # escaped dots: with a bare `.`, `.vercel.app` also accepts `xvercelxapp`
    f"https://nonstopautoapp-git-main-{TEAM}xvercelxapp",
    # a different registrable domain that merely starts the same way
    f"{PREVIEW_BRANCH_ORIGIN}.co",
    "https://nonstopauto-motors.com",
    # vercel.app is a shared suffix — these are projects a stranger can create
    # in their own Vercel team, and only the pinned team slug refuses them
    "https://nonstopautoapp-x.vercel.app",
    "https://nonstopautoapp-evil-attackerteam.vercel.app",
    # scheme downgrade and port suffix: an Origin is scheme + host + port
    "http://www.nonstop-motors.com",
    f"{PRODUCTION_ORIGIN}:8443",
    # the retired brand, which is what the allowlist wrongly contained
    "https://autobaza.vip",
]


def _app(
    *,
    origins: str = DEFAULT_ORIGINS,
    origin_regex: Optional[str] = PREVIEW_REGEX,
) -> TestClient:
    """A minimal app carrying the production CORS wiring.

    No lifespan and no routers: this asserts middleware behaviour. TestClient
    only runs a lifespan when used as a context manager, so a bare client here
    never touches the scheduler or any provider session.
    """
    app = FastAPI()

    @app.get("/probe")
    async def probe() -> dict[str, bool]:
        return {"ok": True}

    settings = Settings(
        cors_allowed_origins=origins,
        cors_allowed_origin_regex=origin_regex,
    )
    configure_cors(app, settings)
    return TestClient(app)


def _preflight(client: TestClient, origin: str):
    """A real browser preflight: OPTIONS plus Access-Control-Request-Method.

    Without that second header CORSMiddleware treats the request as a simple one
    and never runs the origin check at all, so a test that omits it passes no
    matter what the allowlist says.
    """
    return client.options(
        "/probe",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )


# ── allowed origins ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "origin", [PRODUCTION_ORIGIN, APEX_ORIGIN, VERCEL_ALIAS_ORIGIN]
)
def test_allowed_origin_passes_preflight_and_the_actual_response(origin: str) -> None:
    """Both halves. A preflight that passes buys nothing if the real response
    omits Access-Control-Allow-Origin — the browser discards it either way."""
    client = _app()

    pre = _preflight(client, origin)
    assert pre.status_code == 200
    assert pre.headers["access-control-allow-origin"] == origin
    assert "GET" in pre.headers["access-control-allow-methods"]
    assert pre.headers["access-control-max-age"] == "600"

    actual = client.get("/probe", headers={"Origin": origin})
    assert actual.status_code == 200
    assert actual.headers["access-control-allow-origin"] == origin
    # Without Vary: Origin a shared cache could hand one origin's ACAO to another.
    assert "origin" in actual.headers["vary"].lower()


@pytest.mark.parametrize("origin", [PREVIEW_BRANCH_ORIGIN, PREVIEW_DEPLOY_ORIGIN])
def test_preview_deployment_origins_are_allowed(origin: str) -> None:
    """Both Vercel shapes: the per-branch alias and the per-commit URL."""
    client = _app()

    assert _preflight(client, origin).headers["access-control-allow-origin"] == origin
    actual = client.get("/probe", headers={"Origin": origin})
    assert actual.headers["access-control-allow-origin"] == origin


# ── refused origins ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("origin", LOOKALIKE_ORIGINS)
def test_lookalike_origins_are_refused(origin: str) -> None:
    """Each of these is reachable by an attacker; each must fail the preflight."""
    pre = _preflight(_app(), origin)
    assert pre.status_code == 400
    assert pre.text == "Disallowed CORS origin"
    assert "access-control-allow-origin" not in pre.headers


def test_unlisted_origin_is_refused() -> None:
    pre = _preflight(_app(), "https://example.com")
    assert pre.status_code == 400
    assert "access-control-allow-origin" not in pre.headers


def test_a_refused_origin_still_gets_a_normal_body_without_the_header() -> None:
    """CORS is enforced by the browser, not the server, and this documents it.

    A simple GET from a refused origin is executed and answered 200 — the
    response simply carries no Access-Control-Allow-Origin, so the browser
    refuses to hand it to the page. Anyone expecting a 403 here will misdiagnose
    the next incident, and anyone treating CORS as an authorization control will
    build on sand: curl ignores all of this.
    """
    response = _app().get("/probe", headers={"Origin": "https://example.com"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert "access-control-allow-origin" not in response.headers


# ── the regex is off unless it is on ─────────────────────────────────────────


def test_preview_origins_are_refused_when_no_regex_is_configured() -> None:
    """The safe default. Unset must mean "exact allowlist only", never "any"."""
    assert _preflight(_app(origin_regex=None), PREVIEW_BRANCH_ORIGIN).status_code == 400
    # The exact allowlist is untouched by the regex being absent.
    assert _preflight(_app(origin_regex=None), PRODUCTION_ORIGIN).status_code == 200


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_blank_regex_is_treated_as_unset(blank: Optional[str]) -> None:
    """env.example ships this key as an empty placeholder, so "" is the value a
    copied dotenv actually delivers. re.compile("") installs happily and matches
    only the empty Origin: dead config that reads like a live one."""
    settings = Settings(
        cors_allowed_origins=DEFAULT_ORIGINS,
        cors_allowed_origin_regex=blank,
    )
    assert settings.cors_origin_regex is None
    assert resolve_origin_regex(settings) is None


def test_a_malformed_regex_does_not_take_the_exact_allowlist_down() -> None:
    """re.compile runs inside CORSMiddleware.__init__, so an unguarded typo
    raises at import and leaves Render with a process that never starts — a total
    outage in place of a preview-only one."""
    client = _app(origin_regex="https://[unclosed")
    assert _preflight(client, PRODUCTION_ORIGIN).status_code == 200
    assert _preflight(client, PREVIEW_BRANCH_ORIGIN).status_code == 400


# ── credentials ──────────────────────────────────────────────────────────────


def test_credentials_are_not_granted() -> None:
    """No frontend call sets `credentials:`, and this header is the switch that
    makes every other CORS mistake expensive: with it set, Starlette reflects the
    caller's Origin instead of sending `*`, defeating the spec rule that forbids
    `*` on a credentialed request."""
    client = _app()
    assert (
        "access-control-allow-credentials"
        not in _preflight(client, PRODUCTION_ORIGIN).headers
    )
    assert (
        "access-control-allow-credentials"
        not in client.get("/probe", headers={"Origin": PRODUCTION_ORIGIN}).headers
    )


# ── the shipped configuration, not just the mechanism ────────────────────────


def test_the_code_default_names_the_live_frontend() -> None:
    """Environment-independent: reads the class default, not the process env.

    This default is what the deployed service actually runs — CORS_ALLOWED_ORIGINS
    is not set in the Render dashboard and render.yaml has never been synced — so
    this assertion guards production directly, not just a fallback. It is also
    what fails on the day someone renames the product again and forgets this file.
    """
    default = Settings.model_fields["cors_allowed_origins"].default
    assert PRODUCTION_ORIGIN in default
    assert APEX_ORIGIN in default
    assert "autobaza" not in default, "the allowlist still names the retired brand"
    assert "*" not in default


def test_the_regex_default_is_none() -> None:
    """A permissive default here is allow_origins=["*"] wearing a disguise."""
    assert Settings.model_fields["cors_allowed_origin_regex"].default is None


def _blueprint_value(key: str) -> Optional[str]:
    """Read one env var out of render.yaml without adding a YAML dependency.

    Hand-parsed for the same reason tests/test_env_example.py hand-parses
    env.example: PyYAML is in neither requirements.txt nor tests/requirements.txt,
    and a test that only runs where someone happens to have it installed is not a
    test.
    """
    lines = (ROOT / "render.yaml").read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.strip() != f"- key: {key}":
            continue
        for following in lines[index + 1 :]:
            stripped = following.strip()
            if stripped.startswith("- key:"):
                return None
            if stripped.startswith("value:"):
                return stripped.split("value:", 1)[1].strip().strip("'\"")
    return None


def test_the_blueprint_allows_the_production_frontend() -> None:
    """The assertion that would have caught this outage.

    render.yaml is what Render re-applies on every blueprint sync, so a dashboard
    hotfix that is not mirrored here regresses on the next push.
    """
    value = _blueprint_value("CORS_ALLOWED_ORIGINS")
    assert value is not None, "render.yaml no longer sets CORS_ALLOWED_ORIGINS"
    origins = [o.strip() for o in value.split(",") if o.strip()]
    assert PRODUCTION_ORIGIN in origins, (
        f"render.yaml allows {origins}, which does not include the live frontend; "
        "every browser request will fail its preflight"
    )
    assert APEX_ORIGIN in origins
    assert "*" not in origins
    assert not any("autobaza" in o for o in origins)


def test_the_blueprint_preview_pattern_refuses_every_lookalike() -> None:
    """Holds the shipped pattern to the properties the tests above pin, so a
    later edit cannot loosen it to `.*` or drop the escaped dots. Skips when
    previews are deliberately disabled, which is a valid deployment choice."""
    pattern = _blueprint_value("CORS_ALLOWED_ORIGIN_REGEX")
    if not pattern:
        pytest.skip("preview origins are disabled in the blueprint")

    assert "$" not in pattern and "^" not in pattern, (
        "Starlette uses re.fullmatch(), which already anchors both ends, so the "
        "pattern needs no anchors — and `$` is actively unsafe because it also "
        "matches before a trailing newline"
    )

    compiled = re.compile(pattern)
    for origin in LOOKALIKE_ORIGINS:
        assert not compiled.fullmatch(origin), (
            f"render.yaml's preview pattern accepts the lookalike {origin}"
        )

    # The loop above passes vacuously for a pattern that matches nothing, so pin
    # the structure that makes it both useful and safe. The team slug cannot be
    # hardcoded here (it is a deployment fact, not a code fact), so assert the
    # two literals that bound it instead.
    assert pattern.startswith("https://nonstopautoapp-"), (
        "the pattern must anchor on the project name, or a lookalike project "
        "name can precede it"
    )
    assert pattern.endswith(r"\.vercel\.app"), (
        "every dot must be escaped — a bare `.` matches any character, so "
        "`.vercel.app` would also accept `xvercelxapp`"
    )
    slug = pattern[len("https://nonstopautoapp-") : -len(r"\.vercel\.app")]
    assert slug.rstrip("-").endswith(tuple("abcdefghijklmnopqrstuvwxyz0123456789")), (
        "the pattern must end with a literal team slug before `.vercel.app`; "
        "vercel.app is a shared suffix, so a pattern ending in an open character "
        "class also matches a project created in someone else's Vercel team"
    )
