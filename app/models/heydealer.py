from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime


class LoginRequest(BaseModel):
    """Модель запроса для авторизации в HeyDealer"""

    username: str = Field(..., description="Логин пользователя")
    password: str = Field(..., description="Пароль пользователя")
    device_type: str = Field(default="pc", description="Тип устройства")


class LoginUser(BaseModel):
    """Модель пользователя в ответе авторизации"""

    hash_id: str = Field(..., description="Уникальный ID пользователя")


class LoginResponse(BaseModel):
    """Модель ответа авторизации HeyDealer"""

    user: LoginUser = Field(..., description="Данные пользователя")


class InteriorInfo(BaseModel):
    """Информация об интерьере автомобиля"""

    text: str = Field(..., description="Описание интерьера")
    codes: List[str] = Field(..., description="Цветовые коды")


class AuctionTag(BaseModel):
    """Тег аукциона"""

    text: str = Field(..., description="Полный текст тега")
    short_text: str = Field(..., description="Короткий текст тега")
    style: str = Field(..., description="Стиль отображения тега")


class CarDetail(BaseModel):
    """Детальная информация об автомобиле"""

    full_name: Optional[str] = Field(None, description="Полное название автомобиля")
    model_part_name: Optional[str] = Field(None, description="Название модели")
    grade_part_name: Optional[str] = Field(None, description="Название комплектации")
    brand_name: Optional[str] = Field(None, description="Название бренда")
    brand_image_url: Optional[str] = Field(None, description="URL изображения бренда")
    main_image_url: Optional[str] = Field(None, description="URL основного изображения")
    image_urls: List[str] = Field(
        default_factory=list, description="URLs всех изображений"
    )
    car_number: Optional[str] = Field(None, description="Номер автомобиля")
    year: Optional[int] = Field(None, description="Год выпуска")
    initial_registration_date: Optional[str] = Field(
        None, description="Дата первичной регистрации"
    )
    mileage: Optional[int] = Field(None, description="Пробег в км")
    color: Optional[str] = Field(None, description="Цвет")
    interior: Optional[str] = Field(None, description="Интерьер")
    interior_info: Optional[InteriorInfo] = Field(
        None, description="Информация об интерьере"
    )
    fuel: Optional[str] = Field(None, description="Тип топлива")
    fuel_display: Optional[str] = Field(None, description="Отображение типа топлива")
    transmission: Optional[str] = Field(None, description="Коробка передач")
    transmission_display: Optional[str] = Field(
        None, description="Отображение коробки передач"
    )
    location: Optional[str] = Field(None, description="Полное местоположение")
    short_location: Optional[str] = Field(None, description="Короткое местоположение")
    short_location_first_part_name: Optional[str] = Field(
        None, description="Первая часть местоположения"
    )
    is_pre_inspected: Optional[bool] = Field(
        None, description="Проведена ли предварительная инспекция"
    )
    dealer_zero_type: Optional[str] = Field(None, description="Тип дилерского аукциона")
    zero_type: Optional[str] = Field(None, description="Тип zero аукциона")


class Auction(BaseModel):
    """Информация об аукционе"""

    auction_type: str = Field(..., description="Тип аукциона")
    approved_at: str = Field(..., description="Время одобрения")
    end_at: str = Field(..., description="Время окончания")
    ended_at: Optional[str] = Field(None, description="Время фактического окончания")
    invalid_at: Optional[str] = Field(
        None, description="Время признания недействительным"
    )
    expire_at: Optional[str] = Field(None, description="Время истечения")
    expired_at: Optional[str] = Field(None, description="Время фактического истечения")
    selected_at: Optional[str] = Field(None, description="Время выбора")
    max_bids_count: int = Field(..., description="Максимальное количество ставок")
    bids_count: int = Field(..., description="Текущее количество ставок")
    selected_bid: Optional[Any] = Field(None, description="Выбранная ставка")
    highest_bid: Optional[Any] = Field(None, description="Самая высокая ставка")
    my_bid: Optional[Any] = Field(None, description="Моя ставка")
    my_bid_price: Optional[int] = Field(None, description="Цена моей ставки")
    is_visited: bool = Field(..., description="Посещался ли аукцион")
    is_starred: bool = Field(..., description="Добавлен ли в избранное")
    is_additional_information: bool = Field(
        ..., description="Есть ли дополнительная информация"
    )
    has_previous_bid: bool = Field(..., description="Были ли предыдущие ставки")
    category: str = Field(..., description="Категория аукциона")
    tags: List[AuctionTag] = Field(..., description="Теги аукциона")
    desired_price: Optional[int] = Field(None, description="Желаемая цена")
    previous_desired_price_diff: Optional[int] = Field(
        None, description="Разница с предыдущей желаемой ценой"
    )


