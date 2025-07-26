from fastapi import APIRouter, HTTPException, Query, Depends, status
from typing import Optional
import logging

from app.models.bikemart import (
    BikemartResponse,
    BikemartBrandsResponse,
    BikemartFiltersResponse,
    BikemartError,
    BikemartBikeDetailResponse,
    BikemartModelsResponse
)
from app.services.bikemart_service import bikemart_service, BikemartService
from app.core.logging import get_logger

logger = get_logger("bikemart_routes")

router = APIRouter(
    responses={404: {"description": "Not found"}},
)


# Dependency for getting service
def get_bikemart_service() -> BikemartService:
    return bikemart_service


@router.get(
    "/bikes",
    response_model=BikemartResponse,
    summary="Get bikes listing",
    description="Get paginated list of bikes with optional filters",
    responses={
        200: {
            "description": "Successful response with bikes data",
            "model": BikemartResponse
        },
        500: {
            "description": "Internal server error",
            "model": BikemartError
        }
    }
)
async def get_bikes(
    page: int = Query(1, ge=1, description="Page number"),
    brand_seq: Optional[str] = Query(None, description="Brand sequence ID"),
    model: Optional[str] = Query(None, description="Model name"),
    min_year: Optional[int] = Query(None, ge=1990, le=2030, description="Minimum year"),
    max_year: Optional[int] = Query(None, ge=1990, le=2030, description="Maximum year"),
    min_price: Optional[int] = Query(None, ge=0, description="Minimum price in 만원"),
    max_price: Optional[int] = Query(None, ge=0, description="Maximum price in 만원"),
    min_mileage: Optional[int] = Query(None, ge=0, description="Minimum mileage in km"),
    max_mileage: Optional[int] = Query(None, ge=0, description="Maximum mileage in km"),
    search_text: Optional[str] = Query(None, description="Search text"),
    sort_by: Optional[str] = Query(None, description="Sort option"),
    service: BikemartService = Depends(get_bikemart_service)
) -> BikemartResponse:
    """
    Get paginated list of bikes with optional filters
    
    Args:
        page: Page number (starts from 1)
        brand_seq: Filter by brand sequence ID
        model: Filter by model name
        min_year: Minimum manufacturing year
        max_year: Maximum manufacturing year
        min_price: Minimum price in 만원 (10,000 KRW)
        max_price: Maximum price in 만원 (10,000 KRW)
        min_mileage: Minimum mileage in kilometers
        max_mileage: Maximum mileage in kilometers
        search_text: Search in title/description
        sort_by: Sort option (e.g., 'price_asc', 'price_desc', 'year_desc')
        
    Returns:
        BikemartResponse with bikes data and pagination info
    """
    try:
        logger.info(f"Fetching bikes - page: {page}, filters: brand={brand_seq}, model={model}")
        
        # Validate year range
        if min_year and max_year and min_year > max_year:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="min_year cannot be greater than max_year"
            )
        
        # Validate price range
        if min_price and max_price and min_price > max_price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="min_price cannot be greater than max_price"
            )
        
        # Validate mileage range
        if min_mileage and max_mileage and min_mileage > max_mileage:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="min_mileage cannot be greater than max_mileage"
            )
        
        # Fetch bikes from service
        response = await service.get_bikes(
            page=page,
            brand_seq=brand_seq,
            model=model,
            min_year=min_year,
            max_year=max_year,
            min_price=min_price,
            max_price=max_price,
            min_mileage=min_mileage,
            max_mileage=max_mileage,
            search_text=search_text,
            sort_by=sort_by
        )
        
        if not response.success:
            logger.error(f"Failed to fetch bikes: {response.message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.message or "Failed to fetch bikes"
            )
        
        logger.info(f"Successfully fetched {len(response.data)} bikes")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching bikes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get(
    "/brands",
    response_model=BikemartBrandsResponse,
    summary="Get bike brands",
    description="Get list of available bike brands",
    responses={
        200: {
            "description": "Successful response with brands data",
            "model": BikemartBrandsResponse
        },
        500: {
            "description": "Internal server error",
            "model": BikemartError
        }
    }
)
async def get_brands(
    service: BikemartService = Depends(get_bikemart_service)
) -> BikemartBrandsResponse:
    """
    Get list of available bike brands
    
    Returns:
        BikemartBrandsResponse with brands data
    """
    try:
        logger.info("Fetching bike brands")
        
        response = await service.get_brands()
        
        if not response.success:
            logger.error(f"Failed to fetch brands: {response.message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.message or "Failed to fetch brands"
            )
        
        logger.info(f"Successfully fetched {len(response.data)} brands")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching brands: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get(
    "/filters",
    response_model=BikemartFiltersResponse,
    summary="Get filter options",
    description="Get available filter options for bikes search",
    responses={
        200: {
            "description": "Successful response with filter options",
            "model": BikemartFiltersResponse
        },
        500: {
            "description": "Internal server error",
            "model": BikemartError
        }
    }
)
async def get_filters(
    service: BikemartService = Depends(get_bikemart_service)
) -> BikemartFiltersResponse:
    """
    Get available filter options for bikes search
    
    Returns:
        BikemartFiltersResponse with filter options
    """
    try:
        logger.info("Fetching filter options")
        
        response = await service.get_filters()
        
        if not response.success:
            logger.error(f"Failed to fetch filters: {response.message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.message or "Failed to fetch filters"
            )
        
        logger.info("Successfully fetched filter options")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching filters: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get(
    "/brands/{brand_seq}/models",
    response_model=BikemartModelsResponse,
    summary="Get bike models by brand",
    description="Get list of available bike models for a specific brand",
    responses={
        200: {
            "description": "Successful response with models data",
            "model": BikemartModelsResponse
        },
        500: {
            "description": "Internal server error",
            "model": BikemartError
        }
    }
)
async def get_models_by_brand(
    brand_seq: str,
    service: BikemartService = Depends(get_bikemart_service)
) -> BikemartModelsResponse:
    """
    Get list of models for a specific brand
    
    Args:
        brand_seq: Brand sequence ID
        
    Returns:
        BikemartModelsResponse with models data
    """
    try:
        logger.info(f"Fetching models for brand: {brand_seq}")
        
        response = await service.get_models_by_brand(brand_seq)
        
        if not response.success:
            logger.error(f"Failed to fetch models: {response.message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.message or "Failed to fetch models"
            )
        
        logger.info(f"Successfully fetched {len(response.data)} models for brand: {brand_seq}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching models: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get(
    "/bikes/{seq}",
    response_model=BikemartBikeDetailResponse,
    summary="Get bike detail",
    description="Get detailed information about a specific bike",
    responses={
        200: {
            "description": "Successful response with bike detail data",
            "model": BikemartBikeDetailResponse
        },
        404: {
            "description": "Bike not found",
            "model": BikemartError
        },
        500: {
            "description": "Internal server error",
            "model": BikemartError
        }
    }
)
async def get_bike_detail(
    seq: str,
    service: BikemartService = Depends(get_bikemart_service)
) -> BikemartBikeDetailResponse:
    """
    Get detailed information about a specific bike
    
    Args:
        seq: Bike sequence ID
        
    Returns:
        BikemartBikeDetailResponse with bike detail data including images
    """
    try:
        logger.info(f"Fetching bike detail for seq: {seq}")
        
        response = await service.get_bike_detail(seq)
        
        if not response.success:
            logger.error(f"Failed to fetch bike detail: {response.message}")
            if "not found" in (response.message or "").lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Bike not found"
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.message or "Failed to fetch bike detail"
            )
        
        logger.info(f"Successfully fetched bike detail for seq: {seq}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching bike detail: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )