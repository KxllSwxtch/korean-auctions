"""Korean-only tokenized HTTP transport for the DB Auto Glovis API.

Each session slot owns one Korean proxy, cookie jar, and fingerprint. Callers
hand an entire slot to a daemon worker so a hard caller deadline never makes a
still-running Requests session available to another request.
"""

from __future__ import annotations

import hashlib
import math
from queue import Empty, Full, Queue
import re
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

from loguru import logger
import requests

from app.core.proxy_config import get_proxy_pool


T = TypeVar("T")
JsonValue = dict[str, Any] | list[Any]

BASE_URL = "https://cars.dbauto.kr"
TOKEN_PATH = "/api/auth/token"
TOKEN_REFRESH_SECONDS = 110.0
CONNECT_TIMEOUT_SECONDS = 3.0
READ_TIMEOUT_SECONDS = 8.0
OVERALL_DEADLINE_SECONDS = 24.0
MAX_SESSIONS = 4

_OUTBOUND_LIMIT = threading.BoundedSemaphore(MAX_SESSIONS)
_SAFE_OPERATION = re.compile(r"[a-z][a-z0-9_.-]{0,31}")


class GlovisUpstreamError(RuntimeError):
    """Base class for safe, retryable DB Auto transport failures."""

    code = "upstream_unavailable"
    retryable = True

    def __init__(
        self,
        *,
        status_code: int | None = None,
        egress: str | None = None,
    ) -> None:
        super().__init__(self.code)
        self.status_code = status_code
        self.egress = egress


class GlovisUpstreamAuthError(GlovisUpstreamError):
    code = "upstream_auth"


class GlovisUpstreamInvalidResponseError(GlovisUpstreamError):
    code = "upstream_invalid_response"


class GlovisUpstreamUnavailableError(GlovisUpstreamError):
    code = "upstream_unavailable"


class GlovisUpstreamTimeoutError(GlovisUpstreamError):
    code = "upstream_timeout"


class GlovisProxyUnavailableError(GlovisUpstreamError):
    code = "proxy_unavailable"


@dataclass
class _SessionSlot:
    egress: str
    session: requests.Session
    fingerprint: str
    token_acquired_at: float | None = None


@dataclass(frozen=True)
class GlovisTransportResult(Generic[T]):
    value: T
    egress: str
    status_code: int
    elapsed_ms: int


@dataclass(frozen=True)
class _AttemptOutcome:
    response: requests.Response | None
    value: JsonValue | None
    error: GlovisUpstreamError | None


