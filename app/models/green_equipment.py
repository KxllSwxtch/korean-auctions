"""
Pydantic models for Green Heavy Equipment (4396200.com)
Models for both list endpoint and equipment details endpoint
"""

from pydantic import BaseModel, Field
from typing import Optional, List


# ============================================
# Equipment Categories
# ============================================

EQUIPMENT_CATEGORIES = {
    "100": {"ko": "굴삭기/어태치부속", "en": "Excavators & Attachments", "ru": "Экскаваторы и навесное"},
    "101": {"ko": "덤프트럭/추레라", "en": "Dump Trucks & Trailers", "ru": "Самосвалы и прицепы"},
    "102": {"ko": "믹서트럭/펌프카", "en": "Mixer Trucks & Pump Cars", "ru": "Миксеры и бетононасосы"},
    "103": {"ko": "지게차/하이랜더", "en": "Forklifts & Highlanders", "ru": "Погрузчики"},
    "104": {"ko": "압롤/진게/물차", "en": "Armroll/Hook Lift/Water Trucks", "ru": "Мультилифт/Водовозы"},
    "105": {"ko": "카고/냉동/탑차", "en": "Cargo/Refrigerated/Box Trucks", "ru": "Фургоны и рефрижераторы"},
    "106": {"ko": "크레인/카고그레인", "en": "Cranes & Cargo Cranes", "ru": "Краны"},
    "107": {"ko": "로더/도자/그레다", "en": "Loaders/Dozers/Graders", "ru": "Бульдозеры и грейдеры"},
    "108": {"ko": "피니셔/로울러", "en": "Finishers & Rollers", "ru": "Асфальтоукладчики и катки"},
    "109": {"ko": "크락샤/배차플랜트", "en": "Crushers & Batching Plants", "ru": "Дробилки и бетонные заводы"},
    "110": {"ko": "콤푸/드릴/항타기", "en": "Compressors/Drills/Pile Drivers", "ru": "Компрессоры и сваебойки"},
    "111": {"ko": "기타건설기계", "en": "Other Construction Equipment", "ru": "Другая техника"},
}

# ============================================
# Equipment Subcategories
# ============================================

