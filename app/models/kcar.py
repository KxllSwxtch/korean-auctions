from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime


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

    # Поля пагинации
    current_page: int = Field(1, description="Текущая страница")
    page_size: int = Field(50, description="Размер страницы")
    total_pages: Optional[int] = Field(None, description="Общее количество страниц")
    has_next_page: bool = Field(False, description="Есть ли следующая страница")
    has_prev_page: bool = Field(False, description="Есть ли предыдущая страница")

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


class TechnicalSheetInspection(BaseModel):
    """Результат инспекции системы автомобиля"""
    
    status: Optional[str] = Field(None, description="Статус: 양호(Good)/불량(Poor)/수리(Repair)")
    status_code: Optional[str] = Field(None, description="Код статуса: V/O/△/X/W/A")
    
    class Config:
        populate_by_name = True


class TechnicalSheet(BaseModel):
    """Технический лист (점검·검사기록부) автомобиля"""
    
    # Информация о документе
    inspection_number: Optional[str] = Field(None, description="Номер инспекции (제 XXXXXXXXX호)")
    form_number: Optional[str] = Field(None, description="Номер формы (별지 제XX호 서식)")
    
    # Информация о владельце
    owner_info: Optional[Dict[str, str]] = Field(None, description="Информация о владельце")
    
    # Проверка идентичности
    vin_condition: Optional[List[str]] = Field(
        default_factory=list, 
        description="Состояние VIN: 양호/상이/부식/훼손/변조/도말"
    )
    registration_confirmed: Optional[bool] = Field(None, description="Регистрация подтверждена")
    
    # Результаты инспекции систем
    engine_system: Optional[TechnicalSheetInspection] = Field(
        None, description="Система двигателя (기관장치)"
    )
    power_transmission: Optional[TechnicalSheetInspection] = Field(
        None, description="Трансмиссия (동력전달장치)"
    )
    braking_system: Optional[TechnicalSheetInspection] = Field(
        None, description="Тормозная система (제동장치)"
    )
    steering_system: Optional[TechnicalSheetInspection] = Field(
        None, description="Рулевое управление (조향장치)"
    )
    lighting_system: Optional[TechnicalSheetInspection] = Field(
        None, description="Осветительные приборы (등화장치)"
    )
    running_gear: Optional[TechnicalSheetInspection] = Field(
        None, description="Ходовая часть (주행장치)"
    )
    battery_system: Optional[TechnicalSheetInspection] = Field(
        None, description="Электрооборудование (축전기계장치)"
    )
    
    # Дополнительные проверки - детальные компоненты
    detailed_inspections: Optional[Dict[str, Any]] = Field(
        None, description="Детальные проверки компонентов"
    )
    
    # Состояние кузова (из визуальной схемы)
    body_parts: Optional[Dict[str, List[str]]] = Field(
        None, description="Состояние частей кузова: replaced/panel_beaten/corroded/adjusted"
    )
    
    # Дополнительные замечания
    additional_notes: Optional[str] = Field(None, description="Дополнительные замечания")
    
    class Config:
        populate_by_name = True


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
    expected_price: Optional[str] = Field(None, description="Ожидаемая цена")
    auction_status: Optional[str] = Field(None, description="Статус аукциона")
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
    
    # Технический лист
    technical_sheet: Optional[TechnicalSheet] = Field(
        None, description="Технический лист с результатами инспекции"
    )

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
    error_type: Optional[str] = Field(
        None,
        description="Тип ошибки: 'authentication_failed', 'car_not_found', 'parsing_failed', 'redirect', 'timeout', 'http_error', 'network_error'"
    )
    missing_fields: Optional[List[str]] = Field(
        None,
        description="Список полей, которые не удалось извлечь из HTML"
    )
    extraction_stats: Optional[Dict[str, bool]] = Field(
        None,
        description="Статистика извлечения по каждому полю (True = успешно, False = не извлечено)"
    )

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


# =============================================================================
# МОДЕЛИ СИСТЕМЫ ФИЛЬТРАЦИИ KCAR
# =============================================================================


class KCarManufacturer(BaseModel):
    """Модель производителя автомобилей"""

    code: str = Field(..., description="Код производителя")
    name: str = Field(..., description="Название производителя")
    name_en: Optional[str] = Field(None, description="Название на английском")

    class Config:
        populate_by_name = True


