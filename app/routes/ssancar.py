from fastapi import APIRouter, HTTPException, Query, Body, Depends
from typing import Optional, Dict, Any, NoReturn
from datetime import datetime
import asyncio

from app.models.ssancar import (
    SSANCARResponse, SSANCARDetailResponse, SSANCARFilters,
    SSANCARManufacturersResponse, SSANCARModelsResponse,
    SSANCARHealthResponse, SSANCARFilterOptionsResponse,
    SSANCARTotalCountResponse, SSANCARDetailHealthResponse,
)
from app.services.ssancar_service import (
    SSANCARService,
    resolve_ssancar_week,
    validate_ssancar_car_no,
)
from app.services.ssancar_transport import (
    SSANCARUpstreamError,
    SSANCARUpstreamTimeoutError,
)
from app.parsers.ssancar_parser import (
    PARSE_STATUS_VALID,
    PARSE_STATUS_SESSION_EXPIRED,
    PARSE_STATUS_NOT_FOUND,
    PARSE_STATUS_EMPTY,
    PARSE_STATUS_INVALID_DATA,
    PARSE_STATUS_EXCEPTION,
)
from app.core.logging import get_logger

# Maps internal parse statuses to public error codes the frontend branches on.
# Anything other than session_expired collapses to car_unavailable so the UI
# can show the same "auction may have ended / listing removed" copy.
_DETAIL_ERROR_CODES = {
    PARSE_STATUS_SESSION_EXPIRED: "session_expired",
    PARSE_STATUS_NOT_FOUND: "car_unavailable",
    PARSE_STATUS_EMPTY: "car_unavailable",
    PARSE_STATUS_INVALID_DATA: "car_unavailable",
    "request_error": "upstream_error",
    PARSE_STATUS_EXCEPTION: "upstream_error",
}