EQUIPMENT_SUBCATEGORIES = {
    "100": [  # Excavators & Attachments
        {"code": "100100", "ko": "굴삭기 1.3 ㎥ 이상", "en": "Large Excavators 1.3m³+", "ru": "Большие экскаваторы 1.3м³+"},
        {"code": "100101", "ko": "굴삭기 1.0 ㎥ 이상", "en": "Medium-Large 1.0m³+", "ru": "Средне-большие 1.0м³+"},
        {"code": "100102", "ko": "굴삭기 0.4~0.9 ㎥", "en": "Medium 0.4-0.9m³", "ru": "Средние 0.4-0.9м³"},
        {"code": "100103", "ko": "굴삭기 0.3 ㎥ 이하", "en": "Small 0.3m³-", "ru": "Малые 0.3м³-"},
        {"code": "100104", "ko": "미니굴삭기", "en": "Mini Excavators", "ru": "Мини экскаваторы"},
        {"code": "100105", "ko": "굴삭기타이어식", "en": "Wheel Excavators", "ru": "Колесные экскаваторы"},
        {"code": "100106", "ko": "어태치먼트", "en": "Attachments", "ru": "Навесное оборудование"},
        {"code": "100107", "ko": "굴삭기부속", "en": "Excavator Parts", "ru": "Запчасти"},
    ],
    "101": [  # Dump Trucks & Trailers
        {"code": "101100", "ko": "덤프트럭 19톤 이상", "en": "Dump Trucks 19t+", "ru": "Самосвалы 19т+"},
        {"code": "101101", "ko": "덤프트럭 16톤 이하", "en": "Dump Trucks 16t-", "ru": "Самосвалы 16т-"},
        {"code": "101102", "ko": "덤프트럭 10톤 이하", "en": "Dump Trucks 10t-", "ru": "Самосвалы 10т-"},
        {"code": "101103", "ko": "트레일러", "en": "Trailers", "ru": "Прицепы"},
        {"code": "101104", "ko": "추레라", "en": "Tractors", "ru": "Тягачи"},
        {"code": "101105", "ko": "셀프로다", "en": "Self-loaders", "ru": "Самопогрузчики"},
        {"code": "101106", "ko": "덤프추레라 부속", "en": "Dump/Trailer Parts", "ru": "Запчасти"},
    ],
    "102": [  # Mixer Trucks & Pump Cars
        {"code": "102100", "ko": "믹서트럭", "en": "Mixer Trucks", "ru": "Миксеры"},
        {"code": "102101", "ko": "펌프카", "en": "Pump Cars", "ru": "Бетононасосы"},
        {"code": "102102", "ko": "숏크리트", "en": "Shotcrete", "ru": "Торкрет-машины"},
        {"code": "102103", "ko": "몰리,포터블", "en": "Portable Mixers", "ru": "Портативные миксеры"},
        {"code": "102104", "ko": "믹서트럭 펌프카 부속", "en": "Mixer/Pump Parts", "ru": "Запчасти"},
    ],
    "103": [  # Forklifts & Highlanders
        {"code": "103100", "ko": "지게차10톤 이상", "en": "Forklifts 10t+", "ru": "Погрузчики 10т+"},
        {"code": "103101", "ko": "지게차 6톤 이상", "en": "Forklifts 6t+", "ru": "Погрузчики 6т+"},
        {"code": "103102", "ko": "지게차 5톤 이하", "en": "Forklifts 5t-", "ru": "Погрузчики 5т-"},
        {"code": "103103", "ko": "하이랜더", "en": "Highlanders", "ru": "Хайлендеры"},
        {"code": "103104", "ko": "전동지게차", "en": "Electric Forklifts", "ru": "Электропогрузчики"},
        {"code": "103105", "ko": "지게차부속", "en": "Forklift Parts", "ru": "Запчасти"},
        {"code": "103106", "ko": "고소작업차 시저형", "en": "Scissor Lifts", "ru": "Ножничные подъёмники"},
        {"code": "103107", "ko": "고소작업차 붐형", "en": "Boom Lifts", "ru": "Телескопические подъёмники"},
    ],
    "104": [  # Armroll / Hook Lift / Water Trucks
        {"code": "104100", "ko": "압롤", "en": "Armroll", "ru": "Мультилифт"},
        {"code": "104101", "ko": "진게,압착", "en": "Hook Lift / Compactor", "ru": "Крюковой / Пресс"},
        {"code": "104102", "ko": "청소특장", "en": "Cleaning Trucks", "ru": "Уборочные машины"},
        {"code": "104103", "ko": "살수차", "en": "Water Sprinklers", "ru": "Поливомоечные"},
        {"code": "104104", "ko": "탱크로리", "en": "Tank Trucks", "ru": "Автоцистерны"},
        {"code": "104105", "ko": "압롤부속", "en": "Armroll Parts", "ru": "Запчасти"},
    ],
    "105": [  # Cargo / Refrigerated / Box Trucks
        {"code": "105100", "ko": "트럭15톤 이상", "en": "Trucks 15t+", "ru": "Грузовики 15т+"},
        {"code": "105101", "ko": "트럭14톤 이하", "en": "Trucks 14t-", "ru": "Грузовики 14т-"},
        {"code": "105102", "ko": "트럭 7톤 이하", "en": "Trucks 7t-", "ru": "Грузовики 7т-"},
        {"code": "105103", "ko": "윙바디", "en": "Wing Body", "ru": "Бортовые с тентом"},
        {"code": "105104", "ko": "냉동차", "en": "Refrigerated Trucks", "ru": "Рефрижераторы"},
        {"code": "105105", "ko": "각종탑차", "en": "Box Trucks", "ru": "Фургоны"},
    ],
    "106": [  # Cranes & Cargo Cranes
        {"code": "106100", "ko": "크롤라크레인", "en": "Crawler Cranes", "ru": "Гусеничные краны"},
        {"code": "106101", "ko": "트럭식크레인", "en": "Truck Cranes", "ru": "Автокраны"},
        {"code": "106102", "ko": "맹꽁이(RT)", "en": "Rough Terrain Cranes", "ru": "Краны RT"},
        {"code": "106103", "ko": "카고크레인", "en": "Cargo Cranes", "ru": "Грузовые краны"},
        {"code": "106104", "ko": "타워/해상용", "en": "Tower/Marine Cranes", "ru": "Башенные/Морские"},
        {"code": "106105", "ko": "찝게/오가", "en": "Grapple/Auger", "ru": "Грейферы/Буры"},
        {"code": "106106", "ko": "크레인부속", "en": "Crane Parts", "ru": "Запчасти"},
    ],
    "107": [  # Loaders / Dozers / Graders
        {"code": "107100", "ko": "페이로다", "en": "Wheel Loaders", "ru": "Фронтальные погрузчики"},
        {"code": "107101", "ko": "미니로다", "en": "Mini Loaders", "ru": "Мини погрузчики"},
        {"code": "107102", "ko": "불도자", "en": "Bulldozers", "ru": "Бульдозеры"},
        {"code": "107103", "ko": "쇼벨", "en": "Shovels", "ru": "Экскаваторы-погрузчики"},
        {"code": "107104", "ko": "그레이다", "en": "Graders", "ru": "Грейдеры"},
        {"code": "107105", "ko": "기타콤팩터등", "en": "Compactors & Others", "ru": "Катки и другое"},
    ],
    "108": [  # Finishers & Rollers
        {"code": "108100", "ko": "아스팔트피니셔/살포기/파쇄기", "en": "Asphalt Pavers/Spreaders", "ru": "Асфальтоукладчики"},
        {"code": "108101", "ko": "로울러", "en": "Rollers", "ru": "Катки"},
    ],
    "109": [  # Crushers & Batching Plants
        {"code": "109100", "ko": "AP/BP플랜트", "en": "Asphalt/Batch Plants", "ru": "Асфальтобетонные заводы"},
        {"code": "109101", "ko": "크락샤플랜트", "en": "Crusher Plants", "ru": "Дробильные комплексы"},
        {"code": "109102", "ko": "선별기,샌드밀", "en": "Screeners/Sand Mills", "ru": "Сортировочные/Мельницы"},
        {"code": "109103", "ko": "파일,흄관,벽돌", "en": "Piles/Pipes/Bricks", "ru": "Сваи/Трубы/Кирпич"},
        {"code": "109104", "ko": "준설,바지선,샌드", "en": "Dredging/Barges/Sand", "ru": "Земснаряды/Баржи"},
    ],
    "110": [  # Compressors / Drills / Pile Drivers
        {"code": "110100", "ko": "콤푸,드릴,굴착장비", "en": "Compressors/Drills", "ru": "Компрессоры/Буры"},
        {"code": "110101", "ko": "오가,항타기,디포", "en": "Augers/Pile Drivers", "ru": "Сваебойки"},
        {"code": "110102", "ko": "콤푸 오가 등 부속", "en": "Parts", "ru": "Запчасти"},
    ],
    "111": [  # Other Construction Equipment
        {"code": "111100", "ko": "기타건설기계", "en": "Other Equipment", "ru": "Другая техника"},
    ],
}


