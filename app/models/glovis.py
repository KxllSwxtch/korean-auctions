"""
Модели данных для аукциона SSANCAR (используем имя Glovis для API совместимости)
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Union
from pydantic import BaseModel, Field, HttpUrl


class GlovisLocation(str, Enum):
    """Локации для совместимости (SSANCAR использует другую систему)"""

    BUNDANG = "분당"
    SIHWA = "시화"
    YANGSAN = "양산"
    INCHEON = "인천"
    SSANCAR = "SSANCAR"  # Новая локация для SSANCAR


class GlovisCarCondition(str, Enum):
    """Состояние автомобиля (адаптировано под SSANCAR)"""

    A1 = "A/1"
    A2 = "A/2"
    A3 = "A/3"
    A4 = "A/4"
    A5 = "A/5"
    A6 = "A/6"
    A7 = "A/7"
    A8 = "A/8"
    B1 = "B/1"
    B2 = "B/2"
    B3 = "B/3"
    C1 = "C/1"
    C2 = "C/2"
    D1 = "D/1"


class SSANCARWeek(str, Enum):
    """Недели аукциона SSANCAR"""

    WEEK_1 = "1"
    WEEK_2 = "2"
    WEEK_3 = "3"
    WEEK_4 = "4"


class GlovisCar(BaseModel):
    """
    Модель автомобиля SSANCAR (сохраняем имя Glovis для API совместимости)

    Адаптирована под структуру данных SSANCAR:
    - Stock NO, название, год, КПП, топливо, объем, пробег, оценка, цена, изображение
    """

    # Основная информация
    entry_number: str = Field(..., description="Номер лота (Stock NO)")
    car_name: str = Field(..., description="Полное название автомобиля [BRAND] Model")
    brand: Optional[str] = Field(
        None, description="Бренд автомобиля (извлечен из названия)"
    )
    model: Optional[str] = Field(
        None, description="Модель автомобиля (извлечена из названия)"
    )

    # Технические характеристики
    year: int = Field(0, description="Год выпуска")
    transmission: str = Field("", description="Коробка передач (A/T, M/T)")
    fuel_type: str = Field(
        "", description="Тип топлива (Gasoline, Diesel, Hybrid, LPG)"
    )
    engine_volume: str = Field("", description="Объем двигателя (1,399cc)")
    mileage: str = Field("", description="Пробег (72,698 Km)")
    condition_grade: GlovisCarCondition = Field(
        GlovisCarCondition.A4, description="Оценка состояния"
    )

    # Цена и аукцион
    starting_price: int = Field(0, description="Стартовая цена (Bid)")
    currency: str = Field("USD", description="Валюта")

    # Изображения и ссылки
    main_image_url: Optional[HttpUrl] = Field(
        None, description="URL главного изображения"
    )
    detail_url: Optional[HttpUrl] = Field(
        None, description="Ссылка на детальную страницу"
    )
    car_no: Optional[str] = Field(
        None, description="Внутренний номер автомобиля SSANCAR"
    )

    # Дополнительная информация для совместимости с Glovis API
    location: GlovisLocation = Field(
        GlovisLocation.SSANCAR, description="Локация (SSANCAR)"
    )
    lane: str = Field("", description="Полоса (не используется в SSANCAR)")
    license_plate: str = Field(
        "", description="Номер автомобиля (не используется в SSANCAR)"
    )
    auction_number: str = Field("", description="Номер аукциона (weekNo в SSANCAR)")
    usage_type: str = Field("", description="Тип использования")
    color: str = Field("", description="Цвет автомобиля")

    # Внутренние идентификаторы (для совместимости)
    gn: str = Field("", description="GN идентификатор (эмуляция для SSANCAR)")
    rc: str = Field("", description="RC параметр (эмуляция)")
    acc: str = Field("", description="ACC параметр (эмуляция)")
    atn: str = Field("", description="ATN параметр (эмуляция)")
    prodmancd: str = Field("", description="Код производителя (эмуляция)")
    reprcarcd: str = Field(
        "", description="Код представительского автомобиля (эмуляция)"
    )
    detacarcd: str = Field("", description="Код детального автомобиля (эмуляция)")
    cargradcd: str = Field("", description="Код оценки автомобиля (эмуляция)")

    # Метаданные
    parsed_at: datetime = Field(
        default_factory=datetime.now, description="Время парсинга"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "entry_number": "2001",
                "car_name": "[HYUNDAI] NewClick 1.4 i Deluxe",
                "brand": "HYUNDAI",
                "model": "NewClick 1.4 i Deluxe",
                "year": 2010,
                "transmission": "A/T",
                "fuel_type": "Gasoline",
                "engine_volume": "1,399cc",
                "mileage": "72,698 Km",
                "condition_grade": "A/1",
                "starting_price": 1541,
                "currency": "USD",
                "main_image_url": "https://img-auction.autobell.co.kr/...",
                "detail_url": "https://www.ssancar.com/page/car_view.php?car_no=1515765",
                "car_no": "1515765",
                "location": "SSANCAR",
                "auction_number": "2",
            }
        }


class GlovisResponse(BaseModel):
    """
    Ответ API с данными SSANCAR (сохраняем имя Glovis для совместимости)
    """

    success: bool = Field(..., description="Успешность выполнения запроса")
    message: str = Field(..., description="Сообщение о результате")
    total_count: int = Field(0, description="Общее количество найденных автомобилей")
    cars: List[GlovisCar] = Field(
        default_factory=list, description="Список автомобилей"
    )

    # Информация о пагинации (адаптирована под SSANCAR)
    current_page: int = Field(
        0, description="Текущая страница (начинается с 0 в SSANCAR)"
    )
    page_size: int = Field(
        15, description="Размер страницы (по умолчанию 15 в SSANCAR)"
    )
    total_pages: Optional[int] = Field(None, description="Общее количество страниц")
    has_next_page: bool = Field(False, description="Есть ли следующая страница")
    has_prev_page: bool = Field(False, description="Есть ли предыдущая страница")

    # SSANCAR специфичные параметры
    week_number: str = Field("2", description="Номер недели аукциона SSANCAR")
    source: str = Field("SSANCAR", description="Источник данных")

    parsed_at: datetime = Field(
        default_factory=datetime.now, description="Время парсинга"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Автомобили успешно получены",
                "total_count": 385,
                "cars": [],
                "current_page": 0,
                "page_size": 15,
                "total_pages": 26,
                "has_next_page": True,
                "has_prev_page": False,
                "week_number": "2",
                "source": "SSANCAR",
            }
        }


class GlovisError(BaseModel):
    """Модель ошибки для совместимости"""

    success: bool = Field(False, description="Успешность выполнения")
    message: str = Field(..., description="Сообщение об ошибке")
    error_code: Optional[str] = Field(None, description="Код ошибки")
    details: Optional[dict] = Field(None, description="Дополнительные детали ошибки")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Время ошибки"
    )


class SSANCARFilters(BaseModel):
    """
    Модель фильтров для SSANCAR
    """

    week_no: str = Field("2", description="Номер недели аукциона")
    maker: str = Field("", description="Производитель")
    model: str = Field("", description="Модель")
    fuel: str = Field("", description="Тип топлива")
    color: str = Field("", description="Цвет")
    year_from: str = Field("2000", description="Год от")
    year_to: str = Field("2024", description="Год до")
    price_from: str = Field("0", description="Цена от")
    price_to: str = Field("200000", description="Цена до")
    list_size: str = Field("15", description="Количество на странице")
    pages: str = Field("0", description="Номер страницы (начинается с 0)")
    no: str = Field("", description="Дополнительный параметр")

    class Config:
        json_schema_extra = {
            "example": {
                "week_no": "2",
                "maker": "",
                "model": "",
                "fuel": "",
                "color": "",
                "year_from": "2000",
                "year_to": "2024",
                "price_from": "0",
                "price_to": "200000",
                "list_size": "15",
                "pages": "0",
                "no": "",
            }
        }
