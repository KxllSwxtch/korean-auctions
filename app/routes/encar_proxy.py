"""
Transparent Encar API proxy routes.

These endpoints forward requests directly to api.encar.com through the
proxy pool (Oxylabs / BestProxy) and return the raw JSON response. They
exist so that the Next.js frontend can call the korean-auctions backend
instead of maintaining a separate encar-proxy service.

Endpoints:
    GET /api/catalog  — proxies to api.encar.com/search/car/list/premium
    GET /api/nav      — proxies to api.encar.com/search/car/list/general
"""

import aiohttp

from fastapi import APIRouter, Query
from fastapi.responses import ORJSONResponse
from starlette.responses import Response

from app.core.proxy_config import get_proxy_pool
from app.core.logging import get_logger

logger = get_logger("encar_proxy")

router = APIRouter()

# Dedicated proxy pool for Encar API requests. Always enabled regardless
# of the USE_PROXY env gate used by other services.
_pool = get_proxy_pool()

_ENCAR_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
    "origin": "http://www.encar.com",
    "referer": "http://www.encar.com/",
}

ENCAR_API = "http://api.encar.com"


async def _proxy_get(url: str) -> tuple[str, int]:
    """Issue a GET through the rotating proxy pool and return (body, status)."""
    entry, proxy_url = _pool.advance()
    logger.debug(f"Using proxy {entry.name}")

    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(ssl=False)

    async with aiohttp.ClientSession(
        connector=connector, timeout=timeout
    ) as session:
        async with session.get(
            url, headers=_ENCAR_HEADERS, proxy=proxy_url
        ) as resp:
            body = await resp.text()
            return body, resp.status


@router.get("/api/catalog")
async def proxy_catalog(
    q: str = Query(
        "(And.Hidden.N._.CarType.A._.SellType.일반.)",
        description="Encar search query",
    ),
    sr: str = Query(
        "|ModifiedDate|0|21",
        description="Sort / pagination",
    ),
    count: bool = Query(True, description="Include total count"),
):
    """Transparently proxy a catalog request to api.encar.com."""
    count_str = "true" if count else "false"
    url = f"{ENCAR_API}/search/car/list/premium?q={q}&sr={sr}&count={count_str}"
    logger.info(f"Proxy catalog → {url[:120]}…")

    try:
        body, status = await _proxy_get(url)
        return Response(content=body, status_code=status, media_type="application/json")
    except Exception as exc:
        logger.error(f"Proxy catalog error: {exc}")
        return ORJSONResponse(
            {"error": "upstream_error", "detail": str(exc)},
            status_code=502,
        )


@router.get("/api/nav")
async def proxy_nav(
    q: str = Query(..., description="Encar nav query"),
    inav: str = Query("|Metadata|Sort", description="iNav facet spec"),
    count: bool = Query(True, description="Include total count"),
):
    """Transparently proxy a nav/facet request to api.encar.com."""
    count_str = "true" if count else "false"
    url = f"{ENCAR_API}/search/car/list/general?q={q}&inav={inav}&count={count_str}"
    logger.info(f"Proxy nav → {url[:120]}…")

    try:
        body, status = await _proxy_get(url)
        return Response(content=body, status_code=status, media_type="application/json")
    except Exception as exc:
        logger.error(f"Proxy nav error: {exc}")
        return ORJSONResponse(
            {"error": "upstream_error", "detail": str(exc)},
            status_code=502,
        )
