"""
Tuesday-night Autohub catalogue snapshot job.

Walks the entire Autohub auction catalogue once a week (Tuesday 22:00 KST),
persisting it to the SQLite snapshot DB so Wednesday traffic can be served
without touching api.ahsellcar.co.kr. See plans/wednesday-snapshot-mode.md.

Pacing is deliberately gentler than the user-facing path:
- listings: sequential paginated fetches with a short sleep between pages
- per-car detail bundles: concurrency capped at 3 via a job-only semaphore
  (combines with the user-path's _OUTBOUND_LIMIT=5 to floor at 3)
- per-car ThreadPoolExecutor inside the AutohubService.fetch_car_detail_raw
  is already capped at 2 — net peak is ~6 in-flight requests at any moment.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from filelock import FileLock, Timeout

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.autohub_filters import AutohubSearchRequest, AutohubSortOrder
from app.services.autohub_service import autohub_service
from app.storage.autohub_snapshot_repo import SnapshotRepo

logger = get_logger("autohub_snapshot_job")

# Per-job concurrency cap on detail-bundle fetches. The user path uses
# _OUTBOUND_LIMIT=5; this semaphore is independent and lower because the job
# runs unattended at off-peak hours and must be polite.
_JOB_DETAIL_CONCURRENCY = 3
_PAGE_SIZE = 100
_INTER_PAGE_SLEEP_SECS = 0.25
_INTER_BATCH_SLEEP_SECS = 0.5
_DETAIL_BATCH_SIZE = 50

# Filesystem lock to prevent two concurrent runs (e.g. cron + admin trigger).
_RUN_LOCK_PATH_DEFAULT = "/data/autohub_snapshot.run.lock"


def _run_lock_path() -> str:
    """Place the run lock next to the DB so it lives on the same disk."""
    settings = get_settings()
    db_dir = Path(settings.autohub_snapshot_db_path).parent
    return str(db_dir / "autohub_snapshot.run.lock")


# ---------------------------------------------------------------------------
# Singleton repo (one per process; reuses the same SQLite DB file)
# ---------------------------------------------------------------------------

_repo_singleton: Optional[SnapshotRepo] = None
_repo_lock = asyncio.Lock()


async def get_repo() -> SnapshotRepo:
    """Lazy-construct the repo on first use."""
    global _repo_singleton
    async with _repo_lock:
        if _repo_singleton is None:
            settings = get_settings()
            _repo_singleton = SnapshotRepo(settings.autohub_snapshot_db_path)
    return _repo_singleton


# ---------------------------------------------------------------------------
# The job
# ---------------------------------------------------------------------------

async def run_snapshot_job(triggered_by: str = "cron") -> dict:
    """Run a full snapshot. Returns a summary dict on success.

    Acquires an exclusive filelock to prevent overlapping runs (cron + admin
    trigger, or an admin trigger fired twice). If another run holds the lock,
    raises RuntimeError immediately — does not queue.

    Stages:
        1. Begin a fresh `snapshot_id` row (status=in_progress)
        2. Authenticate (existing service handles this on first call)
        3. Paginate listings page=1..N with `_INTER_PAGE_SLEEP_SECS` between
        4. Fetch brands tree (single call)
        5. Per-car detail bundles, batched/`_DETAIL_BATCH_SIZE` cars at a time,
           concurrency capped at `_JOB_DETAIL_CONCURRENCY` per batch, sleeping
           between batches
        6. Atomically activate the new snapshot
        7. Mark complete with car/detail counts
        8. Vacuum old snapshots, keeping the configured retention
    """
    settings = get_settings()
    started_wall = time.monotonic()
    logger.info(f"Snapshot job starting (triggered_by={triggered_by})")

    lock_path = _run_lock_path()
    Path(lock_path).parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(lock_path, timeout=0)
    try:
        lock.acquire()
    except Timeout:
        msg = f"Another snapshot run is already in progress (lock at {lock_path})"
        logger.warning(msg)
        raise RuntimeError(msg)

    repo = await get_repo()
    snap_id = repo.begin_snapshot()
    cars_buffered: list[dict] = []
    detail_count = 0
    error: Optional[str] = None

    try:
        # ---- Stage 1: paginate listings -----------------------------------
        page = 1
        while True:
            params = AutohubSearchRequest(
                page=page,
                page_size=_PAGE_SIZE,
                sort_order=AutohubSortOrder.ENTRY,
                sort_direction="asc",
            )
            try:
                raw = await asyncio.to_thread(
                    autohub_service.fetch_listing_page_raw, params
                )
            except Exception as e:
                logger.error(f"Snapshot: listings page {page} failed: {e}")
                # Surface as job failure — incomplete listings is unacceptable
                raise

            entries = (raw.get("data") or {}).get("list") or []
            total_pages = (raw.get("data") or {}).get("totalPages") or 0

            if not entries:
                logger.info(f"Snapshot: page {page} returned no entries — stopping")
                break

            written = repo.write_cars(snap_id, entries)
            cars_buffered.extend(entries)
            logger.info(
                f"Snapshot: page {page}/{total_pages or '?'} → wrote {written} cars "
                f"(total so far: {len(cars_buffered)})"
            )

            if total_pages and page >= total_pages:
                break
            page += 1
            await asyncio.sleep(_INTER_PAGE_SLEEP_SECS)

        car_count = len(cars_buffered)
        logger.info(f"Snapshot: listings complete, {car_count} cars across {page} pages")

        # ---- Stage 2: brands tree -----------------------------------------
        try:
            brands_raw = await asyncio.to_thread(autohub_service.fetch_brands_raw)
            repo.write_brands(snap_id, brands_raw)
            logger.info("Snapshot: brands tree written")
        except Exception as e:
            # Brands failure is recoverable — the read-path can fall through to
            # an empty filter dropdown. Log and continue.
            logger.warning(f"Snapshot: brands fetch failed (continuing): {e}")

        # ---- Stage 3: per-car detail bundles ------------------------------
        sem = asyncio.Semaphore(_JOB_DETAIL_CONCURRENCY)

        async def _fetch_one(entry: dict) -> bool:
            car_id = entry.get("carId")
            perf_id = entry.get("perfId")
            if not car_id:
                return False
            async with sem:
                try:
                    bundle = await asyncio.to_thread(
                        autohub_service.fetch_car_detail_raw, car_id, perf_id
                    )
                except Exception as e:
                    logger.warning(
                        f"Snapshot: detail bundle failed for {car_id}: {e}"
                    )
                    return False
            try:
                await asyncio.to_thread(
                    repo.write_car_detail,
                    snap_id, car_id,
                    bundle.get("detail"),
                    bundle.get("inspection"),
                    bundle.get("diagram"),
                    bundle.get("legend"),
                    bundle.get("perf_frame"),
                )
                return True
            except Exception as e:
                logger.warning(f"Snapshot: detail write failed for {car_id}: {e}")
                return False

        for batch_start in range(0, car_count, _DETAIL_BATCH_SIZE):
            batch = cars_buffered[batch_start : batch_start + _DETAIL_BATCH_SIZE]
            results = await asyncio.gather(
                *(_fetch_one(c) for c in batch), return_exceptions=False
            )
            wrote_in_batch = sum(1 for r in results if r)
            detail_count += wrote_in_batch
            logger.info(
                f"Snapshot: details {batch_start + len(batch)}/{car_count} "
                f"(batch wrote {wrote_in_batch}/{len(batch)}, "
                f"running total {detail_count})"
            )
            await asyncio.sleep(_INTER_BATCH_SLEEP_SECS)

        # ---- Stage 4: atomic activation -----------------------------------
        repo.activate_snapshot(snap_id)
        repo.complete_snapshot(snap_id, car_count=car_count, detail_count=detail_count)
        elapsed = int(time.monotonic() - started_wall)
        logger.info(
            f"Snapshot {snap_id} READY: {car_count} cars, {detail_count} details "
            f"in {elapsed}s"
        )

        # ---- Stage 5: vacuum old snapshots --------------------------------
        try:
            deleted = repo.vacuum_keeping_last(settings.autohub_snapshot_retention)
            if deleted:
                logger.info(f"Snapshot: vacuum dropped {deleted} stale rows")
        except Exception as e:
            logger.warning(f"Snapshot: vacuum failed (non-fatal): {e}")

        return {
            "snapshot_id": snap_id,
            "car_count": car_count,
            "detail_count": detail_count,
            "elapsed_secs": elapsed,
            "triggered_by": triggered_by,
        }

    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        logger.exception(f"Snapshot {snap_id} failed: {error}")
        try:
            repo.fail_snapshot(snap_id, error)
        except Exception as fail_err:
            logger.error(f"Failed to mark snapshot failed: {fail_err}")
        await _alert_failure(snap_id, error)
        raise
    finally:
        try:
            lock.release()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Failure alerting
# ---------------------------------------------------------------------------

async def _alert_failure(snap_id: int, error: str) -> None:
    """POST a small JSON body to the configured webhook (best-effort)."""
    settings = get_settings()
    webhook = settings.autohub_snapshot_alert_webhook
    if not webhook:
        return
    try:
        import httpx  # already in requirements
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                webhook,
                json={
                    "service": "autobaza-api",
                    "event": "autohub_snapshot_failed",
                    "snapshot_id": snap_id,
                    "error": error[:1000],
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        logger.info("Snapshot failure alert webhook posted")
    except Exception as e:
        logger.warning(f"Snapshot failure alert webhook failed: {e}")


# ---------------------------------------------------------------------------
# CLI entrypoint — run a snapshot manually for local testing.
# Usage: python -m app.services.autohub_snapshot_job
# Honors AUTOHUB_SNAPSHOT_DB_PATH env var; defaults to /data/... (configure
# locally with e.g. AUTOHUB_SNAPSHOT_DB_PATH=./snap.db).
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    async def _main():
        try:
            summary = await run_snapshot_job(triggered_by="cli")
            print(f"\nDONE: {summary}")
        except Exception as e:
            print(f"\nFAILED: {e}", file=sys.stderr)
            sys.exit(1)

    asyncio.run(_main())
