from fastapi import APIRouter, HTTPException, Query, Body, Depends
from typing import Optional, Dict, Any
from datetime import datetime
from loguru import logger

from app.models.ssancar import (
    SSANCARResponse, SSANCARDetailResponse, SSANCARFilters,
    SSANCARManufacturersResponse, SSANCARModelsResponse,
    SSANCARHealthResponse, SSANCARFilterOptionsResponse,
    SSANCARTotalCountResponse
)
from app.services.ssancar_service import SSANCARService
from app.core.logging import get_logger

# Setup logger
ssancar_logger = get_logger("ssancar_routes")

router = APIRouter(prefix="/api/v1/ssancar", tags=["SSANCAR Auction"])

# Global service instance
ssancar_service = SSANCARService()


def get_ssancar_service() -> SSANCARService:
    """Dependency to get SSANCARService instance"""
    return ssancar_service


@router.get("/cars", response_model=SSANCARResponse)
async def get_ssancar_cars(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(15, ge=1, le=100, description="Items per page"),
    week_number: Optional[str] = Query(None, description="Week number (2 for Tuesday, 5 for Friday)"),
    manufacturer: Optional[str] = Query(None, description="Manufacturer in Korean"),
    model: Optional[str] = Query(None, description="Model code"),
    fuel: Optional[str] = Query(None, description="Fuel type in Korean"),
    color: Optional[str] = Query(None, description="Color in Korean"),
    year_from: Optional[int] = Query(2000, description="Year from"),
    year_to: Optional[int] = Query(2025, description="Year to"),
    price_from: Optional[int] = Query(0, description="Price from in USD"),
    price_to: Optional[int] = Query(200000, description="Price to in USD"),
    stock_no: Optional[str] = Query(None, description="Stock number search"),
    service: SSANCARService = Depends(get_ssancar_service)
) -> SSANCARResponse:
    """
    Get list of cars from SSANCAR auction
    
    **Week Number Logic:**
    - Tuesday auctions: weekNo = 2
    - Friday auctions: weekNo = 5
    - If not specified, automatically selects based on current day
    
    **Example usage:**
    ```
    GET /api/v1/ssancar/cars?page=1&manufacturer=현대&model=460
    ```
    """
    try:
        ssancar_logger.info(f"📥 Request for SSANCAR cars (page {page})")
        
        # Build filters
        filters = SSANCARFilters(
            weekNo=week_number or "",
            maker=manufacturer or "",
            model=model or "",
            fuel=fuel or "",
            color=color or "",
            yearFrom=str(year_from),
            yearTo=str(year_to),
            priceFrom=str(price_from),
            priceTo=str(price_to),
            list=str(page_size),
            pages=str(page - 1),  # Convert to 0-based
            no=stock_no or ""
        )
        
        # Get data
        result = service.fetch_cars(filters)
        
        if result.success:
            ssancar_logger.info(f"✅ Successfully fetched {len(result.cars)} cars from SSANCAR")
        else:
            ssancar_logger.error(f"❌ Error fetching SSANCAR data: {result.message}")
        
        return result
        
    except Exception as e:
        ssancar_logger.error(f"❌ Unexpected error fetching SSANCAR cars: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/search", response_model=SSANCARResponse)
async def search_ssancar_cars(
    filters: SSANCARFilters,
    service: SSANCARService = Depends(get_ssancar_service)
) -> SSANCARResponse:
    """
    Search cars with advanced filters
    
    **Request body example:**
    ```json
    {
        "weekNo": "2",
        "maker": "현대",
        "model": "460",
        "fuel": "경유",
        "yearFrom": "2020",
        "yearTo": "2024",
        "priceFrom": "10000",
        "priceTo": "50000",
        "list": "15",
        "pages": "0"
    }
    ```
    """
    try:
        ssancar_logger.info(f"🔍 Search SSANCAR cars with filters")
        
        result = service.search_cars(filters)
        
        if result.success:
            ssancar_logger.info(
                f"✅ Found {result.total_count} cars "
                f"(page {result.current_page})"
            )
        else:
            ssancar_logger.error(f"❌ Search error: {result.message}")
        
        return result
        
    except Exception as e:
        ssancar_logger.error(f"❌ Unexpected error in search: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/total-count", response_model=SSANCARTotalCountResponse)