class KCarModel(BaseModel):
    """Модель автомобиля от API моделей"""

    manufacturer_code: str = Field(
        ..., alias="MNUFTR_CD", description="Код производителя"
    )
    model_group_code: str = Field(
        ..., alias="MODEL_GRP_CD", description="Код группы модели"
    )
    model_group_name: str = Field(
        ..., alias="MODEL_GRP_NM", description="Название модели"
    )
    input_car_code: Optional[str] = Field(
        None, alias="IPTCAR_DCD", description="Код типа автомобиля"
    )

    class Config:
        populate_by_name = True
        allow_population_by_field_name = True


class KCarModelsResponse(BaseModel):
    """Ответ API списка моделей"""

    request_params: Optional[Dict[str, Any]] = Field(
        None, alias="encarReqVo", description="Параметры запроса"
    )
    models: List[KCarModel] = Field(
        default_factory=list, alias="modelVo", description="Список моделей"
    )
    success: bool = Field(True, description="Статус успешности")
    message: Optional[str] = Field(None, description="Сообщение")

    class Config:
        populate_by_name = True
        allow_population_by_field_name = True


class KCarGeneration(BaseModel):
    """Модель поколения автомобиля"""

    model_code: str = Field(..., alias="MODEL_CD", description="Код модели")
    model_name: str = Field(..., alias="MODEL_NM", description="Название модели")
    model_detail_name: str = Field(
        ..., alias="MODEL_DETAIL_NM", description="Детальное название"
    )
    manufacturer_code: Optional[str] = Field(
        None, alias="MNUFTR_CD", description="Код производителя"
    )

    class Config:
        populate_by_name = True
        allow_population_by_field_name = True


class KCarGenerationsResponse(BaseModel):
    """Ответ API списка поколений"""

    request_params: Optional[Dict[str, Any]] = Field(
        None, alias="encarReqVo", description="Параметры запроса"
    )
    generations: List[KCarGeneration] = Field(
        default_factory=list, alias="modelDetailVo", description="Список поколений"
    )
    success: bool = Field(True, description="Статус успешности")
    message: Optional[str] = Field(None, description="Сообщение")

    class Config:
        populate_by_name = True
        allow_population_by_field_name = True


class KCarSearchFilters(BaseModel):
    """Фильтры для расширенного поиска KCar"""

    # Основные фильтры
    manufacturer_code: Optional[str] = Field(None, description="Код производителя")
    model_group_code: Optional[str] = Field(None, description="Код группы модели")
    model_code: Optional[str] = Field(None, description="Код модели")

    # Год выпуска
    year_from: Optional[str] = Field(None, description="Год выпуска от")
    year_to: Optional[str] = Field(None, description="Год выпуска до")

    # Цена аукциона
    price_from: Optional[str] = Field(None, description="Стартовая цена от")
    price_to: Optional[str] = Field(None, description="Стартовая цена до")

    # Пробег
    mileage_from: Optional[str] = Field(None, description="Пробег от")
    mileage_to: Optional[str] = Field(None, description="Пробег до")

    # Технические характеристики
    fuel_type: Optional[str] = Field(None, description="Тип топлива")
    transmission: Optional[str] = Field(None, description="Коробка передач")
    color_code: Optional[str] = Field(None, description="Код цвета")

    # Аукцион
    auction_type: str = Field("weekly", description="Тип аукциона")
    lane_type: Optional[str] = Field(None, description="Тип лейна (A, B или пусто для всех)")
    auction_location: Optional[str] = Field(None, description="Код места аукциона")

    # Пагинация
    page: int = Field(1, ge=1, description="Номер страницы")
    page_size: int = Field(
        18, ge=1, le=100, description="Количество результатов на странице"
    )

    # Дополнительные фильтры
    car_number: Optional[str] = Field(None, description="Номер автомобиля")
    sort_order: Optional[str] = Field(None, description="Порядок сортировки")

    class Config:
        populate_by_name = True


