"""
Base Service for All Auction Scrapers

Provides common functionality for robust session management, authentication,
and error handling.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import time
import requests
from loguru import logger

from app.core.config import get_settings


class BaseAuctionService(ABC):
    """
    Abstract base class for auction services with built-in robustness features.

    Features:
    - Session age tracking and auto-refresh
    - Consecutive failure tracking
    - Automatic session renewal before expiry
    - Standardized authentication flow
    - Request tracking and monitoring

    Subclasses should:
    1. Implement _authenticate() method
    2. Call _refresh_session_if_needed() before requests
    3. Call _record_success() / _record_failure() after requests
    4. Override session_max_age_minutes if needed
    """

    def __init__(self, name: str):
        """
        Initialize service with session management.

        Args:
            name: Service name for logging (e.g., "Lotte Service")
        """
        self.name = name
        self.session = requests.Session()
        self.authenticated = False

        # Session tracking
        self.session_created_at = datetime.now()
        self.session_last_used = datetime.now()
        self.consecutive_failures = 0
        self.session_max_age_minutes = 25  # Refresh before typical 30min expiry

        # Statistics
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0

        # Cache
        self._cache: Dict[str, tuple] = {}  # key -> (data, timestamp)
        self._cache_hits = 0
        self._cache_misses = 0
        self._settings = get_settings()

        logger.info(f"🔧 {self.name} инициализирован с управлением сессиями")

    def _is_session_expired(self) -> bool:
        """
        Check if session has expired based on age.

        Returns:
            True if session is older than session_max_age_minutes
        """
        if not hasattr(self, 'session_created_at'):
            logger.warning(
                f"⚠️ {self.name}: session_created_at не установлен, считаю сессию истекшей"
            )
            return True

        age = datetime.now() - self.session_created_at
        max_age = timedelta(minutes=self.session_max_age_minutes)

        if age > max_age:
            logger.warning(
                f"⏰ {self.name}: Сессия устарела - возраст {age.total_seconds() / 60:.1f} мин, "
                f"максимум {self.session_max_age_minutes} мин"
            )
            return True

        return False

    def _is_session_still_valid(self) -> bool:
        """
        Lightweight session validity check before full re-authentication.

        Tries a cheap request to verify the session is still alive,
        avoiding unnecessary 3-roundtrip re-auth when session is actually valid.

        Subclasses can override this with a service-specific URL check.
        Default implementation checks if the session has cookies set.

        Returns:
            True if session appears still valid
        """
        if not self.authenticated:
            return False

        # If session has no cookies at all, it's definitely invalid
        if not self.session.cookies:
            return False

        # If we have a base_url, try a lightweight HEAD request
        base_url = getattr(self, 'base_url', None)
        if base_url:
            try:
                response = self.session.head(
                    base_url, timeout=10, allow_redirects=False
                )
                # Redirect to login page means session expired
                if response.status_code in [301, 302, 303]:
                    location = response.headers.get("Location", "").lower()
                    if "login" in location or "signin" in location:
                        logger.debug(
                            f"{self.name}: Lightweight check - redirect to login, session expired"
                        )
                        return False
                # 200 or other non-error codes mean session is likely valid
                if response.status_code < 400:
                    logger.debug(
                        f"{self.name}: Lightweight check - session still valid (HTTP {response.status_code})"
                    )
                    return True
                # 403/401 means session expired
                if response.status_code in [401, 403]:
                    return False
            except Exception as e:
                logger.debug(f"{self.name}: Lightweight check failed: {e}")
                return False

        # Fallback: if cookies exist, assume session might still be valid
        return True

    def _refresh_session_if_needed(self) -> bool:
        """
        Refresh session if needed (expired or too many failures).

        This method should be called before making any requests.

        Returns:
            True if session is valid (or successfully refreshed)
            False if session refresh failed
        """
        # Check 1: Is session expired by age?
        if self._is_session_expired():
            # Before full re-auth, try lightweight validation
            if self._is_session_still_valid():
                logger.info(
                    f"{self.name}: Сессия истекла по времени, но ещё работает - продлеваем"
                )
                self.session_created_at = datetime.now()
                return True

            logger.info(f"🔄 {self.name}: Обновляю сессию (истекло время)...")
            if self._authenticate():
                self.session_created_at = datetime.now()
                self.consecutive_failures = 0
                logger.success(f"✅ {self.name}: Сессия успешно обновлена")
                return True
            else:
                self.consecutive_failures += 1
                logger.error(
                    f"❌ {self.name}: Не удалось обновить сессию "
                    f"(попытка #{self.consecutive_failures})"
                )
                return False

        # Check 2: Too many consecutive failures?
        if self.consecutive_failures >= 3:
            logger.warning(
                f"⚠️ {self.name}: Обнаружено {self.consecutive_failures} "
                f"последовательных ошибок, принудительно обновляю сессию..."
            )
            if self._authenticate():
                self.session_created_at = datetime.now()
                self.consecutive_failures = 0
                logger.success(f"✅ {self.name}: Сессия успешно обновлена после ошибок")
                return True
            else:
                self.consecutive_failures += 1
                logger.error(f"❌ {self.name}: Не удалось обновить сессию после ошибок")
                return False

        # Session is valid
        return True

    def _record_success(self) -> None:
        """
        Record successful request.

        Resets consecutive failures counter and updates session timestamp.
        Call this after every successful operation.
        """
        self.consecutive_failures = 0
        self.session_last_used = datetime.now()
        self.successful_requests += 1
        self.total_requests += 1

        logger.debug(
            f"✅ {self.name}: Запрос успешен "
            f"(всего: {self.total_requests}, успешных: {self.successful_requests})"
        )

    def _record_failure(self, error: Optional[Exception] = None) -> None:
        """
        Record failed request.

        Increments consecutive failures counter for session health monitoring.
        Call this after every failed operation.

        Args:
            error: Optional exception that caused the failure
        """
        self.consecutive_failures += 1
        self.failed_requests += 1
        self.total_requests += 1

        error_msg = str(error) if error else "Unknown error"
        logger.warning(
            f"⚠️ {self.name}: Запрос не удался - {error_msg} "
            f"(последовательных ошибок: {self.consecutive_failures}, "
            f"всего ошибок: {self.failed_requests}/{self.total_requests})"
        )

    def _get_session_stats(self) -> dict:
        """
        Get session statistics.

        Returns:
            Dict with session age, request counts, success rate, etc.
        """
        age = datetime.now() - self.session_created_at
        time_since_last_use = datetime.now() - self.session_last_used

        success_rate = (
            (self.successful_requests / self.total_requests * 100)
            if self.total_requests > 0 else 0
        )

        return {
            "authenticated": self.authenticated,
            "session_age_minutes": age.total_seconds() / 60,
            "time_since_last_use_minutes": time_since_last_use.total_seconds() / 60,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "consecutive_failures": self.consecutive_failures,
            "success_rate_percent": round(success_rate, 2),
        }

    def _should_alert(self) -> bool:
        """
        Check if service health requires alerting.

        Returns:
            True if consecutive failures >= 5 or success rate < 50%
        """
        if self.consecutive_failures >= 5:
            logger.critical(
                f"🚨 {self.name}: ALERT - 5+ последовательных ошибок! "
                f"Возможны проблемы с аутентификацией или изменение структуры сайта."
            )
            return True

        if self.total_requests >= 10:
            success_rate = self.successful_requests / self.total_requests
            if success_rate < 0.5:
                logger.critical(
                    f"🚨 {self.name}: ALERT - Success rate < 50% "
                    f"({self.successful_requests}/{self.total_requests})"
                )
                return True

        return False

    @abstractmethod
    def _authenticate(self) -> bool:
        """
        Authenticate with auction site.

        Must be implemented by subclasses.

        Should:
        1. Set up session cookies
        2. Perform login
        3. Set self.authenticated = True on success
        4. Return True/False for success/failure

        Returns:
            True if authentication successful
        """
        pass

    def _get_from_cache(self, key: str, ttl: Optional[int] = None) -> Optional[Any]:
        """
        Get data from in-memory cache with per-key TTL.

        Args:
            key: Cache key
            ttl: TTL in seconds. If None, uses default cache_ttl from settings.

        Returns:
            Cached data or None if expired/missing
        """
        if key in self._cache:
            data, timestamp = self._cache[key]
            effective_ttl = ttl if ttl is not None else self._settings.cache_ttl
            if time.time() - timestamp < effective_ttl:
                self._cache_hits += 1
                return data
            del self._cache[key]
        self._cache_misses += 1
        return None

    def _save_to_cache(self, key: str, data: Any) -> None:
        """Save data to in-memory cache with current timestamp."""
        self._cache[key] = (data, time.time())

    def _clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        logger.info(f"🗑️ {self.name}: Кеш очищен")

    def _get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0
        return {
            "service": self.name,
            "cache_entries": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate_percent": round(hit_rate, 2),
        }

    def close(self) -> None:
        """Close session and cleanup resources."""
        if self.session:
            self.session.close()
            logger.info(f"🔌 {self.name}: Сессия закрыта")

        # Log final stats
        stats = self._get_session_stats()
        logger.info(
            f"📊 {self.name}: Финальная статистика - "
            f"{stats['successful_requests']}/{stats['total_requests']} успешных запросов "
            f"({stats['success_rate_percent']}%)"
        )
