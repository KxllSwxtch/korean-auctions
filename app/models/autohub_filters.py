from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class AutohubSortOrder(str, Enum):
    """Порядок сортировки"""
    ENTRY = "entry"  # По номеру выставки
    PRICE = "price"  # По цене
    YEAR = "year"    # По году
    MILEAGE = "milg"  # По пробегу


class AutohubAuctionResult(str, Enum):
    """Результат аукциона"""
    ALL = ""           # Все
    SOLD = "Y"         # Продано (낙찰 & 후상담낙찰)
    UNSOLD = "N"       # Не продано (유찰 & 낙찰취소)
    NOT_HELD = "none"  # Не проводился (미실시)


class AutohubLane(str, Enum):
    """Полоса аукциона"""
    ALL = ""    # Все
    A = "A"     # A레인
    B = "B"     # B레인
    C = "C"     # C레인
    D = "D"     # D레인


class AutohubYesNoAll(str, Enum):
    """Да/Нет/Все"""
    ALL = "ALL"
    YES = "Y"
    NO = "N"


class AutohubSearchType(str, Enum):
    """Тип поиска по номеру"""
    ENTRY = "E"  # По номеру выставки
    CAR = "C"    # По номеру автомобиля


class AutohubFuelType(str, Enum):
    """Тип топлива"""
    ALL = ""         # Все
    GASOLINE = "01"  # 휘발유
    DIESEL = "02"    # 경유
    LPG = "03"       # LPG
    HYBRID = "04"    # 하이브리드
    ELECTRIC = "05"  # 전기
    OTHER = "06"     # 기타


class AutohubManufacturer(BaseModel):
    """Производитель автомобилей AutoHub"""
    code: str = Field(..., description="Код производителя (например, 'KA')")
    name: str = Field(..., description="Название производителя (например, '기아')")
    name_en: Optional[str] = Field(None, description="Название на английском")


class AutohubModel(BaseModel):
    """Модель автомобиля AutoHub"""
    manufacturer_code: str = Field(..., description="Код производителя")
    model_code: str = Field(..., description="Код модели (например, 'KA01')")
    name: str = Field(..., description="Название модели")


class AutohubGeneration(BaseModel):
    """Поколение автомобиля AutoHub"""
    model_code: str = Field(..., description="Код модели")
    generation_code: str = Field(..., description="Код поколения (например, '008')")
    detail_code: str = Field(..., description="Детальный код (например, 'K01')")
    name: str = Field(..., description="Название поколения")


class AutohubConfiguration(BaseModel):
    """Конфигурация автомобиля AutoHub"""
    generation_code: str = Field(..., description="Код поколения")
    configuration_code: str = Field(..., description="Код конфигурации (например, '001')")
    name: str = Field(..., description="Название конфигурации (например, 'LPG 2WD')")


class AutohubAuctionSession(BaseModel):
    """Сессия аукциона AutoHub"""
    auction_no: str = Field(..., description="Номер аукциона (например, '1332')")
    auction_date: str = Field(..., description="Дата аукциона (YYYY-MM-DD)")
    auction_code: str = Field(..., description="Код аукциона (например, 'AC202507020001')")
    auction_title: str = Field(..., description="Название аукциона")
    is_active: bool = Field(True, description="Активна ли сессия")


