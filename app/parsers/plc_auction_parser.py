import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup
from app.models.plc_auction import (
    PLCAuctionCar, PLCAuctionProduct, PLCAuctionOffer,
    PLCAuctionManufacturer, PLCAuctionModel, MileageInfo
)

logger = logging.getLogger(__name__)


class PLCAuctionParser:
    @staticmethod
    def extract_json_ld_data(html: str) -> Optional[PLCAuctionProduct]:
        """Extract JSON-LD structured data from HTML containing car listings"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find all script tags with type="application/ld+json"
            json_ld_scripts = soup.find_all('script', type='application/ld+json')
            
            for script in json_ld_scripts:
                try:
                    data = json.loads(script.string)
                    
                    # Look for Product type with offers
                    if data.get('@type') == 'Product' and 'offers' in data:
                        return PLCAuctionProduct(**data)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON-LD script: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Error processing JSON-LD data: {e}")
                    continue
            
            logger.warning("No Product JSON-LD data found in HTML")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting JSON-LD data: {e}")
            return None

    @staticmethod
    def parse_cars_from_json_ld(product_data: PLCAuctionProduct) -> Tuple[List[PLCAuctionCar], int]:
        """Parse cars from JSON-LD Product data"""
        cars = []
        total_count = product_data.offers.offer_count
        
        for offer in product_data.offers.offers:
            try:
                car_data = offer.item_offered
                
                # Convert mileage from MileageInfo to formatted string
                if hasattr(car_data, 'mileage_info') and car_data.mileage_info:
                    mileage_value = car_data.mileage_info.value
                    car_data.mileage = f"{mileage_value:,} Km"
                
                # Format transmission for frontend compatibility
                if car_data.transmission == "Automatic":
                    car_data.transmission = "A/T"
                elif car_data.transmission == "Manual":
                    car_data.transmission = "M/T"
                
                # Ensure brand is uppercase for frontend compatibility
                if hasattr(car_data, 'brand'):
                    car_data.brand = car_data.brand.upper()
                
                # Set price from offer
                car_data.starting_price = offer.price
                car_data.currency = offer.price_currency
                
                # Generate a unique car number (could be extracted from image URL or other source)
                if not car_data.car_no and car_data.main_image_url:
                    # Extract potential ID from image URL
                    parts = car_data.main_image_url.split('/')
                    if len(parts) > 6:
                        car_data.car_no = f"{parts[6]}_{parts[7]}"
                
                cars.append(car_data)
                
            except Exception as e:
                logger.error(f"Error parsing car from offer: {e}")
                continue
        
        return cars, total_count

    @staticmethod
    def parse_cars_from_html(html: str) -> Tuple[List[PLCAuctionCar], int]:
        """Main parsing method that extracts cars from HTML"""
        try:
            # First try to extract JSON-LD data
            product_data = PLCAuctionParser.extract_json_ld_data(html)
            
            if product_data:
                return PLCAuctionParser.parse_cars_from_json_ld(product_data)
            
            # Fallback: parse HTML directly if no JSON-LD data
            return PLCAuctionParser._parse_html_fallback(html)
            
        except Exception as e:
            logger.error(f"Error parsing cars from HTML: {e}")
            return [], 0

    @staticmethod
    def _parse_html_fallback(html: str) -> Tuple[List[PLCAuctionCar], int]:
        """Fallback method to parse cars directly from HTML if JSON-LD is not available"""
        cars = []
        total_count = 0
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for Vue.js listing component to get total count
            listing_elem = soup.find('listing')
            if listing_elem and listing_elem.get(':count'):
                try:
                    total_count = int(listing_elem.get(':count'))
                except ValueError:
                    pass
            
            # Look for car cards or listings in the HTML
            # This is a placeholder - actual implementation would depend on HTML structure
            logger.info("Using HTML fallback parser - JSON-LD not found")
            
        except Exception as e:
            logger.error(f"Error in HTML fallback parser: {e}")
        
        return cars, total_count

    @staticmethod
    def extract_pagination_info(html: str, current_page: int, page_size: int) -> Dict[str, Any]:
        """Extract pagination information from HTML"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for Vue.js listing component
            listing_elem = soup.find('listing')
            if listing_elem:
                total_count = int(listing_elem.get(':count', 0))
                total_pages = int(listing_elem.get(':pages', 1))
                
                return {
                    'total_count': total_count,
                    'total_pages': total_pages,
                    'has_next_page': current_page < total_pages,
                    'has_prev_page': current_page > 1
                }
            
            return {
                'total_count': 0,
                'total_pages': 1,
                'has_next_page': False,
                'has_prev_page': False
            }
            
        except Exception as e:
            logger.error(f"Error extracting pagination info: {e}")
            return {
                'total_count': 0,
                'total_pages': 1,
                'has_next_page': False,
                'has_prev_page': False
            }

    @staticmethod
    def extract_filters_from_html(html: str) -> Dict[str, List[Dict[str, Any]]]:
        """Extract available filters from HTML"""
        filters = {
            'manufacturers': [],
            'models': [],
            'fuel_types': [],
            'transmissions': [],
            'colors': []
        }
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract filter options from HTML
            # This would need to be implemented based on actual HTML structure
            
            logger.info("Filter extraction not fully implemented - returning empty filters")
            
        except Exception as e:
            logger.error(f"Error extracting filters: {e}")
        
        return filters