from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class MileageInfo(BaseModel):
    value: int
    unit_code: str = Field(default="KMT", description="Unit code for mileage (KMT = kilometers)")


class PLCAuctionCar(BaseModel):
    entry_number: Optional[str] = Field(None, description="Auction lot number")
    car_name: str = Field(..., description="Full car name (brand + model)")
    brand: str = Field(..., description="Car manufacturer")
    model: str = Field(..., description="Car model")
    year: int = Field(..., alias="productionDate", description="Manufacturing year")
    transmission: str = Field(default="Automatic", alias="vehicleTransmission", description="Transmission type")
    fuel_type: str = Field(..., alias="fuelType", description="Fuel type")
    engine_volume: Optional[str] = Field(None, description="Engine volume")
    mileage: str = Field(..., description="Mileage with unit (e.g. '10,091 Km')")
    mileage_info: Optional[MileageInfo] = Field(None, alias="mileageFromOdometer")
    condition_grade: Optional[str] = Field(None, description="Car condition grade")
    starting_price: float = Field(..., alias="price", description="Starting price")
    currency: str = Field(default="USD", alias="priceCurrency", description="Price currency")
    main_image_url: str = Field(..., alias="image", description="Main image URL")
    detail_url: Optional[str] = Field(None, description="Link to detail page")
    car_no: Optional[str] = Field(None, description="Car number for detail lookup")
    location: Optional[str] = Field(None, description="Auction location")
    color: Optional[str] = Field(None, description="Car color")
    
    class Config:
        populate_by_name = True


class PLCAuctionOffer(BaseModel):
    type: str = Field(alias="@type", default="Offer")
    price: float
    price_currency: str = Field(alias="priceCurrency", default="USD")
    item_offered: PLCAuctionCar = Field(alias="itemOffered")
    
    class Config:
        populate_by_name = True


class PLCAuctionAggregateOffer(BaseModel):
    type: str = Field(alias="@type", default="AggregateOffer")
    price_currency: str = Field(alias="priceCurrency", default="USD")
    low_price: float = Field(alias="lowPrice")
    high_price: float = Field(alias="highPrice")
    offer_count: int = Field(alias="offerCount")
    offers: List[PLCAuctionOffer]
    
    class Config:
        populate_by_name = True


class PLCAuctionProduct(BaseModel):
    context: str = Field(alias="@context", default="http://schema.org/")
    type: str = Field(alias="@type", default="Product")
    name: str
    offers: PLCAuctionAggregateOffer
    
    class Config:
        populate_by_name = True


class PLCAuctionFilters(BaseModel):
    page: int = Field(default=1, description="Page number")
    page_size: int = Field(default=20, description="Items per page")
    country: str = Field(default="kr", description="Country code")
    date: Optional[str] = Field(None, description="Auction date timestamp")
    price_type: str = Field(default="auction", description="Price type")
    manufacturer: Optional[str] = Field(None, description="Car manufacturer filter")
    model: Optional[str] = Field(None, description="Car model filter")
    fuel: Optional[str] = Field(None, description="Fuel type filter")
    color: Optional[str] = Field(None, description="Color filter")
    year_from: Optional[int] = Field(None, description="Year from filter")
    year_to: Optional[int] = Field(None, description="Year to filter")
    price_from: Optional[float] = Field(None, description="Price from filter")
    price_to: Optional[float] = Field(None, description="Price to filter")
    transmission: Optional[str] = Field(None, description="Transmission type filter")
    mileage_from: Optional[int] = Field(None, description="Mileage from filter")
    mileage_to: Optional[int] = Field(None, description="Mileage to filter")


class PLCAuctionResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    total_count: int
    cars: List[PLCAuctionCar]
    current_page: int
    page_size: int
    has_next_page: bool
    has_prev_page: bool
    source: str = "plc_auction"
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    
class PLCAuctionManufacturer(BaseModel):
    code: str
    name: str
    count: int = 0
    

class PLCAuctionModel(BaseModel):
    code: str
    name: str
    manufacturer_code: str
    count: int = 0