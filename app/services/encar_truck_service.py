"""
Service for interacting with Encar Truck API via Oxylabs proxy
Handles truck catalog and vehicle details
"""

from typing import Optional, Dict, Any
import logging
from datetime import datetime, timedelta
from urllib.parse import urlencode

from app.core.http_client import AsyncHttpClient
from app.models.encar_truck import (
    EncarTruckListResponse,
    EncarTruck,
    EncarTruckDetails,
    EncarTruckDetailsResponse,
    TruckDetailPhoto,
)

logger = logging.getLogger(__name__)


class EncarTruckCache:
    """Simple in-memory cache with TTL for truck data"""

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
        logger.debug("Truck cache cleared")

    def delete(self, key: str):
        """Delete specific cache key"""
        if key in self.cache:
            del self.cache[key]
            logger.debug(f"Deleted cache key: {key}")


class EncarTruckService:
    """Service for interacting with Encar Truck API via Oxylabs proxy"""

    # Encar API URLs
    TRUCK_LIST_URL = "http://api.encar.com/search/truck/list/general"
    VEHICLE_DETAILS_URL = "http://api.encar.com/v1/readside/vehicle"

    # Default query for trucks with EncarDiagnosis
    DEFAULT_QUERY = "(And.Hidden.N._.(Or.ServiceMark.EncarDiagnosisP0._.ServiceMark.EncarDiagnosisP1._.ServiceMark.EncarDiagnosisP2.))"

    def __init__(self):
        # Use proxy-enabled HTTP client for direct Encar access via Oxylabs
        self.http_client = AsyncHttpClient(timeout=60, use_proxy=True)
        self.cache = EncarTruckCache(ttl_seconds=300)  # 5 minute cache

        self.headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "origin": "https://www.encar.com",
            "referer": "https://www.encar.com/",
        }

    async def get_trucks(
        self,
        q: str = None,
        sr: str = "|ModifiedDate|0|21",
        count: bool = True,
        use_cache: bool = True,
    ) -> EncarTruckListResponse:
        """
        Get Encar truck catalog listings

        Args:
            q: Query string for filters (uses DEFAULT_QUERY if not provided)
            sr: Sort and pagination string (format: |SortField|Offset|Limit)
            count: Whether to return total count
            use_cache: Whether to use caching

        Returns:
            EncarTruckListResponse with trucks data
        """
        try:
            # Use default query if not provided
            if q is None:
                q = self.DEFAULT_QUERY

            # Build cache key
            cache_key = f"trucks_{q}_{sr}_{count}"

            # Check cache if enabled
            if use_cache:
                cached_response = self.cache.get(cache_key)
                if cached_response:
                    logger.info("Returning cached truck catalog response")
                    return cached_response

            # Build query parameters
            params = {
                "q": q,
                "sr": sr,
                "count": "true" if count else "false",
            }

            # Build URL
            url = f"{self.TRUCK_LIST_URL}?{urlencode(params)}"

            logger.info(f"Fetching Encar truck catalog via Oxylabs proxy: {url}")

            # Fetch data from Encar API through Oxylabs proxy
            response = await self.http_client.get(url, headers=self.headers)

            if not response or response.status_code != 200:
                error_msg = f"Failed response from Encar Truck API: status {response.status_code if response else 'None'}"
                logger.error(error_msg)
                return EncarTruckListResponse(
                    Count=0,
                    SearchResults=[],
                    success=False,
                    message=error_msg
                )

            # Parse JSON response
            response_data = response.json()
            count_value = response_data.get("Count", 0)
            search_results = response_data.get("SearchResults", [])

            # Create response with parsed trucks
            trucks = []
            for truck_data in search_results:
                try:
                    trucks.append(EncarTruck(**truck_data))
                except Exception as e:
                    logger.warning(f"Failed to parse truck: {e}")
                    continue

            catalog_response = EncarTruckListResponse(
                Count=count_value,
                SearchResults=trucks,
                success=True,
                message=None
            )

            # Cache the response
            if use_cache:
                self.cache.set(cache_key, catalog_response)

            logger.info(f"Successfully fetched {len(trucks)} trucks from Encar")
            return catalog_response

        except Exception as e:
            error_msg = f"Error fetching Encar truck catalog: {str(e)}"
            logger.error(error_msg)
            return EncarTruckListResponse(
                Count=0,
                SearchResults=[],
                success=False,
                message=error_msg
            )

    async def get_truck_details(
        self,
        vehicle_id: str,
        use_cache: bool = True,
    ) -> EncarTruckDetailsResponse:
        """
        Get detailed information for a specific truck

        Args:
            vehicle_id: The vehicle ID from Encar
            use_cache: Whether to use caching

        Returns:
            EncarTruckDetailsResponse with full truck details
        """
        try:
            # Build cache key
            cache_key = f"truck_details_{vehicle_id}"

            # Check cache if enabled
            if use_cache:
                cached_response = self.cache.get(cache_key)
                if cached_response:
                    logger.info(f"Returning cached truck details for {vehicle_id}")
                    return cached_response

            # Build URL
            url = f"{self.VEHICLE_DETAILS_URL}/{vehicle_id}"

            logger.info(f"Fetching truck details via Oxylabs proxy: {url}")

            # Fetch data from Encar API through Oxylabs proxy
            response = await self.http_client.get(url, headers=self.headers)

            if not response or response.status_code != 200:
                error_msg = f"Failed to get truck details: status {response.status_code if response else 'None'}"
                logger.error(error_msg)
                return EncarTruckDetailsResponse(
                    success=False,
                    message=error_msg,
                    data=None
                )

            # Parse JSON response
            response_data = response.json()

            # Parse photos separately to handle any issues
            photos = []
            for photo_data in response_data.get("photos", []):
                try:
                    photos.append(TruckDetailPhoto(**photo_data))
                except Exception as e:
                    logger.warning(f"Failed to parse photo: {e}")
                    continue

            # Create truck details object
            try:
                truck_details = EncarTruckDetails(
                    vehicleId=response_data.get("vehicleId"),
                    vehicleType=response_data.get("vehicleType", "TRUCK"),
                    vehicleNo=response_data.get("vehicleNo"),
                    vin=response_data.get("vin"),
                    manage=response_data.get("manage"),
                    category=response_data.get("category"),
                    advertisement=response_data.get("advertisement"),
                    contact=response_data.get("contact"),
                    spec=response_data.get("spec"),
                    photos=photos,
                    options=response_data.get("options"),
                    condition=response_data.get("condition"),
                    partnership=response_data.get("partnership"),
                    contents=response_data.get("contents"),
                    view=response_data.get("view"),
                )
            except Exception as e:
                error_msg = f"Failed to parse truck details: {str(e)}"
                logger.error(error_msg)
                return EncarTruckDetailsResponse(
                    success=False,
                    message=error_msg,
                    data=None
                )

            details_response = EncarTruckDetailsResponse(
                success=True,
                message=None,
                data=truck_details
            )

            # Cache the response
            if use_cache:
                self.cache.set(cache_key, details_response)

            logger.info(f"Successfully fetched truck details for {vehicle_id}")
            return details_response

        except Exception as e:
            error_msg = f"Error fetching truck details: {str(e)}"
            logger.error(error_msg)
            return EncarTruckDetailsResponse(
                success=False,
                message=error_msg,
                data=None
            )

    def clear_cache(self):
        """Clear all cached truck data"""
        self.cache.clear()
        logger.info("Encar truck service cache cleared")


# Singleton instance
encar_truck_service = EncarTruckService()
