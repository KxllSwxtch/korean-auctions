from typing import List, Optional, Any
from pydantic import BaseModel, Field


class KCarCar(BaseModel):
    """Модель автомобиля KCar"""

    # Основная информация
    car_id: Optional[str] = Field(None, alias="CAR_ID", description="ID автомобиля")
    car_name: Optional[str] = Field(
        None, alias="CAR_NM", description="Название автомобиля"
    )
    car_number: Optional[str] = Field(None, alias="CNO", description="Номер автомобиля")

    # Изображения автомобиля
    thumbnail: Optional[str] = Field(
        None,
        alias="THUMBNAIL",
        description="URL фотографии автомобиля (оригинальное качество)",
    )
    thumbnail_mobile: Optional[str] = Field(
        None,
        alias="THUMBNAIL_MOBILE",
        description="URL фотографии автомобиля (оригинальное качество)",
    )

    # Цена и аукцион
    auction_start_price: Optional[str] = Field(
        None, alias="AUC_STRT_PRC", description="Стартовая цена аукциона"
    )
    auction_start_hope: Optional[str] = Field(
        None, alias="AUC_STRT_HOPE", description="Ожидаемая цена"
    )
    auction_code: Optional[str] = Field(
        None, alias="AUC_CD", description="Код аукциона"
    )
    auction_status: Optional[str] = Field(
        None, alias="AUC_STAT", description="Статус аукциона"
    )
    auction_status_name: Optional[str] = Field(
        None, alias="AUC_STAT_NM", description="Название статуса аукциона"
    )
    auction_date: Optional[str] = Field(
        None, alias="AUC_STRT_DT", description="Дата аукциона"
    )
    auction_datetime: Optional[str] = Field(
        None, alias="AUC_STRT_END_DATETIME", description="Дата и время аукциона"
    )
    auction_type_desc: Optional[str] = Field(
        None, alias="AUC_TYPE_DESC", description="Тип аукциона"
    )

    # Характеристики автомобиля
    year: Optional[str] = Field(None, alias="FORM_YR", description="Год выпуска")
    mileage: Optional[str] = Field(None, alias="MILG", description="Пробег")
    displacement: Optional[str] = Field(
        None, alias="ENGDISPMNT", description="Объем двигателя"
    )
    fuel_type: Optional[str] = Field(None, alias="FUEL_CD", description="Тип топлива")
    transmission: Optional[str] = Field(
        None, alias="GBOX_DCD", description="Коробка передач"
    )
    exterior_color: Optional[str] = Field(
        None, alias="EXTERIOR_COLOR_NM", description="Цвет кузова"
    )
    color_code: Optional[str] = Field(None, alias="COLOR_CD", description="Код цвета")

    # Оценка и состояние
    car_point: Optional[str] = Field(
        None, alias="CAR_POINT", description="Оценка автомобиля"
    )
    car_point2: Optional[str] = Field(
        None, alias="CAR_POINT2", description="Оценка автомобиля 2"
    )
    car_status: Optional[str] = Field(
        None, alias="CAR_STAT_CD", description="Статус автомобиля"
    )
    car_use: Optional[str] = Field(
        None, alias="CAR_USE_NM", description="Использование автомобиля"
    )
    accident_yn: Optional[str] = Field(
        None, alias="ACCIDENT_YN", description="Признак аварии"
    )

    # Местоположение
    car_location: Optional[str] = Field(
        None, alias="CAR_LOCT", description="Расположение автомобиля"
    )
    car_location_detail: Optional[str] = Field(
        None, alias="CAR_LOCT_DETAIL", description="Детальное расположение"
    )
    auction_place_name: Optional[str] = Field(
        None, alias="AUC_PLC_NM", description="Название места аукциона"
    )
    lane_type: Optional[str] = Field(None, description="Тип лейна (A или B)")

    # Дополнительная информация
    exhibit_seq: Optional[str] = Field(
        None, alias="EXBIT_SEQ", description="Номер лота"
    )
    foreign: Optional[str] = Field(
        None, alias="FOREIGN", description="Импортный автомобиль"
    )
    carmd_code: Optional[str] = Field(None, alias="CARMD_CD", description="Код модели")

    # Даты создания/изменения
    created_date: Optional[str] = Field(
        None, alias="CRT_DTL_DTTM", description="Дата создания"
    )
    updated_date: Optional[str] = Field(
        None, alias="CHNG_DTL_DTTM", description="Дата изменения"
    )

    class Config:
        populate_by_name = True
        allow_population_by_field_name = True


class KCarAuctionReqVo(BaseModel):
    """Модель запроса аукциона KCar"""

    auction_type: Optional[str] = Field(
        None, alias="AUC_TYPE", description="Тип аукциона"
    )
    start_date: Optional[str] = Field(
        None, alias="START_DATE", description="Дата начала"
    )
    end_date: Optional[str] = Field(
        None, alias="END_DATE", description="Дата окончания"
    )
    page_cnt: Optional[int] = Field(
        None, alias="PAGE_CNT", description="Количество на странице"
    )
    start_rnum: Optional[int] = Field(
        None, alias="START_RNUM", description="Номер страницы (не номер записи!)"
    )
    end_rnum: Optional[int] = Field(
        None, alias="END_RNUM", description="Конечный номер"
    )
    manufacturer_code: Optional[str] = Field(
        None, alias="MNUFTR_CD", description="Код производителя"
    )
    model_group_code: Optional[str] = Field(
        None, alias="MODEL_GRP_CD", description="Код группы модели"
    )
    model_code: Optional[str] = Field(None, alias="MODEL_CD", description="Код модели")
    user_id: Optional[str] = Field(
        None, alias="s_USER_ID", description="ID пользователя"
    )

    class Config:
        populate_by_name = True
        allow_population_by_field_name = True


