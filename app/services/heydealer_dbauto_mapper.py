"""Pure mappers from the dbauto HeyDealer payloads to this API's wire contract.

Every function here is a pure transform of already-parsed JSON: no I/O, no clock,
no environment. That is deliberate -- it is what lets the whole mapping layer be
tested against committed fixtures instead of a live third party, and it keeps the
one place that is coupled to dbauto's field names small enough to re-read when
they change something without telling us.

Two contracts have to be honoured exactly, because the frontend has been shipping
against them for months:

* **List rows are FLAT and aliased.** `autobazaapp/lib/api/heydealer.ts` nests them
  into `detail{}` / `auction{}` client-side, and it does so through two different
  transforms reading two different key sets (`/cars` reads `main_image`/`is_inspected`,
  `/cars/filtered` reads `main_image_url`/`is_pre_inspected`). Emitting the union of
  both key sets is what lets one backend shape feed both endpoints unchanged.
* **Prices stay in 만원.** `desired_price` and `standard_new_car_price` are 10,000-KRW
  units on both sides; the UI multiplies by 10,000 in `lib/currency.ts`. Converting
  here would inflate every price on the site by 10,000x.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

#: dbauto returns the atlas views in wire order; this is the order a human reads
#: a car in. Kept here rather than in the route so the snapshot and the live
#: response can never disagree about it.
ATLAS_VIEW_ORDER = ("top", "side_driver", "side_passenger", "bottom")

#: Korean 성능·상태점검기록부 glyphs. Deliberately not English initials -- a Korean
#: buyer reported "exchange" rendering as "E"; see tests/test_heydealer_diagram_marks.py.
REPAIR_MARKS = {"exchange": "X", "weld": "W", "painted": "P"}


def repair_mark(repair: str | None) -> str:
    """Map a repair code to its inspection-sheet glyph, or '' when there is none."""
    if not repair:
        return ""
    return REPAIR_MARKS.get(str(repair), "")


def _text(value: Any) -> str | None:
    """Normalise upstream's mix of ``None`` and ``""`` into a single absent value."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: Any) -> int | None:
    """Coerce to int, or ``None``.

    Absent must stay absent: a missing accident count rendered as 0 would claim
    "no accidents reported" about a car nobody has inspected.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _interior_text(raw: Any) -> str | None:
    """dbauto sends ``{"text": ..., "codes": [...]}`` here, older payloads a string."""
    if isinstance(raw, Mapping):
        return _text(raw.get("text"))
    return _text(raw)


def _tag_texts(raw: Any) -> list[str]:
    """Flatten dbauto's tag objects to the list of strings the frontend expects.

    `tags[].text` is preferred over `short_text`: upstream's short English form is
    wrong often enough to matter ("단순 (보험4건 · 1,223만원)" comes back as
    "Simple (1 claim)"), and under lang=ru/es the long form is the translated one.
    """
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    tags: list[str] = []
    for item in raw:
        if isinstance(item, Mapping):
            text = _text(item.get("text")) or _text(item.get("short_text"))
        else:
            text = _text(item)
        if text:
            tags.append(text)
    return tags


def _bid_manwon(raw: Any) -> int | None:
    """`highest_bid` is polymorphic: a bare 만원 number on cards, an object on detail."""
    if isinstance(raw, Mapping):
        return _int(raw.get("price"))
    return _int(raw)


def map_list_card(raw: Mapping[str, Any]) -> dict[str, Any]:
    """One dbauto `/cars` item -> one flat row of our `/cars` response.

    Emits the union of the two key sets the frontend transforms read, so the same
    row satisfies both `/cars` and `/cars/filtered` without a second mapper.

    Note the deliberate gap: dbauto's list feed carries **no** `image_urls`, `fuel`,
    `transmission`, `colour` or engine size -- only `main_image_url`. Those stay
    ``None`` on cards rather than being faked; the detail call fills them in.
    """
    hash_id = _text(raw.get("hash_id")) or ""
    full_name = _text(raw.get("full_name"))
    desired_price = _int(raw.get("desired_price"))
    interior = _interior_text(raw.get("interior_info"))
    registration_date = _text(raw.get("initial_registration_date"))
    main_image = _text(raw.get("main_image_url"))
    brand_image = _text(raw.get("brand_image_url"))
    short_location = _text(raw.get("short_location"))
    full_location = _text(raw.get("location"))
    is_inspected = bool(raw.get("is_pre_inspected"))
    tags = _tag_texts(raw.get("tags"))

    return {
        # identity -- three aliases because different call sites read different ones
        "id": hash_id,
        "hash_id": hash_id,
        "lot_number": hash_id,
        "auction_name": "HeyDealer",
        # naming
        "title": full_name,
        "model": full_name,
        "full_name": full_name,
        "model_part_name": _text(raw.get("model_part_name")),
        "grade_part_name": _text(raw.get("grade_part_name")),
        "brand_hash_id": _text(raw.get("brand_hash_id")),
        "model_group_hash_id": _text(raw.get("model_group_hash_id")),
        "model_hash_id": _text(raw.get("model_hash_id")),
        # spec
        "year": _int(raw.get("year")),
        "mileage": _int(raw.get("mileage")),
        "car_number": _text(raw.get("car_number")),
        "registration_date": registration_date,
        "initial_registration_date": registration_date,
        "interior": interior,
        "interior_info": interior,
        # dbauto's list feed has no per-card gallery or drivetrain data
        "images": [],
        "image_urls": [],
        "fuel": None,
        "fuel_display": None,
        "transmission": None,
        "transmission_display": None,
        "gear": None,
        "gear_display": None,
        # media
        "main_image": main_image,
        "main_image_url": main_image,
        "brand_image": brand_image,
        "brand_image_url": brand_image,
        # location
        "location": short_location or full_location,
        "short_location": short_location,
        "full_location": full_location or short_location,
        # status / auction
        "status": _text(raw.get("status")),
        "status_display": _text(raw.get("status_display")),
        "auction_type": _text(raw.get("auction_type")),
        "end_time": _text(raw.get("end_at")),
        "end_at": _text(raw.get("end_at")),
        "approved_at": _text(raw.get("approved_at")),
        "bid_count": _int(raw.get("bids_count")),
        "bids_count": _int(raw.get("bids_count")),
        "max_bids": _int(raw.get("max_bids_count")),
        "max_bids_count": _int(raw.get("max_bids_count")),
        "highest_bid": _bid_manwon(raw.get("highest_bid")),
        # 만원 on both sides -- never convert here
        "price": desired_price,
        "current_price": desired_price,
        "desired_price": desired_price,
        "is_inspected": is_inspected,
        "is_pre_inspected": is_inspected,
        "is_starred": bool(raw.get("is_starred")),
        "zero_type": _text(raw.get("zero_type")),
        "tags": tags,
    }


def normalize_list(body: Any) -> dict[str, Any]:
    """Coerce the four facts pagination arithmetic depends on; pass the rest through.

    The list body is the one response whose numbers drive arithmetic -- the page
    window is computed from `total` and rows are concatenated across pages -- so a
    stringly-typed total or a null array would silently produce a wrong grid rather
    than a caught error. Everything else is left untouched on purpose: dbauto adds
    card fields without warning, and a strict schema would turn a harmless addition
    into an outage.
    """
    body = body if isinstance(body, Mapping) else {}

    def count(value: Any) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None

    raw_items = body.get("items")
    items = [
        item
        for item in (raw_items if isinstance(raw_items, list) else [])
        if isinstance(item, Mapping) and _text(item.get("hash_id"))
    ]
    return {
        "total": count(body.get("total")),
        "page": count(body.get("page")),
        "page_size": count(body.get("page_size")),
        "items": items,
    }


def map_facet_options(body: Any) -> list[dict[str, Any]]:
    """`{options:[{value,label,count}]}` -> the `{hash_id,name,count}` taxonomy DTO.

    A malformed body yields ``[]``, but callers must distinguish that from a
    *failed* call: an empty list is a claim that upstream has zero options, and
    caching that claim freezes an empty dropdown for the whole TTL.
    """
    options = body.get("options") if isinstance(body, Mapping) else None
    if not isinstance(options, list):
        return []
    mapped: list[dict[str, Any]] = []
    for option in options:
        if not isinstance(option, Mapping):
            continue
        value = _text(option.get("value"))
        if not value:
            continue
        mapped.append(
            {
                "hash_id": value,
                "value": value,
                "name": _text(option.get("label")) or value,
                "label": _text(option.get("label")) or value,
                "count": _int(option.get("count")) or 0,
            }
        )
    return mapped


def map_detail(raw: Mapping[str, Any]) -> dict[str, Any]:
    """dbauto `/car` -> the `data` block of our `/cars/{id}` response.

    dbauto nests auction fields under `auction`; our contract flattens them to the
    top level, which is what `HeyDealerCarWithTechSheet` reads.
    """
    auction = raw.get("auction")
    auction = auction if isinstance(auction, Mapping) else {}
    desired_price = _int(auction.get("desired_price"))
    if desired_price is None:
        desired_price = _int(raw.get("desired_price"))

    detail: dict[str, Any] = {
        "hash_id": _text(raw.get("hash_id")) or "",
        "status": _text(raw.get("status")),
        "status_display": _text(raw.get("status_display")),
        "full_name": _text(raw.get("full_name")),
        "full_name_without_brand": _text(raw.get("full_name_without_brand")),
        "model_part_name": _text(raw.get("model_part_name")),
        "grade_part_name": _text(raw.get("grade_part_name")),
        "brand_name": _text(raw.get("brand_name")),
        "brand_image_url": _text(raw.get("brand_image_url")),
        "main_image_url": _text(raw.get("main_image_url")),
        "image_urls": list(raw.get("image_urls") or []),
        "image_groups": list(raw.get("image_groups") or []),
        "car_number": _text(raw.get("car_number")),
        "year": _int(raw.get("year")),
        "initial_registration_date": _text(raw.get("initial_registration_date")),
        "mileage": _int(raw.get("mileage")),
        "color": _text(raw.get("color")),
        "interior": _text(raw.get("interior")),
        "color_info": raw.get("color_info"),
        "interior_info": raw.get("interior_info"),
        "location": _text(raw.get("location")),
        "short_location": _text(raw.get("short_location")),
        "payment": _text(raw.get("payment")),
        "payment_display": _text(raw.get("payment_display")),
        "fuel": _text(raw.get("fuel")),
        "fuel_display": _text(raw.get("fuel_display")),
        "transmission": _text(raw.get("transmission")),
        "transmission_display": _text(raw.get("transmission_display")),
        "accident": _text(raw.get("accident_repairs_summary")),
        "accident_display": _text(raw.get("accident_repairs_summary_display")),
        "accident_repairs_summary": _text(raw.get("accident_repairs_summary")),
        "accident_repairs_summary_display": _text(
            raw.get("accident_repairs_summary_display")
        ),
        "condition_data": _condition_data(raw),
        "condition_description": _text(raw.get("condition_description")),
        "inspected_condition": raw.get("inspected_condition"),
        "is_advanced_options": bool(raw.get("advanced_options")),
        "advanced_options": list(raw.get("advanced_options") or []),
        "description": _text(raw.get("car_description")),
        "car_description": _text(raw.get("car_description")),
        "customer_comment": _text(raw.get("customer_comment")),
        "inspector_comment": _text(raw.get("inspector_comment")),
        "comment": _text(raw.get("inspector_comment")),
        "paint_thickness_inspection": raw.get("paint_thickness_inspection"),
        "refined_inspector_comment_items": _inspector_items(raw),
        "engine_sound_video": raw.get("engine_sound_video"),
        "carhistory": raw.get("carhistory"),
        "carhistory_summary": _carhistory_summary(raw.get("carhistory")),
        "vehicle_information": raw.get("vehicle_information"),
        # auction, flattened
        "auction_type": _text(auction.get("auction_type")),
        "visits_count": _int(auction.get("visits_count")),
        "approved_at": _text(auction.get("approved_at")),
        "end_at": _text(auction.get("end_at")),
        "bids_count": _int(auction.get("bids_count")),
        "max_bids_count": _int(auction.get("max_bids_count")),
        "desired_price": desired_price,
        "highest_bid": _bid_manwon(auction.get("highest_bid")),
        "is_starred": bool(auction.get("is_starred")),
        "category": _text(auction.get("category")),
        "zero_auction_message": _text(auction.get("zero_auction_message")),
        "previous_auction_result": auction.get("previous_auction_result"),
        "is_pre_inspected": bool(raw.get("is_pre_inspected")),
        "zero_type": _text(raw.get("zero_type")),
        "standard_new_car_price": _int(raw.get("standard_new_car_price")),
        "encar_url": _text(raw.get("encar_url")),
        "tags": _tag_texts(raw.get("tags")),
    }
    return detail


def _condition_data(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """Build the UI's `{basic:[], extra:[]}` block from dbauto's `condition_items`.

    dbauto ships pre-rendered display lines (`{"text": "· Body Panel : None"}`) with
    heading rows wrapped in parentheses. The UI's `ConditionItem` wants a `type` to
    pick an icon, so headings become `type: "heading"` and the rest `type: "item"`.
    """
    existing = raw.get("condition_data")
    if isinstance(existing, Mapping) and (existing.get("basic") or existing.get("extra")):
        return dict(existing)

    items = raw.get("condition_items")
    if not isinstance(items, list) or not items:
        return None

    basic: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        text = _text(item.get("text"))
        if not text:
            continue
        is_heading = text.startswith("(") and text.endswith(")")
        basic.append(
            {
                "label": None,
                "text": text.strip("()") if is_heading else text,
                "type": "heading" if is_heading else "item",
                "info_text": _text(item.get("tooltip")),
            }
        )
    return {"basic": basic, "extra": []} if basic else None


def _inspector_items(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten dbauto's `inspector_sections` into the UI's comment-item list."""
    sections = raw.get("inspector_sections")
    if not isinstance(sections, list):
        return []
    items: list[dict[str, Any]] = []
    for section in sections:
        if not isinstance(section, Mapping):
            continue
        title = _text(section.get("title"))
        for entry in section.get("items") or []:
            text = _text(entry.get("text")) if isinstance(entry, Mapping) else _text(entry)
            if text:
                items.append({"title": title, "text": text})
    return items


