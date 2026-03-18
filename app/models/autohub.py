from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ===== API INPUT MODELS (raw API response mapping) =====


class AutohubApiCarEntry(BaseModel):
    """Single car from listing API data.list[]"""
    entryId: Optional[str] = None
    entryNo: Optional[str] = None
    aucDate: Optional[str] = None
    aucLaneCode: Optional[str] = None
    carLocNm: Optional[str] = None
    startAmt: Optional[int] = None
    hopeAmt: Optional[int] = None
    bidSuccAmt: Optional[int] = None
    carId: Optional[str] = None
    mainFileUrl: Optional[str] = None
    carNo: Optional[str] = None
    carNm: Optional[str] = None
    carNmEn: Optional[str] = None
    carYear: Optional[int] = None
    fuelCode: Optional[str] = None
    fuelNmEn: Optional[str] = None
    tmCode: Optional[str] = None
    tmNmEn: Optional[str] = None
    useageCode: Optional[str] = None
    useageNmEn: Optional[str] = None
    mileage: Optional[int] = None
    inspGrade: Optional[str] = None
    perfId: Optional[str] = None
    soh: Optional[float] = None
    aftBidYn: Optional[str] = None
    aftHopeAmt: Optional[int] = None
    bidFailYn: Optional[str] = None


class AutohubApiCarDetail(BaseModel):
    """Car info from detail endpoint"""
    vin: Optional[str] = None
    firstRegDate: Optional[str] = None
    carYear: Optional[int] = None
    mileage: Optional[int] = None
    displacement: Optional[int] = None
    seating: Optional[int] = None
    colorKo: Optional[str] = None
    colorEn: Optional[str] = None
    fuelCode: Optional[str] = None
    tmCode: Optional[str] = None
    shapeCode: Optional[str] = None
    useageCode: Optional[str] = None
    motorType: Optional[str] = None
    totalLossAccidentYn: Optional[str] = None
    floodedAccidentCount: Optional[int] = None
    gnrlTotalLossAccidentCount: Optional[int] = None
    mrtgCnt: Optional[int] = None
    seizrCnt: Optional[int] = None
    inspectValidPeriod: Optional[str] = None
    accidentDesc: Optional[str] = None
    carNm: Optional[str] = None
    carNmEn: Optional[str] = None
    carNo: Optional[str] = None
    fuelNmEn: Optional[str] = None
    tmNmEn: Optional[str] = None
    useageNmEn: Optional[str] = None
    shapeNmEn: Optional[str] = None


class AutohubApiInspectionOption(BaseModel):
    """Single option from inspection (actual API fields)"""
    ctDtlId: Optional[str] = None
    ctDtlNm: Optional[str] = None
    ctCriteria: Optional[str] = None
    url: Optional[str] = None


class AutohubApiPerformanceCriteria(BaseModel):
    """Single criteria within a performance detail (actual API fields)"""
    ctDtlId: Optional[str] = None
    ctDtlNmKo: Optional[str] = None
    orderNo: Optional[int] = None
    criteriaTypeKoNm: Optional[str] = None


class AutohubApiPerformanceDetail(BaseModel):
    """Performance detail item (actual API fields)"""
    ctId: Optional[str] = None
    ctNmKo: Optional[str] = None
    orderNo: Optional[int] = None
    criteriaList: List[AutohubApiPerformanceCriteria] = Field(default_factory=list)


class AutohubApiElectricPart(BaseModel):
    """Electric part evaluation (actual API fields)"""
    ctDtlId: Optional[str] = None
    ctDtlNmKo: Optional[str] = None
    ctCriteriaTypeNmKo: Optional[str] = None


class AutohubApiInspection(BaseModel):
    """Inspection from performance report endpoint"""
    files: Optional[Dict[str, Any]] = None
    car: Optional[Dict[str, Any]] = None
    evaluation: Optional[Dict[str, Any]] = None
    description: Optional[Dict[str, Any]] = None
    soh: Optional[float] = None


class AutohubApiDiagramPart(BaseModel):
    """Single part in the car diagram (actual API fields)"""
    carFrameNmKo: Optional[str] = None
    carFrameNmEn: Optional[str] = None
    carFrameCls: Optional[str] = None
    carFrameImgUrl: Optional[str] = None
    isPri: Optional[bool] = None
    xPoint: Optional[float] = None
    yPoint: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None


class AutohubApiDiagram(BaseModel):
    """Diagram from layout endpoint"""
    frameDraw: Optional[Dict[str, Any]] = None
    criteriaList: List[AutohubApiDiagramPart] = Field(default_factory=list)


class AutohubApiFrameLegendItem(BaseModel):
    """Single legend item (actual API fields)"""
    perfFrameCriteria: Optional[str] = None
    frameEvalNmKo: Optional[str] = None
    frameEvalNmEn: Optional[str] = None
    orderNo: Optional[int] = None


class AutohubApiFrameLegend(BaseModel):
    """Legend from frames endpoint"""
    past: List[AutohubApiFrameLegendItem] = Field(default_factory=list)
    current: List[AutohubApiFrameLegendItem] = Field(default_factory=list)


