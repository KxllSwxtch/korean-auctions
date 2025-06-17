from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class CarStatus(str, Enum):
    """Статус автомобиля на аукционе"""

    REGISTERED = "출품등록"
    BIDDING = "입찰중"
    SOLD = "낙찰"
    UNSOLD = "유찰"
    WITHDRAWN = "취하"


class TransmissionType(str, Enum):
    """Тип трансмиссии"""

    AUTO = "오토"
    MANUAL = "수동"


class FuelType(str, Enum):
    """Тип топлива"""

    GASOLINE = "휘발유"
    DIESEL = "경유"
    ELECTRIC = "전기"
    HYBRID = "하이브리드"


class CarCondition(str, Enum):
    """Оценка состояния автомобиля"""

    EXCELLENT = "상"
    GOOD = "중"
    FAIR = "하"
    BC = "BC"
    CD = "CD"


class AutohubCar(BaseModel):
    """Модель автомобиля с аукциона Autohub"""

    # Основные идентификаторы
    car_id: str = Field(..., description="ID автомобиля в системе")
    auction_number: str = Field(..., description="Номер лота на аукционе")
    car_number: str = Field(..., description="Номер автомобиля")
    parking_number: str = Field(..., description="Номер парковочного места")
    lane: Optional[str] = Field(None, description="Номер полосы")

    # Основная информация об автомобиле
    title: str = Field(..., description="Название автомобиля")
    year: int = Field(..., description="Год выпуска")
    mileage: str = Field(..., description="Пробег")
    transmission: TransmissionType = Field(..., description="Тип трансмиссии")
    fuel_type: FuelType = Field(..., description="Тип топлива")

    # Дополнительная информация
    first_registration_date: Optional[str] = Field(
        None, description="Дата первой регистрации"
    )
    condition_grade: Optional[str] = Field(None, description="Оценка состояния")
    history: Optional[str] = Field(None, description="История использования")

    # Финансовая информация
    starting_price: Optional[int] = Field(
        None, description="Стартовая цена (в манвонах)"
    )
    current_price: Optional[int] = Field(None, description="Текущая цена")
    final_price: Optional[int] = Field(None, description="Финальная цена")

    # Статус
    status: CarStatus = Field(..., description="Статус на аукционе")
    auction_result: Optional[str] = Field(None, description="Результат аукциона")

    # Изображения
    main_image_url: Optional[HttpUrl] = Field(
        None, description="URL основного изображения"
    )
    additional_images: List[HttpUrl] = Field(
        default_factory=list, description="Дополнительные изображения"
    )

    # Метаданные
    parsed_at: datetime = Field(
        default_factory=datetime.now, description="Время парсинга"
    )

    # Дополнительные поля для детальной информации
    entry_number: str = Field(default="", description="Номер выставки")
    vin_number: str = Field(default="", description="VIN номер")
    engine_type: str = Field(default="", description="Тип двигателя")
    mileage_unclear: Optional[bool] = Field(
        False, description="Неопределенность пробега"
    )
    displacement: str = Field(default="", description="Объем двигателя")
    color: str = Field(default="", description="Цвет")
    color_changed: Optional[bool] = Field(False, description="Изменение цвета")
    vehicle_type: str = Field(default="", description="Тип транспортного средства")
    accident_history: Optional[str] = Field(None, description="История аварий")
    tax_type: str = Field(default="", description="Тип налогообложения")
    electric_certificate: Optional[str] = Field(
        None, description="Сертификат электромобиля"
    )


class AutohubResponse(BaseModel):
    """Ответ API с данными Autohub"""

    success: bool = Field(..., description="Успешность выполнения запроса")
    data: List[AutohubCar] = Field(
        default_factory=list, description="Список автомобилей"
    )
    error: Optional[str] = Field(None, description="Сообщение об ошибке")
    total_count: int = Field(0, description="Общее количество найденных автомобилей")

    # Информация о пагинации
    page: int = Field(1, description="Текущая страница")
    limit: int = Field(20, description="Размер страницы")

    parsed_at: datetime = Field(
        default_factory=datetime.now, description="Время парсинга"
    )


class AutohubError(BaseModel):
    """Модель ошибки при парсинге Autohub"""

    success: bool = Field(False, description="Успешность выполнения запроса")
    error_code: str = Field(..., description="Код ошибки")
    message: str = Field(..., description="Сообщение об ошибке")
    details: Optional[str] = Field(None, description="Дополнительные детали ошибки")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Время возникновения ошибки"
    )


class AutohubAuctionDate(BaseModel):
    """Дата аукциона Autohub"""

    date_str: str = Field(..., description="Строка с датой аукциона")


class AutohubPerformanceInfo(BaseModel):
    rating: str
    inspector: str
    stored_items: List[str]
    stored_items_present: str
    notes: str


class AutohubOptionInfo(BaseModel):
    convenience: List[str]
    safety: List[str]
    exterior: List[str]
    interior: List[str]


class AutohubImage(BaseModel):
    large_url: str
    small_url: str
    sequence: int


class AutohubCarDetail(BaseModel):
    # Основная информация
    title: str
    starting_price: str
    auction_number: str
    auction_date: str
    auction_title: str
    auction_code: str

    # Детальная информация об автомобиле
    car_info: AutohubCar

    # Оценка производительности
    performance_info: AutohubPerformanceInfo

    # Опции
    options: AutohubOptionInfo

    # Изображения
    images: List[AutohubImage]

    # Метаданные
    parsed_at: datetime
    source_url: str = "https://www.autohubauction.co.kr"


class AutohubCarDetailRequest(BaseModel):
    # Основные параметры запроса
    auction_number: str  # i_sAucNo
    auction_date: str  # i_sStartDt (format: YYYY-MM-DD)
    auction_title: str  # i_sAucTitle
    auction_code: str  # i_sAucCode
    receive_code: str  # receivecd

    # Опциональные параметры
    page_number: int = 1
    page_size: int = 10
    sort_flag: str = "entry"


class AutohubCarDetailResponse(BaseModel):
    success: bool
    data: Optional[AutohubCarDetail] = None
    error: Optional[str] = None
    request_params: AutohubCarDetailRequest
