import logging
import time
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.models.plc_auction import (
    PLCAuctionCar, PLCAuctionResponse, PLCAuctionFilters,
    PLCAuctionManufacturer, PLCAuctionModel, PLCAuctionCarDetail
)
from app.parsers.plc_auction_parser import PLCAuctionParser
from app.parsers.plc_auction_detail_parser import PLCAuctionDetailParser
from app.core.session_manager import SessionManager
from app.services.intercom_session import IntercomSession

logger = logging.getLogger(__name__)


class PLCAuctionService:
    BASE_URL = "https://plc.auction"
    AUCTION_URL = f"{BASE_URL}/auction"
    
    # Default cookies from the example (updated from working cars.py)
    DEFAULT_COOKIES = {
        "intercom-id-m1d5ih1o": "0f9a1bfc-debc-4985-9a2a-39a9de0f2eb6",
        "intercom-device-id-m1d5ih1o": "b6cba56c-2517-48c5-b1c0-93ff5d6a24fa",
        "_plc_ref": "eyJpdiI6Im90VTUyWlVMNFEzUE5pdi9XSlBCMEE9PSIsInZhbHVlIjoiT3pWbXAwemlJZjFJeVIyeC9na0tMWHJwWUlrV0pwQ1BERi9zdW5pbE9FUmVKYW1laDc3T1pOWWdmcEpVVWZJNXN5QUlmR0tzZHBTTDR5K3pXUjJLNlE9PSIsIm1hYyI6Ijk5YzU4M2I0NmNmZmJjNTBmNWYwMjdmNzllMTBkZWRmNzM5M2JhOTI5ZTZkMDBhYzhmY2Y1M2I4ZGIwYTIxYjQiLCJ0YWciOiIifQ%3D%3D",
        "_locale": "ru",
        "intercom-session-m1d5ih1o": "",
        "cf_clearance": "7podzPcziNpmU4.ig9_DCCrPVDukP2QFPzZ.lorCr9A-1753155652-1.2.1.1-i0XtZFYWWReCdw9i1nccqqHhW.3f3zVaXZJhDzDXqbF9hbMyKEZKFZivDlPig8j256JZ46Q_9IGWKAB_HfI6KbPRA0Jjheye_UwXUrUnZ9TwvDtgbXlUVzHsTdSapbrYmYNiq4a8yDwZs8aDyZnQzTb43HH8FTFeQxhqmplSUiBqIpA5NpyNVsR2pjTf5KVfg_cwgWmLoaU.R84fdxwiItIZOGhNRukJo_vYiBOo05I",
        "XSRF-TOKEN": "eyJpdiI6IjJOaU5rMnI3Zmk1U0w5U0NKR1FqQVE9PSIsInZhbHVlIjoieXVrLzRIUVMwcHdrSHc5d0VHVDI3QStreitUS1hIRWNMMlBhQ1Bab3BWK2VsZUVxSk5oYzRQdXcrbmNGNFhRUlZIak1XQ1pqMjJRajJaRWI2YzZ6N0w3eEJ5RXRJQms5d3JWSkM5T2t1d0VMY2RFckVqSXpuNVplTWdDV1o2N20iLCJtYWMiOiJlOTA0M2NmMmM4NjJjY2I4Mjc4OWE3ZjFiYTJjNzJiYWFjZmFhMGIwYjJjYzkzODQ5Yjg3MGRmOTdlNzI0MWQ0IiwidGFnIjoiIn0%3D",
        "__session": "eyJpdiI6Ik5iNFhOdlF6Z0hhTGJXR1l3RkxLZHc9PSIsInZhbHVlIjoibzRUWHRsV1EwekpGejlRZGFRYVpBRjkyc0VUdnl1d0xSWllDM3RzMGdxR3RGaGxoa2NFUUwxL1VZWEw0NEFrbHE5RDY2dXh6YkdhV2dVYWpXNFpNWnZNNTg3N1VFNjZuWTAvQkVqeThiK0RGMkJBZFduOWR0czJwNjVVZHl3UE0iLCJtYWMiOiI3NmQ5YTMyN2U4ODFhYmM1ZmU1YTVkYTZiMDFmNmU4OWY3NmEyMWU4NzIyM2E4ZGQ5YjFiMDk4YTAwNTdmY2I2IiwidGFnIjoiIn0%3D",
    }
    
    # Default headers from the working example (cars.py)
    DEFAULT_HEADERS = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
        "cache-control": "max-age=0",
        "priority": "u=0, i",
        "referer": "https://plc.auction/",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    }
    
    def __init__(self):
        self.session_manager = SessionManager()
        self.parser = PLCAuctionParser()
        self.headers = self.DEFAULT_HEADERS.copy()
        self.cookies = self.DEFAULT_COOKIES.copy()
        self.intercom = IntercomSession()
        self._setup_session()
        # Start Intercom ping loop
        self.intercom.start_ping_loop()
        # Initialize session with homepage visit
        self._initialize_browser_session()
    
    def _setup_session(self):
        """Setup requests session with retry strategy"""
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default headers
        self.session.headers.update(self.DEFAULT_HEADERS)
        
        # Load or set cookies
        saved_cookies = self.session_manager.load_session('plc_auction')
        if saved_cookies:
            self.session.cookies.update(saved_cookies)
            self.cookies.update(saved_cookies)
        else:
            self.session.cookies.update(self.DEFAULT_COOKIES)
            self.cookies.update(self.DEFAULT_COOKIES)
            
        # Add Intercom cookies
        intercom_cookies = self.intercom.get_intercom_cookies()
        self.session.cookies.update(intercom_cookies)
        self.cookies.update(intercom_cookies)
        
        # Set timeout for all requests
        self.session.timeout = 30
    
    def _save_cookies(self):
        """Save current session cookies"""
        cookies_dict = dict(self.session.cookies)
        self.session_manager.save_session('plc_auction', cookies_dict)
    
    def _initialize_browser_session(self):
        """Initialize session by visiting homepage like a real browser"""
        try:
            logger.info("🌐 Initializing browser-like session by visiting homepage")
            
            # First visit homepage to get initial cookies
            homepage_headers = {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "accept-language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
                "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "none",
                "sec-fetch-user": "?1",
                "upgrade-insecure-requests": "1",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            }
            
            # Visit homepage
            response = self.session.get(
                self.BASE_URL,
                headers=homepage_headers,
                allow_redirects=True,
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info("✅ Homepage visited successfully")
                # Update cookies from response
                self._save_cookies()
                
                # Send initial Intercom ping
                logger.info("🏓 Sending initial Intercom ping")
                ping_result = self.intercom.ping(referer=self.BASE_URL)
                if ping_result:
                    logger.info("✅ Initial Intercom ping successful")
                    # Update session cookie if returned
                    if 'anonymous_session' in ping_result:
                        session_cookie = ping_result.get('anonymous_session')
                        if session_cookie:
                            self.session.cookies.set('anonymous_session', session_cookie)
                            self.cookies['anonymous_session'] = session_cookie
                            self._save_cookies()
            else:
                logger.warning(f"⚠️ Homepage returned status {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Error initializing browser session: {e}")
    
    def fetch_cars(self, filters: PLCAuctionFilters) -> PLCAuctionResponse:
        """Fetch cars from PLC Auction with filters"""
        try:
            # Send Intercom ping before request
            self._ensure_intercom_session()
            
            # Build query parameters
            params = self._build_query_params(filters)
            
            # Make request
            response = self.session.get(
                self.AUCTION_URL,
                params=params,
                timeout=30
            )
            
            # Handle 403 errors by refreshing session
            if response.status_code == 403:
                logger.warning("⚠️ Got 403 error, attempting to refresh session")
                self.refresh_session()
                # Retry request with refreshed session
                response = self.session.get(
                    self.AUCTION_URL,
                    params=params,
                    timeout=30
                )
            
            response.raise_for_status()
            
            # Save cookies after successful request
            self._save_cookies()
            
            # Parse HTML response
            cars, total_count = self.parser.parse_cars_from_html(response.text)
            
            # Get pagination info
            pagination = self.parser.extract_pagination_info(
                response.text, filters.page, filters.page_size
            )
            
            # Build response
            return PLCAuctionResponse(
                success=True,
                message="Cars fetched successfully",
                total_count=pagination.get('total_count', total_count),
                cars=cars,
                current_page=filters.page,
                page_size=filters.page_size,
                has_next_page=pagination.get('has_next_page', False),
                has_prev_page=pagination.get('has_prev_page', False)
            )
            
        except requests.RequestException as e:
            logger.error(f"Request error fetching cars: {e}")
            return PLCAuctionResponse(
                success=False,
                message=f"Failed to fetch cars: {str(e)}",
                total_count=0,
                cars=[],
                current_page=filters.page,
                page_size=filters.page_size,
                has_next_page=False,
                has_prev_page=False
            )
        except Exception as e:
            logger.error(f"Unexpected error fetching cars: {e}")
            return PLCAuctionResponse(
                success=False,
                message=f"Unexpected error: {str(e)}",
                total_count=0,
                cars=[],
                current_page=filters.page,
                page_size=filters.page_size,
                has_next_page=False,
                has_prev_page=False
            )
    
    def _build_query_params(self, filters: PLCAuctionFilters) -> Dict[str, Any]:
        """Build query parameters from filters"""
        # Get current timestamp for date parameter
        import time
        current_timestamp = int(time.time())
        
        params = {
            "page": str(filters.page),  # Always include page as string
            "country": filters.country,
            "date": filters.date or str(current_timestamp),  # Use provided date or current timestamp
            "price_type": filters.price_type
        }
        
        # Add other filters if implemented
        # This would need to be extended based on how PLC Auction handles filters
        
        return params
    
    def _ensure_intercom_session(self):
        """Ensure Intercom session is active"""
        # Check if we need to ping (first time or been a while)
        if (not self.intercom.last_ping or 
            (datetime.now() - self.intercom.last_ping).seconds > 25):
            logger.info("🏓 Sending Intercom ping before request")
            ping_result = self.intercom.ping(referer=self.AUCTION_URL)
            if ping_result:
                # Update cookies with any new values from ping response
                if 'anonymous_session' in ping_result:
                    session_cookie = ping_result.get('anonymous_session')
                    if session_cookie:
                        self.session.cookies.set('anonymous_session', session_cookie)
                        self.cookies['anonymous_session'] = session_cookie
    
    def refresh_session(self):
        """Refresh the entire session when cookies expire"""
        try:
            logger.info("🔄 Refreshing PLC Auction session")
            
            # Clear existing cookies
            self.session.cookies.clear()
            
            # Re-initialize browser session
            self._initialize_browser_session()
            
            # Try to load fresh cookies from file if available
            import os
            cars_path = os.path.join(os.getcwd(), "Glovis", "cars.py")
            if os.path.exists(cars_path):
                logger.info("📄 Found cars.py, attempting to extract fresh cookies")
                self.update_cookies_from_curl(cars_path)
            else:
                logger.warning("⚠️ cars.py not found, using default cookies")
                self.session.cookies.update(self.DEFAULT_COOKIES)
                self.cookies.update(self.DEFAULT_COOKIES)
            
            # Save refreshed cookies
            self._save_cookies()
            logger.info("✅ Session refreshed successfully")
            
        except Exception as e:
            logger.error(f"❌ Error refreshing session: {e}")
    
    def update_cookies_from_curl(self, curl_file_path: str = "Glovis/cars.py") -> bool:
        """
        Update cookies from a curl file (like Glovis/cars.py)
        
        Args:
            curl_file_path: Path to the file containing fresh cookies
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            import ast
            import os
            
            # Read the curl file
            if not os.path.exists(curl_file_path):
                logger.error(f"Curl file not found: {curl_file_path}")
                return False
                
            with open(curl_file_path, 'r') as f:
                content = f.read()
            
            # Parse the Python file to extract cookies
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == 'cookies':
                            if isinstance(node.value, ast.Dict):
                                # Extract cookie values
                                new_cookies = {}
                                for key, value in zip(node.value.keys, node.value.values):
                                    if isinstance(key, ast.Constant) and isinstance(value, ast.Constant):
                                        new_cookies[key.value] = value.value
                                
                                # Update cookies
                                self.cookies.update(new_cookies)
                                # Update session cookies with proper domain/path
                                for name, value in new_cookies.items():
                                    self.session.cookies.set(name, value, domain=".plc.auction", path="/")
                                self._save_cookies()
                                
                                logger.info(f"✅ Successfully updated cookies from {curl_file_path}")
                                return True
            
            logger.error("Could not find cookies in the curl file")
            return False
            
        except Exception as e:
            logger.error(f"Error updating cookies from curl file: {e}")
            return False
    
    def get_manufacturers(self) -> Tuple[List[PLCAuctionManufacturer], bool]:
        """Get list of available manufacturers"""
        try:
            # For now, return a static list
            # In production, this would fetch from the API or parse from HTML
            manufacturers = [
                PLCAuctionManufacturer(code="HYUNDAI", name="Hyundai", count=500),
                PLCAuctionManufacturer(code="KIA", name="Kia", count=300),
                PLCAuctionManufacturer(code="GENESIS", name="Genesis", count=100),
                PLCAuctionManufacturer(code="CHEVROLET", name="Chevrolet", count=150),
                PLCAuctionManufacturer(code="SSANGYONG", name="SsangYong", count=50),
            ]
            
            return manufacturers, True
            
        except Exception as e:
            logger.error(f"Error getting manufacturers: {e}")
            return [], False
    
    def get_models(self, manufacturer_code: str) -> Tuple[List[PLCAuctionModel], bool]:
        """Get list of models for a manufacturer"""
        try:
            # For now, return a static list based on manufacturer
            # In production, this would fetch from the API or parse from HTML
            models_map = {
                "HYUNDAI": [
                    PLCAuctionModel(code="SANTA_FE", name="Santa Fe", manufacturer_code="HYUNDAI", count=100),
                    PLCAuctionModel(code="TUCSON", name="Tucson", manufacturer_code="HYUNDAI", count=80),
                    PLCAuctionModel(code="PALISADE", name="Palisade", manufacturer_code="HYUNDAI", count=60),
                ],
                "KIA": [
                    PLCAuctionModel(code="SPORTAGE", name="Sportage", manufacturer_code="KIA", count=90),
                    PLCAuctionModel(code="SORENTO", name="Sorento", manufacturer_code="KIA", count=70),
                    PLCAuctionModel(code="CARNIVAL", name="Carnival", manufacturer_code="KIA", count=50),
                ],
            }
            
            models = models_map.get(manufacturer_code.upper(), [])
            return models, True
            
        except Exception as e:
            logger.error(f"Error getting models for {manufacturer_code}: {e}")
            return [], False
    
    def search_cars(self, filters: PLCAuctionFilters) -> PLCAuctionResponse:
        """Search cars with advanced filters"""
        # For now, just use the fetch_cars method
        # In production, this might use a different endpoint or add more filters
        return self.fetch_cars(filters)
    
    def get_car_detail(self, slug: str) -> Optional[PLCAuctionCarDetail]:
        """
        Get detailed information about a specific car
        
        Args:
            slug: The car slug from the URL (e.g., "hyundai-santa-fe-2023-kmhs281lgpu493682-25-7112c3769debd7a350b2a5a26e36d3ff")
            
        Returns:
            PLCAuctionCarDetail or None if not found
        """
        try:
            detail_url = f"{self.BASE_URL}/auction/lot/{slug}"
            logger.info(f"Fetching car detail from: {detail_url}")
            
            # Send Intercom ping before request
            self._ensure_intercom_session()
            
            # Update headers with referrer
            headers = self.headers.copy()
            headers['referer'] = self.AUCTION_URL
            
            # Make request
            response = self.session.get(
                detail_url,
                headers=headers,
                cookies=self.cookies,
                timeout=30
            )
            
            # Handle 403 errors by refreshing session
            if response.status_code == 403:
                logger.warning("⚠️ Got 403 error on car detail, attempting to refresh session")
                self.refresh_session()
                # Retry request with refreshed session
                response = self.session.get(
                    detail_url,
                    headers=headers,
                    cookies=self.cookies,
                    timeout=30
                )
            
            if response.status_code == 200:
                # Parse the HTML with our detail parser
                parser = PLCAuctionDetailParser()
                car_detail = parser.parse_car_detail(response.text, detail_url)
                
                if car_detail:
                    logger.info(f"✅ Successfully fetched detail for VIN: {car_detail.vin}")
                    return car_detail
                else:
                    logger.error("Failed to parse car detail from HTML")
                    return None
            else:
                logger.error(f"Failed to fetch car detail. Status: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error fetching car detail: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching car detail: {e}")
            return None