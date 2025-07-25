import json
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
    
    # Car manufacturer and model mapping (from full-page.html)
    CAR_LIST_MAP = {
        "현대": [
            {"no": "472", "name": "아반떼", "e_name": "AVANTE"},
            {"no": "550", "name": "엑센트", "e_name": "ACCENT"},
            {"no": "551", "name": "캐스퍼", "e_name": "CASPER"},
            {"no": "553", "name": "카운티", "e_name": "COUNTY"},
            {"no": "540", "name": "제네시스", "e_name": "GENESIS"},
            {"no": "460", "name": "그랜저", "e_name": "GRANDEUR"},
            {"no": "501", "name": "i30", "e_name": "i30"},
            {"no": "499", "name": "i40", "e_name": "i40"},
            {"no": "490", "name": "아이오닉", "e_name": "IONIQ"},
            {"no": "544", "name": "코나", "e_name": "KONA"},
            {"no": "549", "name": "맥스크루즈", "e_name": "MAXCRUZ"},
            {"no": "555", "name": "마이티", "e_name": "MIGHTY"},
            {"no": "556", "name": "넥쏘", "e_name": "NEXO"},
            {"no": "545", "name": "팰리세이드", "e_name": "PALISADE"},
            {"no": "558", "name": "포터", "e_name": "PORTER"},
            {"no": "541", "name": "싼타페", "e_name": "SANTAFE"},
            {"no": "557", "name": "쏠라티", "e_name": "SOLATI"},
            {"no": "559", "name": "쏘나타", "e_name": "SONATA"},
            {"no": "539", "name": "스타렉스", "e_name": "STAREX"},
            {"no": "560", "name": "스타리아", "e_name": "STARIA"},
            {"no": "542", "name": "투싼", "e_name": "TUCSON"},
            {"no": "546", "name": "벨로스터", "e_name": "VELOSTER"},
            {"no": "561", "name": "베뉴", "e_name": "VENUE"},
        ],
        "기아": [
            {"no": "587", "name": "봉고", "e_name": "BONGO"},
            {"no": "565", "name": "카니발", "e_name": "CARNIVAL"},
            {"no": "588", "name": "EV6", "e_name": "EV6"},
            {"no": "589", "name": "EV9", "e_name": "EV9"},
            {"no": "572", "name": "K3", "e_name": "K3"},
            {"no": "568", "name": "K5", "e_name": "K5"},
            {"no": "566", "name": "K7", "e_name": "K7"},
            {"no": "585", "name": "K8", "e_name": "K8"},
            {"no": "578", "name": "K9", "e_name": "K9"},
            {"no": "577", "name": "모하비", "e_name": "MOHAVE"},
            {"no": "567", "name": "모닝", "e_name": "MORNING"},
            {"no": "575", "name": "니로", "e_name": "NIRO"},
            {"no": "573", "name": "프라이드", "e_name": "PRIDE"},
            {"no": "570", "name": "레이", "e_name": "RAY"},
            {"no": "583", "name": "셀토스", "e_name": "SELTOS"},
            {"no": "569", "name": "쏘렌토", "e_name": "SORENTO"},
            {"no": "576", "name": "쏘울", "e_name": "SOUL"},
            {"no": "571", "name": "스포티지", "e_name": "SPORTAGE"},
            {"no": "590", "name": "스팅어", "e_name": " STINGER"},
            {"no": "582", "name": "스토닉", "e_name": "STONIC"},
        ],
        # Add more manufacturers as needed...
    }
    
    def __init__(self):
        self.session_manager = SessionManager()
        self.parser = SSANCARParser()
        self.session = self._create_session()
        self._load_or_set_cookies()
    
    def _create_session(self) -> requests.Session:
        """Create a requests session with retry logic"""
        session = requests.Session()
        
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
            
            # Get total count (would need separate request)
            total_count = len(cars)  # Simplified for now
            current_page = int(filters.pages) + 1  # Convert 0-based to 1-based
            page_size = int(filters.list)
            
            return SSANCARResponse(
                success=True,
                message="Cars fetched successfully",
                cars=cars,
                total_count=total_count,
                current_page=current_page,
                page_size=page_size,
                has_next_page=len(cars) == page_size,
                has_prev_page=current_page > 1
            )
            
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
            
            # Convert our CAR_LIST_MAP to manufacturer list
            for korean_name, models in self.CAR_LIST_MAP.items():
                # Map Korean names to English
                name_map = {
                    "현대": "HYUNDAI",
                    "기아": "KIA",
                    "한국지엠": "CHEVROLET",
                    "르노삼성": "RENAULT",
                    "쌍용": "SSANGYONG",
                    "제네시스": "GENESIS",
                }
                
                english_name = name_map.get(korean_name, korean_name)
                
                manufacturer = SSANCARManufacturer(
                    code=korean_name,
                    name=english_name,
                    korean_name=korean_name,
                    count=len(models)
                )
                manufacturers.append(manufacturer)
            
            # Add more manufacturers from extended list
            additional_manufacturers = [
                SSANCARManufacturer(code="벤츠", name="BENZ", korean_name="벤츠", count=0),
                SSANCARManufacturer(code="BMW", name="BMW", korean_name="BMW", count=0),
                SSANCARManufacturer(code="아우디", name="AUDI", korean_name="아우디", count=0),
                SSANCARManufacturer(code="폭스바겐", name="VOLKSWAGEN", korean_name="폭스바겐", count=0),
                SSANCARManufacturer(code="랜드로버", name="LANDROVER", korean_name="랜드로버", count=0),
                SSANCARManufacturer(code="미니", name="MINI", korean_name="미니", count=0),
                SSANCARManufacturer(code="포드", name="FORD", korean_name="포드", count=0),
                SSANCARManufacturer(code="닛산", name="NISSAN", korean_name="닛산", count=0),
                SSANCARManufacturer(code="토요타", name="TOYOTA", korean_name="토요타", count=0),
                SSANCARManufacturer(code="렉서스", name="LEXUS", korean_name="렉서스", count=0),
                SSANCARManufacturer(code="마세라티", name="MASERATI", korean_name="마세라티", count=0),
                SSANCARManufacturer(code="링컨", name="LINCOLN", korean_name="링컨", count=0),
                SSANCARManufacturer(code="벤틀리", name="BENTLEY", korean_name="벤틀리", count=0),
                SSANCARManufacturer(code="볼보", name="VOLVO", korean_name="볼보", count=0),
                SSANCARManufacturer(code="시트로엥", name="CITROEN", korean_name="시트로엥", count=0),
                SSANCARManufacturer(code="인피니티", name="INFINITI", korean_name="인피니티", count=0),
                SSANCARManufacturer(code="재규어", name="JAGUAR", korean_name="재규어", count=0),
                SSANCARManufacturer(code="지프", name="JEEP", korean_name="지프", count=0),
                SSANCARManufacturer(code="캐딜락", name="CADILLAC", korean_name="캐딜락", count=0),
                SSANCARManufacturer(code="크라이슬러", name="CHRYSLER", korean_name="크라이슬러", count=0),
                SSANCARManufacturer(code="테슬라", name="TESLA", korean_name="테슬라", count=0),
                SSANCARManufacturer(code="포르쉐", name="PORSCHE", korean_name="포르쉐", count=0),
                SSANCARManufacturer(code="푸조", name="PEUGEOT", korean_name="푸조", count=0),
                SSANCARManufacturer(code="피아트", name="FIAT", korean_name="피아트", count=0),
                SSANCARManufacturer(code="혼다", name="HONDA", korean_name="혼다", count=0),
            ]
            
            manufacturers.extend(additional_manufacturers)
            
            logger.info(f"✅ Retrieved {len(manufacturers)} manufacturers")
            return manufacturers, True
            
        except Exception as e:
            logger.error(f"❌ Error getting manufacturers: {e}")
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
            
            # If no models found in our map, try to fetch from website
            if not models and manufacturer_code not in self.CAR_LIST_MAP:
                logger.warning(f"⚠️ No models found for manufacturer: {manufacturer_code}")
                # Could implement dynamic fetching here
            
            logger.info(f"✅ Retrieved {len(models)} models for {manufacturer_code}")
            return models, True
            
        except Exception as e:
            logger.error(f"❌ Error getting models: {e}")
            return [], False
    
    def get_car_detail(self, car_no: str) -> Optional[SSANCARCarDetail]:
        """Get detailed information about a specific car"""
        try:
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
            from app.models.ssancar import SSANCARFilterOption, SSANCARFilterOptionsResponse
            
            logger.info("🔧 Getting SSANCAR filter options")
            
            # Get manufacturers (already implemented)
            manufacturers, _ = self.get_manufacturers()
            
            # Define static filter options based on SSANCAR's actual filters
            fuel_types = [
                SSANCARFilterOption(value="Gasoline", label="Gasoline", count=None),
                SSANCARFilterOption(value="Diesel", label="Diesel", count=None),
                SSANCARFilterOption(value="LPG", label="LPG", count=None),
                SSANCARFilterOption(value="Hybrid", label="Hybrid", count=None),
                SSANCARFilterOption(value="Electric", label="Electric", count=None),
                SSANCARFilterOption(value="Hydrogen", label="Hydrogen", count=None),
            ]
            
            transmissions = [
                SSANCARFilterOption(value="Automatic", label="Automatic", count=None),
                SSANCARFilterOption(value="Manual", label="Manual", count=None),
                SSANCARFilterOption(value="CVT", label="CVT", count=None),
                SSANCARFilterOption(value="DCT", label="DCT", count=None),
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
                SSANCARFilterOption(value="Black", label="Black", count=None),
                SSANCARFilterOption(value="White", label="White", count=None),
                SSANCARFilterOption(value="Silver", label="Silver", count=None),
                SSANCARFilterOption(value="Gray", label="Gray", count=None),
                SSANCARFilterOption(value="Red", label="Red", count=None),
                SSANCARFilterOption(value="Blue", label="Blue", count=None),
                SSANCARFilterOption(value="Green", label="Green", count=None),
                SSANCARFilterOption(value="Brown", label="Brown", count=None),
                SSANCARFilterOption(value="Beige", label="Beige", count=None),
                SSANCARFilterOption(value="Orange", label="Orange", count=None),
                SSANCARFilterOption(value="Yellow", label="Yellow", count=None),
                SSANCARFilterOption(value="Other", label="Other", count=None),
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
            return response.model_dump()
            
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