class CarEtc(BaseModel):
    """Дополнительная информация об автомобиле"""

    is_associate_member_bid_unavailable: bool = Field(
        ..., description="Недоступна ли ставка для ассоциированного участника"
    )


class HeyDealerCar(BaseModel):
    """Модель автомобиля HeyDealer"""

    hash_id: str = Field(..., description="Уникальный ID автомобиля")
    status: str = Field(..., description="Статус автомобиля")
    status_display: str = Field(..., description="Отображаемый статус")
    detail: CarDetail = Field(..., description="Детальная информация")
    auction: Auction = Field(..., description="Информация об аукционе")
    etc: CarEtc = Field(..., description="Дополнительная информация")


class HeyDealerCarList(BaseModel):
    """Список автомобилей HeyDealer"""

    cars: List[HeyDealerCar] = Field(..., description="Список автомобилей")
    total_count: int = Field(..., description="Общее количество автомобилей")
    page: int = Field(..., description="Номер страницы")


class HeyDealerFilters(BaseModel):
    """Параметры фильтрации для HeyDealer"""

    page: int = Field(default=1, description="Номер страницы")
    type: str = Field(default="auction", description="Тип аукциона")
    is_subscribed: bool = Field(default=False, description="Только подписанные")
    is_retried: bool = Field(default=False, description="Только повторные")
    is_previously_bid: bool = Field(
        default=False, description="Только с предыдущими ставками"
    )
    order: str = Field(default="default", description="Порядок сортировки")


# Модели для унифицированного ответа (аналогично другим аукционам)
class HeyDealerResponse(BaseModel):
    """Унифицированный ответ для HeyDealer"""

    success: bool = Field(..., description="Успешность выполнения запроса")
    data: Optional[HeyDealerCarList] = Field(None, description="Данные автомобилей")
    message: str = Field(..., description="Сообщение о результате")
    total_count: int = Field(default=0, description="Общее количество автомобилей")
    current_page: int = Field(default=1, description="Текущая страница")


class ColorInfo(BaseModel):
    """Информация о цвете автомобиля"""

    text: str = Field(..., description="Название цвета")
    codes: List[str] = Field(..., description="Цветовые коды")


class ImageGroup(BaseModel):
    """Группа изображений"""

    type: str = Field(
        ..., description="Тип группы (outside, inside, scratch_and_others, wheel)"
    )
    name: str = Field(..., description="Название группы")
    image_urls: List[str] = Field(..., description="URLs изображений в группе")
    count: int = Field(..., description="Количество изображений")
    condition_types: List[str] = Field(..., description="Типы состояния")


class AdvancedOption(BaseModel):
    """Расширенная опция автомобиля"""

    hash_id: str = Field(..., description="ID опции")
    name: str = Field(..., description="Название опции")
    choice: Optional[str] = Field(None, description="Выбор опции")
    availability: str = Field(..., description="Доступность")
    availability_for_display: str = Field(
        ..., description="Доступность для отображения"
    )
    category: str = Field(..., description="Категория опции")
    category_display: str = Field(..., description="Отображение категории")
    is_preview: bool = Field(..., description="Является ли превью")
    choices: List[str] = Field(..., description="Доступные варианты")
    is_user_selectable: bool = Field(..., description="Может ли пользователь выбирать")
    is_auto_choice: bool = Field(..., description="Автоматический выбор")


class CarSpec(BaseModel):
    """Спецификация автомобиля"""

    title: str = Field(..., description="Заголовок спецификации")
    description: str = Field(..., description="Описание спецификации")


class AccidentRepair(BaseModel):
    """Информация о ремонте после аварии"""

    part: str = Field(..., description="Часть автомобиля")
    repair: str = Field(..., description="Тип ремонта")