EQUIPMENT_MANUFACTURERS = {
    "현대": {"ko": "현대", "en": "Hyundai", "ru": "Hyundai"},
    "대우": {"ko": "대우", "en": "Daewoo", "ru": "Daewoo"},
    "두산": {"ko": "두산", "en": "Doosan", "ru": "Doosan"},
    "삼성": {"ko": "삼성", "en": "Samsung", "ru": "Samsung"},
    "볼보": {"ko": "볼보", "en": "Volvo", "ru": "Volvo"},
    "한라": {"ko": "한라", "en": "Halla", "ru": "Halla"},
    "코마스": {"ko": "코마스", "en": "Komatsu", "ru": "Komatsu"},
    "히타치": {"ko": "히타치", "en": "Hitachi", "ru": "Hitachi"},
    "코벨코": {"ko": "코벨코", "en": "Kobelco", "ru": "Kobelco"},
    "캐타필라": {"ko": "캐타필라", "en": "Caterpillar", "ru": "Caterpillar"},
    "얀마": {"ko": "얀마", "en": "Yanmar", "ru": "Yanmar"},
    "기타": {"ko": "기타", "en": "Other", "ru": "Другое"},
    "I.H.I": {"ko": "I.H.I", "en": "IHI", "ru": "IHI"},
}


# ============================================
# List API Models
# ============================================

