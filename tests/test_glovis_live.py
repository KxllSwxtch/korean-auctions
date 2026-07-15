import os

import pytest

from app.models.glovis import GlovisCarsQuery
from app.services.glovis_service import GlovisService


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_GLOVIS_LIVE") != "1",
    reason="set RUN_GLOVIS_LIVE=1 to call DB Auto through configured KR proxy",
)


def test_live_auctions_list_and_detail_are_semantically_valid():
    service = GlovisService()
    auctions = service.get_auctions().auctions
    assert auctions
    auction = auctions[0]
    cars = service.get_cars(
        GlovisCarsQuery(
            atn=auction.number,
            acc=auction.acc,
            page=1,
            page_size=1,
        )
    )
    assert cars.total >= len(cars.items)
    if cars.items:
        car = cars.items[0]
        detail = service.get_car_detail(
            gn=car.gn, rc=car.rc, acc=car.acc, atn=car.atn
        )
        assert detail.data.main.gn == car.gn
        assert detail.data.main.title.strip()
