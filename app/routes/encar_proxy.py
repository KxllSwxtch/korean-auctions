"""
Transparent Encar API proxy routes.

These endpoints forward requests to api.encar.com and return the raw JSON
response. They exist so that the Next.js frontend can call the korean-auctions
backend instead of maintaining a separate encar-proxy service — and, because
Encar's edge refuses Vercel's addresses as well, so the detail page can reach
the readside API through this backend too.

Egress policy (adaptive, since 2026-08-29): api.encar.com sits behind
CloudFront, which answers Render/AWS egress addresses with HTTP 403 "Request
blocked". The same URLs succeed from the Korean residential proxy pool
(AUCTION_PROXY_*). Every request therefore goes DIRECT first — free, and the
verified-good path whenever the edge lets us through — and, when the edge
refuses it, is retried once through the pool. A refusal trips a per-process
EgressBreaker so the following requests skip straight to the proxy for one
cooldown window (ENCAR_DIRECT_BLOCK_COOLDOWN_SECONDS, default 600 s), after
which the direct leg is probed again. USE_PROXY=true still makes the pool the
primary leg for every AsyncHttpClient consumer; ENCAR_PROXY_FAILOVER=false
disables the fallback, and a block then surfaces as 503 upstream_blocked.
Proxy-REQUIRED providers (Glovis, HappyCar) do not share this policy and
remain fail-closed.

Endpoints:
    GET /api/catalog                            — search/car/list/premium (cached 15 s)
    GET /api/nav                                — search/car/list/general (cached 5 min)
    GET /api/readside/vehicle/{id}              — v1/readside/vehicle/{id}
    GET /api/readside/inspection/vehicle/{id}   — v1/readside/inspection/vehicle/{id}
    GET /api/readside/record/vehicle/{id}/open  — v1/readside/record/vehicle/{id}/open?vehicleNo=
Readside responses are never cached: the frontend fetches them per page view.
"""

from __future__ import annotations

import asyncio
import re
import threading
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import quote

import aiohttp
from fastapi import APIRouter, Query
from fastapi.responses import ORJSONResponse
from starlette.responses import Response

from app.core.async_cache import SwrCache
from app.core.egress_breaker import Egress, EgressBreaker, looks_like_edge_block
from app.core.http_client import AsyncHttpClient, AsyncHttpResponse
from app.core.logging import get_logger
from app.core.proxy_config import ProxyConfigurationError
from app.core.startup_checks import encar_failover_enabled, render_git_commit
from app.models.diagnostics import CacheStats, EncarEgressDiagnostics

logger = get_logger("encar_proxy")

router = APIRouter()

ENCAR_API = "https://api.encar.com"
REQUEST_TIMEOUT_SECONDS = 30

_ENCAR_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
    "origin": "https://www.encar.com",
    "referer": "https://www.encar.com/",
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
    "upstream_blocked": 503,
    "invalid_vehicle_id": 400,
    "invalid_vehicle_no": 400,
}
_ERROR_MESSAGE = {
    "proxy_unavailable": "Encar egress proxy is not configured",
    "proxy_error": "Encar egress proxy rejected the request",
    "upstream_timeout": "Encar did not respond in time",
    "upstream_unavailable": "Encar is unreachable",
    "upstream_invalid_response": "Encar returned an unreadable response",
    "upstream_error": "Encar returned an error",
    "upstream_blocked": "Encar refused this server's egress address; retry shortly",
    "invalid_vehicle_id": "vehicle id must be 1-12 digits",
    "invalid_vehicle_no": "vehicleNo must be a Korean licence plate",
}
_ERROR_RETRYABLE = {
    "proxy_unavailable": False,
    "proxy_error": True,
    "upstream_timeout": True,
    "upstream_unavailable": True,
    "upstream_invalid_response": True,
    "upstream_error": True,
    "upstream_blocked": True,
    "invalid_vehicle_id": False,
    "invalid_vehicle_no": False,
}

