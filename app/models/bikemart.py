from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class BikemartBike(BaseModel):
    """Model for individual bike listing from Bikemart"""
    
    seq: str = Field(..., description="Bike listing ID")
    sell_gbn: str = Field(..., description="Sell type code")
    sell_gbn_name: str = Field(..., description="Sell type name")
    title: str = Field(..., description="Listing title")
    old_new_gbn: str = Field(..., description="Old/New status")
    product_seq: str = Field(..., description="Product sequence")
    bike_style: Optional[str] = Field(None, description="Bike style")
    bike_style_name: Optional[str] = Field(None, description="Bike style name")
    brand_seq: str = Field(..., description="Brand sequence ID")
    brand_name: str = Field(..., description="Brand name")
    model: str = Field(..., description="Model name")
    p_code: Optional[str] = Field(None, description="Product code")
    piston: str = Field(..., description="Engine displacement")
    mileage: str = Field(..., description="Mileage in km")
    manufacture_year: str = Field(..., description="Manufacturing year")
    made_year: str = Field(..., description="Made year")
    org_price: str = Field(..., description="Original price")
    sale_price: Optional[str] = Field(None, description="Sale price")
    s_price: str = Field(..., description="Start price")
    e_price: str = Field(..., description="End price")
    s_mileage: str = Field(..., description="Start mileage filter")
    e_mileage: str = Field(..., description="End mileage filter")
    s_year: str = Field(..., description="Start year filter")
    e_year: str = Field(..., description="End year filter")
    qty: str = Field(..., description="Quantity")
    is_tuning: str = Field(..., description="Has tuning flag")
    tuning_memo: str = Field(..., description="Tuning details")
    comment: str = Field(..., description="Seller comment")
    nego_yn: str = Field(..., description="Negotiation available flag")
    write_ip: str = Field(..., description="Writer IP")
    userdoc: str = Field(..., description="User document type")
    seller: str = Field(..., description="Seller ID")
    region_master_seq: str = Field(..., description="Region master sequence")
    region_seq: str = Field(..., description="Region sequence")
    region1: str = Field(..., description="Region level 1")
    region2: str = Field(..., description="Region level 2")
    gps_lat: str = Field(..., description="GPS latitude")
    gps_lon: str = Field(..., description="GPS longitude")
    hp: str = Field(..., description="Phone number")
    contact_time_s: str = Field(..., description="Contact time start")
    contact_time_e: str = Field(..., description="Contact time end")
    email: str = Field(..., description="Email")
    status: str = Field(..., description="Status code")
    status_name: str = Field(..., description="Status name")
    trade_method: str = Field(..., description="Trade method")
    trade_helper: str = Field(..., description="Trade helper")
    renew_date: str = Field(..., description="Renew date")
    start_date: str = Field(..., description="Start date")
    end_date: str = Field(..., description="End date")
    hp_open_yn: str = Field(..., description="Phone open flag")
    writer: str = Field(..., description="Writer ID")
    write_date: str = Field(..., description="Write date")
    changer: str = Field(..., description="Changer ID")
    change_date: str = Field(..., description="Change date")
    product_gbn: str = Field(..., description="Product type")
    thumbnail_url: str = Field(..., description="Thumbnail image URL")
    favorite: str = Field(..., description="Favorite count")


class BikemartFilter(BaseModel):
    """Model for filter options"""
    
    value: str = Field(..., description="Filter value")
    label: str = Field(..., description="Filter label")
    count: Optional[int] = Field(None, description="Item count")


class BikemartBrand(BaseModel):
    """Model for bike brand"""
    
    brand_seq: str = Field(..., description="Brand sequence ID")
    brand_name: str = Field(..., description="Brand name")
    count: Optional[int] = Field(None, description="Number of bikes")


class BikemartPaginationInfo(BaseModel):
    """Model for pagination information"""
    
    current_page: int = Field(..., description="Current page number")
    total_pages: int = Field(..., description="Total number of pages")
    total_count: int = Field(..., description="Total number of items")
    items_per_page: int = Field(..., description="Items per page")


class BikemartResponse(BaseModel):
    """Response model for bikes listing"""
    
    success: bool = Field(..., description="Request success status")
    data: List[BikemartBike] = Field(..., description="List of bikes")
    pagination: Optional[BikemartPaginationInfo] = Field(None, description="Pagination info")
    message: Optional[str] = Field(None, description="Response message")


class BikemartBrandsResponse(BaseModel):
    """Response model for brands listing"""
    
    success: bool = Field(..., description="Request success status")
    data: List[BikemartBrand] = Field(..., description="List of brands")
    message: Optional[str] = Field(None, description="Response message")


class BikemartFiltersResponse(BaseModel):
    """Response model for filter options"""
    
    success: bool = Field(..., description="Request success status")
    brands: List[BikemartFilter] = Field(..., description="Brand filters")
    years: List[BikemartFilter] = Field(..., description="Year filters")
    mileage_ranges: List[BikemartFilter] = Field(..., description="Mileage range filters")
    price_ranges: List[BikemartFilter] = Field(..., description="Price range filters")
    regions: List[BikemartFilter] = Field(..., description="Region filters")
    message: Optional[str] = Field(None, description="Response message")


class BikemartError(BaseModel):
    """Error response model"""
    
    success: bool = False
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")


class BikemartImageUpload(BaseModel):
    """Model for bike image upload data"""
    
    seq: str = Field(..., description="Image sequence ID")
    sell_seq: str = Field(..., description="Bike sell sequence ID")
    url: str = Field(..., description="Full image URL")
    thumbnail_url: str = Field(..., description="Thumbnail image URL")
    filepath: str = Field(..., description="File path on server")
    filename: str = Field(..., description="File name")
    origin_filename: str = Field(..., description="Original file name")
    filesize: str = Field(..., description="File size in bytes")
    width: Optional[str] = Field(None, description="Image width")
    height: Optional[str] = Field(None, description="Image height")
    is_default: str = Field(..., description="Is default image flag")


class BikemartBikeDetail(BikemartBike):
    """Model for detailed bike information including images"""
    
    name: Optional[str] = Field(None, description="Seller name")
    nickname: Optional[str] = Field(None, description="Seller nickname")
    tel: Optional[str] = Field(None, description="Telephone number")
    youtube: Optional[str] = Field(None, description="YouTube link")
    upload: List[BikemartImageUpload] = Field(default_factory=list, description="List of bike images")


class BikemartBikeDetailResponse(BaseModel):
    """Response model for bike detail"""
    
    success: bool = Field(..., description="Request success status")
    data: Optional[BikemartBikeDetail] = Field(None, description="Bike detail data")
    message: Optional[str] = Field(None, description="Response message")