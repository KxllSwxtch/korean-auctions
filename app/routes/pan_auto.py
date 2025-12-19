"""
FastAPI routes for Pan-Auto.ru API proxy
Provides HP (horsepower) and Russian customs costs data
"""

from fastapi import APIRouter, HTTPException, Query, Depends, status, Path
import logging

from app.models.pan_auto import (
    PanAutoCarDetailResponse,
    PanAutoError,
)
from app.services.pan_auto_service import pan_auto_service, PanAutoService
from app.core.logging import get_logger

logger = get_logger("pan_auto_routes")

router = APIRouter(
    responses={404: {"description": "Not found"}},
)


# Dependency for getting service
def get_pan_auto_service() -> PanAutoService:
    return pan_auto_service


@router.get(
    "/cars/{car_id}",
    response_model=PanAutoCarDetailResponse,
    summary="Get car data from Pan-Auto.ru",
    description="Get HP (horsepower) and Russian customs costs for a car by Encar ID",
    responses={
        200: {
            "description": "Successful response with car data",
            "model": PanAutoCarDetailResponse
        },
        404: {
            "description": "Car not found on Pan-Auto.ru",
            "model": PanAutoError
        },
        500: {
            "description": "Internal server error",
            "model": PanAutoError
        }
    }
)
async def get_car_detail(
    car_id: str = Path(
        ...,
        description="Encar car ID",
        example="40923777"
    ),
    cache: bool = Query(True, description="Whether to use caching"),
    service: PanAutoService = Depends(get_pan_auto_service)
) -> PanAutoCarDetailResponse:
    """
    Get car data from Pan-Auto.ru API

    This endpoint proxies requests to Pan-Auto.ru to fetch:
    - HP (horsepower) value
    - Russian customs costs (clearanceCost, utilizationFee, customsDuty)
    - Other car details

    Args:
        car_id: Encar car ID (e.g., "40923777")
        cache: Whether to use server-side caching (default: True, 5 min TTL)

    Returns:
        PanAutoCarDetailResponse with HP and customs costs data
    """
    try:
        logger.info(f"Fetching Pan-Auto data for car: {car_id}")

        # Fetch car detail from service
        response = await service.get_car_detail(
            car_id=car_id,
            use_cache=cache
        )

        if not response.success:
            logger.warning(f"Pan-Auto returned no data for car {car_id}: {response.message}")
            # Still return the response with success=False
            # Frontend can handle the case when car is not found
            return response

        logger.info(f"Successfully fetched Pan-Auto data for car {car_id}: HP={response.data.hp if response.data else 'N/A'}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching Pan-Auto data for car {car_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post(
    "/cache/clear",
    summary="Clear Pan-Auto cache",
    description="Clear all cached Pan-Auto data",
    responses={
        200: {
            "description": "Cache cleared successfully",
        }
    }
)
async def clear_cache(
    service: PanAutoService = Depends(get_pan_auto_service)
):
    """
    Clear all cached Pan-Auto data

    This endpoint can be used to force fresh data fetching
    """
    try:
        logger.info("Clearing Pan-Auto cache")
        service.clear_cache()
        return {"success": True, "message": "Pan-Auto cache cleared successfully"}

    except Exception as e:
        logger.error(f"Error clearing Pan-Auto cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )
