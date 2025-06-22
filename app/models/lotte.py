from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime


class FuelType(str, Enum):
    GASOLINE = "gasoline"
    DIESEL = "diesel"
    HYBRID = "hybrid"
    ELECTRIC = "electric"
    LPG = "lpg"
    UNKNOWN = "unknown"


class TransmissionType(str, Enum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    CVT = "cvt"
    UNKNOWN = "unknown"


class GradeType(str, Enum):
    A_A = "A/A"
    A_B = "A/B"
    A_C = "A/C"
    A_D = "A/D"
    B_A = "B/A"
    B_B = "B/B"
    B_C = "B/C"
    B_D = "B/D"
    C_A = "C/A"
    C_B = "C/B"
    C_C = "C/C"
    C_D = "C/D"
    D_A = "D/A"
    D_B = "D/B"
    D_C = "D/C"
    D_D = "D/D"
    UNKNOWN = "unknown"


class LotteCar(BaseModel):
    """Модель автомобиля с аукциона Lotte"""

    # Основная информация
    id: str = Field(..., description="Уникальный ID автомобиля")
    auction_number: str = Field(..., description="Номер на аукционе")
    lane: str = Field(..., description="Полоса (A, B, C, D)")
    license_plate: str = Field(..., description="Номерной знак")

    # Информация об автомобиле
    name: str = Field(..., description="Название автомобиля")
    model: str = Field(..., description="Модель")
    brand: str = Field(..., description="Марка")
    year: int = Field(..., description="Год выпуска", ge=1900, le=2030)

    # Технические характеристики
    mileage: int = Field(..., description="Пробег в км", ge=0)
    fuel_type: FuelType = Field(default=FuelType.UNKNOWN, description="Тип топлива")
    transmission: TransmissionType = Field(
        default=TransmissionType.UNKNOWN, description="Тип КПП"
    )
    engine_capacity: Optional[str] = Field(None, description="Объем двигателя")
    color: str = Field(..., description="Цвет")

    # Состояние и оценка
    grade: GradeType = Field(default=GradeType.UNKNOWN, description="Оценка состояния")

    # Финансовая информация
    starting_price: int = Field(
        ..., description="Стартовая цена в корейских вонах", ge=0
    )

    # Даты
    first_registration_date: Optional[str] = Field(
        None, description="Дата первой регистрации"
    )
    inspection_valid_until: Optional[str] = Field(
        None, description="Действие техосмотра до"
    )

    # Дополнительная информация
    usage_type: Optional[str] = Field(None, description="Тип использования")
    owner_info: Optional[str] = Field(None, description="Информация о владельце")
    vin_number: Optional[str] = Field(None, description="VIN номер")
    engine_model: Optional[str] = Field(None, description="Модель двигателя")

    # Изображения
    images: List[str] = Field(
        default_factory=list, description="Список URL изображений"
    )

    # Детали аукциона
    searchMngDivCd: Optional[str] = Field(None, description="Код управления поиском")
    searchMngNo: Optional[str] = Field(None, description="Номер управления поиском")
    searchExhiRegiSeq: Optional[str] = Field(
        None, description="Порядковый номер выставления"
    )


class LotteAuctionDate(BaseModel):
    """Модель даты аукциона Lotte"""

    auction_date: str = Field(..., description="Дата аукциона (YYYY-MM-DD)")
    year: int = Field(..., description="Год")
    month: int = Field(..., description="Месяц")
    day: int = Field(..., description="День")
    is_today: bool = Field(..., description="Является ли дата сегодняшней")
    is_future: bool = Field(..., description="Является ли дата будущей")
    raw_text: str = Field(..., description="Исходный текст даты")


class LotteResponse(BaseModel):
    """Модель ответа API для данных Lotte"""

    success: bool = Field(..., description="Успешность запроса")
    message: str = Field(..., description="Сообщение")

    # Информация о дате аукциона
    auction_date_info: Optional[LotteAuctionDate] = Field(
        None, description="Информация о дате аукциона"
    )

    # Данные автомобилей
    cars: List[LotteCar] = Field(default_factory=list, description="Список автомобилей")
    total_count: int = Field(default=0, description="Общее количество автомобилей")

    # Пагинация
    page: int = Field(default=1, description="Номер страницы")
    per_page: int = Field(default=20, description="Количество на странице")
    total_pages: int = Field(default=0, description="Общее количество страниц")

    # Информация о запросе
    timestamp: str = Field(..., description="Временная метка запроса")
    request_duration: Optional[float] = Field(
        None, description="Время выполнения запроса в секундах"
    )


class LotteError(BaseModel):
    """Модель ошибки API Lotte"""

    success: bool = Field(default=False, description="Успешность запроса")
    error_code: str = Field(..., description="Код ошибки")
    message: str = Field(..., description="Сообщение об ошибке")
    details: Optional[str] = Field(None, description="Детали ошибки")
    timestamp: str = Field(..., description="Временная метка ошибки")


class LotteCarOwner(BaseModel):
    """Информация о владельце автомобиля"""

    company_name: Optional[str] = None  # 상호(명칭)
    representative_name: Optional[str] = None  # 성명(대표자)
    registration_number: Optional[str] = None  # 주민등록번호 (masked)
    address: Optional[str] = None  # 주소


class LotteCarBasicInfo(BaseModel):
    """Основная информация об автомобиле"""

    title: Optional[str] = None  # THE ALL NEW TUCSON (G) 1.6 T 모던 2WD
    entry_number: Optional[str] = None  # 출품번호
    car_number: Optional[str] = None  # 차량번호
    old_car_number: Optional[str] = None  # 구차량번호
    car_name: Optional[str] = None  # 차명 (투싼)
    vin_number: Optional[str] = None  # 차대번호
    starting_price: Optional[str] = None  # 시작가
    auction_date: Optional[str] = None  # 출품일
    status: Optional[str] = None  # 진행상태
    evaluation_score: Optional[str] = None  # 평가점
    auction_result: Optional[str] = None  # 경매결과


class LotteCarTechnicalSpecs(BaseModel):
    """기술적 사양"""

    car_name: Optional[str] = None  # 차명 (투싼)
    vin_number: Optional[str] = None  # 차대번호
    year: Optional[str] = None  # 연식
    mileage: Optional[str] = None  # 주행거리
    first_registration_date: Optional[str] = None  # 최초등록일
    transmission: Optional[str] = None  # 변속기
    usage_type: Optional[str] = None  # 용도
    color: Optional[str] = None  # 색상
    engine_type: Optional[str] = None  # 원동기형식
    fuel_type: Optional[str] = None  # 연료
    inspection_valid_until: Optional[str] = None  # 검사유효일
    displacement: Optional[str] = None  # 배기량
    car_type: Optional[str] = None  # 차종
    seating_capacity: Optional[str] = None  # 승차정원
    main_options: Optional[str] = None  # 주요옵션
    special_notes: Optional[str] = None  # 특이사항
    complete_documents: Optional[str] = None  # 완비서류
    stored_items: Optional[str] = None  # 보관품


class LotteCarConditionCheck(BaseModel):
    """차량 상태 점검"""

    overall_score: Optional[str] = None  # 평가점 (F / F)
    engine_condition: Optional[str] = None  # 엔진
    transmission_condition: Optional[str] = None  # 미션
    brake_condition: Optional[str] = None  # 제동
    power_transmission_condition: Optional[str] = None  # 동력전달
    air_conditioning_condition: Optional[str] = None  # 공조
    steering_condition: Optional[str] = None  # 조항
    electrical_condition: Optional[str] = None  # 전기

    # Детальные проверки
    engine_device_check: Optional[str] = None  # 기관장치
    power_transmission_device_check: Optional[str] = None  # 동력전달장치
    brake_device_check: Optional[str] = None  # 제동장치
    steering_device_check: Optional[str] = None  # 조향장치
    lighting_device_check: Optional[str] = None  # 등화장치
    driving_device_check: Optional[str] = None  # 주행장치
    electrical_device_check: Optional[str] = None  # 축전기기계장치

    vin_check: Optional[str] = None  # 차대번호 확인
    seal_check: Optional[str] = None  # 봉인 확인
    address_change_check: Optional[str] = None  # 주소변경 확인

    status_map_image: Optional[str] = None  # 상태점검표 이미지
    special_notes: Optional[str] = None  # 특이사항


class LotteCarLegalStatus(BaseModel):
    """법적 상태 (압류/저당)"""

    last_inquiry_date: Optional[str] = None  # 최종조회일자
    seizure_count: Optional[int] = None  # 압류 건수
    mortgage_count: Optional[int] = None  # 저당 건수
    other_count: Optional[int] = None  # 구변 건수


class LotteCarMedia(BaseModel):
    """미디어 파일"""

    main_images: List[str] = []  # 메인 이미지들
    vr_image: Optional[str] = None  # VR 이미지
    thumbnail_images: List[str] = []  # 썸네일 이미지들
    detail_images: List[str] = []  # 상세 이미지들
    video_url: Optional[str] = None  # 차량 영상
    has_video: bool = False  # 영상 존재 여부


class LotteCarInspectionRecord(BaseModel):
    """점검/검사기록부"""

    record_number: Optional[str] = None  # 제 12101 호
    inspection_date: Optional[str] = None  # 2025년 06월 13일
    inspection_location: Optional[str] = None  # 롯데렌탈(주) 안성경매장
    inspector_name: Optional[str] = None  # 최진환

    identity_check_vin: bool = False  # 차대번호 동일성 확인
    identity_check_engine: bool = False  # 원동기형식 동일성 확인
    registration_check: Optional[str] = None  # 등록사항 확인


class LotteCarDetail(BaseModel):
    """완전한 Lotte 자동차 상세 정보"""

    # Основные разделы
    basic_info: LotteCarBasicInfo
    owner_info: LotteCarOwner
    technical_specs: LotteCarTechnicalSpecs
    condition_check: LotteCarConditionCheck
    legal_status: LotteCarLegalStatus
    media: LotteCarMedia
    inspection_record: LotteCarInspectionRecord

    # Мета-информация
    management_number: Optional[str] = None  # KS202506090099
    management_division: Optional[str] = None  # KS
    exhibition_sequence: Optional[str] = None  # 2

    # Технические поля
    parsed_at: Optional[datetime] = None
    source_url: Optional[str] = None


class LotteCarResponse(BaseModel):
    """Ответ API для детальной информации о автомобиле"""

    success: bool
    message: str
    data: Optional[LotteCarDetail] = None
    error: Optional[str] = None
