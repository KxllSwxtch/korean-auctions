"""
SK Auction Service

Service for interacting with SK Car Rental Auction API.
URL: https://auction.skcarrental.com
"""

import time
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from loguru import logger

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

    def _create_session(self) -> None:
        """Create a new authenticated session"""
        logger.info("🔧 Creating new SK Auction session")

        if self._session:
            try:
                self._session.close()
            except Exception:
                pass

        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "OPTIONS"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers
        session.headers.update(self._default_headers)

        # Set initial cookies
        session.cookies.set("selectedLanguage", "en", domain="auction.skcarrental.com")

        # Disable SSL verification (some corporate sites have issues)
        session.verify = False

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

            login_url = f"{self.BASE_URL}{self.ENDPOINTS['login']}"

            # Login form data
            data = {
                "userId": self._username,
                "userPw": self._password,
                "returnUrl": "",
            }

            # Add Referer header for better request authenticity
            headers = {
                "Referer": f"{self.BASE_URL}/pc/main/selectLoginFormView.do",
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
            self._ensure_authenticated()

            # Default auction date to today
            if auction_date is None:
                auction_date = datetime.now().strftime("%Y%m%d")

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
                return SKAuctionDetailResponse(
                    success=True,
                    message="Car detail retrieved successfully",
                    data=car_detail,
                )
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
            return SKAuctionBrandsResponse(
                success=True,
                message=f"Retrieved {len(brands)} brands",
                brands=brands,
                total_count=len(brands),
            )

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
            self._ensure_authenticated()

            url = f"{self.BASE_URL}{self.ENDPOINTS['models']}"
            data = {
                "searchFlag": "mdl",
                "search_mkrCd": brand_code,
                "search_doimCd": region_code,
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
            return SKAuctionModelsResponse(
                success=True,
                message=f"Retrieved {len(models)} models",
                models=models,
                brand_code=brand_code,
                total_count=len(models),
            )

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
            self._ensure_authenticated()

            url = f"{self.BASE_URL}{self.ENDPOINTS['generations']}"
            data = {
                "searchFlag": "carGrp",
                "search_mdlCd": model_code,
                "search_doimCd": region_code,
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
            return SKAuctionGenerationsResponse(
                success=True,
                message=f"Retrieved {len(generations)} generations",
                generations=generations,
                model_code=model_code,
                total_count=len(generations),
            )

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
            return SKAuctionFuelTypesResponse(
                success=True,
                message=f"Retrieved {len(fuel_types)} fuel types",
                fuel_types=fuel_types,
            )

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
            return SKAuctionYearsResponse(
                success=True,
                message=f"Retrieved {len(years)} years",
                years=years,
            )

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
                auction_date = datetime.now().strftime("%Y%m%d")

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
