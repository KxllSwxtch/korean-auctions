"""Mapper tests driven by committed dbauto payloads.

The fixtures are real captured responses, so these tests pin the wire contract in
both directions: they fail if dbauto's shape assumptions stop holding, and they fail
if we break a field the frontend reads. Nothing here touches the network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.heydealer_dbauto_mapper import (
    ATLAS_VIEW_ORDER,
    REPAIR_MARKS,
    build_diagram,
    map_detail,
    map_facet_options,
    map_list_card,
    normalize_list,
    repair_mark,
)

FIXTURES = Path(__file__).parent / "fixtures" / "heydealer"


def _load(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cards():
    return _load("cars")


@pytest.fixture(scope="module")
def detail_rich():
    return _load("detail-rich")


@pytest.fixture(scope="module")
def atlas():
    return _load("accident-atlas")


# --------------------------------------------------------------------------- #
# List rows
# --------------------------------------------------------------------------- #


def test_every_fixture_card_maps_without_error(cards):
    assert len(cards) == 30
    for card in cards:
        row = map_list_card(card)
        assert row["hash_id"]
        assert row["id"] == row["hash_id"] == row["lot_number"]


def test_card_emits_both_frontend_key_sets(cards):
    """/cars reads main_image/is_inspected; /cars/filtered reads the *_url twins."""
    row = map_list_card(cards[0])
    for legacy, modern in (
        ("main_image", "main_image_url"),
        ("brand_image", "brand_image_url"),
        ("registration_date", "initial_registration_date"),
        ("bid_count", "bids_count"),
        ("is_inspected", "is_pre_inspected"),
    ):
        assert row[legacy] == row[modern], f"{legacy} and {modern} must agree"


def test_tags_are_flattened_to_strings(cards):
    """The frontend maps tags with `tag => ({text: tag})`, so objects would render
    as [object Object]."""
    row = map_list_card(cards[0])
    assert row["tags"], "fixture card should carry tags"
    assert all(isinstance(tag, str) for tag in row["tags"])


def test_price_stays_in_manwon(cards):
    """A 10,000x inflation bug would be invisible in types and obvious to a buyer."""
    priced = [c for c in cards if isinstance(c.get("desired_price"), int)]
    for card in priced:
        row = map_list_card(card)
        assert row["desired_price"] == card["desired_price"]
        assert row["price"] == row["current_price"] == row["desired_price"]


def test_absent_price_stays_none_not_zero(cards):
    """desired_price: null means a sealed bid, not a free car."""
    sealed = [c for c in cards if c.get("desired_price") is None]
    assert sealed, "fixture should contain at least one sealed-bid card"
    assert map_list_card(sealed[0])["desired_price"] is None


def test_list_feed_has_no_gallery_or_drivetrain(cards):
    """Documents a real dbauto gap so a future reader does not hunt for a bug."""
    row = map_list_card(cards[0])
    assert row["images"] == [] and row["image_urls"] == []
    assert row["fuel_display"] is None and row["transmission_display"] is None
    assert row["main_image_url"], "but the card image itself must survive"


def test_empty_car_number_becomes_none(cards):
    """Upstream uses "" for unknown; the UI checks for null."""
    blank = [c for c in cards if c.get("car_number") == ""]
    assert blank, "fixture should contain a card with a blank plate"
    assert map_list_card(blank[0])["car_number"] is None


# --------------------------------------------------------------------------- #
# List envelope
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "body,expected_total",
    [
        ({"total": 7003, "items": []}, 7003),
        ({"total": "7003", "items": []}, None),
        ({"total": -1, "items": []}, None),
        ({"total": True, "items": []}, None),
        ({}, None),
        (None, None),
    ],
)
def test_normalize_list_only_trusts_real_counts(body, expected_total):
    assert normalize_list(body)["total"] == expected_total


def test_normalize_list_drops_rows_without_hash_id():
    body = {"items": [{"hash_id": "a"}, {"hash_id": ""}, {}, None, "x"]}
    assert [i["hash_id"] for i in normalize_list(body)["items"]] == ["a"]


def test_normalize_list_survives_a_null_items_array():
    assert normalize_list({"items": None, "total": 5})["items"] == []


# --------------------------------------------------------------------------- #
# Facets
# --------------------------------------------------------------------------- #


def test_facets_map_to_taxonomy_dto():
    body = {"options": [{"value": "xoKegB", "label": "Hyundai", "count": 2470}]}
    assert map_facet_options(body) == [
        {
            "hash_id": "xoKegB",
            "value": "xoKegB",
            "name": "Hyundai",
            "label": "Hyundai",
            "count": 2470,
        }
    ]


def test_facets_of_a_malformed_body_are_empty():
    for body in ({"options": None}, {}, None, []):
        assert map_facet_options(body) == []


def test_facet_without_a_value_is_dropped():
    body = {"options": [{"label": "x", "count": 1}, {"value": "v", "label": "y"}]}
    assert [o["hash_id"] for o in map_facet_options(body)] == ["v"]


# --------------------------------------------------------------------------- #
# Detail
# --------------------------------------------------------------------------- #


def test_detail_flattens_the_auction_block(detail_rich):
    mapped = map_detail(detail_rich)
    auction = detail_rich["auction"]
    assert mapped["auction_type"] == auction["auction_type"]
    assert mapped["end_at"] == auction["end_at"]
    assert mapped["bids_count"] == auction["bids_count"]
    assert mapped["max_bids_count"] == auction["max_bids_count"]


def test_detail_keeps_the_rich_inspection_blocks(detail_rich):
    mapped = map_detail(detail_rich)
    for key in (
        "paint_thickness_inspection",
        "carhistory",
        "vehicle_information",
        "image_groups",
        "advanced_options",
        "engine_sound_video",
        "inspected_condition",
    ):
        assert mapped[key], f"{key} drives a detail section and must survive"
    assert mapped["standard_new_car_price"] == detail_rich["standard_new_car_price"]


def test_condition_data_is_derived_from_condition_items(detail_rich):
    """dbauto has no condition_data; the UI needs {basic:[{text,type}]}."""
    mapped = map_detail(detail_rich)
    basic = mapped["condition_data"]["basic"]
    assert basic and all("text" in item and "type" in item for item in basic)
    assert {item["type"] for item in basic} <= {"heading", "item"}


def test_carhistory_summary_preserves_absent_counts_as_none():
    """0 would claim "no accidents reported"; None means "not reported"."""
    mapped = map_detail({"hash_id": "x", "carhistory": {"owner_changed_count": 2}})
    summary = mapped["carhistory_summary"]
    assert summary["owner_changed_count"] == 2
    assert summary["my_car_accident_count"] is None


def test_detail_of_a_sparse_car_does_not_explode():
    mapped = map_detail(_load("detail-sparse"))
    assert mapped["hash_id"]


def test_detail_without_auction_block_falls_back():
    mapped = map_detail({"hash_id": "x", "desired_price": 1200})
    assert mapped["desired_price"] == 1200


# --------------------------------------------------------------------------- #
# Damage diagram
# --------------------------------------------------------------------------- #


def test_atlas_alone_reports_no_damage(atlas):
    """The atlas is static geometry: every status in it is "none"."""
    diagram = build_diagram(atlas, [])
    assert diagram["total_damages"] == 0
    assert diagram["damage_summary"]["none"] > 0


def test_join_applies_the_cars_real_repairs(atlas, detail_rich):
    repairs = detail_rich["accident_repairs"]
    assert repairs, "the rich fixture should have damage"
    diagram = build_diagram(atlas, repairs)

    assert diagram["total_damages"] == len(repairs)
    flat = [r for view in diagram["views"] for r in view["accident_repairs"]]
    for repair in repairs:
        matched = [r for r in flat if r["part"] == repair["part"]]
        assert matched, f"{repair['part']} is missing from the atlas geometry"
        assert all(r["repair"] == repair["repair"] for r in matched)


def test_every_part_keeps_its_coordinates(atlas, detail_rich):
    diagram = build_diagram(atlas, detail_rich["accident_repairs"])
    for view in diagram["views"]:
        for repair in view["accident_repairs"]:
            assert len(repair["position"]) == 2, "badge placement needs [x, y]"


def test_views_are_ordered_for_reading(atlas):
    diagram = build_diagram(atlas, [])
    assert [v["type"] for v in diagram["views"]] == list(ATLAS_VIEW_ORDER)


def test_legacy_single_view_keys_mirror_the_primary_view(atlas):
    diagram = build_diagram(atlas, [])
    primary = diagram["views"][0]
    assert diagram["image_url"] == primary["image_url"]
    assert diagram["image_width"] == primary["image_width"]
    assert diagram["accident_repairs"] == primary["accident_repairs"]


def test_marks_are_korean_glyphs_never_english_initials(atlas, detail_rich):
    """Regression: a Korean buyer saw 교환 rendered as "E"."""
    diagram = build_diagram(atlas, detail_rich["accident_repairs"])
    labels = {
        r["label"] for view in diagram["views"] for r in view["accident_repairs"]
    }
    assert labels <= {"", "X", "W", "P"}
    assert "E" not in labels
    assert "E" not in REPAIR_MARKS.values()


@pytest.mark.parametrize(
    "code,mark",
    [("exchange", "X"), ("weld", "W"), ("painted", "P"), ("none", ""), (None, ""), ("", "")],
)
def test_repair_mark_table(code, mark):
    assert repair_mark(code) == mark


def test_diagram_of_an_empty_atlas_is_still_well_formed():
    diagram = build_diagram([], [])
    assert diagram["views"] == []
    assert diagram["accident_repairs"] == []
    assert diagram["total_damages"] == 0
