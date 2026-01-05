"""
Pydantic models for Encar Truck API
Models for both list endpoint and vehicle details endpoint
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


# ============================================
# List API Models (search/truck/list/general)
# ============================================

class EncarTruckPhoto(BaseModel):
    """Photo information for truck listing"""
    type: str
    location: str
    updatedDate: str
    ordering: float


class EncarTruck(BaseModel):
    """Truck listing model from search API"""
    Id: str
    Separation: Optional[List[str]] = None
    Trust: Optional[List[str]] = None
    ServiceMark: Optional[List[str]] = None
    Condition: Optional[List[str]] = None
    Photo: Optional[str] = None
    Photos: Optional[List[EncarTruckPhoto]] = None
    Manufacturer: Optional[str] = None
    Model: Optional[str] = None
    FormDetail: Optional[str] = None      # Body type: 냉동탑, 파워게이트, 익스(하이)내장탑
    Capacity: Optional[str] = None        # Tonnage: 1톤, 2.5톤, 5톤
    Standard: Optional[str] = None        # Wheelbase: 초장축, 장축
    Badge: Optional[str] = None           # Trim level: 슈퍼캡 CRDI, 킹캡
    Year: float
    FormYear: Optional[str] = None
    Mileage: float
    Price: float                          # Price in 만원 (10,000 KRW)
    Use: Optional[str] = None             # Usage type: 자가용, 영업용
    OfficeCityState: Optional[str] = None
    ModifiedDate: Optional[str] = None
    SalesStatus: Optional[str] = None


class EncarTruckListResponse(BaseModel):
    """Response model for truck list endpoint"""
    Count: int = Field(..., description="Total number of trucks matching the query")
    SearchResults: List[EncarTruck] = Field(default_factory=list, description="List of trucks")
    success: bool = True
    message: Optional[str] = None


# ============================================
# Details API Models (v1/readside/vehicle)
# ============================================

class TruckManage(BaseModel):
    """Vehicle management info"""
    dummy: bool = False
    dummyVehicleId: Optional[int] = None
    reRegistered: bool = False
    webReserved: bool = False
    registDateTime: Optional[str] = None
    firstAdvertisedDateTime: Optional[str] = None
    modifyDateTime: Optional[str] = None
    subscribeCount: int = 0
    viewCount: int = 0


class TruckCategory(BaseModel):
    """Vehicle category information"""
    type: str
    manufacturerCd: Optional[str] = None
    manufacturerName: str
    modelCd: Optional[str] = None
    modelName: str
    gradeCd: Optional[str] = None
    gradeName: str
    gradeEnglishName: Optional[str] = None
    yearMonth: str
    formYear: str
    formCd: Optional[str] = None
    formName: Optional[str] = None
    formDetailCd: Optional[str] = None
    formDetailName: str
    capacityCd: Optional[str] = None
    capacityName: str
    isSmallCapacity: Optional[bool] = None
    specialManufacturerCd: Optional[str] = None
    specialManufacturerName: Optional[str] = None


class TruckAdvertisement(BaseModel):
    """Advertisement information"""
    type: str
    price: int
    status: str
    warrantyStyleColor: Optional[str] = None
    trust: List[str] = Field(default_factory=list)
    hotMark: List[str] = Field(default_factory=list)
    oneLineText: Optional[str] = None
    salesStatus: Optional[str] = None
    directInspected: bool = False
    preVerified: bool = False
    extendWarranty: bool = False
    deemedExtendWarranty: bool = False
    homeService: bool = False
    meetGo: bool = False
    preDelivery: bool = False
    leaseRentInfo: Optional[Dict[str, Any]] = None
    encarPassType: Optional[str] = None
    encarPassCategoryType: Optional[str] = None
    underBodyPhotos: List[str] = Field(default_factory=list)
    hasUnderBodyPhoto: bool = False
    diagnosisCar: bool = False


class TruckContact(BaseModel):
    """Dealer contact information"""
    userId: Optional[str] = None
    userType: Optional[str] = None
    no: Optional[str] = None
    address: Optional[str] = None
    contactType: Optional[str] = None
    isVerifyOwner: bool = False
    isOwnerPartner: bool = False


class TruckSpec(BaseModel):
    """Vehicle specifications"""
    type: str
    mileage: int
    displacement: Optional[int] = None
    transmissionName: Optional[str] = None
    fuelCd: Optional[str] = None
    fuelName: Optional[str] = None
    colorName: Optional[str] = None
    customColor: Optional[str] = None
    seatCount: Optional[int] = None
    varaxis: Optional[str] = None
    use: Optional[str] = None
    capacityStandardName: Optional[str] = None  # Wheelbase: 초장축, 장축
    horsePower: Optional[int] = None
    carryingBox: bool = False
    carryingBoxBore: int = 0
    carryingBoxHeight: int = 0
    carryingBoxWidth: int = 0


class TruckDetailPhoto(BaseModel):
    """Photo in vehicle details"""
    code: str
    path: str
    type: str  # OUTER, INNER, OPTION, THUMBNAIL
    updateDateTime: Optional[str] = None
    desc: Optional[str] = None


class TruckOptions(BaseModel):
    """Vehicle options"""
    type: str
    standard: List[str] = Field(default_factory=list)
    etc: List[str] = Field(default_factory=list)


class TruckAccident(BaseModel):
    """Accident record info"""
    recordView: bool = False
    resumeView: bool = False


class TruckInspection(BaseModel):
    """Inspection info"""
    formats: List[str] = Field(default_factory=list)


class TruckSeizing(BaseModel):
    """Seizing info"""
    seizingCount: int = 0
    pledgeCount: int = 0


class TruckCondition(BaseModel):
    """Vehicle condition"""
    accident: Optional[TruckAccident] = None
    inspection: Optional[TruckInspection] = None
    seizing: Optional[TruckSeizing] = None


class TruckPartnership(BaseModel):
    """Partnership info"""
    brand: Optional[str] = None
    testdrive: Optional[Dict[str, Any]] = None
    dealer: Optional[str] = None
    isPartneredVehicle: bool = False
    certifiedBrand: Optional[str] = None
    lease: Optional[Dict[str, Any]] = None
    rent: Optional[Dict[str, Any]] = None


class TruckContents(BaseModel):
    """Vehicle description content"""
    text: Optional[str] = None
    meetGoText: Optional[str] = None


class EncarTruckDetails(BaseModel):
    """Full truck details response from v1/readside/vehicle API"""
    vehicleId: int
    vehicleType: str
    vehicleNo: Optional[str] = None
    vin: Optional[str] = None
    manage: Optional[TruckManage] = None
    category: TruckCategory
    advertisement: TruckAdvertisement
    contact: Optional[TruckContact] = None
    spec: TruckSpec
    photos: List[TruckDetailPhoto] = Field(default_factory=list)
    options: Optional[TruckOptions] = None
    condition: Optional[TruckCondition] = None
    partnership: Optional[TruckPartnership] = None
    contents: Optional[TruckContents] = None
    view: Optional[Dict[str, Any]] = None


class EncarTruckDetailsResponse(BaseModel):
    """Wrapper response for truck details"""
    success: bool = True
    message: Optional[str] = None
    data: Optional[EncarTruckDetails] = None


class EncarTruckError(BaseModel):
    """Error response model"""
    success: bool = False
    message: str
    detail: Optional[str] = None