class KCarResponse(BaseModel):
    """Полный ответ от KCar API"""

    auction_req_vo: Optional[KCarAuctionReqVo] = Field(
        None, alias="auctionReqVo", description="Параметры запроса"
    )
    car_list: List[KCarCar] = Field(
        default_factory=list, alias="CAR_LIST", description="Список автомобилей"
    )
    total_count: Optional[int] = Field(None, description="Общее количество автомобилей")
    success: bool = Field(True, description="Статус успешности")
    message: Optional[str] = Field(None, description="Сообщение")

    class Config:
        populate_by_name = True
        allow_population_by_field_name = True


class KCarStatsResponse(BaseModel):
    """Модель статистики по автомобилям KCar"""

    total_cars: int = Field(0, description="Общее количество автомобилей")
    daily_auctions: int = Field(0, description="Ежедневные аукционы")
    weekly_auctions: int = Field(0, description="Еженедельные аукционы")
    locations: List[str] = Field(default_factory=list, description="Доступные локации")
    manufacturers: List[str] = Field(default_factory=list, description="Производители")
    average_price: Optional[float] = Field(None, description="Средняя цена")
    success: bool = Field(True, description="Статус ответа")


class KCarDetailedCar(BaseModel):
    """Детальная модель автомобиля KCar с полной информацией"""

    # Основные идентификаторы
    car_id: Optional[str] = Field(None, description="ID автомобиля")
    auction_code: Optional[str] = Field(None, description="Код аукциона")
    car_number: Optional[str] = Field(None, description="Номер автомобиля")
    lot_number: Optional[str] = Field(None, description="Номер лота")

    # Основная информация
    car_name: Optional[str] = Field(None, description="Полное название автомобиля")
    manufacturer: Optional[str] = Field(None, description="Производитель")
    model: Optional[str] = Field(None, description="Модель")

    # Технические характеристики
    year: Optional[str] = Field(None, description="Год выпуска")
    registration_date: Optional[str] = Field(
        None, description="Дата первой регистрации"
    )
    mileage: Optional[str] = Field(None, description="Пробег")
    fuel_type: Optional[str] = Field(None, description="Тип топлива")
    transmission: Optional[str] = Field(None, description="Коробка передач")
    exterior_color: Optional[str] = Field(None, description="Цвет кузова")
    displacement: Optional[str] = Field(None, description="Объем двигателя")
    car_type: Optional[str] = Field(None, description="Тип кузова")
    doors: Optional[str] = Field(None, description="Количество дверей")
    vin: Optional[str] = Field(None, description="VIN номер")
    engine_type: Optional[str] = Field(None, description="Тип двигателя")

    # Аукционная информация
    auction_date: Optional[str] = Field(None, description="Дата аукциона")
    auction_round: Optional[str] = Field(None, description="Номер аукциона")
    start_price: Optional[str] = Field(None, description="Стартовая цена")
    auction_place: Optional[str] = Field(None, description="Место проведения аукциона")
    auction_type: Optional[str] = Field(None, description="Тип аукциона")

    # Состояние и оценка
    grade: Optional[str] = Field(None, description="Оценка состояния")
    seizure_mortgage: Optional[str] = Field(None, description="Арест/залог")
    flood_damage: Optional[str] = Field(None, description="Повреждение от наводнения")
    accident_history: Optional[str] = Field(None, description="История аварий")

    # Местоположение
    location: Optional[str] = Field(None, description="Расположение автомобиля")
    address: Optional[str] = Field(None, description="Подробный адрес")

    # Владелец (зашифрованные данные)
    owner_name: Optional[str] = Field(None, description="Имя владельца (зашифрованное)")
    owner_company: Optional[str] = Field(None, description="Компания владельца")
    owner_id: Optional[str] = Field(None, description="ID владельца (зашифрованное)")

    # Технический осмотр
    inspection_valid_until: Optional[str] = Field(
        None, description="Техосмотр действителен до"
    )
    inspection_number: Optional[str] = Field(
        None, description="Номер инспекционного документа"
    )

    # Изображения
    main_image: Optional[str] = Field(None, description="Основное изображение")
    all_images: List[str] = Field(
        default_factory=list, description="Все изображения автомобиля"
    )
    thumbnail_images: List[str] = Field(
        default_factory=list, description="Миниатюры изображений"
    )

    # Опции и оборудование
    options: List[str] = Field(
        default_factory=list, description="Список опций и оборудования"
    )

    # Дополнительная информация
    usage_type: Optional[str] = Field(None, description="Тип использования")
    created_at: Optional[str] = Field(None, description="Время создания записи")
    updated_at: Optional[str] = Field(None, description="Время последнего обновления")

    class Config:
        populate_by_name = True
        allow_population_by_field_name = True


class KCarDetailResponse(BaseModel):
    """Ответ API для детальной информации об автомобиле KCar"""

    car: Optional[KCarDetailedCar] = Field(
        None, description="Детальная информация об автомобиле"
    )
    success: bool = Field(True, description="Статус успешности")
    message: Optional[str] = Field(None, description="Сообщение об ошибке или успехе")
    source_url: Optional[str] = Field(None, description="URL источника данных")

    class Config:
        populate_by_name = True
        allow_population_by_field_name = True


class KCarDetailRequest(BaseModel):
    """Модель запроса детальной информации об автомобиле"""

    car_id: str = Field(..., description="ID автомобиля")
    auction_code: str = Field(..., description="Код аукциона")
    page_type: str = Field(default="wCfm", description="Тип страницы")

    class Config:
        populate_by_name = True
        allow_population_by_field_name = True
