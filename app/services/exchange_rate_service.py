import time
from datetime import datetime, timezone

import requests
from loguru import logger

from app.core.config import settings


NAVER_RATE_URL = (
    "https://m.search.naver.com/p/csearch/content/qapirender.nhn"
    "?key=calculator&pkid=141"
    "&q=%ED%99%98%EC%9C%A8&where=m"
    "&u1=keb&u6=standardUnit&u7=0&u3={currency}&u4=KRW&u8=down&u2=1"
)

HEADERS = {
    "Referer": "https://m.search.naver.com/",
    "User-Agent": settings.user_agent,
    "Accept": "*/*",
}

RATE_OFFSET = 10  # Points to subtract from each rate


class ExchangeRateService:
    """Fetches and caches live exchange rates from Naver."""

    def __init__(self) -> None:
        self._cache: dict[str, object] = {}
        self._cache_time: float = 0
        self._cache_ttl: int = settings.cache_ttl_exchange_rate

    def _fetch_single_rate(self, currency: str) -> float:
        """Fetch a single currency rate from Naver and subtract offset."""
        url = NAVER_RATE_URL.format(currency=currency)
        resp = requests.get(url, headers=HEADERS, timeout=settings.request_timeout)
        resp.raise_for_status()
        data = resp.json()
        raw_value = data["country"][1]["value"]
        rate = float(raw_value.replace(",", ""))
        adjusted = rate - RATE_OFFSET
        logger.info(f"Fetched {currency}/KRW rate: {rate} → adjusted: {adjusted}")
        return adjusted

    def get_rates(self, bypass_cache: bool = False) -> dict:
        """Get both USD/KRW and EUR/KRW rates, with in-memory caching."""
        now = time.time()
        if not bypass_cache and self._cache and (now - self._cache_time) < self._cache_ttl:
            logger.debug("Returning cached exchange rates")
            return self._cache

        try:
            usd_krw = self._fetch_single_rate("USD")
            eur_krw = self._fetch_single_rate("EUR")
            fetched_at = datetime.now(timezone.utc).isoformat()

            self._cache = {
                "usd_krw": usd_krw,
                "eur_krw": eur_krw,
                "fetched_at": fetched_at,
            }
            self._cache_time = now
            logger.info(f"Exchange rates updated: USD/KRW={usd_krw}, EUR/KRW={eur_krw}")
            return self._cache

        except Exception as e:
            logger.error(f"Failed to fetch exchange rates: {e}")
            if self._cache:
                logger.warning("Returning stale cached rates after fetch failure")
                return self._cache
            raise


# Singleton instance
exchange_rate_service = ExchangeRateService()
