"""Release-blocking security regressions with secret-safe failure output."""

from __future__ import annotations

import ast
import asyncio
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
LEGACY_PROVIDER_FIELDS = {
    "autohub_username",
    "autohub_password",
    "lotte_username",
    "lotte_password",
    "happycar_username",
    "happycar_password",
    "kcar_username",
    "kcar_password",
}
LEGACY_PROVIDER_ENV = {name.upper() for name in LEGACY_PROVIDER_FIELDS}


def _fail(path: Path, line: int, message: str) -> None:
    pytest.fail(f"{path.relative_to(ROOT)}:{line}: {message}", pytrace=False)


def test_tracked_provider_credentials_are_environment_only() -> None:
    config_path = ROOT / "app/core/config.py"
    config_tree = ast.parse(config_path.read_text(encoding="utf-8"))
    settings_class = next(
        node
        for node in config_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Settings"
    )
    assignments = {
        node.target.id: node
        for node in settings_class.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }

    for field in sorted(LEGACY_PROVIDER_FIELDS):
        assignment = assignments.get(field)
        if assignment is None:
            _fail(config_path, 1, f"missing environment-only setting {field}")
        if not isinstance(assignment.value, ast.Constant) or assignment.value.value is not None:
            _fail(config_path, assignment.lineno, "credential setting has a tracked default")

    kcar_path = ROOT / "app/services/kcar_service.py"
    kcar_tree = ast.parse(kcar_path.read_text(encoding="utf-8"))
    expected_sources = {
        "username": "kcar_username",
        "password": "kcar_password",
    }
    found: set[str] = set()
    for node in ast.walk(kcar_tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and target.attr in expected_sources
        ):
            continue
        found.add(target.attr)
        value = node.value
        valid = (
            isinstance(value, ast.Attribute)
            and value.attr == expected_sources[target.attr]
            and isinstance(value.value, ast.Attribute)
            and value.value.attr == "settings"
            and isinstance(value.value.value, ast.Name)
            and value.value.value.id == "self"
        )
        if not valid:
            _fail(kcar_path, node.lineno, "credential is not sourced from settings")
    if found != expected_sources.keys():
        _fail(kcar_path, 1, "credential assignments are incomplete")

    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    for line_number, line in enumerate(readme.splitlines(), start=1):
        if re.match(r"^\s*-\s*(?:login|password|username|логин|пароль)\s*:", line, re.I):
            _fail(readme_path, line_number, "inline credential documentation is forbidden")
    missing_env = sorted(name for name in LEGACY_PROVIDER_ENV if name not in readme)
    if missing_env:
        _fail(readme_path, 1, "legacy provider environment variables are undocumented")


def test_main_app_imports_without_legacy_provider_credentials(tmp_path: Path) -> None:
    environment = os.environ.copy()
    for name in LEGACY_PROVIDER_ENV:
        environment.pop(name, None)
    environment["PYTHONPATH"] = str(ROOT)

    result = subprocess.run(
        [sys.executable, "-c", "import main; assert main.app is not None"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if result.returncode != 0:
        pytest.fail("main.py: application import requires provider credentials", pytrace=False)


def test_internal_glovis_cache_clear_rejects_non_ascii_token(monkeypatch) -> None:
    import main

    monkeypatch.setenv("GLOVIS_CACHE_ADMIN_TOKEN", "configured-test-token")
    response = asyncio.run(
        main.clear_glovis_cache_internal(x_admin_token="é")
    )

    if response.status_code != 403:
        pytest.fail("main.py: non-ASCII admin token did not return 403", pytrace=False)
    if response.headers.get("cache-control") != "no-store":
        pytest.fail("main.py: non-ASCII admin rejection is cacheable", pytrace=False)