async def get_total_count(
    week_number: Optional[str] = Query(None, description="Week number (2 for Tuesday, 5 for Friday)"),
    manufacturer: Optional[str] = Query(None, description="Manufacturer in Korean"),
    model: Optional[str] = Query(None, description="Model code"),
    fuel: Optional[str] = Query(None, description="Fuel type in Korean"),
    year_from: Optional[int] = Query(2000, description="Year from"),
    year_to: Optional[int] = Query(2025, description="Year to"),
    price_from: Optional[int] = Query(0, description="Price from in USD"),
    price_to: Optional[int] = Query(200000, description="Price to in USD"),
    service: SSANCARService = Depends(get_ssancar_service)
) -> SSANCARTotalCountResponse:
    """
    Get total count of cars in SSANCAR auction
    
    **Example usage:**
    ```
    GET /api/v1/ssancar/total-count
    GET /api/v1/ssancar/total-count?manufacturer=현대&model=460
    ```
    """
    try:
        ssancar_logger.info(f"📊 Request for total car count with week_number: {week_number}")
        
        # Determine week number - use provided or default based on current day
        if week_number:
            week_no = week_number
        else:
            # Default to Tuesday (2) or Friday (5) based on current day
            from datetime import datetime as dt
            current_day = dt.now().weekday()  # 0=Monday, 6=Sunday
            # If it's Thursday-Sunday, use Friday auction (5), otherwise use Tuesday (2)
            week_no = "5" if current_day >= 3 else "2"
        
        # Build filters if any provided
        filters = None
        if any([manufacturer, model, fuel, year_from != 2000, year_to != 2025, 
                price_from != 0, price_to != 200000, week_no]):
            filters = SSANCARFilters(
                weekNo=week_no,  # Always pass a week number
                maker=manufacturer or "",
                model=model or "",
                fuel=fuel or "",
                yearFrom=str(year_from),
                yearTo=str(year_to),
                priceFrom=str(price_from),
                priceTo=str(price_to),
                list="15",
                pages="0"
            )
        
        # Get total count
        total_count = service.fetch_total_count(filters)
        
        # Build filters applied dict for response
        filters_applied = {}
        if manufacturer:
            filters_applied["manufacturer"] = manufacturer
        if model:
            filters_applied["model"] = model
        if fuel:
            filters_applied["fuel"] = fuel
        if year_from != 2000:
            filters_applied["year_from"] = year_from
        if year_to != 2025:
            filters_applied["year_to"] = year_to
        if price_from != 0:
            filters_applied["price_from"] = price_from
        if price_to != 200000:
            filters_applied["price_to"] = price_to
        if week_number:
            filters_applied["week_number"] = week_number
        
        ssancar_logger.info(f"✅ Total count retrieved: {total_count} (week_no: {week_no})")
        
        return SSANCARTotalCountResponse(
            success=True,
            total_count=total_count,
            message="Total count retrieved successfully",
            filters_applied=filters_applied,
            timestamp=datetime.now()
        )
        
    except Exception as e:
        ssancar_logger.error(f"❌ Error getting total count: {e}")
        return SSANCARTotalCountResponse(
            success=False,
            total_count=0,
            message=f"Failed to get total count: {str(e)}",
            filters_applied={},
            timestamp=datetime.now()
        )


@router.get("/manufacturers", response_model=SSANCARManufacturersResponse)
async def get_manufacturers(
    service: SSANCARService = Depends(get_ssancar_service)
) -> SSANCARManufacturersResponse:
    """
    Get list of available car manufacturers
    
    Returns manufacturers with both Korean codes and English names.
    
    **Example usage:**
    ```
    GET /api/v1/ssancar/manufacturers
    ```
    """
    try:
        ssancar_logger.info("🏭 Request for manufacturers list")
        
        manufacturers, success = service.get_manufacturers()
        
        if success:
            ssancar_logger.info(f"✅ Retrieved {len(manufacturers)} manufacturers")
            return SSANCARManufacturersResponse(
                success=True,
                message="Manufacturers retrieved successfully",
                manufacturers=manufacturers,
                total_count=len(manufacturers),
                timestamp=datetime.now()
            )
        else:
            ssancar_logger.error("❌ Failed to get manufacturers")
            return SSANCARManufacturersResponse(
                success=False,
                message="Failed to retrieve manufacturers",
                manufacturers=[],
                total_count=0,
                timestamp=datetime.now()
            )
            
    except Exception as e:
        ssancar_logger.error(f"❌ Unexpected error getting manufacturers: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/models/{manufacturer_code}", response_model=SSANCARModelsResponse)
