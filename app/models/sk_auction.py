"""
SK Auction Pydantic models for vehicle auction data.
SK Auction (SK Car Rental) - https://auction.skcarrental.com
"""

from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
from app.models.base_auction import AuctionErrorType


class SKFuelType(str, Enum):
    """Fuel type codes from SK Auction API"""
    GASOLINE = "G"
    DIESEL = "D"
    LPG = "L"
    LPI_HYBRID = "I"
    GASOLINE_HYBRID = "K"
    DIESEL_HYBRID = "T"
    ELECTRIC = "E"
    GASOLINE_LPG = "H"
    DIESEL_LPG = "P"
    HYDROGEN = "H1"
    HYDROGEN_ELECTRIC = "H2"
    UNKNOWN = ""


class SKTransmissionType(str, Enum):
    """Transmission type codes from SK Auction API"""
    AUTOMATIC = "01"
    MANUAL = "02"
    UNKNOWN = ""


class SKConditionGrade(str, Enum):
    """Vehicle condition grades"""
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"
    UNKNOWN = ""


# ==================== Filter Models ====================

class SKAuctionBrand(BaseModel):
    """Brand/Manufacturer from SK Auction"""
    code: str = Field(..., description="Brand code (e.g., ABI000000005)")
    name: str = Field(..., description="Brand name in Korean")
    name_en: Optional[str] = Field(None, description="Brand name in English")
    exhi_count: int = Field(default=0, description="Number of cars on exhibition")
    doim_cd: Optional[str] = Field(None, description="Region code")
    disp_order: Optional[int] = Field(None, description="Display order")


class SKAuctionModel(BaseModel):
    """Vehicle model from SK Auction"""
    code: str = Field(..., description="Model code (e.g., ABI000000096)")
    name: str = Field(..., description="Model name in Korean")
    brand_code: str = Field(..., description="Parent brand code")
    exhi_count: int = Field(default=0, description="Number of cars on exhibition")


class SKAuctionGeneration(BaseModel):
    """Model generation/variant from SK Auction"""
    code: str = Field(..., description="Generation code")
    name: str = Field(..., description="Generation name in Korean")
    brand_code: str = Field(..., description="Parent brand code")
    exhi_count: int = Field(default=0, description="Number of cars on exhibition")


class SKAuctionFuelTypeOption(BaseModel):
    """Fuel type option for filters"""
    code: str = Field(..., description="Fuel type code")
    name: str = Field(..., description="Fuel type name in Korean")


class SKAuctionYearOption(BaseModel):
    """Year option for filters"""
    code: str = Field(..., description="Year value")
    name: str = Field(..., description="Year display name")


# ==================== Search Filters ====================

class SKAuctionSearchFilters(BaseModel):
    """Search filters for SK Auction car listings"""
    brand_code: Optional[str] = Field(None, alias="set_search_maker")
    model_code: Optional[str] = Field(None, alias="set_search_mdl")
    generation_codes: Optional[List[str]] = Field(None, alias="set_search_chk_carGrp")
    year_from: Optional[int] = Field(None, alias="search_startYyyy")
    year_to: Optional[int] = Field(None, alias="search_endYyyy")
    mileage_from: Optional[int] = Field(None, alias="search_startKm")
    mileage_to: Optional[int] = Field(None, alias="search_endKm")
    price_from: Optional[int] = Field(None, alias="search_startPrice", description="Price in millions of won")
    price_to: Optional[int] = Field(None, alias="search_endPrice", description="Price in millions of won")
    fuel_type: Optional[str] = Field(None, alias="search_fuelCd")
    transmission: Optional[str] = Field(None, alias="search_trnsCd")
    accident_grade: Optional[str] = Field(None, alias="accidGrade")
    condition_grade: Optional[str] = Field(None, alias="stateGrade")
    exhibition_number: Optional[str] = Field(None, alias="search_exhiNo")
    lane_division: Optional[str] = Field(None, alias="search_LaneDiv")
    region_code: str = Field(default="all", alias="search_doimCd")

    class Config:
        populate_by_name = True


# ==================== Car Models ====================

class SKAuctionCar(BaseModel):
    """Car listing from SK Auction API"""

    # Identification
    car_no: str = Field(..., description="Vehicle registration number (e.g., 128허5702)")
    mng_no: str = Field(..., description="Management number (e.g., SR25000118172)")
    mng_div_cd: str = Field(..., description="Management division code (e.g., SR, PC)")
    exhi_regi_seq: int = Field(..., description="Exhibition registration sequence")

    # Auction info
    exhi_no: str = Field(..., description="Exhibition number (e.g., 0001)")
    auction_date: Optional[str] = Field(default="", description="Auction date (YYYYMMDD)")
    lane_div: Optional[str] = Field(default="", description="Lane division (A, B, etc.)")
    exhi_div_cd: str = Field(default="01", description="Exhibition division code")
    exhi_stat_cd: str = Field(default="02", description="Exhibition status code")
    exhi_regi_stat_cd: Optional[str] = Field(default="02", description="Exhibition registration status code")

    # Vehicle info from codes
    mdl_cd: str = Field(..., description="Model code")
    car_grp_cd: str = Field(..., description="Car group/generation code")

    # Vehicle info readable names
    car_name: str = Field(..., description="Full car name")
    model_name: str = Field(..., description="Model name (e.g., 기아 모닝)")
    generation_name: str = Field(..., description="Generation name (e.g., 올 뉴모닝(JA))")

    # Technical specifications
    year: int = Field(..., description="Registration year")
    mileage: int = Field(..., description="Mileage in km")
    transmission: str = Field(..., description="Transmission type name (AT/MT)")
    transmission_code: str = Field(..., description="Transmission code (01/02)")
    fuel_type: str = Field(..., description="Fuel type name")
    color: str = Field(..., description="Color name")
    color_code: str = Field(..., description="Color code")

    # Condition grades
    accident_grade: str = Field(..., description="Accident score (A, B, C, D)")
    exterior_grade: str = Field(..., description="Exterior/condition score (A, B, C, D, F)")

    # Pricing
    starting_price: int = Field(..., description="Starting price in units of 10,000 won")
    starting_price_won: int = Field(default=0, description="Starting price in won")

    # Location
    parking_location: str = Field(default="", description="Parking spot (e.g., 1F-J-0527)")

    # Statistics
    view_count: int = Field(default=0, description="Number of views")
    row_number: int = Field(default=0, description="Row number in result set")

    # Watchlist
    concern_yn: Optional[str] = Field(None, description="Watchlist status")
    concern_search_mode: str = Field(default="none", description="Concern search mode")

    # Status names
    exhi_div_name: str = Field(default="", description="Exhibition division name")
    exhi_stat_name: str = Field(default="", description="Exhibition status name")
    exhi_regi_stat_name: Optional[str] = Field(default="", description="Exhibition registration status name")

    # Image URL (constructed from mng_no)
    main_image_url: Optional[str] = Field(None, description="Main thumbnail image URL")

    class Config:
        populate_by_name = True


# ==================== Car Detail Models ====================

class SKAuctionCarOwner(BaseModel):
    """Owner information from car detail"""
    company_name: Optional[str] = Field(None, description="Company name (상호)")
    representative_name: Optional[str] = Field(None, description="Representative name (성명)")
    registration_number: Optional[str] = Field(None, description="Registration number (masked)")
    address: Optional[str] = Field(None, description="Address")


class SKAuctionCarSpecs(BaseModel):
    """Technical specifications from car detail"""
    year: Optional[str] = Field(None, description="Registration year")
    mileage: Optional[str] = Field(None, description="Mileage")
    first_registration_date: Optional[str] = Field(None, description="First registration date")
    transmission: Optional[str] = Field(None, description="Transmission type")
    usage_type: Optional[str] = Field(None, description="Usage type (e.g., 렌트)")
    color: Optional[str] = Field(None, description="Color")
    engine_type: Optional[str] = Field(None, description="Engine type")
    fuel_type: Optional[str] = Field(None, description="Fuel type")
    inspection_valid_until: Optional[str] = Field(None, description="Inspection validity date")
    displacement: Optional[str] = Field(None, description="Engine displacement")
    car_type: Optional[str] = Field(None, description="Car type (승용/SUV)")
    seating_capacity: Optional[str] = Field(None, description="Seating capacity")
    main_options: Optional[str] = Field(None, description="Main options")
    special_notes: Optional[str] = Field(None, description="Special notes")
    complete_documents: Optional[str] = Field(None, description="Complete documents")
    stored_items: Optional[str] = Field(None, description="Stored items")
    vin_number: Optional[str] = Field(None, description="VIN number")


