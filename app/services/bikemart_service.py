from typing import Optional, Dict, Any, List, Tuple
import logging
from datetime import datetime

from app.core.async_cache import SwrCache
from app.core.http_client import AsyncHttpClient
from app.models.bikemart import (
    BikemartResponse,
    BikemartBrandsResponse,
    BikemartFiltersResponse,
    BikemartError,
    BikemartBikeCard,
    BikemartBrand,
    BikemartPaginationInfo,
    BikemartFilter,
    BikemartBikeDetailResponse,
    BikemartBikeDetail,
    BikemartModelsResponse,
    BikemartModel,
)
from app.parsers.bikemart_parser import BikemartParser, BikemartUpstreamError

logger = logging.getLogger(__name__)

# Bikemart pages the list endpoint 20 at a time and reports the grand total in
# a top-level "total" key rather than a pagination object.
ITEMS_PER_PAGE = 20

# Cache tuning. Listings churn through the day, so they get a short fresh
# window with a long stale window: a user never waits on Korea once a key is
# warm, and an upstream blip keeps serving the last good page instead of an
# error. Brands and models are effectively static reference data.
#
# These live at module scope so every BikemartService instance shares them, but
# note gunicorn runs 2 workers — the cache is per worker, so expect up to one
# upstream call per worker per window rather than exactly one process-wide.
_BIKES_CACHE: SwrCache[Tuple[List[BikemartBikeCard], BikemartPaginationInfo]] = SwrCache(
    ttl=120, stale_ttl=900, maxsize=512, jitter=15, name="bikemart.bikes"
)
_BRANDS_CACHE: SwrCache[List[BikemartBrand]] = SwrCache(
    ttl=1800, stale_ttl=86400, maxsize=1, name="bikemart.brands"
)
_MODELS_CACHE: SwrCache[List[BikemartModel]] = SwrCache(
    ttl=1800, stale_ttl=86400, maxsize=256, name="bikemart.models"
)
_DETAIL_CACHE: SwrCache[BikemartBikeDetail] = SwrCache(
    ttl=300, stale_ttl=1800, maxsize=512, jitter=30, name="bikemart.detail"
)


