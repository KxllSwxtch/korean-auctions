from fastapi import APIRouter, HTTPException, Query, Depends, status
from typing import Optional
import logging

from app.models.encar import (
    EncarCatalogResponse,
    EncarFiltersResponse,
    EncarError,
)
from app.services.encar_service import encar_service, EncarService
from app.core.logging import get_logger
from app.core.single_flight import SingleFlight

logger = get_logger("encar_routes")

_catalog_flight = SingleFlight()
_filters_flight = SingleFlight()

router = APIRouter(
    responses={404: {"description": "Not found"}},
)


# Dependency for getting service
def get_encar_service() -> EncarService:
    return encar_service


@router.get(
    "/catalog",
    response_model=EncarCatalogResponse,
    summary="Get Encar catalog listing",
    description="Get paginated list of cars from Encar with optional filters",
    responses={
        200: {
            "description": "Successful response with cars data",
            "model": EncarCatalogResponse
        },
        500: {
            "description": "Internal server error",
            "model": EncarError
        }
    }
)
async def get_catalog(
    q: str = Query(
        "(And.Hidden.N._.CarType.A._.SellType.%EC%9D%BC%EB%B0%98.)",
        description="Query string for filters"
    ),
    sr: str = Query(
        "|ModifiedDate|0|21",
        description="Sort and pagination string (format: |SortField|SortOrder|Limit)"
    ),
    count: bool = Query(True, description="Whether to return total count"),
    page: int = Query(1, ge=1, description="Page number"),
    cache: bool = Query(True, description="Whether to use caching"),
    service: EncarService = Depends(get_encar_service)
) -> EncarCatalogResponse:
    """
    Get paginated list of cars from Encar

    Args:
        q: Query string for filters (URL-encoded Encar query format)
        sr: Sort and pagination string (format: |SortField|SortOrder|Limit)
        count: Whether to return total count
        page: Page number (starts from 1)
        cache: Whether to use server-side caching (default: True)

    Returns:
        EncarCatalogResponse with cars data and total count
    """
    try:
        logger.info(f"Fetching Encar catalog - page: {page}, q: {q[:50]}...")

        # Deduplicate concurrent identical requests via SingleFlight
        flight_key = f"catalog:{q}:{sr}:{count}:{page}:{cache}"

        async def _fetch():
            return await service.get_catalog(
                q=q, sr=sr, count=count, page=page, use_cache=cache
            )

        response = await _catalog_flight.do(flight_key, _fetch)

        if not response.success:
            logger.error(f"Failed to fetch Encar catalog: {response.message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.message or "Failed to fetch Encar catalog"
            )

        logger.info(f"Successfully fetched {len(response.SearchResults)} cars from Encar")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching Encar catalog: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get(
    "/filters",
    response_model=EncarFiltersResponse,
    summary="Get Encar filter options",
    description="Get available filter options for Encar search (batched endpoint)",
    responses={
        200: {
            "description": "Successful response with filter options",
            "model": EncarFiltersResponse
        },
        500: {
            "description": "Internal server error",
            "model": EncarError
        }
    }
)
async def get_filters(
    manufacturer: Optional[str] = Query(None, description="Selected manufacturer"),
    model_group: Optional[str] = Query(None, description="Selected model group"),
    model: Optional[str] = Query(None, description="Selected model"),
    configuration: Optional[str] = Query(None, description="Selected configuration"),
    badge: Optional[str] = Query(None, description="Selected badge"),
    cache: bool = Query(True, description="Whether to use caching"),
    service: EncarService = Depends(get_encar_service)
) -> EncarFiltersResponse:
    """
    Get available filter options for Encar search

    This endpoint returns all filter options in a single call to reduce
    the number of API requests needed for the frontend.

    Args:
        manufacturer: Selected manufacturer to filter dependent options
        model_group: Selected model group
        model: Selected model
        configuration: Selected configuration
        badge: Selected badge
        cache: Whether to use server-side caching (default: True)

    Returns:
        EncarFiltersResponse with all filter options
    """
    try:
        logger.info(f"Fetching Encar filters - manufacturer: {manufacturer}")

        # Deduplicate concurrent identical requests via SingleFlight
        flight_key = f"filters:{manufacturer}:{model_group}:{model}:{configuration}:{badge}:{cache}"

        async def _fetch():
            return await service.get_filters(
                manufacturer=manufacturer,
                model_group=model_group,
                model=model,
                configuration=configuration,
                badge=badge,
                use_cache=cache,
            )

        response = await _filters_flight.do(flight_key, _fetch)

        if not response.success:
            logger.error(f"Failed to fetch Encar filters: {response.message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.message or "Failed to fetch Encar filters"
            )

        logger.info("Successfully fetched Encar filters")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching Encar filters: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post(
    "/cache/clear",
    summary="Clear Encar cache",
    description="Clear all cached Encar data",
    responses={
        200: {
            "description": "Cache cleared successfully",
        }
    }
)
async def clear_cache(
    service: EncarService = Depends(get_encar_service)
):
    """
    Clear all cached Encar data

    This endpoint can be used to force fresh data fetching
    """
    try:
        logger.info("Clearing Encar cache")
        service.clear_cache()
        return {"success": True, "message": "Cache cleared successfully"}

    except Exception as e:
        logger.error(f"Error clearing Encar cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )
