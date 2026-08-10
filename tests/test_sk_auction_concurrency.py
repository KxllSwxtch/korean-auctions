"""Concurrency guards for SK Auction login.

SK was the only login-gated provider with no lock around authentication.
Routes reach the synchronous service through `asyncio.to_thread`, so N pool
threads per worker could all enter `_create_session()` at once: N login POSTs
against one shared dealer account, and `session.close()` called on a Session
other in-flight threads were still using.

HappyCar (`_auth_lock`, double-checked at happycar_service.py:452-460) and
HeyDealer (`_login_lock`, heydealer_auth_service.py:366-368) already solved
this; these tests hold SK to the same contract.
"""

import threading
import time
from unittest.mock import Mock

import pytest

from app.core.auth_errors import AuthUnavailableError
from app.core.config import settings
from app.services.sk_auction_service import SKAuctionService


def _configured_service(monkeypatch) -> SKAuctionService:
    monkeypatch.setenv("SK_AUCTION_USERNAME", "configured-user")
    monkeypatch.setenv("SK_AUCTION_PASSWORD", "configured-secret")
    monkeypatch.setattr(settings, "sk_auction_username", "configured-user", raising=False)
    monkeypatch.setattr(settings, "sk_auction_password", "configured-secret", raising=False)
    return SKAuctionService()


def test_concurrent_callers_trigger_exactly_one_login(monkeypatch) -> None:
    """Eight simultaneous requests must produce one login, not eight.

    Without the lock every thread saw `_needs_session_refresh() is True` and
    raced into `_create_session()`. On a shared dealer account that is a login
    storm, and the likeliest way to get the account locked.
    """
    service = _configured_service(monkeypatch)
    calls = []
    calls_lock = threading.Lock()

    def _slow_login() -> bool:
        with calls_lock:
            calls.append(1)
        time.sleep(0.05)
        service._authenticated = True
        return True

    service._authenticate = Mock(side_effect=_slow_login)

    errors = []
    barrier = threading.Barrier(8)

    def _worker() -> None:
        try:
            barrier.wait(timeout=5)
            service._ensure_authenticated()
        except Exception as exc:  # noqa: BLE001 — surfaced via the assert below
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors, f"concurrent callers raised: {errors}"
    assert len(calls) == 1, f"expected a single login, got {len(calls)}"


def test_login_does_not_close_a_session_another_thread_holds(monkeypatch) -> None:
    """Refreshing must not close the Session in-flight requests are using.

    `_create_session()` called `self._session.close()` on the outgoing object.
    Any thread that had already snapshotted it got its connection pool shut
    from under it mid-request.
    """
    service = _configured_service(monkeypatch)

    def _succeed() -> bool:
        service._authenticated = True
        return True

    service._authenticate = Mock(side_effect=_succeed)
    service._ensure_authenticated()

    first_session = service._session
    first_session.close = Mock(
        side_effect=AssertionError("closed a session another thread may hold")
    )

    service._authenticated = False
    service._session_created_at = None
    service._last_auth_attempt_at = None
    service._ensure_authenticated()

    first_session.close.assert_not_called()
    assert service._session is not first_session


def test_auth_lock_timeout_raises_instead_of_blocking_forever(monkeypatch) -> None:
    """A stuck login must fail fast, not pin the shared thread pool.

    `asyncio.to_thread` uses one default ThreadPoolExecutor for every provider
    route, so threads parked indefinitely on SK's lock would starve Lotte,
    KCar and Encar too — turning a one-provider outage into a whole-API one.
    """
    service = _configured_service(monkeypatch)
    monkeypatch.setattr(service, "_AUTH_LOCK_TIMEOUT_SECONDS", 0.1)
    service._authenticate = Mock(
        side_effect=AssertionError("must not log in while the lock is held")
    )

    service._auth_lock.acquire()
    try:
        started = time.monotonic()
        with pytest.raises(AuthUnavailableError) as excinfo:
            service._ensure_authenticated()
        elapsed = time.monotonic() - started
    finally:
        service._auth_lock.release()

    assert elapsed < 2, f"waited {elapsed:.2f}s instead of failing fast"
    assert excinfo.value.retriable is True
