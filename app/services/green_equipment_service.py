"""
Service for interacting with Green Heavy Equipment (4396200.com) via Oxylabs proxy
Handles equipment catalog and details
"""

from typing import Optional, Dict, Any, List
import logging
from datetime import datetime, timedelta

from app.core.http_client import AsyncHttpClient
from app.models.green_equipment import (
    GreenEquipmentListResponse,
    GreenEquipment,
    GreenEquipmentDetails,
    GreenEquipmentDetailsResponse,
    CategoriesResponse,
    CategoryInfo,
    EQUIPMENT_CATEGORIES,
    EQUIPMENT_SUBCATEGORIES,
)
from app.parsers.green_equipment_parser import GreenEquipmentParser

logger = logging.getLogger(__name__)


class GreenEquipmentCache:
    """Simple in-memory cache with TTL for equipment data"""

    def __init__(self, ttl_seconds: int = 300):  # 5 minutes default TTL
        self.cache: Dict[str, tuple[Any, datetime]] = {}
        self.ttl = timedelta(seconds=ttl_seconds)

    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired"""
        if key in self.cache:
            value, timestamp = self.cache[key]
            if datetime.now() - timestamp < self.ttl:
                logger.debug(f"Cache hit for key: {key}")
                return value
            else:
                logger.debug(f"Cache expired for key: {key}")
                del self.cache[key]
        return None

    def set(self, key: str, value: Any):
        """Set cached value with current timestamp"""
        self.cache[key] = (value, datetime.now())
        logger.debug(f"Cached key: {key}")

    def clear(self):
        """Clear all cached values"""
        self.cache.clear()
        logger.debug("Green equipment cache cleared")

    def delete(self, key: str):
        """Delete specific cache key"""
        if key in self.cache:
            del self.cache[key]
            logger.debug(f"Deleted cache key: {key}")


class GreenEquipmentService:
    """Service for interacting with Green Heavy Equipment website via Oxylabs proxy"""

    # Website URLs
    BASE_URL = "https://www.4396200.com"
    LIST_URL = "https://www.4396200.com/sub8_1.html"
    DETAIL_URL = "https://www.4396200.com/sub8_1_vvv.html"

    def __init__(self):
        # Use proxy-enabled HTTP client for bypassing captcha via Oxylabs
        self.http_client = AsyncHttpClient(timeout=60, use_proxy=True)
        self.cache = GreenEquipmentCache(ttl_seconds=300)  # 5 minute cache
        self.parser = GreenEquipmentParser()

        self.headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "referer": "https://www.4396200.com/",
        }

    async def get_equipment_list(
        self,
        category_code: str = "100",
        subcategory_code: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        manufacturer: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        use_cache: bool = True,
    ) -> GreenEquipmentListResponse:
        """
        Get equipment list from Green Heavy Equipment website

        Args:
            category_code: Category code (100-111)
            subcategory_code: Subcategory code (e.g., 100100, 101102)
            page: Page number
            per_page: Items per page
            manufacturer: Filter by manufacturer (Korean name)
            year_from: Minimum year
            year_to: Maximum year
            min_price: Minimum price in 만원 (10,000 KRW)
            max_price: Maximum price in 만원 (10,000 KRW)
            use_cache: Whether to use caching

        Returns:
            GreenEquipmentListResponse with equipment data
        """
        try:
            # Validate category code
            if category_code not in EQUIPMENT_CATEGORIES:
                return GreenEquipmentListResponse(
                    count=0,
                    items=[],
                    category_code=category_code,
                    page=page,
                    per_page=per_page,
                    success=False,
                    message=f"Invalid category code: {category_code}"
                )

            # Validate subcategory code if provided
            if subcategory_code:
                valid_subcategory = False
                if category_code in EQUIPMENT_SUBCATEGORIES:
                    for sub in EQUIPMENT_SUBCATEGORIES[category_code]:
                        if sub["code"] == subcategory_code:
                            valid_subcategory = True
                            break
                if not valid_subcategory:
                    return GreenEquipmentListResponse(
                        count=0,
                        items=[],
                        category_code=category_code,
                        page=page,
                        per_page=per_page,
                        success=False,
                        message=f"Invalid subcategory code: {subcategory_code} for category {category_code}"
                    )

            # Build cache key including all filter params
            cache_key = f"equipment_list_{category_code}_{subcategory_code}_{page}_{manufacturer}_{year_from}_{year_to}_{min_price}_{max_price}"

            # Check cache if enabled
            if use_cache:
                cached_response = self.cache.get(cache_key)
                if cached_response:
                    logger.info("Returning cached equipment list response")
                    return cached_response

            # Build URL with parameters
            # If subcategory is provided, use sub8_1_s.html with cate_code=subcategory
            # Otherwise use sub8_1.html with cate_code=category
            if subcategory_code:
                url = f"{self.BASE_URL}/sub8_1_s.html?cate_code={subcategory_code}"
            else:
                url = f"{self.LIST_URL}?cate_code={category_code}"

            logger.info(f"Fetching equipment list from {url} via Oxylabs proxy")

            # Fetch HTML from website through Oxylabs proxy
            response = await self.http_client.get(url, headers=self.headers)

            if not response or response.status_code != 200:
                status_code = response.status_code if response else None
                error_msg = f"Failed to fetch equipment list: status {status_code}"
                logger.error(error_msg)
                return GreenEquipmentListResponse(
                    count=0,
                    items=[],
                    category_code=category_code,
                    page=page,
                    per_page=per_page,
                    success=False,
                    message=error_msg
                )

            # Parse HTML response
            html_content = response.text
            equipment_list, total_count = self.parser.parse_list_page(html_content, category_code)

            # Apply filters (client-side since website may not support them)
            filtered_list = equipment_list

            if manufacturer:
                filtered_list = [e for e in filtered_list if e.manufacturer == manufacturer]

            if year_from:
                filtered_list = [e for e in filtered_list if e.year and e.year >= year_from]

            if year_to:
                filtered_list = [e for e in filtered_list if e.year and e.year <= year_to]

            # Filter by price range (price is in 만원 = 10,000 KRW)
            if min_price is not None:
                filtered_list = [e for e in filtered_list if e.price >= min_price]

            if max_price is not None:
                filtered_list = [e for e in filtered_list if e.price <= max_price]

            # Apply pagination (client-side)
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            paginated_list = filtered_list[start_idx:end_idx]

            # Get category name
            category_info = EQUIPMENT_CATEGORIES.get(category_code, {})
            category_name = category_info.get("ko", "")

            # Create response
            list_response = GreenEquipmentListResponse(
                count=len(filtered_list),
                items=paginated_list,
                category_code=category_code,
                category_name=category_name,
                page=page,
                per_page=per_page,
                success=True,
                message=None
            )

            # Cache the response
            if use_cache:
                self.cache.set(cache_key, list_response)

            logger.info(f"Successfully fetched {len(paginated_list)} equipment items (total: {len(filtered_list)})")
            return list_response

        except Exception as e:
            error_msg = f"Error fetching equipment list: {str(e)}"
            logger.error(error_msg)
            return GreenEquipmentListResponse(
                count=0,
                items=[],
                category_code=category_code,
                page=page,
                per_page=per_page,
                success=False,
                message=error_msg
            )

    async def get_equipment_details(
        self,
        equipment_id: str,
        category_code: str = "",
        use_cache: bool = True,
    ) -> GreenEquipmentDetailsResponse:
        """
        Get detailed information for a specific equipment

        Args:
            equipment_id: Equipment ID (pid)
            category_code: Category code if known
            use_cache: Whether to use caching

        Returns:
            GreenEquipmentDetailsResponse with full equipment details
        """
        try:
            # Build cache key
            cache_key = f"equipment_details_{equipment_id}"

            # Check cache if enabled
            if use_cache:
                cached_response = self.cache.get(cache_key)
                if cached_response:
                    logger.info(f"Returning cached equipment details for {equipment_id}")
                    return cached_response

            # Build URL
            url = f"{self.DETAIL_URL}?pid={equipment_id}"

            logger.info(f"Fetching equipment details from {url} via Oxylabs proxy")

            # Fetch HTML from website through Oxylabs proxy
            response = await self.http_client.get(url, headers=self.headers)

            if not response or response.status_code != 200:
                error_msg = f"Failed to fetch equipment details: status {response.status_code if response else 'None'}"
                logger.error(error_msg)
                return GreenEquipmentDetailsResponse(
                    success=False,
                    message=error_msg,
                    data=None
                )

            # Parse HTML response
            html_content = response.text
            details = self.parser.parse_detail_page(html_content, equipment_id, category_code)

            if not details:
                return GreenEquipmentDetailsResponse(
                    success=False,
                    message=f"Failed to parse equipment details for {equipment_id}",
                    data=None
                )

            details_response = GreenEquipmentDetailsResponse(
                success=True,
                message=None,
                data=details
            )

            # Cache the response
            if use_cache:
                self.cache.set(cache_key, details_response)

            logger.info(f"Successfully fetched equipment details for {equipment_id}")
            return details_response

        except Exception as e:
            error_msg = f"Error fetching equipment details: {str(e)}"
            logger.error(error_msg)
            return GreenEquipmentDetailsResponse(
                success=False,
                message=error_msg,
                data=None
            )

    async def get_all_categories(self) -> CategoriesResponse:
        """
        Get all available equipment categories

        Returns:
            CategoriesResponse with list of categories
        """
        try:
            categories = []
            for code, info in EQUIPMENT_CATEGORIES.items():
                categories.append(CategoryInfo(
                    code=code,
                    name_ko=info.get("ko", ""),
                    name_en=info.get("en", ""),
                    name_ru=info.get("ru", ""),
                ))

            return CategoriesResponse(
                success=True,
                message=None,
                categories=categories
            )

        except Exception as e:
            error_msg = f"Error getting categories: {str(e)}"
            logger.error(error_msg)
            return CategoriesResponse(
                success=False,
                message=error_msg,
                categories=[]
            )

    async def get_all_equipment(
        self,
        page: int = 1,
        per_page: int = 21,
        category_code: Optional[str] = None,
        use_cache: bool = True,
    ) -> GreenEquipmentListResponse:
        """
        Get equipment from all categories or a specific category

        Args:
            page: Page number
            per_page: Items per page
            category_code: Optional category filter
            use_cache: Whether to use caching

        Returns:
            GreenEquipmentListResponse with equipment from all/selected categories
        """
        try:
            all_equipment = []

            # If specific category, just fetch that one
            if category_code:
                return await self.get_equipment_list(
                    category_code=category_code,
                    page=page,
                    per_page=per_page,
                    use_cache=use_cache
                )

            # Otherwise fetch from all categories
            for cat_code in EQUIPMENT_CATEGORIES.keys():
                response = await self.get_equipment_list(
                    category_code=cat_code,
                    page=1,
                    per_page=100,  # Get more items per category
                    use_cache=use_cache
                )
                if response.success and response.items:
                    all_equipment.extend(response.items)

            # Sort by some criteria (e.g., price or registration date)
            # For now, just return as-is

            # Apply pagination
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            paginated_list = all_equipment[start_idx:end_idx]

            return GreenEquipmentListResponse(
                count=len(all_equipment),
                items=paginated_list,
                page=page,
                per_page=per_page,
                success=True,
                message=None
            )

        except Exception as e:
            error_msg = f"Error fetching all equipment: {str(e)}"
            logger.error(error_msg)
            return GreenEquipmentListResponse(
                count=0,
                items=[],
                page=page,
                per_page=per_page,
                success=False,
                message=error_msg
            )

    def clear_cache(self):
        """Clear all cached equipment data"""
        self.cache.clear()
        logger.info("Green equipment service cache cleared")


# Singleton instance
green_equipment_service = GreenEquipmentService()