class BikemartService:
    """Service for interacting with Bikemart API.

    Each upstream call is split into a ``_load_*`` coroutine and a public
    method. The loaders **raise** on failure and the public methods convert
    that into a ``success=False`` DTO. That split is load-bearing rather than
    stylistic: the loaders are what the cache memoises, so a loader that
    swallowed its error and returned an empty DTO would pin that failure in the
    cache for the whole TTL window.
    """

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

    async def _request_json(self, params: Dict[str, str], what: str) -> Dict[str, Any]:
        """GET the upstream API and return decoded JSON, raising on any failure."""
        response = await self.http_client.get(
            self.BASE_URL, params=params, headers=self.headers
        )
        if response.status_code != 200:
            raise BikemartUpstreamError(
                f"Bikemart {what} request returned HTTP {response.status_code}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise BikemartUpstreamError(
                f"Bikemart {what} response was not valid JSON: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Bikes listing
    # ------------------------------------------------------------------
    async def _load_bikes(
        self, key: Tuple[Any, ...]
    ) -> Tuple[List[BikemartBikeCard], BikemartPaginationInfo]:
        """Cache loader for a page of bikes. Raises on any upstream failure."""
        (
            page,
            brand_seq,
            model,
            min_year,
            max_year,
            min_price,
            max_price,
            min_mileage,
            max_mileage,
            search_text,
            sort_by,
        ) = key

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
            "syr": str(min_year) if min_year is not None else "",
            "eyr": str(max_year) if max_year is not None else "",
            "spt": str(min_price) if min_price is not None else "",
            "ept": str(max_price) if max_price is not None else "",
            "spc": str(min_mileage) if min_mileage is not None else "",
            "epc": str(max_mileage) if max_mileage is not None else "",
            "sos": sort_by or "",
            "product_gbn": "BIKE",
            "program": "bike",
            "service": "sell",
            "version": "1.0",
            "action": "getBikeSellList",
            "token": "",
        }

        response_data = await self._request_json(params, "bike list")
        bikes, pagination = self.parser.parse_bikes_response(response_data)

        if not pagination:
            total_count = self.parser.parse_total_count(response_data)
            pagination = BikemartPaginationInfo(
                current_page=page,
                total_pages=max(
                    1, (total_count + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
                ),
                total_count=total_count,
                items_per_page=ITEMS_PER_PAGE,
            )

        return bikes, pagination

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
        sort_by: Optional[str] = None,
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
        # A stable tuple, not a dict or str(params): dicts are unhashable and
        # str() of a dict is insertion-order dependent, so equivalent filter
        # sets would miss each other in the cache.
        key = (
            page,
            brand_seq or None,
            model or None,
            min_year,
            max_year,
            min_price,
            max_price,
            min_mileage,
            max_mileage,
            search_text or None,
            sort_by or None,
        )

        try:
            bikes, pagination = await _BIKES_CACHE.get(
                key, lambda: self._load_bikes(key)
            )
            return BikemartResponse(
                success=True, data=bikes, pagination=pagination, message=""
            )
        except Exception as e:
            logger.error(f"Error fetching bikes: {e}")
            return BikemartResponse(
                success=False, data=[], message=f"Error fetching bikes: {str(e)}"
            )

    # ------------------------------------------------------------------
    # Brands
    # ------------------------------------------------------------------
    async def _load_brands(self) -> List[BikemartBrand]:
        """Cache loader for the brand list. Raises on any upstream failure."""
        params = {
            "program": "bike",
            "service": "sell",
            "version": "1.0",
            "action": "getBikeBrandList",
            "token": "",
        }
        response_data = await self._request_json(params, "brand list")
        return self.parser.parse_brands_response(response_data)

    async def get_brands(self) -> BikemartBrandsResponse:
        """
        Get available bike brands

        Returns:
            BikemartBrandsResponse with brands data
        """
        try:
            brands = await _BRANDS_CACHE.get("brands", self._load_brands)
            return BikemartBrandsResponse(success=True, data=brands, message="")
        except Exception as e:
            logger.error(f"Error fetching brands: {e}")
            return BikemartBrandsResponse(
                success=False, data=[], message=f"Error fetching brands: {str(e)}"
            )

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------
    async def get_filters(self) -> BikemartFiltersResponse:
        """
        Get available filter options

        Year/mileage/price/region options are static ranges; the brand list is
        shared with :meth:`get_brands` through the cache, so rendering the
        filter panel no longer costs a second upstream round trip.

        Returns:
            BikemartFiltersResponse with filter options
        """
        try:
            # Year filters
            current_year = datetime.now().year
            years = [
                BikemartFilter(value=str(year), label=str(year))
                for year in range(current_year, 1990, -1)
            ]

            # Mileage ranges
            mileage_ranges = [
                BikemartFilter(value="0-10000", label="0~10,000km"),
                BikemartFilter(value="10000-30000", label="10,000~30,000km"),
                BikemartFilter(value="30000-50000", label="30,000~50,000km"),
                BikemartFilter(value="50000-100000", label="50,000~100,000km"),
                BikemartFilter(value="100000+", label="100,000km+"),
            ]

            # Price ranges (in 만원)
            price_ranges = [
                BikemartFilter(value="0-100", label="~100만원"),
                BikemartFilter(value="100-200", label="100~200만원"),
                BikemartFilter(value="200-300", label="200~300만원"),
                BikemartFilter(value="300-500", label="300~500만원"),
                BikemartFilter(value="500-1000", label="500~1,000만원"),
                BikemartFilter(value="1000+", label="1,000만원+"),
            ]

            # Get brands for brand filter (served from the shared brands cache)
            brands_response = await self.get_brands()
            brand_filters = [
                BikemartFilter(
                    value=brand.brand_seq, label=brand.brand_name, count=brand.count
                )
                for brand in brands_response.data
            ]

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
                regions=regions,
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
                message=f"Error fetching filters: {str(e)}",
            )

    # ------------------------------------------------------------------
    # Bike detail
    # ------------------------------------------------------------------
    async def _load_bike_detail(self, seq: str) -> BikemartBikeDetail:
        """Cache loader for one bike detail. Raises on any upstream failure."""
        params = {
            "seq": seq,
            "program": "bike",
            "service": "sell",
            "version": "1.0",
            "action": "getBikeSellDetail",
            "token": "",
        }
        response_data = await self._request_json(params, "bike detail")
        bike_detail = self.parser.parse_bike_detail_response(response_data)
        if not bike_detail:
            raise BikemartUpstreamError(f"Bike {seq} could not be parsed")
        return bike_detail

    async def get_bike_detail(self, seq: str) -> BikemartBikeDetailResponse:
        """
        Get detailed bike information by sequence ID

        Args:
            seq: Bike sequence ID

        Returns:
            BikemartBikeDetailResponse with bike detail data
        """
        try:
            detail = await _DETAIL_CACHE.get(
                seq, lambda: self._load_bike_detail(seq)
            )
            return BikemartBikeDetailResponse(success=True, data=detail, message="")
        except Exception as e:
            logger.error(f"Error fetching bike detail: {e}")
            return BikemartBikeDetailResponse(
                success=False,
                data=None,
                message=f"Error fetching bike detail: {str(e)}",
            )

    # ------------------------------------------------------------------
    # Models
    # ------------------------------------------------------------------
    async def _load_models(self, brand_seq: str) -> List[BikemartModel]:
        """Cache loader for a brand's models. Raises on any upstream failure."""
        params = {
            "brand": brand_seq,
            "program": "bike",
            "service": "sell",
            "version": "1.0",
            "action": "getBikeModel",
            "token": "",
        }
        response_data = await self._request_json(params, "model list")
        return self.parser.parse_models_response(response_data)

    async def get_models_by_brand(self, brand_seq: str) -> BikemartModelsResponse:
        """
        Get bike models for a specific brand

        Args:
            brand_seq: Brand sequence ID

        Returns:
            BikemartModelsResponse with models data
        """
        try:
            models = await _MODELS_CACHE.get(
                brand_seq, lambda: self._load_models(brand_seq)
            )
            return BikemartModelsResponse(success=True, data=models, message="")
        except Exception as e:
            logger.error(f"Error fetching models: {e}")
            return BikemartModelsResponse(
                success=False, data=[], message=f"Error fetching models: {str(e)}"
            )

    async def close(self) -> None:
        """Release the shared aiohttp session held by this service."""
        await self.http_client.close()


# Create singleton instance
bikemart_service = BikemartService()