class KCarSearchResponse(BaseModel):
    """Расширенный ответ поиска с фильтрами"""

    request_params: Optional[Dict[str, Any]] = Field(
        None, alias="auctionReqVo", description="Параметры запроса"
    )
    cars: List[KCarCar] = Field(
        default_factory=list, alias="CAR_LIST", description="Список автомобилей"
    )
    total_count: Optional[int] = Field(None, description="Общее количество")
    current_page: int = Field(1, description="Текущая страница")
    page_size: int = Field(18, description="Размер страницы")
    total_pages: Optional[int] = Field(None, description="Общее количество страниц")
    has_next_page: bool = Field(False, description="Есть ли следующая страница")
    has_prev_page: bool = Field(False, description="Есть ли предыдущая страница")
    success: bool = Field(True, description="Статус успешности")
    message: Optional[str] = Field(None, description="Сообщение")

    class Config:
        populate_by_name = True
        allow_population_by_field_name = True
    
    def model_dump(self, **kwargs):
        """Override model_dump to ensure aliases are used"""
        kwargs["by_alias"] = True
        return super().model_dump(**kwargs)
    
    def dict(self, **kwargs):
        """Override dict for backward compatibility"""
        kwargs["by_alias"] = True
        return super().dict(**kwargs)


# Полный список производителей KCar для отображения в UI (новые коды из интерфейса)
KCAR_MANUFACTURERS = [
    # Корейские производители (001_XXX)
    KCarManufacturer(code="001_001", name="현대", name_en="Hyundai"),
    KCarManufacturer(code="001_007", name="제네시스", name_en="Genesis"),
    KCarManufacturer(code="001_002", name="기아", name_en="Kia"),
    KCarManufacturer(
        code="001_003", name="쉐보레(GM대우)", name_en="Chevrolet (GM Daewoo)"
    ),
    KCarManufacturer(
        code="001_005", name="르노코리아(삼성)", name_en="Renault Korea (Samsung)"
    ),
    KCarManufacturer(
        code="001_004", name="KG모빌리티(쌍용)", name_en="KG Mobility (SsangYong)"
    ),
    KCarManufacturer(code="001_088", name="대우버스", name_en="Daewoo Bus"),
    KCarManufacturer(code="001_006", name="기타 제조사", name_en="Other Domestic"),
    # Импортные производители - Европа (002_XXX)
    KCarManufacturer(code="002_013", name="벤츠", name_en="Mercedes-Benz"),
    KCarManufacturer(code="002_012", name="BMW", name_en="BMW"),
    KCarManufacturer(code="002_011", name="아우디", name_en="Audi"),
    KCarManufacturer(code="002_014", name="폭스바겐", name_en="Volkswagen"),
    KCarManufacturer(code="002_054", name="미니", name_en="MINI"),
    KCarManufacturer(code="002_017", name="볼보", name_en="Volvo"),
    KCarManufacturer(code="002_091", name="폴스타", name_en="Polestar"),
    KCarManufacturer(code="002_015", name="포르쉐", name_en="Porsche"),
    KCarManufacturer(code="002_081", name="스마트", name_en="Smart"),
    KCarManufacturer(code="002_053", name="마세라티", name_en="Maserati"),
    KCarManufacturer(code="002_019", name="재규어", name_en="Jaguar"),
    KCarManufacturer(code="002_020", name="랜드로버", name_en="Land Rover"),
    KCarManufacturer(code="002_021", name="푸조", name_en="Peugeot"),
    KCarManufacturer(code="002_022", name="시트로엥", name_en="Citroën"),
    KCarManufacturer(code="002_018", name="피아트", name_en="Fiat"),
    KCarManufacturer(code="002_041", name="페라리", name_en="Ferrari"),
    KCarManufacturer(code="002_049", name="람보르기니", name_en="Lamborghini"),
    KCarManufacturer(code="002_084", name="맥라렌", name_en="McLaren"),
    KCarManufacturer(code="002_080", name="마이바흐", name_en="Maybach"),
    KCarManufacturer(code="002_050", name="벤틀리", name_en="Bentley"),
    KCarManufacturer(code="002_047", name="롤스로이스", name_en="Rolls-Royce"),
    KCarManufacturer(code="002_016", name="사브", name_en="Saab"),
    KCarManufacturer(code="002_070", name="애스턴마틴", name_en="Aston Martin"),
    # Импортные производители - Япония (002_XXX)
    KCarManufacturer(code="002_035", name="렉서스", name_en="Lexus"),
    KCarManufacturer(code="002_031", name="도요타", name_en="Toyota"),
    KCarManufacturer(code="002_058", name="인피니티", name_en="Infiniti"),
    KCarManufacturer(code="002_027", name="혼다", name_en="Honda"),
    KCarManufacturer(code="002_033", name="닛산", name_en="Nissan"),
    KCarManufacturer(code="002_030", name="미쯔비시", name_en="Mitsubishi"),
    KCarManufacturer(code="002_037", name="스즈키", name_en="Suzuki"),
    KCarManufacturer(code="002_029", name="마쯔다", name_en="Mazda"),
    KCarManufacturer(code="002_028", name="이스즈", name_en="Isuzu"),
    KCarManufacturer(code="002_052", name="스바루", name_en="Subaru"),
    KCarManufacturer(code="002_051", name="다이하쯔", name_en="Daihatsu"),
    KCarManufacturer(code="002_057", name="어큐라", name_en="Acura"),
    # Импортные производители - США (002_XXX)
    KCarManufacturer(code="002_087", name="테슬라", name_en="Tesla"),
    KCarManufacturer(code="002_024", name="포드", name_en="Ford"),
    KCarManufacturer(code="002_083", name="지프", name_en="Jeep"),
    KCarManufacturer(code="002_043", name="캐딜락", name_en="Cadillac"),
    KCarManufacturer(code="002_023", name="크라이슬러", name_en="Chrysler"),
    KCarManufacturer(code="002_044", name="링컨", name_en="Lincoln"),
    KCarManufacturer(code="002_056", name="GMC", name_en="GMC"),
    KCarManufacturer(code="002_034", name="닷지", name_en="Dodge"),
    KCarManufacturer(code="002_038", name="쉐보레", name_en="Chevrolet"),
    KCarManufacturer(code="002_048", name="험머", name_en="Hummer"),
    # Импортные производители - Китай (002_XXX)
    KCarManufacturer(code="002_090", name="동풍소콘", name_en="Dongfeng Sokon"),
    KCarManufacturer(code="002_086", name="북기은상", name_en="BAIC"),
    KCarManufacturer(code="002_085", name="포톤", name_en="Foton"),
    KCarManufacturer(code="002_093", name="BYD", name_en="BYD"),
    KCarManufacturer(code="002_092", name="선롱 버스", name_en="Sunlong Bus"),
    # Коммерческие автомобили (003_XXX)
    KCarManufacturer(code="003_005", name="카고(화물)트럭", name_en="Cargo Truck"),
    KCarManufacturer(code="003_003", name="윙바디/탑", name_en="Wing Body/Top"),
    KCarManufacturer(code="003_002", name="버스", name_en="Bus"),
    KCarManufacturer(code="003_007", name="크레인 형태", name_en="Crane Type"),
    KCarManufacturer(
        code="003_004", name="차량견인/운송", name_en="Vehicle Towing/Transport"
    ),
    KCarManufacturer(
        code="003_011", name="폐기/음식물수송", name_en="Waste/Food Transport"
    ),
    KCarManufacturer(code="003_012", name="활어차", name_en="Live Fish Transport"),
    KCarManufacturer(code="003_008", name="탱크로리", name_en="Tank Lorry"),
    KCarManufacturer(code="003_010", name="트렉터", name_en="Tractor"),
    KCarManufacturer(code="003_009", name="트레일러", name_en="Trailer"),
    KCarManufacturer(
        code="003_001",
        name="덤프/건설/중기",
        name_en="Dump/Construction/Heavy Equipment",
    ),
    KCarManufacturer(
        code="003_006", name="캠핑카/캠핑 트레일러", name_en="Camping Car/Trailer"
    ),
    KCarManufacturer(code="003_999", name="기타", name_en="Others"),
]