def _raise_upstream_error(
    error: SSANCARUpstreamError,
    *,
    status_override: Optional[int] = None,
    message: str = "SSANCAR is temporarily unavailable",
) -> NoReturn:
    status_code = status_override or (
        504 if isinstance(error, SSANCARUpstreamTimeoutError) else 502
    )
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": error.code,
            "message": message,
            "retryable": True,
        },
        headers={"Cache-Control": "no-store"},
    )

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
    transmission: Optional[str] = Query(None, description="Transmission/gearbox"),
    mileage_from: Optional[int] = Query(0, ge=0, description="Mileage from"),
    mileage_to: Optional[int] = Query(500000, ge=0, description="Mileage to"),
    year_from: Optional[int] = Query(2000, description="Year from"),
    year_to: Optional[int] = Query(None, description="Year to (defaults to next year)"),
    price_from: Optional[int] = Query(0, description="Price from (upstream ssancar.com filter units — historically USD)"),
    price_to: Optional[int] = Query(200000, description="Price to (upstream ssancar.com filter units — historically USD)"),
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
        resolved_week = resolve_ssancar_week(week_number)
        
        # Build filters
        filters = SSANCARFilters(
            weekNo=resolved_week,
            maker=manufacturer or "",
            model=model or "",
            fuel=fuel or "",
            color=color or "",
            gearbox=transmission or "",
            kmFrom=str(mileage_from),
            kmTo=str(mileage_to),
            yearFrom=str(year_from),
            yearTo=str(year_to or (datetime.now().year + 1)),
            priceFrom=str(price_from),
            priceTo=str(price_to),
            list=str(page_size),
            pages=str(page - 1),  # Convert to 0-based
            no=stock_no or ""
        )
        
        # Get data
        result = await asyncio.to_thread(service.fetch_cars, filters)

        if result.success:
            ssancar_logger.info(f"✅ Successfully fetched {len(result.cars)} cars from SSANCAR")
        else:
            ssancar_logger.error(f"❌ Error fetching SSANCAR data: {result.message}")
        
        return result
    except SSANCARUpstreamError as error:
        ssancar_logger.warning(
            "SSANCAR list upstream failure code={}",
            error.code,
        )
        _raise_upstream_error(error)
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
        filters = filters.model_copy(
            update={"weekNo": resolve_ssancar_week(filters.weekNo)}
        )
        
        result = await asyncio.to_thread(service.search_cars, filters)

        if result.success:
            ssancar_logger.info(
                f"✅ Found {result.total_count} cars "
                f"(page {result.current_page})"
            )
        else:
            ssancar_logger.error(f"❌ Search error: {result.message}")
        
        return result
    except SSANCARUpstreamError as error:
        ssancar_logger.warning(
            "SSANCAR search upstream failure code={}",
            error.code,
        )
        _raise_upstream_error(error)
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
    color: Optional[str] = Query(None, description="Color in Korean"),
    transmission: Optional[str] = Query(None, description="Transmission/gearbox"),
    mileage_from: Optional[int] = Query(0, ge=0, description="Mileage from"),
    mileage_to: Optional[int] = Query(500000, ge=0, description="Mileage to"),
    stock_no: Optional[str] = Query(None, description="Stock number search"),
    year_from: Optional[int] = Query(2000, description="Year from"),
    year_to: Optional[int] = Query(None, description="Year to (defaults to next year)"),
    price_from: Optional[int] = Query(0, description="Price from (upstream ssancar.com filter units — historically USD)"),
    price_to: Optional[int] = Query(200000, description="Price to (upstream ssancar.com filter units — historically USD)"),
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
        
        week_no = resolve_ssancar_week(week_number)
        
        # Build filters if any provided
        default_year_to = datetime.now().year + 1
        effective_year_to = year_to or default_year_to
        filters = SSANCARFilters(
            weekNo=week_no,
            maker=manufacturer or "",
            model=model or "",
            fuel=fuel or "",
            color=color or "",
            gearbox=transmission or "",
            kmFrom=str(mileage_from),
            kmTo=str(mileage_to),
            yearFrom=str(year_from),
            yearTo=str(effective_year_to),
            priceFrom=str(price_from),
            priceTo=str(price_to),
            list="15",
            pages="0",
            no=stock_no or "",
        )
        
        # Get total count
        total_count = await asyncio.to_thread(service.fetch_total_count, filters)
        
        # Build filters applied dict for response
        filters_applied = {}
        if manufacturer:
            filters_applied["manufacturer"] = manufacturer
        if model:
            filters_applied["model"] = model
        if fuel:
            filters_applied["fuel"] = fuel
        if color:
            filters_applied["color"] = color
        if transmission:
            filters_applied["transmission"] = transmission
        if mileage_from != 0:
            filters_applied["mileage_from"] = mileage_from
        if mileage_to != 500000:
            filters_applied["mileage_to"] = mileage_to
        if stock_no:
            filters_applied["stock_no"] = stock_no
        if year_from != 2000:
            filters_applied["year_from"] = year_from
        if year_to and year_to != default_year_to:
            filters_applied["year_to"] = year_to
        if price_from != 0:
            filters_applied["price_from"] = price_from
        if price_to != 200000:
            filters_applied["price_to"] = price_to
        if week_number:
            filters_applied["week_number"] = week_no
        
        ssancar_logger.info(f"✅ Total count retrieved: {total_count} (week_no: {week_no})")
        
        return SSANCARTotalCountResponse(
            success=True,
            total_count=total_count,
            week_number=week_no,
            message="Total count retrieved successfully",
            filters_applied=filters_applied,
            timestamp=datetime.now()
        )
        
    except SSANCARUpstreamError as error:
        ssancar_logger.warning(
            "SSANCAR count upstream failure code={}",
            error.code,
        )
        _raise_upstream_error(error)
    except Exception as e:
        ssancar_logger.error(f"❌ Error getting total count: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
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
        
        manufacturers, success = await asyncio.to_thread(service.get_manufacturers)
        
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
        
        models, success = await asyncio.to_thread(service.get_models, manufacturer_code)
        
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
        try:
            car_no = validate_ssancar_car_no(car_no)
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_car_no",
                    "message": str(error),
                    "retryable": False,
                },
                headers={"Cache-Control": "no-store"},
            ) from error

        ssancar_logger.info(f"📥 Request for car detail: {car_no}")

        car_detail, status = await asyncio.to_thread(
            service.get_car_detail, car_no
        )

        if status == PARSE_STATUS_VALID and car_detail is not None:
            ssancar_logger.info(f"✅ Successfully retrieved car detail for: {car_no}")
            return SSANCARDetailResponse(
                success=True,
                message="Car details retrieved successfully",
                car_detail=car_detail,
                timestamp=datetime.now()
            )

        # The isolated transport raises authentication/invalid-payload errors
        # before this point. Retain the legacy parser-status mapping only for
        # genuine archived/not-found detail responses.
        code = _DETAIL_ERROR_CODES.get(status, "car_unavailable")
        ssancar_logger.warning(
            f"❌ SSANCAR car detail unavailable for {car_no}: "
            f"status={status} code={code}"
        )

        if code == "upstream_error":
            raise HTTPException(
                status_code=502,
                detail={
                    "code": code,
                    "message": "SSANCAR upstream did not respond as expected",
                    "car_no": car_no,
                    "retryable": True,
                },
                headers={"Cache-Control": "no-store"},
            )

        raise HTTPException(
            status_code=404,
            detail={
                "code": code,
                "message": "Car details are not available",
                "car_no": car_no,
                "retryable": False,
            },
            headers={"Cache-Control": "no-store"},
        )

    except SSANCARUpstreamError as error:
        ssancar_logger.warning(
            "SSANCAR detail upstream failure code={}",
            error.code,
        )
        _raise_upstream_error(error)
    except HTTPException:
        raise
    except Exception as e:
        ssancar_logger.error(f"❌ Unexpected error getting car detail: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "internal_error",
                "message": str(e),
                "car_no": car_no,
            },
        )