class AutohubSearchRequest(BaseModel):
    """Запрос поиска автомобилей AutoHub с фильтрами"""
    
    # Основные параметры аукциона
    auction_no: Optional[str] = Field(None, description="Номер аукциона")
    auction_date: Optional[str] = Field(None, description="Дата аукциона (YYYY-MM-DD)")
    auction_code: Optional[str] = Field(None, description="Код аукциона")
    
    # Фильтры по автомобилю
    manufacturer_code: Optional[str] = Field(None, description="Код производителя")
    model_code: Optional[str] = Field(None, description="Код модели")
    generation_code: Optional[str] = Field(None, description="Код поколения")
    detail_code: Optional[str] = Field(None, description="Детальный код")
    
    # Фильтры по характеристикам
    fuel_type: Optional[AutohubFuelType] = Field(None, description="Тип топлива")
    extended_warranty: Optional[AutohubYesNoAll] = Field(
        AutohubYesNoAll.ALL, description="Расширенная гарантия"
    )
    
    # Фильтры по году и пробегу
    year_from: Optional[int] = Field(None, ge=1990, le=2030, description="Год от")
    year_to: Optional[int] = Field(None, ge=1990, le=2030, description="Год до")
    mileage_from: Optional[int] = Field(None, ge=0, description="Пробег от (км)")
    mileage_to: Optional[int] = Field(None, ge=0, description="Пробег до (км)")
    
    # Фильтры по цене (в 만원)
    price_from: Optional[int] = Field(None, ge=0, description="Цена от (만원)")
    price_to: Optional[int] = Field(None, ge=0, description="Цена до (만원)")
    
    # Фильтры по статусу
    auction_result: Optional[AutohubAuctionResult] = Field(
        None, description="Результат аукциона"
    )
    lane: Optional[AutohubLane] = Field(None, description="Полоса аукциона")
    
    # Фильтры по номерам
    entry_no_assigned: Optional[AutohubYesNoAll] = Field(
        AutohubYesNoAll.ALL, description="Назначен ли номер выставки"
    )
    parking_no_assigned: Optional[AutohubYesNoAll] = Field(
        AutohubYesNoAll.YES, description="Назначен ли парковочный номер"
    )
    
    # Поиск по номеру
    search_type: Optional[AutohubSearchType] = Field(
        AutohubSearchType.ENTRY, description="Тип поиска по номеру"
    )
    search_number: Optional[str] = Field(None, description="Номер для поиска (4 цифры)")
    
    # Конкретные номера
    entry_number: Optional[str] = Field(None, description="Номер выставки")
    parking_number: Optional[str] = Field(None, description="Парковочный номер")
    
    # SOH диагностика
    soh_diagnosis: Optional[AutohubYesNoAll] = Field(
        AutohubYesNoAll.ALL, description="SOH диагностика"
    )
    
    # Сортировка и пагинация
    sort_order: Optional[AutohubSortOrder] = Field(
        AutohubSortOrder.ENTRY, description="Порядок сортировки"
    )
    page: int = Field(1, ge=1, description="Номер страницы")
    page_size: int = Field(10, ge=1, le=100, description="Размер страницы")
    
    def to_autohub_params(self) -> Dict[str, Any]:
        """Преобразует параметры запроса в формат AutoHub"""
        params = {
            "i_iNowPageNo": str(self.page),
            "i_iPageSize": str(self.page_size),
            "i_sSortFlag": self.sort_order.value if self.sort_order else "entry",
            "i_entryNoYn": self.entry_no_assigned.value if self.entry_no_assigned else "ALL",
            "i_parkingNoYn": self.parking_no_assigned.value if self.parking_no_assigned else "Y",
            "i_bojeongYn": self.extended_warranty.value if self.extended_warranty else "ALL",
            "i_sohYn": self.soh_diagnosis.value if self.soh_diagnosis else "ALL",
            "tabActiveIdx": "2",  # Вкладка 상세검색
            "listTabActiveIdx": "1",
            "pageFlag": "Y",
            "i_sReturnUrl": "/newfront/receive/rc/receive_rc_list.do",
            # Дополнительные обязательные параметры
            "i_sReturnParam": "",
            "i_sActionFlag": "",
            "i_sReceiveCd": "",
            "i_sMainModel": "",
            "i_sMakerCodeD": "",
            "i_sCarName1CodeD": "",
            "i_sAucNoTempStr": "",
            "i_sMakerCodeD1": "",
            "i_sCarName1CodeD1": "",
            "i_entryNoYn0": "ALL",
            "i_parkingNoYn0": "Y",
            "noSelect": "E",
            "i_sNo": "",
            "entrySort": self.sort_order.value if self.sort_order else "entry",
            "receivecd": "",  # Will be filled if we have it
        }
        
        # Параметры аукциона
        if self.auction_no:
            params["i_sAucNo"] = self.auction_no
        if self.auction_date:
            params["i_sStartDt"] = self.auction_date
        if self.auction_code:
            params["i_sAucCode"] = self.auction_code
            
        # Добавляем специальные параметры если есть информация об аукционе
        if self.auction_no and self.auction_date and self.auction_code:
            auction_temp = f"{self.auction_no}@@{self.auction_date}@@{self.auction_code}"
            params["i_sAucNoTemp1"] = auction_temp
            params["i_sAucNoTemp2"] = auction_temp
            
        # Параметры автомобиля
        if self.manufacturer_code:
            params["i_sMakerCode"] = self.manufacturer_code
        if self.model_code:
            params["i_sCarName1Code"] = self.model_code
        if self.generation_code:
            params["i_sCarName2Code"] = self.generation_code
        if self.detail_code:
            params["i_sCarName3Code"] = self.detail_code
            
        # Характеристики
        if self.fuel_type:
            params["i_sFueltypecode"] = self.fuel_type.value
            
        # Год
        if self.year_from:
            params["i_sCarYearStr"] = str(self.year_from)
        if self.year_to:
            params["i_sCarYearEnd"] = str(self.year_to)
            
        # Пробег
        if self.mileage_from:
            params["i_sDriveKmShortDescStr"] = str(self.mileage_from)
        if self.mileage_to:
            params["i_sDriveKmShortDescEnd"] = str(self.mileage_to)
            
        # Цена
        if self.price_from:
            params["i_sPricecStr"] = str(self.price_from)
        if self.price_to:
            params["i_sPricecEnd"] = str(self.price_to)
            
        # Статус
        if self.auction_result:
            params["i_sAucResult"] = self.auction_result.value
        if self.lane:
            params["i_sAucLane"] = self.lane.value
            
        # Поиск по номеру
        if self.search_type and self.search_number:
            params["noSelect"] = self.search_type.value
            params["i_sNo"] = self.search_number
            
        # Конкретные номера
        if self.entry_number:
            params["i_sEntryNo"] = self.entry_number
        if self.parking_number:
            params["i_sParkingNo"] = self.parking_number
            
        # Убираем None значения
        return {k: v for k, v in params.items() if v is not None}


