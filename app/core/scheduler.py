"""
Background cache warming scheduler.

Uses APScheduler to periodically pre-warm caches for the most popular
endpoints, so user requests always hit warm caches instead of triggering
slow upstream fetches on cache miss.

Only one worker runs warming jobs at a time, coordinated via file lock.
"""

import os
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from filelock import FileLock, Timeout
from loguru import logger

from app.core.config import get_settings

SESSIONS_DIR = Path("cache/sessions")
SCHEDULER_LOCK = SESSIONS_DIR / "scheduler_leader.lock"

_scheduler: AsyncIOScheduler | None = None
_leader_lock: FileLock | None = None  # held at module level to prevent GC


def _is_leader() -> bool:
    """Try to claim leader lock. Returns True if this worker is the leader."""
    global _leader_lock
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _leader_lock = FileLock(str(SCHEDULER_LOCK), timeout=0)
        _leader_lock.acquire()
        return True
    except Timeout:
        return False


# ---------------------------------------------------------------------------
# Warming functions — each wraps its service call in try/except so a single
# failure never crashes the scheduler.
# ---------------------------------------------------------------------------

async def warm_encar_catalog():
    """Warm the default Encar catalog listing (no filters, newest, first page)."""
    try:
        from app.services.encar_service import encar_service
        await encar_service.get_catalog(
            q="(And.Hidden.N._.CarType.A._.SellType.%EC%9D%BC%EB%B0%98.)",
            sr="|ModifiedDate|0|21",
            count=True,
            page=1,
            use_cache=True,
        )
        logger.info("Cache warmer: Encar catalog warmed")
    except Exception as e:
        logger.warning(f"Cache warmer: Encar catalog failed: {e}")


async def warm_exchange_rates():
    """Warm exchange rates cache."""
    try:
        import asyncio
        from app.services.exchange_rate_service import exchange_rate_service
        await asyncio.to_thread(exchange_rate_service.get_rates, bypass_cache=False)
        logger.info("Cache warmer: Exchange rates warmed")
    except Exception as e:
        logger.warning(f"Cache warmer: Exchange rates failed: {e}")


async def warm_kcar_cars():
    """Warm the default KCar car listing."""
    try:
        import asyncio
        from app.routes.kcar import kcar_service
        await asyncio.to_thread(kcar_service.get_cars, {"page_no": "1", "page_size": "20"})
        logger.info("Cache warmer: KCar cars warmed")
    except Exception as e:
        logger.warning(f"Cache warmer: KCar cars failed: {e}")


async def warm_lotte_cars():
    """Warm the default Lotte car listing."""
    try:
        from app.routes.lotte import get_lotte_service
        service = get_lotte_service()
        await service.get_cars_response_with_date_check(limit=20, offset=0)
        logger.info("Cache warmer: Lotte cars warmed")
    except Exception as e:
        logger.warning(f"Cache warmer: Lotte cars failed: {e}")


async def warm_sessions():
    """Proactively refresh auction sessions before they expire."""
    try:
        import asyncio
        from app.routes.lotte import get_lotte_service
        service = get_lotte_service()
        if hasattr(service, '_ensure_session'):
            await asyncio.to_thread(service._ensure_session)
            logger.info("Cache warmer: Lotte session refreshed")
    except Exception as e:
        logger.warning(f"Cache warmer: Lotte session refresh failed: {e}")

    try:
        from app.routes.kcar import kcar_service
        if hasattr(kcar_service, '_ensure_session'):
            import asyncio
            await asyncio.to_thread(kcar_service._ensure_session)
            logger.info("Cache warmer: KCar session refreshed")
    except Exception as e:
        logger.warning(f"Cache warmer: KCar session refresh failed: {e}")


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------

async def start_scheduler():
    """Initialize and start the background scheduler (only on the leader worker)."""
    global _scheduler

    if not _is_leader():
        logger.info("Scheduler: this worker is not the leader, skipping")
        return

    logger.info("Scheduler: this worker is the leader, starting warming jobs")
    _scheduler = AsyncIOScheduler()

    # Car listing warming — every 8 minutes (well within 10-min cache TTL)
    _scheduler.add_job(warm_encar_catalog, "interval", minutes=8,
                       next_run_time=datetime.now(), id="warm_encar")
    _scheduler.add_job(warm_kcar_cars, "interval", minutes=8,
                       next_run_time=datetime.now(), id="warm_kcar")
    _scheduler.add_job(warm_lotte_cars, "interval", minutes=8,
                       next_run_time=datetime.now(), id="warm_lotte")

    # Exchange rates — every 12 minutes (within 15-min TTL)
    _scheduler.add_job(warm_exchange_rates, "interval", minutes=12,
                       next_run_time=datetime.now(), id="warm_rates")

    # Session pre-warming — every 20 minutes (before 25-min expiry)
    _scheduler.add_job(warm_sessions, "interval", minutes=20,
                       next_run_time=datetime.now(), id="warm_sessions")

    # Weekly Autohub snapshot — Tuesday 22:00 KST
    # Gated by env so we can deploy the code dark before flipping the switch.
    settings = get_settings()
    if settings.autohub_snapshot_enabled:
        from app.services.autohub_snapshot_job import run_snapshot_job
        _scheduler.add_job(
            run_snapshot_job,
            CronTrigger(
                day_of_week="tue",
                hour=22,
                minute=0,
                timezone=settings.autohub_snapshot_timezone,
            ),
            id="autohub_weekly_snapshot",
            misfire_grace_time=1800,   # 30-min grace if leader was restarting at 22:00
            max_instances=1,           # never run two snapshots in parallel
            coalesce=True,             # if multiple firings queued, run only latest
        )
        logger.info(
            "Scheduler: registered Autohub snapshot job "
            "(Tuesday 22:00 {})", settings.autohub_snapshot_timezone,
        )
    else:
        logger.info(
            "Scheduler: Autohub snapshot job DISABLED "
            "(set AUTOHUB_SNAPSHOT_ENABLED=true to enable)"
        )

    _scheduler.start()
    logger.info("Scheduler: started with {} jobs", len(_scheduler.get_jobs()))


async def stop_scheduler():
    """Shut down the scheduler gracefully."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler: stopped")
