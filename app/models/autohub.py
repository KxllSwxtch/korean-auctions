from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List, Dict, Union
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

    # Информация об аукционе (для формирования ссылок на детальную страницу)
    auction_date: Optional[str] = Field(None, description="Дата аукциона (YYYY-MM-DD)")
    auction_title: Optional[str] = Field(None, description="Название аукциона")
    auction_code: Optional[str] = Field(None, description="Код аукциона")
    receive_code: Optional[str] = Field(None, description="Код получения")

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
    has_additional_images: bool = Field(
        default=True,
        description="Есть ли дополнительные изображения (доступны через car-detail endpoint)",
    )

    # Метаданные
    parsed_at: datetime = Field(
        default_factory=datetime.now, description="Время парсинга"
    )

    # Дополнительные поля для детальной информации
    entry_number: str = Field(default="", description="Номер выставки")
    vin_number: str = Field(default="", description="VIN номер")
    engine_type: str = Field(default="", description="Тип двигателя")
    mileage_unclear: Optional[bool] = Field(
        False, description="Неопределенность пробега"
    )
    displacement: str = Field(default="", description="Объем двигателя")
    color: str = Field(default="", description="Цвет")
    color_changed: Optional[bool] = Field(False, description="Изменение цвета")
    vehicle_type: str = Field(default="", description="Тип транспортного средства")
    accident_history: Optional[str] = Field(None, description="История аварий")
    tax_type: str = Field(default="", description="Тип налогообложения")
    electric_certificate: Optional[str] = Field(
        None, description="Сертификат электромобиля"
    )


class AutohubResponse(BaseModel):
    """Ответ API с данными Autohub"""

    success: bool = Field(..., description="Успешность выполнения запроса")
    data: List[AutohubCar] = Field(
        default_factory=list, description="Список автомобилей"
    )
    error: Optional[str] = Field(None, description="Сообщение об ошибке")
    total_count: int = Field(0, description="Общее количество найденных автомобилей")

    # Информация о пагинации
    page: int = Field(1, description="Текущая страница")
    limit: int = Field(20, description="Размер страницы")

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


class AutohubAuctionDate(BaseModel):
    """Дата аукциона Autohub"""

    date_str: str = Field(..., description="Строка с датой аукциона")


class AutohubPerformanceInfo(BaseModel):
    rating: str
    inspector: str
    stored_items: List[str]
    stored_items_present: str
    notes: str


class AutohubOptionInfo(BaseModel):
    """Информация об опциях автомобиля"""

    exterior_options: List[str] = Field(default_factory=list)
    interior_options: List[str] = Field(default_factory=list)
    safety_options: List[str] = Field(default_factory=list)
    convenience_options: List[str] = Field(default_factory=list)
    multimedia_options: List[str] = Field(default_factory=list)


class AutohubImage(BaseModel):
    """Изображение автомобиля"""

    large_url: str
    small_url: str
    sequence: int


class AutohubInspectionItem(BaseModel):
    """Элемент проверки части автомобиля"""

    part_id: int = Field(..., description="ID части автомобиля")
    part_name: str = Field(..., description="Название части")
    condition_code: str = Field(
        ..., description="Код состояния (@@@, X@@, W@@, A@@, U@@, E@@, M@@, F@@)"
    )
    condition_description: str = Field(..., description="Описание состояния")
    severity: Optional[str] = Field(None, description="Степень повреждения")

    @property
    def needs_replacement(self) -> bool:
        """Требует замены"""
        return self.condition_code.startswith("X") or self.condition_code == "X@@"

    @property
    def needs_bodywork(self) -> bool:
        """Требует кузовного ремонта"""
        return self.condition_code.startswith("W") or self.condition_code == "W@@"

    @property
    def has_minor_damage(self) -> bool:
        """Имеет незначительные повреждения"""
        return (
            self.condition_code.startswith("A")
            or self.condition_code == "@A@"
            or self.condition_code == "A@@"
        )

    @property
    def needs_painting(self) -> bool:
        """Требует покраски"""
        return self.condition_code.startswith("U") or self.condition_code == "U@@"

    @property
    def needs_replacement_required(self) -> bool:
        """Требует обязательной замены"""
        return self.condition_code.startswith("E") or self.condition_code == "E@@"