def _carhistory_summary(carhistory: Any) -> dict[str, Any] | None:
    """Derive the summary block the UI reads from the full carhistory record.

    Counts use a nullable coercion on purpose: dbauto omits a count it has not been
    told, and rendering that as 0 would turn "not reported" into "spotless".
    """
    if not isinstance(carhistory, Mapping):
        return None
    return {
        "owner_changed_count": _int(carhistory.get("owner_changed_count")),
        "my_car_accident_count": _int(carhistory.get("my_car_accident_count")),
        "other_car_accident_count": _int(carhistory.get("other_car_accident_count")),
        "my_car_accident_cost": _int(carhistory.get("my_car_accident_cost")),
        "other_car_accident_cost": _int(carhistory.get("other_car_accident_cost")),
        "loss_count": _int(carhistory.get("total_loss_count")),
        "flooded_count": _int(carhistory.get("flooded_count")),
        "stolen_count": _int(carhistory.get("stolen_count")),
        "use_record_count": _int(carhistory.get("use_record_count")),
    }


def build_diagram(
    atlas: Iterable[Mapping[str, Any]],
    car_repairs: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Join the static geometry atlas with one car's actual repairs.

    dbauto splits this across two payloads: `/accident_repairs` carries the part
    coordinates and view images but reports every status as "none" (it is the same
    for every car), while the car's real per-part statuses live on the detail with
    no coordinates at all. Neither is usable alone; the join is where the diagram
    actually comes from.

    Returns the 4-view shape under `views`, and mirrors the primary view onto the
    legacy top-level keys so an older client keeps rendering.
    """
    status_by_part: dict[str, Mapping[str, Any]] = {}
    for repair in car_repairs or []:
        if not isinstance(repair, Mapping):
            continue
        part = _text(repair.get("part"))
        if part:
            status_by_part[part] = repair

    views: list[dict[str, Any]] = []
    summary = {"exchange": 0, "weld": 0, "painted": 0, "none": 0}

    for view in atlas or []:
        if not isinstance(view, Mapping):
            continue
        repairs: list[dict[str, Any]] = []
        for part_geometry in view.get("accident_repairs") or []:
            if not isinstance(part_geometry, Mapping):
                continue
            part = _text(part_geometry.get("part"))
            if not part:
                continue
            actual = status_by_part.get(part)
            repair_code = _text(actual.get("repair")) if actual else "none"
            repair_code = repair_code or "none"
            repair_display = (
                _text(actual.get("repair_display")) if actual else None
            ) or _text(part_geometry.get("repair_display"))

            summary[repair_code] = summary.get(repair_code, 0) + 1
            repairs.append(
                {
                    "part": part,
                    "part_display": (
                        (_text(actual.get("part_display")) if actual else None)
                        or _text(part_geometry.get("part_display"))
                    ),
                    "repair": repair_code,
                    "repair_display": repair_display,
                    "position": list(part_geometry.get("position") or []),
                    "category": _text(part_geometry.get("category")),
                    "max_reduction_ratio": part_geometry.get("max_reduction_ratio"),
                    # Computed here and only here: a stale label from an older
                    # capture must never reach the client.
                    "label": repair_mark(repair_code),
                }
            )

        views.append(
            {
                "type": _text(view.get("type")),
                "image_url": _text(view.get("image_url")),
                "image_width": _int(view.get("image_width")),
                "accident_repairs": repairs,
            }
        )

    order = {name: index for index, name in enumerate(ATLAS_VIEW_ORDER)}
    views.sort(key=lambda view: order.get(view.get("type") or "", len(order)))

    primary = views[0] if views else {}
    total_damages = sum(
        count for code, count in summary.items() if code != "none"
    )
    return {
        "views": views,
        "type": primary.get("type"),
        "image_url": primary.get("image_url"),
        "image_width": primary.get("image_width"),
        "accident_repairs": primary.get("accident_repairs", []),
        "total_damages": total_damages,
        "damage_summary": summary,
    }