class AccidentInfo(BaseModel):
    """Информация об аварии"""

    description: str = Field(..., description="Описание аварии")
    insurance_money_display: str = Field(..., description="Страховая выплата")
    insurance_money: int = Field(..., description="Сумма страховой выплаты")
    accident_date: str = Field(..., description="Дата аварии")
    accident_type: str = Field(..., description="Тип аварии")
    is_severe_accident: bool = Field(..., description="Серьезная ли авария")
    amount: int = Field(..., description="Сумма ущерба")


class CarHistory(BaseModel):
    """История автомобиля"""

    result_code: str = Field(..., description="Код результата")
    car_number: str = Field(..., description="Номер автомобиля")
    year: int = Field(..., description="Год выпуска")
    car_type: str = Field(..., description="Тип автомобиля")
    use: str = Field(..., description="Использование")
    displacement: int = Field(..., description="Объем двигателя")
    model_group: str = Field(..., description="Группа модели")
    initial_registration_date: str = Field(
        ..., description="Дата первичной регистрации"
    )
    fuel: str = Field(..., description="Тип топлива")
    fuel_display: str = Field(..., description="Отображение типа топлива")
    shape: str = Field(..., description="Форма кузова")
    car_number_changed_count: int = Field(..., description="Количество смен номера")
    owner_changed_count: int = Field(..., description="Количество смен владельца")
    my_car_accident_count: int = Field(..., description="Количество аварий владельца")
    other_car_accident_count: int = Field(..., description="Количество аварий других")
    my_car_accident_cost: int = Field(..., description="Стоимость аварий владельца")
    stolen_count: int = Field(..., description="Количество краж")
    total_loss_count: int = Field(..., description="Количество полных потерь")
    flooded_count: int = Field(..., description="Количество затоплений")
    my_car_accident_list: List[AccidentInfo] = Field(
        ..., description="Список аварий владельца"
    )


class VehicleInformation(BaseModel):
    """Информация о транспортном средстве"""

    is_erased: bool = Field(..., description="Удалена ли информация")
    car_number: str = Field(..., description="Номер автомобиля")
    car_name: str = Field(..., description="Название автомобиля")
    car_type: str = Field(..., description="Тип автомобиля")
    vin: str = Field(..., description="VIN номер")
    purpose: str = Field(..., description="Назначение")
    year: int = Field(..., description="Год выпуска")
    color: str = Field(..., description="Цвет")
    registration_type: str = Field(..., description="Тип регистрации")
    initial_registration_date: str = Field(
        ..., description="Дата первичной регистрации"
    )
    manufactured_date: str = Field(..., description="Дата производства")
    inspection_valid_from: str = Field(..., description="Действие техосмотра с")
    inspection_valid_until: str = Field(..., description="Действие техосмотра до")
    mileage: int = Field(..., description="Пробег")


class InspectedCondition(BaseModel):
    """Проверенное состояние автомобиля"""

    front_tire: int = Field(..., description="Состояние передних шин (%)")
    rear_tire: int = Field(..., description="Состояние задних шин (%)")
    wheel_scratch: int = Field(..., description="Царапины на дисках")
    outer_panel_scratch: int = Field(..., description="Царапины на кузове")
    has_leakage: bool = Field(..., description="Есть ли утечки")
    has_dashboard_warning: bool = Field(
        ..., description="Есть ли предупреждения на панели"
    )
    has_option_malfunction: bool = Field(..., description="Есть ли неисправности опций")
    comment: str = Field(..., description="Комментарий инспектора")


class AuctionHistory(BaseModel):
    """История аукциона"""

    date: str = Field(..., description="Дата аукциона")
    highest_bid_price: int = Field(..., description="Максимальная ставка")
    bids_count: int = Field(..., description="Количество ставок")


class UserHistory(BaseModel):
    """История пользователя"""

    cars_count: int = Field(..., description="Количество автомобилей")
    traded_cars_count: int = Field(..., description="Количество проданных автомобилей")


