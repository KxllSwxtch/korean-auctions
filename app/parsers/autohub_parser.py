"""
Autohub JSON API mapper.

Replaces the old HTML parser with thin mapping functions for the JSON API.
"""

from typing import List, Optional, Dict, Any
import logging

from app.models.autohub import (
    AutohubCar,
    AutohubCarDetail,
    AutohubInspectionReport,
    AutohubInspectionOption,
    AutohubPerformanceItem,
    AutohubPerformanceCategory,
    AutohubCarDiagram,
    AutohubCarDiagramPart,
    AutohubCarDiagramLegendItem,
)
from app.models.autohub_filters import (
    AutohubBrandsGroup,
    AutohubBrandItem,
    AutohubModelItem,
    AutohubModelDetailItem,
)

logger = logging.getLogger(__name__)

IMAGE_CDN_BASE = "https://api.ahsellcar.co.kr"

# Legend color mapping by perfFrameCriteria code
LEGEND_COLORS: Dict[str, str] = {
    # Past damage codes
    "XX": "#FF6B6B",  # Red - Exchange
    "W":  "#FFA94D",  # Orange - Welding/Bending
    "P":  "#FFD3D3",  # Pink - Painting
    # Current damage codes
    "R":  "#FF6B6B",  # Red - Repair Required
    "M":  "#4DABF7",  # Blue - Mediate/Adjust
    "X":  "#FF4444",  # Dark Red - Exchange Required
}

# Common option translations Korean → English
OPTION_TRANSLATIONS: Dict[str, str] = {
    "내비게이션": "Navigation",
    "선루프": "Sunroof",
    "전동트렁크": "Power Trunk",
    "스마트키": "Smart Key",
    "메모리시트": "Memory Seat",
    "HUD": "HUD",
    "후방카메라": "Rear Camera",
    "열선시트": "Heated Seats",
    "통풍시트": "Ventilated Seats",
    "크루즈컨트롤": "Cruise Control",
    "후방센서": "Rear Sensor",
    "전방센서": "Front Sensor",
    "블랙박스": "Dashcam",
    "ECM룸미러": "ECM Rearview Mirror",
    "오토라이트": "Auto Lights",
    "레인센서": "Rain Sensor",
}

# Performance category translations Korean → English
PERF_CATEGORY_TRANSLATIONS: Dict[str, str] = {
    "엔진": "Engine",
    "미션": "Transmission",
    "동력전달": "Power Delivery",
    "조향": "Steering",
    "제동": "Braking",
    "전기": "Electrical",
    "공조": "HVAC",
    "실내": "Interior",
    "경고등": "Warning Lights",
    "차체부식": "Body Corrosion",
}

# Performance criteria translations Korean → English
PERF_CRITERIA_TRANSLATIONS: Dict[str, str] = {
    "작동상태": "Operating Condition",
    "냉각계통": "Cooling System",
    "구동축": "Drive Shaft",
    "클러치": "Clutch",
    "충전장치": "Charging System",
    "공조기": "Air Conditioner",
    "시트": "Seats",
    "실내트림/내장재": "Interior Trim",
    "경고등": "Warning Lights",
    "차체부식": "Body Corrosion",
}

# Performance value translations Korean → English
PERF_VALUE_TRANSLATIONS: Dict[str, str] = {
    "보통": "Normal",
    "양호": "Good",
}


def format_mileage(mileage: Optional[int]) -> str:
    """Format mileage as string with comma separator and km suffix."""
    if mileage is None:
        return ""
    return f"{mileage:,}km"


def _translate_perf_value(value_ko: Optional[str]) -> Optional[str]:
    """Translate Korean performance value to English, handling '정비요' prefix."""
    if not value_ko:
        return None
    if value_ko in PERF_VALUE_TRANSLATIONS:
        return PERF_VALUE_TRANSLATIONS[value_ko]
    if value_ko.startswith("정비요"):
        detail = value_ko.replace("정비요", "").strip()
        return f"Needs Repair: {detail}" if detail else "Needs Repair"
    return None


def build_image_url(file_id: str, proxy_base: str = "/api/v1/autohub/image") -> str:
    """Construct image URL from file ID. Returns proxy URL for Autohub file IDs."""
    if not file_id:
        return ""
    if file_id.startswith("http"):
        return file_id
    return f"{proxy_base}/{file_id}"


def determine_status(entry: dict) -> str:
    """Determine auction status from entry data."""
    bid_fail = entry.get("bidFailYn", "")
    bid_succ_amt = entry.get("bidSuccAmt")
    aft_bid_yn = entry.get("aftBidYn", "")

    if bid_succ_amt and bid_succ_amt > 0:
        return "낙찰"
    if aft_bid_yn == "Y":
        return "후상담"
    if bid_fail == "Y":
        return "유찰"
    return "출품등록"


