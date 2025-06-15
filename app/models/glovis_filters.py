from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class GlovisManufacturer(BaseModel):
    """Модель производителя автомобилей Glovis"""

    prodmancd: str = Field(..., description="Код производителя")
    name: str = Field(..., description="Название производителя")
    count: int = Field(..., description="Количество доступных автомобилей")
    enabled: bool = Field(True, description="Доступен ли для выбора")


class GlovisModel(BaseModel):
    """Модель автомобиля (базовой модели) Glovis"""

    makeid: str = Field(..., description="ID модели")
    makenm: str = Field(..., description="Название модели")
    reprcarcd: str = Field(..., description="Код модели")
    prodmancd: str = Field(..., description="Код производителя")
    targetcnt: int = Field(0, description="Количество доступных автомобилей")


class GlovisDetailModel(BaseModel):
    """Детальная модель автомобиля Glovis"""

    makeid: str = Field(..., description="ID детальной модели")
    makenm: str = Field(..., description="Название детальной модели")
    detacarcd: str = Field(..., description="Код детальной модели")
    reprcarcd: str = Field(..., description="Код базовой модели")
    prodmancd: str = Field(..., description="Код производителя")
    targetcnt: int = Field(0, description="Количество доступных автомобилей")


class GlovisFilterOptions(BaseModel):
    """Опции фильтрации для поиска автомобилей Glovis"""

    # Производители
    manufacturers: Optional[List[str]] = Field(None, description="Коды производителей")

    # Модели
    models: Optional[List[str]] = Field(None, description="Коды моделей (reprcarcd)")
    detail_models: Optional[List[str]] = Field(
        None, description="Коды детальных моделей (detacarcd)"
    )

    # Цены
    min_price: Optional[int] = Field(
        None, description="Минимальная стартовая цена", ge=0
    )
    max_price: Optional[int] = Field(
        None, description="Максимальная стартовая цена", ge=0
    )

    # Годы выпуска
    min_year: Optional[int] = Field(
        None, description="Минимальный год выпуска", ge=1900, le=2030
    )
    max_year: Optional[int] = Field(
        None, description="Максимальный год выпуска", ge=1900, le=2030
    )

    # Пробег (в километрах)
    min_mileage: Optional[str] = Field(None, description="Минимальный пробег")
    max_mileage: Optional[str] = Field(None, description="Максимальный пробег")

    # Трансмиссия
    transmission: Optional[str] = Field(None, description="Тип трансмиссии")

    # Локация
    location: Optional[str] = Field(None, description="Код локации (rc)")

    # Оценка состояния
    car_grade: Optional[str] = Field(None, description="Код оценки состояния")

    # Поиск по тексту
    search_text: Optional[str] = Field(None, description="Текст для поиска")
    search_type: Optional[str] = Field(None, description="Тип поиска (exhino, carno)")

    # Пагинация
    page: int = Field(1, description="Номер страницы", ge=1)
    page_size: int = Field(18, description="Размер страницы", ge=1, le=100)

    # Сортировка
    sort_order: Optional[str] = Field("01", description="Порядок сортировки")


class GlovisManufacturersResponse(BaseModel):
    """Ответ со списком производителей"""

    success: bool = Field(..., description="Успешность запроса")
    message: str = Field(..., description="Сообщение")
    manufacturers: List[GlovisManufacturer] = Field(
        default_factory=list, description="Список производителей"
    )
    total_count: int = Field(0, description="Общее количество производителей")
    timestamp: str = Field(..., description="Временная метка")


class GlovisModelsResponse(BaseModel):
    """Ответ со списком моделей"""

    success: bool = Field(..., description="Успешность запроса")
    message: str = Field(..., description="Сообщение")
    manufacturer: Optional[GlovisManufacturer] = Field(
        None, description="Информация о производителе"
    )
    models: List[GlovisModel] = Field(
        default_factory=list, description="Список моделей"
    )
    total_count: int = Field(0, description="Общее количество моделей")
    timestamp: str = Field(..., description="Временная метка")


class GlovisDetailModelsResponse(BaseModel):
    """Ответ со списком детальных моделей"""

    success: bool = Field(..., description="Успешность запроса")
    message: str = Field(..., description="Сообщение")
    base_model: Optional[GlovisModel] = Field(
        None, description="Информация о базовой модели"
    )
    detail_models: List[GlovisDetailModel] = Field(
        default_factory=list, description="Список детальных моделей"
    )
    total_count: int = Field(0, description="Общее количество детальных моделей")
    timestamp: str = Field(..., description="Временная метка")


class GlovisFilteredCarsResponse(BaseModel):
    """Ответ с отфильтрованными автомобилями"""

    success: bool = Field(..., description="Успешность запроса")
    message: str = Field(..., description="Сообщение")

    # Применённые фильтры
    applied_filters: GlovisFilterOptions = Field(..., description="Применённые фильтры")

    # Результаты
    cars: List = Field(default_factory=list, description="Список автомобилей")
    total_count: int = Field(0, description="Общее количество найденных автомобилей")

    # Пагинация
    current_page: int = Field(1, description="Текущая страница")
    page_size: int = Field(18, description="Размер страницы")
    total_pages: int = Field(0, description="Общее количество страниц")
    has_next_page: bool = Field(False, description="Есть ли следующая страница")
    has_prev_page: bool = Field(False, description="Есть ли предыдущая страница")

    # Метаданные
    timestamp: str = Field(..., description="Временная метка")
    request_duration: Optional[float] = Field(
        None, description="Время выполнения запроса"
    )


class GlovisFiltersError(BaseModel):
    """Ошибка при работе с фильтрами"""

    success: bool = Field(False, description="Успешность запроса")
    error_code: str = Field(..., description="Код ошибки")
    message: str = Field(..., description="Сообщение об ошибке")
    details: Optional[str] = Field(None, description="Дополнительные детали")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Временная метка",
    )