class DetailedCarDetail(BaseModel):
    """Расширенная детальная информация об автомобиле"""

    detail_hash_id: str = Field(..., description="ID детальной информации")
    model_hash_id: str = Field(..., description="ID модели")
    full_name: str = Field(..., description="Полное название")
    full_name_without_brand: str = Field(..., description="Название без бренда")
    is_detail_verified: bool = Field(..., description="Проверены ли детали")
    model_part_name: str = Field(..., description="Название модели")
    grade_part_name: str = Field(..., description="Название комплектации")
    brand_name: str = Field(..., description="Название бренда")
    brand_image_url: str = Field(..., description="URL изображения бренда")
    main_image_url: str = Field(..., description="URL основного изображения")
    image_urls: List[str] = Field(..., description="URLs всех изображений")
    image_groups: List[ImageGroup] = Field(..., description="Группы изображений")
    car_number: str = Field(..., description="Номер автомобиля")
    year: int = Field(..., description="Год выпуска")
    initial_registration_date: str = Field(
        ..., description="Дата первичной регистрации"
    )
    mileage: int = Field(..., description="Пробег")
    color: str = Field(..., description="Цвет")
    interior: str = Field(..., description="Интерьер")
    color_info: ColorInfo = Field(..., description="Информация о цвете")
    interior_info: InteriorInfo = Field(..., description="Информация об интерьере")
    location: str = Field(..., description="Местоположение")
    short_location: str = Field(..., description="Короткое местоположение")
    short_location_first_part_name: str = Field(
        ..., description="Первая часть местоположения"
    )
    payment: str = Field(..., description="Способ оплаты")
    payment_display: str = Field(..., description="Отображение способа оплаты")
    fuel: str = Field(..., description="Тип топлива")
    fuel_display: str = Field(..., description="Отображение типа топлива")
    transmission: str = Field(..., description="Коробка передач")
    transmission_display: str = Field(..., description="Отображение коробки передач")
    accident: Optional[str] = Field(None, description="Информация об авариях")
    accident_display: Optional[str] = Field(
        None, description="Отображение информации об авариях"
    )
    accident_description: str = Field(..., description="Описание аварий")
    accident_repairs: List[AccidentRepair] = Field(
        ..., description="Ремонт после аварий"
    )
    accident_repairs_summary: str = Field(..., description="Сводка по ремонту")
    accident_repairs_summary_display: str = Field(
        ..., description="Отображение сводки по ремонту"
    )
    is_accident_image_visible: bool = Field(
        ..., description="Видны ли изображения аварий"
    )
    is_advanced_options: bool = Field(..., description="Есть ли расширенные опции")
    advanced_options: List[AdvancedOption] = Field(..., description="Расширенные опции")
    description: Optional[str] = Field(None, description="Описание")
    car_description: str = Field(..., description="Описание автомобиля")
    customer_comment: str = Field(..., description="Комментарий клиента")
    inspector_comment: str = Field(..., description="Комментарий инспектора")
    comment: str = Field(..., description="Общий комментарий")
    car_spec: CarSpec = Field(..., description="Спецификация автомобиля")
    carhistory: CarHistory = Field(..., description="История автомобиля")
    vehicle_information: VehicleInformation = Field(..., description="Информация о ТС")
    phone_number: Optional[str] = Field(None, description="Номер телефона")
    is_reverse_year: bool = Field(..., description="Обратный год")
    inspected_condition: InspectedCondition = Field(
        ..., description="Проверенное состояние"
    )
    is_pre_inspected: bool = Field(..., description="Предварительно проверен")
    dealer_zero_type: Optional[str] = Field(None, description="Тип дилерского аукциона")
    zero_type: str = Field(..., description="Тип zero аукциона")
    early_scrap_display: str = Field(..., description="Отображение ранней утилизации")
    is_operation_unavailable: bool = Field(..., description="Недоступна ли операция")
    operation_unavailable_reasons: List[str] = Field(
        ..., description="Причины недоступности"
    )
    standard_new_car_price: int = Field(..., description="Стандартная цена нового авто")


class DetailedAuction(BaseModel):
    """Расширенная информация об аукционе"""

    auction_type: str = Field(..., description="Тип аукциона")
    visits_count: int = Field(..., description="Количество просмотров")
    approved_at: str = Field(..., description="Время одобрения")
    end_at: str = Field(..., description="Время окончания")
    ended_at: Optional[str] = Field(None, description="Время фактического окончания")
    invalid_at: Optional[str] = Field(
        None, description="Время признания недействительным"
    )
    expire_at: Optional[str] = Field(None, description="Время истечения")
    expired_at: Optional[str] = Field(None, description="Время фактического истечения")
    selected_at: Optional[str] = Field(None, description="Время выбора")
    bids: List[Any] = Field(..., description="Список ставок")
    max_bids_count: int = Field(..., description="Максимальное количество ставок")
    bids_count: int = Field(..., description="Текущее количество ставок")
    selected_bid: Optional[Any] = Field(None, description="Выбранная ставка")
    highest_bid: Optional[Any] = Field(None, description="Самая высокая ставка")
    my_bid: Optional[Any] = Field(None, description="Моя ставка")
    my_bid_price: Optional[int] = Field(None, description="Цена моей ставки")
    is_starred: bool = Field(..., description="Добавлен ли в избранное")
    is_additional_information: bool = Field(
        ..., description="Есть ли дополнительная информация"
    )
    has_previous_bid: bool = Field(..., description="Были ли предыдущие ставки")
    category: str = Field(..., description="Категория аукциона")
    is_bid_unavailable: bool = Field(..., description="Недоступна ли ставка")
    bid_unavailable_message: Optional[str] = Field(
        None, description="Сообщение о недоступности ставки"
    )
    desired_price: int = Field(..., description="Желаемая цена")
    auction_histories: List[AuctionHistory] = Field(
        ..., description="История аукционов"
    )
    user_history: UserHistory = Field(..., description="История пользователя")


class DetailedCarEtc(BaseModel):
    """Расширенная дополнительная информация"""

    has_corporate_owner: bool = Field(..., description="Есть ли корпоративный владелец")
    revision: int = Field(..., description="Версия")


class HeyDealerDetailedCar(BaseModel):
    """Детальная модель автомобиля HeyDealer"""

    hash_id: str = Field(..., description="Уникальный ID автомобиля")
    status: str = Field(..., description="Статус автомобиля")
    status_display: str = Field(..., description="Отображаемый статус")
    detail: DetailedCarDetail = Field(..., description="Детальная информация")
    auction: DetailedAuction = Field(..., description="Информация об аукционе")
    etc: DetailedCarEtc = Field(..., description="Дополнительная информация")


class HeyDealerDetailResponse(BaseModel):
    """Ответ для детальной информации об автомобиле"""

    success: bool = Field(..., description="Успешность выполнения запроса")
    data: Optional[HeyDealerDetailedCar] = Field(
        None, description="Детальные данные автомобиля"
    )
    message: str = Field(..., description="Сообщение о результате")


# === ФИЛЬТРЫ ===
class HeyDealerBrand(BaseModel):
    """Модель марки автомобиля"""

    hash_id: str
    name: str
    is_domestic: bool
    image_url: str
    count: int
    is_subscribed: Optional[bool] = None
    has_subscription: Optional[bool] = None
    can_subscribe: Optional[bool] = None


class HeyDealerModelGroup(BaseModel):
    """Модель группы моделей"""

    hash_id: str
    name: str
    count: int
    is_subscribed: Optional[bool] = None
    has_subscription: Optional[bool] = None


class HeyDealerModel(BaseModel):
    """Модель поколения автомобиля"""

    hash_id: str
    name: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    count: int
    is_subscribed: Optional[bool] = None


class HeyDealerGrade(BaseModel):
    """Модель конфигурации автомобиля"""

    hash_id: str
    name: str
    count: int
    fuel_display: str
    fuel_color_code: str


# === ОТВЕТЫ ДЛЯ ФИЛЬТРОВ ===
class HeyDealerBrandsResponse(BaseModel):
    """Ответ со списком марок"""

    success: bool
    data: List[HeyDealerBrand]
    message: str


class HeyDealerBrandDetailResponse(BaseModel):
    """Ответ с деталями марки и списком моделей"""

    success: bool
    data: Dict[str, Any]  # Содержит информацию о марке и model_groups
    message: str


class HeyDealerModelDetailResponse(BaseModel):
    """Ответ с деталями модели и списком поколений"""

    success: bool
    data: Dict[str, Any]  # Содержит информацию о модели и models
    message: str


class HeyDealerGradeDetailResponse(BaseModel):
    """Ответ с деталями поколения и списком конфигураций"""

    success: bool
    data: Dict[str, Any]  # Содержит информацию о поколении и grades
    message: str