async def get_models(
    manufacturer_code: str,
    service: SSANCARService = Depends(get_ssancar_service)
) -> SSANCARModelsResponse:
    """
    Get list of models for selected manufacturer
    
    **Parameters:**
    - **manufacturer_code**: Manufacturer code in Korean (e.g., 현대, 기아)
    
    **Example usage:**
    ```
    GET /api/v1/ssancar/models/현대
    ```
    """
    try:
        ssancar_logger.info(f"🚗 Request for models of manufacturer {manufacturer_code}")
        
        models, success = service.get_models(manufacturer_code)
        
        if success:
            ssancar_logger.info(f"✅ Retrieved {len(models)} models")
            return SSANCARModelsResponse(
                success=True,
                message="Models retrieved successfully",
                models=models,
                total_count=len(models),
                manufacturer_code=manufacturer_code,
                timestamp=datetime.now()
            )
        else:
            ssancar_logger.error(f"❌ Failed to get models for {manufacturer_code}")
            return SSANCARModelsResponse(
                success=False,
                message=f"Failed to retrieve models for {manufacturer_code}",
                models=[],
                total_count=0,
                manufacturer_code=manufacturer_code,
                timestamp=datetime.now()
            )
            
    except Exception as e:
        ssancar_logger.error(f"❌ Unexpected error getting models: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/car/{car_no}", response_model=SSANCARDetailResponse)
