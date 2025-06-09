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


class AutohubResponse(BaseModel):
    """Ответ API с данными Autohub"""

    success: bool = Field(..., description="Успешность выполнения запроса")
    message: str = Field(..., description="Сообщение о результате")
    total_count: int = Field(0, description="Общее количество найденных автомобилей")
    cars: List[AutohubCar] = Field(
        default_factory=list, description="Список автомобилей"
    )

    # Информация о пагинации
    current_page: int = Field(1, description="Текущая страница")
    page_size: int = Field(20, description="Размер страницы")
    total_pages: Optional[int] = Field(None, description="Общее количество страниц")
    has_next_page: bool = Field(False, description="Есть ли следующая страница")
    has_prev_page: bool = Field(False, description="Есть ли предыдущая страница")

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