class GreenEquipment(BaseModel):
    """Equipment listing model from category page"""
    id: str = Field(..., description="Equipment ID (pid)")
    category_code: str = Field(..., description="Category code (100-111)")
    category_name: Optional[str] = Field(None, description="Category name in Korean")
    subcategory_code: Optional[str] = Field(None, description="Subcategory code")
    subcategory_name: Optional[str] = Field(None, description="Subcategory name in Korean")
    model: str = Field(..., description="Model name/title")
    price: int = Field(..., description="Price in 만원 (10,000 KRW)")
    price_krw: int = Field(..., description="Price in KRW")
    condition: Optional[str] = Field(None, description="Condition grade (A+급, A급, etc.)")
    year: Optional[int] = Field(None, description="Manufacturing year")
    manufacturer: Optional[str] = Field(None, description="Manufacturer name")
    image_url: Optional[str] = Field(None, description="Main image URL")
    images: List[str] = Field(default_factory=list, description="List of image URLs")
    seller_phone: Optional[str] = Field(None, description="Seller phone number")
    seller_name: Optional[str] = Field(None, description="Seller/company name")
    location: Optional[str] = Field(None, description="Equipment location")
    description: Optional[str] = Field(None, description="Short description")
    url: Optional[str] = Field(None, description="Detail page URL")


class GreenEquipmentListResponse(BaseModel):
    """Response model for equipment list endpoint"""
    count: int = Field(..., description="Total number of equipment matching the query")
    items: List[GreenEquipment] = Field(default_factory=list, description="List of equipment")
    category_code: Optional[str] = Field(None, description="Current category code")
    category_name: Optional[str] = Field(None, description="Current category name")
    page: int = Field(1, description="Current page number")
    per_page: int = Field(20, description="Items per page")
    success: bool = True
    message: Optional[str] = None


# ============================================
# Details API Models
# ============================================

class GreenEquipmentSpec(BaseModel):
    """Equipment specifications"""
    model: Optional[str] = Field(None, description="Model name")
    year: Optional[int] = Field(None, description="Manufacturing year")
    manufacturer: Optional[str] = Field(None, description="Manufacturer")
    hours: Optional[int] = Field(None, description="Operating hours")
    capacity: Optional[str] = Field(None, description="Capacity/tonnage")
    engine: Optional[str] = Field(None, description="Engine info")
    weight: Optional[str] = Field(None, description="Operating weight")
    bucket_capacity: Optional[str] = Field(None, description="Bucket capacity")


class GreenEquipmentSeller(BaseModel):
    """Seller information"""
    name: Optional[str] = Field(None, description="Seller/company name")
    phone: Optional[str] = Field(None, description="Primary phone")
    phone2: Optional[str] = Field(None, description="Secondary phone")
    address: Optional[str] = Field(None, description="Address")
    location: Optional[str] = Field(None, description="Region/location")


class GreenEquipmentDetails(BaseModel):
    """Full equipment details response"""
    id: str = Field(..., description="Equipment ID")
    category_code: str = Field(..., description="Category code")
    category_name: Optional[str] = Field(None, description="Category name")
    subcategory_code: Optional[str] = Field(None, description="Subcategory code")
    subcategory_name: Optional[str] = Field(None, description="Subcategory name")
    model: str = Field(..., description="Model name/title")
    price: int = Field(..., description="Price in 만원")
    price_krw: int = Field(..., description="Price in KRW")
    condition: Optional[str] = Field(None, description="Condition grade")
    spec: Optional[GreenEquipmentSpec] = Field(None, description="Equipment specifications")
    seller: Optional[GreenEquipmentSeller] = Field(None, description="Seller information")
    images: List[str] = Field(default_factory=list, description="List of image URLs")
    description: Optional[str] = Field(None, description="Full description")
    registration_date: Optional[str] = Field(None, description="Registration date")
    views: Optional[int] = Field(None, description="View count")
    url: str = Field(..., description="Original listing URL")


class GreenEquipmentDetailsResponse(BaseModel):
    """Wrapper response for equipment details"""
    success: bool = True
    message: Optional[str] = None
    data: Optional[GreenEquipmentDetails] = None


# ============================================
# Category Response Models
# ============================================

class CategoryInfo(BaseModel):
    """Category information"""
    code: str
    name_ko: str
    name_en: str
    name_ru: str


class SubcategoryInfo(BaseModel):
    """Subcategory information"""
    code: str
    name_ko: str
    parent_code: str


class CategoriesResponse(BaseModel):
    """Response model for categories endpoint"""
    success: bool = True
    message: Optional[str] = None
    categories: List[CategoryInfo] = Field(default_factory=list)


# ============================================
# Error Response Model
# ============================================

class GreenEquipmentError(BaseModel):
    """Error response model"""
    success: bool = False
    message: str
    detail: Optional[str] = None
