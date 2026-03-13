from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class HappyCarSaleType(str, Enum):
    ALL = ""
    SALVAGE = "구제"
    SCRAP = "폐차"
    PARTS = "부품"


class HappyCarDamageType(str, Enum):
    TOTAL_LOSS = "전손"
    PARTIAL = "분손"
    NONE = ""


class HappyCarListItem(BaseModel):
    """Single car listing from HappyCar insurance auction"""
    idx: str = Field(..., description="Internal ID from href idx parameter")
    title: str = Field(..., description="Car name/title")
    registration_number: str = Field(default="", description="Registration number e.g. 2026-026094")
    sale_type: str = Field(default="", description="Sale type: 폐차, 구제, 부품")
    damage_type: Optional[str] = Field(None, description="Damage type: 전손, 분손, or None")
    year: Optional[str] = Field(None, description="Manufacturing year e.g. 2014년 9월")
    fuel: Optional[str] = Field(None, description="Fuel type e.g. LPG")
    transmission: Optional[str] = Field(None, description="Transmission e.g. 오토")
    displacement: Optional[str] = Field(None, description="Engine displacement e.g. 1,999cc")
    mileage: Optional[str] = Field(None, description="Mileage e.g. 270,324km or -")
    deadline: Optional[str] = Field(None, description="Auction deadline e.g. 2026-03-13 09시 00분")
    min_bid: Optional[str] = Field(None, description="Minimum bid e.g. 200,000원 or -")
    location: Optional[str] = Field(None, description="Vehicle location e.g. 충북 청주시")
    image_url: Optional[str] = Field(None, description="Full URL to car image")
    detail_url: Optional[str] = Field(None, description="Full URL to detail page")

    class Config:
        json_schema_extra = {
            "example": {
                "idx": "881525",
                "title": "쏘나타 뉴 라이즈",
                "registration_number": "2026-026094",
                "sale_type": "구제",
                "damage_type": "전손",
                "year": "2014년 9월",
                "fuel": "LPG",
                "transmission": "오토",
                "displacement": "1,999cc",
                "mileage": "270,324km",
                "deadline": "2026-03-13 09시 00분",
                "min_bid": "200,000원",
                "location": "충북 청주시",
                "image_url": "https://www.happycarservice.com/upload/auction_ins/881525/thumb_1.jpg",
                "detail_url": "https://www.happycarservice.com/content/ins_view.html?idx=881525",
            }
        }


class HappyCarModelCategory(BaseModel):
    """Model category with count from sidebar filter"""
    name: str = Field(..., description="Model category name e.g. 쏘나타")
    count: int = Field(default=0, description="Number of listings in this category")
    search_key: str = Field(default="", description="Value to pass as model filter")


class HappyCarDetail(BaseModel):
    """Detailed car information from HappyCar detail page"""
    idx: str = Field(..., description="Internal ID")
    title: str = Field(default="", description="Car name/title")
    registration_number: str = Field(default="", description="Registration number")
    sale_type: str = Field(default="", description="Sale type")
    # Specs
    year: Optional[str] = Field(None, description="Manufacturing year")
    transmission: Optional[str] = Field(None, description="Transmission type")
    fuel: Optional[str] = Field(None, description="Fuel type")
    displacement: Optional[str] = Field(None, description="Engine displacement")
    mileage: Optional[str] = Field(None, description="Mileage")
    min_bid: Optional[str] = Field(None, description="Minimum bid amount")
    location: Optional[str] = Field(None, description="Vehicle location")
    deadline: Optional[str] = Field(None, description="Auction deadline")
    cost_processing: Optional[str] = Field(None, description="Cost processing info (발생비용처리)")
    # Damage info
    damage_description: Optional[str] = Field(None, description="Full damage description text")
    # Vehicle info
    car_name_full: Optional[str] = Field(None, description="Full car name")
    msrp: Optional[str] = Field(None, description="Original MSRP")
    vin: Optional[str] = Field(None, description="Vehicle identification number")
    form_number: Optional[str] = Field(None, description="Form/registration number")
    form_year: Optional[str] = Field(None, description="Form year")
    first_registration: Optional[str] = Field(None, description="First registration date")
    color: Optional[str] = Field(None, description="Vehicle color")
    actual_mileage: Optional[str] = Field(None, description="Actual mileage reading")
    inspection_validity: Optional[str] = Field(None, description="Inspection validity date")
    # Insurance history
    plate_changes: Optional[str] = Field(None, description="Number of plate changes")
    owner_changes: Optional[str] = Field(None, description="Number of owner changes")
    my_damage: Optional[str] = Field(None, description="My damage claims amount")
    other_damage: Optional[str] = Field(None, description="Other party damage claims amount")
    # Images
    images: List[str] = Field(default_factory=list, description="List of image URLs")

    class Config:
        json_schema_extra = {
            "example": {
                "idx": "881525",
                "title": "쏘나타 뉴 라이즈",
                "registration_number": "2026-026094",
                "sale_type": "구제",
                "year": "2014년 9월",
                "fuel": "LPG",
                "transmission": "오토",
                "displacement": "1,999cc",
                "mileage": "270,324km",
                "min_bid": "200,000원",
                "location": "충북 청주시",
                "deadline": "2026-03-13 09시 00분",
                "damage_description": "전손 - 차량 전면부 파손",
                "car_name_full": "현대 쏘나타 뉴 라이즈 LPi 프리미엄",
                "vin": "KMHE341DBFA123456",
                "color": "흰색",
                "images": [
                    "https://www.happycarservice.com/upload/auction_ins/881525/1.jpg",
                    "https://www.happycarservice.com/upload/auction_ins/881525/2.jpg",
                ],
            }
        }


class HappyCarResponse(BaseModel):
    """Response model for HappyCar car list endpoint"""
    success: bool
    data: List[HappyCarListItem] = Field(default_factory=list)
    total_count: int = 0
    page: int = 1
    page_size: int = 12
    model_categories: List[HappyCarModelCategory] = Field(default_factory=list)
    message: Optional[str] = None
    parsed_at: datetime = Field(default_factory=datetime.now)


class HappyCarDetailResponse(BaseModel):
    """Response model for HappyCar car detail endpoint"""
    success: bool
    data: Optional[HappyCarDetail] = None
    message: Optional[str] = None
    parsed_at: datetime = Field(default_factory=datetime.now)


class HappyCarHealthResponse(BaseModel):
    """Health check response"""
    success: bool
    message: str
    service: str = "HappyCar Insurance Auction"
    status: str = "active"
    base_url: str = "https://www.happycarservice.com"