def map_car_entry(entry: dict) -> AutohubCar:
    """Map a single car entry from the listing API response."""
    car_id = entry.get("carId", "")
    main_file_url = entry.get("mainFileUrl", "")
    image_url = build_image_url(main_file_url) if main_file_url else None

    return AutohubCar(
        car_id=car_id,
        auction_number=entry.get("entryNo", ""),
        entry_id=entry.get("entryId", ""),
        title=entry.get("carNmEn") or entry.get("carNm", ""),
        year=entry.get("carYear", 0),
        mileage=format_mileage(entry.get("mileage")),
        starting_price=entry.get("startAmt"),
        hope_price=entry.get("hopeAmt"),
        main_image_url=image_url,
        condition_grade=entry.get("inspGrade"),
        lane=entry.get("aucLaneCode"),
        parking_number=entry.get("carLocNm"),
        perf_id=entry.get("perfId"),
        fuel_type=entry.get("fuelNmEn") or entry.get("fuelCode", ""),
        transmission=entry.get("tmNmEn") or entry.get("tmCode", ""),
        usage_type=entry.get("useageNmEn") or entry.get("useageCode"),
        soh=entry.get("soh"),
        status=determine_status(entry),
        bid_success_amt=entry.get("bidSuccAmt"),
        aft_bid_yn=entry.get("aftBidYn"),
    )


def map_car_list(api_data: dict) -> tuple[List[AutohubCar], int]:
    """Map listing API response to list of cars + total count."""
    data = api_data.get("data", {})
    entries = data.get("list", [])
    total_count = data.get("totalCount", 0)

    cars = []
    for entry in entries:
        try:
            car = map_car_entry(entry)
            cars.append(car)
        except Exception as e:
            logger.warning(f"Failed to map car entry: {e}", exc_info=True)

    return cars, total_count


def map_car_detail(detail_data: dict) -> AutohubCarDetail:
    """Map car detail API response."""
    data = detail_data.get("data", detail_data)

    return AutohubCarDetail(
        car_id=data.get("carId", ""),
        title=data.get("carNmEn") or data.get("carNm"),
        vin=data.get("vin"),
        car_number=data.get("carNo"),
        year=data.get("carYear"),
        mileage=data.get("mileage"),
        displacement=data.get("displacement"),
        seating=data.get("seating"),
        color=data.get("colorKo"),
        color_en=data.get("colorEn"),
        fuel_type=data.get("fuelNmEn") or data.get("fuelCode"),
        transmission=data.get("tmNmEn") or data.get("tmCode"),
        shape=data.get("shapeNmEn") or data.get("shapeCode"),
        usage_type=data.get("useageNmEn") or data.get("useageCode"),
        motor_type=data.get("motorType"),
        first_reg_date=data.get("firstRegDate"),
        inspect_valid_period=data.get("inspectValidPeriod"),
        total_loss_accident=data.get("totalLossAccidentYn"),
        flooded_accident_count=data.get("floodedAccidentCount"),
        general_total_loss_count=data.get("gnrlTotalLossAccidentCount"),
        mortgage_count=data.get("mrtgCnt"),
        seizure_count=data.get("seizrCnt"),
        accident_desc=data.get("accidentDesc"),
    )


def map_inspection(insp_data: dict) -> AutohubInspectionReport:
    """Map inspection/performance report API response."""
    data = insp_data.get("data", insp_data)

    # Extract image URLs from files
    image_urls = []
    files_data = data.get("files", {})
    file_ids = files_data.get("fileIds", []) if isinstance(files_data, dict) else []
    for fid in file_ids:
        if fid:
            image_urls.append(build_image_url(str(fid)))

    # Extract options
    options = []
    car_data = data.get("car", {})
    option_list = car_data.get("options", []) if isinstance(car_data, dict) else []
    for opt in option_list:
        name_ko = opt.get("ctDtlNm")
        options.append(AutohubInspectionOption(
            name=name_ko,
            name_en=OPTION_TRANSLATIONS.get(name_ko, "") if name_ko else None,
            available=True,
        ))

    # Extract electric parts
    electric_parts = []
    eval_data = data.get("evaluation", {})
    if isinstance(eval_data, dict):
        for ep in eval_data.get("electricParts", []):
            name_ko = ep.get("ctDtlNmKo")
            value_ko = ep.get("ctCriteriaTypeNmKo")
            electric_parts.append(AutohubPerformanceItem(
                name=name_ko,
                name_en=OPTION_TRANSLATIONS.get(name_ko, "") if name_ko else None,
                value=None,
                value_name=value_ko,
                value_name_en=_translate_perf_value(value_ko),
            ))

    # Extract performance details
    performance_details = []
    if isinstance(eval_data, dict):
        for perf in eval_data.get("performanceDtl", []):
            cat_ko = perf.get("ctNmKo")
            criteria_items = []
            for crit in perf.get("criteriaList", []):
                crit_ko = crit.get("ctDtlNmKo")
                val_ko = crit.get("criteriaTypeKoNm")
                criteria_items.append(AutohubPerformanceItem(
                    name=crit_ko,
                    name_en=PERF_CRITERIA_TRANSLATIONS.get(crit_ko, "") if crit_ko else None,
                    value=None,
                    value_name=val_ko,
                    value_name_en=_translate_perf_value(val_ko),
                ))
            performance_details.append(AutohubPerformanceCategory(
                category=cat_ko,
                category_en=PERF_CATEGORY_TRANSLATIONS.get(cat_ko, "") if cat_ko else None,
                items=criteria_items,
            ))

    # Extract description
    desc_data = data.get("description", {})
    description = desc_data.get("descr") if isinstance(desc_data, dict) else None

    return AutohubInspectionReport(
        image_urls=image_urls,
        options=options,
        electric_parts=electric_parts,
        performance_details=performance_details,
        description=description,
        soh=data.get("soh"),
    )


