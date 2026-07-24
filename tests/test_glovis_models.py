from pydantic import ValidationError
import pytest

from app.models.glovis import (
    GlovisCarDetailResponse,
    GlovisCarsQuery,
    GlovisCarsResponse,
)


def test_query_serializes_repeated_filters_without_losing_order():
    query = GlovisCarsQuery(
        atn="1102",
        acc="20",
        page=2,
        page_size=15,
        brand="146",
        model="1171",
        submodel="2852",
        usage_history=["rental", "commercial"],
        options=["navigation", "sunroof"],
        sort_order="01",
    )

    assert query.upstream_params() == [
        ("atn", "1102"),
        ("acc", "20"),
        ("page", "2"),
        ("page_size", "15"),
        ("lang", "en"),
        ("brand", "146"),
        ("model", "1171"),
        ("submodel", "2852"),
        ("options", "navigation"),
        ("options", "sunroof"),
        ("usage_history", "rental"),
        ("usage_history", "commercial"),
        ("sort_order", "01"),
    ]


@pytest.mark.parametrize("value", ["12a4", "", "1234567", " 1234", "-1"])
def test_query_rejects_malformed_lot_numbers(value):
    with pytest.raises(ValidationError):
        GlovisCarsQuery(atn="1102", acc="20", lot_number=value)


def test_lot_number_is_never_forwarded_upstream():
    query = GlovisCarsQuery(atn="1102", acc="20", lot_number="1004")

    assert query.lot_number == "1004"
    assert query.upstream_params() == [
        ("atn", "1102"),
        ("acc", "20"),
        ("page", "1"),
        ("page_size", "15"),
        ("lang", "en"),
        ("sort_order", "01"),
    ]


def test_list_response_uses_exact_provider_total_for_next_page():
    response = GlovisCarsResponse(
        total=31,
        items=[],
        page=2,
        page_size=15,
        atn="1102",
        acc="20",
    )
    assert response.success is True
    assert response.has_next_page is True


def test_detail_preserves_unknown_future_section_keys():
    response = GlovisCarDetailResponse.model_validate(
        {
            "data": {
                "main": {
                    "gn": "mJDbMQgcohK+3EAebGNDAg==",
                    "rc": "3100",
                    "acc": "20",
                    "atn": "1102",
                    "title": "[ Chevrolet ] IMPALA 2.5 LT",
                    "start_price": 1_600_000,
                },
                "properties": {"lot_position": "C38", "future_property": "kept"},
                "performance": {"engine": "Maintenance required"},
                "total_table": {"future_total": 17},
                "summary_table": {},
                "options": [{"name": "Navigation", "enabled": True}],
                "legal_status": {"seizures": 0, "mortgages": 0},
                "insurance_history": {
                    "special_accidents": {"total_loss": 0, "theft": 0},
                    "owner_changes": 1,
                },
                "accident_records": [],
                "inspection_record": {"vehicle": {"engine_type": "LCV"}},
                "images": ["https://img-auction.autobell.co.kr/example.jpg"],
                "inspection_images": [],
            }
        }
    )

    dumped = response.model_dump()
    assert dumped["data"]["properties"]["future_property"] == "kept"
    assert dumped["data"]["total_table"]["future_total"] == 17


def test_query_rejects_invalid_ranges_and_page_size():
    with pytest.raises(ValidationError):
        GlovisCarsQuery(
            atn="1102",
            acc="20",
            page=1,
            page_size=61,
            year_from=2024,
            year_to=2020,
        )
