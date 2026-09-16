"""The listing-only fields that reach an Autohub car detail.

Prices, the lot number and the auction status live on the auction listing row,
never on the detail endpoint. Two call paths back-fill them - a mapped
AutohubCar (live entry index) and a raw entry dict (snapshot) - and both funnel
through `_set_listing_fields`. These tests pin the invariant that matters: the
two paths cannot disagree about the same car.
"""

from app.models.autohub import AutohubCar, AutohubCarDetail
from app.parsers.autohub_parser import (
    apply_listing_car,
    apply_listing_fields,
    determine_status,
    map_car_entry,
)


def _entry(**overrides) -> dict:
    """A raw listing entry, shaped as the upstream listing endpoint returns it."""
    entry = {
        "carId": "12345",
        "entryNo": "A-77",
        "startAmt": 1200,
        "hopeAmt": 1500,
        "bidSuccAmt": None,
        "bidFailYn": "",
        "aftBidYn": "",
    }
    entry.update(overrides)
    return entry


def _detail() -> AutohubCarDetail:
    return AutohubCarDetail(car_id="12345")


def test_live_and_snapshot_paths_agree_on_status():
    """The anti-drift invariant: one car, two paths, one answer.

    A sold lot must read as sold whether the detail was assembled from the warm
    entry index or from a stored snapshot.
    """
    entry = _entry(bidSuccAmt=1430)

    from_snapshot = _detail()
    apply_listing_fields(from_snapshot, entry)

    from_live = _detail()
    apply_listing_car(from_live, map_car_entry(entry))

    assert from_snapshot.status == "낙찰"
    assert from_live.status == from_snapshot.status
    assert from_live.starting_price == from_snapshot.starting_price == 1200
    assert from_live.lot_number == from_snapshot.lot_number == "A-77"


def test_snapshot_path_derives_every_status_the_listing_can_report():
    for overrides, expected in (
        ({"bidSuccAmt": 1430}, "낙찰"),
        ({"aftBidYn": "Y"}, "후상담"),
        ({"bidFailYn": "Y"}, "유찰"),
        ({}, "출품등록"),
    ):
        detail = _detail()
        apply_listing_fields(detail, _entry(**overrides))
        assert detail.status == expected
        assert determine_status(_entry(**overrides)) == expected


def test_missing_listing_row_leaves_status_unknown():
    """No row means no knowledge - the UI must not be handed a guess."""
    from_missing_car = _detail()
    apply_listing_car(from_missing_car, None)
    assert from_missing_car.status is None

    from_missing_entry = _detail()
    apply_listing_fields(from_missing_entry, None)
    assert from_missing_entry.status is None


def test_blank_upstream_status_normalises_to_none():
    """AutohubCar.status defaults to "", which must not reach the UI as a value."""
    car = AutohubCar(car_id="12345", auction_number="A-77", starting_price=1200)
    assert car.status == ""

    detail = _detail()
    apply_listing_car(detail, car)
    assert detail.status is None


def test_detail_status_defaults_to_none_before_any_listing_row_is_applied():
    assert _detail().status is None
