"""
Модели данных для детальной информации об автомобиле Glovis
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class GlovisCarImage(BaseModel):
    """Изображение автомобиля"""

    url: str = Field(..., description="URL изображения")
    thumbnail_url: Optional[str] = Field(None, description="URL миниатюры")
    alt_text: Optional[str] = Field(None, description="Альтернативный текст")


class GlovisCarBasicInfo(BaseModel):
    """Базовая информация об автомобиле"""

    name: str = Field(..., description="Название автомобиля")
    manufacturer: str = Field(..., description="Производитель")
    model: str = Field(..., description="Модель")
    grade: Optional[str] = Field(None, description="Комплектация")
    year: Optional[str] = Field(None, description="Год выпуска")
    first_registration_date: Optional[str] = Field(
        None, description="Дата первой регистрации"
    )
    fuel_type: Optional[str] = Field(None, description="Тип топлива")
    mileage: Optional[str] = Field(None, description="Пробег")
    transmission: Optional[str] = Field(None, description="Коробка передач")
    color: Optional[str] = Field(None, description="Цвет")
    auction_status: Optional[str] = Field(None, description="Статус аукциона")


class GlovisCarPricing(BaseModel):
    """Информация о ценах"""

    new_car_price: Optional[str] = Field(None, description="Цена нового автомобиля")
    starting_price: Optional[str] = Field(None, description="Стартовая цена")
    current_price: Optional[str] = Field(None, description="Текущая цена")
    estimated_price: Optional[str] = Field(None, description="Оценочная стоимость")
    bid_increment: Optional[str] = Field(None, description="Шаг торгов")


class GlovisCarDetailedSpecs(BaseModel):
    """Детальные характеристики автомобиля"""

    product_category: Optional[str] = Field(None, description="Категория продукта")
    fuel_type: Optional[str] = Field(None, description="Тип топлива")
    engine_displacement: Optional[str] = Field(None, description="Объем двигателя")
    seating_capacity: Optional[str] = Field(None, description="Количество мест")
    usage_purpose: Optional[str] = Field(None, description="Назначение/категория")
    engine_type: Optional[str] = Field(None, description="Тип двигателя")
    accessories: Optional[str] = Field(None, description="Аксессуары")
    inspection_date: Optional[str] = Field(None, description="Дата техосмотра")
    complete_documents: Optional[str] = Field(
        None, description="Полный пакет документов"
    )
    car_number: Optional[str] = Field(None, description="Номер автомобиля")
    chassis_number: Optional[str] = Field(None, description="Номер шасси")
    model_year: Optional[str] = Field(None, description="Модельный год")
    first_registration: Optional[str] = Field(None, description="Первая регистрация")
    mileage: Optional[str] = Field(None, description="Пробег")
    color_full: Optional[str] = Field(None, description="Полное название цвета")
    transmission: Optional[str] = Field(None, description="Трансмиссия")
    lot_number: Optional[str] = Field(None, description="Номер лота")
    missing_documents: Optional[str] = Field(
        None, description="Отсутствующие документы"
    )


class GlovisCarPerformanceCheck(BaseModel):
    """Результаты проверки технического состояния"""

    engine: Optional[str] = Field(None, description="Двигатель")
    braking: Optional[str] = Field(None, description="Тормозная система")
    steering: Optional[str] = Field(None, description="Рулевое управление")
    electrical: Optional[str] = Field(None, description="Электрика")
    transmission: Optional[str] = Field(None, description="Трансмиссия")
    air_conditioning: Optional[str] = Field(None, description="Кондиционер")
    power: Optional[str] = Field(None, description="Силовая установка")
    interior: Optional[str] = Field(None, description="Салон")
    lighting: Optional[str] = Field(None, description="Освещение")
    rating: Optional[str] = Field(None, description="Общий рейтинг")
    special_notes: Optional[str] = Field(None, description="Особые замечания")
    changes: Optional[str] = Field(None, description="Изменения")
    evaluation_opinion: Optional[str] = Field(None, description="Заключение оценщика")


class GlovisCarOptions(BaseModel):
    """Опции автомобиля"""

    standard_options: List[str] = Field(
        default_factory=list, description="Стандартные опции"
    )
    additional_options: List[str] = Field(
        default_factory=list, description="Дополнительные опции"
    )
    all_options_text: Optional[str] = Field(None, description="Полный текст опций")


class GlovisCarAdditionalInfo(BaseModel):
    """Дополнительная информация"""

    auction_location: Optional[str] = Field(
        None, description="Место проведения аукциона"
    )
    auction_date: Optional[str] = Field(None, description="Дата аукциона")
    auction_time: Optional[str] = Field(None, description="Время аукциона")
    seller_info: Optional[str] = Field(None, description="Информация о продавце")
    special_conditions: Optional[str] = Field(None, description="Особые условия")
    warranty_info: Optional[str] = Field(None, description="Информация о гарантии")


class GlovisCarAccidentHistory(BaseModel):
    """История аварий"""

    has_accident_history: Optional[bool] = Field(
        None, description="Есть ли история аварий"
    )
    accident_details: Optional[str] = Field(None, description="Детали аварий")
    repair_history: Optional[str] = Field(None, description="История ремонтов")


class GlovisCarInspectionDetails(BaseModel):
    """Детали технического осмотра"""

    inspection_date: Optional[str] = Field(None, description="Дата осмотра")
    inspector: Optional[str] = Field(None, description="Инспектор")
    inspection_location: Optional[str] = Field(None, description="Место осмотра")
    detailed_notes: Optional[str] = Field(None, description="Подробные заметки")
    photos_count: Optional[int] = Field(None, description="Количество фотографий")


class GlovisCarDetail(BaseModel):
    """Полная детальная информация об автомобиле"""

    # Основная информация
    basic_info: GlovisCarBasicInfo = Field(..., description="Базовая информация")

    # Цены
    pricing: Optional[GlovisCarPricing] = Field(None, description="Информация о ценах")

    # Детальные характеристики
    detailed_specs: Optional[GlovisCarDetailedSpecs] = Field(
        None, description="Детальные характеристики"
    )

    # Техническое состояние
    performance_check: Optional[GlovisCarPerformanceCheck] = Field(
        None, description="Результаты проверки"
    )

    # Опции
    options: Optional[GlovisCarOptions] = Field(None, description="Опции автомобиля")

    # Изображения
    images: List[GlovisCarImage] = Field(
        default_factory=list, description="Изображения автомобиля"
    )

    # Дополнительная информация
    additional_info: Optional[GlovisCarAdditionalInfo] = Field(
        None, description="Дополнительная информация"
    )

    # История аварий
    accident_history: Optional[GlovisCarAccidentHistory] = Field(
        None, description="История аварий"
    )

    # Детали осмотра
    inspection_details: Optional[GlovisCarInspectionDetails] = Field(
        None, description="Детали осмотра"
    )

    # Метаданные
    parsed_at: datetime = Field(
        default_factory=datetime.now, description="Время парсинга"
    )
    source_url: Optional[str] = Field(None, description="URL источника")
    car_id: Optional[str] = Field(None, description="ID автомобиля")
    auction_number: Optional[str] = Field(None, description="Номер аукциона")


class GlovisCarDetailResponse(BaseModel):
    """Ответ API с детальной информацией об автомобиле"""

    success: bool = Field(..., description="Успешность запроса")
    message: str = Field(..., description="Сообщение о результате")
    data: Optional[GlovisCarDetail] = Field(None, description="Данные автомобиля")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class GlovisCarDetailError(BaseModel):
    """Ошибка при получении детальной информации"""

    success: bool = Field(False, description="Успешность запроса")
    message: str = Field(..., description="Сообщение об ошибке")
    error_code: Optional[str] = Field(None, description="Код ошибки")
    details: Optional[Dict[str, Any]] = Field(
        None, description="Дополнительные детали ошибки"
    )
