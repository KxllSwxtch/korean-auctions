from fastapi import APIRouter, Query
from loguru import logger
import asyncio

from app.models.exchange_rate import ExchangeRateResponse, ExchangeRates
from app.services.exchange_rate_service import exchange_rate_service
from app.core.single_flight import SingleFlight

router = APIRouter(tags=["Exchange Rates"])
_rates_flight = SingleFlight()


@router.get("/rates", response_model=ExchangeRateResponse)
async def get_exchange_rates(
    cache: bool = Query(True, description="Set to false to bypass cache"),
) -> ExchangeRateResponse:
    """
    Get live USD/KRW and EUR/KRW exchange rates from Naver.

    Rates are cached for 15 minutes. Each rate has 10 points subtracted.
    """
    try:
        # Wrap sync call in asyncio.to_thread to avoid blocking event loop,
        # and deduplicate via SingleFlight
        flight_key = f"rates:{cache}"
        data = await _rates_flight.do(
            flight_key,
            lambda: asyncio.to_thread(
                exchange_rate_service.get_rates, bypass_cache=not cache
            ),
        )
        return ExchangeRateResponse(
            success=True,
            data=ExchangeRates(**data),
        )
    except Exception as e:
        logger.error(f"Exchange rate endpoint error: {e}")
        return ExchangeRateResponse(
            success=False,
            message=f"Failed to fetch exchange rates: {str(e)}",
        )
