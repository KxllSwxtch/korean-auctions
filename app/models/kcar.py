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
        None, alias="START_RNUM", description="Начальный номер"
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