# === ПАРАМЕТРЫ ФИЛЬТРАЦИИ ===
class HeyDealerFilterParams(BaseModel):
    """Параметры для фильтрации автомобилей"""

    page: int = 1
    type: str = "auction"
    is_subscribed: str = "false"
    is_retried: str = "false"
    is_previously_bid: str = "false"
    brand: Optional[str] = None
    model_group: Optional[str] = None
    model: Optional[str] = None
    grade: Optional[str] = None
    order: str = "default"

    # Дополнительные фильтры
    min_year: Optional[int] = None
    max_year: Optional[int] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    min_mileage: Optional[int] = None
    max_mileage: Optional[int] = None
    fuel: Optional[str] = None
    transmission: Optional[str] = None
    location: Optional[str] = None


# === МОДЕЛИ ДЛЯ ДОПОЛНИТЕЛЬНЫХ ФИЛЬТРОВ ===


class FilterOption(BaseModel):
    """Базовая модель для опции фильтра"""

    name: str
    value: str


class ApprovedAtFilter(BaseModel):
    """Фильтр по времени одобрения"""

    min_approved_at: Optional[str] = None
    max_approved_at: Optional[str] = None
    count: Optional[int] = None
    key: str
    title: str
    description: Optional[str] = None


class YearRange(BaseModel):
    """Диапазон годов"""

    min: int
    max: int


class LocationFilter(BaseModel):
    """Фильтр по местоположению"""

    value: Optional[str] = None
    name: Optional[str] = None


class HeyDealerAvailableFilters(BaseModel):
    """Доступные фильтры для HeyDealer"""

    approved_at: List[ApprovedAtFilter]
    year: YearRange
    location_first_part: List[LocationFilter]
    transmission: List[FilterOption]
    payment: List[FilterOption]
    car_type: List[FilterOption]
    car_segment: List[FilterOption]
    fuel: List[FilterOption]
    mileage: List[int]
    mileage_group: List[FilterOption]
    accident_group: List[FilterOption]
    accident_repairs_summary: List[FilterOption]
    wheel_drive: List[FilterOption]
    my_car_accident_cost: List[FilterOption]
    owner_change_record: List[FilterOption]
    use_record: List[FilterOption]
    special_accident_record: List[FilterOption]
    operation_availability: List[FilterOption]


class HeyDealerFiltersResponse(BaseModel):
    """Ответ с доступными фильтрами"""

    success: bool
    data: HeyDealerAvailableFilters
    message: str


class HeyDealerAdvancedFilterParams(BaseModel):
    """Расширенные параметры фильтрации для HeyDealer"""

    # Базовые параметры
    type: str = "auction"
    is_subscribed: str = "false"
    is_retried: str = "false"
    is_previously_bid: str = "false"
    page: int = 1
    order: str = "default"

    # Фильтры по автомобилю
    brand: Optional[str] = None
    model_group: Optional[str] = None
    model: Optional[str] = None
    grade: Optional[str] = None

    # Год выпуска
    min_year: Optional[int] = None
    max_year: Optional[int] = None

    # Пробег
    min_mileage: Optional[int] = None
    max_mileage: Optional[int] = None
    mileage_group: Optional[str] = None  # "(0, 30000)", "(30000, 50000)" и т.д.

    # Топливо (может быть список)
    fuel: Optional[Union[str, List[str]]] = (
        None  # ["gasoline", "diesel", "lpg", "hybrid", "electric"]
    )

    # Трансмиссия
    transmission: Optional[str] = None  # "auto", "manual"

    # Привод
    wheel_drive: Optional[str] = None  # "2WD", "4WD"

    # Тип кузова/сегмент (может быть список)
    car_segment: Optional[Union[str, List[str]]] = (
        None  # ["a", "b", "c", "d", "f", "s", "suv"]
    )

    # Тип автомобиля
    car_type: Optional[str] = None  # "domestic", "foreign", "etc"

    # Местоположение (может быть список)
    location_first_part: Optional[Union[str, List[str]]] = (
        None  # ["9", "101"] - коды регионов
    )

    # Способ оплаты (может быть список)
    payment: Optional[Union[str, List[str]]] = (
        None  # ["cash", "finance_lease", "operating_lease", "rent"]
    )

    # Дата одобрения
    min_approved_at: Optional[str] = None
    max_approved_at: Optional[str] = None
    approved_at_key: Optional[str] = None  # "2025-06-25 00:00:00~"

    # Аварийность
    accident_repairs_summary: Optional[str] = (
        None  # "complete_no_accident", "simple_exchange_no_accident", "accident"
    )
    accident_group: Optional[Union[str, List[str]]] = (
        None  # ["minor", "major", "critical"]
    )

    # История автомобиля
    my_car_accident_cost: Optional[str] = (
        None  # "none", "gt_0_lte_1000k", "gt_1000k_lte_3000k", "gt_3000k"
    )
    owner_change_record: Optional[str] = None  # "none", "exists"
    use_record: Optional[str] = None  # "none", "rent", "business", "public"
    special_accident_record: Optional[str] = None  # "none", "exists"

    # Работоспособность
    operation_availability: Optional[str] = None  # "available", "unavailable"


