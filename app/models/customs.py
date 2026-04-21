"""
Pydantic models for the Russian customs calculator (calcus.ru) proxy.

The Next.js frontend used to call calcus.ru directly via the public CORS proxy
``https://corsproxy.io``, which rate-limits per source IP and returns 403 to
many real users (mobile carriers, large NATs). These schemas describe the
typed contract for our server-to-server replacement at
``POST /api/v1/customs/calculate``.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# Calcus.ru "age" buckets — see ``autobazaapp/components/car/PriceCalculator.tsx``
# (the frontend already computes these values from the registration date).
AgeCategory = Literal["0-3", "3-5", "5-7", "7-0"]

# Calcus.ru engine codes — see ``autobazaapp/lib/utils/fuelTypeMapping.ts``.
# 1 = gasoline, 2 = diesel, 4 = electric, 5 = hybrid, 6 = plug-in hybrid.
EngineCode = Literal["1", "2", "4", "5", "6"]

OwnerType = Literal["1", "2"]


class CustomsCalculationRequest(BaseModel):
    """Inputs accepted by ``POST /api/v1/customs/calculate``."""

    age: AgeCategory = Field(
        ...,
        description="Vehicle age bucket as expected by calcus.ru",
        examples=["0-3"],
    )
    engine: EngineCode = Field(
        ...,
        description="Calcus.ru engine code (1=gasoline, 2=diesel, 4=EV, 5=HEV, 6=PHEV)",
        examples=["1"],
    )
    power_hp: int = Field(
        ...,
        ge=1,
        le=2000,
        description="Engine power in horsepower",
        examples=[160],
    )
    displacement_cc: int = Field(
        ...,
        ge=1,
        le=20000,
        description="Engine displacement in cubic centimeters",
        examples=[1999],
    )
    price_krw: int = Field(
        ...,
        ge=1,
        description="Korean ad price in KRW (already multiplied by 10 000)",
        examples=[365_000_000],
    )
    owner: OwnerType = Field(
        "1",
        description="1 = physical person, 2 = legal entity",
    )


class CustomsCalculationData(BaseModel):
    """The numeric fields the frontend turnkey calculator consumes."""

    tax: float = Field(..., description="Таможенная пошлина (RUB)")
    sbor: float = Field(..., description="Таможенный сбор (RUB)")
    util: float = Field(..., description="Утилизационный сбор (RUB)")
    total: float = Field(..., description="Сумма всех сборов (RUB)")
    total2: str = Field(
        ...,
        description="Полная стоимость авто, formatted as calcus.ru returns it",
    )
    total_car_cost_rub: int = Field(
        ...,
        description="Numeric form of total2 — parsed once on the backend",
    )


class CustomsCalculationResponse(BaseModel):
    """Standard envelope used by every public endpoint in this service."""

    success: bool = True
    data: Optional[CustomsCalculationData] = None
    message: Optional[str] = None
