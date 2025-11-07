from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class EncarPhoto(BaseModel):
    """Photo information for Encar car listing"""
    type: str
    location: str
    updatedDate: str
    ordering: int


class EncarCar(BaseModel):
    """Encar car listing model"""
    Id: str
    Separation: Optional[List[str]] = None
    Trust: Optional[List[str]] = None
    ServiceMark: Optional[List[str]] = None
    Condition: Optional[List[str]] = None
    Photo: Optional[str] = None
    Photos: Optional[List[EncarPhoto]] = None
    Manufacturer: Optional[str] = None
    Model: Optional[str] = None
    Badge: Optional[str] = None
    BadgeDetail: Optional[str] = None
    Transmission: Optional[str] = None
    FuelType: Optional[str] = None
    Year: int
    FormYear: Optional[str] = None
    Mileage: int
    Price: int
    SellType: Optional[str] = None
    BuyType: Optional[List[str]] = None
    ModifiedDate: Optional[str] = None
    OfficeCityState: Optional[str] = None
    OfficeName: Optional[str] = None
    DealerName: Optional[str] = None
    HomeServiceVerification: Optional[str] = None
    ServiceCopyCar: Optional[str] = None
    SalesStatus: Optional[str] = None
    FINISH: Optional[int] = None


class EncarCatalogResponse(BaseModel):
    """Response model for Encar catalog endpoint"""
    Count: int = Field(..., description="Total number of cars matching the query")
    SearchResults: List[EncarCar] = Field(default_factory=list, description="List of cars")
    success: bool = True
    message: Optional[str] = None


class EncarFilterOption(BaseModel):
    """Filter option model"""
    value: str
    label: str
    count: Optional[int] = None


class EncarFiltersResponse(BaseModel):
    """Response model for Encar filters endpoint"""
    success: bool = True
    message: Optional[str] = None
    manufacturers: List[EncarFilterOption] = Field(default_factory=list)
    modelGroups: List[EncarFilterOption] = Field(default_factory=list)
    models: List[EncarFilterOption] = Field(default_factory=list)
    configurations: List[EncarFilterOption] = Field(default_factory=list)
    badges: List[EncarFilterOption] = Field(default_factory=list)
    badgeDetails: List[EncarFilterOption] = Field(default_factory=list)


class EncarError(BaseModel):
    """Error response model"""
    success: bool = False
    message: str
    detail: Optional[str] = None
