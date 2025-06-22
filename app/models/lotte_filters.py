from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class LotteManufacturer(BaseModel):
    """Модель производителя автомобилей Lotte"""

    code: str = Field(..., description="Код производителя (например, 'AD')")
    name: str = Field(..., description="Название производителя (например, 'AUDI')")


class LotteModel(BaseModel):
    """Модель автомобиля Lotte"""

    code: str = Field(..., description="Код модели (например, 'AD004')")
    name: str = Field(..., description="Название модели (например, 'аudi A6')")
    manufacturer_code: Optional[str] = Field(None, description="Код производителя")


class LotteCarGroup(BaseModel):
    """Группа автомобилей Lotte"""

    code: str = Field(..., description="Код группы (например, 'AD004001')")
    name: str = Field(..., description="Название группы (например, 'аudi A6')")
    model_code: Optional[str] = Field(None, description="Код модели")


class LotteMPriceCar(BaseModel):
    """Подмодель автомобиля с ценой Lotte"""

    code: str = Field(..., description="Код подмодели (например, '0000002309')")
    name: str = Field(
        ..., description="Полное название (например, 'AUDI A6 (D) 2.0 35 TDI DYNAMIC')"
    )
    car_group_code: Optional[str] = Field(None, description="Код группы автомобилей")


class LotteFilterRequest(BaseModel):
    """Запрос фильтрации автомобилей Lotte"""

    # Основные фильтры
    manufacturer_code: Optional[str] = Field(None, description="Код производителя")
    model_code: Optional[str] = Field(None, description="Код модели")
    car_group_codes: Optional[List[str]] = Field(
        None, description="Коды групп автомобилей"
    )
    mprice_car_codes: Optional[List[str]] = Field(None, description="Коды подмоделей")

    # Дата аукциона
    auction_date: Optional[str] = Field(None, description="Дата аукциона (YYYYMMDD)")

    # Ценовые фильтры
    min_price: Optional[int] = Field(
        None, ge=0, description="Минимальная цена (в 10,000 вон)"
    )
    max_price: Optional[int] = Field(
        None, ge=0, description="Максимальная цена (в 10,000 вон)"
    )

    # Год выпуска
    min_year: Optional[int] = Field(
        None, ge=1990, le=2030, description="Минимальный год выпуска"
    )
    max_year: Optional[int] = Field(
        None, ge=1990, le=2030, description="Максимальный год выпуска"
    )

    # Дополнительные фильтры
    fuel_code: Optional[str] = Field(None, description="Код типа топлива")
    transmission_code: Optional[str] = Field(None, description="Код трансмиссии")
    lane_division: Optional[str] = Field(None, description="Разделение по полосам")
    exhibition_number: Optional[str] = Field(None, description="Номер выставки")

    # Пагинация
    page: int = Field(1, ge=1, description="Номер страницы")
    per_page: int = Field(20, ge=1, le=100, description="Количество на странице")


class LotteManufacturersResponse(BaseModel):
    """Ответ со списком производителей"""

    success: bool = True
    message: str = "Список производителей получен успешно"
    manufacturers: List[LotteManufacturer] = Field(default_factory=list)
    total_count: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class LotteModelsResponse(BaseModel):
    """Ответ со списком моделей"""

    success: bool = True
    message: str = "Список моделей получен успешно"
    models: List[LotteModel] = Field(default_factory=list)
    manufacturer_code: Optional[str] = None
    total_count: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class LotteCarGroupsResponse(BaseModel):
    """Ответ со списком групп автомобилей"""

    success: bool = True
    message: str = "Список групп автомобилей получен успешно"
    car_groups: List[LotteCarGroup] = Field(default_factory=list)
    model_code: Optional[str] = None
    total_count: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class LotteMPriceCarsResponse(BaseModel):
    """Ответ со списком подмоделей с ценами"""

    success: bool = True
    message: str = "Список подмоделей получен успешно"
    mprice_cars: List[LotteMPriceCar] = Field(default_factory=list)
    car_group_code: Optional[str] = None
    total_count: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class LotteFilterError(BaseModel):
    """Ошибка при работе с фильтрами"""

    success: bool = False
    error_code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