async def get_car_detail(
    car_no: str,
    service: SSANCARService = Depends(get_ssancar_service)
) -> SSANCARDetailResponse:
    """
    Get detailed information about a specific car
    
    **Parameters:**
    - **car_no**: The car number from SSANCAR (e.g., "1536311")
    
    **Example usage:**
    ```
    GET /api/v1/ssancar/car/1536311
    ```
    """
    try:
        ssancar_logger.info(f"📥 Request for car detail: {car_no}")
        
        car_detail = service.get_car_detail(car_no)
        
        if car_detail:
            ssancar_logger.info(f"✅ Successfully retrieved car detail for: {car_no}")
            return SSANCARDetailResponse(
                success=True,
                message="Car details retrieved successfully",
                car_detail=car_detail,
                timestamp=datetime.now()
            )
        else:
            ssancar_logger.error(f"❌ Car not found: {car_no}")
            raise HTTPException(
                status_code=404,
                detail=f"Car not found: {car_no}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        ssancar_logger.error(f"❌ Unexpected error getting car detail: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/update-cookies", response_model=Dict[str, Any])
async def update_cookies(
    cookies: Dict[str, str] = Body(..., description="Fresh cookies from browser"),
    service: SSANCARService = Depends(get_ssancar_service)
) -> Dict[str, Any]:
    """
    Update SSANCAR cookies manually
    
    **Request body example:**
    ```json
    {
        "_gcl_au": "1.1.78877594.1751338453",
        "e1192aefb64683cc97abb83c71057733": "bGlzdA%3D%3D",
        "PHPSESSID": "new_session_id",
        "2a0d2363701f23f8a75028924a3af643": "new_token"
    }
    ```
    """
    try:
        ssancar_logger.info("🍪 Updating SSANCAR cookies")
        
        # Update service cookies
        service.update_cookies(cookies)
        
        # Test if cookies work
        test_filters = SSANCARFilters(
            weekNo="2",
            list="1",
            pages="0"
        )
        test_result = service.fetch_cars(test_filters)
        
        return {
            "success": True,
            "message": "Cookies updated successfully",
            "cookies_count": len(cookies),
            "test_passed": test_result.success,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        ssancar_logger.error(f"❌ Error updating cookies: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update cookies: {str(e)}"
        )


@router.get("/health", response_model=SSANCARHealthResponse)
async def health_check() -> SSANCARHealthResponse:
    """
    Check health status of SSANCAR service
    
    **Example usage:**
    ```
    GET /api/v1/ssancar/health
    ```
    """
    try:
        ssancar_logger.info("🏥 Health check request")
        
        return SSANCARHealthResponse(
            success=True,
            message="SSANCAR service is healthy",
            service="SSANCAR Auction",
            status="active",
            base_url=ssancar_service.BASE_URL,
            timestamp=datetime.now()
        )
        
    except Exception as e:
        ssancar_logger.error(f"❌ Health check failed: {e}")
        return SSANCARHealthResponse(
            success=False,
            message=f"Service unhealthy: {str(e)}",
            service="SSANCAR Auction",
            status="error",
            base_url=ssancar_service.BASE_URL,
            timestamp=datetime.now()
        )


@router.get("/filters/options", response_model=SSANCARFilterOptionsResponse)
async def get_filter_options(
    service: SSANCARService = Depends(get_ssancar_service)
) -> SSANCARFilterOptionsResponse:
    """
    Get all available filter options for SSANCAR
    
    Returns complete set of available filters for car search.
    
    **Example usage:**
    ```
    GET /api/v1/ssancar/filters/options
    ```
    
    **Response includes:**
    - List of manufacturers
    - Fuel types
    - Transmissions
    - Grades
    - Colors
    - Auction weeks
    - Year, price, and mileage ranges
    """
    try:
        ssancar_logger.info("🔧 Request for filter options")
        
        filter_options = service.get_filter_options()
        
        if filter_options.get("success"):
            ssancar_logger.info("✅ Filter options retrieved successfully")
            return SSANCARFilterOptionsResponse(**filter_options)
        else:
            ssancar_logger.error(f"❌ Failed to get filter options: {filter_options.get('message')}")
            return SSANCARFilterOptionsResponse(**filter_options)
            
    except Exception as e:
        ssancar_logger.error(f"❌ Unexpected error getting filter options: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


# Compatibility endpoints for existing Glovis integration
@router.get("/filters/ssancar/manufacturers", response_model=Dict[str, Any])
async def get_ssancar_manufacturers_compat(
    service: SSANCARService = Depends(get_ssancar_service)
) -> Dict[str, Any]:
    """Get manufacturers in Glovis-compatible format"""
    response = await get_manufacturers(service)
    return {
        "success": response.success,
        "message": response.message,
        "manufacturers": response.manufacturers,
        "total_count": response.total_count,
        "timestamp": response.timestamp.isoformat()
    }


@router.get("/filters/ssancar/models/{manufacturer_code}", response_model=Dict[str, Any])
async def get_ssancar_models_compat(
    manufacturer_code: str,
    service: SSANCARService = Depends(get_ssancar_service)
) -> Dict[str, Any]:
    """Get models in Glovis-compatible format"""
    response = await get_models(manufacturer_code, service)
    return {
        "success": response.success,
        "message": response.message,
        "models": response.models,
        "total_count": response.total_count,
        "manufacturer_code": response.manufacturer_code,
        "timestamp": response.timestamp.isoformat()
    }


@router.post("/filters/ssancar/search", response_model=Dict[str, Any])
async def search_ssancar_cars_compat(
    filters: Dict[str, Any] = Body(..., description="Search filters"),
    service: SSANCARService = Depends(get_ssancar_service)
) -> Dict[str, Any]:
    """Search cars in Glovis-compatible format"""
    # Convert to SSANCAR filters
    ssancar_filters = SSANCARFilters(
        weekNo=str(filters.get("week_number", "")),
        maker=filters.get("manufacturer", ""),
        model=filters.get("model", ""),
        fuel=filters.get("fuel", ""),
        color=filters.get("color", ""),
        yearFrom=str(filters.get("year_from", 2000)),
        yearTo=str(filters.get("year_to", 2025)),
        priceFrom=str(filters.get("price_from", 0)),
        priceTo=str(filters.get("price_to", 200000)),
        list=str(filters.get("page_size", 15)),
        pages=str(filters.get("page", 1) - 1),  # Convert to 0-based
        no=filters.get("stock_no", "")
    )
    
    response = await search_ssancar_cars(ssancar_filters, service)
    
    # Convert response to match expected format
    return {
        "success": response.success,
        "message": response.message,
        "cars": [car.dict() for car in response.cars],
        "total_count": response.total_count,
        "current_page": response.current_page,
        "page_size": response.page_size,
        "has_next_page": response.has_next_page,
        "has_prev_page": response.has_prev_page,
        "timestamp": response.timestamp.isoformat()
    }