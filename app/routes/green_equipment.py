"""
FastAPI routes for Green Heavy Equipment (4396200.com)
Provides endpoints for equipment catalog and details
"""

from fastapi import APIRouter, HTTPException, Query, Depends, status
import logging

from app.models.green_equipment import (
    GreenEquipmentListResponse,
    GreenEquipmentDetailsResponse,
    CategoriesResponse,
    GreenEquipmentError,
    EQUIPMENT_CATEGORIES,
)
from app.services.green_equipment_service import green_equipment_service, GreenEquipmentService
from app.core.logging import get_logger

logger = get_logger("green_equipment_routes")

router = APIRouter(
    responses={404: {"description": "Not found"}},
)


# Dependency for getting service
def get_equipment_service() -> GreenEquipmentService:
    return green_equipment_service


@router.get(
    "/equipment",
    response_model=GreenEquipmentListResponse,
    summary="Get heavy equipment catalog listing",
    description="Get paginated list of heavy equipment from Green Heavy Equipment (4396200.com)",
    responses={
        200: {
            "description": "Successful response with equipment data",
            "model": GreenEquipmentListResponse
        },
        500: {
            "description": "Internal server error",
            "model": GreenEquipmentError
        }
    }
)
async def get_equipment(
    category: str = Query(
        None,
        description="Category code (100-111). If not provided, returns equipment from all categories"
    ),
    subcategory: str = Query(
        None,
        description="Subcategory code (e.g., 100100, 101102). Requires category to be set."
    ),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(21, ge=1, le=100, description="Items per page"),
    manufacturer: str = Query(None, description="Filter by manufacturer (Korean name)"),
    year_from: int = Query(None, ge=1975, le=2026, description="Minimum year"),
    year_to: int = Query(None, ge=1975, le=2026, description="Maximum year"),
    min_price: int = Query(None, ge=0, description="Minimum price in 만원 (10,000 KRW units)"),
    max_price: int = Query(None, ge=0, description="Maximum price in 만원 (10,000 KRW units)"),
    cache: bool = Query(True, description="Whether to use caching"),
    service: GreenEquipmentService = Depends(get_equipment_service)
) -> GreenEquipmentListResponse:
    """
    Get paginated list of heavy equipment

    Args:
        category: Category code (100-111). Available categories:
            - 100: Excavators & Attachments (굴삭기/어태치부속)
            - 101: Dump Trucks & Trailers (덤프트럭/추레라)
            - 102: Mixer Trucks & Pump Cars (믹서트럭/펌프카)
            - 103: Forklifts & Highlanders (지게차/하이랜더)
            - 104: Armroll/Hook Lift/Water Trucks (압롤/진게/물차)
            - 105: Cargo/Refrigerated/Box Trucks (카고/냉동/탑차)
            - 106: Cranes & Cargo Cranes (크레인/카고그레인)
            - 107: Loaders/Dozers/Graders (로더/도자/그레다)
            - 108: Finishers & Rollers (피니셔/로울러)
            - 109: Crushers & Batching Plants (크락샤/배차플랜트)
            - 110: Compressors/Drills/Pile Drivers (콤푸/드릴/항타기)
            - 111: Other Construction Equipment (기타건설기계)
        subcategory: Subcategory code (e.g., 100100 for Large Excavators)
        page: Page number (default: 1)
        per_page: Items per page (default: 21, max: 100)
        manufacturer: Filter by manufacturer name in Korean
        year_from: Minimum manufacturing year
        year_to: Maximum manufacturing year
        min_price: Minimum price in 만원 (10,000 KRW)
        max_price: Maximum price in 만원 (10,000 KRW)
        cache: Whether to use server-side caching (default: True)

    Returns:
        GreenEquipmentListResponse with equipment data and pagination info
    """
    try:
        # Validate category code if provided
        if category and category not in EQUIPMENT_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid category code: {category}. Valid codes are: {', '.join(EQUIPMENT_CATEGORIES.keys())}"
            )

        logger.info(f"Fetching equipment - category: {category}, page: {page}, per_page: {per_page}")

        # Fetch equipment from service
        if category:
            response = await service.get_equipment_list(
                category_code=category,
                subcategory_code=subcategory,
                page=page,
                per_page=per_page,
                manufacturer=manufacturer,
                year_from=year_from,
                year_to=year_to,
                min_price=min_price,
                max_price=max_price,
                use_cache=cache
            )
        else:
            response = await service.get_all_equipment(
                page=page,
                per_page=per_page,
                use_cache=cache
            )

        if not response.success:
            logger.error(f"Failed to fetch equipment: {response.message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.message or "Failed to fetch equipment"
            )

        logger.info(f"Successfully fetched {len(response.items)} equipment items (total: {response.count})")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching equipment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get(
    "/equipment/{equipment_id}",
    response_model=GreenEquipmentDetailsResponse,
    summary="Get equipment details",
    description="Get detailed information for a specific equipment by ID",
    responses={
        200: {
            "description": "Successful response with equipment details",
            "model": GreenEquipmentDetailsResponse
        },
        404: {
            "description": "Equipment not found",
            "model": GreenEquipmentError
        },
        500: {
            "description": "Internal server error",
            "model": GreenEquipmentError
        }
    }
)
async def get_equipment_details(
    equipment_id: str,
    category: str = Query(None, description="Category code (optional, helps with parsing)"),
    cache: bool = Query(True, description="Whether to use caching"),
    service: GreenEquipmentService = Depends(get_equipment_service)
) -> GreenEquipmentDetailsResponse:
    """
    Get detailed information for a specific equipment

    Args:
        equipment_id: The equipment ID (pid) from the website
        category: Category code (optional, helps with parsing)
        cache: Whether to use server-side caching (default: True)

    Returns:
        GreenEquipmentDetailsResponse with full equipment details including:
        - Model name and specifications
        - Price in KRW
        - Condition grade
        - Seller contact information
        - Images
        - Description
    """
    try:
        logger.info(f"Fetching equipment details for: {equipment_id}")

        # Fetch equipment details from service
        response = await service.get_equipment_details(
            equipment_id=equipment_id,
            category_code=category or "",
            use_cache=cache
        )

        if not response.success:
            logger.error(f"Failed to fetch equipment details: {response.message}")

            # Check if it's a not found error
            if "not found" in str(response.message).lower() or "404" in str(response.message):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Equipment with ID {equipment_id} not found"
                )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.message or "Failed to fetch equipment details"
            )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Equipment with ID {equipment_id} not found"
            )

        logger.info(f"Successfully fetched equipment details for {equipment_id}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching equipment details: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get(
    "/categories",
    response_model=CategoriesResponse,
    summary="Get equipment categories",
    description="Get all available equipment categories with translations",
    responses={
        200: {
            "description": "Successful response with categories",
            "model": CategoriesResponse
        }
    }
)
async def get_categories(
    service: GreenEquipmentService = Depends(get_equipment_service)
) -> CategoriesResponse:
    """
    Get all available equipment categories

    Returns:
        CategoriesResponse with list of categories including:
        - Category code
        - Korean name
        - English name
        - Russian name
    """
    try:
        logger.info("Fetching equipment categories")
        response = await service.get_all_categories()

        if not response.success:
            logger.error(f"Failed to fetch categories: {response.message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.message or "Failed to fetch categories"
            )

        logger.info(f"Successfully fetched {len(response.categories)} categories")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching categories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post(
    "/equipment/cache/clear",
    summary="Clear equipment cache",
    description="Clear all cached equipment data",
    responses={
        200: {
            "description": "Cache cleared successfully",
        }
    }
)
async def clear_equipment_cache(
    service: GreenEquipmentService = Depends(get_equipment_service)
):
    """
    Clear all cached equipment data

    This endpoint can be used to force fresh data fetching
    """
    try:
        logger.info("Clearing Green equipment cache")
        service.clear_cache()
        return {"success": True, "message": "Equipment cache cleared successfully"}

    except Exception as e:
        logger.error(f"Error clearing equipment cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )
