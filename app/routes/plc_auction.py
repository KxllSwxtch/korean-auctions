from fastapi import APIRouter, HTTPException, Query, Depends, Body
from typing import Optional, Dict, Any, List
from datetime import datetime
from loguru import logger

from app.models.plc_auction import (
    PLCAuctionResponse, PLCAuctionFilters, 
    PLCAuctionManufacturer, PLCAuctionModel,
    PLCAuctionCarDetail, PLCAuctionDetailResponse
)
from app.services.plc_auction_service import PLCAuctionService
from app.core.logging import get_logger

# Setup logger
plc_logger = get_logger("plc_auction_routes")

router = APIRouter(prefix="/api/v1/glovis", tags=["Glovis"])

# Global service instance
plc_auction_service = PLCAuctionService()


def get_plc_auction_service() -> PLCAuctionService:
    """Dependency to get PLCAuctionService instance"""
    return plc_auction_service


@router.get("/cars", response_model=PLCAuctionResponse)
async def get_glovis_cars(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    country: str = Query("kr", description="Country code"),
    date: Optional[str] = Query(None, description="Auction date timestamp"),
    price_type: str = Query("auction", description="Price type"),
    manufacturer: Optional[str] = Query(None, description="Car manufacturer filter"),
    model: Optional[str] = Query(None, description="Car model filter"),
    fuel: Optional[str] = Query(None, description="Fuel type filter"),
    color: Optional[str] = Query(None, description="Color filter"),
    year_from: Optional[int] = Query(None, description="Year from filter"),
    year_to: Optional[int] = Query(None, description="Year to filter"),
    price_from: Optional[float] = Query(None, description="Price from filter (USD)"),
    price_to: Optional[float] = Query(None, description="Price to filter (USD)"),
    transmission: Optional[str] = Query(None, description="Transmission type filter"),
    mileage_from: Optional[int] = Query(None, description="Mileage from filter (km)"),
    mileage_to: Optional[int] = Query(None, description="Mileage to filter (km)"),
) -> PLCAuctionResponse:
    """
    Get list of cars from PLC Auction (Glovis)
    
    **Example usage:**
    ```
    GET /api/v1/glovis/cars?page=1&manufacturer=HYUNDAI
    ```
    """
    try:
        plc_logger.info(f"📥 Request for PLC Auction cars (page {page})")
        
        # Build filters
        filters = PLCAuctionFilters(
            page=page,
            page_size=page_size,
            country=country,
            date=date,
            price_type=price_type,
            manufacturer=manufacturer,
            model=model,
            fuel=fuel,
            color=color,
            year_from=year_from,
            year_to=year_to,
            price_from=price_from,
            price_to=price_to,
            transmission=transmission,
            mileage_from=mileage_from,
            mileage_to=mileage_to
        )
        
        # Get data
        result = plc_auction_service.fetch_cars(filters)
        
        if result.success:
            plc_logger.info(f"✅ Successfully fetched {len(result.cars)} cars from PLC Auction")
        else:
            plc_logger.error(f"❌ Error fetching PLC Auction data: {result.message}")
        
        return result
        
    except Exception as e:
        plc_logger.error(f"❌ Unexpected error fetching PLC Auction cars: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/search", response_model=PLCAuctionResponse)
async def search_glovis_cars(
    filters: PLCAuctionFilters
) -> PLCAuctionResponse:
    """
    Search cars with advanced filters
    
    **Request body example:**
    ```json
    {
        "page": 1,
        "page_size": 20,
        "manufacturer": "HYUNDAI",
        "model": "Santa Fe",
        "year_from": 2020,
        "year_to": 2024,
        "price_from": 10000,
        "price_to": 50000
    }
    ```
    """
    try:
        plc_logger.info(f"🔍 Search PLC Auction cars with filters")
        
        result = plc_auction_service.search_cars(filters)
        
        if result.success:
            plc_logger.info(
                f"✅ Found {result.total_count} cars "
                f"(page {result.current_page}/{result.page_size})"
            )
        else:
            plc_logger.error(f"❌ Search error: {result.message}")
        
        return result
        
    except Exception as e:
        plc_logger.error(f"❌ Unexpected error in search: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/filters/manufacturers", response_model=Dict[str, Any])
async def get_manufacturers() -> Dict[str, Any]:
    """
    Get list of available car manufacturers
    
    **Example usage:**
    ```
    GET /api/v1/glovis/filters/manufacturers
    ```
    """
    try:
        plc_logger.info("🏭 Request for manufacturers list")
        
        manufacturers, success = plc_auction_service.get_manufacturers()
        
        if success:
            plc_logger.info(f"✅ Retrieved {len(manufacturers)} manufacturers")
            return {
                "success": True,
                "message": "Manufacturers retrieved successfully",
                "manufacturers": manufacturers,
                "total_count": len(manufacturers),
                "timestamp": datetime.now().isoformat()
            }
        else:
            plc_logger.error("❌ Failed to get manufacturers")
            return {
                "success": False,
                "message": "Failed to retrieve manufacturers",
                "manufacturers": [],
                "total_count": 0,
                "timestamp": datetime.now().isoformat()
            }
            
    except Exception as e:
        plc_logger.error(f"❌ Unexpected error getting manufacturers: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/filters/models/{manufacturer_code}", response_model=Dict[str, Any])
