from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, computed_field, model_validator


class ExtensibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class GlovisAuction(BaseModel):
    number: str
    acc: str
    title: str
    date: date


class GlovisAuctionsResponse(BaseModel):
    success: Literal[True] = True
    auctions: list[GlovisAuction]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GlovisOption(BaseModel):
    value: str
    label: str
    count: StrictInt = Field(default=0, ge=0)


class GlovisFilterItemsResponse(BaseModel):
    success: Literal[True] = True
    items: list[GlovisOption]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GlovisSearchForm(BaseModel):
    colors: list[GlovisOption] = Field(default_factory=list)
    options: list[GlovisOption] = Field(default_factory=list)
    lanes: list[GlovisOption] = Field(default_factory=list)
    transmissions: list[GlovisOption] = Field(default_factory=list)
    fuels: list[GlovisOption] = Field(default_factory=list)
    insurance_damage: list[GlovisOption] = Field(default_factory=list)
    usage_history: list[GlovisOption] = Field(default_factory=list)
    accident_history: list[GlovisOption] = Field(default_factory=list)
    sort_orders: list[GlovisOption] = Field(default_factory=list)
    rooms: list[GlovisOption] = Field(default_factory=list)
    bid_statuses: list[GlovisOption] = Field(default_factory=list)


class GlovisFilterOptionsResponse(BaseModel):
    success: Literal[True] = True
    filters: GlovisSearchForm
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GlovisCar(BaseModel):
    gn: str
    rc: str
    acc: str
    atn: str
    title: str
    lot_number: str
    thumbnail: str | None = None
    room: str | None = None
    lane: str | None = None
    plate_number: str | None = None
    year: StrictInt | None = Field(default=None, ge=1900, le=2200)
    mileage: StrictInt | None = Field(default=None, ge=0)
    displacement: StrictInt | None = Field(default=None, ge=0)
    start_price: StrictInt | None = Field(default=None, ge=0)
    fuel_type: str | None = None
    transmission: str | None = None
    color: str | None = None
    rating: str | None = None
    brand_code: str | None = None
    brand: str | None = None
    model_code: str | None = None
    model: str | None = None
    submodel_code: str | None = None
    submodel: str | None = None
    configuration: str | None = None
    status: str | None = None


class GlovisCarsQuery(BaseModel):
    atn: str
    acc: str
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=15, ge=1, le=60)
    brand: str | None = None
    model: str | None = None
    submodel: str | None = None
    year_from: int | None = Field(default=None, ge=1900, le=2200)
    year_to: int | None = Field(default=None, ge=1900, le=2200)
    mileage_from: int | None = Field(default=None, ge=0)
    mileage_to: int | None = Field(default=None, ge=0)
    price_from: int | None = Field(default=None, ge=0)
    price_to: int | None = Field(default=None, ge=0)
    transmission: str | None = None
    fuel_type: str | None = None
    color: str | None = None
    options: list[str] = Field(default_factory=list)
    insurance_damage: str | None = None
    usage_history: list[str] = Field(default_factory=list)
    accident_history: str | None = None
    room: str | None = None
    lane: str | None = None
    bid_status: str | None = None
    sort_order: str = "01"

    @model_validator(mode="after")
    def validate_relationships(self) -> "GlovisCarsQuery":
        if self.model and not self.brand:
            raise ValueError("model requires brand")
        if self.submodel and not (self.brand and self.model):
            raise ValueError("submodel requires brand and model")
        for lower, upper, label in (
            (self.year_from, self.year_to, "year"),
            (self.mileage_from, self.mileage_to, "mileage"),
            (self.price_from, self.price_to, "price"),
        ):
            if lower is not None and upper is not None and lower > upper:
                raise ValueError(f"{label}_from must be <= {label}_to")
        return self

    def upstream_params(self, page: int | None = None) -> list[tuple[str, str]]:
        values: list[tuple[str, str]] = [
            ("atn", self.atn),
            ("acc", self.acc),
            ("page", str(page or self.page)),
            ("page_size", str(self.page_size)),
            ("lang", "en"),
        ]
        for name in (
            "brand", "model", "submodel", "year_from", "year_to",
            "mileage_from", "mileage_to", "price_from", "price_to",
            "transmission", "fuel_type", "color", "insurance_damage",
            "accident_history", "room", "lane", "bid_status",
        ):
            value = getattr(self, name)
            if value is not None and value != "":
                values.append((name, str(value)))
        values.extend(("options", value) for value in self.options if value)
        values.extend(
            ("usage_history", value) for value in self.usage_history if value
        )
        values.append(("sort_order", self.sort_order))
        return values


