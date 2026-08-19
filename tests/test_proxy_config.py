"""Security regression tests for source-managed proxy configuration."""

from __future__ import annotations

import ast
import json
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


# ---------------------------------------------------------------------------
# AUCTION_PROXY_POOL: additional entries stacked onto the legacy triple.
# ---------------------------------------------------------------------------

_AUCTION_VARIABLES = (
    "AUCTION_PROXY_HOST",
    "AUCTION_PROXY_USERNAME",
    "AUCTION_PROXY_PASSWORD",
    "AUCTION_PROXY_NAME",
    "AUCTION_PROXY_SUPPORTS_STICKY",
    "AUCTION_PROXY_POOL",
)


@pytest.fixture
def auction_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Start every case from an unconfigured pool, whatever the shell exports."""
    for name in _AUCTION_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _set_legacy_triple(
    env: pytest.MonkeyPatch,
    host: str = "proxy.legacy.test:8080",
    username: str = "operator",
    password: str = "secret",
) -> None:
    env.setenv("AUCTION_PROXY_HOST", host)
    env.setenv("AUCTION_PROXY_USERNAME", username)
    env.setenv("AUCTION_PROXY_PASSWORD", password)


def _set_pool(env: pytest.MonkeyPatch, *items: dict) -> None:
    env.setenv("AUCTION_PROXY_POOL", json.dumps(list(items)))


_SECOND = {
    "name": "second-provider",
    "host": "proxy.second.test:2312",
    "username": "second-user",
    "password": "second-pass",
}


def test_pool_json_entries_append_to_the_legacy_entry(
    auction_env: pytest.MonkeyPatch,
) -> None:
    _set_legacy_triple(auction_env)
    _set_pool(auction_env, _SECOND)

    pool = proxy_config.get_proxy_pool()

    assert len(pool) == 2
    assert pool.names == ["auction-proxy", "second-provider"]


def test_pool_round_robin_cycles_and_wraps(
    auction_env: pytest.MonkeyPatch,
) -> None:
    """The behaviour the whole feature exists for: traffic alternates."""
    _set_legacy_triple(auction_env)
    _set_pool(auction_env, _SECOND)

    pool = proxy_config.get_proxy_pool()

    assert pool.current()[0].name == "auction-proxy"
    assert [pool.advance()[0].name for _ in range(4)] == [
        "second-provider",
        "auction-proxy",
        "second-provider",
        "auction-proxy",
    ]


def test_each_entry_builds_a_url_from_its_own_credentials(
    auction_env: pytest.MonkeyPatch,
) -> None:
    _set_legacy_triple(auction_env)
    _set_pool(auction_env, _SECOND)

    pool = proxy_config.get_proxy_pool()

    assert pool.current()[1] == "http://operator:secret@proxy.legacy.test:8080"
    assert pool.advance()[1] == (
        "http://second-user:second-pass@proxy.second.test:2312"
    )


def test_pool_entry_name_defaults_to_a_distinguishable_label(
    auction_env: pytest.MonkeyPatch,
) -> None:
    """pool.names is logged at startup, so entries must stay tellable apart."""
    _set_legacy_triple(auction_env)
    _set_pool(
        auction_env,
        {"host": "a.test:1", "username": "u1", "password": "p1"},
        {"host": "b.test:2", "username": "u2", "password": "p2"},
    )

    assert proxy_config.get_proxy_pool().names == [
        "auction-proxy",
        "auction-proxy-2",
        "auction-proxy-3",
    ]


def test_pool_only_configuration_builds_a_working_pool(
    auction_env: pytest.MonkeyPatch,
) -> None:
    _set_pool(auction_env, _SECOND)

    pool = proxy_config.get_proxy_pool()

    assert pool.names == ["second-provider"]
    assert pool.current()[1].endswith("@proxy.second.test:2312")


def test_sticky_pool_entry_substitutes_the_session_placeholder(
    auction_env: pytest.MonkeyPatch,
) -> None:
    _set_pool(
        auction_env,
        {
            "name": "sticky",
            "host": "proxy.sticky.test:9000",
            "username": "user_session-{session}",
            "password": "pw",
            "supports_sticky": True,
        },
    )

    _, url = proxy_config.get_proxy_pool().current()

    assert "user_session-" in url
    assert "{session}" not in url


@pytest.mark.parametrize(
    "raw",
    [
        "not json at all",
        '{"host": "a.test:1"}',
        "[[]]",
        '["http://user:pass@host:1"]',
    ],
    ids=["invalid-json", "object-not-array", "element-not-object", "bare-string"],
)
def test_malformed_pool_json_raises(
    auction_env: pytest.MonkeyPatch, raw: str
) -> None:
    _set_legacy_triple(auction_env)
    auction_env.setenv("AUCTION_PROXY_POOL", raw)

    with pytest.raises(proxy_config.ProxyConfigurationError):
        proxy_config.get_proxy_pool()


@pytest.mark.parametrize(
    "item",
    [
        {"username": "u", "password": "p"},
        {"host": "a.test:1", "password": "p"},
        {"host": "a.test:1", "username": "u"},
        {"host": "  ", "username": "u", "password": "p"},
    ],
    ids=["no-host", "no-username", "no-password", "blank-host"],
)
def test_incomplete_pool_entry_raises(
    auction_env: pytest.MonkeyPatch, item: dict
) -> None:
    _set_pool(auction_env, item)

    with pytest.raises(proxy_config.ProxyConfigurationError):
        proxy_config.get_proxy_pool()


@pytest.mark.parametrize(
    "host",
    [
        "http://proxy.test:2312",
        "user:pass@proxy.test:2312",
        "proxy.test:2312/path",
        "proxy.test:2312?q=1",
        "proxy.test:2312#frag",
    ],
)
def test_pool_host_rejects_url_shaped_values(
    auction_env: pytest.MonkeyPatch, host: str
) -> None:
    """build_url() interpolates host verbatim; a full URL would corrupt it."""
    _set_pool(auction_env, {"host": host, "username": "u", "password": "p"})

    with pytest.raises(proxy_config.ProxyConfigurationError):
        proxy_config.get_proxy_pool()


@pytest.mark.parametrize(
    "present",
    ["AUCTION_PROXY_HOST", "AUCTION_PROXY_USERNAME", "AUCTION_PROXY_PASSWORD"],
)
def test_partial_legacy_triple_raises_even_when_the_pool_is_valid(
    auction_env: pytest.MonkeyPatch, present: str
) -> None:
    """A typo in one name must not silently shrink the pool to the JSON only."""
    auction_env.setenv(present, "value")
    _set_pool(auction_env, _SECOND)

    with pytest.raises(proxy_config.ProxyConfigurationError):
        proxy_config.get_proxy_pool()


def test_duplicate_entry_across_the_two_sources_raises(
    auction_env: pytest.MonkeyPatch,
) -> None:
    """A doubled proxy would take twice its share of traffic, silently."""
    _set_legacy_triple(auction_env, host="dup.test:1", username="u", password="p")
    _set_pool(auction_env, {"host": "dup.test:1", "username": "u", "password": "p"})

    with pytest.raises(proxy_config.ProxyConfigurationError):
        proxy_config.get_proxy_pool()


def test_duplicate_entry_within_the_pool_json_raises(
    auction_env: pytest.MonkeyPatch,
) -> None:
    _set_pool(
        auction_env,
        {"name": "a", "host": "dup.test:1", "username": "u", "password": "p"},
        {"name": "b", "host": "dup.test:1", "username": "u", "password": "p"},
    )

    with pytest.raises(proxy_config.ProxyConfigurationError):
        proxy_config.get_proxy_pool()


def test_blank_pool_variable_leaves_the_legacy_entry_alone(
    auction_env: pytest.MonkeyPatch,
) -> None:
    """Deployments that never set the new variable must be unaffected."""
    _set_legacy_triple(auction_env)
    auction_env.setenv("AUCTION_PROXY_POOL", "   ")

    assert proxy_config.get_proxy_pool().names == ["auction-proxy"]
