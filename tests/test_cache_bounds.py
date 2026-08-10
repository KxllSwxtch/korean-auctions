"""Guards on the Autohub in-process cache.

`_cache` only evicted a key when that same key was read back after expiry, so
anything fetched once and never again stayed for the life of the worker. Keys
are md5(filter params), so the key space grew with every distinct filter
combination a user tried.

The acute case was `get_image`, which stored raw JPEG bytes there with a 24h
TTL: paging through galleries at ~200KB an image leaked roughly 200MB per
thousand images, per worker. On Render's 512MB starter plan that is an OOM
restart loop. Image bytes are no longer cached at all — the route serves them
with an immutable Cache-Control and lets the CDN and browser absorb repeats.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.services.autohub_service import AutohubService

ROOT = Path(__file__).resolve().parents[1]
SERVICE_SRC = ROOT / "app/services/autohub_service.py"


def _get_function(name: str) -> ast.FunctionDef:
    tree = ast.parse(SERVICE_SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in autohub_service.py")


def test_get_image_does_not_populate_the_in_process_cache() -> None:
    """Raw image bytes must never go back into `_cache`."""
    fn = _get_function("get_image")
    calls = [
        n.func.attr
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    ]
    assert "_save_to_cache" not in calls, (
        "get_image writes image bytes into the unbounded _cache again — that is "
        "the ~200MB-per-1000-images leak. Caching belongs in the route's "
        "Cache-Control header."
    )
    assert "_get_from_cache" not in calls, (
        "get_image reads from _cache again; if nothing writes to it this is dead "
        "code, and if something does it reintroduces the leak."
    )


def test_image_route_sets_an_immutable_cache_header() -> None:
    """Removing the byte cache is only safe because HTTP caching replaces it."""
    route_src = (ROOT / "app/routes/autohub.py").read_text(encoding="utf-8")
    assert "max-age=31536000" in route_src and "immutable" in route_src, (
        "the image route must cache hard at the CDN/browser — that is what "
        "replaced the in-process byte cache"
    )


def test_cache_is_bounded() -> None:
    """Inserting well past the cap must not grow the dict without limit."""
    service = AutohubService.__new__(AutohubService)  # skip __init__/network
    service._cache = {}
    service._cache_hits = 0
    service._cache_misses = 0

    limit = AutohubService._CACHE_MAX_ENTRIES
    for i in range(limit * 3):
        service._save_to_cache(f"key-{i}", {"payload": i})

    assert len(service._cache) <= limit, (
        f"cache grew to {len(service._cache)} entries, cap is {limit}"
    )


def test_eviction_drops_the_oldest_entries_first() -> None:
    service = AutohubService.__new__(AutohubService)
    service._cache = {}
    service._cache_hits = 0
    service._cache_misses = 0

    limit = AutohubService._CACHE_MAX_ENTRIES
    for i in range(limit):
        service._save_to_cache(f"key-{i}", i)

    # One more insert triggers a batch eviction of the oldest entries.
    service._save_to_cache("newest", "value")

    assert "newest" in service._cache
    assert "key-0" not in service._cache, "the oldest entry should be evicted first"
    # The most recent pre-eviction keys should survive.
    assert f"key-{limit - 1}" in service._cache


def test_updating_an_existing_key_does_not_trigger_eviction() -> None:
    """Refreshing a hot key at the cap must not evict anything."""
    service = AutohubService.__new__(AutohubService)
    service._cache = {}
    service._cache_hits = 0
    service._cache_misses = 0

    limit = AutohubService._CACHE_MAX_ENTRIES
    for i in range(limit):
        service._save_to_cache(f"key-{i}", i)
    before = set(service._cache)

    service._save_to_cache("key-0", "refreshed")

    assert set(service._cache) == before
    assert service._cache["key-0"][0] == "refreshed"


@pytest.mark.parametrize("attr", ["_CACHE_MAX_ENTRIES"])
def test_cap_is_declared_on_the_class(attr: str) -> None:
    assert isinstance(getattr(AutohubService, attr), int)
    assert getattr(AutohubService, attr) > 0
