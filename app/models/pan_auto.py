"""
Pydantic models for Pan-Auto.ru API responses
Used for fetching HP (horsepower) and customs costs data
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class PanAutoCostsRUB(BaseModel):
    """Russian customs costs from Pan-Auto.ru"""
    carPriceEncar: Optional[float] = None
    carPrice: Optional[float] = None
    clearanceCost: Optional[float] = Field(None, description="Таможенный сбор")
    utilizationFee: Optional[float] = Field(None, description="Утилизационный сбор")
    customsDuty: Optional[float] = Field(None, description="Таможенная пошлина")
    deliveryRate: Optional[float] = None
    deliveryCost: Optional[float] = None
    vladivostokServices: Optional[float] = None
    totalFees: Optional[float] = None
    finalCost: Optional[float] = None
    pizdec: Optional[float] = None
    pizdecTotal: Optional[float] = None
    dealerCost: Optional[float] = None


class PanAutoCosts(BaseModel):
    """Costs breakdown by currency"""
    RUB: Optional[PanAutoCostsRUB] = None
    USD: Optional[Dict[str, Any]] = None
    KRW: Optional[Dict[str, Any]] = None


class PanAutoCarDetail(BaseModel):
    """Car detail data from Pan-Auto.ru"""
    id: Optional[str] = None
    hp: Optional[int] = Field(None, description="Horsepower")
    ckw: Optional[float] = Field(None, description="Power in kW")
    costs: Optional[PanAutoCosts] = None
    # Additional fields that may be present
    title: Optional[str] = None
    price: Optional[int] = None
    year: Optional[int] = None
    mileage: Optional[int] = None
    displacement: Optional[int] = None


class PanAutoCarDetailResponse(BaseModel):
    """Response model for Pan-Auto car detail endpoint"""
    success: bool = True
    data: Optional[PanAutoCarDetail] = None
    message: Optional[str] = None


class PanAutoError(BaseModel):
    """Error response model"""
    success: bool = False
    message: str
    detail: Optional[str] = None