@router.post("/update-cookies", response_model=Dict[str, Any])
async def update_cookies(
    cookies: Optional[Dict[str, str]] = Body(
        None,
        description="Deprecated compatibility body",
    ),
    service: SSANCARService = Depends(get_ssancar_service)
) -> Dict[str, Any]:
    """Compatibility tombstone; transport sessions manage their own cookies."""

    del cookies, service
    raise HTTPException(
        status_code=410,
        detail={
            "code": "manual_cookie_updates_removed",
            "message": "Manual SSANCAR cookie updates are no longer supported",
            "retryable": False,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/health", response_model=SSANCARHealthResponse)
async def health_check(
    week_number: Optional[str] = Query(
        None,
        description="Week number (2 for Tuesday, 5 for Friday)",
    ),
    service: SSANCARService = Depends(get_ssancar_service),
) -> SSANCARHealthResponse:
    """
    Check health status of SSANCAR service
    
    **Example usage:**
    ```
    GET /api/v1/ssancar/health
    ```
    """
    try:
        ssancar_logger.info("🏥 Health check request")
        
        probe = await asyncio.to_thread(service.check_health, week_number)
        return SSANCARHealthResponse(
            success=True,
            message="SSANCAR upstream is healthy",
            service="SSANCAR Auction",
            status="healthy",
            base_url=service.BASE_URL,
            week_number=probe.week_number,
            upstream_count=probe.upstream_count,
            egress=probe.egress,
            checked_at=probe.checked_at,
        )
    except SSANCARUpstreamError as error:
        ssancar_logger.warning(
            "SSANCAR health upstream failure code={}",
            error.code,
        )
        _raise_upstream_error(
            error,
            status_override=503,
            message="SSANCAR readiness probe failed",
        )


@router.get("/health/detail", response_model=SSANCARDetailHealthResponse)
async def detail_health_check(
    week_number: Optional[str] = Query(
        None,
        description="Week number (2 for Tuesday, 5 for Friday)",
    ),
    service: SSANCARService = Depends(get_ssancar_service),
) -> SSANCARDetailHealthResponse:
    """Validate a live detail from the current auction when inventory exists."""

    try:
        probe = await asyncio.to_thread(service.check_detail_health, week_number)
        return SSANCARDetailHealthResponse(
            status="healthy",
            week_number=probe.week_number,
            upstream_count=probe.upstream_count,
            detail_checked=probe.detail_checked,
            sample_car_no=probe.sample_car_no,
            egress=probe.egress,
            checked_at=probe.checked_at,
        )
    except SSANCARUpstreamError as error:
        ssancar_logger.warning(
            "SSANCAR detail health upstream failure code={}",
            error.code,
        )
        _raise_upstream_error(
            error,
            status_override=503,
            message="SSANCAR detail readiness probe failed",
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
        
        filter_options = await asyncio.to_thread(service.get_filter_options)
        
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
        gearbox=filters.get("transmission", ""),
        kmFrom=str(filters.get("mileage_from", 0)),
        kmTo=str(filters.get("mileage_to", 500000)),
        yearFrom=str(filters.get("year_from", 2000)),
        yearTo=str(filters.get("year_to") or (datetime.now().year + 1)),
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
        "week_number": response.week_number,
        "timestamp": response.timestamp.isoformat()
    }
