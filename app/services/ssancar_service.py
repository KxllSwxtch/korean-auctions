import json
import hashlib
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional, Dict, Any, Tuple

from bs4 import BeautifulSoup
from loguru import logger
import pytz

from app.models.ssancar import (
    SSANCARCar, SSANCARCarDetail, SSANCARFilters,
    SSANCARResponse,
    SSANCARManufacturer, SSANCARModel,
)
from app.parsers.ssancar_parser import (
    SSANCARParser,
    PARSE_STATUS_VALID,
    PARSE_STATUS_SESSION_EXPIRED,
    PARSE_STATUS_NOT_FOUND,
)
from app.parsers.ssancar_auth import is_ssancar_login_html
from app.core.config import get_settings
from app.services.ssancar_transport import (
    OVERALL_DEADLINE_SECONDS,
    PayloadValidation,
    SSANCARTransport,
    SSANCARUpstreamAuthError,
    SSANCARUpstreamInvalidResponseError,
)


SEOUL_TIMEZONE = pytz.timezone("Asia/Seoul")


def resolve_ssancar_week(
    supplied: Optional[Any] = None,
    *,
    now: Optional[datetime] = None,
) -> str:
    """Return the selected Tuesday (2) or Friday (5) auction window.

    Valid supplied values are authoritative. Missing and legacy/invalid values
    use the exact Seoul-time transition schedule used by SSANCAR.
    """

    supplied_text = str(supplied) if supplied is not None else ""
    if supplied_text in {"2", "5"}:
        return supplied_text

    current = now or datetime.now(SEOUL_TIMEZONE)
    if current.tzinfo is None:
        current = SEOUL_TIMEZONE.localize(current)
    else:
        current = current.astimezone(SEOUL_TIMEZONE)

    weekday = current.weekday()
    switch_reached = (current.hour, current.minute, current.second) >= (18, 0, 0)
    if weekday == 0:
        return "2" if switch_reached else "5"
    if weekday in {1, 2}:
        return "2"
    if weekday == 3:
        return "5" if switch_reached else "2"
    return "5"


@dataclass(frozen=True)
class SSANCARHealthProbe:
    week_number: str
    upstream_count: int
    egress: str
    checked_at: datetime


@dataclass(frozen=True)
class SSANCARDetailHealthProbe:
    week_number: str
    upstream_count: int
    detail_checked: bool
    sample_car_no: Optional[str]
    egress: str
    checked_at: datetime


def validate_ssancar_car_no(car_no: Any) -> str:
    """Return a safe SSANCAR identifier or reject it before any I/O."""

    value = str(car_no) if car_no is not None else ""
    if not re.fullmatch(r"[0-9]{1,20}", value):
        raise ValueError("car_no must contain 1 to 20 ASCII digits")
    return value


