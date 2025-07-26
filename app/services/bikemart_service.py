from typing import Optional, Dict, Any, List
import logging
import asyncio
from datetime import datetime

from app.core.http_client import AsyncHttpClient
from app.models.bikemart import (
    BikemartResponse,
    BikemartBrandsResponse,
    BikemartFiltersResponse,
    BikemartError,
    BikemartBike,
    BikemartPaginationInfo,
    BikemartFilter,
    BikemartBikeDetailResponse,
    BikemartBikeDetail,
    BikemartModelsResponse,
    BikemartModel
)
from app.parsers.bikemart_parser import BikemartParser

logger = logging.getLogger(__name__)


class BikemartService:
    """Service for interacting with Bikemart API"""
    
    BASE_URL = "https://shop.bikemart.co.kr/api/index.php"
    
    def __init__(self):
        self.parser = BikemartParser()
        self.http_client = AsyncHttpClient(timeout=30)
        
        # Default headers from the example
        self.headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "content-type": "application/x-www-form-urlencoded;charset=utf-8;",
            "origin": "https://bikeweb.bikemart.co.kr",
            "priority": "u=1, i",
            "referer": "https://bikeweb.bikemart.co.kr/",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        }
    
    async def get_bikes(
        self,
        page: int = 1,
        brand_seq: Optional[str] = None,
        model: Optional[str] = None,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_mileage: Optional[int] = None,
        max_mileage: Optional[int] = None,
        search_text: Optional[str] = None,
        sort_by: Optional[str] = None
    ) -> BikemartResponse:
        """
        Get bikes listing with optional filters
        
        Args:
            page: Page number (default: 1)
            brand_seq: Brand sequence ID
            model: Model name
            min_year: Minimum year
            max_year: Maximum year
            min_price: Minimum price (in 만원)
            max_price: Maximum price (in 만원)
            min_mileage: Minimum mileage
            max_mileage: Maximum mileage
            search_text: Search text
            sort_by: Sort option
            
        Returns:
            BikemartResponse with bikes data
        """
        try:
            # Build query parameters
            params = {
                "page": str(page),
                "gbn": "1000",  # Direct transaction type
                "seq": "",
                "searchText": search_text or "",
                "rgm": "",
                "rgd": "",
                "bbs": brand_seq or "",
                "bms": model or "",
                "bsc": "",
                "syr": str(min_year) if min_year else "",
                "eyr": str(max_year) if max_year else "",
                "spt": str(min_price) if min_price else "",
                "ept": str(max_price) if max_price else "",
                "spc": str(min_mileage) if min_mileage else "",
                "epc": str(max_mileage) if max_mileage else "",
                "sos": sort_by or "",
                "product_gbn": "BIKE",
                "program": "bike",
                "service": "sell",
                "version": "1.0",
                "action": "getBikeSellList",
                "token": "",
            }
            
            # Make API request
            response = await self.http_client.get(
                self.BASE_URL,
                params=params,
                headers=self.headers
            )
            
            if response.status_code != 200:
                logger.error(f"API returned status code: {response.status_code}")
                return BikemartResponse(
                    success=False,
                    data=[],
                    message=f"API error: {response.status_code}"
                )
            
            # Parse response
            response_data = response.json()
            bikes, pagination = self.parser.parse_bikes_response(response_data)
            
            # Calculate pagination if not provided
            if not pagination:
                total_count = self.parser.parse_total_count(response_data)
                items_per_page = 20  # Default items per page
                pagination = BikemartPaginationInfo(
                    current_page=page,
                    total_pages=max(1, (total_count + items_per_page - 1) // items_per_page),
                    total_count=total_count,
                    items_per_page=items_per_page
                )
            
            return BikemartResponse(
                success=True,
                data=bikes,
                pagination=pagination,
                message=response_data.get("ResultMessage", "")
            )
            
        except Exception as e:
            logger.error(f"Error fetching bikes: {e}")
            return BikemartResponse(
                success=False,
                data=[],
                message=f"Error fetching bikes: {str(e)}"
            )
    
    async def get_brands(self) -> BikemartBrandsResponse:
        """
        Get available bike brands
        
        Returns:
            BikemartBrandsResponse with brands data
        """
        try:
            # Build query parameters for getting brands
            params = {
                "program": "bike",
                "service": "sell",
                "version": "1.0",
                "action": "getBikeBrandList",
                "token": "",
            }
            
            # Make API request
            response = await self.http_client.get(
                self.BASE_URL,
                params=params,
                headers=self.headers
            )
            
            if response.status_code != 200:
                logger.error(f"API returned status code: {response.status_code}")
                return BikemartBrandsResponse(
                    success=False,
                    data=[],
                    message=f"API error: {response.status_code}"
                )
            
            # Parse response
            response_data = response.json()
            brands = self.parser.parse_brands_response(response_data)
            
            return BikemartBrandsResponse(
                success=True,
                data=brands,
                message=response_data.get("ResultMessage", "")
            )
            
        except Exception as e:
            logger.error(f"Error fetching brands: {e}")
            return BikemartBrandsResponse(
                success=False,
                data=[],
                message=f"Error fetching brands: {str(e)}"
            )
    
    async def get_filters(self) -> BikemartFiltersResponse:
        """
        Get available filter options
        
        Returns:
            BikemartFiltersResponse with filter options
        """
        try:
            # For filters, we'll create static options based on common ranges
            # In a real implementation, you might want to fetch these dynamically
            
            # Year filters
            current_year = datetime.now().year
            years = []
            for year in range(current_year, 1990, -1):
                years.append(BikemartFilter(
                    value=str(year),
                    label=str(year)
                ))
            
            # Mileage ranges
            mileage_ranges = [
                BikemartFilter(value="0-10000", label="0~10,000km"),
                BikemartFilter(value="10000-30000", label="10,000~30,000km"),
                BikemartFilter(value="30000-50000", label="30,000~50,000km"),
                BikemartFilter(value="50000-100000", label="50,000~100,000km"),
                BikemartFilter(value="100000+", label="100,000km+")
            ]
            
            # Price ranges (in 만원)
            price_ranges = [
                BikemartFilter(value="0-100", label="~100만원"),
                BikemartFilter(value="100-200", label="100~200만원"),
                BikemartFilter(value="200-300", label="200~300만원"),
                BikemartFilter(value="300-500", label="300~500만원"),
                BikemartFilter(value="500-1000", label="500~1,000만원"),
                BikemartFilter(value="1000+", label="1,000만원+")
            ]
            
            # Get brands for brand filter
            brands_response = await self.get_brands()
            brand_filters = []
            if brands_response.success:
                for brand in brands_response.data:
                    brand_filters.append(BikemartFilter(
                        value=brand.brand_seq,
                        label=brand.brand_name,
                        count=brand.count
                    ))
            
            # Regions (major cities in Korea)
            regions = [
                BikemartFilter(value="seoul", label="서울"),
                BikemartFilter(value="gyeonggi", label="경기"),
                BikemartFilter(value="incheon", label="인천"),
                BikemartFilter(value="busan", label="부산"),
                BikemartFilter(value="daegu", label="대구"),
                BikemartFilter(value="gwangju", label="광주"),
                BikemartFilter(value="daejeon", label="대전"),
                BikemartFilter(value="ulsan", label="울산"),
            ]
            
            return BikemartFiltersResponse(
                success=True,
                brands=brand_filters,
                years=years,
                mileage_ranges=mileage_ranges,
                price_ranges=price_ranges,
                regions=regions
            )
            
        except Exception as e:
            logger.error(f"Error fetching filters: {e}")
            return BikemartFiltersResponse(
                success=False,
                brands=[],
                years=[],
                mileage_ranges=[],
                price_ranges=[],
                regions=[],
                message=f"Error fetching filters: {str(e)}"
            )
    
    async def get_bike_detail(self, seq: str) -> BikemartBikeDetailResponse:
        """
        Get detailed bike information by sequence ID
        
        Args:
            seq: Bike sequence ID
            
        Returns:
            BikemartBikeDetailResponse with bike detail data
        """
        try:
            # Build query parameters for getting bike detail
            params = {
                "seq": seq,
                "program": "bike",
                "service": "sell",
                "version": "1.0",
                "action": "getBikeSellDetail",
                "token": "",
            }
            
            # Make API request
            response = await self.http_client.get(
                self.BASE_URL,
                params=params,
                headers=self.headers
            )
            
            if response.status_code != 200:
                logger.error(f"API returned status code: {response.status_code}")
                return BikemartBikeDetailResponse(
                    success=False,
                    data=None,
                    message=f"API error: {response.status_code}"
                )
            
            # Parse response
            response_data = response.json()
            bike_detail = self.parser.parse_bike_detail_response(response_data)
            
            if not bike_detail:
                return BikemartBikeDetailResponse(
                    success=False,
                    data=None,
                    message="Failed to parse bike detail"
                )
            
            return BikemartBikeDetailResponse(
                success=True,
                data=bike_detail,
                message=response_data.get("ResultMessage", "")
            )
            
        except Exception as e:
            logger.error(f"Error fetching bike detail: {e}")
            return BikemartBikeDetailResponse(
                success=False,
                data=None,
                message=f"Error fetching bike detail: {str(e)}"
            )
    
    async def get_models_by_brand(self, brand_seq: str) -> BikemartModelsResponse:
        """
        Get bike models for a specific brand
        
        Args:
            brand_seq: Brand sequence ID
            
        Returns:
            BikemartModelsResponse with models data
        """
        try:
            # Build query parameters for getting models
            params = {
                "brand": brand_seq,
                "program": "bike",
                "service": "sell",
                "version": "1.0",
                "action": "getBikeModel",
                "token": "",
            }
            
            # Make API request
            response = await self.http_client.get(
                self.BASE_URL,
                params=params,
                headers=self.headers
            )
            
            if response.status_code != 200:
                logger.error(f"API returned status code: {response.status_code}")
                return BikemartModelsResponse(
                    success=False,
                    data=[],
                    message=f"API error: {response.status_code}"
                )
            
            # Parse response
            response_data = response.json()
            models = self.parser.parse_models_response(response_data)
            
            return BikemartModelsResponse(
                success=True,
                data=models,
                message=response_data.get("ResultMessage", "")
            )
            
        except Exception as e:
            logger.error(f"Error fetching models: {e}")
            return BikemartModelsResponse(
                success=False,
                data=[],
                message=f"Error fetching models: {str(e)}"
            )


# Create singleton instance
bikemart_service = BikemartService()