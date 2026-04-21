"""
Service that proxies the Russian customs calculator at calcus.ru.

Why a backend proxy: the browser cannot reach calcus.ru directly because of
CORS, and the previous workaround (``corsproxy.io``) returns 403 once its free
quota is exhausted for a given source IP. Calling calcus.ru server-to-server
removes both problems and lets us add caching + request coalescing on top.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

from app.core.http_client import AsyncHttpClient
from app.core.logging import get_logger
from app.core.single_flight import SingleFlight
from app.models.customs import (
    CustomsCalculationData,
    CustomsCalculationRequest,
    CustomsCalculationResponse,
)

logger = get_logger("customs_service")


class CustomsCache:
    """In-memory TTL cache (mirrors PanAutoCache for consistency)."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._store: Dict[str, Tuple[CustomsCalculationResponse, datetime]] = {}
        self._ttl = timedelta(seconds=ttl_seconds)

    def get(self, key: str) -> Optional[CustomsCalculationResponse]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, ts = entry
        if datetime.now() - ts >= self._ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: CustomsCalculationResponse) -> None:
        self._store[key] = (value, datetime.now())

    def clear(self) -> None:
        self._store.clear()


def _parse_ru_number(raw: Any) -> float:
    """Parse calcus.ru's formatted numbers (e.g. ``"8 900 160,00"``) to float.

    Calcus returns every numeric field as a string with non-breaking-space
    thousand separators and a comma decimal mark. Falls back to 0.0 for
    anything unparseable so the caller can keep the response success-y.
    """
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    text = (
        str(raw)
        .replace("\u00a0", "")  # NBSP
        .replace("\xa0", "")
        .replace(" ", "")
        .replace(",", ".")
    )
    try:
        return float(text)
    except ValueError:
        return 0.0


def _parse_total2(raw: Any) -> int:
    """Integer RUB form of total2 — used directly by the frontend turnkey calc."""
    return int(_parse_ru_number(raw))


class CustomsService:
    """Async proxy + cache + single-flight wrapper around calcus.ru."""

    CALCUS_URL = "https://calcus.ru/calculate/Customs"

    def __init__(self) -> None:
        self._http = AsyncHttpClient(timeout=15)
        self._cache = CustomsCache(ttl_seconds=300)
        self._flight = SingleFlight()
        self._headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://calcus.ru",
            "Referer": "https://calcus.ru/rastamozhka",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "X-Requested-With": "XMLHttpRequest",
        }

    @staticmethod
    def _cache_key(req: CustomsCalculationRequest) -> str:
        return (
            "customs:"
            f"o={req.owner}|a={req.age}|e={req.engine}"
            f"|p={req.power_hp}|v={req.displacement_cc}|pr={req.price_krw}"
        )

    @staticmethod
    def _build_body(req: CustomsCalculationRequest) -> str:
        return urlencode(
            {
                "owner": req.owner,
                "age": req.age,
                "engine": req.engine,
                "power": str(req.power_hp),
                "power_unit": "1",  # 1 = л.с. (HP)
                "value": str(req.displacement_cc),
                "price": str(req.price_krw),
                "curr": "KRW",
            }
        )

    async def calculate(
        self, req: CustomsCalculationRequest
    ) -> CustomsCalculationResponse:
        """Return a customs breakdown — from cache if fresh, otherwise calcus.ru."""
        key = self._cache_key(req)

        cached = self._cache.get(key)
        if cached is not None:
            logger.debug(f"Customs cache hit for key={key}")
            return cached

        try:
            response = await self._flight.do(key, lambda: self._fetch(req))
        except Exception as exc:  # network errors propagated by single-flight
            logger.error(f"Customs calculation failed for key={key}: {exc}")
            return CustomsCalculationResponse(
                success=False,
                data=None,
                message="Сервис расчёта временно недоступен",
            )

        if response.success:
            self._cache.set(key, response)
        return response

    async def _fetch(
        self, req: CustomsCalculationRequest
    ) -> CustomsCalculationResponse:
        body = self._build_body(req)
        logger.info(
            "Calling calcus.ru: age=%s engine=%s hp=%s cc=%s price=%s",
            req.age, req.engine, req.power_hp, req.displacement_cc, req.price_krw,
        )

        response = await self._http.post(
            self.CALCUS_URL, data=body, headers=self._headers
        )

        if response.status_code != 200:
            msg = f"calcus.ru returned status {response.status_code}"
            logger.warning(msg)
            return CustomsCalculationResponse(
                success=False, data=None, message=msg
            )

        try:
            payload = response.json()
        except Exception as exc:
            logger.error(f"Failed to parse calcus.ru response as JSON: {exc}")
            return CustomsCalculationResponse(
                success=False,
                data=None,
                message="Не удалось разобрать ответ калькулятора",
            )

        return self._build_response(payload)

    @staticmethod
    def _build_response(payload: Dict[str, Any]) -> CustomsCalculationResponse:
        total2_raw = payload.get("total2")
        try:
            data = CustomsCalculationData(
                tax=_parse_ru_number(payload.get("tax")),
                sbor=_parse_ru_number(payload.get("sbor")),
                util=_parse_ru_number(payload.get("util")),
                total=_parse_ru_number(payload.get("total")),
                total2=str(total2_raw) if total2_raw is not None else "",
                total_car_cost_rub=_parse_total2(total2_raw),
            )
        except (TypeError, ValueError) as exc:
            logger.error(f"calcus.ru payload had unexpected shape: {exc}; raw={payload!r}")
            return CustomsCalculationResponse(
                success=False,
                data=None,
                message="Калькулятор вернул неожиданный ответ",
            )
        if total2_raw is None or data.total_car_cost_rub == 0:
            logger.warning(f"calcus.ru returned zero/missing total2; raw={payload!r}")
            return CustomsCalculationResponse(
                success=False,
                data=None,
                message="Калькулятор вернул неполный ответ",
            )
        return CustomsCalculationResponse(success=True, data=data, message=None)

    def clear_cache(self) -> None:
        self._cache.clear()
        logger.info("Customs service cache cleared")


# Singleton — matches pan_auto_service / exchange_rate_service pattern
customs_service = CustomsService()
