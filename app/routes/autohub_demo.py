"""
Autohub demo routes — deprecated after JSON API migration.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/demo")
async def demo_deprecated():
    """Demo endpoint is deprecated after JSON API migration."""
    return {
        "success": False,
        "message": "Demo endpoint is deprecated. Use POST /search instead.",
    }