class AutohubInspectionReport(BaseModel):
    """Технический лист с результатами проверки автомобиля"""

    category_code: str = Field(
        ...,
        description="Код категории автомобиля (001=седан, 002=пикап, 003=микроавтобус, 004=грузовик)",
    )
    category_name: str = Field(..., description="Название категории автомобиля")

    # Основные показатели
    total_items: int = Field(..., description="Общее количество проверенных частей")
    damaged_items: int = Field(..., description="Количество поврежденных частей")
    replacement_needed: int = Field(
        ..., description="Количество частей, требующих замены"
    )
    bodywork_needed: int = Field(
        ..., description="Количество частей, требующих кузовного ремонта"
    )
    painting_needed: int = Field(
        ..., description="Количество частей, требующих покраски"
    )

    # Детальная информация по частям
    inspection_items: List[AutohubInspectionItem] = Field(
        default_factory=list, description="Детальная информация по каждой части"
    )

    # Дополнительная информация
    special_notes: Optional[str] = Field(None, description="Особые замечания")
    inspector_comments: Optional[str] = Field(
        None, description="Комментарии инспектора"
    )

    # Статистика по типам повреждений
    damage_summary: Dict[str, int] = Field(
        default_factory=dict, description="Сводка по типам повреждений"
    )


class AutohubCarDetail(BaseModel):
    # Основная информация
    title: str
    starting_price: str
    auction_number: str
    auction_date: str
    auction_title: str
    auction_code: str

    # Детальная информация об автомобиле
    car_info: AutohubCar

    # Оценка производительности
    performance_info: AutohubPerformanceInfo

    # Опции
    options: AutohubOptionInfo

    # Изображения
    images: List[AutohubImage]

    # Технический лист с заменами и покрасками
    inspection_report: Optional[AutohubInspectionReport] = Field(
        None, description="Технический лист с информацией о повреждениях и ремонте"
    )

    # Метаданные
    parsed_at: datetime
    source_url: str = "https://www.autohubauction.co.kr"


class AutohubCarDetailRequest(BaseModel):
    # Основные параметры запроса
    auction_number: str  # i_sAucNo
    auction_date: str  # i_sStartDt (format: YYYY-MM-DD)
    auction_title: str  # i_sAucTitle
    auction_code: str  # i_sAucCode
    receive_code: str  # receivecd

    # Опциональные параметры
    page_number: int = 1
    page_size: int = 10
    sort_flag: str = "entry"


class AutohubCarDetailResponse(BaseModel):
    success: bool
    data: Optional[Union[AutohubCarDetail, "AutohubCarDetailExtended"]] = None
    error: Optional[str] = None
    request_params: AutohubCarDetailRequest


# ===== МОДЕЛИ ДЛЯ СХЕМЫ ДЕТАЛЕЙ АВТОМОБИЛЯ =====


class CarPartCondition(str, Enum):
    """Состояние части автомобиля"""

    NORMAL = "@@@"  # Нормальное состояние
    REPLACEMENT_NEEDED = "X@@"  # Требует замены (красный X)
    ACCIDENT_DAMAGE = "@A@"  # Повреждение от аварии
    REPAIR_NEEDED = "@U@"  # Требует ремонта/шпатлевки (U)
    OPERATIONAL_DAMAGE = "@E@"  # Повреждение от эксплуатации (E)
    WELDING_NEEDED = "@W@"  # Требует сварки (W)


class CarType(str, Enum):
    """Тип автомобиля для схемы деталей"""

    SEDAN = "sedan"  # Седан (car_01) - части A, B, C, D
    PICKUP = "pickup"  # Пикап (car_02) - части E, F, G, H
    TRUCK = "truck"  # Грузовик/минивэн (car_03) - части M, N, O, P


class AutohubCarPart(BaseModel):
    """Информация о части автомобиля"""

    part_id: str = Field(..., description="ID части (например: A01, B01, C01)")
    part_code: str = Field(..., description="Код части в системе (например: ax010)")
    condition: CarPartCondition = Field(..., description="Состояние части")
    condition_symbol: str = Field("", description="Символ состояния (X, U, A, E, W)")
    zone: str = Field("", description="Зона автомобиля (left, top, right, bottom)")
    position_x: Optional[int] = Field(None, description="X координата на схеме")
    position_y: Optional[int] = Field(None, description="Y координата на схеме")
    image_path: str = Field("", description="Путь к изображению части")

    @property
    def is_damaged(self) -> bool:
        """Повреждена ли часть"""
        return self.condition != CarPartCondition.NORMAL

    @property
    def needs_replacement(self) -> bool:
        """Требует ли замены"""
        return self.condition == CarPartCondition.REPLACEMENT_NEEDED

    @property
    def needs_repair(self) -> bool:
        """Требует ли ремонта"""
        return self.condition in [
            CarPartCondition.REPAIR_NEEDED,
            CarPartCondition.WELDING_NEEDED,
            CarPartCondition.ACCIDENT_DAMAGE,
            CarPartCondition.OPERATIONAL_DAMAGE,
        ]


