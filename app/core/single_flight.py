"""
SingleFlight — coalesces concurrent identical async requests into a single
execution, sharing the result (or exception) with all waiters.

Prevents the "thundering herd" problem where many concurrent requests for the
same expired cache key all trigger independent upstream fetches.

Usage:
    flight = SingleFlight()

    async def handle(key, fetch_fn):
        return await flight.do(key, fetch_fn)
"""

import asyncio
from typing import Any, Awaitable, Callable, Dict
from loguru import logger


class SingleFlight:
    """Coalesces concurrent identical async requests into a single execution."""

    def __init__(self) -> None:
        self._in_flight: Dict[str, asyncio.Future] = {}

    async def do(self, key: str, fn: Callable[[], Awaitable[Any]]) -> Any:
        """
        Execute *fn* once for the given *key*. If another coroutine has
        already started a call for the same key, piggy-back on its result
        instead of making a duplicate call.

        Exceptions from *fn* propagate to all waiters.
        """
        existing = self._in_flight.get(key)
        if existing is not None:
            logger.debug("SingleFlight: piggybacking on in-flight request for {}", key)
            return await existing

        # Store a Future immediately (synchronously, before any await) so that
        # all subsequent callers for the same key see it and piggyback.
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._in_flight[key] = future

        try:
            result = await fn()
            future.set_result(result)
            return result
        except Exception as e:
            future.set_exception(e)
            raise
        finally:
            self._in_flight.pop(key, None)

    @property
    def in_flight_count(self) -> int:
        """Number of currently in-flight requests (useful for monitoring)."""
        return len(self._in_flight)
