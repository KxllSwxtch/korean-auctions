"""CORS is a deployment contract, and it has now broken twice without one test failing.

Incident one: the allowlist read `https://www.autobaza.vip,https://autobaza.vip`
for three days after the product moved to nonstop-motors.com. Incident two: it
read the nonstop-motors.com domains after the move to SMMotors Korea. Both times
every client-side fetch from the live frontend was refused at the preflight with
400 "Disallowed CORS origin" while the API looked healthy — /health answered 200
and every route answered curl normally, because CORS is enforced by the browser
and not by the server. Inspecting the running service tells you nothing.

The suite written after incident one did not catch incident two, and the reason
is worth stating plainly: it hardcoded the *then-current* brand as the expected
answer (`PRODUCTION_ORIGIN = "https://www.nonstop-motors.com"`, `assert "autobaza"
not in default`). That is a one-shot ratchet — it guards the rename that already
happened, never the next one. It stayed green while production was down.

So this file is now split by what each part actually tests:

  Layer 1  the MIDDLEWARE, using deliberately fake brands. ~200 lines that can
           never rot, because they contain no real hostname to go stale.
  Layer 2  the SHIPPED CONFIG, via properties derived from the values themselves
           rather than compared against a literal.
  Layer 3  CROSS-ARTIFACT AGREEMENT between config.py, render.yaml and
           env.example — three hand-edited files whose whole job is to agree.

The one invariant none of these can express — "the allowlist names a domain that
is actually live and actually ours" — needs the real internet, and lives in
tests/test_cors_live.py.

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
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.cors import configure_cors, resolve_origin_regex


ROOT = Path(__file__).resolve().parents[1]

LOOPBACK_PREFIXES = ("http://localhost", "http://127.0.0.1")


# ── Layer 1 fixtures ─────────────────────────────────────────────────────────
# Deliberately fake. Everything from here to the Layer 2 banner tests the
# middleware's behaviour, which has nothing to do with what this product is
# called. Using real hostnames here is what forced a rename to touch tests that
# had no business changing.

FAKE_PROJECT = "exampleapp"
FAKE_TEAM = "example-team"
FAKE_PRODUCTION_ORIGIN = "https://www.example-product.test"
FAKE_APEX_ORIGIN = "https://example-product.test"
FAKE_VERCEL_ALIAS_ORIGIN = f"https://{FAKE_PROJECT}.vercel.app"
DEFAULT_ORIGINS = (
    f"{FAKE_PRODUCTION_ORIGIN},{FAKE_APEX_ORIGIN},{FAKE_VERCEL_ALIAS_ORIGIN}"
)

# Mirrors the SHAPE shipped in render.yaml, including the alternation. A fixture
# that kept the old single-wildcard form would stop describing the mechanism
# actually deployed, and the lookalike it admits (see `-git-<team>` below) would
# go untested here.
PREVIEW_REGEX = (
    rf"https://{FAKE_PROJECT}-"
    rf"(git-[a-z0-9-]{{1,40}}|[a-z0-9]{{6,16}})"
    rf"-{FAKE_TEAM}\.vercel\.app"
)
PREVIEW_BRANCH_ORIGIN = f"https://{FAKE_PROJECT}-git-main-{FAKE_TEAM}.vercel.app"
PREVIEW_DEPLOY_ORIGIN = f"https://{FAKE_PROJECT}-9f3ab12cd-{FAKE_TEAM}.vercel.app"


def lookalike_origins(*, project: str, team: str, https_origins: list[str]) -> list[str]:
    """Origins an attacker can actually obtain, each refused by one property.

    Generated from the project/team/allowlist rather than written out, so the
    list tracks a rename automatically instead of being the next thing to rot.
    Each entry is annotated with the single pattern property that refuses it —
    delete that property and the corresponding entry starts passing, which is
    the point of enumerating them.
    """
    alias = f"https://{project}.vercel.app"
    preview_branch = f"https://{project}-git-main-{team}.vercel.app"

    generated = [
        # fullmatch (not .match / .search): nothing may follow vercel.app
        f"{alias}.evil.com",
        f"{preview_branch}.evil.com",
        # start anchor: nothing may precede the project name
        f"https://evil-{project}-git-main-{team}.vercel.app",
        # escaped dots: with a bare `.`, `.vercel.app` also accepts `xvercelxapp`
        f"https://{project}-git-main-{team}xvercelxapp",
        # a different registrable domain that merely starts the same way
        f"{preview_branch}.co",
        # vercel.app is a shared suffix — these are projects a stranger can
        # create in their own team, and only the pinned team slug refuses them
        f"https://{project}-x.vercel.app",
        f"https://{project}-evil-attackerteam.vercel.app",
        # THE ALTERNATION CASE. A single `[a-z0-9-]{1,48}` middle segment
        # accepts this: the wildcard matches just `git` and the `-<first label
        # of the team slug>` is absorbed by a shorter attacker-owned slug.
        # Requiring `git-` to be followed by >=1 branch character refuses it.
        f"https://{project}-git-{team}.vercel.app",
        # the retired brands this list has twice wrongly contained
        "https://autobaza.vip",
    ]

    for origin in https_origins:
        # nothing may follow an allowed origin
        generated.append(f"{origin}.evil.com")
        # an Origin is scheme + host + port: no scheme downgrade,
        generated.append(origin.replace("https://", "http://", 1))
        # and no added port
        generated.append(f"{origin}:8443")

    return generated


LOOKALIKE_ORIGINS = lookalike_origins(
    project=FAKE_PROJECT,
    team=FAKE_TEAM,
    https_origins=[
        FAKE_PRODUCTION_ORIGIN,
        FAKE_APEX_ORIGIN,
        FAKE_VERCEL_ALIAS_ORIGIN,
    ],
)


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


# ═══ Layer 1 — the middleware ════════════════════════════════════════════════


@pytest.mark.parametrize(
    "origin", [FAKE_PRODUCTION_ORIGIN, FAKE_APEX_ORIGIN, FAKE_VERCEL_ALIAS_ORIGIN]
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
    assert _preflight(_app(origin_regex=None), FAKE_PRODUCTION_ORIGIN).status_code == 200


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
    assert _preflight(client, FAKE_PRODUCTION_ORIGIN).status_code == 200
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
        not in _preflight(client, FAKE_PRODUCTION_ORIGIN).headers
    )
    assert (
        "access-control-allow-credentials"
        not in client.get("/probe", headers={"Origin": FAKE_PRODUCTION_ORIGIN}).headers
    )


# ═══ Layer 2 — the shipped configuration ═════════════════════════════════════
#
# Derived properties, never a literal comparison against a brand. A literal is
# what made the previous suite pass through two renames: `https://www.nonstop-
# motors.com` satisfies every structural property you can name and is 410 Gone.


def _shipped_origins() -> list[str]:
    """The allowlist the deployed service actually reads.

    Environment-independent: reads the class default, not the process env.
    CORS_ALLOWED_ORIGINS is not set in the Render dashboard and render.yaml has
    never been synced, so this string *is* production.
    """
    default = Settings.model_fields["cors_allowed_origins"].default
    return [o.strip() for o in default.split(",") if o.strip()]


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


def _env_example_value(key: str) -> Optional[str]:
    """Read one KEY=VALUE line out of env.example, ignoring comments."""
    for line in (ROOT / "env.example").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        if name.strip() == key:
            return value.strip()
    return None


def _split(value: Optional[str]) -> set[str]:
    return {o.strip() for o in (value or "").split(",") if o.strip()}


def _without_loopback(origins) -> set[str]:
    return {o for o in origins if not o.startswith(LOOPBACK_PREFIXES)}


def test_the_shipped_allowlist_is_structurally_sound() -> None:
    """Properties, not a brand string.

    Replaces the old `assert "autobaza" not in default`, which could only ever
    catch the rename that had already happened. Every assertion here stays
    meaningful across any number of future renames.
    """
    origins = _shipped_origins()

    assert origins, "the allowlist is empty; every browser request would fail"
    assert "*" not in origins, 'allow_origins=["*"] is never correct here'
    assert not any("*" in o for o in origins), "wildcards are not expanded by Starlette"

    https = [o for o in origins if o.startswith("https://")]
    assert https, (
        "the allowlist contains no https origin — this is the dev-only config, "
        "and deploying it refuses every request from the real site"
    )

    for origin in origins:
        assert origin == origin.strip(), f"{origin!r} has surrounding whitespace"
        assert origin == origin.lower(), (
            f"{origin!r} is not lowercase; Starlette compares the Origin header "
            "byte-for-byte, so a capital letter silently never matches"
        )
        assert " " not in origin, f"{origin!r} contains a space"

        parts = urlsplit(origin)
        assert parts.scheme in ("http", "https"), f"{origin!r} has no usable scheme"
        assert parts.netloc, f"{origin!r} has no host"
        assert parts.path == "", (
            f"{origin!r} carries a path or a trailing slash. An Origin header is "
            "scheme + host + port and never has either, so this entry can never "
            "match anything — it is dead config that reads as live."
        )
        assert not parts.query and not parts.fragment, f"{origin!r} is not an origin"

        if not origin.startswith(LOOPBACK_PREFIXES):
            assert origin.startswith("https://"), (
                f"{origin!r} is plaintext http on a non-loopback host"
            )

    assert len(origins) == len(set(origins)), "the allowlist contains duplicates"


def test_the_regex_default_is_none() -> None:
    """A permissive default here is allow_origins=["*"] wearing a disguise, and
    it would silently apply to every deployment — and every fork — that never
    sets the variable."""
    assert Settings.model_fields["cors_allowed_origin_regex"].default is None


# ── the shipped preview pattern ──────────────────────────────────────────────


def _shipped_preview_pattern() -> Optional[str]:
    return _blueprint_value("CORS_ALLOWED_ORIGIN_REGEX")


def _project_and_team(pattern: str) -> tuple[str, Optional[str]]:
    r"""Recover the project and team slug the shipped pattern is pinned to.

    Derived so the attack list below tracks a rename by itself, and written to
    cope with any pattern shape — not just the one currently shipped. If it
    parsed only the alternation, then swapping in a looser pattern would fail
    this test with "cannot parse", hiding the fact that the pattern is *unsafe*
    behind a complaint that it is *unfamiliar*. The caller asserts both halves,
    so an unparseable team slug is still a failure, just an accurate one.

    project = the literal run after https:// and before the first metacharacter.
    team    = the trailing literal run before \.vercel\.app, or None when the
              pattern ends in a character class (which is the "any Vercel team"
              bug, and must be reported as such).
    """
    head = re.match(r"https://[a-z0-9-]+", pattern)
    project = head.group(0)[len("https://") :].rstrip("-") if head else ""

    suffix = r"\.vercel\.app"
    team: Optional[str] = None
    if pattern.endswith(suffix):
        trailing = re.search(r"[-a-z0-9]+$", pattern[: -len(suffix)])
        if trailing:
            team = trailing.group(0).lstrip("-") or None
    return project, team


def test_the_blueprint_preview_pattern_refuses_every_lookalike() -> None:
    """Holds the shipped pattern to the properties Layer 1 pins, so a later edit
    cannot loosen it to `.*` or drop the escaped dots. Skips when previews are
    deliberately disabled, which is a valid deployment choice."""
    pattern = _shipped_preview_pattern()
    if not pattern:
        pytest.skip("preview origins are disabled in the blueprint")

    assert "$" not in pattern and "^" not in pattern, (
        "Starlette uses re.fullmatch(), which already anchors both ends, so the "
        "pattern needs no anchors — and `$` is actively unsafe because it also "
        "matches before a trailing newline"
    )
    assert pattern.endswith(r"\.vercel\.app"), (
        "every dot must be escaped — a bare `.` matches any character, so "
        "`.vercel.app` would also accept `xvercelxapp`"
    )

    project, team = _project_and_team(pattern)
    assert project and "/" not in project, f"unparseable project in {pattern!r}"
    assert team is not None and re.fullmatch(r"[a-z0-9-]+", team), (
        "the pattern must end with a literal team slug before `.vercel.app`; "
        "vercel.app is a shared suffix, so a pattern ending in an open character "
        "class also matches a project created in someone else's Vercel team"
    )
    assert pattern.startswith(f"https://{project}-"), (
        "the pattern must anchor on the project name, or a lookalike project "
        "name can precede it"
    )

    compiled = re.compile(pattern)

    # It must actually admit the two shapes Vercel mints, or it is a pattern
    # that refuses everything and the loop below would pass vacuously.
    for origin in (
        f"https://{project}-git-main-{team}.vercel.app",
        f"https://{project}-9f3ab12cd-{team}.vercel.app",
    ):
        assert compiled.fullmatch(origin), (
            f"the shipped pattern rejects the real preview origin {origin}"
        )

    for origin in lookalike_origins(
        project=project,
        team=team,
        https_origins=[o for o in _shipped_origins() if o.startswith("https://")],
    ):
        assert not compiled.fullmatch(origin), (
            f"render.yaml's preview pattern accepts the lookalike {origin}"
        )


# ═══ Layer 3 — the three artifacts must agree ════════════════════════════════


def test_config_render_yaml_and_env_example_declare_the_same_origins() -> None:
    """The assertion that catches a half-done rename.

    This is not "code equals itself": app/core/config.py, render.yaml and
    env.example are three independently hand-edited files whose entire job is to
    agree, and they have disagreed in production. config.py is what the deployed
    service reads today; render.yaml is what Render would re-apply on a blueprint
    sync, so a drift there is a regression waiting on the next push; env.example
    is what a new contributor copies.

    Loopback is excluded: render.yaml deliberately omits it (it is a deployment
    blueprint, not a dev config) and says so at the CORS_ALLOWED_ORIGINS comment.
    """
    from_config = _without_loopback(_shipped_origins())
    from_blueprint = _split(_blueprint_value("CORS_ALLOWED_ORIGINS"))
    from_env_example = _without_loopback(_split(_env_example_value("CORS_ALLOWED_ORIGINS")))

    assert from_blueprint, "render.yaml no longer sets CORS_ALLOWED_ORIGINS"
    assert from_env_example, "env.example no longer sets CORS_ALLOWED_ORIGINS"

    assert from_config == from_blueprint, (
        "app/core/config.py and render.yaml disagree.\n"
        f"  only in config.py:   {sorted(from_config - from_blueprint)}\n"
        f"  only in render.yaml: {sorted(from_blueprint - from_config)}"
    )
    assert from_config == from_env_example, (
        "app/core/config.py and env.example disagree.\n"
        f"  only in config.py:    {sorted(from_config - from_env_example)}\n"
        f"  only in env.example:  {sorted(from_env_example - from_config)}"
    )
