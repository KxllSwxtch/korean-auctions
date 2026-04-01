from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class AutohubSortOrder(str, Enum):
    """Sort order options"""
    ENTRY = "entry"
    PRICE = "price"
    YEAR = "year"
    MILEAGE = "milg"


class AutohubAuctionResult(str, Enum):
    """Auction result filter"""
    ALL = ""
    SOLD = "Y"
    UNSOLD = "N"
    NOT_HELD = "none"


class AutohubLane(str, Enum):
    """Auction lane filter"""
    ALL = ""
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class AutohubFuelType(str, Enum):
    """Fuel type filter"""
    ALL = ""
    GASOLINE = "01"
    DIESEL = "02"
    LPG = "03"
    HYBRID = "04"
    ELECTRIC = "05"
    OTHER = "06"


# ===== Hierarchical Brand Models =====


class AutohubModelDetailItem(BaseModel):
    """Model detail (generation) from API brands endpoint"""
    modelDetailId: Optional[str] = None
    modelDetailNm: Optional[str] = None
    modelDetailNmEn: Optional[str] = None
    modelDetailCnt: Optional[int] = None


class AutohubModelItem(BaseModel):
    """Model from API brands endpoint"""
    modelId: Optional[str] = None
    modelNm: Optional[str] = None
    modelNmEn: Optional[str] = None
    modelCnt: Optional[int] = None
    modelDetailList: List[AutohubModelDetailItem] = Field(default_factory=list)


class AutohubBrandItem(BaseModel):
    """Brand from API brands endpoint"""
    brandId: Optional[str] = None
    brandNm: Optional[str] = None
    brandNmEn: Optional[str] = None
    brandCnt: Optional[int] = None
    modelList: List[AutohubModelItem] = Field(default_factory=list)


class AutohubBrandsGroup(BaseModel):
    """Brand group (domestic/import) from API brands endpoint"""
    carOrigin: Optional[str] = None
    brandList: List[AutohubBrandItem] = Field(default_factory=list)


class AutohubBrandsResponse(BaseModel):
    """Wraps brands API response"""
    success: bool = True
    data: List[AutohubBrandsGroup] = Field(default_factory=list)
    error: Optional[str] = None


# ===== Search Request =====


class AutohubSearchRequest(BaseModel):
    """Search request with multi-brand arrays"""

    # Multi-select brand/model/detail filters (new API format)
    car_brands: Optional[List[str]] = Field(None, description="Brand IDs")
    car_models: Optional[List[str]] = Field(None, description="Model IDs")
    car_model_details: Optional[List[str]] = Field(None, description="Model detail IDs")

    # Characteristic filters
    fuel_type: Optional[AutohubFuelType] = Field(None, description="Fuel type code")

    # Range filters
    year_from: Optional[int] = Field(None, ge=1990, le=2035)
    year_to: Optional[int] = Field(None, ge=1990, le=2035)
    mileage_from: Optional[int] = Field(None, ge=0)
    mileage_to: Optional[int] = Field(None, ge=0)
    price_from: Optional[int] = Field(None, ge=0, description="Price from (만원)")
    price_to: Optional[int] = Field(None, ge=0, description="Price to (만원)")

    # Status filters
    auction_result: Optional[AutohubAuctionResult] = Field(None)
    lane: Optional[AutohubLane] = Field(None)
    condition_grade: Optional[str] = Field(None, description="Inspection grade filter")

    # Search
    entry_number: Optional[str] = Field(None, description="Entry number search")

    # Sorting and pagination
    sort_order: Optional[AutohubSortOrder] = Field(AutohubSortOrder.ENTRY)
    sort_direction: str = Field("desc", description="Sort direction")
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)

    def to_api_body(self) -> dict:
        """Convert to API POST body for listing endpoint"""
        body: Dict[str, Any] = {
            "tenant": "1",
            "pageSize": self.page_size,
            "pageIndex": self.page,
            "sort": self.sort_direction,
            "sortBy": self.sort_order.value if self.sort_order else "entry",
        }

        if self.car_brands:
            body["carBrand"] = self.car_brands
        if self.car_models:
            body["carModel"] = self.car_models
        if self.car_model_details:
            body["carModelDetail"] = self.car_model_details
        if self.fuel_type and self.fuel_type != AutohubFuelType.ALL:
            body["fuelCode"] = self.fuel_type.value
        if self.year_from is not None:
            body["carYearFrom"] = self.year_from
        if self.year_to is not None:
            body["carYearTo"] = self.year_to
        if self.mileage_from is not None:
            body["mileageFrom"] = self.mileage_from
        if self.mileage_to is not None:
            body["mileageTo"] = self.mileage_to
        if self.price_from is not None:
            body["startAmtFrom"] = self.price_from
        if self.price_to is not None:
            body["startAmtTo"] = self.price_to
        if self.lane and self.lane != AutohubLane.ALL:
            body["aucLaneCode"] = self.lane.value
        if self.condition_grade:
            body["inspGrade"] = self.condition_grade
        # NOTE: entryNo is NOT a supported filter on the external API's paging
        # endpoint — it is silently ignored. Entry number search is handled
        # by server-side post-filtering in AutohubService._search_by_entry_number().

        return body


class AutohubFilterInfo(BaseModel):
    """Available filter options for frontend"""
    fuel_types: List[Dict[str, str]] = Field(default_factory=list)
    lanes: List[Dict[str, str]] = Field(default_factory=list)
    auction_results: List[Dict[str, str]] = Field(default_factory=list)
    year_range: Dict[str, int] = Field(default={"min": 1990, "max": 2026})
    mileage_options: List[int] = Field(default_factory=list)
    price_options: List[int] = Field(default_factory=list)


# Static filter data
AUTOHUB_MILEAGE_OPTIONS = [
    500, 1000, 2000, 3000, 4000, 5000, 10000, 15000, 20000, 25000, 30000,
    35000, 40000, 45000, 50000, 60000, 70000, 80000, 90000, 100000,
    120000, 140000, 160000, 180000, 200000, 250000, 300000
]

AUTOHUB_PRICE_OPTIONS = [
    100, 200, 300, 400, 500, 600, 700, 800, 900, 1000,
    1200, 1400, 1600, 1800, 2000, 2500, 3000, 3500, 4000,
    4500, 5000, 6000, 7000, 8000, 9000, 10000, 12000, 14000,
    16000, 18000, 20000, 30000
]
