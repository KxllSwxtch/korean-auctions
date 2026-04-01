"""
Autohub JSON API service.

Replaces HTML scraping with direct JSON API calls to api.ahsellcar.co.kr.
"""

import time
import json
import hashlib
import base64
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.models.autohub import (
    AutohubResponse,
    AutohubCarDetail,
    AutohubCarDetailResponse,
)
from app.models.autohub_filters import (
    AutohubSearchRequest,
    AutohubBrandsResponse,
    AutohubBrandsGroup,
    AutohubFilterInfo,
    AutohubSortOrder,
    AutohubFuelType,
    AutohubAuctionResult,
    AutohubLane,
    AUTOHUB_MILEAGE_OPTIONS,
    AUTOHUB_PRICE_OPTIONS,
)
from app.parsers.autohub_parser import (
    map_car_list,
    map_car_detail,
    map_inspection,
    map_diagram,
    map_brands,
    extract_entry_prices,
)
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("autohub_service")


class AutohubService:
    """Service for Autohub JSON API"""

    def __init__(self):
        self.settings = get_settings()
        self._session: Optional[requests.Session] = None
        self._jwt_token: Optional[str] = self.settings.autohub_jwt_token
        self._refresh_token: Optional[str] = None
        self.api_base = self.settings.autohub_api_base_url

        # In-memory cache with tiered TTL
        self._cache: Dict[str, tuple] = {}
        self._cache_hits = 0
        self._cache_misses = 0

        # Auto-authenticate if no valid token from env
        if not self._is_token_valid():
            self._authenticate()

    # ===== Session Management =====

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = self._create_session()
        return self._session

    def _create_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update(self._get_base_headers())
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        return s

    def _get_base_headers(self) -> Dict[str, str]:
        """Browser-like headers to avoid WAF/CDN blocking."""
        return {
            "Accept": "application/json",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.5,en;q=0.3",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Origin": "https://www.autohubauction.co.kr",
            "Pragma": "no-cache",
            "Referer": "https://www.autohubauction.co.kr/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "User-Agent": self.settings.user_agent,
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }

    def _get_auth_headers(self) -> Dict[str, str]:
        headers = self._get_base_headers()
        if self._jwt_token:
            headers["Authorization"] = f"Bearer {self._jwt_token}"
        return headers

    def _is_token_valid(self) -> bool:
        """Check if the JWT token is present and not expired."""
        if not self._jwt_token:
            return False
        try:
            parts = self._jwt_token.split(".")
            if len(parts) != 3:
                return False
            # Decode payload (add padding)
            payload = parts[1]
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            decoded = json.loads(base64.urlsafe_b64decode(payload))
            exp = decoded.get("exp", 0)
            # Token valid if not expired (with 5 min margin)
            return time.time() < (exp - 300)
        except Exception as e:
            logger.warning(f"Failed to decode JWT token: {e}")
            return False

    def _authenticate(self) -> bool:
        """Login to Autohub API to obtain JWT access token."""
        try:
            logger.info("Authenticating with Autohub API...")
            response = self.session.post(
                self.settings.autohub_signin_url,
                json={
                    "userEmail": self.settings.autohub_username,
                    "pw": self.settings.autohub_password,
                    "productId": self.settings.autohub_product_id,
                },
                headers=self._get_base_headers(),
                timeout=self.settings.request_timeout,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("code") == "1" and data.get("data", {}).get("accessToken"):
                self._jwt_token = data["data"]["accessToken"]
                self._refresh_token = data["data"].get("refreshToken")
                logger.info("Authentication successful")
                return True
            else:
                msg = data.get("message", "Unknown error")
                logger.error(f"Authentication failed: {msg}")
                return False
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False

    def _ensure_authenticated(self) -> None:
        """Ensure we have a valid JWT token, authenticate if needed."""
        if not self._is_token_valid():
            if not self._authenticate():
                raise requests.exceptions.HTTPError(
                    "Failed to authenticate with Autohub API",
                    response=type("Response", (), {"status_code": 401})(),
                )

    def set_jwt_token(self, token: str) -> bool:
        """Set or update JWT token."""
        self._jwt_token = token
        valid = self._is_token_valid()
        logger.info(f"JWT token {'accepted (valid)' if valid else 'set (validation status unknown)'}")
        return valid

    # ===== Cache =====

    def _get_from_cache(self, key: str, ttl: int = 300) -> Optional[Any]:
        if key in self._cache:
            data, timestamp = self._cache[key]
            if time.time() - timestamp < ttl:
                self._cache_hits += 1
                return data
            del self._cache[key]
        self._cache_misses += 1
        return None

    def _save_to_cache(self, key: str, data: Any) -> None:
        self._cache[key] = (data, time.time())

    def _make_cache_key(self, prefix: str, params: Optional[Dict] = None) -> str:
        if params:
            param_str = json.dumps(params, sort_keys=True, default=str)
            param_hash = hashlib.md5(param_str.encode()).hexdigest()[:12]
            return f"autohub:{prefix}:{param_hash}"
        return f"autohub:{prefix}"

    def _get_cache_stats(self) -> Dict[str, Any]:
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0
        return {
            "service": "Autohub",
            "total_requests": total,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate_percent": round(hit_rate, 1),
            "cached_keys": len(self._cache),
        }

    # ===== API Methods =====

    def _api_get(self, path: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make authenticated GET request to Autohub API with auto-auth and 401/403 retry."""
        self._ensure_authenticated()
        url = f"{self.api_base}{path}"
        logger.info(f"GET {url}")
        response = self.session.get(
            url,
            headers=self._get_auth_headers(),
            params=params,
            timeout=self.settings.request_timeout,
        )
        if response.status_code in (401, 403):
            logger.warning(f"Got {response.status_code} on GET, re-authenticating...")
            logger.debug(f"Response body: {response.text[:500]}")
            if self._authenticate():
                response = self.session.get(
                    url,
                    headers=self._get_auth_headers(),
                    params=params,
                    timeout=self.settings.request_timeout,
                )
        response.raise_for_status()
        return response.json()

    def _api_post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """Make authenticated POST request to Autohub API with auto-auth and 401/403 retry."""
        self._ensure_authenticated()
        url = f"{self.api_base}{path}"
        logger.info(f"POST {url}")
        response = self.session.post(
            url,
            headers=self._get_auth_headers(),
            json=body,
            timeout=self.settings.request_timeout,
        )
        if response.status_code in (401, 403):
            logger.warning(f"Got {response.status_code} on POST, re-authenticating...")
            logger.debug(f"Response body: {response.text[:500]}")
            if self._authenticate():
                response = self.session.post(
                    url,
                    headers=self._get_auth_headers(),
                    json=body,
                    timeout=self.settings.request_timeout,
                )
        response.raise_for_status()
        return response.json()

    # ===== Core Methods =====

    def get_car_list(self, params: AutohubSearchRequest) -> AutohubResponse:
        """Fetch car listing from API. Dispatches to entry search when needed."""
        if params.entry_number:
            return self._search_by_entry_number(params)
        return self._fetch_car_page(params)

    def _fetch_car_page(self, params: AutohubSearchRequest) -> AutohubResponse:
        """Fetch a single page of car listings from the external API."""
        api_body = params.to_api_body()
        cache_key = self._make_cache_key("car_list", api_body)
        cached = self._get_from_cache(cache_key, ttl=self.settings.cache_ttl_car_list)
        if cached:
            return cached

        try:
            response_data = self._api_post(
                "/auction/external/rest/api/v1/entry/list/paging",
                api_body,
            )
            cars, total_count, total_pages = map_car_list(response_data)

            # Fallback: if API didn't provide total_pages, compute it
            if total_pages == 0 and total_count > 0 and params.page_size > 0:
                total_pages = (total_count + params.page_size - 1) // params.page_size

            result = AutohubResponse(
                success=True,
                data=cars,
                total_count=total_count,
                total_pages=total_pages,
                current_page=params.page,
                page_size=params.page_size,
            )
            self._save_to_cache(cache_key, result)
            return result

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else 0
            if status_code == 401:
                logger.error("Authentication failed after retry")
                return AutohubResponse(
                    success=False,
                    error="Authentication failed after retry. Check credentials.",
                    current_page=params.page,
                    page_size=params.page_size,
                )
            logger.error(f"HTTP error fetching car list: {e}")
            return AutohubResponse(
                success=False,
                error=f"HTTP error: {status_code}",
                current_page=params.page,
                page_size=params.page_size,
            )
        except Exception as e:
            logger.error(f"Error fetching car list: {e}", exc_info=True)
            return AutohubResponse(
                success=False,
                error=str(e),
                current_page=params.page,
                page_size=params.page_size,
            )

    def _search_by_entry_number(self, params: AutohubSearchRequest) -> AutohubResponse:
        """Search for a specific car by entry number using server-side filtering.

        The external API does not support entryNo as a request filter,
        so we fetch pages sorted by entry number and scan for the match.
        Early termination: stop once we pass the target in sorted order.
        """
        target = params.entry_number
        try:
            target_int = int(target)
        except (ValueError, TypeError):
            return AutohubResponse(
                success=True, data=[], total_count=0,
                total_pages=0, current_page=1, page_size=params.page_size,
            )

        # Check cache (keyed by normalized entry number + active filters)
        cache_key = self._make_cache_key("entry_search", {
            "entry": target_int,
            "brands": params.car_brands,
            "models": params.car_models,
            "details": params.car_model_details,
            "fuel": params.fuel_type.value if params.fuel_type else None,
            "lane": params.lane.value if params.lane else None,
            "year_from": params.year_from,
            "year_to": params.year_to,
            "mileage_from": params.mileage_from,
            "mileage_to": params.mileage_to,
            "price_from": params.price_from,
            "price_to": params.price_to,
            "auction_result": params.auction_result.value if params.auction_result else None,
            "condition_grade": params.condition_grade,
        })
        cached = self._get_from_cache(cache_key, ttl=self.settings.cache_ttl_car_list)
        if cached:
            return cached

        # Build scan params: no entry_number, large page, sorted by entry asc
        scan_params = params.model_copy()
        scan_params.entry_number = None
        scan_params.page_size = 100
        scan_params.sort_order = AutohubSortOrder.ENTRY
        scan_params.sort_direction = "asc"
        scan_params.page = 1

        max_pages = 30  # safety limit (~3000 cars)

        for page_num in range(1, max_pages + 1):
            scan_params.page = page_num
            result = self._fetch_car_page(scan_params)

            if not result.success or not result.data:
                break

            for car in result.data:
                try:
                    car_entry_int = int(car.auction_number)
                except (ValueError, TypeError):
                    continue

                if car_entry_int == target_int:
                    found = AutohubResponse(
                        success=True, data=[car],
                        total_count=1, total_pages=1,
                        current_page=1, page_size=params.page_size,
                    )
                    self._save_to_cache(cache_key, found)
                    return found

                if car_entry_int > target_int:
                    # Passed target in sorted order — not found
                    break
            else:
                # Inner loop completed without break; check if more pages exist
                if page_num >= result.total_pages:
                    break
                continue
            break  # Inner loop broke (early termination)

        not_found = AutohubResponse(
            success=True, data=[], total_count=0,
            total_pages=0, current_page=1, page_size=params.page_size,
        )
        self._save_to_cache(cache_key, not_found)
        return not_found

    def get_brands(self) -> AutohubBrandsResponse:
        """Fetch hierarchical brands from API (cached 24h)."""
        cache_key = self._make_cache_key("brands")
        cached = self._get_from_cache(cache_key, ttl=self.settings.cache_ttl_static)
        if cached:
            return cached

        try:
            response_data = self._api_get(
                "/auction/external/rest/api/v1/entry/car/brand/list"
            )
            groups = map_brands(response_data)
            result = AutohubBrandsResponse(success=True, data=groups)
            self._save_to_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error fetching brands: {e}", exc_info=True)
            return AutohubBrandsResponse(success=False, error=str(e))

    def get_car_detail(self, car_id: str, perf_id: Optional[str] = None) -> AutohubCarDetailResponse:
        """Fetch composite car detail from multiple endpoints."""
        cache_key = self._make_cache_key("car_detail", {"car_id": car_id, "perf_id": perf_id})
        cached = self._get_from_cache(cache_key, ttl=self.settings.cache_ttl_car_detail)
        if cached:
            return cached

        try:
            # Parallel API calls using ThreadPoolExecutor
            detail_data = {}
            inspection_data = {}
            diagram_data = {}
            legend_data = {}
            perf_frame_data = {}
            entry_listing_data = {}

            def fetch_detail():
                return self._api_get(f"/cardata/external/rest/api/v1/data/info/{car_id}")

            def fetch_inspection():
                if not perf_id:
                    return {}
                return self._api_get(f"/inspection/external/rest/api/v1/perf/review/report/{perf_id}")

            def fetch_diagram():
                return self._api_get(
                    "/inspection/external/rest/api/v1/layout/list",
                    params={"carId": car_id, "perfClsSet": "EXTERIOR"},
                )

            def fetch_legend():
                cache_legend_key = self._make_cache_key("legend")
                cached_legend = self._get_from_cache(cache_legend_key, ttl=self.settings.cache_ttl_static)
                if cached_legend:
                    return cached_legend
                result = self._api_get("/inspection/external/rest/api/v1/layout/criteria/frames")
                self._save_to_cache(cache_legend_key, result)
                return result

            def fetch_perf_frame():
                if not perf_id:
                    return {}
                return self._api_get(
                    "/inspection/external/rest/api/v1/perf/frame/info",
                    params={"perfId": perf_id},
                )

            def fetch_entry_listing():
                """Fetch listing entry for this car to get pricing data."""
                return self._api_post(
                    "/auction/external/rest/api/v1/entry/list/paging",
                    {"tenant": "1", "carId": car_id, "pageSize": 5, "pageIndex": 1},
                )

            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = {
                    executor.submit(fetch_detail): "detail",
                    executor.submit(fetch_inspection): "inspection",
                    executor.submit(fetch_diagram): "diagram",
                    executor.submit(fetch_legend): "legend",
                    executor.submit(fetch_perf_frame): "perf_frame",
                    executor.submit(fetch_entry_listing): "entry_listing",
                }

                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        result = future.result()
                        if name == "detail":
                            detail_data = result
                        elif name == "inspection":
                            inspection_data = result
                        elif name == "diagram":
                            diagram_data = result
                        elif name == "legend":
                            legend_data = result
                        elif name == "perf_frame":
                            perf_frame_data = result
                        elif name == "entry_listing":
                            entry_listing_data = result
                    except Exception as e:
                        logger.warning(f"Failed to fetch {name} for car {car_id}: {e}")

            # Map detail
            car_detail = map_car_detail(detail_data)

            # Extract prices from listing entry if available
            if entry_listing_data:
                starting_price, hope_price = extract_entry_prices(entry_listing_data, car_id)
                car_detail.starting_price = starting_price
                car_detail.hope_price = hope_price

            # Map inspection if available
            if inspection_data:
                car_detail.inspection = map_inspection(inspection_data)

            # Map diagram if available
            if diagram_data:
                car_detail.diagram = map_diagram(diagram_data, legend_data, perf_frame_data)

            result = AutohubCarDetailResponse(success=True, data=car_detail)
            self._save_to_cache(cache_key, result)
            return result

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else 0
            error_msg = "Authentication failed after retry. Check credentials." if status_code == 401 else f"HTTP error: {status_code}"
            logger.error(f"HTTP error fetching car detail: {e}")
            return AutohubCarDetailResponse(
                success=False,
                error=error_msg,
            )
        except Exception as e:
            logger.error(f"Error fetching car detail: {e}", exc_info=True)
            return AutohubCarDetailResponse(success=False, error=str(e))

    def get_filters_info(self) -> AutohubFilterInfo:
        """Get filter options for frontend."""
        return AutohubFilterInfo(
            fuel_types=[
                {"code": ft.value, "name": ft.name.replace("_", " ").title()}
                for ft in AutohubFuelType
                if ft != AutohubFuelType.ALL
            ],
            lanes=[
                {"code": lane.value, "name": f"Lane {lane.value}"}
                for lane in AutohubLane
                if lane != AutohubLane.ALL
            ],
            auction_results=[
                {"code": ar.value, "name": ar.name.replace("_", " ").title()}
                for ar in AutohubAuctionResult
                if ar != AutohubAuctionResult.ALL
            ],
            year_range={"min": 1990, "max": 2026},
            mileage_options=AUTOHUB_MILEAGE_OPTIONS,
            price_options=AUTOHUB_PRICE_OPTIONS,
        )

    def get_image(self, file_id: str) -> tuple:
        """Fetch image from Autohub API, returns (bytes, content_type)."""
        cache_key = self._make_cache_key("image", {"file_id": file_id})
        cached = self._get_from_cache(cache_key, ttl=86400)
        if cached:
            return cached

        self._ensure_authenticated()
        url = f"{self.api_base}/file/external/rest/api/v1/image/{file_id}"
        response = self.session.get(
            url,
            headers=self._get_auth_headers(),
            timeout=self.settings.request_timeout,
        )
        if response.status_code == 401:
            logger.warning("Got 401 on image fetch, re-authenticating...")
            if self._authenticate():
                response = self.session.get(
                    url,
                    headers=self._get_auth_headers(),
                    timeout=self.settings.request_timeout,
                )
        response.raise_for_status()

        content_type = response.headers.get("content-type", "image/jpeg")
        result = (response.content, content_type)
        self._save_to_cache(cache_key, result)
        return result

    def get_auth_status(self) -> Dict[str, Any]:
        """Check JWT token validity and auto-login status."""
        return {
            "has_token": self._jwt_token is not None,
            "is_valid": self._is_token_valid(),
            "auto_login_enabled": bool(self.settings.autohub_username and self.settings.autohub_password),
            "has_refresh_token": self._refresh_token is not None,
            "cache_stats": self._get_cache_stats(),
        }

    def close(self):
        """Cleanup resources."""
        if self._session:
            self._session.close()
            self._session = None


# Global service instance
autohub_service = AutohubService()