# Readside path parameters are validated with fullmatch BEFORE any network
# call, so these routes are an allowlist of three fixed upstream paths rather
# than a relay. ASCII digits only: Unicode digits would be forwarded as an
# unexpected percent-encoded segment.
_VEHICLE_ID_RE = re.compile(r"\d{1,12}", re.ASCII)
_VEHICLE_NO_RE = re.compile(r"[0-9A-Za-z가-힣 ]{1,16}")


@dataclass(frozen=True)
class _UpstreamOk:
    """A 2xx from Encar — the only thing the caches ever store."""

    status: int
    text: str
    egress: str


class _ForwardError(Exception):
    """One of the public error codes above. str() is the code alone, because
    SwrCache logs loader exceptions verbatim and aiohttp messages can embed
    the proxy URL."""

    def __init__(
        self,
        code: str,
        *,
        upstream_status: int | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.upstream_status = upstream_status
        self.retry_after = retry_after


class _UpstreamPassthrough(Exception):
    """A non-block 4xx from Encar (404 for a removed car) relayed verbatim."""

    def __init__(self, status: int, text: str, content_type: str) -> None:
        super().__init__(f"upstream {status}")
        self.status = status
        self.text = text
        self.content_type = content_type


# Per-worker read caches. Constructed at import on purpose: SwrCache touches
# neither the environment nor an event loop until the first get(), so this is
# --preload safe. Nav facets change slowly and are expensive for Encar;
# catalog pages change constantly but the same first page is requested by
# every visitor, so a short TTL still coalesces the stampede. The stale window
# is what keeps the filter sidebar populated while the edge is refusing us.
_NAV_CACHE: SwrCache[_UpstreamOk] = SwrCache(
    ttl=300, stale_ttl=3600, maxsize=96, jitter=30, name="encar-nav"
)
_CATALOG_CACHE: SwrCache[_UpstreamOk] = SwrCache(
    ttl=15, stale_ttl=120, maxsize=256, jitter=3, name="encar-catalog"
)

# One pooled client and one breaker per worker process. Built lazily so
# module import never reads proxy environment: start.sh runs `gunicorn
# --preload`, which imports main in the master before forking, and an aiohttp
# session must be bound to the worker's own event loop. AsyncHttpClient
# satisfies both — it defers session creation to the first awaited request.
_client: AsyncHttpClient | None = None
_client_lock = threading.Lock()
_breaker: EgressBreaker | None = None
_breaker_lock = threading.Lock()


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
                    proxy_failover=encar_failover_enabled(),
                )
                logger.info(
                    f"Encar proxy client ready (egress={_client.egress_mode}, "
                    f"failover_armed={_client.failover_armed}, "
                    f"failover_pool_size={_client.failover_pool_size})"
                )
    return _client


def get_encar_breaker() -> EgressBreaker:
    """Return the process-wide direct-egress breaker."""
    global _breaker
    if _breaker is None:
        with _breaker_lock:
            if _breaker is None:
                _breaker = EgressBreaker.from_env()
    return _breaker


def encar_diagnostics_snapshot() -> EncarEgressDiagnostics:
    """Read-only egress state for /api/v1/diagnostics/encar. No probing,
    no pool names, no values — only modes, counters and timestamps."""
    client, breaker = get_encar_proxy_client(), get_encar_breaker()
    state = breaker.snapshot()
    return EncarEgressDiagnostics(
        commit=render_git_commit(),
        egress_mode=client.egress_mode,
        failover_enabled=encar_failover_enabled(),
        failover_armed=client.failover_armed,
        proxy_pool_size=client.failover_pool_size,
        breaker_open=state.open,
        breaker_seconds_remaining=state.seconds_remaining,
        breaker_trips=state.trips,
        cooldown_seconds=state.cooldown_seconds,
        last_direct_status=state.last_direct_status,
        last_proxy_status=state.last_proxy_status,
        last_block_at=state.last_block_at,
        caches={
            "nav": CacheStats(**_NAV_CACHE.stats()),
            "catalog": CacheStats(**_CATALOG_CACHE.stats()),
        },
    )


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


