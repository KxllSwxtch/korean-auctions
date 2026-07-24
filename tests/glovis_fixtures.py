from __future__ import annotations

from base64 import b64encode
from copy import deepcopy

GN_RAW = "mJDbMQgcohK+3EAebGNDAg=="
GN_PATH = "mJDbMQgcohK-3EAebGNDAg~~"


def raw_auctions() -> list[dict[str, object]]:
    return [
        {"atn": "1102", "acc": "20", "title": "Glovis July A", "date": "2026-07-16"},
        {"atn": "1103", "acc": "20", "title": "Glovis July B", "date": "2026-07-18"},
    ]


def valid_list_car() -> dict[str, object]:
    return {
        "gn": GN_RAW,
        "rc": "3100",
        "acc": "20",
        "atn": "1102",
        "title": "[ Chevrolet ] IMPALA 2.5 LT",
        "lot_number": "1001",
        "thumbnail": "https://img-auction.autobell.co.kr/example-list.jpg",
        "room": "Yangsan",
        "lane": "A",
        "plate_number": "TEST-1001",
        "year": 2016,
        "mileage": 193_512,
        "displacement": 2_457,
        "start_price": 1_600_000,
        "fuel_type": "Gasoline",
        "transmission": "A/T",
        "color": "Gray",
        "rating": "A/1",
        "brand_code": "1",
        "brand": "Chevrolet",
        "model_code": "26",
        "model": "Impala",
        "submodel_code": "1568",
        "submodel": "Impala",
        "configuration": "2.5 LT",
        "status": None,
    }


def valid_list(total: int = 1) -> dict[str, object]:
    return {"total": total, "items": [valid_list_car()] if total else []}


def lot_scan_page(lots: list[int], total: int) -> dict[str, object]:
    """Build a cars page whose items carry the given lot numbers."""
    items: list[dict[str, object]] = []
    for lot in lots:
        car = valid_list_car()
        car["gn"] = b64encode(f"glovis-lot-{lot:08d}".encode()).decode("ascii")
        car["rc"] = str(3000 + lot)
        car["lot_number"] = str(lot)
        car["plate_number"] = f"TEST-{lot}"
        items.append(car)
    return {"total": total, "items": items}


def valid_filter_items() -> list[dict[str, object]]:
    return [{"value": "146", "label": "Genesis", "count": 72}]


def valid_search_form() -> dict[str, object]:
    item = {"value": "sample", "label": "Sample", "count": 1}
    return {
        "colors": [dict(item, value="White", label="White")],
        "options": [dict(item, value="navigation", label="Navigation")],
        "lanes": [dict(item, value="A", label="A")],
        "transmissions": [dict(item, value="A/T", label="A/T")],
        "fuels": [dict(item, value="Gasoline", label="Gasoline")],
        "insurance_damage": [dict(item, value="none", label="None")],
        "usage_history": [dict(item, value="rental", label="Rental")],
        "accident_history": [dict(item, value="none", label="None")],
        "sort_orders": [dict(item, value="01", label="Lot number")],
        "rooms": [dict(item, value="Yangsan", label="Yangsan")],
        "bid_statuses": [dict(item, value="open", label="Open")],
    }


def valid_detail() -> dict[str, object]:
    return {
        "main": {
            **valid_list_car(),
            "vin": "SYNTHETICVIN00001",
            "vehicle_type": "Personal/Passenger",
            "first_registration_date": "2015-10-30",
            "registration_date": None,
            "sold_price": None,
            "hope_price": None,
            "auction_start_time": None,
            "absentee_bid_start_time": None,
            "rating": {"frame": "None"},
        },
        "properties": {
            "product_type": "Own Company",
            "seating_capacity": "5-seater",
            "usage_type": "Personal/Corporate",
            "engine_model": "LCV",
            "storage_items": "None",
            "inspection_date": "Not Checked",
            "lot_position": "C38",
            "documents_complete": "Synthetic registration packet",
            "documents_missing": "-",
            "future_property": "kept",
        },
        "performance": {
            "engine": "Maintenance required",
            "brakes": "Normal",
            "steering": "Normal",
            "electrical": "Good",
            "Shifting": "Maintenance required",
            "hvac": "Normal",
            "power": "Normal",
            "interior": "Normal",
            "lighting": "Good",
            "Remarks": "-",
            "Changes": "-",
        },
        "total_table": {"future_total": 17},
        "summary_table": {"future_summary": "visible"},
        "options": [
            {"name": "Navigation", "enabled": True},
            {"name": "Sunroof", "enabled": False},
        ],
        "legal_status": {"seizures": 0, "mortgages": 0},
        "insurance_history": {
            "special_accidents": {
                "total_loss": 0,
                "theft": 0,
                "flood_total": 0,
                "flood_partial": 0,
            },
            "plate_changes": 0,
            "owner_changes": 1,
            "commercial_history": 0,
        },
        "accident_records": [
            {
                "date": "2025.07.20",
                "status": "Confirmed",
                "type": "Own insurance",
                "parts_cost": 10,
                "labor_cost": 20,
                "paint_cost": 30,
                "repair_cost": 60,
                "insurance_paid": 50,
            }
        ],
        "inspection_record": {
            "vehicle": {"usage": "Personal/Corporate", "engine_type": "LCV"},
            "future_inspection": {"value": "kept"},
        },
        "images": ["https://img-auction.autobell.co.kr/example-main.jpg"],
        "inspection_images": ["https://img-auction.autobell.co.kr/example-inspection.jpg"],
        "performance_image": "https://auction.autobell.co.kr/example-performance.jpg",
        "registration_certificate_image": "https://auction.autobell.co.kr/example-certificate.jpg",
        "remarks": "Synthetic provider remark",
    }


def placeholder_detail() -> dict[str, object]:
    payload = deepcopy(valid_detail())
    payload["main"] = {
        "gn": GN_RAW,
        "rc": "3100",
        "acc": "20",
        "atn": "1102",
        "title": "",
    }
    payload["images"] = []
    payload["performance_image"] = None
    payload["registration_certificate_image"] = None
    return payload