class SKAuctionConditionCheck(BaseModel):
    """Condition check results"""
    overall_score: Optional[str] = Field(None, description="Overall evaluation score (e.g., A/C)")
    engine_condition: Optional[str] = Field(None, description="Engine condition")
    transmission_condition: Optional[str] = Field(None, description="Transmission condition")
    brake_condition: Optional[str] = Field(None, description="Brake condition")
    power_transmission: Optional[str] = Field(None, description="Power transmission condition")
    air_conditioning: Optional[str] = Field(None, description="Air conditioning condition")
    steering_condition: Optional[str] = Field(None, description="Steering condition")
    electrical_condition: Optional[str] = Field(None, description="Electrical condition")
    interior_condition: Optional[str] = Field(None, description="Interior condition")
    special_notes: Optional[str] = Field(None, description="Special notes")
    status_map_image: Optional[str] = Field(None, description="Status check map image URL")


class SKAuctionLegalStatus(BaseModel):
    """Legal status (seizure/mortgage)"""
    last_inquiry_date: Optional[str] = Field(None, description="Last inquiry date")
    seizure_count: int = Field(default=0, description="Number of seizures")
    mortgage_count: int = Field(default=0, description="Number of mortgages")
    modification_count: int = Field(default=0, description="Number of modifications")


class SKAuctionTireInfo(BaseModel):
    """Tire condition information"""
    front_left: Optional[Dict[str, str]] = Field(None, description="Front left tire condition")
    front_right: Optional[Dict[str, str]] = Field(None, description="Front right tire condition")
    rear_left: Optional[Dict[str, str]] = Field(None, description="Rear left tire condition")
    rear_right: Optional[Dict[str, str]] = Field(None, description="Rear right tire condition")


class SKAuctionMedia(BaseModel):
    """Media files for car detail"""
    main_images: List[str] = Field(default_factory=list, description="Main car images")
    thumbnail_images: List[str] = Field(default_factory=list, description="Thumbnail images")
    undercarriage_image: Optional[str] = Field(None, description="Undercarriage scan image")
    undercarriage_videos: List[str] = Field(default_factory=list, description="Undercarriage videos")
    cv_joint_images: List[str] = Field(default_factory=list, description="CV joint images")


class SKAuctionInspectionRecord(BaseModel):
    """Inspection record information"""
    record_number: Optional[str] = Field(None, description="Record number")
    inspection_date: Optional[str] = Field(None, description="Inspection date")
    inspector_location: Optional[str] = Field(None, description="Inspection location")
    inspector_name: Optional[str] = Field(None, description="Inspector name")
    identity_check_vin: bool = Field(default=False, description="VIN identity check")
    identity_check_engine: bool = Field(default=False, description="Engine type identity check")


class SKAuctionCarDetail(BaseModel):
    """Complete car detail from SK Auction"""

    # Basic identification
    car_no: str = Field(..., description="Vehicle registration number")
    mng_no: str = Field(..., description="Management number")
    mng_div_cd: str = Field(..., description="Management division code")
    exhi_regi_seq: int = Field(..., description="Exhibition registration sequence")

    # Auction info
    exhi_no: str = Field(..., description="Exhibition number")
    auction_date: Optional[str] = Field(None, description="Auction date")
    lane_div: Optional[str] = Field(None, description="Lane division")
    auction_status: Optional[str] = Field(None, description="Auction status")
    auction_result: Optional[str] = Field(None, description="Auction result")
    parking_location: Optional[str] = Field(None, description="Parking location")

    # Vehicle info
    car_name: str = Field(..., description="Full car name")
    starting_price: int = Field(..., description="Starting price in units of 10,000 won")
    starting_price_text: Optional[str] = Field(None, description="Starting price formatted text")

    # Nested models
    owner_info: SKAuctionCarOwner = Field(default_factory=SKAuctionCarOwner)
    technical_specs: SKAuctionCarSpecs = Field(default_factory=SKAuctionCarSpecs)
    condition_check: SKAuctionConditionCheck = Field(default_factory=SKAuctionConditionCheck)
    legal_status: SKAuctionLegalStatus = Field(default_factory=SKAuctionLegalStatus)
    tire_info: Optional[SKAuctionTireInfo] = Field(None, description="Tire condition info")
    media: SKAuctionMedia = Field(default_factory=SKAuctionMedia)
    inspection_record: SKAuctionInspectionRecord = Field(default_factory=SKAuctionInspectionRecord)

    # Meta
    parsed_at: Optional[datetime] = Field(None, description="Parse timestamp")
    source_url: Optional[str] = Field(None, description="Source URL")


