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
    [
        "app/routes/heydealer_dbauto.py",
        "app/services/heydealer_dbauto_service.py",
    ],
)
def test_heydealer_never_calls_the_blocking_transport_from_async_code(
    module_path: str,
) -> None:
    """`DbautoTransport.get_json` is synchronous `requests`.

    It must only ever be reached through `asyncio.to_thread`. Called straight
    from a coroutine it blocks the loop for the whole round trip to Korea — the
    same failure the deleted `_hd_get` guard covered, on the module that replaced
    it.
    """
    offenders = _blocking_calls_in_async_defs(module_path, {"get_json"})
    assert not offenders, (
        f"{module_path}: blocking get_json called directly from async code at "
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