def _header(headers: Mapping[str, str], name: str) -> str | None:
    """Case-insensitive header lookup over the plain dict AsyncHttpResponse keeps."""
    wanted = name.lower()
    return next((value for key, value in headers.items() if key.lower() == wanted), None)


def _error(
    code: str,
    *,
    upstream_status: int | None = None,
    retry_after: int | None = None,
) -> ORJSONResponse:
    """Build the public error body. Never echoes exception text."""
    detail: dict[str, object] = {
        "code": code,
        "message": _ERROR_MESSAGE[code],
        "retryable": _ERROR_RETRYABLE[code],
    }
    if upstream_status is not None:
        detail["upstream_status"] = upstream_status
    headers = {"Cache-Control": "no-store"}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return ORJSONResponse(
        {"error": code, "detail": detail},
        status_code=_ERROR_STATUS[code],
        headers=headers,
    )


async def _leg(
    client: AsyncHttpClient,
    breaker: EgressBreaker,
    url: str,
    egress: Egress,
    operation: str,
) -> AsyncHttpResponse:
    """One request over one egress leg. Transport failures become _ForwardError.

    Exception text never leaves this function: every message is the class
    name, and the raised error carries only the public code.
    """
    try:
        response = await client.get(url, headers=_ENCAR_HEADERS, egress=egress)
    except ProxyConfigurationError:
        logger.error(
            f"{operation}: auction proxy required but unconfigured; set "
            f"AUCTION_PROXY_HOST, AUCTION_PROXY_USERNAME, AUCTION_PROXY_PASSWORD"
        )
        raise _ForwardError("proxy_unavailable") from None
    except asyncio.TimeoutError:
        # aiohttp.ServerTimeoutError subclasses asyncio.TimeoutError.
        logger.warning(
            f"{operation}: upstream timeout after {REQUEST_TIMEOUT_SECONDS}s "
            f"(egress={egress})"
        )
        raise _ForwardError("upstream_timeout") from None
    except (aiohttp.ClientProxyConnectionError, aiohttp.ClientHttpProxyError) as exc:
        logger.error(f"{operation}: proxy transport failure ({_safe_reason(exc)})")
        raise _ForwardError("proxy_error") from None
    except aiohttp.ClientPayloadError as exc:
        logger.error(f"{operation}: malformed upstream payload ({_safe_reason(exc)})")
        raise _ForwardError("upstream_invalid_response") from None
    except aiohttp.ClientError as exc:
        # ClientConnectorError / ServerDisconnectedError / InvalidURL / etc.
        logger.error(
            f"{operation}: upstream transport failure ({_safe_reason(exc)}, "
            f"egress={egress})"
        )
        raise _ForwardError("upstream_unavailable") from None

    breaker.record(egress, response.status_code)
    return response


async def _fetch(url: str, operation: str) -> _UpstreamOk:
    """Try each egress leg in turn; return the 2xx body or raise.

    Raises _UpstreamPassthrough for Encar's own 4xx (relayed verbatim) and
    _ForwardError for everything the public contract maps to a status of
    ours — including upstream_blocked when every leg was refused.
    """
    client, breaker = get_encar_proxy_client(), get_encar_breaker()
    legs: tuple[Egress, ...]
    if client.egress_mode == "proxy":
        legs = ("proxy",)  # USE_PROXY=true: the pool is already the primary leg
    else:
        legs = breaker.legs(armed=client.failover_armed)

    last_block: int | None = None
    for egress in legs:
        response = await _leg(client, breaker, url, egress, operation)
        if looks_like_edge_block(response.status_code, response.headers, response.text):
            last_block = response.status_code
            if egress == "direct" and breaker.trip() == "opened":
                logger.warning(
                    f"{operation}: direct egress to api.encar.com blocked "
                    f"(HTTP {last_block}); routing via proxy for "
                    f"{breaker.cooldown_seconds}s "
                    f"(failover_armed={client.failover_armed})"
                )
            continue
        if egress == "direct" and breaker.reset():
            logger.info(
                f"{operation}: direct egress to api.encar.com recovered "
                f"(HTTP {response.status_code})"
            )
        if response.status_code >= 500:
            logger.error(
                f"{operation}: upstream returned {response.status_code} "
                f"({len(response.text)} bytes, egress={egress})"
            )
            raise _ForwardError("upstream_error", upstream_status=response.status_code)
        if not 200 <= response.status_code < 300:
            raise _UpstreamPassthrough(
                response.status_code,
                response.text,
                _header(response.headers, "content-type") or "application/json",
            )
        return _UpstreamOk(response.status_code, response.text, egress)

    logger.error(
        f"{operation}: every egress leg refused by Encar's edge "
        f"(last HTTP {last_block}, legs={legs}, failover_armed={client.failover_armed})"
    )
    raise _ForwardError(
        "upstream_blocked",
        upstream_status=last_block,
        retry_after=int(breaker.seconds_remaining()) or 60,
    )


