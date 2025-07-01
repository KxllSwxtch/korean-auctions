"""
Модели данных для аукциона SSANCAR (используем имя Glovis для API совместимости)
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Union, Dict
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


# =============================================================================
# SSANCAR FILTER MODELS
# =============================================================================


class SSANCARManufacturer(BaseModel):
    """Модель производителя SSANCAR"""

    code: str = Field(..., description="Код производителя")
    name: str = Field(..., description="Название производителя")
    name_en: Optional[str] = Field(None, description="Название на английском")
    name_kr: Optional[str] = Field(None, description="Название на корейском")
    model_count: int = Field(0, description="Количество моделей производителя")
    count: int = Field(0, description="Количество доступных автомобилей")
    enabled: bool = Field(True, description="Доступен ли для выбора")


class SSANCARModel(BaseModel):
    """Модель автомобиля SSANCAR"""

    code: str = Field(..., description="Код модели")
    name: str = Field(..., description="Название модели")
    name_en: Optional[str] = Field(None, description="Название на английском")
    name_kr: Optional[str] = Field(None, description="Название на корейском")
    manufacturer_code: str = Field(..., description="Код производителя")
    count: int = Field(0, description="Количество доступных автомобилей")


class SSANCARFuelType(BaseModel):
    """Тип топлива SSANCAR"""

    code: str = Field(..., description="Код типа топлива")
    name: str = Field(..., description="Название типа топлива")


class SSANCARColor(BaseModel):
    """Цвет автомобиля SSANCAR"""

    code: str = Field(..., description="Код цвета")
    name: str = Field(..., description="Название цвета")


class SSANCARTransmission(BaseModel):
    """Тип трансмиссии SSANCAR"""

    code: str = Field(..., description="Код трансмиссии")
    name: str = Field(..., description="Название трансмиссии")


class SSANCARConditionGrade(BaseModel):
    """Оценка состояния SSANCAR"""

    code: str = Field(..., description="Код состояния")
    name: str = Field(..., description="Описание состояния")


class SSANCARWeek(BaseModel):
    """Неделя аукциона SSANCAR"""

    number: int = Field(..., description="Номер недели (1-4)")
    name: str = Field(..., description="Описание недели")
    active: bool = Field(True, description="Активна ли неделя")


class SSANCARAdvancedFilters(BaseModel):
    """Расширенные фильтры SSANCAR с дополнительными опциями"""

    # Основные фильтры SSANCAR
    week_number: Optional[int] = Field(1, description="Номер недели аукциона (1-4)")
    manufacturer: Optional[str] = Field(None, description="Код производителя")
    model: Optional[str] = Field(None, description="Модель автомобиля")
    fuel: Optional[str] = Field(None, description="Тип топлива")
    color: Optional[str] = Field(None, description="Цвет автомобиля")

    # Диапазоны (делаем int для удобства API)
    year_from: Optional[int] = Field(None, description="Год от")
    year_to: Optional[int] = Field(None, description="Год до")
    price_from: Optional[int] = Field(None, description="Цена от ($)")
    price_to: Optional[int] = Field(None, description="Цена до ($)")

    # Дополнительные фильтры
    transmission: Optional[str] = Field(None, description="Тип трансмиссии")
    condition_grade: Optional[str] = Field(None, description="Оценка состояния")
    engine_volume_from: Optional[int] = Field(
        None, description="Объем двигателя от (cc)"
    )
    engine_volume_to: Optional[int] = Field(None, description="Объем двигателя до (cc)")
    mileage_from: Optional[int] = Field(None, description="Пробег от (км)")
    mileage_to: Optional[int] = Field(None, description="Пробег до (км)")

    # Текстовый поиск
    search_text: Optional[str] = Field(None, description="Поиск по названию/номеру")

    # Пагинация
    page: Optional[int] = Field(1, description="Номер страницы", ge=1)
    page_size: Optional[int] = Field(15, description="Размер страницы", ge=1, le=100)

    # Сортировка
    sort_by: Optional[str] = Field("default", description="Поле сортировки")
    sort_order: Optional[str] = Field(
        "asc", description="Порядок сортировки (asc/desc)"
    )


# =============================================================================
# RESPONSE MODELS FOR SSANCAR FILTERS
# =============================================================================


class SSANCARManufacturersResponse(BaseModel):
    """Ответ со списком производителей SSANCAR"""

    success: bool = Field(True, description="Успешность операции")
    message: str = Field("Список производителей получен", description="Сообщение")
    manufacturers: List[SSANCARManufacturer] = Field(default_factory=list)
    total_count: int = Field(0, description="Общее количество производителей")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class SSANCARModelsResponse(BaseModel):
    """Ответ со списком моделей SSANCAR"""

    success: bool = Field(True, description="Успешность операции")
    message: str = Field("Список моделей получен", description="Сообщение")
    models: List[SSANCARModel] = Field(default_factory=list)
    manufacturer_code: Optional[str] = Field(None, description="Код производителя")
    total_count: int = Field(0, description="Общее количество моделей")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class SSANCARFilterOptionsResponse(BaseModel):
    """Ответ с опциями фильтрации SSANCAR"""

    success: bool = Field(True, description="Успешность операции")
    message: str = Field("Опции фильтрации получены", description="Сообщение")

    # Списки фильтров
    manufacturers: List[SSANCARManufacturer] = Field(default_factory=list)
    fuel_types: List[SSANCARFuelType] = Field(default_factory=list)
    colors: List[SSANCARColor] = Field(default_factory=list)
    transmissions: List[SSANCARTransmission] = Field(default_factory=list)
    condition_grades: List[SSANCARConditionGrade] = Field(default_factory=list)
    weeks: List[SSANCARWeek] = Field(default_factory=list)

    # Диапазоны
    year_range: Dict[str, int] = Field(
        default_factory=lambda: {"min": 1990, "max": 2025}
    )
    price_range: Dict[str, int] = Field(
        default_factory=lambda: {"min": 0, "max": 100000}
    )

    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class SSANCARFilteredCarsResponse(BaseModel):
    """Ответ с отфильтрованными автомобилями SSANCAR"""

    success: bool = Field(True, description="Успешность операции")
    message: str = Field("Автомобили найдены", description="Сообщение")

    # Примененные фильтры
    applied_filters: SSANCARAdvancedFilters = Field(
        ..., description="Примененные фильтры"
    )

    # Результаты
    cars: List[GlovisCar] = Field(default_factory=list)
    total_count: int = Field(0, description="Общее количество найденных автомобилей")

    # Пагинация
    current_page: int = Field(1, description="Текущая страница")
    page_size: int = Field(15, description="Размер страницы")
    total_pages: int = Field(0, description="Общее количество страниц")
    has_next_page: bool = Field(False, description="Есть ли следующая страница")
    has_prev_page: bool = Field(False, description="Есть ли предыдущая страница")

    # Метаданные
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    request_duration: Optional[float] = Field(
        None, description="Время выполнения запроса"
    )


# =============================================================================
# SSANCAR CAR DETAIL MODELS
# =============================================================================


class SSANCARCarDetail(BaseModel):
    """Детальная информация об автомобиле SSANCAR"""

    # Основная информация
    car_no: str = Field(..., description="Номер автомобиля SSANCAR")
    stock_no: str = Field(..., description="Номер лота (Stock NO)")
    car_name: str = Field(..., description="Полное название автомобиля")
    brand: Optional[str] = Field(None, description="Бренд автомобиля")
    model: Optional[str] = Field(None, description="Модель автомобиля")

    # Технические характеристики
    year: Optional[int] = Field(None, description="Год выпуска")
    transmission: Optional[str] = Field(None, description="Коробка передач")
    fuel_type: Optional[str] = Field(None, description="Тип топлива")
    engine_volume: Optional[str] = Field(None, description="Объем двигателя")
    mileage: Optional[str] = Field(None, description="Пробег")
    condition_grade: Optional[str] = Field(None, description="Оценка состояния")

    # Цена и аукцион
    starting_price: Optional[str] = Field(None, description="Стартовая цена")
    currency: str = Field("USD", description="Валюта")

    # Фотографии
    images: List[str] = Field(default_factory=list, description="URLs фотографий")
    main_image: Optional[str] = Field(None, description="URL главной фотографии")

    # Дополнительная информация
    auction_date: Optional[str] = Field(None, description="Дата аукциона")
    auction_time_remaining: Optional[str] = Field(None, description="Оставшееся время")
    upload_date: Optional[str] = Field(None, description="Дата загрузки")
    auction_start_date: Optional[str] = Field(None, description="Дата начала аукциона")

    # Ссылки
    detail_url: Optional[str] = Field(None, description="URL детальной страницы")
    manager_url: Optional[str] = Field(None, description="URL страницы менеджеров")

    # Метаданные
    parsed_at: datetime = Field(
        default_factory=datetime.now, description="Время парсинга"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "car_no": "1515765",
                "stock_no": "2001",
                "car_name": "[HYUNDAI] NewClick 1.4 i Deluxe",
                "brand": "HYUNDAI",
                "model": "NewClick 1.4 i Deluxe",
                "year": 2010,
                "transmission": "A/T",
                "fuel_type": "Gasoline",
                "engine_volume": "1,399cc",
                "mileage": "72,698 Km",
                "condition_grade": "A/1",
                "starting_price": "1,541$~",
                "currency": "USD",
                "images": ["https://img-auction.autobell.co.kr/..."],
                "main_image": "https://img-auction.autobell.co.kr/...",
            }
        }


class SSANCARCarDetailResponse(BaseModel):
    """Ответ с детальной информацией об автомобиле SSANCAR"""

    success: bool = Field(True, description="Успешность операции")
    message: str = Field("Детальная информация получена", description="Сообщение")
    car_detail: Optional[SSANCARCarDetail] = Field(
        None, description="Детали автомобиля"
    )
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