class HeyDealerListResponse(BaseModel):
    """Ответ со списком автомобилей"""

    success: bool
    data: List[Dict[str, Any]]  # Изменено для поддержки нормализованных данных
    message: str


# === МОДЕЛИ ДЛЯ ТЕХНИЧЕСКОГО ЛИСТА (ACCIDENT REPAIRS) ===


class MaxReductionRatio(BaseModel):
    """Максимальные коэффициенты снижения цены"""

    exchange: float = Field(..., description="Коэффициент для замены")
    weld: float = Field(..., description="Коэффициент для сварки")


class AccidentRepairDetail(BaseModel):
    """Детальная информация о ремонте части автомобиля"""

    part: str = Field(..., description="Часть автомобиля (bumper_front, hood, etc.)")
    part_display: str = Field(..., description="Отображаемое название части")
    repair: str = Field(..., description="Тип ремонта (none, exchange, weld)")
    repair_display: str = Field(..., description="Отображаемый тип ремонта")
    position: List[int] = Field(..., description="Позиция на схеме [x, y]")
    category: str = Field(
        ..., description="Категория части (frame, outer_panel_rank_1, etc.)"
    )
    max_reduction_ratio: MaxReductionRatio = Field(
        ..., description="Максимальные коэффициенты снижения цены"
    )
    max_reduction_ratio_for_zero: MaxReductionRatio = Field(
        ..., description="Коэффициенты для zero аукциона"
    )


class AccidentRepairsResponse(BaseModel):
    """Ответ API с техническим листом автомобиля"""

    type: Optional[str] = Field(None, description="Тип схемы повреждений")
    image_url: str = Field(..., description="URL схемы автомобиля")
    image_width: int = Field(..., description="Ширина изображения схемы")
    accident_repairs: List[AccidentRepairDetail] = Field(
        ..., description="Список деталей и их состояние"
    )


class AccidentRepairsFullResponse(BaseModel):
    """Полный ответ с техническим листом"""

    success: bool = Field(..., description="Успешность выполнения запроса")
    data: Optional[AccidentRepairsResponse] = Field(
        None, description="Данные технического листа"
    )
    message: str = Field(..., description="Сообщение о результате")
    timestamp: str = Field(..., description="Время выполнения запроса")


# === РАСШИРЕННЫЕ МОДЕЛИ ДЛЯ АВТОМОБИЛЕЙ С ТЕХНИЧЕСКИМ ЛИСТОМ ===


class CarWithAccidentRepairs(BaseModel):
    """Автомобиль с техническим листом"""

    # Базовая информация об автомобиле
    hash_id: str = Field(..., description="Уникальный ID автомобиля")
    status: str = Field(..., description="Статус автомобиля")
    status_display: str = Field(..., description="Отображаемый статус")
    full_name: Optional[str] = Field(None, description="Полное название автомобиля")
    brand_name: Optional[str] = Field(None, description="Название бренда")
    year: Optional[int] = Field(None, description="Год выпуска")
    mileage: Optional[int] = Field(None, description="Пробег")
    main_image_url: Optional[str] = Field(None, description="URL основного изображения")
    desired_price: Optional[int] = Field(None, description="Желаемая цена")

    # Технический лист
    accident_repairs: Optional[AccidentRepairsResponse] = Field(
        None, description="Технический лист автомобиля"
    )


class CarWithAccidentRepairsResponse(BaseModel):
    """Ответ с автомобилем и техническим листом"""

    success: bool = Field(..., description="Успешность выполнения запроса")
    data: Optional[CarWithAccidentRepairs] = Field(
        None, description="Данные автомобиля с техническим листом"
    )
    message: str = Field(..., description="Сообщение о результате")
    timestamp: str = Field(..., description="Время выполнения запроса")
