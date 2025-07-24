import re
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup
from loguru import logger

from app.models.ssancar import (
    SSANCARCar, SSANCARCarDetail, SSANCARManufacturer, SSANCARModel
)


class SSANCARParser:
    """Parser for SSANCAR auction HTML responses"""
    
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
                        detail_url=detail_url
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
            # Grade (A1-D2 pattern or A/1-D/2 pattern)
            elif re.match(r'^[A-D][/]?\d$', text):
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
        
        return year, mileage, mileage_formatted, fuel, transmission, grade
    
    def parse_car_detail(self, html: str) -> Optional[SSANCARCarDetail]:
        """Parse detailed car information from SSANCAR detail page"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract basic info from the page
            # This would need to be implemented based on actual HTML structure
            # For now, returning None as placeholder
            logger.warning("Car detail parsing not yet implemented")
            return None
            
        except Exception as e:
            logger.error(f"Error parsing car detail: {e}")
            return None
    
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