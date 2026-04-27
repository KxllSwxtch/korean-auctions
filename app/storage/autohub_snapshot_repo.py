"""
SQLite-backed repository for the weekly Autohub catalogue snapshot.

Designed for one writer (the Tuesday-night snapshot job, gated by the
APScheduler leader lock) and many concurrent readers (Wednesday traffic
from both Gunicorn workers). WAL mode permits readers and the writer to
proceed without blocking each other.

Atomic publish:
    - Each run inserts a new row into `snapshots` with status='in_progress'
      and a unique `snapshot_id`. Cars/details/brands rows are written
      against that id incrementally.
    - When the writer is done, `activate_snapshot(snap_id)` updates the
      single row in `active_snapshot` inside one transaction.
    - Readers always join through `active_snapshot` so the cutover is
      instantaneous.

Image storage is intentionally NOT included in v1: the frontend loads
images directly from file.ahsellcar.co.kr (a separate CDN host), and the
overload complaint targets api.ahsellcar.co.kr only.

See plans/wednesday-snapshot-mode.md for the full design.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from app.core.logging import get_logger

logger = get_logger("autohub_snapshot_repo")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    status          TEXT NOT NULL DEFAULT 'in_progress',
    car_count       INTEGER NOT NULL DEFAULT 0,
    detail_count    INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    duration_secs   INTEGER
);

CREATE TABLE IF NOT EXISTS active_snapshot (
    pk              INTEGER PRIMARY KEY CHECK (pk = 1),
    snapshot_id     INTEGER NOT NULL REFERENCES snapshots(id)
);

CREATE TABLE IF NOT EXISTS cars (
    snapshot_id     INTEGER NOT NULL,
    car_id          TEXT NOT NULL,
    entry_no        TEXT,
    entry_id        TEXT,
    title_en        TEXT,
    title_ko        TEXT,
    car_year        INTEGER,
    mileage         INTEGER,
    fuel_code       TEXT,
    brand_id        TEXT,
    model_id        TEXT,
    model_detail_id TEXT,
    starting_price  INTEGER,
    hope_price      INTEGER,
    condition_grade TEXT,
    lane            TEXT,
    perf_id         TEXT,
    soh             REAL,
    auction_result  TEXT,
    auction_date    TEXT,
    raw_listing_json TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, car_id)
);
CREATE INDEX IF NOT EXISTS cars_entry_idx    ON cars(snapshot_id, entry_no);
CREATE INDEX IF NOT EXISTS cars_brand_idx    ON cars(snapshot_id, brand_id, model_id, model_detail_id);
CREATE INDEX IF NOT EXISTS cars_year_idx     ON cars(snapshot_id, car_year);
CREATE INDEX IF NOT EXISTS cars_mileage_idx  ON cars(snapshot_id, mileage);
CREATE INDEX IF NOT EXISTS cars_price_idx    ON cars(snapshot_id, starting_price);
CREATE INDEX IF NOT EXISTS cars_fuel_idx     ON cars(snapshot_id, fuel_code);

CREATE TABLE IF NOT EXISTS car_details (
    snapshot_id     INTEGER NOT NULL,
    car_id          TEXT NOT NULL,
    detail_json     TEXT,
    inspection_json TEXT,
    diagram_json    TEXT,
    legend_json     TEXT,
    perf_frame_json TEXT,
    fetched_at      TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, car_id)
);

CREATE TABLE IF NOT EXISTS brands (
    snapshot_id     INTEGER PRIMARY KEY,
    brands_json     TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

class SnapshotRepo:
    """SQLite repo for the Autohub weekly snapshot.

    Connections are per-thread (sqlite3 forbids sharing a connection across
    threads by default). We keep a thread-local cache so each Gunicorn
    worker thread can reuse its own connection without paying for repeat
    `PRAGMA` setup.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._tls = threading.local()
        self._init_lock = threading.Lock()
        self._initialized = False
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    # ----- low-level connection plumbing ----------------------------------

    def _initialize(self) -> None:
        """Create the schema and apply WAL pragmas. Idempotent."""
        with self._init_lock:
            if self._initialized:
                return
            con = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
            try:
                con.execute("PRAGMA journal_mode=WAL")
                con.execute("PRAGMA synchronous=NORMAL")
                con.execute("PRAGMA busy_timeout=5000")
                con.execute("PRAGMA foreign_keys=ON")
                con.executescript(_SCHEMA)
            finally:
                con.close()
            self._initialized = True
            logger.info(f"Autohub snapshot DB ready at {self.db_path}")

    def _connection(self) -> sqlite3.Connection:
        """Get (or create) the thread-local SQLite connection."""
        con = getattr(self._tls, "con", None)
        if con is None:
            con = sqlite3.connect(self.db_path, timeout=30)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=NORMAL")
            con.execute("PRAGMA busy_timeout=5000")
            con.execute("PRAGMA foreign_keys=ON")
            self._tls.con = con
        return con

    @contextmanager
    def _txn(self) -> Iterator[sqlite3.Connection]:
        """Run a block inside a single transaction; commit or roll back.

        If BEGIN IMMEDIATE itself fails (e.g. SQLITE_BUSY beyond busy_timeout),
        we re-raise without attempting ROLLBACK — there is no transaction to
        roll back, and calling ROLLBACK would mask the original error with
        "no transaction is active". Likewise, failures during ROLLBACK are
        logged and swallowed so the user-facing exception is the real one.
        """
        con = self._connection()
        try:
            con.execute("BEGIN IMMEDIATE")
        except Exception:
            raise
        try:
            yield con
            con.execute("COMMIT")
        except Exception:
            try:
                con.execute("ROLLBACK")
            except Exception as rb_err:
                logger.warning(f"ROLLBACK failed (suppressed): {rb_err}")
            raise

    # ----- snapshot lifecycle ---------------------------------------------

    def begin_snapshot(self) -> int:
        """Insert a new row in `snapshots` and return its id."""
        now = datetime.now(timezone.utc).isoformat()
        with self._txn() as con:
            cur = con.execute(
                "INSERT INTO snapshots (started_at, status) VALUES (?, 'in_progress')",
                (now,),
            )
            snap_id = cur.lastrowid
        logger.info(f"Snapshot {snap_id} begun at {now}")
        return int(snap_id)

    def activate_snapshot(self, snap_id: int) -> None:
        """Atomically promote `snap_id` to be the active snapshot."""
        with self._txn() as con:
            con.execute(
                """
                INSERT INTO active_snapshot (pk, snapshot_id)
                VALUES (1, ?)
                ON CONFLICT(pk) DO UPDATE SET snapshot_id=excluded.snapshot_id
                """,
                (snap_id,),
            )
        logger.info(f"Snapshot {snap_id} is now active")

    def complete_snapshot(self, snap_id: int, car_count: int, detail_count: int) -> None:
        """Mark the snapshot as completed with counts and duration."""
        with self._txn() as con:
            row = con.execute(
                "SELECT started_at FROM snapshots WHERE id = ?", (snap_id,)
            ).fetchone()
            duration = None
            if row and row["started_at"]:
                started = datetime.fromisoformat(row["started_at"])
                duration = int((datetime.now(timezone.utc) - started).total_seconds())
            now = datetime.now(timezone.utc).isoformat()
            con.execute(
                """
                UPDATE snapshots
                SET status='completed', completed_at=?, car_count=?,
                    detail_count=?, duration_secs=?
                WHERE id=?
                """,
                (now, car_count, detail_count, duration, snap_id),
            )
        logger.info(
            f"Snapshot {snap_id} completed: {car_count} cars, "
            f"{detail_count} details, duration={duration}s"
        )

    def fail_snapshot(self, snap_id: int, error: str) -> None:
        """Mark the snapshot as failed; readers will skip it."""
        now = datetime.now(timezone.utc).isoformat()
        with self._txn() as con:
            con.execute(
                """
                UPDATE snapshots
                SET status='failed', completed_at=?, error=?
                WHERE id=?
                """,
                (now, error[:2000], snap_id),
            )
        logger.error(f"Snapshot {snap_id} marked failed: {error[:200]}")

    # ----- writes ---------------------------------------------------------

    def write_brands(self, snap_id: int, brands_payload: Any) -> None:
        """Store the raw brands tree response under this snapshot."""
        payload = json.dumps(brands_payload, ensure_ascii=False, default=str)
        with self._txn() as con:
            con.execute(
                """
                INSERT INTO brands (snapshot_id, brands_json) VALUES (?, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET brands_json=excluded.brands_json
                """,
                (snap_id, payload),
            )

    def write_cars(self, snap_id: int, entries: Iterable[dict]) -> int:
        """Insert raw listing entries. Returns the count actually written.

        `entries` is an iterable of dicts in the shape returned by
        /auction/external/rest/api/v1/entry/list/paging -> data.list[].
        """
        rows = []
        for entry in entries:
            car_id = entry.get("carId")
            if not car_id:
                continue
            rows.append((
                snap_id,
                car_id,
                entry.get("entryNo"),
                entry.get("entryId"),
                entry.get("carNmEn"),
                entry.get("carNm"),
                entry.get("carYear"),
                entry.get("mileage"),
                entry.get("fuelCode"),
                entry.get("brandId"),
                entry.get("modelId"),
                entry.get("modelDetailId"),
                entry.get("startAmt"),
                entry.get("hopeAmt"),
                entry.get("inspGrade"),
                entry.get("aucLaneCode"),
                entry.get("perfId"),
                entry.get("soh"),
                _auction_result_flag(entry),
                entry.get("aucDate"),
                json.dumps(entry, ensure_ascii=False, default=str),
            ))
        if not rows:
            return 0
        with self._txn() as con:
            con.executemany(
                """
                INSERT INTO cars (
                    snapshot_id, car_id, entry_no, entry_id, title_en, title_ko,
                    car_year, mileage, fuel_code, brand_id, model_id, model_detail_id,
                    starting_price, hope_price, condition_grade, lane, perf_id,
                    soh, auction_result, auction_date, raw_listing_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_id, car_id) DO UPDATE SET
                    raw_listing_json=excluded.raw_listing_json
                """,
                rows,
            )
        return len(rows)

    def write_car_detail(
        self,
        snap_id: int,
        car_id: str,
        detail_json: Optional[dict] = None,
        inspection_json: Optional[dict] = None,
        diagram_json: Optional[dict] = None,
        legend_json: Optional[dict] = None,
        perf_frame_json: Optional[dict] = None,
    ) -> None:
        """Persist the six-endpoint detail bundle for a car."""
        now = datetime.now(timezone.utc).isoformat()
        with self._txn() as con:
            con.execute(
                """
                INSERT INTO car_details (
                    snapshot_id, car_id, detail_json, inspection_json,
                    diagram_json, legend_json, perf_frame_json, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_id, car_id) DO UPDATE SET
                    detail_json=excluded.detail_json,
                    inspection_json=excluded.inspection_json,
                    diagram_json=excluded.diagram_json,
                    legend_json=excluded.legend_json,
                    perf_frame_json=excluded.perf_frame_json,
                    fetched_at=excluded.fetched_at
                """,
                (
                    snap_id, car_id,
                    _dump_or_none(detail_json),
                    _dump_or_none(inspection_json),
                    _dump_or_none(diagram_json),
                    _dump_or_none(legend_json),
                    _dump_or_none(perf_frame_json),
                    now,
                ),
            )

    # ----- reads ----------------------------------------------------------

    def get_active_snapshot(self) -> Optional[dict]:
        """Return metadata for the currently-active snapshot, or None."""
        con = self._connection()
        row = con.execute(
            """
            SELECT s.id, s.started_at, s.completed_at, s.status,
                   s.car_count, s.detail_count, s.duration_secs
            FROM active_snapshot a
            JOIN snapshots s ON s.id = a.snapshot_id
            WHERE a.pk = 1
            """
        ).fetchone()
        if not row:
            return None
        return dict(row)

    def list_snapshots(self, limit: int = 20) -> list[dict]:
        """List recent snapshots, newest first."""
        con = self._connection()
        rows = con.execute(
            """
            SELECT id, started_at, completed_at, status, car_count,
                   detail_count, error, duration_secs
            FROM snapshots
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_brands_json(self, snap_id: int) -> Optional[str]:
        con = self._connection()
        row = con.execute(
            "SELECT brands_json FROM brands WHERE snapshot_id = ?", (snap_id,)
        ).fetchone()
        return row["brands_json"] if row else None

    def get_car_detail_bundle(
        self, snap_id: int, car_id: str
    ) -> Optional[dict]:
        con = self._connection()
        row = con.execute(
            """
            SELECT detail_json, inspection_json, diagram_json,
                   legend_json, perf_frame_json, fetched_at
            FROM car_details
            WHERE snapshot_id = ? AND car_id = ?
            """,
            (snap_id, car_id),
        ).fetchone()
        return dict(row) if row else None

    def query_cars(
        self,
        snap_id: int,
        where: str,
        params: tuple,
        order_by: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        """Run a parameterised filter+sort+paginate query against `cars`.

        `where` is an extra clause AND'd onto `snapshot_id = ?`; `params`
        is the tuple of bind values for it. Returns (rows, total_count).
        """
        con = self._connection()
        full_where = f"snapshot_id = ?{(' AND ' + where) if where else ''}"
        total = con.execute(
            f"SELECT COUNT(*) AS n FROM cars WHERE {full_where}",
            (snap_id, *params),
        ).fetchone()["n"]
        offset = max(0, (page - 1) * page_size)
        rows = con.execute(
            f"""
            SELECT raw_listing_json FROM cars
            WHERE {full_where}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
            """,
            (snap_id, *params, page_size, offset),
        ).fetchall()
        return [dict(r) for r in rows], int(total)

    # ----- maintenance ----------------------------------------------------

    def vacuum_keeping_last(self, keep: int) -> int:
        """Drop snapshot rows beyond the `keep` most recent. Returns deleted count.

        Never drops the currently-active snapshot, even if it's older.
        """
        if keep < 1:
            keep = 1
        with self._txn() as con:
            active_row = con.execute(
                "SELECT snapshot_id FROM active_snapshot WHERE pk = 1"
            ).fetchone()
            active_id = active_row["snapshot_id"] if active_row else None
            keep_ids = [
                r["id"] for r in con.execute(
                    "SELECT id FROM snapshots ORDER BY id DESC LIMIT ?",
                    (keep,),
                ).fetchall()
            ]
            if active_id is not None and active_id not in keep_ids:
                keep_ids.append(active_id)
            if not keep_ids:
                return 0
            placeholders = ",".join("?" for _ in keep_ids)
            con.execute(
                f"DELETE FROM cars WHERE snapshot_id NOT IN ({placeholders})",
                tuple(keep_ids),
            )
            con.execute(
                f"DELETE FROM car_details WHERE snapshot_id NOT IN ({placeholders})",
                tuple(keep_ids),
            )
            con.execute(
                f"DELETE FROM brands WHERE snapshot_id NOT IN ({placeholders})",
                tuple(keep_ids),
            )
            cur = con.execute(
                f"DELETE FROM snapshots WHERE id NOT IN ({placeholders})",
                tuple(keep_ids),
            )
            deleted = cur.rowcount
        if deleted:
            logger.info(f"Vacuum: dropped {deleted} old snapshot rows, kept {keep_ids}")
        # WAL checkpoint to reclaim disk space.
        try:
            self._connection().execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError:
            pass
        return int(deleted)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dump_or_none(payload: Optional[Any]) -> Optional[str]:
    if payload is None:
        return None
    return json.dumps(payload, ensure_ascii=False, default=str)


def _auction_result_flag(entry: dict) -> Optional[str]:
    """Map an auction listing entry to a filterable result code.

    Y   = sold (bidSuccAmt > 0)
    N   = unsold (bidFailYn == "Y")
    NULL = registered / not yet held / pending

    NOTE for Phase C: the frontend's `AutohubAuctionResult.NOT_HELD = "none"`
    filter must be translated to `WHERE auction_result IS NULL` (not
    `WHERE auction_result = 'none'`) when building the SnapshotSource WHERE
    clause.
    """
    if entry.get("bidSuccAmt"):
        return "Y"
    if entry.get("bidFailYn") == "Y":
        return "N"
    return None
