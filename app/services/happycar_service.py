import hashlib
import json
import time
import urllib3
from typing import Optional, Dict, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from loguru import logger

from app.models.happycar import (
    HappyCarListItem, HappyCarDetail, HappyCarModelCategory,
    HappyCarResponse, HappyCarDetailResponse,
)
from app.parsers.happycar_parser import HappyCarParser
from app.core.config import get_settings

# Suppress InsecureRequestWarning for verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

settings = get_settings()


class HappyCarService:
    """Service for scraping HappyCar insurance auction website.

    Handles authentication, session management, caching, and data fetching.
    """

    BASE_URL = "https://www.happycarservice.com"
    LOGIN_URL = f"{BASE_URL}/member/login.ajax.html"
    LIST_AJAX_URL = f"{BASE_URL}/content/auction_ins.ajax.html"
    DETAIL_URL = f"{BASE_URL}/content/ins_view.html"

    PROXY_URL = "http://bp-bfk2u7wtb3gy_area-KR:zwj1SkzW69P1nhUs@proxy.bestproxy.com:2312"

    DEFAULT_HEADERS = {
        "Accept": "text/html, */*; q=0.01",
        "Accept-Language": "en,ru;q=0.9,ko;q=0.5",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://www.happycarservice.com",
        "Referer": "https://www.happycarservice.com/content/auction_ins.html",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/138.0.0.0 Safari/537.36"
        ),
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

    def __init__(self):
        self.parser = HappyCarParser()
        self.session = self._create_session()
        self._authenticated = False

        # Cached model categories (parsed from full page, not available in AJAX)
        self._model_categories = []

        # In-memory cache with tiered TTL
        self._cache: Dict[str, tuple] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def _create_session(self) -> requests.Session:
        """Create a requests.Session with retry logic, proxy, and SSL workaround."""
        session = requests.Session()

        # Retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=10,
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Default headers
        session.headers.update(self.DEFAULT_HEADERS)

        # Proxy
        session.proxies = {
            "http": self.PROXY_URL,
            "https": self.PROXY_URL,
        }

        # SSL verification disabled (required for some Korean sites behind proxies)
        session.verify = False

        return session

    # ─── Authentication ───────────────────────────────────────────────

    def _authenticate(self):
        """Login to HappyCar to get a valid PHPSESSID."""
        try:
            logger.info("🔐 Authenticating with HappyCar...")

            # Step 1: GET the main page to pick up initial cookies
            main_resp = self.session.get(
                f"{self.BASE_URL}/content/auction_ins.html",
                timeout=15,
            )
            main_resp.raise_for_status()
            logger.info(f"📄 Got main page, status={main_resp.status_code}")

            # Parse model categories from the full page (not available in AJAX responses)
            _, _, model_cats = self.parser.parse_car_list(main_resp.text)
            if model_cats:
                self._model_categories = model_cats
                logger.info(f"📋 Parsed {len(model_cats)} model categories from full page")

            # Step 2: POST login credentials
            login_data = {
                "member_id": settings.happycar_username,
                "member_pwd": settings.happycar_password,
            }
            login_resp = self.session.post(
                self.LOGIN_URL,
                data=login_data,
                timeout=15,
                allow_redirects=True,
            )
            login_resp.raise_for_status()

            # Check for successful login (redirect back or success indicator)
            if login_resp.status_code in (200, 302) or 'logout' in login_resp.text.lower():
                self._authenticated = True
                logger.info("✅ HappyCar authentication successful")
            else:
                logger.warning(f"⚠️ HappyCar login response unclear: {login_resp.status_code}")
                # Still set authenticated to try — session cookies might work
                self._authenticated = True

        except requests.RequestException as e:
            logger.error(f"❌ HappyCar authentication failed: {e}")
            self._authenticated = False
        except Exception as e:
            logger.error(f"❌ Unexpected error during HappyCar auth: {e}")
            self._authenticated = False

    def _ensure_authenticated(self):
        """Ensure we have a valid session, re-authenticate if needed."""
        if not self._authenticated:
            self._authenticate()

    # ─── Caching ──────────────────────────────────────────────────────

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
            return f"happycar:{prefix}:{param_hash}"
        return f"happycar:{prefix}"

    def _get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0
        return {
            "service": "HappyCar",
            "cache_entries": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate_percent": round(hit_rate, 2),
        }

    # ─── Data Fetching ────────────────────────────────────────────────

    def fetch_cars(
        self,
        page: int = 1,
        page_size: int = 12,
        sale_type: str = "",
        model_filter: str = "",
        year_start: str = "",
        month_start: str = "",
        year_end: str = "",
        month_end: str = "",
        region: str = "",
        search_type: str = "",
        search_text: str = "",
    ) -> HappyCarResponse:
        """Fetch car listings from the HappyCar AJAX endpoint."""
        try:
            self._ensure_authenticated()

            # Check cache (180s TTL for listings)
            cache_params = {
                "page": page, "page_size": page_size, "sale_type": sale_type,
                "model_filter": model_filter, "year_start": year_start,
                "month_start": month_start, "year_end": year_end,
                "month_end": month_end, "region": region,
                "search_type": search_type, "search_text": search_text,
            }
            cache_key = self._make_cache_key("cars", cache_params)
            cached = self._get_from_cache(cache_key, ttl=180)
            if cached is not None:
                logger.debug("📦 HappyCar cars cache hit")
                return cached

            # Map Korean sale type labels to numeric codes used by the website
            SALE_TYPE_CODES = {
                "구제": "2",
                "폐차": "1",
                "부품": "3",
            }
            au_gubun = SALE_TYPE_CODES.get(sale_type, sale_type)

            # Build POST form data matching the website's AJAX request
            data = {
                "code": "",
                "mode": "list",
                "page": str(page),
                "pageSize0": "",
                "gallerySel": "",
                "sOrder": "",
                "sOrderArrow": "",
                "au_gubun": au_gubun,
                "search_name_text": model_filter,
                "au_gubun_chk": au_gubun,
                "start_auregModelY": year_start,
                "start_auregModelM": month_start,
                "end_auregModelY": year_end,
                "end_auregModelM": month_end,
                "au_keepArea": region,
                "f_gbn": search_type,
                "f_text": search_text,
                "ajaxYn": "Y",
            }

            logger.info(f"🚗 Fetching HappyCar cars: page={page}, sale_type={sale_type}, model={model_filter}")

            response = self.session.post(
                self.LIST_AJAX_URL,
                data=data,
                timeout=20,
            )
            response.raise_for_status()

            # Parse HTML
            cars, total_count, model_categories = self.parser.parse_car_list(response.text)

            # Update cached model categories when AJAX returns them (sale-type specific)
            if model_categories:
                self._model_categories = model_categories
            elif self._model_categories:
                # Fall back to cached categories only when AJAX didn't include any
                model_categories = self._model_categories

            result = HappyCarResponse(
                success=True,
                data=cars,
                total_count=total_count,
                page=page,
                page_size=page_size,
                model_categories=model_categories,
                message=f"Fetched {len(cars)} cars (total: {total_count})",
            )

            self._save_to_cache(cache_key, result)
            logger.info(f"✅ HappyCar: fetched {len(cars)} cars, total={total_count}")
            return result

        except requests.RequestException as e:
            logger.error(f"❌ Request error fetching HappyCar cars: {e}")
            return HappyCarResponse(
                success=False,
                message=f"Failed to fetch cars: {str(e)}",
            )
        except Exception as e:
            logger.error(f"❌ Unexpected error fetching HappyCar cars: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return HappyCarResponse(
                success=False,
                message=f"Unexpected error: {str(e)}",
            )

    def fetch_car_detail(self, idx: str) -> HappyCarDetailResponse:
        """Fetch detailed info for a single car by idx."""
        try:
            self._ensure_authenticated()

            # Check cache (1800s TTL for details)
            cache_key = self._make_cache_key("detail", {"idx": idx})
            cached = self._get_from_cache(cache_key, ttl=1800)
            if cached is not None:
                logger.debug(f"📦 HappyCar detail cache hit: {idx}")
                return cached

            url = f"{self.DETAIL_URL}?idx={idx}"
            logger.info(f"📄 Fetching HappyCar car detail: {url}")

            response = self.session.get(url, timeout=20)
            response.raise_for_status()

            # Detail page uses EUC-KR encoding
            response.encoding = "euc-kr"
            detail = self.parser.parse_car_detail(response.text)

            if not detail:
                logger.error(f"❌ Failed to parse car detail for idx={idx}")
                return HappyCarDetailResponse(
                    success=False,
                    message=f"Failed to parse car detail for idx={idx}",
                )

            # Ensure idx is set
            if not detail.idx:
                detail.idx = idx

            result = HappyCarDetailResponse(
                success=True,
                data=detail,
                message="Car detail retrieved successfully",
            )

            self._save_to_cache(cache_key, result)
            logger.info(f"✅ HappyCar: retrieved detail for idx={idx}")
            return result

        except requests.RequestException as e:
            logger.error(f"❌ Request error fetching HappyCar detail: {e}")
            return HappyCarDetailResponse(
                success=False,
                message=f"Failed to fetch car detail: {str(e)}",
            )
        except Exception as e:
            logger.error(f"❌ Unexpected error fetching HappyCar detail: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return HappyCarDetailResponse(
                success=False,
                message=f"Unexpected error: {str(e)}",
            )
