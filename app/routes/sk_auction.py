"""
SK Auction API Routes

FastAPI routes for SK Car Rental Auction.
URL: https://auction.skcarrental.com
"""

from fastapi import APIRouter, HTTPException, Query, Path
from typing import List, Optional
from loguru import logger

from app.models.sk_auction import (
    SKAuctionResponse,
    SKAuctionDetailResponse,
    SKAuctionBrandsResponse,
    SKAuctionModelsResponse,
    SKAuctionGenerationsResponse,
    SKAuctionFuelTypesResponse,
    SKAuctionYearsResponse,
    SKAuctionCountResponse,
    SKAuctionSearchFilters,
)
from app.services.sk_auction_service import SKAuctionService


router = APIRouter(prefix="/api/v1/sk-auction", tags=["SK Auction"])

# Global service instance
sk_auction_service = SKAuctionService()


# ==================== Car Listings ====================


@router.get("/cars", response_model=SKAuctionResponse)
async def get_cars(
    brand_code: Optional[str] = Query(None, alias="set_search_maker", description="Brand code (e.g., ABI000000005)"),
    model_code: Optional[str] = Query(None, alias="set_search_mdl", description="Model code (e.g., ABI000000096)"),
    generation_codes: Optional[str] = Query(None, alias="set_search_chk_carGrp", description="Comma-separated generation codes"),
    year_from: Optional[int] = Query(None, alias="search_startYyyy", description="Year from"),
    year_to: Optional[int] = Query(None, alias="search_endYyyy", description="Year to"),
    mileage_from: Optional[int] = Query(None, alias="search_startKm", description="Mileage from (km)"),
    mileage_to: Optional[int] = Query(None, alias="search_endKm", description="Mileage to (km)"),
    price_from: Optional[int] = Query(None, alias="search_startPrice", description="Price from (millions won)"),
    price_to: Optional[int] = Query(None, alias="search_endPrice", description="Price to (millions won)"),
    fuel_type: Optional[str] = Query(None, alias="search_fuelCd", description="Fuel type code"),
    transmission: Optional[str] = Query(None, alias="search_trnsCd", description="Transmission code (01=AT, 02=MT)"),
    accident_grade: Optional[str] = Query(None, alias="accidGrade", description="Accident grade (A-F)"),
    condition_grade: Optional[str] = Query(None, alias="stateGrade", description="Condition grade (A-F)"),
    exhibition_number: Optional[str] = Query(None, alias="search_exhiNo", description="Exhibition number"),
    lane_division: Optional[str] = Query(None, alias="search_LaneDiv", description="Lane division (A, B, etc.)"),
    region_code: str = Query("all", alias="search_doimCd", description="Region code"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Records per page"),
    auction_date: Optional[str] = Query(None, description="Auction date (YYYYMMDD format)"),
):
    """
    Get list of cars from SK Auction.

    Returns paginated list of cars with optional filters.
    Auction date defaults to today if not specified.
    """
    try:
        logger.info(f"📥 SK Auction cars request: page={page}, brand={brand_code}, model={model_code}")

        # Build filters
        filters = None
        if any([brand_code, model_code, generation_codes, year_from, year_to,
                mileage_from, mileage_to, price_from, price_to, fuel_type,
                transmission, accident_grade, condition_grade, exhibition_number,
                lane_division, region_code != "all"]):

            # Parse generation codes if provided
            gen_codes_list = None
            if generation_codes:
                gen_codes_list = [g.strip() for g in generation_codes.split(",")]

            filters = SKAuctionSearchFilters(
                brand_code=brand_code,
                model_code=model_code,
                generation_codes=gen_codes_list,
                year_from=year_from,
                year_to=year_to,
                mileage_from=mileage_from,
                mileage_to=mileage_to,
                price_from=price_from,
                price_to=price_to,
                fuel_type=fuel_type,
                transmission=transmission,
                accident_grade=accident_grade,
                condition_grade=condition_grade,
                exhibition_number=exhibition_number,
                lane_division=lane_division,
                region_code=region_code,
            )

        result = sk_auction_service.get_cars(
            filters=filters,
            page=page,
            page_size=page_size,
            auction_date=auction_date,
        )

        if not result.success:
            logger.warning(f"⚠️ SK Auction cars request failed: {result.message}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Failed to fetch cars",
                    "message": result.message,
                },
            )

        logger.info(f"✅ Returning {len(result.cars)} cars from SK Auction")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ SK Auction cars error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": str(e)},
        )


