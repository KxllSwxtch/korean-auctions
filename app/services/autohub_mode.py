"""
Mode resolver for the Autohub read path.

Decides on each request whether to serve from the live Autohub API or
from the weekly SQLite snapshot. Returns a small dataclass so callers
don't have to re-implement the decision logic.

Decision tree (in priority order):
    1. AUTOHUB_SNAPSHOT_ENABLED is false              → "live"
    2. Today's KST weekday not in AUTOHUB_SNAPSHOT_DAYS → "live"
    3. Active snapshot doesn't exist                  → "snapshot_unavailable"
    4. Active snapshot exists but is older than max_age → "snapshot" + stale=True
    5. Active snapshot exists and is fresh             → "snapshot"

Live mode is the safe default at every step; we never accidentally fall
into snapshot mode without an explicit "yes" on every check.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("autohub_mode")


ModeName = Literal["live", "snapshot", "snapshot_unavailable"]


@dataclass(frozen=True)
class ResolvedMode:
    """The resolved read-path mode plus metadata for the response."""
    mode: ModeName
    snapshot_id: Optional[int] = None
    snapshot_taken_at_iso: Optional[str] = None  # UTC ISO datetime
    stale: bool = False
    reason: str = ""

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    @property
    def is_snapshot(self) -> bool:
        return self.mode == "snapshot"

    @property
    def is_unavailable(self) -> bool:
        return self.mode == "snapshot_unavailable"


def _today_weekday_kst(tz_name: str) -> int:
    """Mon=0..Sun=6 in the configured timezone."""
    return datetime.now(ZoneInfo(tz_name)).weekday()


def _parse_days(days_csv: str) -> set[int]:
    """Parse "0,1,2" into a set of weekday ints. Empty string → empty set."""
    out: set[int] = set()
    for raw in days_csv.split(","):
        raw = raw.strip()
        if raw.isdigit():
            n = int(raw)
            if 0 <= n <= 6:
                out.add(n)
    return out


def resolve_mode(repo=None) -> ResolvedMode:
    """Compute the active read mode for right now.

    `repo` is an optional `SnapshotRepo` — if omitted, we lazy-load the
    job's singleton. Passing one explicitly is mainly for tests.
    """
    settings = get_settings()

    # Step 1: kill switch
    if not settings.autohub_snapshot_enabled:
        return ResolvedMode(mode="live", reason="snapshot_enabled=false")

    # Step 2: not a snapshot day in the configured timezone
    snapshot_days = _parse_days(settings.autohub_snapshot_days)
    if not snapshot_days:
        return ResolvedMode(mode="live", reason="snapshot_days empty")
    today = _today_weekday_kst(settings.autohub_snapshot_timezone)
    if today not in snapshot_days:
        return ResolvedMode(
            mode="live",
            reason=f"weekday {today} not in {sorted(snapshot_days)}",
        )

    # Step 3: snapshot must exist
    if repo is None:
        try:
            from app.services.autohub_snapshot_job import get_repo
            # We're sync here, but get_repo's only async call is the
            # threading.Lock-guarded singleton init, which is non-blocking
            # after the first call. Run it via a small sync shim.
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None and loop.is_running():
                # Caller is in async context — they should pass repo explicitly
                # to avoid blocking. Fall back to constructing a fresh repo.
                from app.storage.autohub_snapshot_repo import SnapshotRepo
                repo = SnapshotRepo(settings.autohub_snapshot_db_path)
            else:
                repo = asyncio.run(get_repo())
        except Exception as e:
            logger.warning(f"Mode resolver: repo unavailable ({e}) — failing safe to live")
            return ResolvedMode(mode="live", reason=f"repo init failed: {e}")

    try:
        active = repo.get_active_snapshot()
    except Exception as e:
        logger.warning(f"Mode resolver: get_active_snapshot failed ({e}) — failing safe to live")
        return ResolvedMode(mode="live", reason=f"repo read failed: {e}")

    if active is None:
        # Wednesday but no snapshot has ever been published. Hard fail —
        # the alternative (silent fallback to live) defeats the entire
        # purpose of snapshot mode on Wednesday.
        logger.error("Snapshot mode active but no snapshot published yet")
        return ResolvedMode(mode="snapshot_unavailable", reason="no active snapshot")

    if active.get("status") != "completed":
        logger.error(
            f"Active snapshot id={active.get('id')} has status="
            f"{active.get('status')!r} — treating as unavailable"
        )
        return ResolvedMode(
            mode="snapshot_unavailable",
            snapshot_id=active.get("id"),
            reason=f"active snapshot status is {active.get('status')!r}",
        )

    # Step 4 / 5: freshness check
    completed_at = active.get("completed_at")
    age_days: Optional[float] = None
    if completed_at:
        try:
            ts = datetime.fromisoformat(completed_at)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - ts).total_seconds() / 86400
        except Exception as e:
            logger.warning(f"Mode resolver: bad completed_at {completed_at!r} ({e})")

    stale = bool(
        age_days is not None
        and age_days > settings.autohub_snapshot_max_age_days
    )

    return ResolvedMode(
        mode="snapshot",
        snapshot_id=active.get("id"),
        snapshot_taken_at_iso=completed_at,
        stale=stale,
        reason=f"active snapshot id={active.get('id')} age_days={age_days}",
    )