# Упрощенный список производителей для работы с API KCar (старые коды)
KCAR_API_MANUFACTURERS = [
    KCarManufacturer(code="001", name="현대", name_en="Hyundai"),
    KCarManufacturer(code="002", name="기아", name_en="Kia"),
    KCarManufacturer(code="003", name="삼성르노", name_en="Samsung Renault"),
    KCarManufacturer(code="004", name="대우GM", name_en="Daewoo GM"),
    KCarManufacturer(code="005", name="쌍용", name_en="SsangYong"),
    KCarManufacturer(code="006", name="한국GM", name_en="GM Korea"),
    KCarManufacturer(code="007", name="수입", name_en="Import"),
    KCarManufacturer(code="008", name="기타", name_en="Others"),
]

# Mapping между UI кодами и API кодами
KCAR_UI_TO_API_MAPPING = {
    # Корейские производители
    "001_001": "001",  # Hyundai
    "001_007": "001",  # Genesis -> Hyundai
    "001_002": "002",  # Kia
    "001_003": "004",  # Chevrolet (GM Daewoo) -> Daewoo GM
    "001_005": "003",  # Renault Korea (Samsung) -> Samsung Renault
    "001_004": "005",  # KG Mobility (SsangYong) -> SsangYong
    "001_088": "008",  # Daewoo Bus -> Others
    "001_006": "008",  # Other Domestic -> Others
    # Импортные производители - используем фактические коды
    "002_013": "013",  # Mercedes-Benz
    "002_012": "012",  # BMW
    "002_011": "011",  # Audi
    "002_014": "014",  # Volkswagen
    "002_054": "054",  # MINI
    "002_017": "017",  # Volvo
    "002_091": "091",  # Polestar
    "002_015": "015",  # Porsche
    "002_081": "081",  # Smart
    "002_053": "053",  # Maserati
    "002_019": "019",  # Jaguar
    "002_020": "020",  # Land Rover
    "002_021": "021",  # Peugeot
    "002_022": "022",  # Citroën
    "002_018": "018",  # Fiat
    "002_041": "041",  # Ferrari
    "002_049": "049",  # Lamborghini
    "002_084": "084",  # McLaren
    "002_080": "080",  # Maybach
    "002_050": "050",  # Bentley
    "002_047": "047",  # Rolls-Royce
    "002_016": "016",  # Saab
    "002_070": "070",  # Aston Martin
    "002_035": "035",  # Lexus
    "002_031": "031",  # Toyota
    "002_058": "058",  # Infiniti
    "002_027": "027",  # Honda
    "002_033": "033",  # Nissan
    "002_030": "030",  # Mitsubishi
    "002_037": "037",  # Suzuki
    "002_029": "029",  # Mazda
    "002_028": "028",  # Isuzu
    "002_052": "052",  # Subaru
    "002_051": "051",  # Daihatsu
    "002_057": "057",  # Acura
    "002_087": "087",  # Tesla
    "002_024": "024",  # Ford
    "002_083": "083",  # Jeep
    "002_043": "043",  # Cadillac
    "002_023": "023",  # Chrysler
    "002_044": "044",  # Lincoln
    "002_056": "056",  # GMC
    "002_034": "034",  # Dodge
    "002_038": "038",  # Chevrolet
    "002_048": "048",  # Hummer
    "002_090": "090",  # Dongfeng Sokon
    "002_086": "086",  # BAIC
    "002_085": "085",  # Foton
    "002_093": "093",  # BYD
    "002_092": "092",  # Sunlong Bus
    # Коммерческие автомобили
    "003_005": "008",  # Cargo Truck -> Others
    "003_003": "008",  # Wing Body/Top -> Others
    "003_002": "008",  # Bus -> Others
    "003_007": "008",  # Crane Type -> Others
    "003_004": "008",  # Vehicle Towing/Transport -> Others
    "003_011": "008",  # Waste/Food Transport -> Others
    "003_012": "008",  # Live Fish Transport -> Others
    "003_008": "008",  # Tank Lorry -> Others
    "003_010": "008",  # Tractor -> Others
    "003_009": "008",  # Trailer -> Others
    "003_001": "008",  # Dump/Construction/Heavy Equipment -> Others
    "003_006": "008",  # Camping Car/Trailer -> Others
    "003_999": "008",  # Others -> Others
}


class KCarCountResponse(BaseModel):
    """Response for KCar total car count"""
    lane_a_count: int = Field(default=0, description="Number of cars in LANE A")
    lane_b_count: int = Field(default=0, description="Number of cars in LANE B")
    total_count: int = Field(default=0, description="Total number of cars (LANE A + LANE B)")
    success: bool = Field(default=True, description="Whether the request was successful")
    message: str = Field(default="", description="Response message")
    timestamp: datetime = Field(default_factory=datetime.now, description="Response timestamp")
