import hashlib
import re
from typing import List, Optional, Dict, Any, Tuple
from bs4 import BeautifulSoup
from loguru import logger

from app.models.ssancar import (
    SSANCARCar, SSANCARCarDetail, SSANCARManufacturer, SSANCARModel
)

# Status codes returned by parse_car_detail alongside the parsed object.
# The service layer translates these into HTTP error codes for the route.
PARSE_STATUS_VALID = "valid"
PARSE_STATUS_SESSION_EXPIRED = "session_expired"
PARSE_STATUS_NOT_FOUND = "not_found"
PARSE_STATUS_EMPTY = "empty"
PARSE_STATUS_INVALID_DATA = "invalid_data"
PARSE_STATUS_EXCEPTION = "exception"

# Markers that indicate SSANCAR returned a login/session-expired page instead
# of the requested car detail. Lowercased before matching.
_LOGIN_REDIRECT_MARKERS = (
    '/member/login',
    'name="loginform"',
    "name='loginform'",
    "id='loginform'",
    'id="loginform"',
    'session expired',
    'session_expired',
    '로그인',
)

# Markers that indicate the car was archived / not found by SSANCAR
# (200 OK with a "no such car" page).
_NOT_FOUND_MARKERS = (
    '차량을 찾을 수 없습니다',
    '존재하지 않는',
    '잘못된 접근',
    'no such car',
)

# Minimum HTML length we'd plausibly accept as a real car detail page.
# A real car_view.php page is multi-KB; anything substantially smaller is
# almost certainly an empty body, error envelope, or redirect stub.
_MIN_HTML_LENGTH = 500