@router.post("/search", response_model=SKAuctionResponse)
async def search_cars(
    filters: SKAuctionSearchFilters,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Records per page"),
    auction_date: Optional[str] = Query(None, description="Auction date (YYYYMMDD format)"),
):
    """
    Search cars with filters (POST endpoint).

    Accepts filters in request body for complex queries.
    """
    try:
        logger.info(f"🔍 SK Auction search request: {filters.model_dump()}")

        result = sk_auction_service.search_cars(
            filters=filters,
            page=page,
            page_size=page_size,
            auction_date=auction_date,
        )

        if not result.success:
            logger.warning(f"⚠️ SK Auction search failed: {result.message}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Search failed",
                    "message": result.message,
                },
            )

        logger.info(f"✅ Search returned {len(result.cars)} cars")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ SK Auction search error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": str(e)},
        )


# ==================== Car Detail ====================


@router.get(
    "/cars/{mng_div_cd}/{mng_no}/{exhi_regi_seq}/detail",
    response_model=SKAuctionDetailResponse,
)
async def get_car_detail(
    mng_div_cd: str = Path(..., description="Management division code (e.g., SR, PC)"),
    mng_no: str = Path(..., description="Management number (e.g., SR25000114199)"),
    exhi_regi_seq: int = Path(..., description="Exhibition registration sequence"),
):
    """
    Get car detail by scraping HTML page.

    Returns comprehensive car information including:
    - Vehicle specifications
    - Owner information
    - Condition check results
    - Legal status
    - Tire information
    - Image gallery
    - Inspection record
    """
    try:
        logger.info(f"🔍 SK Auction detail request: {mng_div_cd}/{mng_no}/{exhi_regi_seq}")

        result = sk_auction_service.get_car_detail(
            mng_div_cd=mng_div_cd,
            mng_no=mng_no,
            exhi_regi_seq=exhi_regi_seq,
        )

        if not result.success:
            logger.warning(f"⚠️ SK Auction detail failed: {result.message}")

            # Determine appropriate status code
            status_code = 404 if "not found" in result.message.lower() else 400

            raise HTTPException(
                status_code=status_code,
                detail={
                    "error": "Failed to fetch car detail",
                    "message": result.message,
                    "mng_no": mng_no,
                },
            )

        logger.info(f"✅ Car detail retrieved for {mng_no}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ SK Auction detail error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": str(e)},
        )


# ==================== Filter Data ====================


@router.get("/brands", response_model=SKAuctionBrandsResponse)
async def get_brands(
    region_code: str = Query("all", description="Region code filter"),
):
    """
    Get list of car brands.

    Returns all available brands with exhibition counts.
    """
    try:
        logger.info("📋 SK Auction brands request")

        result = sk_auction_service.get_brands(region_code=region_code)

        if not result.success:
            logger.warning(f"⚠️ SK Auction brands failed: {result.message}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Failed to fetch brands",
                    "message": result.message,
                },
            )

        logger.info(f"✅ Returning {len(result.brands)} brands")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ SK Auction brands error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": str(e)},
        )


@router.get("/models/{brand_code}", response_model=SKAuctionModelsResponse)
async def get_models(
    brand_code: str = Path(..., description="Brand code (e.g., ABI000000005)"),
    region_code: str = Query("all", description="Region code filter"),
):
    """
    Get list of models for a brand.

    Returns all available models for the specified brand.
    """
    try:
        logger.info(f"📋 SK Auction models request for brand: {brand_code}")

        result = sk_auction_service.get_models(
            brand_code=brand_code,
            region_code=region_code,
        )

        if not result.success:
            logger.warning(f"⚠️ SK Auction models failed: {result.message}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Failed to fetch models",
                    "message": result.message,
                    "brand_code": brand_code,
                },
            )

        logger.info(f"✅ Returning {len(result.models)} models for brand {brand_code}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ SK Auction models error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": str(e)},
        )


@router.get("/generations/{model_code}", response_model=SKAuctionGenerationsResponse)
async def get_generations(
    model_code: str = Path(..., description="Model code (e.g., ABI000000096)"),
    region_code: str = Query("all", description="Region code filter"),
):
    """
    Get list of generations for a model.

    Returns all available generations/variants for the specified model.
    """
    try:
        logger.info(f"📋 SK Auction generations request for model: {model_code}")

        result = sk_auction_service.get_generations(
            model_code=model_code,
            region_code=region_code,
        )

        if not result.success:
            logger.warning(f"⚠️ SK Auction generations failed: {result.message}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Failed to fetch generations",
                    "message": result.message,
                    "model_code": model_code,
                },
            )

        logger.info(f"✅ Returning {len(result.generations)} generations for model {model_code}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ SK Auction generations error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": str(e)},
        )


