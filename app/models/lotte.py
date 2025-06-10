from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum


class FuelType(str, Enum):
    GASOLINE = "gasoline"
    DIESEL = "diesel"
    HYBRID = "hybrid"
    ELECTRIC = "electric"
    LPG = "lpg"
    UNKNOWN = "unknown"


class TransmissionType(str, Enum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    CVT = "cvt"
    UNKNOWN = "unknown"


class GradeType(str, Enum):
    A_A = "A/A"
    A_B = "A/B"
    A_C = "A/C"
    A_D = "A/D"
    B_A = "B/A"
    B_B = "B/B"
    B_C = "B/C"
    B_D = "B/D"
    C_A = "C/A"
    C_B = "C/B"
    C_C = "C/C"
    C_D = "C/D"
    D_A = "D/A"
    D_B = "D/B"
    D_C = "D/C"
    D_D = "D/D"
    UNKNOWN = "unknown"


class LotteCar(BaseModel):
    """Модель автомобиля с аукциона Lotte"""

    # Основная информация
    id: str = Field(..., description="Уникальный ID автомобиля")
    auction_number: str = Field(..., description="Номер на аукционе")
    lane: str = Field(..., description="Полоса (A, B, C, D)")
    license_plate: str = Field(..., description="Номерной знак")

    # Информация об автомобиле
    name: str = Field(..., description="Название автомобиля")
    model: str = Field(..., description="Модель")
    brand: str = Field(..., description="Марка")
    year: int = Field(..., description="Год выпуска", ge=1900, le=2030)

    # Технические характеристики
    mileage: int = Field(..., description="Пробег в км", ge=0)
    fuel_type: FuelType = Field(default=FuelType.UNKNOWN, description="Тип топлива")
    transmission: TransmissionType = Field(
        default=TransmissionType.UNKNOWN, description="Тип КПП"
    )
    engine_capacity: Optional[str] = Field(None, description="Объем двигателя")
    color: str = Field(..., description="Цвет")

    # Состояние и оценка
    grade: GradeType = Field(default=GradeType.UNKNOWN, description="Оценка состояния")

    # Финансовая информация
    starting_price: int = Field(
        ..., description="Стартовая цена в корейских вонах", ge=0
    )

    # Даты
    first_registration_date: Optional[str] = Field(
        None, description="Дата первой регистрации"
    )
    inspection_valid_until: Optional[str] = Field(
        None, description="Действие техосмотра до"
    )

    # Дополнительная информация
    usage_type: Optional[str] = Field(None, description="Тип использования")
    owner_info: Optional[str] = Field(None, description="Информация о владельце")
    vin_number: Optional[str] = Field(None, description="VIN номер")
    engine_model: Optional[str] = Field(None, description="Модель двигателя")

    # Изображения
    images: List[str] = Field(
        default_factory=list, description="Список URL изображений"
    )

    # Детали аукциона
    searchMngDivCd: Optional[str] = Field(None, description="Код управления поиском")
    searchMngNo: Optional[str] = Field(None, description="Номер управления поиском")
    searchExhiRegiSeq: Optional[str] = Field(
        None, description="Порядковый номер выставления"
    )


class LotteAuctionDate(BaseModel):
    """Модель даты аукциона Lotte"""

    auction_date: str = Field(..., description="Дата аукциона (YYYY-MM-DD)")
    year: int = Field(..., description="Год")
    month: int = Field(..., description="Месяц")
    day: int = Field(..., description="День")
    is_today: bool = Field(..., description="Является ли дата сегодняшней")
    is_future: bool = Field(..., description="Является ли дата будущей")
    raw_text: str = Field(..., description="Исходный текст даты")


class LotteResponse(BaseModel):
    """Модель ответа API для данных Lotte"""

    success: bool = Field(..., description="Успешность запроса")
    message: str = Field(..., description="Сообщение")

    # Информация о дате аукциона
    auction_date_info: Optional[LotteAuctionDate] = Field(
        None, description="Информация о дате аукциона"
    )

    # Данные автомобилей
    cars: List[LotteCar] = Field(default_factory=list, description="Список автомобилей")
    total_count: int = Field(default=0, description="Общее количество автомобилей")

    # Пагинация
    page: int = Field(default=1, description="Номер страницы")
    per_page: int = Field(default=20, description="Количество на странице")
    total_pages: int = Field(default=0, description="Общее количество страниц")

    # Информация о запросе
    timestamp: str = Field(..., description="Временная метка запроса")
    request_duration: Optional[float] = Field(
        None, description="Время выполнения запроса в секундах"
    )


class LotteError(BaseModel):
    """Модель ошибки API Lotte"""

    success: bool = Field(default=False, description="Успешность запроса")
    error_code: str = Field(..., description="Код ошибки")
    message: str = Field(..., description="Сообщение об ошибке")
    details: Optional[str] = Field(None, description="Детали ошибки")
    timestamp: str = Field(..., description="Временная метка ошибки")