class SSANCARParser:
    """Parser for SSANCAR auction HTML responses"""

    @staticmethod
    def _classify_html(html: str) -> str:
        """Classify a raw HTML body before attempting selector extraction.

        Returns one of the PARSE_STATUS_* codes. Anything other than
        PARSE_STATUS_VALID means the parser should bail out without
        constructing a (zero-filled) object.
        """
        if not html or len(html.strip()) < _MIN_HTML_LENGTH:
            return PARSE_STATUS_EMPTY

        haystack = html.lower()
        for marker in _LOGIN_REDIRECT_MARKERS:
            if marker in haystack:
                return PARSE_STATUS_SESSION_EXPIRED
        for marker in _NOT_FOUND_MARKERS:
            if marker in html:  # Korean markers — case preserved
                return PARSE_STATUS_NOT_FOUND
        return PARSE_STATUS_VALID

    @staticmethod
    def _is_minimally_valid(detail: SSANCARCarDetail) -> bool:
        """Reject objects that lack core identity fields.

        A usable detail record must have a car_no plus enough naming/pricing
        info to render a meaningful page. Without these the UI degrades to
        "Unknown Car / N/A / TBA / $0", which is the bug we're closing.
        """
        if not detail.car_no:
            return False
        has_name = bool(detail.full_name) or (
            bool(detail.manufacturer) and bool(detail.model)
        )
        has_signal = (
            detail.year and detail.year > 0
        ) or bool(detail.starting_price) or bool(detail.images)
        return has_name and has_signal
    
    def parse_car_list(self, html: str) -> List[SSANCARCar]:
        """Parse car list from SSANCAR HTML response"""
        try:
            cars = []
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find all car list items
            car_items = soup.find_all('li')
            
            for item in car_items:
                # Find the main link
                link = item.find('a', href=True)
                if not link or 'car_view.php' not in link['href']:
                    continue
                
                try:
                    # Extract car_no from URL
                    car_no_match = re.search(r'car_no=(\d+)', link['href'])
                    car_no = car_no_match.group(1) if car_no_match else ""
                    
                    # Extract stock number
                    stock_elem = item.find('span', class_='num')
                    stock_no = stock_elem.text.strip() if stock_elem else ""
                    
                    # Extract car name
                    name_elem = item.find('span', class_='name')
                    full_name = name_elem.text.strip() if name_elem else ""
                    
                    # Parse manufacturer and model from full name
                    manufacturer, model = self._parse_manufacturer_model(full_name)
                    
                    # Extract details (year, mileage, fuel, transmission, grade)
                    detail_elem = item.find('ul', class_='detail')
                    year, mileage, mileage_formatted, fuel, transmission, grade = self._parse_details(detail_elem)
                    
                    # Extract price
                    money_elem = item.find('p', class_='money')
                    bid_price = 0
                    if money_elem:
                        # Find the span with class 'num' inside money element
                        price_span = money_elem.find('span', class_='num')
                        if price_span:
                            price_text = price_span.text.strip().replace(',', '')
                            try:
                                bid_price = int(price_text)
                            except ValueError:
                                bid_price = 0
                    
                    # Extract thumbnail
                    img_elem = item.find('img')
                    thumbnail_url = img_elem['src'] if img_elem and 'src' in img_elem.attrs else ""
                    
                    # Build detail URL
                    detail_url = f"https://www.ssancar.com{link['href']}" if link['href'].startswith('/') else link['href']
                    
                    car = SSANCARCar(
                        car_no=car_no,
                        stock_no=stock_no,
                        manufacturer=manufacturer,
                        model=model,
                        full_name=full_name,
                        year=year,
                        mileage=mileage,
                        mileage_formatted=mileage_formatted,
                        fuel=fuel,
                        transmission=transmission,
                        grade=grade,
                        bid_price=bid_price,
                        thumbnail_url=thumbnail_url,
                        detail_url=detail_url,
                        source="SSANCAR"
                    )
                    
                    cars.append(car)
                    
                except Exception as e:
                    logger.error(f"Error parsing car item: {e}")
                    continue
            
            logger.info(f"✅ Parsed {len(cars)} cars from HTML")
            return cars
            
        except Exception as e:
            logger.error(f"Error parsing car list: {e}")
            return []
    
    def _parse_manufacturer_model(self, full_name: str) -> tuple[str, str]:
        """Extract manufacturer and model from full car name"""
        if not full_name:
            return "", ""
        
        # Check for format "[MANUFACTURER] Model Name"
        bracket_match = re.search(r'^\[(.+?)\]\s*(.+)', full_name)
        if bracket_match:
            manufacturer = bracket_match.group(1).upper()
            model = bracket_match.group(2).strip()
            return manufacturer, model
        
        # Common manufacturer patterns
        manufacturers = {
            'BMW', 'BENZ', 'MERCEDES', 'AUDI', 'VOLKSWAGEN', 'VOLVO',
            'HYUNDAI', 'KIA', 'GENESIS', 'CHEVROLET', 'FORD', 'TOYOTA',
            'NISSAN', 'HONDA', 'MAZDA', 'LEXUS', 'INFINITI', 'ACURA',
            'LANDROVER', 'JAGUAR', 'PORSCHE', 'FERRARI', 'LAMBORGHINI',
            'MASERATI', 'BENTLEY', 'ROLLS-ROYCE', 'MINI', 'JEEP',
            'LINCOLN', 'CADILLAC', 'CHRYSLER', 'DODGE', 'RAM',
            'TESLA', 'PEUGEOT', 'CITROEN', 'FIAT', 'ALFA ROMEO',
            'SSANGYONG', 'RENAULT', 'KGMobility'
        }
        
        # Check for Korean manufacturers with English names in parentheses
        korean_match = re.search(r'^(.+?)\((.+?)\)', full_name)
        if korean_match:
            manufacturer = korean_match.group(2).upper()
            model = full_name.replace(korean_match.group(0), '').strip()
        else:
            # Find manufacturer in the beginning of the name
            parts = full_name.split()
            manufacturer = ""
            model = full_name
            
            for i, part in enumerate(parts):
                if part.upper() in manufacturers:
                    manufacturer = part.upper()
                    model = ' '.join(parts[i+1:])
                    break
        
        return manufacturer, model
    
    def _parse_details(self, detail_elem) -> tuple:
        """Parse car details from detail list element"""
        year = 0
        mileage = None
        mileage_formatted = ""
        fuel = ""
        transmission = ""
        grade = ""

        if not detail_elem:
            return year, mileage, mileage_formatted, fuel, transmission, grade

        # Find all span elements in details
        spans = detail_elem.find_all('span')

        for i, span in enumerate(spans):
            text = span.text.strip()

            # Year (4 digits)
            if re.match(r'^\d{4}$', text):
                year = int(text)
            # Mileage (contains 'km')
            elif 'km' in text.lower():
                mileage_formatted = text
                # Extract numeric value
                mileage_num = re.sub(r'[^\d]', '', text)
                if mileage_num:
                    mileage = int(mileage_num)
            # Grade (letter + optional slash + digit, e.g. A1, A/1, F/1)
            elif re.match(r'^[A-Z][/]?\d$', text):
                grade = text.replace('/', '')  # Normalize A/1 to A1
            # Transmission (A/T, M/T)
            elif text.upper() in ['A/T', 'M/T', 'CVT', 'DCT']:
                transmission = 'Automatic' if text.upper() == 'A/T' else text
            # Fuel type
            elif text.lower() in ['gasoline', 'diesel', 'lpg', 'hybrid', 'electric', 'hydrogen']:
                fuel = text
            # Korean fuel types
            elif text in ['휘발유', '경유', 'LPG', '하이브리드', '전기', '수소']:
                fuel_map = {
                    '휘발유': 'Gasoline',
                    '경유': 'Diesel',
                    'LPG': 'LPG',
                    '하이브리드': 'Hybrid',
                    '전기': 'Electric',
                    '수소': 'Hydrogen'
                }
                fuel = fuel_map.get(text, text)
            # Engine volume (contains 'cc') — skip, not extracted in list parser
            elif 'cc' in text.lower():
                pass
            # Bare numeric value (comma-formatted, 1000+) — mileage without "km" suffix
            elif re.match(r'^\d{1,3}(,\d{3})+$', text):
                mileage_formatted = f"{text} Km"
                mileage_num = text.replace(',', '')
                if mileage_num:
                    mileage = int(mileage_num)

        return year, mileage, mileage_formatted, fuel, transmission, grade
    
    def parse_car_detail(
        self, html: str
    ) -> Tuple[Optional[SSANCARCarDetail], str]:
        """Parse detailed car information from SSANCAR detail page.

        Returns a tuple of (parsed_detail, status_code). The detail is None
        whenever status is anything other than PARSE_STATUS_VALID. The status
        lets the service/route layer translate the failure into a
        discriminated HTTP 404 (session_expired vs car_unavailable) instead
        of silently returning a zero-filled object.
        """
        # Pre-flight: detect non-detail responses (login redirect, empty
        # body, archived page) before we construct any object.
        pre_status = self._classify_html(html)
        if pre_status != PARSE_STATUS_VALID:
            html_len = len(html) if html else 0
            html_sha = (
                hashlib.sha256(html.encode("utf-8", "ignore")).hexdigest()[:12]
                if html else "-"
            )
            logger.warning(
                f"⚠️ SSANCAR detail pre-flight rejected: status={pre_status} "
                f"len={html_len} sha={html_sha}"
            )
            return None, pre_status

        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract car_no from URL parameter in the HTML or from script tags
            car_no = ""
            # Try to find in URL parameters first
            car_no_match = re.search(r'car_no=(\d+)', html)
            if car_no_match:
                car_no = car_no_match.group(1)
            else:
                # Try to find in JavaScript or other places
                car_no_script_match = re.search(r"['\"]car_no['\"]:\s*['\"](\d+)['\"]", html)
                if car_no_script_match:
                    car_no = car_no_script_match.group(1)
            
            # Extract stock number
            stock_elem = soup.find('p', class_='num')
            stock_no = ""
            if stock_elem:
                stock_span = stock_elem.find('span')
                if stock_span:
                    stock_no = stock_span.text.strip()
            
            # Extract car name and parse manufacturer/model
            name_elem = soup.find('p', class_='name')
            full_name = ""
            manufacturer = ""
            model = ""
            if name_elem:
                name_span = name_elem.find('span')
                if name_span:
                    full_name = name_span.text.strip()
                    manufacturer, model = self._parse_manufacturer_model(full_name)
            
            # Known color names for extraction
            KNOWN_COLORS = {
                'black', 'white', 'silver', 'gray', 'grey', 'red', 'blue',
                'green', 'brown', 'beige', 'orange', 'yellow', 'gold', 'navy',
                'purple', 'pink', 'burgundy', 'champagne', 'bronze', 'ivory'
            }

            # Extract details (year, transmission, fuel, etc.)
            year = 0
            transmission = ""
            fuel_type = ""
            engine_volume = ""
            mileage = None  # Initialize as None (optional int)
            mileage_formatted = ""
            condition_grade = ""
            color = ""

            detail_elem = soup.find('ul', class_='detail')
            if detail_elem:
                li_elem = detail_elem.find('li')
                if li_elem:
                    spans = li_elem.find_all('span')
                    for span in spans:
                        text = span.text.strip()

                        # Year (4 digits)
                        if re.match(r'^\d{4}$', text):
                            year = int(text)
                        # Transmission
                        elif text.upper() in ['A/T', 'M/T', 'CVT', 'DCT']:
                            transmission = text
                        # Fuel type
                        elif text.lower() in ['gasoline', 'diesel', 'lpg', 'hybrid', 'electric', 'hydrogen']:
                            fuel_type = text
                        # Engine volume (contains 'cc')
                        elif 'cc' in text.lower():
                            engine_volume = text
                        # Mileage (contains 'km')
                        elif 'km' in text.lower():
                            mileage_formatted = text
                            # Extract numeric value for mileage
                            mileage_num = re.sub(r'[^\d]', '', text)
                            if mileage_num:
                                mileage = int(mileage_num)
                        # Grade (letter + optional slash + digit, e.g. A1, A/1, F/1)
                        elif re.match(r'^[A-Z][/]?\d$', text):
                            condition_grade = text
                        # Color (known color names)
                        elif text.lower() in KNOWN_COLORS:
                            color = text
                        # Bare numeric value (comma-formatted, 1000+) — mileage without "km" suffix
                        elif re.match(r'^\d{1,3}(,\d{3})+$', text):
                            mileage_formatted = f"{text} Km"
                            mileage_num = text.replace(',', '')
                            if mileage_num:
                                mileage = int(mileage_num)
            
            # Extract starting price
            starting_price = ""
            currency = "USD"
            money_elem = soup.find('p', class_='money')
            if money_elem:
                money_span = money_elem.find('span')
                if money_span:
                    price_text = money_span.text.strip()
                    starting_price = price_text
                    # Determine currency from price format
                    if '$' in price_text:
                        currency = "USD"
                    elif '₩' in price_text or 'won' in price_text.lower():
                        currency = "KRW"
            
            # Extract images from swiper slides
            images = []
            swiper_slides = soup.find_all('div', class_='swiper-slide')
            for slide in swiper_slides:
                img = slide.find('img')
                if img and 'src' in img.attrs:
                    img_url = img['src']
                    # Skip placeholder images
                    if 'no_image' not in img_url:
                        images.append(img_url)
            
            # Main image is the first image
            main_image = images[0] if images else ""
            
            # Extract auction dates and timing
            auction_start_date = None
            auction_end_date = None
            upload_date = ""
            auction_time_remaining = ""
            
            # Look for date information in the day_list section
            day_list = soup.find('ul', class_='day_list')
            if day_list:
                detail_elem = day_list.find('p', class_='detail')
                if detail_elem:
                    detail_text = detail_elem.get_text(separator=' ')
                    
                    # Extract upload date
                    upload_match = re.search(r'Upload\s*:\s*(\d{4}-\d{2}-\d{2}\s+\d+:\d+(?:AM|PM)?)', detail_text)
                    if upload_match:
                        upload_date = upload_match.group(1)
                    
                    # Extract start date
                    start_match = re.search(r'Start\s*:\s*(\d{4}-\d{2}-\d{2}\s+\d+:\d+(?:AM|PM)?)', detail_text)
                    if start_match:
                        auction_start_date = start_match.group(1)
                        auction_end_date = auction_start_date  # SSANCAR typically has same day auctions
            
            # Extract remaining time
            timer_elem = soup.find('strong', id='timer')
            if timer_elem:
                # Get the formatted time string
                time_text = timer_elem.get_text(strip=True)
                auction_time_remaining = time_text if time_text else "Time :DHms"
            
            # Build the SSANCARCarDetail object
            from datetime import datetime
            car_detail = SSANCARCarDetail(
                car_no=car_no,
                stock_no=stock_no,
                manufacturer=manufacturer,
                model=model,
                full_name=full_name,
                year=year,
                mileage=mileage,  # Already None if not found
                mileage_formatted=mileage_formatted,
                fuel=fuel_type,
                fuel_type=fuel_type,  # Set both fuel and fuel_type
                transmission=transmission,
                grade=condition_grade,
                condition_grade=condition_grade,  # Set both grade and condition_grade
                color=color,
                engine_size=engine_volume,
                engine_volume=engine_volume,  # Set both engine_size and engine_volume
                vin="",  # VIN not shown in public view
                bid_price=0,  # Will be parsed from starting_price
                buy_now_price=0,  # Not available in SSANCAR
                auction_date=datetime.now() if auction_start_date else None,
                auction_status="active" if auction_time_remaining and "D" in auction_time_remaining else "ended",
                images=images,
                inspection_sheet_url="",  # Not provided in the HTML
                features=[],  # Features not listed in detail page
                condition_notes="",  # Notes not shown in public view
                # Additional SSANCAR specific fields
                starting_price=starting_price,
                currency=currency,
                main_image=main_image,
                auction_start_date=auction_start_date,
                auction_end_date=auction_end_date,
                auction_time_remaining=auction_time_remaining,
                upload_date=upload_date,
                parsed_at=datetime.now().isoformat()
            )
            
            # Post-parse validation: reject objects that lack core identity.
            # Without this gate, a 200 OK page with the wrong markup yields
            # a zero-filled SSANCARCarDetail that the UI renders as
            # "Unknown Car / N/A / TBA / $0".
            if not self._is_minimally_valid(car_detail):
                html_sha = hashlib.sha256(
                    html.encode("utf-8", "ignore")
                ).hexdigest()[:12]
                logger.warning(
                    f"⚠️ SSANCAR parser produced empty/invalid result: "
                    f"car_no='{car_no}' year={year} name='{full_name}' "
                    f"len={len(html)} sha={html_sha}"
                )
                return None, PARSE_STATUS_INVALID_DATA

            logger.info(f"✅ Successfully parsed car detail for {car_no}")
            return car_detail, PARSE_STATUS_VALID

        except Exception as e:
            logger.error(f"Error parsing car detail: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None, PARSE_STATUS_EXCEPTION
    
    def parse_manufacturers(self, html: str) -> List[SSANCARManufacturer]:
        """Parse manufacturer list from dropdown or JavaScript"""
        try:
            manufacturers = []
            
            # The carList object from JavaScript contains manufacturer data
            # Extract it using regex
            carlist_match = re.search(r'const carList = ({[^}]+})', html, re.DOTALL)
            if not carlist_match:
                logger.error("Could not find carList in HTML")
                return manufacturers
            
            # Parse the JavaScript object
            # This is a simplified approach - in production, you might use a proper JS parser
            carlist_text = carlist_match.group(1)
            
            # Extract manufacturer entries
            manufacturer_matches = re.findall(r'"([^"]+)":\s*\[', carlist_text)
            
            for korean_name in manufacturer_matches:
                # Map Korean names to English
                name_map = {
                    "현대": "HYUNDAI",
                    "기아": "KIA",
                    "한국지엠": "CHEVROLET",
                    "르노삼성": "RENAULT",
                    "쌍용": "SSANGYONG",
                    "제네시스": "GENESIS",
                    "벤츠": "BENZ",
                    "BMW": "BMW",
                    "아우디": "AUDI",
                    "폭스바겐": "VOLKSWAGEN",
                    "랜드로버": "LANDROVER",
                    "미니": "MINI",
                    "포드": "FORD",
                    "닛산": "NISSAN",
                    "토요타": "TOYOTA",
                    "렉서스": "LEXUS",
                    "마세라티": "MASERATI",
                    "링컨": "LINCOLN",
                    "벤틀리": "BENTLEY",
                    "볼보": "VOLVO",
                    "시트로엥": "CITROEN",
                    "인피니티": "INFINITI",
                    "재규어": "JAGUAR",
                    "지프": "JEEP",
                    "캐딜락": "CADILLAC",
                    "크라이슬러": "CHRYSLER",
                    "테슬라": "TESLA",
                    "포르쉐": "PORSCHE",
                    "푸조": "PEUGEOT",
                    "피아트": "FIAT",
                    "혼다": "HONDA"
                }
                
                english_name = name_map.get(korean_name, korean_name)
                
                manufacturer = SSANCARManufacturer(
                    code=korean_name,
                    name=english_name,
                    korean_name=korean_name,
                    count=0  # Count would need to be fetched separately
                )
                manufacturers.append(manufacturer)
            
            logger.info(f"✅ Parsed {len(manufacturers)} manufacturers")
            return manufacturers
            
        except Exception as e:
            logger.error(f"Error parsing manufacturers: {e}")
            return []
    
    def parse_models(self, carlist_data: Dict[str, List[Dict[str, Any]]], manufacturer_code: str) -> List[SSANCARModel]:
        """Parse models for a specific manufacturer from carList data"""
        try:
            models = []
            
            if manufacturer_code not in carlist_data:
                logger.warning(f"Manufacturer {manufacturer_code} not found in carList")
                return models
            
            model_list = carlist_data.get(manufacturer_code, [])
            
            for model_data in model_list:
                model = SSANCARModel(
                    no=model_data.get('no', ''),
                    name=model_data.get('name', ''),
                    e_name=model_data.get('e_name', ''),
                    manufacturer_code=manufacturer_code
                )
                models.append(model)
            
            logger.info(f"✅ Parsed {len(models)} models for {manufacturer_code}")
            return models
            
        except Exception as e:
            logger.error(f"Error parsing models: {e}")
            return []