# ==================== Response Models ====================

class SKAuctionPaginationInfo(BaseModel):
    """Pagination information from SK Auction API"""
    current_page: int = Field(default=1, description="Current page number")
    records_per_page: int = Field(default=20, description="Records per page")
    page_size: int = Field(default=10, description="Page links size")
    total_records: int = Field(default=0, description="Total record count")
    total_pages: int = Field(default=0, description="Total page count")
    first_page: int = Field(default=1, description="First page number")
    last_page: int = Field(default=1, description="Last page number")


class SKAuctionResponse(BaseModel):
    """Response model for SK Auction car listings"""

    success: bool = Field(..., description="Request success status")
    message: str = Field(..., description="Response message")

    # Data
    cars: List[SKAuctionCar] = Field(default_factory=list, description="List of cars")
    pagination: SKAuctionPaginationInfo = Field(default_factory=SKAuctionPaginationInfo)

    # Convenience fields
    total_count: int = Field(default=0, description="Total car count")
    current_page: int = Field(default=1, description="Current page")
    page_size: int = Field(default=20, description="Page size")
    total_pages: int = Field(default=0, description="Total pages")
    has_next_page: bool = Field(default=False, description="Has next page")
    has_prev_page: bool = Field(default=False, description="Has previous page")

    # Metadata
    auction_date: Optional[str] = Field(None, description="Auction date")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="Response timestamp")
    request_duration: Optional[float] = Field(None, description="Request duration in seconds")

    # Error handling
    error_type: Optional[AuctionErrorType] = Field(None, description="Error type for client handling")


class SKAuctionDetailResponse(BaseModel):
    """Response model for SK Auction car detail"""

    success: bool = Field(..., description="Request success status")
    message: str = Field(..., description="Response message")
    data: Optional[SKAuctionCarDetail] = Field(None, description="Car detail data")

    # Error handling
    error: Optional[str] = Field(None, description="Error message")
    error_type: Optional[AuctionErrorType] = Field(None, description="Error type for client handling")

    # Metadata
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="Response timestamp")


class SKAuctionBrandsResponse(BaseModel):
    """Response model for brands list"""

    success: bool = Field(..., description="Request success status")
    message: str = Field(..., description="Response message")
    brands: List[SKAuctionBrand] = Field(default_factory=list, description="List of brands")
    total_count: int = Field(default=0, description="Total brands count")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class SKAuctionModelsResponse(BaseModel):
    """Response model for models list"""

    success: bool = Field(..., description="Request success status")
    message: str = Field(..., description="Response message")
    models: List[SKAuctionModel] = Field(default_factory=list, description="List of models")
    brand_code: Optional[str] = Field(None, description="Brand code filter")
    total_count: int = Field(default=0, description="Total models count")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class SKAuctionGenerationsResponse(BaseModel):
    """Response model for generations list"""

    success: bool = Field(..., description="Request success status")
    message: str = Field(..., description="Response message")
    generations: List[SKAuctionGeneration] = Field(default_factory=list, description="List of generations")
    model_code: Optional[str] = Field(None, description="Model code filter")
    total_count: int = Field(default=0, description="Total generations count")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class SKAuctionFuelTypesResponse(BaseModel):
    """Response model for fuel types list"""

    success: bool = Field(..., description="Request success status")
    message: str = Field(..., description="Response message")
    fuel_types: List[SKAuctionFuelTypeOption] = Field(default_factory=list, description="List of fuel types")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class SKAuctionYearsResponse(BaseModel):
    """Response model for years list"""

    success: bool = Field(..., description="Request success status")
    message: str = Field(..., description="Response message")
    years: List[SKAuctionYearOption] = Field(default_factory=list, description="List of years")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class SKAuctionCountResponse(BaseModel):
    """Response model for total cars count"""

    success: bool = Field(..., description="Request success status")
    total_count: int = Field(default=0, description="Total number of cars")
    message: str = Field(..., description="Response message")
    auction_date: Optional[str] = Field(None, description="Auction date")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class SKAuctionError(BaseModel):
    """Error response model"""

    success: bool = Field(default=False, description="Always false for errors")
    error_code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: Optional[str] = Field(None, description="Error details")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
