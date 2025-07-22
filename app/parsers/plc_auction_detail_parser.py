import json
import re
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
from app.models.plc_auction import PLCAuctionCarDetail, PLCAuctionVehicleSchema
from app.core.logging import get_logger

logger = get_logger("plc_auction_detail_parser")


class PLCAuctionDetailParser:
    """Parser for PLC Auction car detail pages"""
    
    def parse_car_detail(self, html_content: str, detail_url: str) -> Optional[PLCAuctionCarDetail]:
        """
        Parse car detail information from PLC Auction HTML
        
        Args:
            html_content: HTML content of the detail page
            detail_url: URL of the detail page
            
        Returns:
            PLCAuctionCarDetail or None if parsing fails
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract schema.org structured data
            vehicle_data = self._extract_schema_data(soup)
            if not vehicle_data:
                logger.error("Failed to extract schema.org data")
                return None
                
            # Extract additional data from HTML
            lot_data = self._extract_lot_data(soup)
            
            # Parse mileage
            mileage_str, mileage_km = self._parse_mileage(vehicle_data, lot_data)
            
            # Extract images
            images = self._extract_images(soup, vehicle_data)
            
            # Build car detail object
            car_detail = PLCAuctionCarDetail(
                title=vehicle_data.get('name', ''),
                vin=vehicle_data.get('vehicleIdentificationNumber', ''),
                year=vehicle_data.get('productionDate', 0),
                manufacturer=self._extract_manufacturer(vehicle_data),
                model=self._extract_model(vehicle_data),
                engine_volume=self._extract_engine_volume(vehicle_data),
                fuel_type=vehicle_data.get('fuelType', 'Unknown'),
                transmission=vehicle_data.get('vehicleTransmission', 'Unknown'),
                drive_type=vehicle_data.get('driveWheelConfiguration'),
                color=vehicle_data.get('color'),
                mileage=mileage_str,
                mileage_km=mileage_km,
                lot_number=lot_data.get('entry_number'),
                location=lot_data.get('location', 'South Korea'),
                country=lot_data.get('country', 'KR'),
                auction_date=lot_data.get('auction_date'),
                current_bid=lot_data.get('price_bid'),
                buy_now_price=lot_data.get('price_buy'),
                currency=lot_data.get('currency', 'USD'),
                in_stock=lot_data.get('in_stock', True),
                is_auction=lot_data.get('is_auction', True),
                can_bid=lot_data.get('can_bid', True),
                can_buy=lot_data.get('can_book', False),
                main_image=images[0] if images else None,
                images=images,
                runs_drives=lot_data.get('runs_drive'),
                body_type=lot_data.get('body_type'),
                damage=lot_data.get('damage'),
                detail_url=detail_url,
                similar_url=lot_data.get('similar')
            )
            
            logger.info(f"✅ Successfully parsed car detail for VIN: {car_detail.vin}")
            return car_detail
            
        except Exception as e:
            logger.error(f"❌ Error parsing car detail: {e}")
            return None
    
    def _extract_schema_data(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """Extract schema.org Vehicle JSON-LD data"""
        try:
            # Find the Vehicle schema script tag
            scripts = soup.find_all('script', type='application/ld+json')
            
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    if data.get('@type') == 'Vehicle':
                        return data
                except json.JSONDecodeError:
                    continue
                    
            return None
            
        except Exception as e:
            logger.error(f"Error extracting schema data: {e}")
            return None
    
    def _extract_lot_data(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract additional lot data from HTML components"""
        lot_data = {}
        
        try:
            # Look for Vue.js component data
            sidebar_component = soup.find('single-sidebar-component')
            if sidebar_component and sidebar_component.get(':lot'):
                try:
                    lot_json = sidebar_component.get(':lot')
                    # Parse the JSON-like string (need to handle single quotes)
                    lot_json = lot_json.replace("'", '"')
                    lot_info = json.loads(lot_json)
                    
                    lot_data.update({
                        'country': lot_info.get('country'),
                        'country_name': lot_info.get('country_name'),
                        'entry_number': lot_info.get('entry_number'),
                        'in_stock': lot_info.get('in_stock', True),
                        'is_auction': lot_info.get('is_auction', True),
                        'can_bid': lot_info.get('can_bid', True),
                        'can_book': lot_info.get('can_book', False),
                        'price_bid': lot_info.get('price_bid'),
                        'price_buy': lot_info.get('price_buy'),
                        'final_price': lot_info.get('final_price'),
                        'currency': lot_info.get('currency', 'USD'),
                        'similar': lot_info.get('similar'),
                        'timestamp': lot_info.get('timestamp'),
                        'auction_date': self._timestamp_to_date(lot_info.get('timestamp'))
                    })
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse lot component data: {e}")
            
            # Extract from meta description
            meta_desc = soup.find('meta', {'name': 'description'})
            if meta_desc:
                desc_content = meta_desc.get('content', '')
                # Extract location from description
                if 'from' in desc_content:
                    location_match = re.search(r'from\s+([^&]+)', desc_content)
                    if location_match:
                        lot_data['location'] = location_match.group(1).strip()
            
        except Exception as e:
            logger.error(f"Error extracting lot data: {e}")
            
        return lot_data
    
    def _extract_images(self, soup: BeautifulSoup, vehicle_data: Dict[str, Any]) -> List[str]:
        """Extract all car images"""
        images = []
        
        try:
            # From schema.org data
            if vehicle_data and 'image' in vehicle_data:
                schema_images = vehicle_data['image']
                if isinstance(schema_images, list):
                    for img in schema_images:
                        if isinstance(img, dict) and 'contentUrl' in img:
                            images.append(img['contentUrl'])
                        elif isinstance(img, str):
                            images.append(img)
                elif isinstance(schema_images, dict) and 'contentUrl' in schema_images:
                    images.append(schema_images['contentUrl'])
                elif isinstance(schema_images, str):
                    images.append(schema_images)
            
            # From meta og:image
            og_image = soup.find('meta', {'property': 'og:image'})
            if og_image:
                img_url = og_image.get('content')
                if img_url and img_url not in images:
                    images.append(img_url)
            
            # From gallery if present
            gallery = soup.find('div', class_='gallery')
            if gallery:
                for img in gallery.find_all('img'):
                    src = img.get('src') or img.get('data-src')
                    if src and src not in images:
                        images.append(src)
                        
        except Exception as e:
            logger.error(f"Error extracting images: {e}")
            
        return images
    
    def _parse_mileage(self, vehicle_data: Dict[str, Any], lot_data: Dict[str, Any]) -> tuple:
        """Parse mileage information"""
        mileage_str = "Unknown"
        mileage_km = None
        
        try:
            # From schema.org data
            if vehicle_data and 'mileageFromOdometer' in vehicle_data:
                mileage_info = vehicle_data['mileageFromOdometer']
                if isinstance(mileage_info, dict):
                    value = mileage_info.get('value', 0)
                    unit = mileage_info.get('unitCode', 'KMT')
                    
                    if unit == 'KMT':  # Kilometers
                        mileage_km = int(value)
                        mileage_str = f"{value:,} km"
                    elif unit == 'SMI':  # Miles
                        mileage_km = int(value * 1.60934)
                        mileage_str = f"{value:,} mi"
                        
        except Exception as e:
            logger.error(f"Error parsing mileage: {e}")
            
        return mileage_str, mileage_km
    
    def _extract_manufacturer(self, vehicle_data: Dict[str, Any]) -> str:
        """Extract manufacturer name"""
        if vehicle_data.get('manufacturer'):
            return vehicle_data['manufacturer']
            
        if vehicle_data.get('brand') and isinstance(vehicle_data['brand'], dict):
            return vehicle_data['brand'].get('name', '')
            
        # Fallback: extract from name
        name = vehicle_data.get('name', '')
        parts = name.split()
        if parts:
            return parts[0]
            
        return 'Unknown'
    
    def _extract_model(self, vehicle_data: Dict[str, Any]) -> str:
        """Extract model name"""
        if vehicle_data.get('model'):
            return vehicle_data['model']
            
        # Fallback: extract from name
        name = vehicle_data.get('name', '')
        parts = name.split()
        if len(parts) > 1:
            return ' '.join(parts[1:])
            
        return 'Unknown'
    
    def _extract_engine_volume(self, vehicle_data: Dict[str, Any]) -> Optional[float]:
        """Extract engine volume"""
        try:
            engine = vehicle_data.get('vehicleEngine')
            if engine and isinstance(engine, dict):
                displacement = engine.get('engineDisplacement')
                if displacement:
                    # Parse displacement value (could be string like "2.5L")
                    if isinstance(displacement, (int, float)):
                        return float(displacement)
                    elif isinstance(displacement, str):
                        match = re.search(r'(\d+\.?\d*)', displacement)
                        if match:
                            return float(match.group(1))
        except Exception as e:
            logger.error(f"Error extracting engine volume: {e}")
            
        return None
    
    def _timestamp_to_date(self, timestamp: Optional[int]) -> Optional[str]:
        """Convert timestamp to date string"""
        if not timestamp:
            return None
            
        try:
            from datetime import datetime
            dt = datetime.fromtimestamp(timestamp / 1000)  # Assuming milliseconds
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return None