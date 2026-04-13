import json
import hashlib
import re
import time
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from loguru import logger

from app.models.ssancar import (
    SSANCARCar, SSANCARCarDetail, SSANCARFilters,
    SSANCARResponse, SSANCARDetailResponse,
    SSANCARManufacturer, SSANCARModel,
    SSANCARManufacturersResponse, SSANCARModelsResponse
)
from app.parsers.ssancar_parser import SSANCARParser
from app.core.session_manager import SessionManager
from app.core.proxy_config import get_proxy_pool


class SSANCARService:
    """Service for interacting with SSANCAR auction website"""
    
    BASE_URL = "https://www.ssancar.com"
    AJAX_CAR_LIST_URL = f"{BASE_URL}/ajax/ajax_car_list.php"
    AJAX_CAR_NUM_URL = f"{BASE_URL}/ajax/ajax_car_num.php"
    CAR_VIEW_URL = f"{BASE_URL}/page/car_view.php"
    LIST_PAGE_URL = f"{BASE_URL}/bbs/board.php?bo_table=list"
    
    # Default cookies from the provided example
    DEFAULT_COOKIES = {
        "_gcl_au": "1.1.78877594.1751338453",
        "e1192aefb64683cc97abb83c71057733": "bGlzdA%3D%3D",
        "PHPSESSID": "3tkj2orbe4h537fjor8b3623cb",
        "2a0d2363701f23f8a75028924a3af643": "MTc2LjY0LjIzLjg%3D",
    }
    
    # Default headers from the provided example
    DEFAULT_HEADERS = {
        "Accept": "*/*",
        "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://www.ssancar.com",
        "Referer": "https://www.ssancar.com/bbs/board.php?bo_table=list",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
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
    
    def __init__(self):
        # Load car list data first
        self._load_carlist_data()

        self.session_manager = SessionManager()
        self.parser = SSANCARParser()
        # Per-instance pool: pre-seeded by ProxyPool.__post_init__.
        self._proxy_pool = get_proxy_pool()
        logger.info(
            f"🔐 SSANCAR proxy pool: {self._proxy_pool.names}, "
            f"starting on '{self._proxy_pool.current()[0].name}'"
        )
        self.session = self._create_session()
        self._load_or_set_cookies()

        # In-memory cache with tiered TTL
        self._cache: Dict[str, tuple] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def _get_from_cache(self, key: str, ttl: int = 300) -> Optional[Any]:
        """Get data from in-memory cache with per-key TTL."""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if time.time() - timestamp < ttl:
                self._cache_hits += 1
                return data
            del self._cache[key]
        self._cache_misses += 1
        return None

    def _save_to_cache(self, key: str, data: Any) -> None:
        """Save data to in-memory cache."""
        self._cache[key] = (data, time.time())

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
    
    def _create_session(self) -> requests.Session:
        """Create a requests session with retry logic and pooled proxy."""
        session = requests.Session()

        # Pull current proxy from the per-instance pool. _rotate_proxy() will
        # advance and recreate the session when a provider stops working.
        entry, _ = self._proxy_pool.current()
        session.proxies = self._proxy_pool.current_dict()
        logger.info(f"🔐 SSANCAR session using proxy '{entry.name}'")

        # Setup retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers
        session.headers.update(self.DEFAULT_HEADERS)

        return session

    def _rotate_proxy(self) -> None:
        """Advance to the next pool entry and rebuild the session.

        Call this when the current proxy starts returning failures the retry
        adapter cannot handle (e.g. exhausted quota, persistent 407/403).
        """
        entry, _ = self._proxy_pool.advance()
        logger.info(f"🔁 SSANCAR rotating proxy to '{entry.name}'")
        # Preserve cookies across rotation — server-side session is tied to PHPSESSID.
        old_cookies = dict(self.session.cookies)
        self.session = self._create_session()
        self.session.cookies.update(old_cookies)
    
    def _load_or_set_cookies(self):
        """Load saved cookies or use default ones"""
        saved_cookies = self.session_manager.load_session('ssancar')
        
        if saved_cookies:
            self.session.cookies.update(saved_cookies)
            logger.info("✅ Loaded saved SSANCAR cookies")
        else:
            self.session.cookies.update(self.DEFAULT_COOKIES)
            logger.info("📝 Using default SSANCAR cookies")
            self._save_cookies()
    
    def _save_cookies(self):
        """Save current session cookies"""
        cookies_dict = dict(self.session.cookies)
        self.session_manager.save_session('ssancar', cookies_dict)
        logger.info("💾 Saved SSANCAR cookies")
    
    def _get_week_number(self) -> str:
        """Get the appropriate week number based on Seoul time
        
        Auction schedule:
        - Tuesday auction (weekNo=2): Switches at 6PM Monday Seoul time
        - Friday auction (weekNo=5): Switches at 6PM Thursday Seoul time
        """
        import pytz
        
        # Get current time in Seoul timezone (KST = UTC+9)
        seoul_tz = pytz.timezone('Asia/Seoul')
        seoul_time = datetime.now(seoul_tz)
        
        weekday = seoul_time.weekday()  # 0=Monday, 6=Sunday
        hour = seoul_time.hour
        
        logger.info(f"📅 Seoul time: {seoul_time.strftime('%Y-%m-%d %H:%M:%S %Z')}, weekday: {weekday}, hour: {hour}")
        
        # Monday: switch at 6PM
        if weekday == 0:  # Monday
            if hour < 18:
                logger.info("🎯 Monday before 6PM Seoul → Friday auction (weekNo=5)")
                return "5"  # Still showing previous Friday auction
            else:
                logger.info("🎯 Monday after 6PM Seoul → Tuesday auction (weekNo=2)")
                return "2"  # Switch to Tuesday auction
        
        # Tuesday to Wednesday: Tuesday auction
        elif weekday in [1, 2]:  # Tuesday, Wednesday
            logger.info("🎯 Tuesday/Wednesday → Tuesday auction (weekNo=2)")
            return "2"
        
        # Thursday: switch at 6PM
        elif weekday == 3:  # Thursday
            if hour < 18:
                logger.info("🎯 Thursday before 6PM Seoul → Tuesday auction (weekNo=2)")
                return "2"  # Still showing Tuesday auction
            else:
                logger.info("🎯 Thursday after 6PM Seoul → Friday auction (weekNo=5)")
                return "5"  # Switch to Friday auction
        
        # Friday to Sunday: Friday auction
        else:  # Friday, Saturday, Sunday
            logger.info("🎯 Friday/Weekend → Friday auction (weekNo=5)")
            return "5"
    
    def fetch_cars(self, filters: SSANCARFilters) -> SSANCARResponse:
        """Fetch cars from SSANCAR with filters"""
        try:
            # Auto-set weekNo if not provided
            if not filters.weekNo or filters.weekNo == "4":
                filters.weekNo = self._get_week_number()
                logger.info(f"📅 Auto-set weekNo to {filters.weekNo} based on current day")

            # Check cache (3min TTL for car listings)
            cache_params = filters.model_dump() if hasattr(filters, 'model_dump') else vars(filters)
            cache_key = self._make_cache_key("cars", cache_params)
            cached = self._get_from_cache(cache_key, ttl=180)
            if cached is not None:
                logger.debug(f"📦 SSANCAR cars cache hit")
                return cached
            
            # Prepare POST data
            data = {
                "weekNo": filters.weekNo,
                "maker": filters.maker or "",
                "model": filters.model or "",
                "fuel": filters.fuel or "",
                "color": filters.color or "",
                "yearFrom": filters.yearFrom,
                "yearTo": filters.yearTo,
                "priceFrom": filters.priceFrom,
                "priceTo": filters.priceTo,
                "list": filters.list,
                "pages": filters.pages,
                "no": filters.no or "",
            }
            
            logger.info(f"🚗 Fetching SSANCAR cars with filters: {data}")
            
            # Make request
            response = self.session.post(
                self.AJAX_CAR_LIST_URL,
                data=data,
                timeout=15
            )
            
            response.raise_for_status()

            # Parse HTML response
            cars = self.parser.parse_car_list(response.text)

            # CRITICAL: Always filter to ensure ONLY SSANCAR cars are returned
            # The SSANCAR website may aggregate cars from multiple sources
            original_count = len(cars)
            cars = [car for car in cars if car.source.upper() == "SSANCAR"]
            filtered_count = len(cars)

            if original_count != filtered_count:
                logger.warning(
                    f"⚠️ Filtered out {original_count - filtered_count} non-SSANCAR cars! "
                    f"Returning {filtered_count} SSANCAR-only cars"
                )
            else:
                logger.info(f"✅ All {filtered_count} cars are from SSANCAR source")

            # Get total count (would need separate request)
            total_count = len(cars)  # Simplified for now
            current_page = int(filters.pages) + 1  # Convert 0-based to 1-based
            page_size = int(filters.list)
            
            result = SSANCARResponse(
                success=True,
                message="Cars fetched successfully",
                cars=cars,
                total_count=total_count,
                current_page=current_page,
                page_size=page_size,
                has_next_page=len(cars) == page_size,
                has_prev_page=current_page > 1
            )
            self._save_to_cache(cache_key, result)
            return result
            
        except requests.RequestException as e:
            logger.error(f"❌ Request error fetching SSANCAR cars: {e}")
            return SSANCARResponse(
                success=False,
                message=f"Failed to fetch cars: {str(e)}",
                cars=[],
                total_count=0,
                current_page=1,
                page_size=15
            )
        except Exception as e:
            logger.error(f"❌ Unexpected error fetching SSANCAR cars: {e}")
            return SSANCARResponse(
                success=False,
                message=f"Unexpected error: {str(e)}",
                cars=[],
                total_count=0,
                current_page=1,
                page_size=15
            )
    
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
    
    def get_car_detail(self, car_no: str) -> Optional[SSANCARCarDetail]:
        """Get detailed information about a specific car"""
        try:
            # Check cache (30min TTL for car details)
            cache_key = self._make_cache_key("detail", {"car_no": car_no})
            cached = self._get_from_cache(cache_key, ttl=1800)
            if cached is not None:
                logger.debug(f"📦 SSANCAR car detail cache hit: {car_no}")
                return cached

            url = f"{self.CAR_VIEW_URL}?car_no={car_no}"
            logger.info(f"📄 Fetching car detail from: {url}")
            
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            # Parse the detail page
            car_detail = self.parser.parse_car_detail(response.text)
            
            if not car_detail:
                logger.error(f"❌ Failed to parse car detail for car_no: {car_no}")
                return None
            
            # Ensure car_no is set
            if not car_detail.car_no:
                car_detail.car_no = car_no
            
            # Additional processing for SSANCAR specific fields
            # Ensure we have all required fields for the frontend
            if not car_detail.full_name and car_detail.manufacturer and car_detail.model:
                car_detail.full_name = f"[{car_detail.manufacturer}] {car_detail.model}"
            
            # Parse bid price from starting_price if needed
            if car_detail.starting_price and not car_detail.bid_price:
                price_match = re.search(r'(\d+(?:,\d+)*)', car_detail.starting_price)
                if price_match:
                    try:
                        car_detail.bid_price = int(price_match.group(1).replace(',', ''))
                    except ValueError:
                        car_detail.bid_price = 0
            
            # Ensure we have the main_image set
            if not car_detail.main_image and car_detail.images:
                car_detail.main_image = car_detail.images[0]
            
            # Set engine_volume if we have engine_size
            if not hasattr(car_detail, 'engine_volume') and car_detail.engine_size:
                car_detail.engine_volume = car_detail.engine_size
            
            # Set fuel_type if we have fuel
            if not hasattr(car_detail, 'fuel_type') and car_detail.fuel:
                car_detail.fuel_type = car_detail.fuel
            
            logger.info(f"✅ Successfully retrieved car detail for: {car_no}")
            self._save_to_cache(cache_key, car_detail)
            return car_detail
            
        except requests.RequestException as e:
            logger.error(f"❌ Request error fetching car detail: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error fetching car detail: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def update_cookies(self, new_cookies: Dict[str, str]):
        """Update service cookies"""
        self.session.cookies.update(new_cookies)
        self._save_cookies()
        logger.info("✅ Updated SSANCAR cookies")
    
    def get_filter_options(self) -> Dict[str, Any]:
        """Get all available filter options for SSANCAR"""
        try:
            # Check cache (1h TTL for filter metadata)
            cache_key = self._make_cache_key("filter_options")
            cached = self._get_from_cache(cache_key, ttl=3600)
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
        """Fetch total car count from SSANCAR using the same pattern as fetch_cars

        Args:
            filters: Optional filters to apply for count

        Returns:
            Total count of cars matching the filters
        """
        try:
            # Determine week number - same logic as fetch_cars
            if filters and filters.weekNo:
                week_no = filters.weekNo
            else:
                week_no = self._get_week_number()
                logger.info(f"📅 Auto-set weekNo to {week_no} for total count")

            # Check cache (5min TTL for total count)
            cache_params = {"week_no": week_no}
            if filters:
                cache_params.update(filters.model_dump() if hasattr(filters, 'model_dump') else vars(filters))
            cache_key = self._make_cache_key("total_count", cache_params)
            cached = self._get_from_cache(cache_key, ttl=300)
            if cached is not None:
                logger.debug("📦 SSANCAR total count cache hit")
                return cached
            
            # Build data dictionary - NOT a string! Same format as fetch_cars
            data = {
                "weekNo": week_no,
                "maker": filters.maker or "" if filters else "",
                "model": filters.model or "" if filters else "",
                "fuel": filters.fuel or "" if filters else "",
                "color": filters.color or "" if filters else "",
                "yearFrom": filters.yearFrom or "2000" if filters else "2000",
                "yearTo": filters.yearTo or "2025" if filters else "2025",
                "priceFrom": filters.priceFrom or "0" if filters else "0",
                "priceTo": filters.priceTo or "200000" if filters else "200000",
                "kmFrom": "0",
                "kmTo": "500000",
                "gearbox": "",
                "list": "15",
                "pages": "1",
                "sorts": "Low.Price",
                "no": filters.no or "" if filters else "",
            }
            
            logger.info(f"📊 Fetching total count from SSANCAR with filters: {data}")
            
            # Make the request using the same pattern as fetch_cars
            response = self.session.post(
                self.AJAX_CAR_NUM_URL,
                data=data,  # Send as dictionary, NOT string!
                timeout=15  # Same timeout as fetch_cars
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Non-200 status from SSANCAR car num: {response.status_code}")
                return 0
            
            # The response should be a simple HTML with just a number
            count_text = response.text.strip()
            
            # Try to extract the number
            try:
                total_count = int(count_text)
                logger.info(f"✅ Successfully fetched total count: {total_count}")
                self._save_to_cache(cache_key, total_count)
                return total_count
            except ValueError:
                logger.error(f"❌ Could not parse count from response: {count_text[:100]}")
                return 0
                
        except requests.RequestException as e:
            logger.error(f"❌ Request error fetching total count: {e}")
            return 0
        except Exception as e:
            logger.error(f"❌ Unexpected error fetching total count: {e}")
            return 0