# ===== OUTPUT MODELS (what we return to frontend) =====


class AutohubCar(BaseModel):
    """Car listing item returned to frontend"""
    car_id: str = Field(..., description="Car ID (carId)")
    auction_number: str = Field("", description="Entry number (entryNo)")
    entry_id: str = Field("", description="Entry ID (entryId)")
    title: str = Field("", description="Car name (carNmEn)")
    year: int = Field(0, description="Year (carYear)")
    mileage: str = Field("", description="Mileage formatted")
    starting_price: Optional[int] = Field(None, description="Start price (startAmt)")
    hope_price: Optional[int] = Field(None, description="Hope price (hopeAmt)")
    main_image_url: Optional[str] = Field(None, description="Main image URL")
    condition_grade: Optional[str] = Field(None, description="Inspection grade")
    lane: Optional[str] = Field(None, description="Auction lane code")
    parking_number: Optional[str] = Field(None, description="Car location name")
    perf_id: Optional[str] = Field(None, description="Performance ID")
    fuel_type: str = Field("", description="Fuel type EN name")
    transmission: str = Field("", description="Transmission EN name")
    usage_type: Optional[str] = Field(None, description="Usage type EN name")
    soh: Optional[float] = Field(None, description="SOH value")
    status: str = Field("", description="Auction status")
    bid_success_amt: Optional[int] = Field(None, description="Bid success amount")
    aft_bid_yn: Optional[str] = Field(None, description="After-bid consultation flag")


class AutohubCarDiagramPart(BaseModel):
    """Part in the car body diagram"""
    name_ko: Optional[str] = None
    name_en: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    is_primary: bool = False
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None


class AutohubCarDiagramLegendItem(BaseModel):
    """Legend item for car diagram"""
    name: Optional[str] = None
    name_en: Optional[str] = None
    color: Optional[str] = None
    cls: Optional[str] = None


class AutohubCarDiagram(BaseModel):
    """Car body diagram with parts overlay"""
    frame_draw_url: Optional[str] = None
    parts: List[AutohubCarDiagramPart] = Field(default_factory=list)
    legend_past: List[AutohubCarDiagramLegendItem] = Field(default_factory=list)
    legend_current: List[AutohubCarDiagramLegendItem] = Field(default_factory=list)


class AutohubInspectionOption(BaseModel):
    """Car option from inspection report"""
    name: Optional[str] = None
    name_en: Optional[str] = None
    available: bool = False


class AutohubPerformanceItem(BaseModel):
    """Performance evaluation criteria"""
    name: Optional[str] = None
    name_en: Optional[str] = None
    value: Optional[str] = None
    value_name: Optional[str] = None
    value_name_en: Optional[str] = None


class AutohubPerformanceCategory(BaseModel):
    """Performance evaluation category"""
    category: Optional[str] = None
    category_en: Optional[str] = None
    items: List[AutohubPerformanceItem] = Field(default_factory=list)


class AutohubInspectionReport(BaseModel):
    """Inspection report data"""
    image_urls: List[str] = Field(default_factory=list)
    options: List[AutohubInspectionOption] = Field(default_factory=list)
    electric_parts: List[AutohubPerformanceItem] = Field(default_factory=list)
    performance_details: List[AutohubPerformanceCategory] = Field(default_factory=list)
    description: Optional[str] = None
    soh: Optional[float] = None


class AutohubCarDetail(BaseModel):
    """Composite car detail from multiple API endpoints"""
    car_id: str
    title: Optional[str] = None
    vin: Optional[str] = None
    car_number: Optional[str] = None
    year: Optional[int] = None
    mileage: Optional[int] = None
    displacement: Optional[int] = None
    seating: Optional[int] = None
    color: Optional[str] = None
    color_en: Optional[str] = None
    fuel_type: Optional[str] = None
    transmission: Optional[str] = None
    shape: Optional[str] = None
    usage_type: Optional[str] = None
    motor_type: Optional[str] = None
    first_reg_date: Optional[str] = None
    inspect_valid_period: Optional[str] = None
    total_loss_accident: Optional[str] = None
    flooded_accident_count: Optional[int] = None
    general_total_loss_count: Optional[int] = None
    mortgage_count: Optional[int] = None
    seizure_count: Optional[int] = None
    accident_desc: Optional[str] = None
    inspection: Optional[AutohubInspectionReport] = None
    diagram: Optional[AutohubCarDiagram] = None


class AutohubResponse(BaseModel):
    """Wraps car list response"""
    success: bool = True
    data: List[AutohubCar] = Field(default_factory=list)
    error: Optional[str] = None
    total_count: int = 0
    total_pages: int = 0
    current_page: int = 1
    page_size: int = 20


class AutohubCarDetailResponse(BaseModel):
    """Wraps car detail response"""
    success: bool = True
    data: Optional[AutohubCarDetail] = None
    error: Optional[str] = None
