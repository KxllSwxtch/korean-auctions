from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import logging

from app.models.bikemart import (
    BikemartBike,
    BikemartBikeCard,
    BikemartFilter,
    BikemartBrand,
    BikemartPaginationInfo,
    BikemartBikeDetail,
    BikemartImageUpload,
    BikemartModel
)

logger = logging.getLogger(__name__)


class BikemartUpstreamError(RuntimeError):
    """The upstream returned a payload we must not treat as a valid result.

    Raised rather than returned so that callers wrapping these parsers in a
    cache cannot accidentally memoise an upstream failure as "zero bikes".
    """


def _require_ok(response_data: Dict[str, Any], what: str) -> None:
    """Reject envelopes the upstream itself marked as failed."""
    if not response_data.get("ResultCode"):
        message = response_data.get("ResultMessage") or "ResultCode is False"
        raise BikemartUpstreamError(f"Bikemart {what} request rejected: {message}")


class BikemartParser:
    """Parser for Bikemart API responses"""

    @staticmethod
    def parse_bikes_response(response_data: Dict[str, Any]) -> tuple[List[BikemartBikeCard], Optional[BikemartPaginationInfo]]:
        """
        Parse bikes listing response from Bikemart API

        Only the fields the catalog card renders are projected out; the full
        record is available from the detail endpoint. Fields are read with
        ``.get()`` defaults rather than a ``**`` splat so that an upstream
        rename cannot silently empty the whole page.

        Args:
            response_data: Raw JSON response from API

        Returns:
            Tuple of (bike cards, pagination info)

        Raises:
            BikemartUpstreamError: the upstream reported a failed request.
        """
        _require_ok(response_data, "bike list")

        bikes: List[BikemartBikeCard] = []
        bikes_data = response_data.get("data") or []
        for bike_data in bikes_data:
            if not isinstance(bike_data, dict):
                logger.warning(f"Skipping non-object bike entry: {type(bike_data)}")
                continue
            seq = bike_data.get("seq")
            if not seq:
                logger.warning("Skipping bike entry without a seq")
                continue
            bikes.append(
                BikemartBikeCard(
                    seq=str(seq),
                    brand_name=bike_data.get("brand_name") or "",
                    model=bike_data.get("model") or "",
                    manufacture_year=bike_data.get("manufacture_year") or "",
                    mileage=bike_data.get("mileage") or "",
                    org_price=bike_data.get("org_price") or "",
                    sale_price=bike_data.get("sale_price") or None,
                    thumbnail_url=bike_data.get("thumbnail_url") or None,
                    status=bike_data.get("status") or "",
                    is_tuning=bike_data.get("is_tuning") or "",
                )
            )

        if bikes_data and not bikes:
            # Every row was unusable: that is a schema break, not an empty page.
            raise BikemartUpstreamError(
                f"Bikemart returned {len(bikes_data)} bikes but none could be parsed"
            )

        # The live API carries no "pagination" key (the count lives in "total"),
        # but honour it if it ever appears.
        pagination = None
        raw_pagination = response_data.get("pagination")
        if isinstance(raw_pagination, dict):
            try:
                pagination = BikemartPaginationInfo(**raw_pagination)
            except Exception as e:
                logger.error(f"Error parsing pagination: {e}")

        return bikes, pagination

    @staticmethod
    def parse_brands_response(response_data: Dict[str, Any]) -> List[BikemartBrand]:
        """
        Parse brands response from Bikemart API

        Args:
            response_data: Raw JSON response from API

        Returns:
            List of brands

        Raises:
            BikemartUpstreamError: the upstream reported a failed request.
        """
        _require_ok(response_data, "brand list")

        brands: List[BikemartBrand] = []
        brands_data = response_data.get("data") or []
        for brand_data in brands_data:
            if not isinstance(brand_data, dict):
                continue
            brand_seq = brand_data.get("seq")
            brand_name = brand_data.get("brand_name")
            if not brand_seq or not brand_name:
                # A blank entry would render as an unselectable empty dropdown row.
                continue
            brands.append(
                BikemartBrand(
                    brand_seq=str(brand_seq),
                    brand_name=brand_name,
                    count=None,  # Count is not provided in the API response
                )
            )

        if brands_data and not brands:
            raise BikemartUpstreamError(
                f"Bikemart returned {len(brands_data)} brands but none could be parsed"
            )

        return brands

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
    
    @staticmethod
    def parse_bike_detail_response(response_data: Dict[str, Any]) -> Optional[BikemartBikeDetail]:
        """
        Parse bike detail response from Bikemart API
        
        Args:
            response_data: Raw JSON response from API
            
        Returns:
            BikemartBikeDetail object or None if parsing fails

        Raises:
            BikemartUpstreamError: the upstream reported a failed request.
        """
        _require_ok(response_data, "bike detail")

        try:
            # Extract bike data
            bike_data = response_data.get("data")
            if not bike_data:
                logger.error("No bike data in response")
                return None
            
            # Parse image uploads
            upload_images = []
            if "upload" in bike_data and isinstance(bike_data["upload"], list):
                for img_data in bike_data["upload"]:
                    try:
                        image = BikemartImageUpload(**img_data)
                        upload_images.append(image)
                    except Exception as e:
                        logger.error(f"Error parsing image data: {e}")
                        continue
            
            # Add upload images to bike data
            bike_data["upload"] = upload_images
            
            # Create BikemartBikeDetail object
            bike_detail = BikemartBikeDetail(**bike_data)
            
            return bike_detail
            
        except Exception as e:
            logger.error(f"Error parsing bike detail response: {e}")
            return None
    
    @staticmethod
    def parse_models_response(response_data: Dict[str, Any]) -> List[BikemartModel]:
        """
        Parse models response from Bikemart API
        
        Args:
            response_data: Raw JSON response from API
            
        Returns:
            List of models

        Raises:
            BikemartUpstreamError: the upstream reported a failed request.
        """
        _require_ok(response_data, "model list")

        models: List[BikemartModel] = []
        models_data = response_data.get("data") or []
        for model_data in models_data:
            try:
                models.append(BikemartModel(**model_data))
            except Exception as e:
                logger.error(f"Error parsing model data: {e}")
                continue

        if models_data and not models:
            raise BikemartUpstreamError(
                f"Bikemart returned {len(models_data)} models but none could be parsed"
            )

        return models