async def get_models(manufacturer_code: str) -> Dict[str, Any]:
    """
    Get list of models for selected manufacturer
    
    **Parameters:**
    - **manufacturer_code**: Manufacturer code (e.g., HYUNDAI, KIA)
    
    **Example usage:**
    ```
    GET /api/v1/glovis/filters/models/HYUNDAI
    ```
    """
    try:
        plc_logger.info(f"🚗 Request for models of manufacturer {manufacturer_code}")
        
        models, success = plc_auction_service.get_models(manufacturer_code)
        
        if success:
            plc_logger.info(f"✅ Retrieved {len(models)} models")
            return {
                "success": True,
                "message": "Models retrieved successfully",
                "models": models,
                "total_count": len(models),
                "manufacturer_code": manufacturer_code,
                "timestamp": datetime.now().isoformat()
            }
        else:
            plc_logger.error(f"❌ Failed to get models for {manufacturer_code}")
            return {
                "success": False,
                "message": f"Failed to retrieve models for {manufacturer_code}",
                "models": [],
                "total_count": 0,
                "manufacturer_code": manufacturer_code,
                "timestamp": datetime.now().isoformat()
            }
            
    except Exception as e:
        plc_logger.error(f"❌ Unexpected error getting models: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/cars/{slug}", response_model=PLCAuctionDetailResponse)
async def get_car_detail(
    slug: str,
    service: PLCAuctionService = Depends(get_plc_auction_service)
) -> PLCAuctionDetailResponse:
    """
    Get detailed information about a specific car
    
    **Parameters:**
    - **slug**: The car slug from the URL
    
    **Example usage:**
    ```
    GET /api/v1/glovis/cars/hyundai-santa-fe-2023-kmhs281lgpu493682-25-7112c3769debd7a350b2a5a26e36d3ff
    ```
    """
    try:
        plc_logger.info(f"📥 Request for car detail: {slug}")
        
        car_detail = service.get_car_detail(slug)
        
        if car_detail:
            plc_logger.info(f"✅ Successfully retrieved car detail for VIN: {car_detail.vin}")
            return PLCAuctionDetailResponse(
                success=True,
                message="Car details retrieved successfully",
                data=car_detail
            )
        else:
            plc_logger.error(f"❌ Car not found: {slug}")
            raise HTTPException(
                status_code=404,
                detail=f"Car not found: {slug}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        plc_logger.error(f"❌ Unexpected error getting car detail: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/health", response_model=Dict[str, Any])
async def health_check() -> Dict[str, Any]:
    """
    Check health status of PLC Auction service
    
    **Example usage:**
    ```
    GET /api/v1/glovis/health
    ```
    """
    try:
        plc_logger.info("🏥 Health check request")
        
        return {
            "success": True,
            "message": "PLC Auction service is healthy",
            "service": "PLC Auction (Glovis)",
            "status": "active",
            "base_url": plc_auction_service.BASE_URL,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        plc_logger.error(f"❌ Health check failed: {e}")
        return {
            "success": False,
            "message": f"Service unhealthy: {str(e)}",
            "service": "PLC Auction (Glovis)",
            "status": "error",
            "timestamp": datetime.now().isoformat()
        }


# SSANCAR compatibility endpoints
@router.get("/filters/ssancar/manufacturers", response_model=Dict[str, Any])
async def get_ssancar_manufacturers() -> Dict[str, Any]:
    """Get manufacturers in SSANCAR format for compatibility"""
    return await get_manufacturers()


@router.get("/filters/ssancar/models/{manufacturer_code}", response_model=Dict[str, Any])
async def get_ssancar_models(manufacturer_code: str) -> Dict[str, Any]:
    """Get models in SSANCAR format for compatibility"""
    return await get_models(manufacturer_code)


@router.post("/filters/ssancar/search", response_model=PLCAuctionResponse)
async def search_ssancar_cars(
    filters: Dict[str, Any] = Body(..., description="Search filters")
) -> PLCAuctionResponse:
    """Search cars in SSANCAR format for compatibility"""
    # Convert SSANCAR filters to PLC Auction filters
    plc_filters = PLCAuctionFilters(
        page=filters.get("page", 1),
        page_size=filters.get("page_size", 20),
        manufacturer=filters.get("manufacturer"),
        model=filters.get("model"),
        fuel=filters.get("fuel"),
        color=filters.get("color"),
        year_from=filters.get("year_from"),
        year_to=filters.get("year_to"),
        price_from=filters.get("price_from"),
        price_to=filters.get("price_to"),
        transmission=filters.get("transmission"),
        mileage_from=filters.get("mileage_from"),
        mileage_to=filters.get("mileage_to")
    )
    
    return await search_glovis_cars(plc_filters)


@router.get("/cars/ssancar/{car_no}", response_model=PLCAuctionDetailResponse)
async def get_ssancar_car_detail(
    car_no: str,
    service: PLCAuctionService = Depends(get_plc_auction_service)
) -> PLCAuctionDetailResponse:
    """Get car detail in SSANCAR format for compatibility"""
    # In SSANCAR format, car_no might be used directly as slug
    # For PLC auction, we need to find or construct the proper slug
    # For now, we'll use car_no as slug (may need adjustment based on actual mapping)
    return await get_car_detail(car_no, service)