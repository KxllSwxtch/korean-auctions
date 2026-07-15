"""Security regression tests for source-managed proxy configuration."""

from __future__ import annotations

import ast
from pathlib import Path
import re

import pytest

from app.core import proxy_config


ROOT = Path(__file__).resolve().parents[1]
PROXY_CONFIG = ROOT / "app/core/proxy_config.py"
_CREDENTIAL_URL = re.compile(r"https?://[^\s/:@]+:[^\s/@]+@", re.IGNORECASE)


def test_proxy_config_source_contains_no_literal_proxy_credentials() -> None:
    source = PROXY_CONFIG.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_keywords = {"host", "username", "username_template", "password"}
    literal_defaults: list[tuple[str, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg in forbidden_keywords:
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                if node.value.value.strip():
                    literal_defaults.append((node.arg, node.lineno))
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert not _CREDENTIAL_URL.search(node.value), (
                f"credential-bearing proxy URL literal at line {node.lineno}"
            )

    assert literal_defaults == []
    assert "os.getenv" in source


def test_generic_proxy_pool_requires_environment_managed_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "AUCTION_PROXY_HOST",
        "AUCTION_PROXY_USERNAME",
        "AUCTION_PROXY_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(proxy_config.ProxyConfigurationError):
        proxy_config.get_proxy_pool()
