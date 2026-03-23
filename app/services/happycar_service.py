import hashlib
import json
import random
import re
import string
import threading
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
    LIST_PAGE_URL = f"{BASE_URL}/content/auction_ins.html"
    LIST_AJAX_URL = f"{BASE_URL}/content/auction_ins.ajax.html"
    DETAIL_URL = f"{BASE_URL}/content/ins_view.html"
    LOGOUT_URL = f"{BASE_URL}/member/logout.ajax.html"

    PROXY_URL = "http://bp-bfk2u7wtb3gy_area-KR_life-60_session-EoitGYdhe:zwj1SkzW69P1nhUs@proxy.bestproxy.com:2312"

    _PROXY_LIFETIME: int = 3600     # 60 min — matches life-60 parameter
    _PROXY_SAFETY_MARGIN: int = 300 # 5 min buffer before proxy rotation

    # Session-level headers — common to ALL requests
    BASE_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/138.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en,ru;q=0.9,ko;q=0.5",
        "Sec-Fetch-Site": "same-origin",
    }

    # Per-request headers for AJAX/POST calls
    AJAX_HEADERS = {
        "Accept": "text/html, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://www.happycarservice.com",
        "Referer": "https://www.happycarservice.com/content/auction_ins.html",
        "X-Requested-With": "XMLHttpRequest",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
    }

    # Per-request headers for full-page GET navigation
    BROWSER_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Upgrade-Insecure-Requests": "1",
    }

    _LOGIN_REDIRECT_RE = re.compile(
        r"""location\.href\s*=\s*['"][^'"]*login\.html""",
        re.IGNORECASE,
    )

    def __init__(self):
        self.parser = HappyCarParser()
        self.session = self._create_session()
        self._authenticated = False
        self._auth_lock = threading.Lock()
        self._auth_timestamp: float = 0.0
        self._SESSION_TTL: int = 1500  # 25 min (5-min buffer before PHP's ~30-min expiry)

        # Cached model categories (parsed from full page, not available in AJAX)
        self._model_categories = []

        # Proxy session tracking (sticky IP lifetime)
        self._proxy_session_start: float = time.time()
        self._current_proxy_ip: Optional[str] = None

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
        session.headers.update(self.BASE_HEADERS)

        # Proxy
        session.proxies = {
            "http": self.PROXY_URL,
            "https": self.PROXY_URL,
        }

        # SSL verification disabled (required for some Korean sites behind proxies)
        session.verify = False

        return session

    # ─── Diagnostics ──────────────────────────────────────────────────

    def _log_cookies(self, label: str) -> None:
        """Log cookie count, names+domains, and PHPSESSID presence."""
        cookies = self.session.cookies
        cookie_names = [f"{c.name}@{c.domain}" for c in cookies]
        has_phpsessid = any(c.name == "PHPSESSID" for c in cookies)
        logger.info(
            f"[HappyCar cookies] {label}: count={len(cookie_names)}, "
            f"PHPSESSID={'YES' if has_phpsessid else 'NO'}, names={cookie_names}"
        )

    def _log_proxy_ip(self, label: str = "check") -> Optional[str]:
        """One-shot GET to httpbin.org/ip through proxy to verify outgoing IP."""
        try:
            resp = self.session.get("https://httpbin.org/ip", timeout=10)
            ip = resp.json().get("origin", "unknown")
            self._current_proxy_ip = ip
            logger.info(f"[HappyCar proxy] {label}: Outgoing IP = {ip}")
            return ip
        except Exception as e:
            logger.warning(f"[HappyCar proxy] {label}: IP check failed: {e}")
            return None

    def _is_login_redirect(self, html: str) -> bool:
        """Detect a genuine JS-based login redirect page.

        Real redirects are tiny script-only pages (<2KB) with a JS assignment
        like: location.href = '/member/login.html';
        Valid detail pages are 10KB+ and may incidentally contain both
        'login.html' and 'location.href', which causes false positives
        with simple substring checks.
        """
        if len(html) > 2000:
            return False
        return bool(self._LOGIN_REDIRECT_RE.search(html))

    def _is_proxy_session_expiring(self) -> bool:
        """Return True when within safety margin of the proxy's sticky-IP lifetime."""
        elapsed = time.time() - self._proxy_session_start
        expiring = elapsed >= (self._PROXY_LIFETIME - self._PROXY_SAFETY_MARGIN)
        if expiring:
            logger.info(f"[HappyCar proxy] Session expiring: {elapsed:.0f}s elapsed (limit {self._PROXY_LIFETIME}s)")
        return expiring

    def _reset_proxy_session(self) -> None:
        """Generate a new proxy session ID to get a fresh sticky IP.

        Must be called inside self._auth_lock.
        """
        new_id = "".join(random.choices(string.ascii_letters + string.digits, k=9))
        self.PROXY_URL = (
            f"http://bp-bfk2u7wtb3gy_area-KR_life-60_session-{new_id}"
            f":zwj1SkzW69P1nhUs@proxy.bestproxy.com:2312"
        )
        self._proxy_session_start = time.time()
        self._current_proxy_ip = None
        self._authenticated = False
        self.session = self._create_session()
        logger.info(f"[HappyCar proxy] Reset proxy session: session-{new_id}")

    def _rotate_to_new_ip(self, max_attempts: int = 5) -> bool:
        """Rotate proxy until we get a genuinely different IP.

        Calls _reset_proxy_session() up to max_attempts times,
        checking the outgoing IP via httpbin after each rotation.
        Must be called inside self._auth_lock.

        Returns True if IP changed, False if exhausted attempts.
        """
        old_ip = self._current_proxy_ip
        for attempt in range(1, max_attempts + 1):
            self._reset_proxy_session()
            new_ip = self._log_proxy_ip(f"rotation attempt {attempt}/{max_attempts}")

            if new_ip is None:
                # httpbin check failed — can't verify, proceed anyway
                logger.warning(f"[HappyCar proxy] IP check failed on attempt {attempt}, proceeding without verification")
                return True

            if old_ip is None or new_ip != old_ip:
                logger.info(f"[HappyCar proxy] IP changed: {old_ip} -> {new_ip}")
                return True

            logger.warning(f"[HappyCar proxy] Attempt {attempt}: still same IP {new_ip}, retrying...")
            time.sleep(1)  # Brief pause before next rotation attempt

        logger.error(f"[HappyCar proxy] Failed to get new IP after {max_attempts} attempts (stuck on {old_ip})")
        return False

    def _logout(self) -> None:
        """Terminate the current server-side session via LOGOUT_URL.

        Called BEFORE creating a new session so the server releases the
        IP-bound login slot. Uses the current session's PHPSESSID cookie.
        """
        try:
            resp = self.session.get(self.LOGOUT_URL, headers=self.BROWSER_HEADERS, timeout=10)
            logger.info(f"[HappyCar] Logout: status={resp.status_code}")
        except Exception as e:
            logger.warning(f"[HappyCar] Logout failed (non-critical): {e}")
        finally:
            self._authenticated = False

    # ─── Authentication ───────────────────────────────────────────────

    def _warm_up_list_context(self) -> None:
        """Establish server-side navigation state required by the detail page.

        The HappyCar server tracks navigation in $_SESSION. The detail page
        (ins_view.html) checks that the session previously performed an
        authenticated full-page GET of the list page (auction_ins.html).
        Without this, the server sees a deep-link and redirects to login.

        Step 1: Full-page GET of the list page (sets $_SESSION navigation flag)
        Step 2: AJAX POST to the list endpoint (secondary warm-up)
        """
        # Step 1: Full-page GET — this is the critical step
        try:
            resp = self.session.get(
                self.LIST_PAGE_URL,
                headers=self.BROWSER_HEADERS,
                timeout=15,
            )
            logger.info(f"[HappyCar] List page visit: status={resp.status_code}, length={len(resp.text)}")
            self._log_cookies("after list page visit")

            # Parse model categories from the authenticated full page
            if self._is_login_redirect(resp.text):
                logger.warning("[HappyCar] List page visit returned login redirect — session may not be fully established")
            else:
                _, _, model_cats = self.parser.parse_car_list(resp.text)
                if model_cats:
                    self._model_categories = model_cats
                    logger.info(f"[HappyCar] Parsed {len(model_cats)} model categories from authenticated list page")
        except Exception as e:
            logger.warning(f"[HappyCar] List page visit failed (non-critical): {e}")

        # Step 2: AJAX POST — secondary warm-up
        try:
            data = {
                "code": "", "mode": "list", "page": "1", "pageSize0": "",
                "gallerySel": "", "sOrder": "", "sOrderArrow": "",
                "au_gubun": "", "search_name_text": "", "au_gubun_chk": "",
                "start_auregModelY": "", "start_auregModelM": "",
                "end_auregModelY": "", "end_auregModelM": "",
                "au_keepArea": "", "f_gbn": "", "f_text": "", "ajaxYn": "Y",
            }
            resp = self.session.post(
                self.LIST_AJAX_URL, data=data,
                headers=self.AJAX_HEADERS, timeout=15,
            )
            logger.info(f"[HappyCar] List AJAX warm-up: status={resp.status_code}, length={len(resp.text)}")
            self._log_cookies("after list AJAX warm-up")
        except Exception as e:
            logger.warning(f"[HappyCar] List AJAX warm-up failed (non-critical): {e}")

    def _authenticate(self) -> bool:
        """Login to HappyCar to get a valid PHPSESSID."""
        try:
            logger.info("Authenticating with HappyCar...")

            # Step 1: GET the main page to pick up initial cookies (PHPSESSID)
            # NOTE: This returns a login redirect page (unauthenticated).
            # Model categories are parsed later from the authenticated list page
            # in _warm_up_list_context().
            main_resp = self.session.get(
                self.LIST_PAGE_URL,
                headers=self.BROWSER_HEADERS,
                timeout=15,
            )
            main_resp.raise_for_status()
            logger.info(f"Got main page (pre-login), status={main_resp.status_code}")

            # Step 2: POST login credentials
            login_data = {
                "member_id": settings.happycar_username,
                "member_pwd": settings.happycar_password,
            }
            login_resp = self.session.post(
                self.LOGIN_URL,
                data=login_data,
                headers=self.AJAX_HEADERS,
                timeout=15,
                allow_redirects=True,
            )
            login_resp.raise_for_status()

            # Parse JSON response — HappyCar returns {"rst_code": 1, "rst_msg": ""} on success
            raw = login_resp.text.strip()
            try:
                resp_json = json.loads(raw)
                rst_code = resp_json.get("rst_code")

                if rst_code == 1:
                    self._authenticated = True
                    self._auth_timestamp = time.time()
                    logger.info(f"HappyCar authentication successful (rst_code={rst_code})")
                    self._log_cookies("after login")
                    self._warm_up_list_context()
                    self._log_proxy_ip("after auth")
                    return True
                elif rst_code == -6:
                    # Can't logout old session (don't have its PHPSESSID).
                    # Rotate proxy to get a fresh IP with no existing sessions.
                    logger.warning("HappyCar rst_code=-6: IP collision. Rotating proxy...")
                    self._rotate_to_new_ip()

                    # Re-GET main page on new IP to pick up PHPSESSID cookie
                    main_resp = self.session.get(
                        self.LIST_PAGE_URL,
                        headers=self.BROWSER_HEADERS, timeout=15,
                    )

                    # Retry login on new IP
                    retry_resp = self.session.post(
                        self.LOGIN_URL, data=login_data,
                        headers=self.AJAX_HEADERS, timeout=15, allow_redirects=True,
                    )
                    retry_resp.raise_for_status()
                    retry_json = json.loads(retry_resp.text.strip())
                    retry_code = retry_json.get("rst_code")

                    if retry_code == 1:
                        self._authenticated = True
                        self._auth_timestamp = time.time()
                        logger.info("HappyCar auth successful after proxy rotation")
                        self._log_cookies("after login (proxy rotation)")
                        self._warm_up_list_context()
                        self._log_proxy_ip("after auth (proxy rotation)")
                        return True
                    else:
                        self._authenticated = False
                        logger.error(f"HappyCar login failed after proxy rotation: rst_code={retry_code}")
                        return False
                else:
                    rst_msg = resp_json.get("rst_msg", "")
                    self._authenticated = False
                    logger.error(f"HappyCar login failed: rst_code={rst_code}, rst_msg={rst_msg}")
                    return False

            except (json.JSONDecodeError, ValueError):
                # Fallback: non-JSON response — check text heuristics
                response_text = raw.lower()
                if '"result":"y"' in response_text or '"result": "y"' in response_text or "success" in response_text:
                    self._authenticated = True
                    self._auth_timestamp = time.time()
                    logger.info("HappyCar authentication successful (text fallback)")
                    self._warm_up_list_context()
                    return True
                elif "logout" in response_text:
                    self._authenticated = True
                    self._auth_timestamp = time.time()
                    logger.info("HappyCar already authenticated (logout link found)")
                    self._warm_up_list_context()
                    return True
                else:
                    self._authenticated = False
                    logger.error(f"HappyCar login failed, response: {raw[:200]}")
                    return False

        except requests.RequestException as e:
            logger.error(f"HappyCar authentication failed: {e}")
            self._authenticated = False
            return False
        except Exception as e:
            logger.error(f"Unexpected error during HappyCar auth: {e}")
            self._authenticated = False
            return False

    def _ensure_authenticated(self):
        """Ensure we have a valid session, re-authenticate if needed (thread-safe)."""
        if self._authenticated:
            elapsed = time.time() - self._auth_timestamp
            if elapsed < self._SESSION_TTL and not self._is_proxy_session_expiring():
                return

        with self._auth_lock:
            # Re-check inside lock (another thread may have already refreshed)
            if self._authenticated:
                elapsed = time.time() - self._auth_timestamp
                if elapsed < self._SESSION_TTL and not self._is_proxy_session_expiring():
                    return

            if self._is_proxy_session_expiring():
                logger.info("[HappyCar] Proxy session expiring, rotating...")
                self._logout()
                self._rotate_to_new_ip()
            else:
                logger.info("[HappyCar] Session expired or not authenticated, refreshing...")
                self._logout()
                self.session = self._create_session()

            if not self._authenticate():
                # Last resort: rotate proxy and try once more
                logger.warning("Auth failed, attempting proxy rotation as last resort...")
                self._rotate_to_new_ip()
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
                headers=self.AJAX_HEADERS,
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

            detail_headers = {
                **self.BROWSER_HEADERS,
                "Referer": f"{self.BASE_URL}/content/auction_ins.html",
            }
            response = self.session.get(url, headers=detail_headers, timeout=20)
            response.raise_for_status()

            # Detail page uses EUC-KR encoding
            response.encoding = "euc-kr"
            html = response.text
            logger.debug(
                f"[HappyCar] Detail response: idx={idx}, length={len(html)}, "
                f"head={html[:500]!r}"
            )

            # Detect login redirect — page requires auth but session expired
            if self._is_login_redirect(html):
                logger.warning(f"HappyCar detail page returned login redirect for idx={idx}")
                self._log_cookies("before re-auth (detail redirect)")
                self._log_proxy_ip("detail redirect")

                with self._auth_lock:
                    self._logout()
                    self._rotate_to_new_ip()
                    if not self._authenticate():
                        logger.error("HappyCar: re-auth failed after proxy rotation")
                        return HappyCarDetailResponse(
                            success=False,
                            message="Authentication failed after proxy rotation",
                        )

                self._log_cookies("after re-auth")

                # Retry once with fresh session
                response = self.session.get(url, headers=detail_headers, timeout=20)
                response.raise_for_status()
                response.encoding = "euc-kr"
                html = response.text
                logger.debug(
                    f"[HappyCar] Detail response (retry): idx={idx}, length={len(html)}, "
                    f"head={html[:500]!r}"
                )

                if self._is_login_redirect(html):
                    logger.error(f"HappyCar: still redirected to login after re-auth for idx={idx}")
                    self._log_cookies("STILL FAILING after re-auth")
                    return HappyCarDetailResponse(
                        success=False,
                        message="Authentication failed — cannot access detail page",
                    )

            detail = self.parser.parse_car_detail(html)

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
