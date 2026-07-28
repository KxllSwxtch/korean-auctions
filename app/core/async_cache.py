"""
In-process TTL cache with single-flight coalescing and stale-while-revalidate.

Designed for read-heavy upstream scrapes where the data tolerates seconds of
staleness but users should never wait on a round trip to Korea.

Three properties, each of which matters on its own:

* **TTL** — a value is served verbatim until ``ttl`` seconds have passed.
* **Single flight** — N concurrent misses on one key produce exactly one
  upstream call. The in-flight ``asyncio.Task`` itself is what the waiters
  share, so there is no lock convoy and no thundering herd on cache expiry.
* **Stale-while-revalidate** — past ``ttl`` but within ``stale_ttl``, the cached
  value is returned immediately and a refresh runs in the background. Only a
  cold or fully-expired key makes a caller block.

Failures are never cached. If a refresh fails while a stale value is held, the
stale window is extended so the last-known-good value keeps serving instead of
the outage being handed straight to users.

Deployment note: ``start.sh`` runs gunicorn with ``--workers 2``, so this cache
is per worker — expect up to one upstream call per worker per TTL window rather
than exactly one process-wide. ``--max-requests 1000`` recycles workers and
discards the cache, which is precisely why the stale window matters: the
re-warm cost is paid by a background task, not by whoever arrives first.
``--preload`` means nothing here may be populated at import; warm from the
lifespan startup hook, which runs after the fork.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Awaitable, Callable, Generic, Hashable, TypeVar

from app.core.logging import get_logger

logger = get_logger("async_cache")

T = TypeVar("T")

#: A zero-argument coroutine function that produces the cached value.
#: It MUST raise on failure — returning a sentinel "error" object would pin that
#: error in the cache for the whole TTL.
Loader = Callable[[], Awaitable[T]]


@dataclass
class _Entry(Generic[T]):
    value: T
    fresh_until: float  # monotonic deadline: serve without refreshing
    stale_until: float  # monotonic deadline: serve, but refresh in background


class SwrCache(Generic[T]):
    """TTL + single-flight + stale-while-revalidate cache for coroutines.

    Args:
        ttl: Seconds a freshly loaded value is served without any refresh.
        stale_ttl: Extra seconds the value may be served while a background
            refresh runs. ``0`` disables stale serving (callers block on expiry).
        maxsize: Maximum distinct keys retained; least-recently-used are evicted.
        jitter: Upper bound of a random extra TTL, in seconds. Spreads the
            expiry of keys that were populated together so they do not all
            stampede at the same instant.
    """

    def __init__(
        self,
        *,
        ttl: float,
        stale_ttl: float = 0.0,
        maxsize: int = 256,
        jitter: float = 0.0,
        name: str = "cache",
    ) -> None:
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        if stale_ttl < 0:
            raise ValueError("stale_ttl must not be negative")
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        if jitter < 0:
            raise ValueError("jitter must not be negative")

        self._ttl = ttl
        self._stale_ttl = stale_ttl
        self._maxsize = maxsize
        self._jitter = jitter
        self._name = name

        self._entries: OrderedDict[Hashable, _Entry[T]] = OrderedDict()
        self._inflight: dict[Hashable, asyncio.Task[T]] = {}
        self._hits = 0
        self._misses = 0
        self._stale_hits = 0
        self._loads = 0

    async def get(self, key: Hashable, loader: Loader[T]) -> T:
        """Return the cached value for ``key``, loading it if necessary.

        Raises whatever ``loader`` raises, but only when there is no usable
        value to fall back on.
        """
        now = time.monotonic()
        entry = self._entries.get(key)

        if entry is not None and now < entry.fresh_until:
            self._entries.move_to_end(key)
            self._hits += 1
            return entry.value

        if entry is not None and now < entry.stale_until:
            # Answer instantly from the stale value; refresh behind the user.
            self._entries.move_to_end(key)
            self._stale_hits += 1
            self._spawn(key, loader)
            return entry.value

        # Cold or fully expired: block, but only one caller actually fetches.
        # shield() so that a browser disconnecting (Starlette cancels the
        # request handler) cannot cancel the shared fetch for everyone else.
        self._misses += 1
        return await asyncio.shield(self._spawn(key, loader))

    def invalidate(self, key: Hashable) -> None:
        """Drop a single key. In-flight loads are left to finish."""
        self._entries.pop(key, None)

    def clear(self) -> None:
        """Drop every cached value. In-flight loads are left to finish."""
        self._entries.clear()

    def stats(self) -> dict[str, int]:
        """Counters for diagnostics.

        ``misses`` counts *callers* that found no fresh value; ``loads`` counts
        actual loader invocations. The gap between them is what single-flight
        saved — 20 concurrent misses served by 1 load reads as
        ``misses=20, loads=1``.
        """
        return {
            "entries": len(self._entries),
            "inflight": len(self._inflight),
            "hits": self._hits,
            "stale_hits": self._stale_hits,
            "misses": self._misses,
            "loads": self._loads,
        }

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _spawn(self, key: Hashable, loader: Loader[T]) -> asyncio.Task[T]:
        """Return the in-flight task for ``key``, starting one if needed."""
        existing = self._inflight.get(key)
        if existing is not None:
            return existing  # the coalescing point: every waiter shares this

        task = asyncio.create_task(self._load(key, loader))
        # asyncio keeps only weak references to tasks, so this dict entry is
        # also what stops a background refresh from being garbage collected
        # mid-flight. It is removed in _load's finally.
        self._inflight[key] = task
        # Background refreshes have no awaiter; retrieve the exception so
        # asyncio does not emit "Task exception was never retrieved".
        task.add_done_callback(self._consume_exception)
        return task

    @staticmethod
    def _consume_exception(task: asyncio.Task[T]) -> None:
        if not task.cancelled():
            task.exception()

    async def _load(self, key: Hashable, loader: Loader[T]) -> T:
        self._loads += 1
        try:
            value = await loader()
        except Exception as exc:
            entry = self._entries.get(key)
            if entry is not None:
                # We still hold a usable value: keep serving it rather than
                # propagating the outage, and try again after the next window.
                entry.stale_until = time.monotonic() + self._stale_ttl
                logger.warning(
                    f"{self._name}: refresh failed for {key!r}, "
                    f"continuing to serve stale value: {exc}"
                )
            else:
                logger.warning(f"{self._name}: cold load failed for {key!r}: {exc}")
            raise
        else:
            ttl = self._ttl + (random.uniform(0, self._jitter) if self._jitter else 0.0)
            now = time.monotonic()
            self._entries[key] = _Entry(
                value=value,
                fresh_until=now + ttl,
                stale_until=now + ttl + self._stale_ttl,
            )
            self._entries.move_to_end(key)
            while len(self._entries) > self._maxsize:
                self._entries.popitem(last=False)  # evict least recently used
            return value
        finally:
            self._inflight.pop(key, None)