def map_diagram(diagram_data: dict, legend_data: dict) -> AutohubCarDiagram:
    """Map diagram and legend API responses."""
    data = diagram_data.get("data", diagram_data)

    # Frame draw URL
    frame_draw = data.get("frameDraw", {})
    frame_draw_url = None
    if isinstance(frame_draw, dict):
        draw_file_url = frame_draw.get("drawFileUrl")
        if draw_file_url:
            frame_draw_url = build_image_url(draw_file_url) if not draw_file_url.startswith("http") else draw_file_url

    # Map parts from criteriaList
    parts = []
    for part in data.get("criteriaList", []):
        img_url = part.get("carFrameImgUrl")
        parts.append(AutohubCarDiagramPart(
            name_ko=part.get("carFrameNmKo") or part.get("carFrameNm"),
            name_en=part.get("carFrameNmEn"),
            category=part.get("carFrameCls"),
            image_url=build_image_url(img_url) if img_url and not img_url.startswith("http") else img_url,
            is_primary=part.get("isPri", False),
            x=part.get("xPoint"),
            y=part.get("yPoint"),
            width=part.get("width"),
            height=part.get("height"),
        ))

    # Map legend
    legend = legend_data.get("data", legend_data) if legend_data else {}

    legend_past = []
    for item in (legend.get("past", []) if isinstance(legend, dict) else []):
        criteria_code = item.get("perfFrameCriteria", "")
        legend_past.append(AutohubCarDiagramLegendItem(
            name=item.get("frameEvalNmKo"),
            name_en=item.get("frameEvalNmEn"),
            color=LEGEND_COLORS.get(criteria_code, "#ccc"),
            cls=criteria_code,
        ))

    legend_current = []
    for item in (legend.get("current", []) if isinstance(legend, dict) else []):
        criteria_code = item.get("perfFrameCriteria", "")
        legend_current.append(AutohubCarDiagramLegendItem(
            name=item.get("frameEvalNmKo"),
            name_en=item.get("frameEvalNmEn"),
            color=LEGEND_COLORS.get(criteria_code, "#ccc"),
            cls=criteria_code,
        ))

    return AutohubCarDiagram(
        frame_draw_url=frame_draw_url,
        parts=parts,
        legend_past=legend_past,
        legend_current=legend_current,
    )


def map_brands(api_data: dict) -> List[AutohubBrandsGroup]:
    """Map hierarchical brands API response."""
    data = api_data.get("data", api_data)
    if not isinstance(data, list):
        data = [data] if data else []

    groups = []
    for group in data:
        brand_items = []
        for brand in group.get("brandList", []):
            model_items = []
            for model in brand.get("modelList", []):
                detail_items = []
                for detail in model.get("modelDetailList", []):
                    detail_items.append(AutohubModelDetailItem(
                        modelDetailId=detail.get("modelDetailId"),
                        modelDetailNm=detail.get("modelDetailNm"),
                        modelDetailNmEn=detail.get("modelDetailNmEn"),
                        modelDetailCnt=detail.get("modelDetailCnt"),
                    ))
                model_items.append(AutohubModelItem(
                    modelId=model.get("modelId"),
                    modelNm=model.get("modelNm"),
                    modelNmEn=model.get("modelNmEn"),
                    modelCnt=model.get("modelCnt"),
                    modelDetailList=detail_items,
                ))
            brand_items.append(AutohubBrandItem(
                brandId=brand.get("brandId"),
                brandNm=brand.get("brandNm"),
                brandNmEn=brand.get("brandNmEn"),
                brandCnt=brand.get("brandCnt"),
                modelList=model_items,
            ))
        groups.append(AutohubBrandsGroup(
            carOrigin=group.get("carOrigin"),
            brandList=brand_items,
        ))

    return groups