class AutohubManufacturersResponse(BaseModel):
    """Ответ со списком производителей"""
    success: bool = True
    message: str = "Список производителей получен успешно"
    manufacturers: List[AutohubManufacturer] = Field(default_factory=list)
    total_count: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class AutohubModelsResponse(BaseModel):
    """Ответ со списком моделей"""
    success: bool = True
    message: str = "Список моделей получен успешно"
    models: List[AutohubModel] = Field(default_factory=list)
    manufacturer_code: Optional[str] = None
    total_count: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class AutohubGenerationsResponse(BaseModel):
    """Ответ со списком поколений"""
    success: bool = True
    message: str = "Список поколений получен успешно"
    generations: List[AutohubGeneration] = Field(default_factory=list)
    model_code: Optional[str] = None
    total_count: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class AutohubAuctionSessionsResponse(BaseModel):
    """Ответ со списком сессий аукциона"""
    success: bool = True
    message: str = "Список сессий аукциона получен успешно"
    sessions: List[AutohubAuctionSession] = Field(default_factory=list)
    current_session: Optional[AutohubAuctionSession] = None
    total_count: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class AutohubConfigurationsResponse(BaseModel):
    """Ответ со списком конфигураций"""
    success: bool = True
    message: str = "Список конфигураций получен успешно"
    configurations: List[AutohubConfiguration] = Field(default_factory=list)
    generation_code: Optional[str] = None
    total_count: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class AutohubFilterInfo(BaseModel):
    """Информация о доступных фильтрах"""
    manufacturers: List[Dict[str, str]] = Field(
        default_factory=list, description="Список производителей"
    )
    fuel_types: List[Dict[str, str]] = Field(
        default_factory=list, description="Типы топлива"
    )
    lanes: List[Dict[str, str]] = Field(
        default_factory=list, description="Полосы аукциона"
    )
    auction_results: List[Dict[str, str]] = Field(
        default_factory=list, description="Результаты аукциона"
    )
    year_range: Dict[str, int] = Field(
        default={"min": 1990, "max": 2025}, description="Диапазон годов"
    )
    mileage_options: List[int] = Field(
        default_factory=list, description="Варианты пробега"
    )
    price_options: List[int] = Field(
        default_factory=list, description="Варианты цен"
    )


