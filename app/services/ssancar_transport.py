"""Validated, failover-aware HTTP transport dedicated to SSANCAR.

The transport intentionally does not share the generic auction proxy pool or
its cookies.  Every egress candidate owns a separate ``requests.Session`` and
every operation starts with direct egress before trying configured fallbacks.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from queue import Empty, Queue
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, List, Mapping, Optional, Tuple, TypeVar
from urllib.parse import urlsplit

from loguru import logger
import requests

from app.parsers.ssancar_auth import is_ssancar_login_url


T = TypeVar("T")

CONNECT_TIMEOUT_SECONDS = 3.0
READ_TIMEOUT_SECONDS = 8.0
OVERALL_DEADLINE_SECONDS = 24.0

_OUTBOUND_LIMIT = threading.BoundedSemaphore(5)
_KOREAN_PROXY_MARKER = re.compile(
    r"(?:area|country|region|geo)[_\-=:]*kr(?:\b|[_\-])",
    re.IGNORECASE,
)


class SSANCARUpstreamError(RuntimeError):
    """Base class for retryable SSANCAR upstream failures."""

    code = "upstream_unavailable"

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        selector_count: Optional[int] = None,
        status_code: Optional[int] = None,
        redirect_path: Optional[str] = None,
        egress: Optional[str] = None,
    ) -> None:
        super().__init__(message or self.code)
        self.selector_count = selector_count
        self.status_code = status_code
        self.redirect_path = redirect_path
        self.egress = egress
        self.retryable = True


class SSANCARUpstreamAuthError(SSANCARUpstreamError):
    code = "upstream_auth"


class SSANCARUpstreamInvalidResponseError(SSANCARUpstreamError):
    code = "upstream_invalid_response"


class SSANCARUpstreamUnavailableError(SSANCARUpstreamError):
    code = "upstream_unavailable"


class SSANCARUpstreamTimeoutError(SSANCARUpstreamError):
    code = "upstream_timeout"


@dataclass(frozen=True)
class PayloadValidation(Generic[T]):
    """A semantically validated value plus safe structural diagnostics."""

    value: T
    selector_count: Optional[int] = None


@dataclass(frozen=True)
class SSANCARTransportResult(Generic[T]):
    value: T
    egress: str
    status_code: int
    selector_count: Optional[int]
    elapsed_ms: int


@dataclass(frozen=True)
class _AttemptOutcome(Generic[T]):
    response: Optional[requests.Response]
    validation: Optional[PayloadValidation[T]]
    error: Optional[Exception]


@dataclass(frozen=True)
class SSANCAREgressCandidate:
    name: str
    session: requests.Session


Validator = Callable[[requests.Response], PayloadValidation[T]]
SessionFactory = Callable[[], requests.Session]


class SSANCARTransport:
    """Try direct SSANCAR egress, then isolated non-KR proxy candidates."""

    def __init__(
        self,
        *,
        proxy_urls: Optional[List[str]] = None,
        headers: Optional[Mapping[str, str]] = None,
        session_factory: SessionFactory = requests.Session,
        clock: Callable[[], float] = time.monotonic,
        overall_deadline_seconds: float = OVERALL_DEADLINE_SECONDS,
    ) -> None:
        self._clock = clock
        if overall_deadline_seconds <= 0:
            raise ValueError("overall_deadline_seconds must be positive")
        self._overall_deadline_seconds = float(overall_deadline_seconds)
        configured_urls = (
            self._load_proxy_urls_from_env() if proxy_urls is None else proxy_urls
        )
        safe_proxy_urls = self._validated_proxy_urls(configured_urls)

        candidates: List[SSANCAREgressCandidate] = []
        candidates.append(
            SSANCAREgressCandidate(
                name="direct",
                session=self._create_session(
                    session_factory=session_factory,
                    headers=headers,
                    proxy_url=None,
                ),
            )
        )
        for index, proxy_url in enumerate(safe_proxy_urls, start=1):
            candidates.append(
                SSANCAREgressCandidate(
                    name=f"proxy-{index}",
                    session=self._create_session(
                        session_factory=session_factory,
                        headers=headers,
                        proxy_url=proxy_url,
                    ),
                )
            )
        self._candidates = tuple(candidates)

    @property
    def candidates(self) -> Tuple[SSANCAREgressCandidate, ...]:
        """Expose sanitized candidate names and sessions for diagnostics/tests."""

        return self._candidates

    @staticmethod
    def _load_proxy_urls_from_env() -> List[str]:
        raw = os.getenv("SSANCAR_PROXY_URLS", "").strip()
        if not raw:
            return []
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning(
                "ssancar_proxy_config_rejected error_code=invalid_json"
            )
            return []
        if not isinstance(decoded, list):
            logger.warning(
                "ssancar_proxy_config_rejected error_code=not_array"
            )
            return []
        return [value for value in decoded if isinstance(value, str)]

    @staticmethod
    def _validated_proxy_urls(proxy_urls: List[str]) -> List[str]:
        accepted: List[str] = []
        for index, proxy_url in enumerate(proxy_urls, start=1):
            try:
                parsed = urlsplit(proxy_url)
                valid_url = parsed.scheme in {"http", "https"} and bool(
                    parsed.hostname
                )
            except ValueError:
                valid_url = False

            if not valid_url:
                logger.warning(
                    "ssancar_proxy_config_rejected candidate_index={} "
                    "error_code=invalid_url",
                    index,
                )
                continue
            if _KOREAN_PROXY_MARKER.search(proxy_url):
                logger.warning(
                    "ssancar_proxy_config_rejected candidate_index={} "
                    "error_code=korean_egress_not_allowed",
                    index,
                )
                continue
            accepted.append(proxy_url)
        return accepted

    @staticmethod
    def _create_session(
        *,
        session_factory: SessionFactory,
        headers: Optional[Mapping[str, str]],
        proxy_url: Optional[str],
    ) -> requests.Session:
        session = session_factory()
        # Direct egress must never inherit HTTP(S)_PROXY, netrc credentials,
        # or other machine-specific Requests environment behavior.
        session.trust_env = False
        if headers:
            session.headers.update(headers)
        if proxy_url:
            session.proxies.update({"http": proxy_url, "https": proxy_url})
        else:
            session.proxies.clear()
        return session

    @staticmethod
    def _safe_path(url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        try:
            return urlsplit(url).path or "/"
        except ValueError:
            return None

    @classmethod
    def _is_login_url(cls, url: Optional[str]) -> bool:
        return is_ssancar_login_url(url)

    @classmethod
    def _classify_response(cls, response: requests.Response) -> None:
        status_code = int(response.status_code)
        location = response.headers.get("Location")
        redirect_path = cls._safe_path(location)

        if cls._is_login_url(getattr(response, "url", None)):
            raise SSANCARUpstreamAuthError(
                status_code=status_code,
                redirect_path=cls._safe_path(getattr(response, "url", None)),
            )

        for prior in getattr(response, "history", ()) or ():
            if cls._is_login_url(prior.headers.get("Location")) or cls._is_login_url(
                getattr(prior, "url", None)
            ):
                raise SSANCARUpstreamAuthError(
                    status_code=int(prior.status_code),
                    redirect_path=cls._safe_path(prior.headers.get("Location")),
                )

        if 300 <= status_code < 400:
            if cls._is_login_url(location):
                raise SSANCARUpstreamAuthError(
                    status_code=status_code,
                    redirect_path=redirect_path,
                )
            raise SSANCARUpstreamInvalidResponseError(
                status_code=status_code,
                redirect_path=redirect_path,
            )

        if status_code in {401, 403}:
            raise SSANCARUpstreamAuthError(status_code=status_code)
        if status_code == 429 or status_code >= 500:
            raise SSANCARUpstreamUnavailableError(status_code=status_code)
        if status_code != 200:
            raise SSANCARUpstreamInvalidResponseError(status_code=status_code)

    @staticmethod
    def _payload_metadata(response: Optional[requests.Response]) -> Tuple[int, str]:
        if response is None:
            return 0, "-"
        text = response.text or ""
        digest = hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:12]
        return len(text), digest

    @classmethod
    def _log_attempt(
        cls,
        *,
        operation: str,
        egress: str,
        response: Optional[requests.Response],
        selector_count: Optional[int],
        elapsed_ms: int,
        error_code: Optional[str],
        redirect_path: Optional[str] = None,
    ) -> None:
        payload_length, payload_hash = cls._payload_metadata(response)
        status = int(response.status_code) if response is not None else None
        safe_redirect_path = redirect_path
        if safe_redirect_path is None and response is not None:
            safe_redirect_path = cls._safe_path(response.headers.get("Location"))
        event = "ssancar_upstream_failure" if error_code else "ssancar_upstream_success"
        log = logger.warning if error_code else logger.info
        log(
            "{} operation={} egress={} status={} redirect_path={} payload_length={} "
            "payload_hash={} selector_count={} elapsed_ms={} error_code={}",
            event,
            operation,
            egress,
            status,
            safe_redirect_path,
            payload_length,
            payload_hash,
            selector_count,
            elapsed_ms,
            error_code,
        )

    @staticmethod
    def _select_exhausted_error(
        failures: List[SSANCARUpstreamError],
    ) -> SSANCARUpstreamError:
        for error_type in (
            SSANCARUpstreamAuthError,
            SSANCARUpstreamInvalidResponseError,
            SSANCARUpstreamTimeoutError,
            SSANCARUpstreamUnavailableError,
        ):
            for failure in failures:
                if isinstance(failure, error_type):
                    return failure
        return SSANCARUpstreamUnavailableError()

    @staticmethod
    def _timeout_for_remaining(remaining: float) -> Tuple[float, float]:
        if remaining >= CONNECT_TIMEOUT_SECONDS + READ_TIMEOUT_SECONDS:
            return CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS
        connect = min(CONNECT_TIMEOUT_SECONDS, max(0.001, remaining / 2))
        read = min(READ_TIMEOUT_SECONDS, max(0.001, remaining - connect))
        return connect, read

    def request(
        self,
        method: str,
        url: str,
        validator: Validator[T],
        *,
        operation: str = "request",
        deadline_at: Optional[float] = None,
        **kwargs: Any,
    ) -> SSANCARTransportResult[T]:
        """Execute one attempt per candidate and return only validated data."""

        started_at = self._clock()
        operation_label = (
            operation
            if re.fullmatch(r"[a-z][a-z0-9_.-]{0,31}", operation or "")
            else "unknown"
        )
        deadline = started_at + self._overall_deadline_seconds
        if deadline_at is not None:
            shared_deadline = float(deadline_at)
            if not math.isfinite(shared_deadline):
                raise ValueError("deadline_at must be a finite monotonic timestamp")
            deadline = min(deadline, shared_deadline)
        failures: List[SSANCARUpstreamError] = []

        for candidate in self._candidates:
            attempt_started = self._clock()
            remaining = deadline - attempt_started
            if remaining <= 0:
                failures.append(SSANCARUpstreamTimeoutError(egress=candidate.name))
                break

            response: Optional[requests.Response] = None
            try:
                acquired = False
                limiter = _OUTBOUND_LIMIT
                try:
                    acquire_remaining = deadline - self._clock()
                    if acquire_remaining <= 0:
                        raise SSANCARUpstreamTimeoutError()
                    acquired = limiter.acquire(timeout=acquire_remaining)
                    if not acquired:
                        raise SSANCARUpstreamTimeoutError()

                    request_remaining = deadline - self._clock()
                    if request_remaining <= 0:
                        raise SSANCARUpstreamTimeoutError()
                    request_kwargs: Dict[str, Any] = dict(kwargs)
                    request_kwargs["allow_redirects"] = False
                    request_kwargs["timeout"] = self._timeout_for_remaining(
                        request_remaining
                    )
                    outcomes: Queue[_AttemptOutcome[T]] = Queue(maxsize=1)
                    attempt_response: List[Optional[requests.Response]] = [None]

                    def execute_attempt() -> None:
                        outcome: _AttemptOutcome[T]
                        try:
                            worker_response = candidate.session.request(
                                method,
                                url,
                                **request_kwargs,
                            )
                            attempt_response[0] = worker_response
                            self._classify_response(worker_response)
                            worker_validation = validator(worker_response)
                            outcome = _AttemptOutcome(
                                response=worker_response,
                                validation=worker_validation,
                                error=None,
                            )
                        except Exception as error:
                            outcome = _AttemptOutcome(
                                response=attempt_response[0],
                                validation=None,
                                error=error,
                            )
                        finally:
                            limiter.release()
                        outcomes.put(outcome)

                    worker = threading.Thread(
                        target=execute_attempt,
                        name=f"ssancar-{candidate.name}",
                        daemon=True,
                    )
                    worker.start()
                    # The worker owns the limiter slot until the actual HTTP
                    # request and semantic validation both finish. If the
                    # caller deadline expires first, at most the configured
                    # process-wide number of daemon attempts can remain live.
                    acquired = False

                    wait_remaining = deadline - self._clock()
                    if wait_remaining <= 0:
                        raise SSANCARUpstreamTimeoutError()
                    try:
                        outcome = outcomes.get(timeout=wait_remaining)
                    except Empty:
                        response = attempt_response[0]
                        raise SSANCARUpstreamTimeoutError()

                    response = outcome.response
                    if outcome.error is not None:
                        raise outcome.error
                    if outcome.validation is None:
                        raise SSANCARUpstreamInvalidResponseError()
                    validation = outcome.validation
                finally:
                    if acquired:
                        limiter.release()

                elapsed_ms = int((self._clock() - attempt_started) * 1000)
                if self._clock() > deadline:
                    raise SSANCARUpstreamTimeoutError(
                        selector_count=validation.selector_count,
                        status_code=int(response.status_code),
                    )
                self._log_attempt(
                    operation=operation_label,
                    egress=candidate.name,
                    response=response,
                    selector_count=validation.selector_count,
                    elapsed_ms=elapsed_ms,
                    error_code=None,
                )
                return SSANCARTransportResult(
                    value=validation.value,
                    egress=candidate.name,
                    status_code=int(response.status_code),
                    selector_count=validation.selector_count,
                    elapsed_ms=elapsed_ms,
                )
            except requests.Timeout:
                failure: SSANCARUpstreamError = SSANCARUpstreamTimeoutError()
            except requests.RequestException:
                failure = SSANCARUpstreamUnavailableError()
            except SSANCARUpstreamError as error:
                failure = error
            except Exception:
                # Parser/validator exceptions are semantic upstream failures;
                # the raw exception is intentionally neither logged nor exposed.
                failure = SSANCARUpstreamInvalidResponseError()

            failure.egress = candidate.name
            if response is not None and failure.status_code is None:
                failure.status_code = int(response.status_code)
            elapsed_ms = int((self._clock() - attempt_started) * 1000)
            self._log_attempt(
                operation=operation_label,
                egress=candidate.name,
                response=response,
                selector_count=failure.selector_count,
                elapsed_ms=elapsed_ms,
                error_code=failure.code,
                redirect_path=failure.redirect_path,
            )
            failures.append(failure)

        raise self._select_exhausted_error(failures)
