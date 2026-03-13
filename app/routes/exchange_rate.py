from fastapi import APIRouter, Query
from loguru import logger

from app.models.exchange_rate import ExchangeRateResponse, ExchangeRates
from app.services.exchange_rate_service import exchange_rate_service

router = APIRouter(tags=["Exchange Rates"])


@router.get("/rates", response_model=ExchangeRateResponse)
async def get_exchange_rates(
    cache: bool = Query(True, description="Set to false to bypass cache"),
) -> ExchangeRateResponse:
    """
    Get live USD/KRW and EUR/KRW exchange rates from Naver.

    Rates are cached for 30 minutes. Each rate has 10 points subtracted.
    """
    try:
        data = exchange_rate_service.get_rates(bypass_cache=not cache)
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
