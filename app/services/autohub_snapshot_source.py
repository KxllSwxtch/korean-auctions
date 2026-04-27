"""
Read source backed by the weekly Autohub snapshot.

Translates `AutohubSearchRequest` filters/sort/pagination into SQL against
the SnapshotRepo, then runs the raw JSON rows through the same map_*
parsers the live path uses. This keeps live and snapshot results
bit-identical for the same inputs (within snapshot freshness).

Used only when the mode resolver returns mode="snapshot". Live behavior
must never depend on this module.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from app.core.logging import get_logger
from app.models.autohub import (
    AutohubCarDetail,
    AutohubCarDetailResponse,
    AutohubResponse,
)
from app.models.autohub_filters import (
    AutohubAuctionResult,
    AutohubBrandsResponse,
    AutohubFuelType,
    AutohubLane,
    AutohubSearchRequest,
    AutohubSortOrder,
)
from app.parsers.autohub_parser import (
    map_brands,
    map_car_detail,
    map_car_entry,
    map_diagram,
    map_inspection,
)
from app.storage.autohub_snapshot_repo import SnapshotRepo

logger = get_logger("autohub_snapshot_source")


# Map sort enum → SQL column. entry_no is stored as TEXT (Autohub returns
# it that way) but is numeric, so cast for correct ordering.
_SORT_COLUMN = {
    AutohubSortOrder.ENTRY: "CAST(entry_no AS INTEGER)",
    AutohubSortOrder.PRICE: "starting_price",
    AutohubSortOrder.YEAR: "car_year",
    AutohubSortOrder.MILEAGE: "mileage",
}


class AutohubSnapshotSource:
    """SQLite-backed read source for snapshot mode."""

    def __init__(self, repo: SnapshotRepo):
        self.repo = repo

    # ----- public API ------------------------------------------------------

    def get_car_list(
        self, params: AutohubSearchRequest, snapshot_id: int
    ) -> AutohubResponse:
        """Filter+sort+paginate against the snapshot's cars table."""
        # Entry-number lookup: a single indexed equality query, no scan.
        if params.entry_number:
            return self._search_by_entry_number(params, snapshot_id)

        where, args = self._build_where(params)
        order_by = self._build_order_by(params)
        rows, total_count = self.repo.query_cars(
            snapshot_id, where=where, params=tuple(args),
            order_by=order_by, page=params.page, page_size=params.page_size,
        )
        cars = self._rows_to_cars(rows)
        total_pages = (total_count + params.page_size - 1) // params.page_size if params.page_size > 0 else 0
        return AutohubResponse(
            success=True,
            data=cars,
            total_count=total_count,
            total_pages=total_pages,
            current_page=params.page,
            page_size=params.page_size,
        )

    def get_brands(self, snapshot_id: int) -> AutohubBrandsResponse:
        raw = self.repo.get_brands_json(snapshot_id)
        if raw is None:
            # Brands fetch failed during snapshot (recoverable per the job
            # design). Surface an empty list rather than 500 — frontend
            # filter dropdowns degrade to empty, which is acceptable.
            logger.warning(f"Snapshot {snapshot_id} has no brands payload")
            return AutohubBrandsResponse(success=True, data=[])
        try:
            payload = json.loads(raw)
            groups = map_brands(payload)
            return AutohubBrandsResponse(success=True, data=groups)
        except Exception as e:
            logger.error(f"Snapshot brands deserialise failed: {e}", exc_info=True)
            return AutohubBrandsResponse(success=False, error=str(e))

    def get_car_detail(
        self, car_id: str, perf_id: Optional[str], snapshot_id: int
    ) -> AutohubCarDetailResponse:
        bundle = self.repo.get_car_detail_bundle(snapshot_id, car_id)
        if bundle is None:
            return AutohubCarDetailResponse(
                success=False,
                error=f"Car {car_id} is not in this week's snapshot",
            )

        try:
            detail_data = _loads_or_empty(bundle.get("detail_json"))
            inspection_data = _loads_or_empty(bundle.get("inspection_json"))
            diagram_data = _loads_or_empty(bundle.get("diagram_json"))
            legend_data = _loads_or_empty(bundle.get("legend_json"))
            perf_frame_data = _loads_or_empty(bundle.get("perf_frame_json"))

            car_detail = map_car_detail(detail_data) if detail_data else AutohubCarDetail(car_id=car_id)
            if inspection_data:
                car_detail.inspection = map_inspection(inspection_data)
            if diagram_data:
                car_detail.diagram = map_diagram(diagram_data, legend_data, perf_frame_data)

            # Pull starting/hope price from the listing row (we already have it).
            listing_rows, _ = self.repo.query_cars(
                snapshot_id,
                where="car_id = ?", params=(car_id,),
                order_by="car_id", page=1, page_size=1,
            )
            if listing_rows:
                listing = json.loads(listing_rows[0]["raw_listing_json"])
                car_detail.starting_price = listing.get("startAmt")
                car_detail.hope_price = listing.get("hopeAmt")

            return AutohubCarDetailResponse(success=True, data=car_detail)
        except Exception as e:
            logger.error(
                f"Snapshot car_detail mapping failed for {car_id}: {e}",
                exc_info=True,
            )
            return AutohubCarDetailResponse(success=False, error=str(e))

    # ----- helpers ---------------------------------------------------------

    def _build_where(self, params: AutohubSearchRequest) -> tuple[str, list]:
        clauses: list[str] = []
        args: list[Any] = []

        if params.car_brands:
            placeholders = ",".join("?" for _ in params.car_brands)
            clauses.append(f"brand_id IN ({placeholders})")
            args.extend(params.car_brands)
        if params.car_models:
            placeholders = ",".join("?" for _ in params.car_models)
            clauses.append(f"model_id IN ({placeholders})")
            args.extend(params.car_models)
        if params.car_model_details:
            placeholders = ",".join("?" for _ in params.car_model_details)
            clauses.append(f"model_detail_id IN ({placeholders})")
            args.extend(params.car_model_details)

        if params.fuel_type and params.fuel_type != AutohubFuelType.ALL:
            clauses.append("fuel_code = ?")
            args.append(params.fuel_type.value)

        if params.year_from is not None:
            clauses.append("car_year >= ?")
            args.append(params.year_from)
        if params.year_to is not None:
            clauses.append("car_year <= ?")
            args.append(params.year_to)

        if params.mileage_from is not None:
            clauses.append("mileage >= ?")
            args.append(params.mileage_from)
        if params.mileage_to is not None:
            clauses.append("mileage <= ?")
            args.append(params.mileage_to)

        if params.price_from is not None:
            clauses.append("starting_price >= ?")
            args.append(params.price_from)
        if params.price_to is not None:
            clauses.append("starting_price <= ?")
            args.append(params.price_to)

        if params.lane and params.lane != AutohubLane.ALL:
            clauses.append("lane = ?")
            args.append(params.lane.value)

        if params.condition_grade:
            clauses.append("condition_grade = ?")
            args.append(params.condition_grade)

        # Auction result filter — note the special NOT_HELD = "none" mapping
        # to NULL, since registered/pending cars are stored as auction_result
        # IS NULL by _auction_result_flag in the repo.
        if params.auction_result and params.auction_result != AutohubAuctionResult.ALL:
            if params.auction_result == AutohubAuctionResult.NOT_HELD:
                clauses.append("auction_result IS NULL")
            else:
                clauses.append("auction_result = ?")
                args.append(params.auction_result.value)

        return " AND ".join(clauses), args

    def _build_order_by(self, params: AutohubSearchRequest) -> str:
        col = _SORT_COLUMN.get(params.sort_order or AutohubSortOrder.ENTRY, "CAST(entry_no AS INTEGER)")
        direction = (params.sort_direction or "desc").lower()
        if direction not in ("asc", "desc"):
            direction = "desc"
        return f"{col} {direction.upper()}"

    def _search_by_entry_number(
        self, params: AutohubSearchRequest, snapshot_id: int
    ) -> AutohubResponse:
        """O(log n) indexed lookup — replaces the live path's 30-page scan."""
        rows, total = self.repo.query_cars(
            snapshot_id,
            where="entry_no = ?", params=(params.entry_number,),
            order_by="car_id", page=1, page_size=1,
        )
        cars = self._rows_to_cars(rows)
        return AutohubResponse(
            success=True,
            data=cars,
            total_count=total,
            total_pages=1 if cars else 0,
            current_page=1,
            page_size=params.page_size,
        )

    def _rows_to_cars(self, rows: list[dict]) -> list:
        out = []
        for row in rows:
            try:
                entry = json.loads(row["raw_listing_json"])
                out.append(map_car_entry(entry))
            except Exception as e:
                logger.warning(f"Snapshot row deserialise failed: {e}")
        return out


def _loads_or_empty(s: Optional[str]) -> dict:
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception:
        return {}
