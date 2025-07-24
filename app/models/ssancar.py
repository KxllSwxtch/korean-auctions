from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class SSANCARCar(BaseModel):
    """Model for SSANCAR car listing"""
    car_no: str = Field(..., description="Unique car number")
    stock_no: str = Field(..., description="Stock number with auction type (A/B)")
    manufacturer: str = Field(..., description="Car manufacturer")
    model: str = Field(..., description="Car model")
    full_name: str = Field(..., description="Full car name")
    year: int = Field(..., description="Manufacturing year")
    mileage: Optional[int] = Field(None, description="Mileage in km")
    mileage_formatted: str = Field(..., description="Formatted mileage string")
    fuel: str = Field(..., description="Fuel type")
    transmission: str = Field(..., description="Transmission type")
    grade: str = Field(..., description="Car grade (A1-D2)")
    bid_price: int = Field(..., description="Starting bid price in USD")
    thumbnail_url: str = Field(..., description="Thumbnail image URL")
    detail_url: str = Field(..., description="Detail page URL")
    
    class Config:
        json_schema_extra = {
            "example": {
                "car_no": "1536311",
                "stock_no": "1001(A)",
                "manufacturer": "BMW",
                "model": "6Series (F12) 650i Convertible",
                "full_name": "BMW 6Series (F12) 650i Convertible",
                "year": 2011,
                "mileage": 114774,
                "mileage_formatted": "114,774km",
                "fuel": "Gasoline",
                "transmission": "Automatic",
                "grade": "A2",
                "bid_price": 8002,
                "thumbnail_url": "https://www.kcarauction.com/auction/IMAGE_UPLOAD/CAR/2032/CA20325265/CA2032526519f23838_370.JPG",
                "detail_url": "https://www.ssancar.com/page/car_view.php?car_no=1536311"
            }
        }


class SSANCARCarDetail(BaseModel):
    """Detailed car information from SSANCAR"""
    car_no: str
    stock_no: str
    manufacturer: str
    model: str
    full_name: str
    year: int
    mileage: Optional[int]
    mileage_formatted: str
    fuel: str
    transmission: str
    grade: str
    color: Optional[str]
    engine_size: Optional[str]
    vin: Optional[str]
    bid_price: int
    buy_now_price: Optional[int]
    auction_date: Optional[datetime]
    auction_status: str  # "upcoming", "active", "ended"
    images: List[str] = Field(default_factory=list)
    inspection_sheet_url: Optional[str]
    features: List[str] = Field(default_factory=list)
    condition_notes: Optional[str]
    
    class Config:
        json_schema_extra = {
            "example": {
                "car_no": "1536311",
                "stock_no": "1001(A)",
                "manufacturer": "BMW",
                "model": "6Series (F12) 650i Convertible",
                "full_name": "BMW 6Series (F12) 650i Convertible",
                "year": 2011,
                "mileage": 114774,
                "mileage_formatted": "114,774km",
                "fuel": "Gasoline",
                "transmission": "Automatic",
                "grade": "A2",
                "color": "Black",
                "engine_size": "4.4L",
                "vin": "WBAYH8C57BG123456",
                "bid_price": 8002,
                "buy_now_price": 12000,
                "auction_date": "2025-01-28T13:00:00",
                "auction_status": "upcoming",
                "images": [
                    "https://www.kcarauction.com/auction/IMAGE_UPLOAD/CAR/2032/CA20325265/CA2032526519f23838_1.JPG",
                    "https://www.kcarauction.com/auction/IMAGE_UPLOAD/CAR/2032/CA20325265/CA2032526519f23838_2.JPG"
                ],
                "inspection_sheet_url": "https://www.ssancar.com/inspection/1536311.pdf",
                "features": ["Sunroof", "Leather seats", "Navigation"],
                "condition_notes": "Minor scratches on front bumper"
            }
        }


class SSANCARManufacturer(BaseModel):
    """Manufacturer model for SSANCAR"""
    code: str = Field(..., description="Manufacturer code in Korean")
    name: str = Field(..., description="Manufacturer name in English")
    korean_name: str = Field(..., description="Manufacturer name in Korean")
    count: Optional[int] = Field(0, description="Number of cars available")
    
    class Config:
        json_schema_extra = {
            "example": {
                "code": "현대",
                "name": "HYUNDAI",
                "korean_name": "현대",
                "count": 150
            }
        }


class SSANCARModel(BaseModel):
    """Car model for SSANCAR"""
    no: str = Field(..., description="Model number")
    name: str = Field(..., description="Model name in Korean")
    e_name: str = Field(..., description="Model name in English")
    manufacturer_code: str = Field(..., description="Manufacturer code")
    
    class Config:
        json_schema_extra = {
            "example": {
                "no": "460",
                "name": "그랜저",
                "e_name": "GRANDEUR",
                "manufacturer_code": "현대"
            }
        }


class SSANCARFilters(BaseModel):
    """Filters for SSANCAR search"""
    weekNo: str = Field("4", description="Week number (2 for Tuesday, 5 for Friday)")
    maker: Optional[str] = Field("", description="Manufacturer in Korean")
    model: Optional[str] = Field("", description="Model code")
    fuel: Optional[str] = Field("", description="Fuel type in Korean")
    color: Optional[str] = Field("", description="Color in Korean")
    yearFrom: str = Field("2000", description="Year from")
    yearTo: str = Field("2025", description="Year to")
    priceFrom: str = Field("0", description="Price from in USD")
    priceTo: str = Field("200000", description="Price to in USD")
    list: str = Field("15", description="Items per page")
    pages: str = Field("0", description="Page number (0-based)")
    no: Optional[str] = Field("", description="Stock number search")


class SSANCARResponse(BaseModel):
    """Response model for SSANCAR API endpoints"""
    success: bool
    message: str
    cars: List[SSANCARCar] = Field(default_factory=list)
    total_count: int = 0
    current_page: int = 1
    page_size: int = 15
    has_next_page: bool = False
    has_prev_page: bool = False
    timestamp: datetime = Field(default_factory=datetime.now)


class SSANCARDetailResponse(BaseModel):
    """Response model for car detail endpoint"""
    success: bool
    message: str
    car_detail: Optional[SSANCARCarDetail] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class SSANCARManufacturersResponse(BaseModel):
    """Response for manufacturers list"""
    success: bool
    message: str
    manufacturers: List[SSANCARManufacturer] = Field(default_factory=list)
    total_count: int = 0
    timestamp: datetime = Field(default_factory=datetime.now)


class SSANCARModelsResponse(BaseModel):
    """Response for models list"""
    success: bool
    message: str
    models: List[SSANCARModel] = Field(default_factory=list)
    total_count: int = 0
    manufacturer_code: str
    timestamp: datetime = Field(default_factory=datetime.now)


class SSANCARHealthResponse(BaseModel):
    """Health check response"""
    success: bool
    message: str
    service: str = "SSANCAR Auction"
    status: str = "active"
    base_url: str = "https://www.ssancar.com"
    timestamp: datetime = Field(default_factory=datetime.now)