"""
Service for fetching car data from Pan-Auto.ru API
Provides HP (horsepower) and Russian customs costs data
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.core.http_client import AsyncHttpClient
from app.models.pan_auto import (
    PanAutoCarDetail,
    PanAutoCarDetailResponse,
    PanAutoCosts,
    PanAutoCostsRUB,
)

logger = logging.getLogger(__name__)


class PanAutoCache:
    """Simple in-memory cache with TTL for Pan-Auto data"""

    def __init__(self, ttl_seconds: int = 300):  # 5 minutes default TTL
        self.cache: Dict[str, tuple[Any, datetime]] = {}
        self.ttl = timedelta(seconds=ttl_seconds)

    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired"""
        if key in self.cache:
            value, timestamp = self.cache[key]
            if datetime.now() - timestamp < self.ttl:
                logger.debug(f"Cache hit for Pan-Auto key: {key}")
                return value
            else:
                logger.debug(f"Cache expired for Pan-Auto key: {key}")
                del self.cache[key]
        return None

    def set(self, key: str, value: Any):
        """Set cached value with current timestamp"""
        self.cache[key] = (value, datetime.now())
        logger.debug(f"Cached Pan-Auto key: {key}")

    def clear(self):
        """Clear all cached values"""
        self.cache.clear()
        logger.debug("Pan-Auto cache cleared")

    def delete(self, key: str):
        """Delete specific cache key"""
        if key in self.cache:
            del self.cache[key]
            logger.debug(f"Deleted Pan-Auto cache key: {key}")


class PanAutoService:
    """Service for interacting with Pan-Auto.ru API"""

    BASE_URL = "https://zefir.pan-auto.ru/api"

    def __init__(self):
        self.http_client = AsyncHttpClient(timeout=15)
        self.cache = PanAutoCache(ttl_seconds=300)  # 5 minute cache

        # Headers required for Pan-Auto.ru API
        self.headers = {
            "Accept": "*/*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Origin": "https://pan-auto.ru",
            "Referer": "https://pan-auto.ru/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

    async def get_car_detail(
        self,
        car_id: str,
        use_cache: bool = True,
    ) -> PanAutoCarDetailResponse:
        """
        Get car detail from Pan-Auto.ru API

        Args:
            car_id: Encar car ID
            use_cache: Whether to use caching

        Returns:
            PanAutoCarDetailResponse with HP and customs costs
        """
        try:
            # Build cache key
            cache_key = f"pan_auto_car_{car_id}"

            # Check cache if enabled
            if use_cache:
                cached_response = self.cache.get(cache_key)
                if cached_response:
                    logger.info(f"Returning cached Pan-Auto response for car {car_id}")
                    return cached_response

            # Build URL
            url = f"{self.BASE_URL}/korea/{car_id}/"

            logger.info(f"Fetching Pan-Auto data for car: {car_id}")

            # Fetch data
            response = await self.http_client.get(url, headers=self.headers)

            if not response or response.status_code != 200:
                error_msg = f"Pan-Auto API returned status {response.status_code if response else 'None'} for car {car_id}"
                logger.warning(error_msg)
                return PanAutoCarDetailResponse(
                    success=False, data=None, message=error_msg
                )

            # Parse JSON response
            try:
                response_data = response.json()
            except Exception as json_error:
                logger.error(f"Failed to parse Pan-Auto JSON response: {json_error}")
                return PanAutoCarDetailResponse(
                    success=False,
                    data=None,
                    message="Failed to parse Pan-Auto response",
                )

            # Extract data with proper error handling
            car_detail = self._parse_car_detail(response_data, car_id)

            # Create response
            result = PanAutoCarDetailResponse(
                success=True, data=car_detail, message=None
            )

            # Cache the response
            if use_cache:
                self.cache.set(cache_key, result)

            logger.info(
                f"Successfully fetched Pan-Auto data for car {car_id}: HP={car_detail.hp}"
            )
            return result

        except Exception as e:
            error_msg = f"Error fetching Pan-Auto data for car {car_id}: {str(e)}"
            logger.error(error_msg)
            return PanAutoCarDetailResponse(success=False, data=None, message=error_msg)

    def _parse_car_detail(self, data: Dict[str, Any], car_id: str) -> PanAutoCarDetail:
        """
        Parse raw Pan-Auto.ru response into typed model

        Args:
            data: Raw JSON response
            car_id: Car ID for reference

        Returns:
            PanAutoCarDetail with parsed data
        """
        # Extract HP value
        hp = data.get("hp")
        if hp is not None:
            try:
                hp = int(hp)
            except (ValueError, TypeError):
                hp = None

        # Extract kW value
        ckw = data.get("ckw")
        if ckw is not None:
            try:
                ckw = float(ckw)
            except (ValueError, TypeError):
                ckw = None

        # Extract costs
        costs = None
        costs_data = data.get("costs")
        if costs_data:
            rub_costs = costs_data.get("RUB")
            if rub_costs:
                costs = PanAutoCosts(
                    RUB=PanAutoCostsRUB(
                        carPriceEncar=rub_costs.get("carPriceEncar"),
                        carPrice=rub_costs.get("carPrice"),
                        clearanceCost=rub_costs.get("clearanceCost"),
                        utilizationFee=rub_costs.get("utilizationFee"),
                        customsDuty=rub_costs.get("customsDuty"),
                        deliveryRate=rub_costs.get("deliveryRate"),
                        deliveryCost=rub_costs.get("deliveryCost"),
                        vladivostokServices=rub_costs.get("vladivostokServices"),
                        totalFees=rub_costs.get("totalFees"),
                        finalCost=rub_costs.get("finalCost"),
                        pizdec=rub_costs.get("pizdec"),
                        pizdecTotal=rub_costs.get("pizdecTotal"),
                        dealerCost=rub_costs.get("dealerCost"),
                    ),
                    USD=costs_data.get("USD"),
                    KRW=costs_data.get("KRW"),
                )

        # Extract year value from Russian format like "Июнь, 2020 год"
        year = None
        year_raw = data.get("year")
        if year_raw is not None:
            try:
                year = int(year_raw)
            except (ValueError, TypeError):
                # Extract 4-digit year from Russian date string
                year_match = re.search(r"\b(19|20)\d{2}\b", str(year_raw))
                if year_match:
                    year = int(year_match.group())

        # Fallback to formYear if year couldn't be parsed
        if year is None:
            form_year = data.get("formYear")
            if form_year is not None:
                try:
                    year = int(form_year)
                except (ValueError, TypeError):
                    pass

        return PanAutoCarDetail(
            id=str(car_id),
            hp=hp,
            ckw=ckw,
            costs=costs,
            title=data.get("title"),
            price=data.get("price"),
            year=year,
            mileage=data.get("mileage"),
            displacement=data.get("displacement"),
        )

    def clear_cache(self):
        """Clear all cached data"""
        self.cache.clear()
        logger.info("Pan-Auto service cache cleared")


# Singleton instance
pan_auto_service = PanAutoService()