async def _forward(
    url: str,
    operation: str,
    *,
    cache: SwrCache[_UpstreamOk] | None = None,
) -> Response:
    """Fetch `url` from Encar, through `cache` when given, as a public Response.

    Non-2xx is never cached: the loader raises, and SwrCache caches only
    returned values.
    """
    loaded = False

    async def loader() -> _UpstreamOk:
        nonlocal loaded
        loaded = True
        return await _fetch(url, operation)

    try:
        if cache is not None:
            outcome = await cache.get(url, loader)
        else:
            outcome = await loader()
    except _UpstreamPassthrough as passthrough:
        return Response(
            content=passthrough.text,
            status_code=passthrough.status,
            media_type=passthrough.content_type,
        )
    except _ForwardError as failure:
        return _error(
            failure.code,
            upstream_status=failure.upstream_status,
            retry_after=failure.retry_after,
        )

    return Response(
        content=outcome.text,
        status_code=outcome.status,
        media_type="application/json",
        headers={"X-Encar-Source": outcome.egress if loaded else "cache"},
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
    return await _forward(url, "catalog", cache=_CATALOG_CACHE)


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
    return await _forward(url, "nav", cache=_NAV_CACHE)


@router.get("/api/readside/vehicle/{vehicle_id}")
async def proxy_readside_vehicle(vehicle_id: str) -> Response:
    """Vehicle detail for the frontend's car page (never cached)."""
    if not _VEHICLE_ID_RE.fullmatch(vehicle_id):
        return _error("invalid_vehicle_id")
    logger.info(f"Proxy readside vehicle → {vehicle_id}")
    return await _forward(
        f"{ENCAR_API}/v1/readside/vehicle/{vehicle_id}", "readside-vehicle"
    )


@router.get("/api/readside/inspection/vehicle/{vehicle_id}")
async def proxy_readside_inspection(vehicle_id: str) -> Response:
    """Inspection report for the frontend's car page (never cached)."""
    if not _VEHICLE_ID_RE.fullmatch(vehicle_id):
        return _error("invalid_vehicle_id")
    logger.info(f"Proxy readside inspection → {vehicle_id}")
    return await _forward(
        f"{ENCAR_API}/v1/readside/inspection/vehicle/{vehicle_id}",
        "readside-inspection",
    )


@router.get("/api/readside/record/vehicle/{vehicle_id}/open")
async def proxy_readside_record(
    vehicle_id: str,
    vehicle_no: str = Query(..., alias="vehicleNo", description="Licence plate"),
) -> Response:
    """Accident/insurance record for the frontend's car page (never cached)."""
    if not _VEHICLE_ID_RE.fullmatch(vehicle_id):
        return _error("invalid_vehicle_id")
    if not _VEHICLE_NO_RE.fullmatch(vehicle_no):
        return _error("invalid_vehicle_no")
    logger.info(f"Proxy readside record → {vehicle_id}")
    url = (
        f"{ENCAR_API}/v1/readside/record/vehicle/{vehicle_id}/open"
        f"?vehicleNo={quote(vehicle_no, safe='')}"
    )
    return await _forward(url, "readside-record")