@router.get("/fuel-types", response_model=SKAuctionFuelTypesResponse)
async def get_fuel_types():
    """
    Get list of fuel types.

    Returns all available fuel type options for filtering.
    """
    try:
        logger.info("📋 SK Auction fuel types request")

        result = sk_auction_service.get_fuel_types()

        if not result.success:
            logger.warning(f"⚠️ SK Auction fuel types failed: {result.message}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Failed to fetch fuel types",
                    "message": result.message,
                },
            )

        logger.info(f"✅ Returning {len(result.fuel_types)} fuel types")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ SK Auction fuel types error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": str(e)},
        )


@router.get("/years", response_model=SKAuctionYearsResponse)
async def get_years():
    """
    Get list of available years.

    Returns all available year options for filtering.
    Years are returned in descending order (newest first).
    """
    try:
        logger.info("📋 SK Auction years request")

        result = sk_auction_service.get_years()

        if not result.success:
            logger.warning(f"⚠️ SK Auction years failed: {result.message}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Failed to fetch years",
                    "message": result.message,
                },
            )

        logger.info(f"✅ Returning {len(result.years)} years")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ SK Auction years error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": str(e)},
        )


# ==================== Statistics ====================


@router.get("/total-count", response_model=SKAuctionCountResponse)
async def get_total_count(
    auction_date: Optional[str] = Query(None, description="Auction date (YYYYMMDD format)"),
):
    """
    Get total count of cars.

    Returns total number of cars available for the auction date.
    Defaults to today's date if not specified.
    """
    try:
        logger.info(f"📊 SK Auction total count request: date={auction_date}")

        result = sk_auction_service.get_total_count(auction_date=auction_date)

        if not result.success:
            logger.warning(f"⚠️ SK Auction count failed: {result.message}")
            # Return 0 count instead of error
            return SKAuctionCountResponse(
                success=False,
                total_count=0,
                message=result.message,
                auction_date=auction_date,
            )

        logger.info(f"✅ Total count: {result.total_count}")
        return result

    except Exception as e:
        logger.error(f"❌ SK Auction count error: {e}")
        return SKAuctionCountResponse(
            success=False,
            total_count=0,
            message=f"Error: {str(e)}",
            auction_date=auction_date,
        )


# ==================== Health & Info ====================


@router.get("/health")
async def health_check():
    """
    Check SK Auction service health.

    Returns service status and capabilities.
    """
    try:
        logger.info("🏥 SK Auction health check")

        result = sk_auction_service.health_check()
        return result

    except Exception as e:
        logger.error(f"❌ SK Auction health check error: {e}")
        return {
            "service": "SK Auction Service",
            "status": "unhealthy",
            "error": str(e),
        }


@router.get("/info")
async def get_info():
    """
    Get SK Auction API information.

    Returns basic information about the API endpoints.
    """
    return {
        "name": "SK Auction API",
        "version": "1.0.0",
        "description": "API for SK Car Rental Auction (auction.skcarrental.com)",
        "features": [
            "Car listings with filters",
            "Car detail (HTML scraping)",
            "Brand/Model/Generation cascading filters",
            "Fuel type filters",
            "Year range filters",
            "Price range filters",
            "Mileage range filters",
            "Condition grade filters",
        ],
        "authentication": "Session-based with 30-minute expiry",
        "base_url": "https://auction.skcarrental.com",
        "endpoints": {
            "cars": "/api/v1/sk-auction/cars",
            "car_detail": "/api/v1/sk-auction/cars/{mng_div_cd}/{mng_no}/{exhi_regi_seq}/detail",
            "search": "/api/v1/sk-auction/search",
            "brands": "/api/v1/sk-auction/brands",
            "models": "/api/v1/sk-auction/models/{brand_code}",
            "generations": "/api/v1/sk-auction/generations/{model_code}",
            "fuel_types": "/api/v1/sk-auction/fuel-types",
            "years": "/api/v1/sk-auction/years",
            "total_count": "/api/v1/sk-auction/total-count",
            "health": "/api/v1/sk-auction/health",
        },
        "filter_info": {
            "year_range": "Use year_from and year_to (ensure year_from <= year_to)",
            "price_range": "Values in millions of won",
            "mileage_range": "Values in kilometers",
            "condition_grades": "A (best) to F (worst)",
            "transmission": "01 = Automatic, 02 = Manual",
        },
    }