class GlovisTransport:
    """Maintain bounded, proxy-affine DB Auto sessions and token state."""

    def __init__(
        self,
        *,
        proxy_candidates: list[tuple[str, str]] | None = None,
        session_factory: Callable[[], requests.Session] = requests.Session,
        fingerprint_factory: Callable[[], str] | None = None,
        clock: Callable[[], float] = time.monotonic,
        overall_deadline_seconds: float = OVERALL_DEADLINE_SECONDS,
    ) -> None:
        candidates = (
            self._proxy_candidates_from_pool()
            if proxy_candidates is None
            else proxy_candidates
        )
        if not candidates:
            raise GlovisProxyUnavailableError()
        if (
            not math.isfinite(overall_deadline_seconds)
            or overall_deadline_seconds <= 0
        ):
            raise ValueError("overall_deadline_seconds must be positive and finite")

        self._clock = clock
        self._deadline_seconds = float(overall_deadline_seconds)
        self._closing = threading.Event()
        self._state_lock = threading.Lock()

        selected = candidates[:MAX_SESSIONS]
        self._slots: Queue[_SessionSlot] = Queue(maxsize=len(selected))
        slots: list[_SessionSlot] = []
        make_fingerprint = fingerprint_factory or self._new_fingerprint
        for egress, proxy_url in selected:
            session = session_factory()
            session.trust_env = False
            session.proxies.update({"http": proxy_url, "https": proxy_url})
            session.headers.update(self._base_headers())
            slot = _SessionSlot(
                egress=egress,
                session=session,
                fingerprint=make_fingerprint(),
            )
            slots.append(slot)
            self._slots.put(slot)
        self._all_slots = tuple(slots)

    @staticmethod
    def _base_headers() -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://cars.dbauto.kr/en/glovis",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
        }

    @staticmethod
    def _new_fingerprint() -> str:
        return hashlib.sha256(secrets.token_bytes(32)).hexdigest()

    @staticmethod
    def _proxy_candidates_from_pool() -> list[tuple[str, str]]:
        pool = get_proxy_pool()
        count = min(len(pool), MAX_SESSIONS)
        candidates: list[tuple[str, str]] = []
        for index in range(count):
            entry, proxy_url = pool.current() if index == 0 else pool.advance()
            candidate = (entry.name, proxy_url)
            if candidate not in candidates:
                candidates.append(candidate)
        return candidates

    @staticmethod
    def _timeout_for_remaining(remaining: float) -> tuple[float, float]:
        if remaining >= CONNECT_TIMEOUT_SECONDS + READ_TIMEOUT_SECONDS:
            return CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS
        connect = min(CONNECT_TIMEOUT_SECONDS, max(0.001, remaining / 2))
        read = min(READ_TIMEOUT_SECONDS, max(0.001, remaining - connect))
        return connect, read

    @staticmethod
    def _has_token_cookie(session: requests.Session) -> bool:
        return any(
            cookie.name == "x-api-token" and bool(cookie.value)
            for cookie in session.cookies
        )

    @staticmethod
    def _clear_token_cookie(session: requests.Session) -> None:
        for cookie in list(session.cookies):
            if cookie.name == "x-api-token":
                session.cookies.clear(
                    domain=cookie.domain,
                    path=cookie.path,
                    name=cookie.name,
                )

    @staticmethod
    def _classify_response(
        response: requests.Response,
        *,
        egress: str,
    ) -> None:
        status_code = int(response.status_code)
        if status_code in {401, 403}:
            raise GlovisUpstreamAuthError(
                status_code=status_code,
                egress=egress,
            )
        if status_code in {407, 429} or status_code >= 500:
            raise GlovisUpstreamUnavailableError(
                status_code=status_code,
                egress=egress,
            )
        if status_code != 200:
            raise GlovisUpstreamInvalidResponseError(
                status_code=status_code,
                egress=egress,
            )

    def _request_timeout(self, deadline: float, *, egress: str) -> tuple[float, float]:
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise GlovisUpstreamTimeoutError(egress=egress)
        return self._timeout_for_remaining(remaining)

    def _ensure_token(
        self,
        slot: _SessionSlot,
        deadline: float,
        force: bool = False,
        capture_response: Callable[[requests.Response], None] | None = None,
        clear_response: Callable[[], None] | None = None,
    ) -> None:
        now = self._clock()
        token_is_fresh = (
            slot.token_acquired_at is not None
            and now - slot.token_acquired_at < TOKEN_REFRESH_SECONDS
            and self._has_token_cookie(slot.session)
        )
        if not force and token_is_fresh:
            return

        self._clear_token_cookie(slot.session)
        slot.token_acquired_at = None
        if clear_response is not None:
            clear_response()
        response = slot.session.request(
            "POST",
            f"{BASE_URL}{TOKEN_PATH}",
            json={"fingerprint": slot.fingerprint},
            allow_redirects=False,
            timeout=self._request_timeout(deadline, egress=slot.egress),
        )
        if capture_response is not None:
            capture_response(response)
        self._classify_response(response, egress=slot.egress)
        try:
            payload = response.json()
        except Exception:
            raise GlovisUpstreamInvalidResponseError(
                status_code=int(response.status_code),
                egress=slot.egress,
            ) from None
        if (
            not isinstance(payload, dict)
            or payload.get("ok") is not True
            or not self._has_token_cookie(slot.session)
        ):
            raise GlovisUpstreamInvalidResponseError(
                status_code=int(response.status_code),
                egress=slot.egress,
            )
        slot.token_acquired_at = self._clock()

    def _request_api_json(
        self,
        slot: _SessionSlot,
        path: str,
        params: Any,
        deadline: float,
        capture_response: Callable[[requests.Response], None],
        clear_response: Callable[[], None],
    ) -> tuple[requests.Response, JsonValue]:
        clear_response()
        response = slot.session.request(
            "GET",
            f"{BASE_URL}{path}",
            params=params,
            headers={"X-Fingerprint": slot.fingerprint},
            allow_redirects=False,
            timeout=self._request_timeout(deadline, egress=slot.egress),
        )
        capture_response(response)
        if int(response.status_code) in {401, 403}:
            self._ensure_token(
                slot,
                deadline,
                force=True,
                capture_response=capture_response,
                clear_response=clear_response,
            )
            clear_response()
            response = slot.session.request(
                "GET",
                f"{BASE_URL}{path}",
                params=params,
                headers={"X-Fingerprint": slot.fingerprint},
                allow_redirects=False,
                timeout=self._request_timeout(deadline, egress=slot.egress),
            )
            capture_response(response)

        self._classify_response(response, egress=slot.egress)
        try:
            payload = response.json()
        except Exception:
            raise GlovisUpstreamInvalidResponseError(
                status_code=int(response.status_code),
                egress=slot.egress,
            ) from None
        if not isinstance(payload, (dict, list)):
            raise GlovisUpstreamInvalidResponseError(
                status_code=int(response.status_code),
                egress=slot.egress,
            )
        return response, payload

    @staticmethod
    def _payload_metadata(
        response: requests.Response | None,
    ) -> tuple[int, str]:
        if response is None:
            return 0, "-"
        text = response.text or ""
        payload = text if isinstance(text, str) else str(text)
        digest = hashlib.sha256(payload.encode("utf-8", "ignore")).hexdigest()[:12]
        return len(payload), digest

    @classmethod
    def _log_attempt(
        cls,
        *,
        operation: str,
        egress: str,
        response: requests.Response | None,
        elapsed_ms: int,
        error: GlovisUpstreamError | None,
    ) -> None:
        payload_length, payload_hash = cls._payload_metadata(response)
        status = (
            int(response.status_code)
            if response is not None
            else error.status_code if error is not None else None
        )
        event = "glovis_upstream_failure" if error else "glovis_upstream_success"
        log = logger.warning if error else logger.info
        log(
            "{} operation={} egress={} status={} payload_length={} "
            "payload_hash={} elapsed_ms={} error_code={}",
            event,
            operation,
            egress,
            status,
            payload_length,
            payload_hash,
            elapsed_ms,
            error.code if error else None,
        )

    @staticmethod
    def _select_exhausted_error(
        failures: list[GlovisUpstreamError],
    ) -> GlovisUpstreamError:
        for error_type in (
            GlovisUpstreamAuthError,
            GlovisUpstreamInvalidResponseError,
            GlovisUpstreamTimeoutError,
            GlovisUpstreamUnavailableError,
        ):
            for failure in failures:
                if isinstance(failure, error_type):
                    return failure
        return GlovisUpstreamUnavailableError()

    @staticmethod
    def _close_session(session: requests.Session) -> None:
        try:
            session.close()
        except Exception:
            # Shutdown must remain best effort, and raw close failures may
            # contain proxy details that are not safe to log.
            pass

    def _release_unstarted_slot(self, slot: _SessionSlot) -> None:
        close_session = False
        with self._state_lock:
            if self._closing.is_set():
                close_session = True
            else:
                try:
                    self._slots.put_nowait(slot)
                except Full:
                    close_session = True
        if close_session:
            self._close_session(slot.session)

    def _execute_attempt(
        self,
        *,
        slot: _SessionSlot,
        path: str,
        params: Any,
        deadline: float,
        outcomes: Queue[_AttemptOutcome],
        limiter: threading.BoundedSemaphore,
    ) -> None:
        response: requests.Response | None = None
        value: JsonValue | None = None
        error: GlovisUpstreamError | None = None

        def capture_response(worker_response: requests.Response) -> None:
            nonlocal response
            response = worker_response

        def clear_response() -> None:
            nonlocal response
            response = None

        try:
            self._ensure_token(
                slot,
                deadline,
                capture_response=capture_response,
                clear_response=clear_response,
            )
            response, value = self._request_api_json(
                slot,
                path,
                params,
                deadline,
                capture_response,
                clear_response,
            )
        except requests.Timeout:
            error = GlovisUpstreamTimeoutError(egress=slot.egress)
        except requests.RequestException:
            error = GlovisUpstreamUnavailableError(egress=slot.egress)
        except GlovisUpstreamError as upstream_error:
            error = upstream_error
        except Exception:
            error = GlovisUpstreamInvalidResponseError(egress=slot.egress)

        if error is not None:
            error.egress = slot.egress
            if response is not None and error.status_code is None:
                error.status_code = int(response.status_code)
        outcome = _AttemptOutcome(response=response, value=value, error=error)

        close_session = False
        try:
            with self._state_lock:
                if self._closing.is_set():
                    close_session = True
                else:
                    try:
                        self._slots.put_nowait(slot)
                    except Full:
                        close_session = True
            if close_session:
                self._close_session(slot.session)
        finally:
            limiter.release()
            outcomes.put(outcome)

    def _lease_slot(self, deadline: float) -> _SessionSlot:
        if self._closing.is_set():
            raise GlovisUpstreamUnavailableError()
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise GlovisUpstreamTimeoutError()
        try:
            slot = self._slots.get(timeout=remaining)
        except Empty as error:
            raise GlovisUpstreamTimeoutError() from error

        close_session = False
        with self._state_lock:
            if self._closing.is_set():
                close_session = True
        if close_session:
            self._close_session(slot.session)
            raise GlovisUpstreamUnavailableError()
        return slot

    def get_json(
        self,
        path: str,
        params: Any,
        operation: str,
        deadline_at: float | None = None,
    ) -> GlovisTransportResult[JsonValue]:
        """Fetch one JSON object/array before the hard monotonic deadline."""

        if self._closing.is_set():
            raise GlovisUpstreamUnavailableError()
        started_at = self._clock()
        deadline = started_at + self._deadline_seconds
        if deadline_at is not None:
            shared_deadline = float(deadline_at)
            if not math.isfinite(shared_deadline):
                raise ValueError("deadline_at must be a finite monotonic timestamp")
            deadline = min(deadline, shared_deadline)
        operation_label = (
            operation if _SAFE_OPERATION.fullmatch(operation or "") else "unknown"
        )
        failures: list[GlovisUpstreamError] = []

        for _ in self._all_slots:
            if deadline - self._clock() <= 0:
                failures.append(GlovisUpstreamTimeoutError())
                break
            slot = self._lease_slot(deadline)
            attempt_started = self._clock()

            limiter = _OUTBOUND_LIMIT
            acquired = False
            ownership_transferred = False
            try:
                acquire_remaining = deadline - self._clock()
                if acquire_remaining <= 0:
                    raise GlovisUpstreamTimeoutError(egress=slot.egress)
                acquired = limiter.acquire(timeout=acquire_remaining)
                if not acquired:
                    raise GlovisUpstreamTimeoutError(egress=slot.egress)

                with self._state_lock:
                    closing = self._closing.is_set()
                if closing:
                    limiter.release()
                    acquired = False
                    raise GlovisUpstreamUnavailableError(egress=slot.egress)

                outcomes: Queue[_AttemptOutcome] = Queue(maxsize=1)
                worker = threading.Thread(
                    target=self._execute_attempt,
                    kwargs={
                        "slot": slot,
                        "path": path,
                        "params": params,
                        "deadline": deadline,
                        "outcomes": outcomes,
                        "limiter": limiter,
                    },
                    name="glovis-attempt",
                    daemon=True,
                )
                try:
                    worker.start()
                except Exception:
                    limiter.release()
                    acquired = False
                    raise

                # From this point the daemon worker exclusively owns both the
                # session lease and limiter permit until Requests actually
                # finishes, even when this caller reaches its hard deadline.
                acquired = False
                ownership_transferred = True
                wait_remaining = deadline - self._clock()
                if wait_remaining <= 0:
                    raise GlovisUpstreamTimeoutError(egress=slot.egress)
                try:
                    outcome = outcomes.get(timeout=wait_remaining)
                except Empty as error:
                    timeout_error = GlovisUpstreamTimeoutError(egress=slot.egress)
                    self._log_attempt(
                        operation=operation_label,
                        egress=slot.egress,
                        response=None,
                        elapsed_ms=int((self._clock() - attempt_started) * 1000),
                        error=timeout_error,
                    )
                    raise timeout_error from error
            except GlovisUpstreamError:
                if acquired:
                    limiter.release()
                if not ownership_transferred:
                    self._release_unstarted_slot(slot)
                raise
            except Exception:
                if acquired:
                    limiter.release()
                if not ownership_transferred:
                    self._release_unstarted_slot(slot)
                failure = GlovisUpstreamUnavailableError(egress=slot.egress)
                self._log_attempt(
                    operation=operation_label,
                    egress=slot.egress,
                    response=None,
                    elapsed_ms=int((self._clock() - attempt_started) * 1000),
                    error=failure,
                )
                failures.append(failure)
                continue

            elapsed_ms = int((self._clock() - attempt_started) * 1000)
            if outcome.error is not None:
                self._log_attempt(
                    operation=operation_label,
                    egress=slot.egress,
                    response=outcome.response,
                    elapsed_ms=elapsed_ms,
                    error=outcome.error,
                )
                failures.append(outcome.error)
                continue
            if outcome.response is None or outcome.value is None:
                failure = GlovisUpstreamInvalidResponseError(egress=slot.egress)
                self._log_attempt(
                    operation=operation_label,
                    egress=slot.egress,
                    response=outcome.response,
                    elapsed_ms=elapsed_ms,
                    error=failure,
                )
                failures.append(failure)
                continue
            if self._clock() > deadline:
                raise GlovisUpstreamTimeoutError(
                    status_code=int(outcome.response.status_code),
                    egress=slot.egress,
                )

            self._log_attempt(
                operation=operation_label,
                egress=slot.egress,
                response=outcome.response,
                elapsed_ms=elapsed_ms,
                error=None,
            )
            return GlovisTransportResult(
                value=outcome.value,
                egress=slot.egress,
                status_code=int(outcome.response.status_code),
                elapsed_ms=elapsed_ms,
            )

        if deadline - self._clock() <= 0:
            raise GlovisUpstreamTimeoutError(
                status_code=failures[-1].status_code if failures else None,
                egress=failures[-1].egress if failures else None,
            )
        raise self._select_exhausted_error(failures)

    def close(self) -> None:
        """Close idle sessions now and in-flight sessions after worker exit."""

        idle: list[_SessionSlot] = []
        with self._state_lock:
            if self._closing.is_set():
                return
            self._closing.set()
            while True:
                try:
                    idle.append(self._slots.get_nowait())
                except Empty:
                    break
        for slot in idle:
            self._close_session(slot.session)
