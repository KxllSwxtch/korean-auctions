"""Behavioural tests for SwrCache.

The interesting properties here are concurrency properties, so every test
counts actual loader invocations rather than inspecting internal state.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.async_cache import SwrCache


class _CountingLoader:
    """Loader that records calls and can be made to fail or stall."""

    def __init__(self, value: str = "v1", delay: float = 0.0) -> None:
        self.value = value
        self.delay = delay
        self.calls = 0
        self.fail_with: Exception | None = None
        self.started = asyncio.Event()

    async def __call__(self) -> str:
        self.calls += 1
        self.started.set()
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail_with is not None:
            raise self.fail_with
        return self.value


def test_value_is_cached_within_ttl() -> None:
    async def scenario() -> None:
        cache = SwrCache[str](ttl=60)
        loader = _CountingLoader()

        assert await cache.get("k", loader) == "v1"
        assert await cache.get("k", loader) == "v1"
        assert await cache.get("k", loader) == "v1"
        assert loader.calls == 1

    asyncio.run(scenario())


def test_distinct_keys_do_not_share_values() -> None:
    async def scenario() -> None:
        cache = SwrCache[str](ttl=60)
        a, b = _CountingLoader("a"), _CountingLoader("b")

        assert await cache.get("a", a) == "a"
        assert await cache.get("b", b) == "b"
        assert a.calls == 1 and b.calls == 1

    asyncio.run(scenario())


def test_concurrent_misses_trigger_exactly_one_load() -> None:
    """Single flight: this is what stops a cache miss becoming a stampede."""

    async def scenario() -> None:
        cache = SwrCache[str](ttl=60)
        loader = _CountingLoader(delay=0.05)

        results = await asyncio.gather(*(cache.get("k", loader) for _ in range(25)))

        assert results == ["v1"] * 25
        assert loader.calls == 1, f"expected 1 upstream call, got {loader.calls}"

        # The stats must make the saving visible: 25 callers missed, 1 loaded.
        stats = cache.stats()
        assert stats["misses"] == 25
        assert stats["loads"] == 1

    asyncio.run(scenario())


def test_value_reloads_after_ttl_expires() -> None:
    async def scenario() -> None:
        cache = SwrCache[str](ttl=0.05)
        loader = _CountingLoader()

        assert await cache.get("k", loader) == "v1"
        await asyncio.sleep(0.08)
        loader.value = "v2"
        assert await cache.get("k", loader) == "v2"
        assert loader.calls == 2

    asyncio.run(scenario())


def test_stale_value_is_served_immediately_while_refreshing() -> None:
    """Past the TTL but inside the stale window, callers must not block."""

    async def scenario() -> None:
        cache = SwrCache[str](ttl=0.05, stale_ttl=60)
        loader = _CountingLoader()

        assert await cache.get("k", loader) == "v1"
        await asyncio.sleep(0.08)

        loader.value = "v2"
        loader.delay = 0.2  # a refresh far slower than any acceptable wait

        started = asyncio.get_running_loop().time()
        stale = await cache.get("k", loader)
        elapsed = asyncio.get_running_loop().time() - started

        assert stale == "v1", "stale value should be returned during refresh"
        assert elapsed < 0.05, f"stale read blocked for {elapsed:.3f}s"

        await asyncio.sleep(0.3)  # let the background refresh land
        assert await cache.get("k", loader) == "v2"
        assert loader.calls == 2

    asyncio.run(scenario())


def test_failures_are_never_cached() -> None:
    async def scenario() -> None:
        cache = SwrCache[str](ttl=60)
        loader = _CountingLoader()
        loader.fail_with = RuntimeError("upstream down")

        with pytest.raises(RuntimeError):
            await cache.get("k", loader)

        # A second attempt must retry rather than replay the cached failure.
        loader.fail_with = None
        assert await cache.get("k", loader) == "v1"
        assert loader.calls == 2

    asyncio.run(scenario())


def test_failed_refresh_keeps_serving_last_known_good() -> None:
    async def scenario() -> None:
        cache = SwrCache[str](ttl=0.05, stale_ttl=0.5)
        loader = _CountingLoader()

        assert await cache.get("k", loader) == "v1"
        await asyncio.sleep(0.08)

        loader.fail_with = RuntimeError("upstream down")
        assert await cache.get("k", loader) == "v1"  # stale served, refresh spawned
        await asyncio.sleep(0.05)

        # Refresh failed, but the stale window was extended rather than the
        # entry being dropped, so users still see the last good value.
        assert await cache.get("k", loader) == "v1"

    asyncio.run(scenario())


def test_caller_cancellation_does_not_kill_the_shared_load() -> None:
    """A disconnecting browser must not cancel everyone else's fetch."""

    async def scenario() -> None:
        cache = SwrCache[str](ttl=60)
        loader = _CountingLoader(delay=0.15)

        first = asyncio.create_task(cache.get("k", loader))
        second = asyncio.create_task(cache.get("k", loader))
        await loader.started.wait()

        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first

        assert await second == "v1"
        assert loader.calls == 1

    asyncio.run(scenario())


def test_lru_eviction_respects_maxsize() -> None:
    async def scenario() -> None:
        cache = SwrCache[str](ttl=60, maxsize=2)

        await cache.get("a", _CountingLoader("a"))
        await cache.get("b", _CountingLoader("b"))
        await cache.get("a", _CountingLoader("a"))  # refresh recency of "a"
        await cache.get("c", _CountingLoader("c"))  # should evict "b"

        assert cache.stats()["entries"] == 2

        reload_b = _CountingLoader("b")
        await cache.get("b", reload_b)
        assert reload_b.calls == 1, "b should have been evicted and reloaded"

    asyncio.run(scenario())


def test_invalidate_forces_a_reload() -> None:
    async def scenario() -> None:
        cache = SwrCache[str](ttl=60)
        loader = _CountingLoader()

        await cache.get("k", loader)
        cache.invalidate("k")
        await cache.get("k", loader)
        assert loader.calls == 2

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ttl": 0},
        {"ttl": -1},
        {"ttl": 10, "stale_ttl": -1},
        {"ttl": 10, "maxsize": 0},
        {"ttl": 10, "jitter": -1},
    ],
)
def test_invalid_configuration_is_rejected(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        SwrCache(**kwargs)
