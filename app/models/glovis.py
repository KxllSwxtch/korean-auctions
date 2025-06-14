from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class GlovisCarCondition(str, Enum):
    """Оценка состояния автомобиля Glovis"""

    A1 = "A/1"
    A2 = "A/2"
    A3 = "A/3"
    A4 = "A/4"
    A5 = "A/5"
    A6 = "A/6"
    A7 = "A/7"


class GlovisLocation(str, Enum):
    """Локации Glovis"""

    BUNDANG = "분당"
    SIHEUNG = "시화"
    YANGSAN = "양산"
    INCHEON = "인천"


class GlovisCar(BaseModel):
    """Модель автомобиля с аукциона Hyundai Glovis"""

    # Основные идентификаторы
    entry_number: str = Field(..., description="Номер выставки")
    car_name: str = Field(..., description="Название автомобиля")
    location: GlovisLocation = Field(..., description="Локация")
    lane: str = Field(..., description="Номер полосы")
    license_plate: str = Field(..., description="Номер автомобиля")

    # Детали автомобиля
    year: int = Field(..., description="Год выпуска")
    transmission: str = Field(..., description="Тип трансмиссии (A/T, M/T)")
    engine_volume: str = Field(..., description="Объем двигателя")
    mileage: str = Field(..., description="Пробег")
    color: str = Field(..., description="Цвет")
    fuel_type: str = Field(..., description="Тип топлива")
    usage_type: str = Field(
        ..., description="Тип использования (개인, 법인, 법인상품용)"
    )
    condition_grade: GlovisCarCondition = Field(..., description="Оценка состояния")

    # Аукционная информация
    auction_number: str = Field(..., description="Номер аукциона")
    starting_price: int = Field(..., description="Стартовая цена в манвонах")

    # Изображения
    main_image_url: Optional[HttpUrl] = Field(
        None, description="URL основного изображения"
    )

    # Внутренние идентификаторы (из HTML атрибутов)
    gn: str = Field(..., description="Внутренний идентификатор gn")
    rc: str = Field(..., description="Код региона")
    acc: str = Field(..., description="Код acc")
    atn: str = Field(..., description="Код atn")
    prodmancd: str = Field(..., description="Код производителя")
    reprcarcd: str = Field(..., description="Код модели")
    detacarcd: str = Field(..., description="Код детальной модели")
    cargradcd: str = Field(..., description="Код оценки")

    # Метаданные
    parsed_at: datetime = Field(
        default_factory=datetime.now, description="Время парсинга"
    )


class GlovisResponse(BaseModel):
    """Ответ API с данными Glovis"""

    success: bool = Field(..., description="Успешность выполнения запроса")
    message: str = Field(..., description="Сообщение о результате")
    total_count: int = Field(0, description="Общее количество найденных автомобилей")
    cars: List[GlovisCar] = Field(
        default_factory=list, description="Список автомобилей"
    )

    # Информация о пагинации
    current_page: int = Field(1, description="Текущая страница")
    page_size: int = Field(18, description="Размер страницы (по умолчанию 18)")
    total_pages: Optional[int] = Field(None, description="Общее количество страниц")
    has_next_page: bool = Field(False, description="Есть ли следующая страница")
    has_prev_page: bool = Field(False, description="Есть ли предыдущая страница")

    parsed_at: datetime = Field(
        default_factory=datetime.now, description="Время парсинга"
    )


class GlovisError(BaseModel):
    """Модель ошибки при парсинге Glovis"""

    success: bool = Field(False, description="Успешность выполнения запроса")
    error_code: str = Field(..., description="Код ошибки")
    message: str = Field(..., description="Сообщение об ошибке")
    details: Optional[str] = Field(None, description="Дополнительные детали ошибки")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Время возникновения ошибки"
    )
