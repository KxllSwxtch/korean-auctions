import os

import pytest
from loguru import logger

from app.models.glovis import GlovisCarsQuery
from app.services.glovis_service import GlovisService


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_GLOVIS_LIVE") != "1",
    reason="set RUN_GLOVIS_LIVE=1 to call DB Auto through configured KR proxy",
)


def test_live_auctions_list_and_detail_are_semantically_valid():
    logger.disable("app.services.glovis_transport")
    try:
        service = GlovisService()
        try:
            auctions = service.get_auctions().auctions
            if not auctions:
                pytest.fail("live Glovis auction list was empty", pytrace=False)
            auction = auctions[0]
            filters = service.get_filter_options(
                atn=auction.number,
                acc=auction.acc,
            ).filters
            if not filters.fuels:
                pytest.fail("live Glovis fuel filters were empty", pytrace=False)
            if not filters.sort_orders:
                pytest.fail("live Glovis sort filters were empty", pytrace=False)
            cars = service.get_cars(
                GlovisCarsQuery(
                    atn=auction.number,
                    acc=auction.acc,
                    page=1,
                    page_size=1,
                )
            )
            if cars.total < len(cars.items):
                pytest.fail("live Glovis list total was inconsistent", pytrace=False)
            if not cars.items:
                pytest.fail("live Glovis first page was empty", pytrace=False)
            car = cars.items[0]
            detail = service.get_car_detail(
                gn=car.gn, rc=car.rc, acc=car.acc, atn=car.atn
            )
            if detail is None:
                pytest.fail("live Glovis detail was missing", pytrace=False)
            if detail.data.main.gn != car.gn:
                pytest.fail("live Glovis detail identity did not match", pytrace=False)
            if not detail.data.main.title.strip():
                pytest.fail("live Glovis detail title was blank", pytrace=False)
        finally:
            service.close()
    finally:
        logger.enable("app.services.glovis_transport")