class SSANCARService:
    """Service for interacting with SSANCAR auction website"""
    
    BASE_URL = "https://www.ssancar.com"
    AJAX_CAR_LIST_URL = f"{BASE_URL}/ajax/ajax_car_list.php"
    AJAX_CAR_NUM_URL = f"{BASE_URL}/ajax/ajax_car_num.php"
    CAR_VIEW_URL = f"{BASE_URL}/page/car_view.php"
    LIST_PAGE_URL = f"{BASE_URL}/bbs/board.php?bo_table=list"
    
    COMMON_HEADERS = {
        "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
        "Connection": "keep-alive",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    }
    AJAX_HEADERS = {
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://www.ssancar.com",
        "Referer": "https://www.ssancar.com/bbs/board.php?bo_table=list",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "X-Requested-With": "XMLHttpRequest",
    }
    DETAIL_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.ssancar.com/bbs/board.php?bo_table=list",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Upgrade-Insecure-Requests": "1",
    }
    
    # Load car manufacturer and model mapping from JSON
    CAR_LIST_MAP = {}
    MANUFACTURER_MAPPING = {}
    
    @classmethod
    def _load_carlist_data(cls):
        """Load car list data from JSON file"""
        if cls.CAR_LIST_MAP:  # Already loaded
            return
            
        try:
            import os
            json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'ssancar_carlist.json')
            
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                cls.CAR_LIST_MAP = data.get('models', {})
                cls.MANUFACTURER_MAPPING = {
                    'korean_to_english': data.get('korean_to_english_manufacturers', {}),
                    'english_to_korean': data.get('english_to_korean_manufacturers', {})
                }
                logger.info(f"✅ Loaded {len(cls.CAR_LIST_MAP)} manufacturers with models from ssancar_carlist.json")
        except FileNotFoundError:
            logger.warning("⚠️ ssancar_carlist.json not found, using default data")
            # Fallback to minimal data
            cls.CAR_LIST_MAP = {
                "현대": [
                    {"no": "472", "name": "아반떼", "e_name": "AVANTE"},
                    {"no": "460", "name": "그랜저", "e_name": "GRANDEUR"},
                    {"no": "559", "name": "쏘나타", "e_name": "SONATA"},
                ],
                "기아": [
                    {"no": "565", "name": "카니발", "e_name": "CARNIVAL"},
                    {"no": "568", "name": "K5", "e_name": "K5"},
                    {"no": "571", "name": "스포티지", "e_name": "SPORTAGE"},
                ],
            }
        except Exception as e:
            logger.error(f"❌ Error loading ssancar_carlist.json: {e}")
            cls.CAR_LIST_MAP = {}
    
    def __init__(
        self,
        *,
        transport: Optional[SSANCARTransport] = None,
        now_provider: Optional[Callable[[], datetime]] = None,
        cache_clock: Optional[Callable[[], float]] = None,
        deadline_clock: Optional[Callable[[], float]] = None,
    ):
        # Load car list data first
        self._load_carlist_data()

        self.parser = SSANCARParser()
        self.transport = transport or SSANCARTransport(
            headers=self.COMMON_HEADERS,
        )
        self._now_provider = now_provider
        self._cache_clock = cache_clock or time.time
        self._deadline_clock = deadline_clock or time.monotonic

        # In-memory cache with tiered TTL
        self._cache: Dict[str, tuple] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def _get_from_cache(self, key: str, ttl: int = 300) -> Optional[Any]:
        """Get data from in-memory cache with per-key TTL."""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if self._cache_clock() - timestamp < ttl:
                self._cache_hits += 1
                return data
            del self._cache[key]
        self._cache_misses += 1
        return None

    def _save_to_cache(self, key: str, data: Any) -> None:
        """Save data to in-memory cache."""
        self._cache[key] = (data, self._cache_clock())

    def _make_cache_key(self, prefix: str, params: Optional[Dict] = None) -> str:
        """Create a cache key from prefix and optional params dict."""
        if params:
            param_str = json.dumps(params, sort_keys=True, default=str)
            param_hash = hashlib.md5(param_str.encode()).hexdigest()[:12]
            return f"ssancar:{prefix}:{param_hash}"
        return f"ssancar:{prefix}"

    def _get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0
        return {
            "service": "SSANCAR",
            "cache_entries": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate_percent": round(hit_rate, 2),
        }
    
    def _current_time(self) -> datetime:
        current = (
            self._now_provider()
            if self._now_provider is not None
            else datetime.now(SEOUL_TIMEZONE)
        )
        if current.tzinfo is None:
            return SEOUL_TIMEZONE.localize(current)
        return current.astimezone(SEOUL_TIMEZONE)

    def _resolve_week(self, supplied: Optional[Any]) -> str:
        return resolve_ssancar_week(supplied, now=self._current_time())

    def _get_week_number(self) -> str:
        """Backward-compatible accessor for the current auction window."""

        return self._resolve_week(None)
    
    def fetch_cars(self, filters: SSANCARFilters) -> SSANCARResponse:
        """Fetch and cache only a semantically validated SSANCAR list."""

        normalized = filters.model_copy(
            update={"weekNo": self._resolve_week(filters.weekNo)}
        )
        cache_params = normalized.model_dump()
        cache_key = self._make_cache_key("cars", cache_params)
        cached = self._get_from_cache(
            cache_key,
            ttl=get_settings().cache_ttl_car_list,
        )
        if cached is not None:
            logger.debug("📦 SSANCAR cars cache hit")
            return cached

        data = self._build_post_data(normalized)
        transport_result = self.transport.request(
            "POST",
            self.AJAX_CAR_LIST_URL,
            self._validate_car_list_response,
            operation="list",
            data=data,
            headers=self.AJAX_HEADERS,
        )
        cars = transport_result.value
        current_page = int(normalized.pages) + 1
        page_size = int(normalized.list)
        result = SSANCARResponse(
            success=True,
            message="Cars fetched successfully",
            cars=cars,
            total_count=len(cars),
            current_page=current_page,
            page_size=page_size,
            has_next_page=len(cars) == page_size,
            has_prev_page=current_page > 1,
            week_number=normalized.weekNo,
        )
        self._save_to_cache(cache_key, result)
        return result

    @staticmethod
    def _build_post_data(filters: SSANCARFilters) -> Dict[str, str]:
        return {
            "weekNo": filters.weekNo,
            "maker": filters.maker or "",
            "model": filters.model or "",
            "fuel": filters.fuel or "",
            "color": filters.color or "",
            "gearbox": filters.gearbox or "",
            "kmFrom": filters.kmFrom,
            "kmTo": filters.kmTo,
            "yearFrom": filters.yearFrom,
            "yearTo": filters.yearTo,
            "priceFrom": filters.priceFrom,
            "priceTo": filters.priceTo,
            "list": filters.list,
            "pages": filters.pages,
            "no": filters.no or "",
        }

    def _validate_car_list_response(self, response) -> PayloadValidation[List[SSANCARCar]]:
        html = response.text or ""
        if is_ssancar_login_html(html):
            raise SSANCARUpstreamAuthError(selector_count=0)
        if not html.strip():
            return PayloadValidation(value=[], selector_count=0)

        soup = BeautifulSoup(html, "html.parser")
        selector_count = len(soup.select('li a[href*="car_view.php"]'))
        if selector_count == 0:
            raise SSANCARUpstreamInvalidResponseError(selector_count=0)

        cars = self.parser.parse_car_list(html)
        validated_cars: List[SSANCARCar] = []
        for car in cars:
            if car.source.upper() != "SSANCAR" or not (
                car.full_name or ""
            ).strip():
                continue
            try:
                car.car_no = validate_ssancar_car_no(car.car_no)
            except ValueError:
                continue
            validated_cars.append(car)
        cars = validated_cars
        if not cars:
            raise SSANCARUpstreamInvalidResponseError(
                selector_count=selector_count
            )
        return PayloadValidation(value=cars, selector_count=selector_count)
    
    def search_cars(self, filters: SSANCARFilters) -> SSANCARResponse:
        """Search cars with filters - same as fetch_cars for SSANCAR"""
        return self.fetch_cars(filters)
    
    def get_manufacturers(self) -> Tuple[List[SSANCARManufacturer], bool]:
        """Get list of manufacturers"""
        try:
            manufacturers = []
            
            # Use manufacturer mapping from loaded JSON
            korean_to_english = self.MANUFACTURER_MAPPING.get('korean_to_english', {})
            
            # Convert our CAR_LIST_MAP to manufacturer list
            for korean_name, models in self.CAR_LIST_MAP.items():
                # Get English name from mapping
                english_name = korean_to_english.get(korean_name, korean_name)
                
                manufacturer = SSANCARManufacturer(
                    code=korean_name,
                    name=english_name,
                    korean_name=korean_name,
                    count=len(models) if isinstance(models, list) else 0
                )
                manufacturers.append(manufacturer)
            
            # Sort by Korean name for consistency
            manufacturers.sort(key=lambda x: x.korean_name)
            
            logger.info(f"✅ Retrieved {len(manufacturers)} manufacturers with models")
            return manufacturers, True
            
        except Exception as e:
            logger.error(f"❌ Error getting manufacturers: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return [], False
    
    def get_models(self, manufacturer_code: str) -> Tuple[List[SSANCARModel], bool]:
        """Get models for a specific manufacturer"""
        try:
            models = []
            
            # Get models from our CAR_LIST_MAP
            model_list = self.CAR_LIST_MAP.get(manufacturer_code, [])
            
            for model_data in model_list:
                model = SSANCARModel(
                    no=model_data['no'],
                    name=model_data['name'],
                    e_name=model_data['e_name'],
                    manufacturer_code=manufacturer_code
                )
                models.append(model)
            
            # Log info about models found
            if models:
                logger.info(f"✅ Found {len(models)} models for {manufacturer_code}")
            else:
                logger.info(f"ℹ️ No models configured for {manufacturer_code} yet")
            
            logger.info(f"✅ Retrieved {len(models)} models for {manufacturer_code}")
            return models, True
            
        except Exception as e:
            logger.error(f"❌ Error getting models: {e}")
            return [], False
    
    def get_car_detail(
        self, car_no: str
    ) -> Tuple[Optional[SSANCARCarDetail], str]:
        """Get a validated detail through the same isolated egress chain."""

        car_no = validate_ssancar_car_no(car_no)
        cache_key = self._make_cache_key("detail", {"car_no": car_no})
        cached = self._get_from_cache(
            cache_key, ttl=get_settings().cache_ttl_car_detail
        )
        if cached is not None:
            logger.debug(f"📦 SSANCAR car detail cache hit: {car_no}")
            return cached, PARSE_STATUS_VALID

        logger.info("📄 Fetching SSANCAR car detail car_no={}", car_no)

        transport_result = self._request_car_detail(car_no, operation="detail")
        car_detail, status = transport_result.value
        if status == PARSE_STATUS_VALID and car_detail is not None:
            self._save_to_cache(cache_key, car_detail)
        return car_detail, status

    def _validate_detail_response(
        self,
        response,
        requested_car_no: str,
    ) -> PayloadValidation[Tuple[Optional[SSANCARCarDetail], str]]:
        if is_ssancar_login_html(response.text):
            raise SSANCARUpstreamAuthError(selector_count=0)

        car_detail, status = self.parser.parse_car_detail(response.text)
        if status == PARSE_STATUS_SESSION_EXPIRED:
            raise SSANCARUpstreamAuthError(selector_count=0)
        if status == PARSE_STATUS_NOT_FOUND:
            return PayloadValidation(value=(None, status), selector_count=0)
        if status != PARSE_STATUS_VALID or car_detail is None:
            raise SSANCARUpstreamInvalidResponseError(selector_count=0)

        if car_detail.car_no and car_detail.car_no != requested_car_no:
            raise SSANCARUpstreamInvalidResponseError(selector_count=1)
        if not car_detail.car_no:
            car_detail.car_no = requested_car_no
        if not car_detail.full_name and car_detail.manufacturer and car_detail.model:
            car_detail.full_name = f"[{car_detail.manufacturer}] {car_detail.model}"
        if car_detail.starting_price and not car_detail.bid_price:
            price_match = re.search(r'(\d+(?:,\d+)*)', car_detail.starting_price)
            if price_match:
                try:
                    car_detail.bid_price = int(price_match.group(1).replace(',', ''))
                except ValueError:
                    car_detail.bid_price = 0

        if not car_detail.main_image and car_detail.images:
            car_detail.main_image = car_detail.images[0]
        if not car_detail.engine_volume and car_detail.engine_size:
            car_detail.engine_volume = car_detail.engine_size
        if not car_detail.fuel_type and car_detail.fuel:
            car_detail.fuel_type = car_detail.fuel
        return PayloadValidation(
            value=(car_detail, PARSE_STATUS_VALID),
            selector_count=1,
        )

    def _request_car_detail(
        self,
        car_no: str,
        *,
        operation: str,
        require_valid: bool = False,
        deadline_at: Optional[float] = None,
    ):
        car_no = validate_ssancar_car_no(car_no)

        def validate_detail(response):
            validation = self._validate_detail_response(response, car_no)
            if require_valid:
                car_detail, status = validation.value
                if status != PARSE_STATUS_VALID or car_detail is None:
                    raise SSANCARUpstreamInvalidResponseError(
                        selector_count=validation.selector_count,
                    )
            return validation

        return self.transport.request(
            "GET",
            self.CAR_VIEW_URL,
            validate_detail,
            operation=operation,
            deadline_at=deadline_at,
            params={"car_no": car_no},
            headers=self.DETAIL_HEADERS,
        )
    
    def get_filter_options(self) -> Dict[str, Any]:
        """Get all available filter options for SSANCAR"""
        try:
            # Check cache (1h TTL for filter metadata)
            cache_key = self._make_cache_key("filter_options")
            cached = self._get_from_cache(cache_key, ttl=get_settings().cache_ttl_filters)
            if cached is not None:
                logger.debug("📦 SSANCAR filter options cache hit")
                return cached

            from app.models.ssancar import SSANCARFilterOption, SSANCARFilterOptionsResponse

            logger.info("🔧 Getting SSANCAR filter options")
            
            # Get manufacturers (already implemented)
            manufacturers, _ = self.get_manufacturers()
            
            # Define static filter options based on SSANCAR's actual filters
            # Updated to use code/name structure for frontend compatibility
            fuel_types = [
                {"code": "Gasoline", "name": "Gasoline"},
                {"code": "Diesel", "name": "Diesel"},
                {"code": "LPG", "name": "LPG"},
                {"code": "Hybrid", "name": "Hybrid"},
                {"code": "Electric", "name": "Electric"},
                {"code": "Hydrogen", "name": "Hydrogen"},
            ]
            
            transmissions = [
                {"code": "Automatic", "name": "Automatic"},
                {"code": "Manual", "name": "Manual"},
                {"code": "CVT", "name": "CVT"},
                {"code": "DCT", "name": "DCT"},
            ]
            
            grades = [
                SSANCARFilterOption(value="A1", label="A1", count=None),
                SSANCARFilterOption(value="A2", label="A2", count=None),
                SSANCARFilterOption(value="A3", label="A3", count=None),
                SSANCARFilterOption(value="A4", label="A4", count=None),
                SSANCARFilterOption(value="B1", label="B1", count=None),
                SSANCARFilterOption(value="B2", label="B2", count=None),
                SSANCARFilterOption(value="B3", label="B3", count=None),
                SSANCARFilterOption(value="B4", label="B4", count=None),
                SSANCARFilterOption(value="C1", label="C1", count=None),
                SSANCARFilterOption(value="C2", label="C2", count=None),
                SSANCARFilterOption(value="C3", label="C3", count=None),
                SSANCARFilterOption(value="C4", label="C4", count=None),
                SSANCARFilterOption(value="D1", label="D1", count=None),
                SSANCARFilterOption(value="D2", label="D2", count=None),
            ]
            
            colors = [
                {"code": "Black", "name": "Black"},
                {"code": "White", "name": "White"},
                {"code": "Silver", "name": "Silver"},
                {"code": "Gray", "name": "Gray"},
                {"code": "Red", "name": "Red"},
                {"code": "Blue", "name": "Blue"},
                {"code": "Green", "name": "Green"},
                {"code": "Brown", "name": "Brown"},
                {"code": "Beige", "name": "Beige"},
                {"code": "Orange", "name": "Orange"},
                {"code": "Yellow", "name": "Yellow"},
                {"code": "Other", "name": "Other"},
            ]
            
            # Auction weeks
            weeks = [
                {"value": "2", "label": "Tuesday Auction", "day": "Tuesday"},
                {"value": "5", "label": "Friday Auction", "day": "Friday"},
            ]
            
            # Dynamic ranges - these could be updated based on actual data
            year_range = {"min": 2000, "max": 2025}
            price_range = {"min": 0, "max": 200000}
            mileage_range = {"min": 0, "max": 500000}
            
            response = SSANCARFilterOptionsResponse(
                success=True,
                message="Filter options retrieved successfully",
                manufacturers=manufacturers,
                fuel_types=fuel_types,
                transmissions=transmissions,
                grades=grades,
                colors=colors,
                weeks=weeks,
                year_range=year_range,
                price_range=price_range,
                mileage_range=mileage_range
            )
            
            logger.info("✅ SSANCAR filter options retrieved")
            result = response.model_dump()
            self._save_to_cache(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"❌ Error getting filter options: {e}")
            from app.models.ssancar import SSANCARFilterOptionsResponse
            
            error_response = SSANCARFilterOptionsResponse(
                success=False,
                message=f"Failed to get filter options: {str(e)}",
                manufacturers=[],
                fuel_types=[],
                transmissions=[],
                grades=[],
                colors=[],
                weeks=[],
                year_range={"min": 2000, "max": 2025},
                price_range={"min": 0, "max": 200000},
                mileage_range={"min": 0, "max": 500000}
            )
            return error_response.model_dump()
    
    def fetch_total_count(self, filters: Optional[SSANCARFilters] = None) -> int:
        """Fetch and cache a strictly validated numeric count."""

        normalized = self._normalized_count_filters(filters)
        cache_key = self._make_cache_key(
            "total_count",
            normalized.model_dump(),
        )
        cached = self._get_from_cache(cache_key, ttl=get_settings().cache_ttl)
        if cached is not None:
            logger.debug("📦 SSANCAR total count cache hit")
            return cached

        count, _ = self._request_total_count(normalized)
        self._save_to_cache(cache_key, count)
        return count

    def _normalized_count_filters(
        self,
        filters: Optional[SSANCARFilters],
    ) -> SSANCARFilters:
        source = filters or SSANCARFilters()
        return source.model_copy(
            update={"weekNo": self._resolve_week(source.weekNo)}
        )

    @staticmethod
    def _build_count_data(filters: SSANCARFilters) -> Dict[str, str]:
        data = SSANCARService._build_post_data(filters)
        data.update(
            {
                "list": "15",
                "pages": "1",
                "sorts": "Low.Price",
            }
        )
        return data

    @staticmethod
    def _validate_count_response(response) -> PayloadValidation[int]:
        count_text = (response.text or "").strip()
        if is_ssancar_login_html(count_text):
            raise SSANCARUpstreamAuthError(selector_count=0)
        if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)", count_text):
            raise SSANCARUpstreamInvalidResponseError(selector_count=0)
        return PayloadValidation(
            value=int(count_text.replace(",", "")),
            selector_count=1,
        )

    def _request_total_count(
        self,
        filters: SSANCARFilters,
        *,
        operation: str = "count",
        deadline_at: Optional[float] = None,
    ) -> Tuple[int, str]:
        result = self.transport.request(
            "POST",
            self.AJAX_CAR_NUM_URL,
            self._validate_count_response,
            operation=operation,
            deadline_at=deadline_at,
            data=self._build_count_data(filters),
            headers=self.AJAX_HEADERS,
        )
        return result.value, result.egress

    def check_health(
        self,
        week_number: Optional[Any] = None,
    ) -> SSANCARHealthProbe:
        """Run a separate 30-second-cached, validated readiness probe."""

        resolved_week = self._resolve_week(week_number)
        cache_key = self._make_cache_key(
            "health_probe",
            {"week_number": resolved_week},
        )
        cached = self._get_from_cache(cache_key, ttl=30)
        if cached is not None:
            return cached

        filters = SSANCARFilters(weekNo=resolved_week)
        count, egress = self._request_total_count(filters)
        probe = SSANCARHealthProbe(
            week_number=resolved_week,
            upstream_count=count,
            egress=egress,
            checked_at=self._current_time(),
        )
        self._save_to_cache(cache_key, probe)
        return probe

    def check_detail_health(
        self,
        week_number: Optional[Any] = None,
    ) -> SSANCARDetailHealthProbe:
        """Validate the current detail capability without using detail cache."""

        resolved_week = self._resolve_week(week_number)
        cache_key = self._make_cache_key(
            "detail_health_probe",
            {"week_number": resolved_week},
        )
        cached = self._get_from_cache(cache_key, ttl=300)
        if cached is not None:
            return cached

        deadline_at = self._deadline_clock() + OVERALL_DEADLINE_SECONDS
        filters = SSANCARFilters(weekNo=resolved_week, list="1", pages="0")
        count, count_egress = self._request_total_count(
            filters,
            operation="detail_health_count",
            deadline_at=deadline_at,
        )
        if count == 0:
            probe = SSANCARDetailHealthProbe(
                week_number=resolved_week,
                upstream_count=0,
                detail_checked=False,
                sample_car_no=None,
                egress=count_egress,
                checked_at=self._current_time(),
            )
            self._save_to_cache(cache_key, probe)
            return probe

        def validate_health_list(response):
            validation = self._validate_car_list_response(response)
            if not validation.value:
                raise SSANCARUpstreamInvalidResponseError(
                    selector_count=validation.selector_count,
                )
            try:
                sample_car_no = validate_ssancar_car_no(
                    validation.value[0].car_no
                )
            except (AttributeError, IndexError, TypeError, ValueError) as error:
                raise SSANCARUpstreamInvalidResponseError(
                    selector_count=validation.selector_count,
                ) from error
            return PayloadValidation(
                value=sample_car_no,
                selector_count=validation.selector_count,
            )

        list_result = self.transport.request(
            "POST",
            self.AJAX_CAR_LIST_URL,
            validate_health_list,
            operation="detail_health_list",
            deadline_at=deadline_at,
            data=self._build_post_data(filters),
            headers=self.AJAX_HEADERS,
        )

        sample_car_no = list_result.value
        detail_result = self._request_car_detail(
            sample_car_no,
            operation="detail_health_detail",
            require_valid=True,
            deadline_at=deadline_at,
        )

        probe = SSANCARDetailHealthProbe(
            week_number=resolved_week,
            upstream_count=count,
            detail_checked=True,
            sample_car_no=sample_car_no,
            egress=detail_result.egress,
            checked_at=self._current_time(),
        )
        self._save_to_cache(cache_key, probe)
        return probe
