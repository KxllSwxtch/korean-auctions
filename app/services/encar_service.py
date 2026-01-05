from typing import Optional, Dict, Any, List
import logging
import asyncio
from datetime import datetime, timedelta
from urllib.parse import urlencode

from app.core.http_client import AsyncHttpClient
from app.models.encar import (
    EncarCatalogResponse,
    EncarFiltersResponse,
    EncarFilterOption,
    EncarCar,
    EncarError,
)

logger = logging.getLogger(__name__)


class EncarCache:
    """Simple in-memory cache with TTL"""

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
        logger.debug("Cache cleared")

    def delete(self, key: str):
        """Delete specific cache key"""
        if key in self.cache:
            del self.cache[key]
            logger.debug(f"Deleted cache key: {key}")


class EncarService:
    """Service for interacting with Encar API via Oxylabs proxy"""

    # Direct Encar API URL
    ENCAR_API_URL = "http://api.encar.com"

    def __init__(self):
        # Use proxy-enabled HTTP client for direct Encar access
        self.http_client = AsyncHttpClient(timeout=60, use_proxy=True)
        self.cache = EncarCache(ttl_seconds=300)  # 5 minute cache

        self.headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "origin": "http://www.encar.com",
            "referer": "http://www.encar.com/",
        }

    async def get_catalog(
        self,
        q: str = "(And.Hidden.N._.CarType.A._.SellType.%EC%9D%BC%EB%B0%98.)",
        sr: str = "|ModifiedDate|0|21",
        count: bool = True,
        page: int = 1,
        use_cache: bool = True,
    ) -> EncarCatalogResponse:
        """
        Get Encar catalog listings

        Args:
            q: Query string for filters
            sr: Sort and pagination string (format: |SortField|SortOrder|Limit)
            count: Whether to return total count
            page: Page number
            use_cache: Whether to use caching

        Returns:
            EncarCatalogResponse with cars data
        """
        try:
            # Build cache key
            cache_key = f"catalog_{q}_{sr}_{count}_{page}"

            # Check cache if enabled
            if use_cache:
                cached_response = self.cache.get(cache_key)
                if cached_response:
                    logger.info("Returning cached catalog response")
                    return cached_response

            # Build query parameters
            params = {
                "q": q,
                "sr": sr,
                "count": "true" if count else "false",
            }

            # Build URL - Direct Encar API with Oxylabs proxy
            url = f"{self.ENCAR_API_URL}/search/car/list/premium?{urlencode(params)}"

            logger.info(f"Fetching Encar catalog via Oxylabs proxy: {url}")

            # Fetch data from Encar API through Oxylabs proxy
            response = await self.http_client.get(url, headers=self.headers)

            if not response or response.status_code != 200:
                error_msg = f"Failed response from Encar API: status {response.status_code if response else 'None'}"
                logger.error(error_msg)
                return EncarCatalogResponse(
                    Count=0,
                    SearchResults=[],
                    success=False,
                    message=error_msg
                )

            # Parse JSON response
            response_data = response.json()
            count_value = response_data.get("Count", 0)
            search_results = response_data.get("SearchResults", [])

            # Create response
            catalog_response = EncarCatalogResponse(
                Count=count_value,
                SearchResults=[EncarCar(**car) for car in search_results],
                success=True,
                message=None
            )

            # Cache the response
            if use_cache:
                self.cache.set(cache_key, catalog_response)

            logger.info(f"Successfully fetched {len(search_results)} cars from Encar")
            return catalog_response

        except Exception as e:
            error_msg = f"Error fetching Encar catalog: {str(e)}"
            logger.error(error_msg)
            return EncarCatalogResponse(
                Count=0,
                SearchResults=[],
                success=False,
                message=error_msg
            )

    async def get_filters(
        self,
        manufacturer: Optional[str] = None,
        model_group: Optional[str] = None,
        model: Optional[str] = None,
        configuration: Optional[str] = None,
        badge: Optional[str] = None,
        use_cache: bool = True,
    ) -> EncarFiltersResponse:
        """
        Get all available filters in a single call

        This method batches multiple filter requests to reduce API calls

        Args:
            manufacturer: Selected manufacturer to filter dependent options
            model_group: Selected model group
            model: Selected model
            configuration: Selected configuration
            badge: Selected badge
            use_cache: Whether to use caching

        Returns:
            EncarFiltersResponse with all filter options
        """
        try:
            # Build cache key
            cache_key = f"filters_{manufacturer}_{model_group}_{model}_{configuration}_{badge}"

            # Check cache if enabled
            if use_cache:
                cached_response = self.cache.get(cache_key)
                if cached_response:
                    logger.info("Returning cached filters response")
                    return cached_response

            # For now, we'll make parallel requests to the proxy
            # In the future, this should be a single batched endpoint
            tasks = []

            # Fetch manufacturers
            tasks.append(self._fetch_filter_option("manufacturer", None))

            # Fetch model groups if manufacturer selected
            if manufacturer:
                tasks.append(self._fetch_filter_option("modelGroup", {"manufacturer": manufacturer}))

            # Fetch models if model group selected
            if model_group:
                tasks.append(self._fetch_filter_option("model", {"manufacturer": manufacturer, "modelGroup": model_group}))

            # Execute all tasks in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Parse results
            manufacturers = results[0] if len(results) > 0 and not isinstance(results[0], Exception) else []
            model_groups = results[1] if len(results) > 1 and not isinstance(results[1], Exception) else []
            models = results[2] if len(results) > 2 and not isinstance(results[2], Exception) else []

            # Create response
            filters_response = EncarFiltersResponse(
                success=True,
                message=None,
                manufacturers=manufacturers,
                modelGroups=model_groups,
                models=models,
                configurations=[],  # TODO: Implement when endpoint available
                badges=[],  # TODO: Implement when endpoint available
                badgeDetails=[],  # TODO: Implement when endpoint available
            )

            # Cache the response
            if use_cache:
                self.cache.set(cache_key, filters_response)

            logger.info("Successfully fetched Encar filters")
            return filters_response

        except Exception as e:
            error_msg = f"Error fetching Encar filters: {str(e)}"
            logger.error(error_msg)
            return EncarFiltersResponse(
                success=False,
                message=error_msg,
            )

    async def _fetch_filter_option(
        self,
        filter_type: str,
        params: Optional[Dict[str, str]] = None
    ) -> List[EncarFilterOption]:
        """
        Helper method to fetch individual filter options

        Args:
            filter_type: Type of filter (manufacturer, modelGroup, model, etc.)
            params: Additional parameters for the request

        Returns:
            List of EncarFilterOption
        """
        try:
            # For now, return empty list as we need the actual proxy endpoints
            # This is a placeholder for future implementation
            logger.warning(f"Filter endpoint not implemented yet: {filter_type}")
            return []

        except Exception as e:
            logger.error(f"Error fetching filter option {filter_type}: {str(e)}")
            return []

    def clear_cache(self):
        """Clear all cached data"""
        self.cache.clear()
        logger.info("Encar service cache cleared")


# Singleton instance
encar_service = EncarService()
