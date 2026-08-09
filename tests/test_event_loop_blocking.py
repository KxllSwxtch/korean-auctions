"""Guards against blocking the event loop and against serial upstream fetches.

Every route in this codebase is declared `async def`, but much of the client
code is synchronous `requests`. Calling it directly from a route stalls the
whole worker: uvicorn's heartbeat is a coroutine on the same loop, so a blocked
loop stops the heartbeat and gunicorn SIGKILLs the worker at `--timeout 120`,
taking every other in-flight request with it.

Two measured cases motivated these tests:
  * GET /api/v1/lotte/cars?limit=20  -> 20.6 s (sequential detail fetches)
  * GET /api/v1/heydealer/cars       -> 15.8 s (sequential generation fetches)
"""

from __future__ import annotations

import ast
import asyncio
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _blocking_calls_in_async_defs(module_path: str, func_names: set[str]):
    """Return (async_fn, lineno) for each `func_names` call made without await.

    A call is considered safe when it is lexically inside a plain `def` (those
    are the bodies handed to `asyncio.to_thread`), so only calls sitting
    directly in async code are reported.
    """
    src = (ROOT / module_path).read_text(encoding="utf-8")
    tree = ast.parse(src)
    offenders: list[tuple[str, int]] = []

    def walk(node, async_fn: str | None):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.AsyncFunctionDef):
                walk(child, child.name)
                continue
            if isinstance(child, ast.FunctionDef):
                # Sync nested helper: its body is what gets sent to a thread.
                walk(child, None)
                continue
            if isinstance(child, ast.Lambda):
                walk(child, None)
                continue
            if (
                async_fn
                and isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id in func_names
            ):
                offenders.append((async_fn, child.lineno))
            walk(child, async_fn)

    walk(tree, None)
    return offenders


@pytest.mark.parametrize(
    "module_path",
    ["app/routes/heydealer.py", "app/routes/heydealer_filters.py"],
)
def test_heydealer_routes_never_call_blocking_hd_get(module_path: str) -> None:
    """`_hd_get` is synchronous; async routes must use `_hd_get_async`."""
    offenders = _blocking_calls_in_async_defs(module_path, {"_hd_get"})
    assert not offenders, (
        f"{module_path}: blocking _hd_get called directly from async code at "
        f"{offenders}. Use `await _hd_get_async(...)`, which wraps it in a thread."
    )


def test_lotte_detail_fetch_is_not_sequential() -> None:
    """The per-car loop must go through the bounded-parallel gatherer."""
    src = (ROOT / "app/services/lotte_service.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        if node.name in {"_gather_car_details", "_get_car_details"}:
            continue
        body = ast.get_source_segment(src, node) or ""
        # An awaited detail fetch inside a for-loop is the serial pattern.
        if "for car_data in" in body and "await self._get_car_details(" in body:
            pytest.fail(
                f"lotte_service.{node.name} fetches car details sequentially. "
                "Use _gather_car_details, which bounds concurrency at "
                "_DETAIL_CONCURRENCY."
            )


def test_lotte_detail_loop_has_no_per_item_sleep() -> None:
    """The old loop slept 0.5s per car — 10s of pure delay at limit=20."""
    src = (ROOT / "app/services/lotte_service.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_gather_car_details":
            body = ast.get_source_segment(src, node) or ""
            assert "asyncio.sleep" not in body


def test_generation_fetches_run_concurrently() -> None:
    """`_fetch_cars_for_generations` must overlap its upstream calls.

    Ten simulated 100 ms fetches take ~1 s serially and ~0.2 s at concurrency 5.
    The 0.6 s ceiling fails the serial implementation without being tight enough
    to flake on a loaded machine.
    """
    from app.routes import heydealer

    calls: list[str] = []

    class FakeResponse:
        status_code = 200

        def __init__(self, gen_id: str):
            self._gen_id = gen_id

        def json(self):
            return [{"id": f"{self._gen_id}-car"}]

    async def fake_hd_get_async(url, **kwargs):
        calls.append(kwargs["params"]["model"])
        await asyncio.sleep(0.1)
        return FakeResponse(kwargs["params"]["model"])

    original = heydealer._hd_get_async
    heydealer._hd_get_async = fake_hd_get_async
    try:
        generations = [f"gen{i}" for i in range(10)]
        started = time.perf_counter()
        cars, failed = asyncio.run(
            heydealer._fetch_cars_for_generations(generations, {}, {}, {})
        )
        elapsed = time.perf_counter() - started
    finally:
        heydealer._hd_get_async = original

    assert len(cars) == 10, "every generation's cars should be collected"
    assert not failed
    assert sorted(calls) == sorted(generations)
    assert elapsed < 0.6, (
        f"generation fetches took {elapsed:.2f}s; serial execution would be ~1.0s. "
        "They must run concurrently."
    )


def test_generation_failures_are_reported_not_swallowed() -> None:
    """A non-200 generation used to be dropped silently, so a partial result
    was indistinguishable from a complete one."""
    from app.routes import heydealer

    class FakeResponse:
        def __init__(self, status_code: int, gen_id: str):
            self.status_code = status_code
            self._gen_id = gen_id

        def json(self):
            return [{"id": f"{self._gen_id}-car"}]

    async def fake_hd_get_async(url, **kwargs):
        gen_id = kwargs["params"]["model"]
        # gen1 fails upstream.
        return FakeResponse(500 if gen_id == "gen1" else 200, gen_id)

    original = heydealer._hd_get_async
    heydealer._hd_get_async = fake_hd_get_async
    try:
        cars, failed = asyncio.run(
            heydealer._fetch_cars_for_generations(
                ["gen0", "gen1", "gen2"], {}, {}, {}
            )
        )
    finally:
        heydealer._hd_get_async = original

    assert len(cars) == 2
    assert failed == ["gen1"]


def test_generation_concurrency_is_bounded() -> None:
    """Unbounded fan-out would burst N simultaneous requests at HeyDealer,
    which is exactly what gets a shared dealer account throttled."""
    from app.routes import heydealer

    in_flight = 0
    peak = 0

    class FakeResponse:
        status_code = 200

        def json(self):
            return []

    async def fake_hd_get_async(url, **kwargs):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1
        return FakeResponse()

    original = heydealer._hd_get_async
    heydealer._hd_get_async = fake_hd_get_async
    try:
        asyncio.run(
            heydealer._fetch_cars_for_generations(
                [f"gen{i}" for i in range(30)], {}, {}, {}
            )
        )
    finally:
        heydealer._hd_get_async = original

    assert peak <= heydealer._GENERATION_CONCURRENCY, (
        f"peaked at {peak} concurrent upstream requests, "
        f"limit is {heydealer._GENERATION_CONCURRENCY}"
    )