class GlovisCarsResponse(BaseModel):
    success: Literal[True] = True
    total: StrictInt = Field(ge=0)
    items: list[GlovisCar]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=60)
    atn: str
    acc: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @computed_field
    @property
    def has_next_page(self) -> bool:
        return self.page * self.page_size < self.total


class GlovisMain(ExtensibleModel):
    gn: str
    rc: str
    acc: str
    atn: str
    title: str
    lot_number: str | None = None
    lane: str | None = None
    room: str | None = None
    plate_number: str | None = None
    vin: str | None = None
    year: StrictInt | None = None
    mileage: StrictInt | None = None
    displacement: StrictInt | None = None
    fuel_type: str | None = None
    transmission: str | None = None
    color: str | None = None
    vehicle_type: str | None = None
    brand_code: str | None = None
    brand: str | None = None
    model_code: str | None = None
    model: str | None = None
    submodel_code: str | None = None
    submodel: str | None = None
    configuration: str | None = None
    first_registration_date: date | None = None
    registration_date: date | None = None
    start_price: StrictInt | None = None
    sold_price: StrictInt | None = None
    hope_price: StrictInt | None = None
    auction_start_time: datetime | str | None = None
    absentee_bid_start_time: datetime | str | None = None
    rating: dict[str, Any] | str | None = None
    status: str | None = None


class GlovisEquipmentOption(ExtensibleModel):
    name: str
    enabled: bool


class GlovisLegalStatus(ExtensibleModel):
    seizures: StrictInt | None = Field(default=None, ge=0)
    mortgages: StrictInt | None = Field(default=None, ge=0)


class GlovisSpecialAccidents(ExtensibleModel):
    total_loss: StrictInt | None = Field(default=None, ge=0)
    theft: StrictInt | None = Field(default=None, ge=0)
    flood_total: StrictInt | None = Field(default=None, ge=0)
    flood_partial: StrictInt | None = Field(default=None, ge=0)


class GlovisInsuranceHistory(ExtensibleModel):
    special_accidents: GlovisSpecialAccidents | None = None
    plate_changes: StrictInt | None = Field(default=None, ge=0)
    owner_changes: StrictInt | None = Field(default=None, ge=0)


class GlovisAccidentRecord(ExtensibleModel):
    date: str | None = None
    status: str | None = None
    type: str | None = None
    parts_cost: StrictInt | None = Field(default=None, ge=0)
    labor_cost: StrictInt | None = Field(default=None, ge=0)
    paint_cost: StrictInt | None = Field(default=None, ge=0)
    repair_cost: StrictInt | None = Field(default=None, ge=0)
    insurance_paid: StrictInt | None = Field(default=None, ge=0)


class GlovisCarDetail(ExtensibleModel):
    main: GlovisMain
    properties: dict[str, Any] = Field(default_factory=dict)
    performance: dict[str, Any] = Field(default_factory=dict)
    total_table: dict[str, Any] = Field(default_factory=dict)
    summary_table: dict[str, Any] = Field(default_factory=dict)
    options: list[GlovisEquipmentOption] = Field(default_factory=list)
    legal_status: GlovisLegalStatus | None = None
    insurance_history: GlovisInsuranceHistory | None = None
    accident_records: list[GlovisAccidentRecord] = Field(default_factory=list)
    inspection_record: dict[str, Any] = Field(default_factory=dict)
    images: list[str] = Field(default_factory=list)
    inspection_images: list[str] = Field(default_factory=list)
    performance_image: str | None = None
    registration_certificate_image: str | None = None
    remarks: str | None = None


class GlovisCarDetailResponse(BaseModel):
    success: Literal[True] = True
    data: GlovisCarDetail
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GlovisHealthResponse(BaseModel):
    status: Literal["healthy"] = "healthy"
    provider: Literal["dbauto"] = "dbauto"
    auction_count: StrictInt = Field(ge=0)
    list_count: StrictInt = Field(ge=0)
    egress: str
    checked_at: datetime


class GlovisDetailHealthResponse(GlovisHealthResponse):
    detail_checked: Literal[True] = True
