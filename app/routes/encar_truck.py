"""
FastAPI routes for Encar Truck API
Provides endpoints for truck catalog and vehicle details
"""

from fastapi import APIRouter, HTTPException, Query, Depends, status
import logging

from app.models.encar_truck import (
    EncarTruckListResponse,
    EncarTruckDetailsResponse,
    EncarTruckError,
)
from app.services.encar_truck_service import encar_truck_service, EncarTruckService
from app.core.logging import get_logger

logger = get_logger("encar_truck_routes")

router = APIRouter(
    responses={404: {"description": "Not found"}},
)


# Dependency for getting service
def get_truck_service() -> EncarTruckService:
    return encar_truck_service


@router.get(
    "/trucks",
    response_model=EncarTruckListResponse,
    summary="Get Encar truck catalog listing",
    description="Get paginated list of trucks/special equipment from Encar with optional filters",
    responses={
        200: {
            "description": "Successful response with trucks data",
            "model": EncarTruckListResponse
        },
        500: {
            "description": "Internal server error",
            "model": EncarTruckError
        }
    }
)
async def get_trucks(
    q: str = Query(
        None,
        description="Query string for filters. If not provided, uses default query for trucks with EncarDiagnosis"
    ),
    sr: str = Query(
        "|ModifiedDate|0|21",
        description="Sort and pagination string (format: |SortField|Offset|Limit)"
    ),
    count: bool = Query(True, description="Whether to return total count"),
    cache: bool = Query(True, description="Whether to use caching"),
    service: EncarTruckService = Depends(get_truck_service)
) -> EncarTruckListResponse:
    """
    Get paginated list of trucks from Encar

    Args:
        q: Query string for filters (URL-encoded Encar query format).
           Default: (And.Hidden.N._.(Or.ServiceMark.EncarDiagnosisP0...))
        sr: Sort and pagination string (format: |SortField|Offset|Limit)
        count: Whether to return total count
        cache: Whether to use server-side caching (default: True)

    Returns:
        EncarTruckListResponse with trucks data and total count

    Query format examples:
        - Default (all with diagnosis): (And.Hidden.N._.(Or.ServiceMark.EncarDiagnosisP0._.ServiceMark.EncarDiagnosisP1._.ServiceMark.EncarDiagnosisP2.))
        - Filter by manufacturer: (And.Hidden.N._.Manufacturer.현대._.(Or.ServiceMark.EncarDiagnosisP0...))
        - Filter by capacity: (And.Hidden.N._.Capacity.1톤._.(Or.ServiceMark.EncarDiagnosisP0...))
        - Filter by form detail: (And.Hidden.N._.FormDetail.냉동탑._.(Or.ServiceMark.EncarDiagnosisP0...))

    Sort options:
        - |ModifiedDate|{offset}|{limit} - Sort by modified date (newest first)
        - |PriceAsc|{offset}|{limit} - Sort by price ascending
        - |PriceDesc|{offset}|{limit} - Sort by price descending
        - |MileageAsc|{offset}|{limit} - Sort by mileage ascending
        - |MileageDesc|{offset}|{limit} - Sort by mileage descending
        - |Year|{offset}|{limit} - Sort by year descending
    """
    try:
        logger.info(f"Fetching Encar trucks - q: {q[:50] if q else 'default'}..., sr: {sr}")

        # Fetch trucks from service
        response = await service.get_trucks(
            q=q,
            sr=sr,
            count=count,
            use_cache=cache
        )

        if not response.success:
            logger.error(f"Failed to fetch Encar trucks: {response.message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.message or "Failed to fetch Encar trucks"
            )

        logger.info(f"Successfully fetched {len(response.SearchResults)} trucks from Encar (total: {response.Count})")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching Encar trucks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get(
    "/trucks/{vehicle_id}",
    response_model=EncarTruckDetailsResponse,
    summary="Get truck details",
    description="Get detailed information for a specific truck by vehicle ID",
    responses={
        200: {
            "description": "Successful response with truck details",
            "model": EncarTruckDetailsResponse
        },
        404: {
            "description": "Truck not found",
            "model": EncarTruckError
        },
        500: {
            "description": "Internal server error",
            "model": EncarTruckError
        }
    }
)
async def get_truck_details(
    vehicle_id: str,
    cache: bool = Query(True, description="Whether to use caching"),
    service: EncarTruckService = Depends(get_truck_service)
) -> EncarTruckDetailsResponse:
    """
    Get detailed information for a specific truck

    Args:
        vehicle_id: The vehicle ID from Encar (e.g., "41238622")
        cache: Whether to use server-side caching (default: True)

    Returns:
        EncarTruckDetailsResponse with full truck details including:
        - Category: manufacturer, model, grade, form details, capacity
        - Spec: mileage, transmission, fuel, color, horsepower
        - Advertisement: price, status
        - Photos: exterior, interior, options, thumbnails
        - Contents: seller description
        - Options: standard and additional equipment
    """
    try:
        logger.info(f"Fetching truck details for vehicle_id: {vehicle_id}")

        # Fetch truck details from service
        response = await service.get_truck_details(
            vehicle_id=vehicle_id,
            use_cache=cache
        )

        if not response.success:
            logger.error(f"Failed to fetch truck details: {response.message}")

            # Check if it's a not found error
            if "404" in str(response.message) or "not found" in str(response.message).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Truck with ID {vehicle_id} not found"
                )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.message or "Failed to fetch truck details"
            )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Truck with ID {vehicle_id} not found"
            )

        logger.info(f"Successfully fetched truck details for {vehicle_id}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching truck details: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post(
    "/trucks/cache/clear",
    summary="Clear truck cache",
    description="Clear all cached truck data",
    responses={
        200: {
            "description": "Cache cleared successfully",
        }
    }
)
async def clear_truck_cache(
    service: EncarTruckService = Depends(get_truck_service)
):
    """
    Clear all cached truck data

    This endpoint can be used to force fresh data fetching
    """
    try:
        logger.info("Clearing Encar truck cache")
        service.clear_cache()
        return {"success": True, "message": "Truck cache cleared successfully"}

    except Exception as e:
        logger.error(f"Error clearing truck cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )
