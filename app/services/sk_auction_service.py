"""
SK Auction Service

Service for interacting with SK Car Rental Auction API.
URL: https://auction.skcarrental.com
"""

import time
import json
import hashlib
import threading
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from loguru import logger

# Process-wide cap on concurrent outbound requests to auction.skcarrental.com.
# Mirrors the Autohub Phase 1 mitigation. Sessions are recreated on refresh,
# so we gate get/post inside _create_session().
_OUTBOUND_LIMIT = threading.BoundedSemaphore(5)

from app.models.sk_auction import (
    SKAuctionCar,
    SKAuctionCarDetail,
    SKAuctionBrand,
    SKAuctionModel,
    SKAuctionGeneration,
    SKAuctionFuelTypeOption,
    SKAuctionYearOption,
    SKAuctionResponse,
    SKAuctionDetailResponse,
    SKAuctionBrandsResponse,
    SKAuctionModelsResponse,
    SKAuctionGenerationsResponse,
    SKAuctionFuelTypesResponse,
    SKAuctionYearsResponse,
    SKAuctionCountResponse,
    SKAuctionSearchFilters,
    SKAuctionNextDateResponse,
)
from app.parsers.sk_auction_parser import SKAuctionParser
from app.core.config import get_settings
from app.core.logging import get_logger


class SKAuctionService:
    """Service for SK Car Rental Auction API"""

    BASE_URL = "https://auction.skcarrental.com"

    # API Endpoints
    ENDPOINTS = {
        "cars_list": "/auc/auctInfo/selectExhiList.do",
        "brands": "/sys/comnCombo/selectMultiComboVehi.do",
        "models": "/sys/comnCombo/selectMultiComboVehi.do",
        "generations": "/sys/comnCombo/selectMultiComboVehi.do",
        "fuel_types": "/sys/comnCd/selectCodeList.do",
        "years": "/sys/comnCd/selectCodeList.do",
        "login": "/main/actionLogin.do",
        "exhibition_page": "/pc/auc/auctInfo/selectExhiListView.do",
        "car_detail": "/pc/No",  # HTML page
    }

    # Session configuration
    SESSION_TIMEOUT = 30 * 60  # 30 minutes in seconds
    SESSION_REFRESH_BUFFER = 5 * 60  # Refresh 5 minutes before expiry

    def __init__(self):
        self.settings = get_settings()
        self.parser = SKAuctionParser()
        self._session: Optional[requests.Session] = None
        self._authenticated = False
        self._session_created_at: Optional[datetime] = None
        self._last_auth_check: Optional[datetime] = None

        # Credentials from config
        self._username = "094200"
        self._password = "baza9851@@"

        # In-memory cache with tiered TTL
        self._cache: Dict[str, tuple] = {}
        self._cache_hits = 0
        self._cache_misses = 0

        # Default headers for all requests
        self._default_headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": self.BASE_URL,
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

        # HTML page headers
        self._html_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

        logger.info("🚗 SK Auction Service initialized")

    # ==================== Session Management ====================

    @property
    def session(self) -> requests.Session:
        """Get or create an authenticated session"""
        if self._session is None or self._needs_session_refresh():
            self._create_session()
        return self._session

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
            return f"sk:{prefix}:{param_hash}"
        return f"sk:{prefix}"

    def _get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0
        return {
            "service": "SK Auction",
            "cache_entries": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate_percent": round(hit_rate, 2),
        }

    def _create_session(self) -> None:
        """Create a new authenticated session"""
        logger.info("🔧 Creating new SK Auction session")

        if self._session:
            try:
                self._session.close()
            except Exception:
                pass

        session = requests.Session()

        # Configure retry strategy — exponential backoff + Retry-After awareness
        retry_strategy = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "OPTIONS"],
            respect_retry_after_header=True,
        )

        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=10,
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers
        session.headers.update(self._default_headers)

        # Set initial cookies
        session.cookies.set("selectedLanguage", "en", domain="auction.skcarrental.com")

        # Disable SSL verification (some corporate sites have issues)
        session.verify = False

        # Gate session.get/post with the process-wide outbound semaphore.
        # Idempotency guard prevents compound wrapping on re-init.
        if not getattr(session.get, "_is_gated", False):
            _orig_get, _orig_post = session.get, session.post

            def _gated_get(*args, **kwargs):
                with _OUTBOUND_LIMIT:
                    return _orig_get(*args, **kwargs)
            _gated_get._is_gated = True

            def _gated_post(*args, **kwargs):
                with _OUTBOUND_LIMIT:
                    return _orig_post(*args, **kwargs)
            _gated_post._is_gated = True

            session.get = _gated_get
            session.post = _gated_post

        self._session = session
        self._session_created_at = datetime.now()

        # Authenticate
        if self._authenticate():
            logger.info("✅ SK Auction session created and authenticated")
        else:
            logger.warning("⚠️ SK Auction session created but authentication failed")

    def _needs_session_refresh(self) -> bool:
        """Check if session needs to be refreshed"""
        if self._session_created_at is None:
            return True

        elapsed = datetime.now() - self._session_created_at
        remaining = self.SESSION_TIMEOUT - elapsed.total_seconds()

        # Refresh if less than buffer time remaining
        if remaining < self.SESSION_REFRESH_BUFFER:
            logger.info(f"⏰ Session expiring in {remaining:.0f}s, refreshing...")
            return True

        return False

    def _authenticate(self) -> bool:
        """Authenticate with SK Auction"""
        try:
            logger.info(f"🔐 Authenticating with SK Auction as {self._username}")

            # First, visit the login page to get initial SESSION cookie
            login_page_url = f"{self.BASE_URL}/pc/main/selectLoginFormView.do"
            try:
                self._session.get(login_page_url, timeout=30)
            except Exception as e:
                logger.warning(f"Failed to fetch login page: {e}")

            login_url = f"{self.BASE_URL}{self.ENDPOINTS['login']}"

            # Login form data
            # membDiv: hidden field indicating auction member type
            # encPwd: password field (form copies userPwd to encPwd before submit)
            data = {
                "membDiv": "AUCT",
                "userId": self._username,
                "encPwd": self._password,
            }

            # Add headers for proper form submission
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": self.BASE_URL,
                "Referer": login_page_url,
            }

            response = self._session.post(
                login_url,
                data=data,
                headers=headers,
                timeout=30,
                allow_redirects=True,
            )

            # Successful login redirects to main page (302 -> 200)
            # Check if we're on the main page after redirect
            if response.status_code == 200:
                # Check for any session cookie (JSESSIONID or SESSION)
                cookies = self._session.cookies.get_dict()
                has_session_cookie = any(
                    k.upper() in ["SESSION", "JSESSIONID"] for k in cookies.keys()
                )

                if has_session_cookie:
                    self._authenticated = True
                    self._last_auth_check = datetime.now()
                    logger.info("✅ SK Auction authentication successful (session cookie found)")
                    return True

                # Even without explicit session cookie, check if logged in by content
                if "로그아웃" in response.text or "actionLogout.do" in response.text:
                    self._authenticated = True
                    self._last_auth_check = datetime.now()
                    logger.info("✅ SK Auction authentication successful (verified by page content)")
                    return True

                # Check if redirected to main page
                if "/main/selectMainView.do" in response.url:
                    self._authenticated = True
                    self._last_auth_check = datetime.now()
                    logger.info("✅ SK Auction authentication successful (redirected to main)")
                    return True

                logger.warning("⚠️ Login response OK but no session indicator found")
            else:
                logger.error(f"❌ SK Auction login failed: status={response.status_code}, url={response.url}")

            self._authenticated = False
            return False

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ SK Auction authentication error: {e}")
            self._authenticated = False
            return False

    def _ensure_authenticated(self) -> bool:
        """Ensure session is authenticated"""
        if self._needs_session_refresh():
            self._create_session()
        return self._authenticated

    # ==================== Auction Date Resolution ====================

    def _get_next_auction_date(self) -> str:
        """
        Get the next auction date from SK Auction website.

        The exhibition list page contains a hidden input set server-side:
        <input id="auctDt" name="auctDt" type="hidden" value="YYYYMMDD"/>
        This always points to the next auction date.

        Returns:
            Auction date string in YYYYMMDD format.
            Falls back to today's date if parsing fails.
        """
        cache_key = self._make_cache_key("next_auction_date")
        cached = self._get_from_cache(cache_key, ttl=self.settings.cache_ttl_auction_date)
        if cached is not None:
            logger.debug(f"📦 SK next auction date cache hit: {cached}")
            return cached

        fallback_date = datetime.now().strftime("%Y%m%d")

        try:
            self._ensure_authenticated()

            url = f"{self.BASE_URL}{self.ENDPOINTS['exhibition_page']}"
            logger.info("📥 Fetching SK Auction exhibition page for next auction date")

            response = self.session.get(url, headers=self._html_headers, timeout=30)

            if response.status_code != 200:
                logger.warning(f"⚠️ Exhibition page HTTP {response.status_code}")
                return fallback_date

            date_str = self.parser.parse_next_auction_date(response.text)

            if not date_str:
                logger.warning("⚠️ Parser returned None for auction date, using fallback")
                return fallback_date

            # Validate date format
            try:
                datetime.strptime(date_str, "%Y%m%d")
            except ValueError:
                logger.warning(f"⚠️ Invalid date format from parser: {date_str}")
                return fallback_date

            self._save_to_cache(cache_key, date_str)
            logger.info(f"✅ Next auction date resolved: {date_str}")
            return date_str

        except requests.exceptions.Timeout:
            logger.error("⏰ Timeout fetching exhibition page")
            return fallback_date
        except requests.exceptions.RequestException as e:
            logger.error(f"🌐 Network error fetching exhibition page: {e}")
            return fallback_date
        except Exception as e:
            logger.error(f"❌ Error resolving next auction date: {e}")
            return fallback_date

    def get_next_auction_date(self) -> SKAuctionNextDateResponse:
        """
        Get the next auction date with metadata.

        Returns:
            SKAuctionNextDateResponse with date info
        """
        try:
            date_str = self._get_next_auction_date()

            parsed = datetime.strptime(date_str, "%Y%m%d").date()
            today = datetime.now().date()

            formatted = f"{date_str[:4]}.{date_str[4:6]}.{date_str[6:8]}"
            is_today = parsed == today
            is_future = parsed > today

            if is_today:
                message = "Auction is today"
            elif is_future:
                days_until = (parsed - today).days
                message = f"Next auction in {days_until} day{'s' if days_until != 1 else ''}"
            else:
                message = "Auction date is in the past"

            return SKAuctionNextDateResponse(
                success=True,
                auction_date=date_str,
                formatted_date=formatted,
                is_today=is_today,
                is_future=is_future,
                message=message,
            )
        except Exception as e:
            logger.error(f"❌ Error building auction date response: {e}")
            fallback = datetime.now().strftime("%Y%m%d")
            return SKAuctionNextDateResponse(
                success=False,
                auction_date=fallback,
                formatted_date=f"{fallback[:4]}.{fallback[4:6]}.{fallback[6:8]}",
                is_today=True,
                is_future=False,
                message=f"Error: {str(e)}",
            )

    # ==================== API Methods ====================

    def get_cars(
        self,
        filters: Optional[SKAuctionSearchFilters] = None,
        page: int = 1,
        page_size: int = 20,
        auction_date: Optional[str] = None,
    ) -> SKAuctionResponse:
        """
        Get list of cars from SK Auction.

        Args:
            filters: Search filters
            page: Page number (1-based)
            page_size: Records per page
            auction_date: Auction date in YYYYMMDD format (defaults to today)

        Returns:
            SKAuctionResponse with cars list
        """
        start_time = time.time()

        try:
            # Default auction date to today
            if auction_date is None:
                auction_date = self._get_next_auction_date()

            # Check cache (3min TTL for car listings)
            cache_params = {
                "filters": filters.model_dump() if filters else None,
                "page": page,
                "page_size": page_size,
                "auction_date": auction_date,
            }
            cache_key = self._make_cache_key("cars", cache_params)
            cached = self._get_from_cache(cache_key, ttl=self.settings.cache_ttl_car_list)
            if cached is not None:
                logger.debug(f"📦 SK Auction cars cache hit: {cache_key}")
                return cached

            self._ensure_authenticated()

            # Build request data
            data = self._build_cars_request_data(filters, page, page_size, auction_date)

            logger.info(f"📥 Fetching SK Auction cars: page={page}, filters={filters}")

            # Make request
            url = f"{self.BASE_URL}{self.ENDPOINTS['cars_list']}"
            response = self.session.post(url, data=data, timeout=30)

            if response.status_code != 200:
                logger.error(f"❌ SK Auction API error: {response.status_code}")
                return SKAuctionResponse(
                    success=False,
                    message=f"API error: {response.status_code}",
                    cars=[],
                    request_duration=time.time() - start_time,
                )

            # Parse response
            json_data = response.json()
            result = self.parser.parse_cars_json(json_data, page, page_size)
            result.request_duration = time.time() - start_time
            result.auction_date = auction_date

            # Cache successful result
            if result.success:
                self._save_to_cache(cache_key, result)

            logger.info(f"✅ Fetched {len(result.cars)} cars in {result.request_duration:.2f}s")
            return result

        except requests.exceptions.Timeout:
            logger.error("⏰ SK Auction request timeout")
            return SKAuctionResponse(
                success=False,
                message="Request timeout",
                cars=[],
                request_duration=time.time() - start_time,
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"🌐 SK Auction network error: {e}")
            return SKAuctionResponse(
                success=False,
                message=f"Network error: {str(e)}",
                cars=[],
                request_duration=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"❌ SK Auction error: {e}")
            return SKAuctionResponse(
                success=False,
                message=f"Error: {str(e)}",
                cars=[],
                request_duration=time.time() - start_time,
            )

    def _build_cars_request_data(
        self,
        filters: Optional[SKAuctionSearchFilters],
        page: int,
        page_size: int,
        auction_date: str,
    ) -> Dict[str, Any]:
        """Build request data for cars list API"""
        data = {
            "pageIndex": str(page),
            "pageUnitCnt": str(page_size),
            "auctDt": auction_date,
            "search_doimCd": "all",
            "set_search_maker": "",
            "set_search_mdl": "",
            "set_search_chk_carGrp": "",
            "search_startYyyy": "",
            "search_endYyyy": "",
            "search_startKm": "",
            "search_endKm": "",
            "search_startPrice": "",
            "search_endPrice": "",
            "search_fuelCd": "",
            "search_trnsCd": "",
            "accidGrade": "",
            "stateGrade": "",
            "search_exhiNo": "",
            "search_concVal": "",
            "search_LaneDiv": "",
            "v_pageUnitCnt": str(page_size),
        }

        if filters:
            if filters.brand_code:
                data["set_search_maker"] = filters.brand_code
            if filters.model_code:
                data["set_search_mdl"] = filters.model_code
            if filters.generation_codes:
                # Join multiple generation codes
                data["set_search_chk_carGrp"] = ",".join(filters.generation_codes)
            if filters.year_from:
                data["search_startYyyy"] = str(filters.year_from)
            if filters.year_to:
                data["search_endYyyy"] = str(filters.year_to)
            if filters.mileage_from:
                data["search_startKm"] = str(filters.mileage_from)
            if filters.mileage_to:
                data["search_endKm"] = str(filters.mileage_to)
            if filters.price_from:
                data["search_startPrice"] = str(filters.price_from)
            if filters.price_to:
                data["search_endPrice"] = str(filters.price_to)
            if filters.fuel_type:
                data["search_fuelCd"] = filters.fuel_type
            if filters.transmission:
                data["search_trnsCd"] = filters.transmission
            if filters.accident_grade:
                data["accidGrade"] = filters.accident_grade
            if filters.condition_grade:
                data["stateGrade"] = filters.condition_grade
            if filters.exhibition_number:
                data["search_exhiNo"] = filters.exhibition_number
            if filters.lane_division:
                data["search_LaneDiv"] = filters.lane_division
            if filters.region_code and filters.region_code != "all":
                data["search_doimCd"] = filters.region_code

        return data

    def get_car_detail(
        self,
        mng_div_cd: str,
        mng_no: str,
        exhi_regi_seq: int,
    ) -> SKAuctionDetailResponse:
        """
        Get car detail by scraping HTML page.

        Args:
            mng_div_cd: Management division code (e.g., SR)
            mng_no: Management number (e.g., SR25000114199)
            exhi_regi_seq: Exhibition registration sequence

        Returns:
            SKAuctionDetailResponse with car detail
        """
        start_time = time.time()

        try:
            # Check cache (30min TTL for car details)
            cache_key = self._make_cache_key("detail", {"mng_div_cd": mng_div_cd, "mng_no": mng_no, "exhi_regi_seq": exhi_regi_seq})
            cached = self._get_from_cache(cache_key, ttl=self.settings.cache_ttl_car_detail)
            if cached is not None:
                logger.debug(f"📦 SK Auction car detail cache hit: {mng_no}")
                return cached

            self._ensure_authenticated()

            # Build URL for car detail page
            url = f"{self.BASE_URL}{self.ENDPOINTS['car_detail']}/{mng_div_cd}/{mng_no}/{exhi_regi_seq}"
            logger.info(f"📥 Fetching SK Auction car detail: {url}")

            # Use HTML headers for page request
            response = self.session.get(
                url,
                headers=self._html_headers,
                timeout=30,
            )

            if response.status_code != 200:
                logger.error(f"❌ SK Auction detail page error: {response.status_code}")
                return SKAuctionDetailResponse(
                    success=False,
                    message=f"Page error: {response.status_code}",
                    data=None,
                )

            # Parse HTML
            car_detail = self.parser.parse_car_detail_html(
                response.text,
                mng_div_cd,
                mng_no,
                exhi_regi_seq,
            )

            if car_detail:
                logger.info(f"✅ Parsed car detail for {mng_no}")
                result = SKAuctionDetailResponse(
                    success=True,
                    message="Car detail retrieved successfully",
                    data=car_detail,
                )
                self._save_to_cache(cache_key, result)
                return result
            else:
                logger.warning(f"⚠️ Failed to parse car detail for {mng_no}")
                return SKAuctionDetailResponse(
                    success=False,
                    message="Failed to parse car detail",
                    data=None,
                )

        except requests.exceptions.Timeout:
            logger.error("⏰ SK Auction detail request timeout")
            return SKAuctionDetailResponse(
                success=False,
                message="Request timeout",
                data=None,
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"🌐 SK Auction detail network error: {e}")
            return SKAuctionDetailResponse(
                success=False,
                message=f"Network error: {str(e)}",
                data=None,
            )

        except Exception as e:
            logger.error(f"❌ SK Auction detail error: {e}")
            return SKAuctionDetailResponse(
                success=False,
                message=f"Error: {str(e)}",
                data=None,
            )

    def get_brands(self, region_code: str = "all") -> SKAuctionBrandsResponse:
        """
        Get list of car brands.

        Args:
            region_code: Region filter (default: all)

        Returns:
            SKAuctionBrandsResponse with brands list
        """
        try:
            # Check cache (24h TTL for static metadata)
            cache_key = self._make_cache_key("brands", {"region": region_code})
            cached = self._get_from_cache(cache_key, ttl=self.settings.cache_ttl_static)
            if cached is not None:
                logger.debug(f"📦 SK Auction brands cache hit")
                return cached

            self._ensure_authenticated()

            url = f"{self.BASE_URL}{self.ENDPOINTS['brands']}"
            data = {
                "searchFlag": "maker",
                "search_doimCd": region_code,
            }

            logger.info(f"📥 Fetching SK Auction brands")
            response = self.session.post(url, data=data, timeout=30)

            if response.status_code != 200:
                logger.error(f"❌ SK Auction brands API error: {response.status_code}")
                return SKAuctionBrandsResponse(
                    success=False,
                    message=f"API error: {response.status_code}",
                    brands=[],
                    total_count=0,
                )

            json_data = response.json()
            brands = self.parser.parse_brands_json(json_data)

            logger.info(f"✅ Fetched {len(brands)} brands")
            result = SKAuctionBrandsResponse(
                success=True,
                message=f"Retrieved {len(brands)} brands",
                brands=brands,
                total_count=len(brands),
            )
            self._save_to_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"❌ SK Auction brands error: {e}")
            return SKAuctionBrandsResponse(
                success=False,
                message=f"Error: {str(e)}",
                brands=[],
                total_count=0,
            )

    def get_models(self, brand_code: str, region_code: str = "all") -> SKAuctionModelsResponse:
        """
        Get list of models for a brand.

        Args:
            brand_code: Brand code (e.g., ABI000000005)
            region_code: Region filter (default: all)

        Returns:
            SKAuctionModelsResponse with models list
        """
        try:
            # Check cache (24h TTL for static metadata)
            cache_key = self._make_cache_key("models", {"brand": brand_code, "region": region_code})
            cached = self._get_from_cache(cache_key, ttl=self.settings.cache_ttl_static)
            if cached is not None:
                logger.debug(f"📦 SK Auction models cache hit for brand {brand_code}")
                return cached

            self._ensure_authenticated()

            url = f"{self.BASE_URL}{self.ENDPOINTS['models']}"
            data = {
                "searchFlag": "mdl",
                "searchCode": brand_code,
            }

            logger.info(f"📥 Fetching SK Auction models for brand {brand_code}")
            response = self.session.post(url, data=data, timeout=30)

            if response.status_code != 200:
                logger.error(f"❌ SK Auction models API error: {response.status_code}")
                return SKAuctionModelsResponse(
                    success=False,
                    message=f"API error: {response.status_code}",
                    models=[],
                    brand_code=brand_code,
                    total_count=0,
                )

            json_data = response.json()
            models = self.parser.parse_models_json(json_data, brand_code)

            logger.info(f"✅ Fetched {len(models)} models for brand {brand_code}")
            result = SKAuctionModelsResponse(
                success=True,
                message=f"Retrieved {len(models)} models",
                models=models,
                brand_code=brand_code,
                total_count=len(models),
            )
            self._save_to_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"❌ SK Auction models error: {e}")
            return SKAuctionModelsResponse(
                success=False,
                message=f"Error: {str(e)}",
                models=[],
                brand_code=brand_code,
                total_count=0,
            )

    def get_generations(self, model_code: str, region_code: str = "all") -> SKAuctionGenerationsResponse:
        """
        Get list of generations for a model.

        Args:
            model_code: Model code (e.g., ABI000000096)
            region_code: Region filter (default: all)

        Returns:
            SKAuctionGenerationsResponse with generations list
        """
        try:
            # Check cache (24h TTL for static metadata)
            cache_key = self._make_cache_key("generations", {"model": model_code, "region": region_code})
            cached = self._get_from_cache(cache_key, ttl=self.settings.cache_ttl_static)
            if cached is not None:
                logger.debug(f"📦 SK Auction generations cache hit for model {model_code}")
                return cached

            self._ensure_authenticated()

            url = f"{self.BASE_URL}{self.ENDPOINTS['generations']}"
            data = {
                "searchFlag": "carGrp",
                "searchCode": model_code,
            }

            logger.info(f"📥 Fetching SK Auction generations for model {model_code}")
            response = self.session.post(url, data=data, timeout=30)

            if response.status_code != 200:
                logger.error(f"❌ SK Auction generations API error: {response.status_code}")
                return SKAuctionGenerationsResponse(
                    success=False,
                    message=f"API error: {response.status_code}",
                    generations=[],
                    model_code=model_code,
                    total_count=0,
                )

            json_data = response.json()
            generations = self.parser.parse_generations_json(json_data, model_code)

            logger.info(f"✅ Fetched {len(generations)} generations for model {model_code}")
            result = SKAuctionGenerationsResponse(
                success=True,
                message=f"Retrieved {len(generations)} generations",
                generations=generations,
                model_code=model_code,
                total_count=len(generations),
            )
            self._save_to_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"❌ SK Auction generations error: {e}")
            return SKAuctionGenerationsResponse(
                success=False,
                message=f"Error: {str(e)}",
                generations=[],
                model_code=model_code,
                total_count=0,
            )

    def get_fuel_types(self) -> SKAuctionFuelTypesResponse:
        """
        Get list of fuel types.

        Returns:
            SKAuctionFuelTypesResponse with fuel types list
        """
        try:
            # Check cache (24h TTL for static metadata)
            cache_key = self._make_cache_key("fuel_types")
            cached = self._get_from_cache(cache_key, ttl=self.settings.cache_ttl_static)
            if cached is not None:
                logger.debug("📦 SK Auction fuel types cache hit")
                return cached

            self._ensure_authenticated()

            url = f"{self.BASE_URL}{self.ENDPOINTS['fuel_types']}"
            data = {
                "codeId": "FUEL_CD",
                "defaultCode": "",
                "defaultName": "-전체-",
            }

            logger.info("📥 Fetching SK Auction fuel types")
            response = self.session.post(url, data=data, timeout=30)

            if response.status_code != 200:
                logger.error(f"❌ SK Auction fuel types API error: {response.status_code}")
                return SKAuctionFuelTypesResponse(
                    success=False,
                    message=f"API error: {response.status_code}",
                    fuel_types=[],
                )

            json_data = response.json()
            fuel_types = self.parser.parse_fuel_types_json(json_data)

            logger.info(f"✅ Fetched {len(fuel_types)} fuel types")
            result = SKAuctionFuelTypesResponse(
                success=True,
                message=f"Retrieved {len(fuel_types)} fuel types",
                fuel_types=fuel_types,
            )
            self._save_to_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"❌ SK Auction fuel types error: {e}")
            return SKAuctionFuelTypesResponse(
                success=False,
                message=f"Error: {str(e)}",
                fuel_types=[],
            )

    def get_years(self) -> SKAuctionYearsResponse:
        """
        Get list of available years.

        Returns:
            SKAuctionYearsResponse with years list
        """
        try:
            # Check cache (24h TTL for static metadata)
            cache_key = self._make_cache_key("years")
            cached = self._get_from_cache(cache_key, ttl=self.settings.cache_ttl_static)
            if cached is not None:
                logger.debug("📦 SK Auction years cache hit")
                return cached

            self._ensure_authenticated()

            url = f"{self.BASE_URL}{self.ENDPOINTS['years']}"
            data = {
                "codeId": "REGI_YEAR_CD",
                "defaultCode": "",
                "defaultName": "-전체-",
            }

            logger.info("📥 Fetching SK Auction years")
            response = self.session.post(url, data=data, timeout=30)

            if response.status_code != 200:
                logger.error(f"❌ SK Auction years API error: {response.status_code}")
                return SKAuctionYearsResponse(
                    success=False,
                    message=f"API error: {response.status_code}",
                    years=[],
                )

            json_data = response.json()
            years = self.parser.parse_years_json(json_data)

            logger.info(f"✅ Fetched {len(years)} years")
            result = SKAuctionYearsResponse(
                success=True,
                message=f"Retrieved {len(years)} years",
                years=years,
            )
            self._save_to_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"❌ SK Auction years error: {e}")
            return SKAuctionYearsResponse(
                success=False,
                message=f"Error: {str(e)}",
                years=[],
            )

    def get_total_count(self, auction_date: Optional[str] = None) -> SKAuctionCountResponse:
        """
        Get total count of cars for an auction date.

        Args:
            auction_date: Auction date in YYYYMMDD format (defaults to today)

        Returns:
            SKAuctionCountResponse with total count
        """
        try:
            if auction_date is None:
                auction_date = self._get_next_auction_date()

            # Fetch first page with minimal data to get count
            result = self.get_cars(page=1, page_size=1, auction_date=auction_date)

            return SKAuctionCountResponse(
                success=result.success,
                total_count=result.total_count,
                message=f"Total {result.total_count} cars available",
                auction_date=auction_date,
            )

        except Exception as e:
            logger.error(f"❌ SK Auction count error: {e}")
            return SKAuctionCountResponse(
                success=False,
                total_count=0,
                message=f"Error: {str(e)}",
                auction_date=auction_date,
            )

    def search_cars(
        self,
        filters: SKAuctionSearchFilters,
        page: int = 1,
        page_size: int = 20,
        auction_date: Optional[str] = None,
    ) -> SKAuctionResponse:
        """
        Search cars with filters.

        Args:
            filters: Search filters
            page: Page number (1-based)
            page_size: Records per page
            auction_date: Auction date in YYYYMMDD format

        Returns:
            SKAuctionResponse with filtered cars
        """
        return self.get_cars(
            filters=filters,
            page=page,
            page_size=page_size,
            auction_date=auction_date,
        )

    # ==================== Health Check ====================

    def health_check(self) -> Dict[str, Any]:
        """
        Check service health.

        Returns:
            Health status dictionary
        """
        try:
            logger.info("🏥 SK Auction service health check")

            # Try to authenticate
            self._ensure_authenticated()

            return {
                "service": "SK Auction Service",
                "status": "healthy" if self._authenticated else "degraded",
                "authenticated": self._authenticated,
                "base_url": self.BASE_URL,
                "session_age": (
                    (datetime.now() - self._session_created_at).total_seconds()
                    if self._session_created_at
                    else None
                ),
                "timestamp": datetime.now().isoformat(),
                "features": {
                    "car_list": True,
                    "car_detail": True,
                    "brands": True,
                    "models": True,
                    "generations": True,
                    "fuel_types": True,
                    "years": True,
                    "search": True,
                },
            }

        except Exception as e:
            logger.error(f"❌ SK Auction health check error: {e}")
            return {
                "service": "SK Auction Service",
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def __del__(self):
        """Cleanup session on destruction"""
        try:
            if hasattr(self, "_session") and self._session:
                self._session.close()
                logger.info("🧹 SK Auction session closed")
        except Exception:
            pass
