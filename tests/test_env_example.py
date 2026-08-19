"""env.example must stay a dotenv file the application can actually load.

`Settings.model_config["extra"]` is pydantic-settings' "forbid" default, so a
key present in .env but not declared on Settings raises ValidationError at
import and takes the whole application down — before any route, health check
or log line. env.example is the file people copy to .env, which makes an
undocumented or stale key there a boot-time outage waiting to happen.

Motivating incident: env.example documented 13 of ~70 variables and zero
credentials, so a fresh clone produced a backend that started cleanly and
answered 503 on every login-gated auction route.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings


ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / "env.example"

# Provided by the platform rather than by a dotenv file, so their absence from
# env.example is intentional and must not fail the coverage check below.
PLATFORM_PROVIDED = {"PORT"}

# Credential-bearing keys whose names carry no _USERNAME/_PASSWORD/_TOKEN
# suffix, so the suffix rule below cannot recognise them. Both hold a JSON
# document with credentials inside it.
CREDENTIAL_BEARING_NAMES = {"AUCTION_PROXY_POOL", "SSANCAR_PROXY_URLS"}


def _declared_names() -> set[str]:
    return {name.upper() for name in Settings.model_fields}


def _documented_names() -> list[str]:
    names: list[str] = []
    for raw in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        names.append(line.split("=", 1)[0].strip())
    return names


def test_env_example_exists() -> None:
    assert ENV_EXAMPLE.is_file(), "env.example is the documented .env template"


def test_every_documented_key_is_a_declared_setting() -> None:
    """The failure this test exists to prevent: copying env.example kills boot."""
    undeclared = sorted(set(_documented_names()) - _declared_names())
    assert not undeclared, (
        "env.example documents keys that are not fields on Settings: "
        f"{undeclared}. With extra='forbid', copying env.example to .env would "
        "raise ValidationError at import. Declare them in app/core/config.py "
        "(see the declaration-only blocks) or remove them from env.example."
    )


def test_env_example_has_no_duplicate_keys() -> None:
    """A duplicate silently wins over the earlier line — usually not intended."""
    names = _documented_names()
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert not duplicates, f"env.example defines these keys twice: {duplicates}"


def test_every_credential_variable_is_documented() -> None:
    """Credentials are the class of variable that was missing entirely."""
    documented = set(_documented_names())
    credentials = {
        name
        for name in _declared_names()
        if name.endswith(("_USERNAME", "_PASSWORD", "_JWT_TOKEN"))
    }
    missing = sorted(credentials - documented)
    assert not missing, (
        f"credential variables absent from env.example: {missing}. An operator "
        "has no way to discover a variable that appears in neither the template "
        "nor the code they are reading."
    )


def test_env_example_covers_every_declared_setting() -> None:
    """Keeps the template from drifting as new fields are added."""
    missing = sorted(_declared_names() - set(_documented_names()) - PLATFORM_PROVIDED)
    assert not missing, (
        f"Settings fields absent from env.example: {missing}. Add them (secrets "
        "as empty placeholders) or list them in PLATFORM_PROVIDED with a reason."
    )


def test_settings_loads_from_env_example(monkeypatch: pytest.MonkeyPatch) -> None:
    """The end-to-end version of the checks above: it must actually parse."""
    for name in _declared_names():
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=str(ENV_EXAMPLE))

    # A sanity value proving the file was parsed rather than silently skipped.
    assert settings.app_name


def test_secret_placeholders_are_empty() -> None:
    """env.example is committed; it must never carry a real credential."""
    offenders: list[str] = []
    for raw in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        secret = name.endswith(
            ("_USERNAME", "_PASSWORD", "_JWT_TOKEN", "_TOKEN")
        ) or name in CREDENTIAL_BEARING_NAMES
        if secret and value.strip():
            offenders.append(name)
    assert not offenders, (
        f"env.example assigns a value to secret-bearing keys: {offenders}. "
        "This file is tracked in git; placeholders must be empty."
    )
