from pydantic import BaseModel, Field
from typing import Optional


class ExchangeRates(BaseModel):
    """Live exchange rates from Naver"""
    usd_krw: float = Field(..., description="USD to KRW rate (minus 10 points)")
    eur_krw: float = Field(..., description="EUR to KRW rate (minus 10 points)")
    fetched_at: str = Field(..., description="ISO timestamp when rates were fetched")


class ExchangeRateResponse(BaseModel):
    """API response wrapper for exchange rates"""
    success: bool = Field(..., description="Whether the fetch was successful")
    data: Optional[ExchangeRates] = Field(None, description="Exchange rate data")
    message: Optional[str] = Field(None, description="Error message if failed")
