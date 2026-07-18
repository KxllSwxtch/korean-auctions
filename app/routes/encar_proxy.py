"""
Transparent Encar API proxy routes.

These endpoints forward requests to api.encar.com and return the raw JSON
response. They exist so that the Next.js frontend can call the korean-auctions
backend instead of maintaining a separate encar-proxy service.

Egress policy: Encar's public search API is proxy-OPTIONAL. Requests go through
the shared auction proxy pool when USE_PROXY=true and AUCTION_PROXY_* are
provisioned, and go direct otherwise. Direct egress is a supported production
mode, not a fallback hack — api.encar.com answers non-Korean addresses, which
is why /api/v1/encar/catalog (app/services/encar_service.py, same upstream URL)
kept working while these routes returned 502. Proxy-REQUIRED providers (Glovis,
HappyCar) deliberately do not share this policy and remain fail-closed.

Endpoints:
    GET /api/catalog  — proxies to api.encar.com/search/car/list/premium
    GET /api/nav      — proxies to api.encar.com/search/car/list/general
"""

from __future__ import annotations

import asyncio
import threading

import aiohttp
from fastapi import APIRouter, Query
from fastapi.responses import ORJSONResponse
from starlette.responses import Response

from app.core.http_client import AsyncHttpClient, AsyncHttpResponse
from app.core.logging import get_logger
from app.core.proxy_config import ProxyConfigurationError

logger = get_logger("encar_proxy")

router = APIRouter()

ENCAR_API = "http://api.encar.com"
REQUEST_TIMEOUT_SECONDS = 30

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

# Stable public error contract. Mirrors app/routes/glovis.py:34-40 so the
# frontend sees one error shape across every provider.
_ERROR_STATUS = {
    "proxy_unavailable": 503,
    "proxy_error": 502,
    "upstream_timeout": 504,
    "upstream_unavailable": 502,
    "upstream_invalid_response": 502,
    "upstream_error": 502,
}
_ERROR_MESSAGE = {
    "proxy_unavailable": "Encar egress proxy is not configured",
    "proxy_error": "Encar egress proxy rejected the request",
    "upstream_timeout": "Encar did not respond in time",
    "upstream_unavailable": "Encar is unreachable",
    "upstream_invalid_response": "Encar returned an unreadable response",
    "upstream_error": "Encar returned an error",
}
_ERROR_RETRYABLE = {
    "proxy_unavailable": False,
    "proxy_error": True,
    "upstream_timeout": True,
    "upstream_unavailable": True,
    "upstream_invalid_response": True,
    "upstream_error": True,
}

# One pooled client per worker process. Built lazily so module import never
# reads proxy environment: start.sh runs `gunicorn --preload`, which imports
# main in the master before forking, and an aiohttp session must be bound to
# the worker's own event loop. AsyncHttpClient satisfies both — it defers
# session creation to the first awaited request.
_client: AsyncHttpClient | None = None
_client_lock = threading.Lock()


def get_encar_proxy_client() -> AsyncHttpClient:
    """Return the process-wide pooled client used for api.encar.com."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = AsyncHttpClient(
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    use_proxy=True,
                    proxy_required=False,
                )
                logger.info(
                    f"Encar proxy client ready (egress={_client.egress_mode})"
                )
    return _client


async def close_encar_proxy_client() -> None:
    """Close the pooled client during application shutdown."""
    global _client
    client, _client = _client, None
    if client is not None:
        await client.close()


def _safe_reason(exc: BaseException) -> str:
    """Class name only: aiohttp messages can embed the full proxy URL.

    ProxyEntry.build_url does not validate the host, so a malformed
    AUCTION_PROXY_HOST yields an aiohttp.InvalidURL whose str() contains the
    quoted proxy password. Never echo exception text into a public response.
    """
    return type(exc).__name__


def _error(code: str, *, upstream_status: int | None = None) -> ORJSONResponse:
    """Build the public error body. Never echoes exception text."""
    detail: dict[str, object] = {
        "code": code,
        "message": _ERROR_MESSAGE[code],
        "retryable": _ERROR_RETRYABLE[code],
    }
    if upstream_status is not None:
        detail["upstream_status"] = upstream_status
    return ORJSONResponse(
        {"error": code, "detail": detail},
        status_code=_ERROR_STATUS[code],
        headers={"Cache-Control": "no-store"},
    )


async def _forward(url: str, operation: str) -> Response:
    """Fetch `url` from Encar and translate each failure mode distinctly."""
    client = get_encar_proxy_client()
    try:
        response: AsyncHttpResponse = await client.get(url, headers=_ENCAR_HEADERS)
    except ProxyConfigurationError:
        logger.error(
            f"{operation}: auction proxy required but unconfigured; set "
            f"AUCTION_PROXY_HOST, AUCTION_PROXY_USERNAME, AUCTION_PROXY_PASSWORD"
        )
        return _error("proxy_unavailable")
    except asyncio.TimeoutError:
        # aiohttp.ServerTimeoutError subclasses asyncio.TimeoutError.
        logger.warning(
            f"{operation}: upstream timeout after {REQUEST_TIMEOUT_SECONDS}s "
            f"(egress={client.egress_mode})"
        )
        return _error("upstream_timeout")
    except (aiohttp.ClientProxyConnectionError, aiohttp.ClientHttpProxyError) as exc:
        logger.error(f"{operation}: proxy transport failure ({_safe_reason(exc)})")
        return _error("proxy_error")
    except aiohttp.ClientPayloadError as exc:
        logger.error(f"{operation}: malformed upstream payload ({_safe_reason(exc)})")
        return _error("upstream_invalid_response")
    except aiohttp.ClientError as exc:
        # ClientConnectorError / ServerDisconnectedError / InvalidURL / etc.
        logger.error(
            f"{operation}: upstream transport failure ({_safe_reason(exc)}, "
            f"egress={client.egress_mode})"
        )
        return _error("upstream_unavailable")

    if response.status_code >= 500:
        logger.error(
            f"{operation}: upstream returned {response.status_code} "
            f"({len(response.text)} bytes, egress={client.egress_mode})"
        )
        return _error("upstream_error", upstream_status=response.status_code)

    return Response(
        content=response.text,
        status_code=response.status_code,
        media_type="application/json",
    )


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
) -> Response:
    """Transparently proxy a catalog request to api.encar.com."""
    count_str = "true" if count else "false"
    # Hand Encar the raw query string. Encar requires unencoded Korean and pipe
    # characters; passing these through `params=` would double-encode them and
    # silently return Count: 0.
    url = f"{ENCAR_API}/search/car/list/premium?q={q}&sr={sr}&count={count_str}"
    logger.info(f"Proxy catalog → {url[:120]}…")
    return await _forward(url, "catalog")


@router.get("/api/nav")
async def proxy_nav(
    q: str = Query(..., description="Encar nav query"),
    inav: str = Query("|Metadata|Sort", description="iNav facet spec"),
    count: bool = Query(True, description="Include total count"),
) -> Response:
    """Transparently proxy a nav/facet request to api.encar.com."""
    count_str = "true" if count else "false"
    url = f"{ENCAR_API}/search/car/list/general?q={q}&inav={inav}&count={count_str}"
    logger.info(f"Proxy nav → {url[:120]}…")
    return await _forward(url, "nav")
