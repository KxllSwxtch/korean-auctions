import logging
import time
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
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

logger = logging.getLogger(__name__)


class PLCAuctionService:
    BASE_URL = "https://plc.auction"
    AUCTION_URL = f"{BASE_URL}/auction"
    
    # Default cookies from the example (updated with cf_clearance and session tokens)
    DEFAULT_COOKIES = {
        "intercom-id-m1d5ih1o": "0f9a1bfc-debc-4985-9a2a-39a9de0f2eb6",
        "intercom-device-id-m1d5ih1o": "b6cba56c-2517-48c5-b1c0-93ff5d6a24fa",
        "_plc_ref": "eyJpdiI6Im90VTUyWlVMNFEzUE5pdi9XSlBCMEE9PSIsInZhbHVlIjoiT3pWbXAwemlJZjFJeVIyeC9na0tMWHJwWUlrV0pwQ1BERi9zdW5pbE9FUmVKYW1laDc3T1pOWWdmcEpVVWZJNXN5QUlmR0tzZHBTTDR5K3pXUjJLNlE9PSIsIm1hYyI6Ijk5YzU4M2I0NmNmZmJjNTBmNWYwMjdmNzllMTBkZWRmNzM5M2JhOTI5ZTZkMDBhYzhmY2Y1M2I4ZGIwYTIxYjQiLCJ0YWciOiIifQ%3D%3D",
        "_locale": "ru",
        "intercom-session-m1d5ih1o": "",
        "cf_clearance": "Ze88aRgkaEQVa4qjDnI8z7Bqteor1p6GxDN4MOG6jMQ-1753154140-1.2.1.1-orqppZYrg0xKbrCB6cwGVIGc2Fe3UOebr1MUbQ6p3htC0h8IlBhtd0TPHjsfoHawulQnK3IXq0hrEMxdfeZ6bcO0lDjOwI3AN9oGAnM1lORm.NM_z00gsqgExT0Hq_9_Fvv.H8vByM27cv7xui8pjT8hCj09OzijAVysgnK5bAtXCXtfreeA47qERB_VT_030HO60mzqK0ArsoIzTK56n7x1MBztnnBAStoUx1HaCII",
        "XSRF-TOKEN": "eyJpdiI6IlloMVNsY2Vja05hQ2FiT1Q0VFVIOVE9PSIsInZhbHVlIjoiTWs5dHlvN3Vtd3RkODlubmpXbzlYQjI4MCsxTnZobytlYSttS2Q4b1NhUUtXQk0xWWoyc00wUXpsbzJ0NG9aTnRUYVVWQUNiQTFLT3NUQVh5WnZ0ZWFLenRsSHBUYWt1dGcrd0wyeW5pS3dqSHNFS3k5Q3gza1hvZEV2Nlc4YjYiLCJtYWMiOiJmY2JmMTFjOTBiYWUzMDE2YzBiNTgwZjZiMjYzNDc2MzQ2MWM5MjkwYWU2YTUyMWE4ZWU3MWY5NmRkZjkyMGExIiwidGFnIjoiIn0%3D",
        "__session": "eyJpdiI6IlF0T3huRkh6TTdlUDJrQkRnVlRQdXc9PSIsInZhbHVlIjoiWWdaTDBEVitSOG5SQ0J0ZHUzUWZmR3JlUkFPeUd5WG9kNFJhMlpNRlJsbDk4VnJxSWxFY1k3M3BCcG5Rc1FHQ2QyaEFEbG1KbFQva254bVJLSXZBbk5nbU5sOGFuOVVLdUl3Qmp5ejU0aFFra3dneDBZOUxSMzYrU1FneUF4RDQiLCJtYWMiOiJkNzY0YWI5MWFmMTJiZjEwMzNiNDQ5ZjVmMDE4NzExNzFmNjVlZTQ3ZmYwMDgzMTQzNzcyZWFjNDkzY2Y3MWNlIiwidGFnIjoiIn0%3D",
    }
    
    # Default headers from the example
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
        self._setup_session()
    
    def _setup_session(self):
        """Setup requests session with retry strategy"""
        self.session = requests.Session()
        
        # Configure proxy if enabled
        from app.core.proxy_config import get_proxy_config
        proxy_config = get_proxy_config()
        if proxy_config:
            self.session.proxies.update(proxy_config)
            logger.info("🌐 Proxy configured for PLC Auction session")
        else:
            logger.info("📡 Direct connection (no proxy) for PLC Auction session")
        
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
    
    def _save_cookies(self):
        """Save current session cookies"""
        cookies_dict = dict(self.session.cookies)
        self.session_manager.save_session('plc_auction', cookies_dict)
    
    def fetch_cars(self, filters: PLCAuctionFilters) -> PLCAuctionResponse:
        """Fetch cars from PLC Auction with filters"""
        try:
            # Build query parameters
            params = self._build_query_params(filters)
            
            # Make request
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
        params = {
            "country": filters.country,
            "price_type": filters.price_type
        }
        
        # Add page parameter (not needed for first page)
        if filters.page > 1:
            params["page"] = filters.page
        
        # Add date if provided
        if filters.date:
            params["date"] = filters.date
        
        # Add other filters if implemented
        # This would need to be extended based on how PLC Auction handles filters
        
        return params
    
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