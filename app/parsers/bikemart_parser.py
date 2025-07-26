from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import logging

from app.models.bikemart import (
    BikemartBike, 
    BikemartFilter, 
    BikemartBrand,
    BikemartPaginationInfo
)

logger = logging.getLogger(__name__)


class BikemartParser:
    """Parser for Bikemart API responses"""
    
    @staticmethod
    def parse_bikes_response(response_data: Dict[str, Any]) -> tuple[List[BikemartBike], Optional[BikemartPaginationInfo]]:
        """
        Parse bikes listing response from Bikemart API
        
        Args:
            response_data: Raw JSON response from API
            
        Returns:
            Tuple of (bikes list, pagination info)
        """
        try:
            bikes = []
            
            # Check if response is successful
            if not response_data.get("ResultCode"):
                logger.error("Invalid response: ResultCode is False")
                return [], None
            
            # Extract bikes data
            bikes_data = response_data.get("data", [])
            for bike_data in bikes_data:
                try:
                    bike = BikemartBike(**bike_data)
                    bikes.append(bike)
                except Exception as e:
                    logger.error(f"Error parsing bike data: {e}")
                    continue
            
            # Extract pagination info if available
            pagination = None
            if "pagination" in response_data:
                try:
                    pagination = BikemartPaginationInfo(**response_data["pagination"])
                except Exception as e:
                    logger.error(f"Error parsing pagination: {e}")
            
            return bikes, pagination
            
        except Exception as e:
            logger.error(f"Error parsing bikes response: {e}")
            return [], None
    
    @staticmethod
    def parse_brands_response(response_data: Dict[str, Any]) -> List[BikemartBrand]:
        """
        Parse brands response from Bikemart API
        
        Args:
            response_data: Raw JSON response from API
            
        Returns:
            List of brands
        """
        try:
            brands = []
            
            # Check if response is successful
            if not response_data.get("ResultCode"):
                logger.error("Invalid response: ResultCode is False")
                return []
            
            # Extract brands data
            brands_data = response_data.get("data", [])
            for brand_data in brands_data:
                try:
                    # Transform the data to match our model
                    brand = BikemartBrand(
                        brand_seq=brand_data.get("Value", ""),
                        brand_name=brand_data.get("Name", ""),
                        count=brand_data.get("Count", 0)
                    )
                    brands.append(brand)
                except Exception as e:
                    logger.error(f"Error parsing brand data: {e}")
                    continue
            
            return brands
            
        except Exception as e:
            logger.error(f"Error parsing brands response: {e}")
            return []
    
    @staticmethod
    def extract_filters_from_page(html_content: str) -> Dict[str, List[BikemartFilter]]:
        """
        Extract filter options from HTML page
        
        Args:
            html_content: HTML content of the page
            
        Returns:
            Dictionary of filter categories and their options
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            filters = {
                "brands": [],
                "years": [],
                "mileage_ranges": [],
                "price_ranges": [],
                "regions": []
            }
            
            # Extract brand filters
            brand_select = soup.find('select', {'id': 'brandSelect'})
            if brand_select:
                for option in brand_select.find_all('option'):
                    if option.get('value'):
                        filters["brands"].append(BikemartFilter(
                            value=option.get('value', ''),
                            label=option.text.strip()
                        ))
            
            # Extract year filters (generate common year ranges)
            current_year = 2025
            for year in range(current_year, 1990, -1):
                filters["years"].append(BikemartFilter(
                    value=str(year),
                    label=str(year)
                ))
            
            # Common mileage ranges
            mileage_ranges = [
                ("0-10000", "0~10,000km"),
                ("10000-30000", "10,000~30,000km"),
                ("30000-50000", "30,000~50,000km"),
                ("50000-100000", "50,000~100,000km"),
                ("100000+", "100,000km+")
            ]
            for value, label in mileage_ranges:
                filters["mileage_ranges"].append(BikemartFilter(
                    value=value,
                    label=label
                ))
            
            # Common price ranges (in 만원)
            price_ranges = [
                ("0-100", "~100만원"),
                ("100-200", "100~200만원"),
                ("200-300", "200~300만원"),
                ("300-500", "300~500만원"),
                ("500-1000", "500~1,000만원"),
                ("1000+", "1,000만원+")
            ]
            for value, label in price_ranges:
                filters["price_ranges"].append(BikemartFilter(
                    value=value,
                    label=label
                ))
            
            return filters
            
        except Exception as e:
            logger.error(f"Error extracting filters: {e}")
            return {
                "brands": [],
                "years": [],
                "mileage_ranges": [],
                "price_ranges": [],
                "regions": []
            }
    
    @staticmethod
    def parse_total_count(response_data: Dict[str, Any]) -> int:
        """
        Extract total count from response
        
        Args:
            response_data: Raw JSON response from API
            
        Returns:
            Total count of items
        """
        try:
            # Try different possible locations for total count
            if "totalCount" in response_data:
                return int(response_data["totalCount"])
            elif "total" in response_data:
                return int(response_data["total"])
            elif "pagination" in response_data and "total_count" in response_data["pagination"]:
                return int(response_data["pagination"]["total_count"])
            else:
                # If no total count, return the length of data array
                return len(response_data.get("data", []))
        except Exception as e:
            logger.error(f"Error parsing total count: {e}")
            return 0