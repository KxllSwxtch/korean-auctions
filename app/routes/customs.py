"""
FastAPI routes for the Russian customs calculator (calcus.ru) proxy.

Replaces the front-end's previous direct call through ``corsproxy.io`` which
was returning 403 once the public proxy's free quota was exhausted.
"""

from fastapi import APIRouter, Depends, status

from app.core.logging import get_logger
from app.models.customs import (
    CustomsCalculationRequest,
    CustomsCalculationResponse,
)
from app.services.customs_service import CustomsService, customs_service

logger = get_logger("customs_routes")

router = APIRouter(
    responses={500: {"description": "Internal server error"}},
)


def get_customs_service() -> CustomsService:
    return customs_service


@router.post(
    "/calculate",
    response_model=CustomsCalculationResponse,
    summary="Calculate Russian customs costs (calcus.ru proxy)",
    description=(
        "Server-to-server proxy for https://calcus.ru/calculate/Customs. "
        "Used by the Next.js car detail page to estimate the turnkey price "
        "in Vladivostok when the user has supplied an HP value."
    ),
    responses={
        200: {
            "description": "Customs breakdown (or success=false with reason)",
            "model": CustomsCalculationResponse,
        }
    },
)
async def calculate(
    payload: CustomsCalculationRequest,
    service: CustomsService = Depends(get_customs_service),
) -> CustomsCalculationResponse:
    return await service.calculate(payload)


@router.post(
    "/cache/clear",
    summary="Clear customs calculator cache",
    status_code=status.HTTP_200_OK,
)
async def clear_cache(
    service: CustomsService = Depends(get_customs_service),
):
    service.clear_cache()
    return {"success": True, "message": "Customs cache cleared"}
