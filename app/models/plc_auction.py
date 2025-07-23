from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class MileageInfo(BaseModel):
    value: int
    unit_code: str = Field(default="KMT", description="Unit code for mileage (KMT = kilometers)")


class PLCAuctionCar(BaseModel):
    """Car data from PLC Auction API response"""
    id: str = Field(..., description="Car hash ID")
    slug: str = Field(..., description="URL slug for car detail")
    url: str = Field(..., description="Full URL to car detail page")
    title: str = Field(..., description="Car title (brand + model)")
    manufacturer: str = Field(..., description="Car manufacturer")
    model: str = Field(..., description="Car model")
    year: int = Field(..., description="Manufacturing year")
    price: float = Field(..., description="Current bid price")
    price_formatted: str = Field(..., description="Formatted price with currency")
    fuel: str = Field(default="", description="Fuel type")
    transmission: str = Field(default="", description="Transmission type")
    mileage: Optional[int] = Field(None, description="Mileage in km")
    mileage_formatted: str = Field(default="", description="Formatted mileage with unit")
    condition: str = Field(default="Unknown", description="Car condition")
    thumbnail: str = Field(..., description="Thumbnail image URL")
    country: str = Field(..., description="Country code")
    country_name: str = Field(..., description="Country name")
    auction_date: Optional[datetime] = Field(None, description="Auction date and time")
    is_auction: bool = Field(default=True, description="Is this an auction")
    in_stock: bool = Field(default=True, description="Is car in stock")
    can_book: bool = Field(default=False, description="Can book this car")
    can_check: bool = Field(default=False, description="Can check this car")
    
    # Legacy fields for compatibility
    entry_number: Optional[str] = Field(None, description="Auction lot number")
    car_name: Optional[str] = Field(None, description="Full car name (brand + model)")
    brand: Optional[str] = Field(None, description="Car manufacturer")
    fuel_type: Optional[str] = Field(None, description="Fuel type")
    starting_price: Optional[float] = Field(None, description="Starting price")
    currency: str = Field(default="USD", description="Price currency")
    main_image_url: Optional[str] = Field(None, description="Main image URL")
    detail_url: Optional[str] = Field(None, description="Link to detail page")
    car_no: Optional[str] = Field(None, description="Car number for detail lookup")
    location: Optional[str] = Field(None, description="Auction location")
    color: Optional[str] = Field(None, description="Car color")
    
    def __init__(self, **data):
        super().__init__(**data)
        # Set legacy fields for compatibility
        if not self.car_name:
            self.car_name = self.title
        if not self.brand:
            self.brand = self.manufacturer
        if not self.fuel_type:
            self.fuel_type = self.fuel
        if not self.starting_price:
            self.starting_price = self.price
        if not self.main_image_url:
            self.main_image_url = self.thumbnail
        if not self.detail_url:
            self.detail_url = self.url
        if not self.car_no:
            self.car_no = self.id
    
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


class PLCAuctionVehicleSchema(BaseModel):
    """Schema.org Vehicle structured data from PLC Auction"""
    type: str = Field(alias="@type", default="Vehicle")
    id: str = Field(alias="@id")
    main_entity_of_page: str = Field(alias="mainEntityOfPage")
    name: str
    mileage_from_odometer: Optional[MileageInfo] = Field(None, alias="mileageFromOdometer")
    brand: Optional[Dict[str, str]] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    production_date: Optional[int] = Field(None, alias="productionDate")
    vehicle_transmission: Optional[str] = Field(None, alias="vehicleTransmission")
    fuel_type: Optional[str] = Field(None, alias="fuelType")
    vehicle_engine: Optional[Dict[str, Any]] = Field(None, alias="vehicleEngine")
    drive_wheel_configuration: Optional[str] = Field(None, alias="driveWheelConfiguration")
    color: Optional[str] = None
    vehicle_identification_number: Optional[str] = Field(None, alias="vehicleIdentificationNumber")
    offers: Optional[Dict[str, Any]] = None
    image: Optional[List[str]] = None
    
    class Config:
        populate_by_name = True


class PLCAuctionCarDetail(BaseModel):
    """Detailed car information from PLC Auction"""
    success: bool = True
    message: str = "Success"
    # Basic info
    title: str
    vin: str
    year: int
    manufacturer: str
    model: str
    # Specifications
    engine_volume: Optional[float] = None
    fuel_type: str
    transmission: str
    drive_type: Optional[str] = None
    color: Optional[str] = None
    mileage: str
    mileage_km: Optional[int] = None
    # Auction info
    lot_number: Optional[str] = None
    location: str
    country: str
    auction_date: Optional[str] = None
    # Pricing
    current_bid: Optional[float] = None
    buy_now_price: Optional[float] = None
    currency: str = "USD"
    # Status
    in_stock: bool = True
    is_auction: bool = True
    can_bid: bool = True
    can_buy: bool = False
    # Images
    main_image: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    # Additional info
    runs_drives: Optional[str] = None
    body_type: Optional[str] = None
    damage: Optional[str] = None
    # URLs
    detail_url: str
    similar_url: Optional[str] = None
    # Metadata
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    source: str = "plc_auction"
    
    
class PLCAuctionDetailResponse(BaseModel):
    """Response wrapper for car detail endpoint"""
    success: bool = True
    message: str = "Car details retrieved successfully"
    data: Optional[PLCAuctionCarDetail] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())