# Статические данные производителей AutoHub
AUTOHUB_MANUFACTURERS = [
    AutohubManufacturer(code="KA", name="기아", name_en="Kia"),
    AutohubManufacturer(code="HD", name="현대", name_en="Hyundai"),
    AutohubManufacturer(code="GN", name="제네시스", name_en="Genesis"),
    AutohubManufacturer(code="CV", name="쉐보레", name_en="Chevrolet"),
    AutohubManufacturer(code="RN", name="르노삼성", name_en="Renault Samsung"),
    AutohubManufacturer(code="SY", name="쌍용", name_en="SsangYong"),
    AutohubManufacturer(code="BZ", name="벤츠", name_en="Mercedes-Benz"),
    AutohubManufacturer(code="BM", name="BMW", name_en="BMW"),
    AutohubManufacturer(code="AD", name="아우디", name_en="Audi"),
    AutohubManufacturer(code="VW", name="폭스바겐", name_en="Volkswagen"),
    AutohubManufacturer(code="FD", name="포드", name_en="Ford"),
    AutohubManufacturer(code="TY", name="토요타", name_en="Toyota"),
    AutohubManufacturer(code="HD", name="혼다", name_en="Honda"),
    AutohubManufacturer(code="NS", name="닛산", name_en="Nissan"),
    AutohubManufacturer(code="MZ", name="마쯔다", name_en="Mazda"),
    AutohubManufacturer(code="PS", name="푸조", name_en="Peugeot"),
    AutohubManufacturer(code="VL", name="볼보", name_en="Volvo"),
    AutohubManufacturer(code="JG", name="재규어", name_en="Jaguar"),
    AutohubManufacturer(code="LR", name="랜드로버", name_en="Land Rover"),
    AutohubManufacturer(code="PO", name="포르쉐", name_en="Porsche"),
    AutohubManufacturer(code="JP", name="지프", name_en="Jeep"),
    AutohubManufacturer(code="TS", name="테슬라", name_en="Tesla"),
    AutohubManufacturer(code="LX", name="렉서스", name_en="Lexus"),
    AutohubManufacturer(code="MN", name="미니", name_en="Mini"),
    AutohubManufacturer(code="FT", name="피아트", name_en="Fiat"),
    AutohubManufacturer(code="IF", name="인피니티", name_en="Infiniti"),
    AutohubManufacturer(code="MS", name="미쯔비시", name_en="Mitsubishi"),
    AutohubManufacturer(code="CT", name="시트로엥", name_en="Citroen"),
    AutohubManufacturer(code="CD", name="캐딜락", name_en="Cadillac"),
    AutohubManufacturer(code="LN", name="링컨", name_en="Lincoln"),
    AutohubManufacturer(code="DS", name="DS", name_en="DS"),
    AutohubManufacturer(code="MR", name="마세라티", name_en="Maserati"),
    AutohubManufacturer(code="FR", name="페라리", name_en="Ferrari"),
    AutohubManufacturer(code="LB", name="람보르기니", name_en="Lamborghini"),
    AutohubManufacturer(code="BT", name="벤틀리", name_en="Bentley"),
    AutohubManufacturer(code="RR", name="롤스로이스", name_en="Rolls-Royce"),
    AutohubManufacturer(code="SM", name="스마트", name_en="Smart"),
    AutohubManufacturer(code="AC", name="아큐라", name_en="Acura"),
    AutohubManufacturer(code="AS", name="애스턴마틴", name_en="Aston Martin"),
    AutohubManufacturer(code="MC", name="맥라렌", name_en="McLaren"),
    AutohubManufacturer(code="MY", name="마이바흐", name_en="Maybach"),
    AutohubManufacturer(code="GMC", name="GMC", name_en="GMC"),
    AutohubManufacturer(code="DG", name="닷지", name_en="Dodge"),
    AutohubManufacturer(code="CR", name="크라이슬러", name_en="Chrysler"),
    AutohubManufacturer(code="HM", name="험머", name_en="Hummer"),
    AutohubManufacturer(code="SZ", name="스즈키", name_en="Suzuki"),
    AutohubManufacturer(code="SB", name="스바루", name_en="Subaru"),
    AutohubManufacturer(code="OT", name="기타", name_en="Others"),
]

# Диапазоны пробега (в км)
AUTOHUB_MILEAGE_OPTIONS = [
    500, 1000, 2000, 3000, 4000, 5000, 10000, 15000, 20000, 25000, 30000,
    35000, 40000, 45000, 50000, 60000, 70000, 80000, 90000, 100000,
    120000, 140000, 160000, 180000, 200000, 250000, 300000
]

# Диапазоны цен (в 만원)
AUTOHUB_PRICE_OPTIONS = [
    100, 200, 300, 400, 500, 600, 700, 800, 900, 1000,
    1200, 1400, 1600, 1800, 2000, 2500, 3000, 3500, 4000,
    4500, 5000, 6000, 7000, 8000, 9000, 10000, 12000, 14000,
    16000, 18000, 20000, 30000
]