class AutohubCarDiagram(BaseModel):
    """Схема деталей автомобиля"""

    car_type: CarType = Field(..., description="Тип автомобиля")
    background_image: str = Field(..., description="Путь к фоновому изображению схемы")
    parts: List[AutohubCarPart] = Field(
        default_factory=list, description="Список частей автомобиля"
    )

    # Статистика
    total_parts: int = Field(0, description="Общее количество частей")
    damaged_parts: int = Field(0, description="Количество поврежденных частей")
    replacement_needed: int = Field(0, description="Количество частей требующих замены")
    repair_needed: int = Field(0, description="Количество частей требующих ремонта")

    def calculate_statistics(self):
        """Вычисляет статистику по частям"""
        self.total_parts = len(self.parts)
        self.damaged_parts = sum(1 for part in self.parts if part.is_damaged)
        self.replacement_needed = sum(
            1 for part in self.parts if part.needs_replacement
        )
        self.repair_needed = sum(1 for part in self.parts if part.needs_repair)


# Константы для парсинга схемы деталей
CAR_PART_ZONES = {
    # Седан (car_01)
    "A": "left",  # Левая сторона
    "B": "top",  # Верх
    "C": "right",  # Правая сторона
    "D": "bottom",  # Низ
    # Пикап (car_02)
    "E": "left",  # Левая сторона
    "F": "top",  # Верх
    "G": "right",  # Правая сторона
    "H": "bottom",  # Низ
    # Грузовик (car_03)
    "M": "left",  # Левая сторона
    "N": "top",  # Верх
    "O": "right",  # Правая сторона
    "P": "bottom",  # Низ
}

CAR_TYPE_MAPPING = {
    "car_01": CarType.SEDAN,
    "car_02": CarType.PICKUP,
    "car_03": CarType.TRUCK,
}

BACKGROUND_IMAGES = {
    CarType.SEDAN: "/images/front/car_info/bg_car1.png",
    CarType.PICKUP: "/images/front/car_info/bg_car2.png",
    CarType.TRUCK: "/images/front/car_info/bg_car3.png",
}


# Обновляем AutohubCarDetail для включения схемы деталей
class AutohubCarDetailExtended(AutohubCarDetail):
    """Расширенная информация об автомобиле с схемой деталей"""

    # Схема деталей автомобиля
    car_diagram: Optional[AutohubCarDiagram] = Field(
        None, description="Схема деталей автомобиля с повреждениями"
    )


# Константы для расшифровки кодов состояния
CONDITION_CODES = {
    "@@@": "Нормальное состояние",
    "X@@": "Замена",
    "W@@": "Кузовной ремонт, сварка",
    "A@@": "Незначительные повреждения",
    "@A@": "Незначительные повреждения",  # Альтернативный формат
    "U@@": "Кузовной ремонт, покраска требуется",
    "E@@": "Замена обязательна",
    "M@@": "Регулировка, снятие/установка",
    "F@@": "Повреждение/изгиб",
}

# Названия частей автомобиля по позициям (для седана - категория 001)
SEDAN_PARTS = {
    0: "Передний левый крыло",
    1: "Передний левый фонарь",
    2: "Передний левый бампер",
    3: "Передняя левая дверь",
    4: "Передняя левая стойка",
    5: "Задняя левая дверь",
    6: "Задний левый крыло",
    7: "Задний левый фонарь",
    8: "Задний левый бампер",
    9: "Передний капот",
    10: "Передний левый угол",
    11: "Передний правый угол",
    12: "Передняя панель",
    13: "Крыша передняя",
    14: "Крыша средняя",
    15: "Крыша задняя",
    16: "Задняя панель",
    17: "Задний левый угол",
    18: "Задний правый угол",
    19: "Задний капот",
    20: "Передний правый крыло",
    21: "Передний правый фонарь",
    22: "Передний правый бампер",
    23: "Передняя правая дверь",
    24: "Передняя правая стойка",
    25: "Задняя правая дверь",
    26: "Задний правый крыло",
    27: "Задний правый фонарь",
    28: "Задний правый бампер",
    29: "Нижняя передняя панель",
    30: "Левое зеркало",
    31: "Правое зеркало",
    32: "Нижняя средняя панель",
    33: "Нижняя задняя панель",
    34: "Левое заднее колесо",
    35: "Правое заднее колесо",
    36: "Центральная нижняя панель",
    37: "Нижняя задняя панель",
}

CATEGORY_NAMES = {
    "001": "Седан",
    "002": "Пикап",
    "003": "Микроавтобус",
    "004": "Грузовик",
}
