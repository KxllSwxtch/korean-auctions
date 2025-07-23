import logging
import time
import random
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import cloudscraper

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
    
    # Default cookies from the working cars.py example
    DEFAULT_COOKIES = {
        "intercom-id-m1d5ih1o": "0f9a1bfc-debc-4985-9a2a-39a9de0f2eb6",
        "intercom-device-id-m1d5ih1o": "b6cba56c-2517-48c5-b1c0-93ff5d6a24fa",
        "_plc_ref": "eyJpdiI6Im90VTUyWlVMNFEzUE5pdi9XSlBCMEE9PSIsInZhbHVlIjoiT3pWbXAwemlJZjFJeVIyeC9na0tMWHJwWUlrV0pwQ1BERi9zdW5pbE9FUmVKYW1laDc3T1pOWWdmcEpVVWZJNXN5QUlmR0tzZHBTTDR5K3pXUjJLNlE9PSIsIm1hYyI6Ijk5YzU4M2I0NmNmZmJjNTBmNWYwMjdmNzllMTBkZWRmNzM5M2JhOTI5ZTZkMDBhYzhmY2Y1M2I4ZGIwYTIxYjQiLCJ0YWciOiIifQ%3D%3D",
        "_locale": "ru",
        "intercom-session-m1d5ih1o": "",
        "cf_clearance": "4eiWor1neELyote2XWvOrh0PpfULqeuVjtfzzsrC_Qs-1753259372-1.2.1.1-4HmD7L3Db_8cGxL0PbIhA36DK5XnestDU9GqoMfoktged1BQou.4AiMZb66SvS3nxdmYwaIotcgXCCafYDvC4C5cN_8xDT0l0CjPg6DfzBti_QgT58SUyf02in37WCrTzZWvTPc2PSdHYu6t05q4AZalU65K5.BDZ.G1R_Ep2gLkuvRFqzqkWp7g3GAQeQskEuz3Iq2TrEXfyqkoSj1RcnYBAxcl0PAJYFbJToWn3Hs",
        "XSRF-TOKEN": "eyJpdiI6IkxsMEJMZFVWNWlRSnZmcmJhRmVKdHc9PSIsInZhbHVlIjoiSWRhM1RFKzMrcUF6bzdJbEZ4SkZETmZEUXp3THRvbGZFWXFnVGJZcUZ3YWFsck1CRDBMUkFNTzVjQ1lTaEplOWYxa3M0WmJQVEl1ZzF1OXp6aW9sZ2VJQU53TCtDaEFrTjF5N3JnaUF5OVpqZDFxU25wMHlxRTJKemxqdjVkVUUiLCJtYWMiOiIxNmU4ZDI4YzFiODM4M2MyNTEyMmRhMDhlYjVmZjJhZjgxMjg5ZWEzMTYzMzhlNGEzMjI5OTkzY2Q1NzFlNDgwIiwidGFnIjoiIn0%3D",
        "__session": "eyJpdiI6IjZ6SFl3YVBVWGJCVXVJRXREeEFSRGc9PSIsInZhbHVlIjoiOVFiaHdia2U2azhIUnk5N3V6ZVVhOWUvaUZlZUxDSFVBYmVvVUl2SFdOWFg5SlRQVldRbWdEZ1VIaDBFWXhLUzcxVHFxaS8veVVBYmM2Y0VlZ1JsamhidEFtclBuQjJIcUxNbjhCY1dabGd0MStIT3hjWWpub3NNbkE0L2ovYTEiLCJtYWMiOiJiOTI4NzhmYTMwNzUxYzEzY2M2YjExMjUxNTM1MGYwZDM4NWM3ODJmNDNlZWFjNDQ5ZjAzOTUzMjdiZjIzNzJlIiwidGFnIjoiIn0%3D",
    }
    
    # Default headers from the working cars.py example  
    DEFAULT_HEADERS = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
        "content-type": "application/json",
        "origin": "https://plc.auction",
        "priority": "u=1, i",
        "referer": "https://plc.auction/auction?country=kr&date=1753304400&price_type=auction",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "x-requested-with": "XMLHttpRequest",
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
        """Setup cloudscraper session to handle Cloudflare challenges"""
        # Create cloudscraper session with updated configuration
        self.session = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'darwin',
                'desktop': True,
                'mobile': False,
                'custom': f'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(138, 142)}.0.0.0 Safari/537.36'
            },
            delay=3,  # Increased delay to avoid rate limiting
            debug=False,
            interpreter='nodejs'  # Use nodejs interpreter for better challenge solving
        )
        
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
            for name, value in saved_cookies.items():
                if value:  # Skip empty values
                    self.session.cookies.set(name, value)
            self.cookies.update(saved_cookies)
        else:
            for name, value in self.DEFAULT_COOKIES.items():
                if value:  # Skip empty values
                    self.session.cookies.set(name, value)
            self.cookies.update(self.DEFAULT_COOKIES)
            
        # Add Intercom cookies
        intercom_cookies = self.intercom.get_intercom_cookies()
        for name, value in intercom_cookies.items():
            if value:  # Skip empty values
                self.session.cookies.set(name, value)
        self.cookies.update(intercom_cookies)
        
        # Set timeout for all requests
        self.session.timeout = 30
    
    def _save_cookies(self):
        """Save current session cookies"""
        cookies_dict = dict(self.session.cookies)
        self.session_manager.save_session('plc_auction', cookies_dict)
    
    def _apply_default_cookies(self):
        """Apply default cookies to session"""
        for name, value in self.DEFAULT_COOKIES.items():
            if value:  # Skip empty values
                self.session.cookies.set(name, value, domain=".plc.auction", path="/")
        self.cookies.update(self.DEFAULT_COOKIES)
    
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
        """Fetch cars from PLC Auction with filters using POST request"""
        try:
            # Validate cookies before making request
            if not self._validate_cookies():
                logger.warning("⚠️ Invalid cookies detected, refreshing session...")
                self.refresh_session()
            
            # Send Intercom ping before request
            self._ensure_intercom_session()
            
            # Build JSON data for POST request
            json_data = self._build_json_data(filters)
            
            # Update headers for POST request
            headers = self.DEFAULT_HEADERS.copy()
            headers["x-xsrf-token"] = self.cookies.get("XSRF-TOKEN", "")
            
            # Add small delay to avoid rate limiting
            time.sleep(1)
            
            # Make POST request to the API endpoint
            response = self.session.post(
                f"{self.BASE_URL}/auction/request",
                json=json_data,
                headers=headers,
                cookies=self.cookies,
                timeout=30
            )
            
            # Handle 403 errors with improved retry logic
            if response.status_code == 403:
                logger.warning("⚠️ Got 403 error, attempting to refresh session")
                
                # First attempt: Clear cookies and try with fresh session
                logger.info("🔄 Attempt 1: Clearing cookies and retrying...")
                self.session.cookies.clear()
                self._apply_default_cookies()
                time.sleep(2)
                
                response = self.session.post(
                    f"{self.BASE_URL}/auction/request",
                    json=json_data,
                    headers=headers,
                    cookies=self.cookies,
                    timeout=30
                )
                
                # Second attempt: Try to refresh cookies from cars.py
                if response.status_code == 403:
                    logger.info("🔄 Attempt 2: Loading fresh cookies from cars.py...")
                    import os
                    cars_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "Glovis", "cars.py")
                    if self.update_cookies_from_curl(cars_path):
                        logger.info("✅ Updated cookies from cars.py, retrying...")
                        # Update headers with new XSRF token
                        headers["x-xsrf-token"] = self.cookies.get("XSRF-TOKEN", "")
                        time.sleep(2)
                        response = self.session.post(
                            f"{self.BASE_URL}/auction/request",
                            json=json_data,
                            headers=headers,
                            cookies=self.cookies,
                            timeout=30
                        )
                
                # Third attempt: Full session refresh if still 403
                if response.status_code == 403:
                    logger.warning("🔄 Attempt 3: Performing full session refresh...")
                    self.refresh_session()
                    # Add extra delay after full refresh
                    time.sleep(3)
                    # Final retry with refreshed session
                    response = self.session.post(
                        f"{self.BASE_URL}/auction/request",
                        json=json_data,
                        headers=headers,
                        cookies=self.cookies,
                        timeout=30
                    )
                
                # If still failing, provide more detailed error
                if response.status_code == 403:
                    logger.error("❌ All attempts failed. Cloudflare protection may have changed.")
                    # Log response headers for debugging
                    logger.debug(f"Response headers: {dict(response.headers)}")
                    # Check if we got a challenge page
                    if 'cf-ray' in response.headers:
                        logger.error("🛡️ Cloudflare challenge detected. Manual cookie update may be required.")
            
            response.raise_for_status()
            
            # Save cookies after successful request
            self._save_cookies()
            
            # Parse JSON response
            data = response.json()
            
            # Extract cars from JSON
            cars = []
            for lot in data.get('lots', []):
                car = self._parse_car_from_json(lot)
                if car:
                    cars.append(car)
            
            # Get pagination info
            total_count = data.get('count', len(cars))
            current_page = data.get('page', filters.page)
            total_pages = data.get('pages', 1)
            
            # Build response
            return PLCAuctionResponse(
                success=True,
                message="Cars fetched successfully",
                total_count=total_count,
                cars=cars,
                current_page=current_page,
                page_size=filters.page_size,
                has_next_page=current_page < total_pages,
                has_prev_page=current_page > 1
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
    
    def _build_json_data(self, filters: PLCAuctionFilters) -> Dict[str, Any]:
        """Build JSON data for POST request from filters"""
        # Get current timestamp for date parameter
        import time
        current_timestamp = int(time.time())
        
        # Base JSON data structure from cars.py
        json_data = {
            "country": filters.country,
            "damage": "none",  # Default to none, can be extended later
            "date": filters.date or str(current_timestamp),
            "price_type": filters.price_type
        }
        
        # Add pagination if not first page
        if filters.page > 1:
            json_data["page"] = filters.page
        
        # Add other filters if provided
        # This can be extended based on API capabilities
        
        return json_data
    
    def _parse_car_from_json(self, lot: Dict[str, Any]) -> Optional[PLCAuctionCar]:
        """Parse car data from JSON response"""
        try:
            # Extract attributes
            attributes = lot.get('attributes', {})
            
            # Extract fuel, transmission, and mileage
            fuel = attributes.get('fuel', {}).get('value', '')
            transmission = attributes.get('transmission', {}).get('value', '')
            odometer = attributes.get('odometer', {}).get('value', '')
            
            # Parse mileage (remove 'km' and spaces)
            mileage = None
            if odometer:
                mileage_str = odometer.replace('km', '').replace(' ', '').strip()
                try:
                    mileage = int(mileage_str)
                except:
                    pass
            
            # Extract car details from title and URL
            title = lot.get('title', '')
            url = lot.get('url', '')
            
            # Extract manufacturer and model from title
            title_parts = title.split()
            manufacturer = title_parts[0] if title_parts else ''
            model = ' '.join(title_parts[1:]) if len(title_parts) > 1 else ''
            
            # Extract slug from URL
            slug = url.split('/')[-1] if url else ''
            
            # Create PLCAuctionCar object
            return PLCAuctionCar(
                id=lot.get('hash', ''),
                slug=slug,
                url=url,
                title=title,
                manufacturer=manufacturer,
                model=model,
                year=lot.get('year', 0),
                price=lot.get('price_bid', 0),
                price_formatted=lot.get('price_bid_html', ''),
                fuel=fuel,
                transmission=transmission,
                mileage=mileage,
                mileage_formatted=odometer,
                condition=lot.get('runs_drive', 'Unknown'),
                thumbnail=lot.get('thumb', ''),
                country=lot.get('country', ''),
                country_name=lot.get('country_name', ''),
                auction_date=datetime.fromtimestamp(lot.get('timestamp', 0) / 1000) if lot.get('timestamp') else None,
                is_auction=lot.get('is_auction', True),
                in_stock=lot.get('in_stock', True),
                can_book=lot.get('can_book', False),
                can_check=lot.get('can_check', False)
            )
        except Exception as e:
            logger.error(f"Error parsing car from JSON: {e}")
            return None
    
    def _validate_cookies(self) -> bool:
        """Validate if current cookies are still valid"""
        essential_cookies = ['cf_clearance', 'XSRF-TOKEN', '__session']
        
        for cookie_name in essential_cookies:
            cookie_value = self.session.cookies.get(cookie_name)
            if not cookie_value:
                logger.warning(f"⚠️ Missing essential cookie: {cookie_name}")
                return False
        
        # Check if cf_clearance looks expired (very basic check)
        cf_clearance = self.session.cookies.get('cf_clearance')
        if cf_clearance and len(cf_clearance) < 50:
            logger.warning("⚠️ cf_clearance cookie appears to be invalid")
            return False
        
        # Check if cookies were set recently (within last 24 hours)
        # This is a heuristic since we can't directly check cookie expiration
        try:
            session_file = self.session_manager.session_file
            if session_file.exists():
                import json
                from datetime import datetime, timedelta
                
                with open(session_file, 'r') as f:
                    session_data = json.load(f)
                
                # Check if session was updated recently
                last_updated = session_data.get('last_updated')
                if last_updated:
                    last_update_time = datetime.fromisoformat(last_updated)
                    if datetime.now() - last_update_time > timedelta(hours=24):
                        logger.warning("⚠️ Cookies are older than 24 hours")
                        return False
        except Exception as e:
            logger.debug(f"Could not check cookie age: {e}")
            
        return True

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
            
            # Clear existing cookies and recreate session
            self.session.cookies.clear()
            
            # Stop current Intercom session
            if hasattr(self, 'intercom'):
                self.intercom.stop_ping_loop()
            
            # Recreate cloudscraper session with fresh configuration
            self._setup_session()
            
            # Try multiple approaches to get fresh cookies
            cookie_refresh_success = False
            
            # Approach 1: Try to solve Cloudflare challenge directly
            try:
                logger.info("🔐 Attempting to solve Cloudflare challenge...")
                test_response = self.session.get(self.BASE_URL, timeout=15)
                if test_response.status_code == 200:
                    logger.info("✅ Successfully passed Cloudflare challenge")
                    cookie_refresh_success = True
            except Exception as e:
                logger.warning(f"⚠️ Cloudflare challenge failed: {e}")
            
            # Approach 2: Load fresh cookies from file if available
            if not cookie_refresh_success:
                import os
                cars_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "Glovis", "cars.py")
                if os.path.exists(cars_path):
                    logger.info("📄 Found cars.py, attempting to extract fresh cookies")
                    if self.update_cookies_from_curl(cars_path):
                        logger.info("✅ Successfully loaded cookies from cars.py")
                        cookie_refresh_success = True
                    else:
                        logger.warning("⚠️ Failed to extract cookies from cars.py")
            
            # Approach 3: Use default cookies as last resort
            if not cookie_refresh_success:
                logger.warning("⚠️ Using default cookies as fallback")
                self._apply_default_cookies()
            
            # Restart Intercom session
            self.intercom = IntercomSession()
            self.intercom.start_ping_loop()
            
            # Re-initialize browser session to establish new connection
            self._initialize_browser_session()
            
            # Save refreshed cookies
            self._save_cookies()
            logger.info("✅ Session refreshed successfully")
            
        except Exception as e:
            logger.error(f"❌ Error refreshing session: {e}")
            # Fallback to default cookies
            self._apply_default_cookies()
    
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
                                # Clear existing cookies first to avoid duplicates
                                self.session.cookies.clear()
                                # Update session cookies with proper domain/path
                                for name, value in new_cookies.items():
                                    # Skip empty cookie values to avoid errors
                                    if value:
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