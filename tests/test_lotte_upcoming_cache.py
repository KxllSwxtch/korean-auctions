"""/cars/upcoming must read a cache, and must not cache a failed page.

`get_cars` (behind /api/v1/lotte/cars/upcoming, the endpoint the frontend
calls) read no cache at all, while the scheduler warmed `lotte_cars_20_0` every
8 minutes — a key only /api/v1/lotte/cars reads. The warmer was doing real work
for an endpoint nobody hits from the site.

The two caches stay separate on purpose: get_cars_with_date_check stores cars
WITH details gathered per car, get_cars stores just the parsed list rows. One
key for both would hand a caller the wrong shape.

Async tests use asyncio.run(scenario()) to match tests/test_async_cache.py.
"""

from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest

from app.core.auth_errors import AuthUnavailableError
from app.services.lotte_service import LotteService


class _Response:
    text = "<html>irrelevant, _parse_cars is stubbed</html>"


def _service() -> LotteService:
    svc = object.__new__(LotteService)
    svc.session = None
    svc.authenticated = True
    svc.cache = {}
    svc._ensure_session = Mock(return_value=True)
    return svc


def _with_cars(svc: LotteService, cars: list) -> None:
    async def _fetch(limit, offset):
        return _Response()

    svc._fetch_cars_page = _fetch
    svc._parse_cars = Mock(return_value=cars)


def test_second_call_is_served_from_cache() -> None:
    service = _service()
    _with_cars(service, [{"id": "a"}, {"id": "b"}])

    async def scenario() -> None:
        first = await service.get_cars(limit=20, offset=0)
        second = await service.get_cars(limit=20, offset=0)
        assert first == second
        # Parsed once; the second call never reached the parser.
        assert service._parse_cars.call_count == 1

    asyncio.run(scenario())


def test_cache_key_varies_by_pagination() -> None:
    service = _service()
    _with_cars(service, [{"id": "a"}])

    async def scenario() -> None:
        await service.get_cars(limit=20, offset=0)
        await service.get_cars(limit=20, offset=20)
        assert service._parse_cars.call_count == 2, "offset must not share a key"

    asyncio.run(scenario())


def test_does_not_collide_with_the_detailed_cache() -> None:
    """get_cars_with_date_check uses lotte_cars_*; get_cars must not reuse it."""
    service = _service()
    _with_cars(service, [{"id": "a"}])

    async def scenario() -> None:
        await service.get_cars(limit=20, offset=0)
        assert "lotte_upcoming_20_0" in service.cache
        assert "lotte_cars_20_0" not in service.cache

    asyncio.run(scenario())


def test_empty_result_is_not_cached() -> None:
    """A parse failure must not pin "auction is empty" for the whole TTL."""
    service = _service()
    _with_cars(service, [])

    async def scenario() -> None:
        await service.get_cars(limit=20, offset=0)
        assert service.cache == {}

    asyncio.run(scenario())


def test_auth_failure_is_not_cached() -> None:
    service = _service()
    _with_cars(service, [{"id": "a"}])
    service._ensure_session = Mock(return_value=False)

    async def scenario() -> None:
        with pytest.raises(AuthUnavailableError):
            await service.get_cars(limit=20, offset=0)
        assert service.cache == {}

    asyncio.run(scenario())


def test_cached_result_does_not_reauthenticate() -> None:
    """The point of the warm cache: a cache hit costs no upstream round-trip."""
    service = _service()
    _with_cars(service, [{"id": "a"}])

    async def scenario() -> None:
        await service.get_cars(limit=20, offset=0)
        calls_after_first = service._ensure_session.call_count
        await service.get_cars(limit=20, offset=0)
        assert service._ensure_session.call_count == calls_after_first

    asyncio.run(scenario())
