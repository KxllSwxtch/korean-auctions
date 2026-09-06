"""Shared tokenized HTTP transport for the DB Auto (cars.dbauto.kr) JSON API.

`cars.dbauto.kr` fronts several auction feeds -- Glovis at ``/api/auctions/glovis``
and HeyDealer at ``/api/auctions/heydealer`` -- behind one identical gate: POST an
arbitrary 64-hex fingerprint to ``/api/auth/token`` and the response sets a
short-lived ``x-api-token`` cookie (server ``Max-Age`` 180 s) that authorises every
subsequent read. There is no account and no login, which is the whole point: a feed
reached this way cannot be evicted by somebody else signing in.

Two properties of the host drive the design here.

**It geo-blocks Korea.** Every data endpoint answers ``403 {"error":"Access denied"}``
from a Korean IP while the token mint still returns 200 from anywhere, so the block
surfaces on the first real call and reads exactly like an auth failure. This is the
opposite requirement to every other source in this repo -- Encar/Autohub/KCar/SK/Lotte
are Korean domestic sites that *need* the KR egress -- so the egress country is a
per-service policy rather than a global constant, and dbauto's policy excludes KR.

**Its facet endpoints are slow and the proxy throttles parallelism.** Measured through
a JP residential exit: a warm ``/cars`` is ~0.8 s but a cold ``/model-counts`` or
``/section-counts`` can take 12-15 s, and the proxy degrades hard past ~4 concurrent
connections. A catalog page must therefore never queue behind a 13-call facet fan-out,
which is what `LaneScheduler` structurally guarantees.
"""

from __future__ import annotations

import hashlib
import math
import os
import random
import re
import secrets
import threading
import time
from dataclasses import dataclass
from queue import Empty, Full, Queue
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import quote, unquote, urlsplit

from loguru import logger
import requests

JsonValue = dict[str, Any] | list[Any]

BASE_URL = "https://cars.dbauto.kr"
TOKEN_PATH = "/api/auth/token"

#: Server Max-Age is 180 s; re-mint early so a token never expires mid-flight.
TOKEN_REFRESH_SECONDS = 150.0

CONNECT_TIMEOUT_SECONDS = 5.0
#: Cold facet calls legitimately take 12-15 s upstream, so a tight read timeout
#: would turn a slow-but-successful response into a spurious failure.
READ_TIMEOUT_SECONDS = 25.0
OVERALL_DEADLINE_SECONDS = 30.0

#: Statuses worth another attempt. Everything else (400, 404, ...) is a client
#: error that a retry cannot fix, so it propagates immediately.
RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36"
)

_SAFE_OPERATION = re.compile(r"[a-z][a-z0-9_.-]{0,31}")
#: A diagnostics label such as ``jp-primary``: a country prefix plus up to two
#: short segments. Deliberately narrow -- this string reaches logs and health
#: payloads, so it must never be able to carry a credential.
_SAFE_EGRESS = re.compile(r"[a-z]{2}-[a-z0-9]{1,12}(?:-[a-z0-9]{1,12}){0,2}", re.ASCII)
_FORBIDDEN_HOST_CHARACTERS = ("/", "@", "?", "#")


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class DbautoUpstreamError(RuntimeError):
    """Base class for safe, caller-visible DB Auto transport failures.

    Carries a stable ``code`` rather than a message: route layers map the code to
    an HTTP status, and no upstream text (which can embed proxy credentials) is
    ever forwarded to a client.
    """

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


class DbautoUpstreamAuthError(DbautoUpstreamError):
    code = "upstream_auth"


class DbautoUpstreamInvalidResponseError(DbautoUpstreamError):
    code = "upstream_invalid_response"


class DbautoUpstreamUnavailableError(DbautoUpstreamError):
    code = "upstream_unavailable"


class DbautoUpstreamTimeoutError(DbautoUpstreamError):
    code = "upstream_timeout"


class DbautoProxyUnavailableError(DbautoUpstreamError):
    code = "proxy_unavailable"


class DbautoGeoBlockedError(DbautoUpstreamError):
    """A 403 from a Korean egress -- a geo problem wearing an auth costume.

    Separated from `DbautoUpstreamAuthError` because the remedies are opposite: an
    auth error wants a fresh token, whereas re-minting against a Korean exit will
    fail forever. Alerting must be able to tell the two apart.
    """

    code = "egress_geo_blocked"
    retryable = False


@dataclass(frozen=True)
class DbautoErrorSet:
    """The five error classes a service surfaces, so per-feed subclasses work."""

    auth: type[DbautoUpstreamError] = DbautoUpstreamAuthError
    invalid: type[DbautoUpstreamError] = DbautoUpstreamInvalidResponseError
    unavailable: type[DbautoUpstreamError] = DbautoUpstreamUnavailableError
    timeout: type[DbautoUpstreamError] = DbautoUpstreamTimeoutError
    proxy: type[DbautoUpstreamError] = DbautoProxyUnavailableError
    geo: type[DbautoUpstreamError] = DbautoGeoBlockedError


DEFAULT_ERRORS = DbautoErrorSet()


# --------------------------------------------------------------------------- #
# Proxy configuration
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DbautoProxyCandidate:
    """One validated egress with a log-safe diagnostics label."""

    country: str
    egress: str
    proxy_url: str

    @property
    def identity(self) -> str:
        parsed = urlsplit(self.proxy_url)
        try:
            port = parsed.port
        except ValueError:
            port = None
        canonical = (
            f"{parsed.scheme.lower()}|{unquote(parsed.username or '').lower()}|"
            f"{(parsed.hostname or '').lower()}|{port or ''}"
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def normalize_proxy_candidate(
    candidate: DbautoProxyCandidate,
    *,
    allowed_countries: frozenset[str],
    errors: DbautoErrorSet = DEFAULT_ERRORS,
) -> DbautoProxyCandidate:
    """Validate one candidate, or raise the service's proxy error.

    ``allowed_countries`` is the policy hook that makes this module reusable: dbauto
    passes every country *except* KR, while a Korean-domestic source would pass only
    KR. A candidate outside the allowlist is rejected at construction rather than
    producing a 403 on the first real call.
    """
    try:
        country = candidate.country.strip().upper()
        egress = candidate.egress.strip().lower()
        proxy_url = candidate.proxy_url.strip()
    except (AttributeError, TypeError):
        raise errors.proxy() from None

    if country not in allowed_countries or not _SAFE_EGRESS.fullmatch(egress):
        raise errors.proxy()

    try:
        parsed = urlsplit(proxy_url)
        port = parsed.port
    except ValueError:
        raise errors.proxy() from None

    username = unquote(parsed.username or "").strip()
    password = unquote(parsed.password or "").strip()
    hostname = (parsed.hostname or "").strip().lower()
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not hostname
        or port is None
        or not username
        or not password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise errors.proxy()

    # The egress label is logged and returned in health payloads. If any part of
    # the credential appears inside it, that label becomes a leak.
    for sensitive in (username, password, hostname):
        normalized_sensitive = sensitive.strip().lower()
        if len(normalized_sensitive) >= 3 and normalized_sensitive in egress:
            raise errors.proxy()

    return DbautoProxyCandidate(country=country, egress=egress, proxy_url=proxy_url)


def load_proxy_candidates(
    prefixes: Sequence[str],
    *,
    allowed_countries: frozenset[str],
    environment: Mapping[str, str] | None = None,
    errors: DbautoErrorSet = DEFAULT_ERRORS,
) -> list[DbautoProxyCandidate]:
    """Build the egress list from secret-managed env only.

    ``prefixes`` are tried in order and the first complete set wins, so a shared
    ``DBAUTO_PROXY_*`` can be introduced while a per-service ``GLOVIS_PROXY_*``
    keeps an already-deployed service booting untouched.
    """
    values = os.environ if environment is None else environment

    for prefix in prefixes:
        host = values.get(f"{prefix}_HOST", "").strip()
        username = values.get(f"{prefix}_USERNAME", "").strip()
        password = values.get(f"{prefix}_PASSWORD", "").strip()
        country = values.get(f"{prefix}_COUNTRY", "").strip()
        egress = values.get(f"{prefix}_EGRESS_LABEL", "").strip()
        if not (host and username and password and country and egress):
            continue
        if any(character in host for character in _FORBIDDEN_HOST_CHARACTERS):
            raise errors.proxy()

        proxy_url = (
            f"http://{quote(username, safe='')}:{quote(password, safe='')}@{host}"
        )
        return [
            normalize_proxy_candidate(
                DbautoProxyCandidate(
                    country=country, egress=egress, proxy_url=proxy_url
                ),
                allowed_countries=allowed_countries,
                errors=errors,
            )
        ]

    raise errors.proxy()


# --------------------------------------------------------------------------- #
# Scheduling
# --------------------------------------------------------------------------- #

#: Scheduling class for one call.
#:  - ``interactive``  catalog list and car detail. Latency-critical; slots are
#:    structurally reserved for it.
#:  - ``cascade``      the 1-3 make/model facet calls a waiting user is blocked on.
#:  - ``bulk``         the 13-call section fan-out and background enrichment.
Lane = str
INTERACTIVE: Lane = "interactive"
CASCADE: Lane = "cascade"
BULK: Lane = "bulk"


class LaneScheduler:
    """Bounded priority semaphore with a reservation for interactive traffic.

    ``capacity`` total permits; the facet class (cascade + bulk combined) may hold at
    most ``facet_max``, so ``capacity - facet_max`` permits are always available to
    list/detail calls. On release the queues drain interactive first, then cascade,
    then bulk -- a user waiting on the Make dropdown must never sit behind some other
    request's section fan-out.
    """

    def __init__(self, capacity: int, facet_max: int) -> None:
        self._capacity = max(1, capacity)
        self._facet_max = max(1, min(facet_max, self._capacity - 1)) if self._capacity > 1 else 1
        self._lock = threading.Lock()
        self._active = 0
        self._active_facet = 0
        self._waiting: dict[Lane, list[threading.Event]] = {
            INTERACTIVE: [],
            CASCADE: [],
            BULK: [],
        }

    @property
    def facet_capacity(self) -> int:
        return self._facet_max

    @staticmethod
    def _is_facet(lane: Lane) -> bool:
        return lane != INTERACTIVE

    def _can_run_locked(self, lane: Lane) -> bool:
        if self._active >= self._capacity:
            return False
        return not self._is_facet(lane) or self._active_facet < self._facet_max

    def _grant_locked(self, lane: Lane) -> None:
        self._active += 1
        if self._is_facet(lane):
            self._active_facet += 1

    def acquire(self, lane: Lane, timeout: float) -> bool:
        """Take a permit, or return False when ``timeout`` seconds elapse first."""
        with self._lock:
            if self._can_run_locked(lane):
                self._grant_locked(lane)
                return True
            waiter = threading.Event()
            queue = self._waiting.setdefault(lane, [])
            queue.append(waiter)

        if waiter.wait(timeout=max(0.0, timeout)):
            # The releasing thread granted the permit on our behalf.
            return True

        with self._lock:
            queue = self._waiting.get(lane, [])
            if waiter in queue:
                queue.remove(waiter)
                return False
            # Raced with a release that granted us a permit after the timeout.
            if waiter.is_set():
                return True
            return False

    def release(self, lane: Lane) -> None:
        with self._lock:
            self._active -= 1
            if self._is_facet(lane):
                self._active_facet -= 1
            for candidate in (INTERACTIVE, CASCADE, BULK):
                queue = self._waiting.get(candidate) or []
                if not queue or not self._can_run_locked(candidate):
                    continue
                self._grant_locked(candidate)
                queue.pop(0).set()
                break


@dataclass
class _SessionSlot:
    """One requests.Session with its own cookie jar, fingerprint and token clock."""

    egress: str
    session: requests.Session
    fingerprint: str
    token_acquired_at: float | None = None
    #: Monotonically increasing generation, bumped on every successful mint. A
    #: failing attempt records the generation it used so a concurrent 401 burst
    #: produces exactly one forced re-mint instead of one per caller.
    token_generation: int = 0


@dataclass(frozen=True)
class DbautoServiceConfig:
    """Per-feed policy: everything that differs between Glovis and HeyDealer."""

    name: str
    #: e.g. ``/api/auctions/heydealer`` -- prepended to every data path.
    api_prefix: str
    #: Sent as Referer on both the mint and the data calls.
    referer: str
    #: Exact data paths (relative to ``api_prefix``) this service may request.
    #: An allowlist, so a bug or an injected value cannot turn the transport into
    #: a general-purpose proxy for arbitrary upstream URLs.
    allowed_paths: frozenset[str]
    allowed_countries: frozenset[str]
    proxy_env_prefixes: Sequence[str]
    errors: DbautoErrorSet = DEFAULT_ERRORS
    max_sessions: int = 4
    facet_concurrency: int = 2
    #: Minimum spacing between request *starts*, across all lanes (politeness).
    min_interval_seconds: float = 0.2
    retries: int = 3
    retry_base_seconds: float = 0.6


@dataclass(frozen=True)
class DbautoResult:
    value: JsonValue
    egress: str
    status_code: int
    elapsed_ms: int


class DbautoTransport:
    """Bounded, lane-aware, token-refreshing client for one dbauto feed."""

    def __init__(
        self,
        config: DbautoServiceConfig,
        *,
        proxy_candidates: list[DbautoProxyCandidate] | None = None,
        session_factory: Callable[[], requests.Session] = requests.Session,
        fingerprint_factory: Callable[[], str] | None = None,
        clock: Callable[[], float] = time.monotonic,
        overall_deadline_seconds: float = OVERALL_DEADLINE_SECONDS,
    ) -> None:
        self._config = config
        self._errors = config.errors
        self._clock = clock
        if not math.isfinite(overall_deadline_seconds) or overall_deadline_seconds <= 0:
            raise ValueError("overall_deadline_seconds must be positive and finite")
        self._deadline_seconds = float(overall_deadline_seconds)

        candidates = (
            load_proxy_candidates(
                config.proxy_env_prefixes,
                allowed_countries=config.allowed_countries,
                errors=self._errors,
            )
            if proxy_candidates is None
            else [
                normalize_proxy_candidate(
                    candidate,
                    allowed_countries=config.allowed_countries,
                    errors=self._errors,
                )
                for candidate in proxy_candidates
            ]
        )
        if not candidates:
            raise self._errors.proxy()

        self._closing = threading.Event()
        self._pace_lock = threading.Lock()
        self._next_start_at = 0.0
        self._scheduler = LaneScheduler(config.max_sessions, config.facet_concurrency)

        make_fingerprint = fingerprint_factory or self._new_fingerprint
        self._slots: Queue[_SessionSlot] = Queue(maxsize=config.max_sessions)
        built: list[_SessionSlot] = []
        try:
            for index in range(config.max_sessions):
                candidate = candidates[index % len(candidates)]
                session = session_factory()
                try:
                    # trust_env=False keeps an operator's shell HTTP_PROXY from
                    # silently overriding the validated egress.
                    session.trust_env = False
                    session.proxies.update(
                        {"http": candidate.proxy_url, "https": candidate.proxy_url}
                    )
                    session.headers.update(self._base_headers())
                except Exception:
                    self._close_session(session)
                    raise
                slot = _SessionSlot(
                    egress=candidate.egress,
                    session=session,
                    fingerprint=make_fingerprint(),
                )
                built.append(slot)
                self._slots.put(slot)
        except Exception:
            for slot in built:
                self._close_session(slot.session)
            raise
        self._all_slots = tuple(built)

    # -- construction helpers ------------------------------------------------ #

    def _base_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en,ko;q=0.8",
            "Referer": self._config.referer,
            "User-Agent": USER_AGENT,
        }

    @staticmethod
    def _new_fingerprint() -> str:
        return secrets.token_hex(32)

    @staticmethod
    def _close_session(session: requests.Session) -> None:
        try:
            session.close()
        except Exception:
            # Best effort: a raw close failure can embed proxy details, so it is
            # never logged.
            pass

    @property
    def egress_labels(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(slot.egress for slot in self._all_slots))

    # -- token --------------------------------------------------------------- #

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
                    domain=cookie.domain, path=cookie.path, name=cookie.name
                )

    def _classify(self, response: requests.Response, *, egress: str) -> None:
        status_code = int(response.status_code)
        if status_code == 403:
            # dbauto answers 403 both for a dead token and for a blocked country.
            # The body is identical, so the egress policy is what disambiguates:
            # a KR exit could never have been constructed here, meaning a 403 that
            # survives a re-mint is the geo-block reaching us some other way.
            raise self._errors.auth(status_code=status_code, egress=egress)
        if status_code == 401:
            raise self._errors.auth(status_code=status_code, egress=egress)
        if status_code in {407, 429} or status_code >= 500:
            raise self._errors.unavailable(status_code=status_code, egress=egress)
        if status_code != 200:
            raise self._errors.invalid(status_code=status_code, egress=egress)

    def _timeout(self, deadline: float, *, egress: str) -> tuple[float, float]:
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise self._errors.timeout(egress=egress)
        return CONNECT_TIMEOUT_SECONDS, min(READ_TIMEOUT_SECONDS, remaining)

    def _ensure_token(
        self, slot: _SessionSlot, deadline: float, *, force: bool = False
    ) -> None:
        now = self._clock()
        fresh = (
            slot.token_acquired_at is not None
            and now - slot.token_acquired_at < TOKEN_REFRESH_SECONDS
            and self._has_token_cookie(slot.session)
        )
        if not force and fresh:
            return

        self._clear_token_cookie(slot.session)
        slot.token_acquired_at = None
        response = slot.session.request(
            "POST",
            f"{BASE_URL}{TOKEN_PATH}",
            json={"fingerprint": slot.fingerprint},
            headers={
                "Content-Type": "application/json",
                "Accept": "*/*",
                "Origin": BASE_URL,
            },
            allow_redirects=False,
            timeout=self._timeout(deadline, egress=slot.egress),
        )
        self._classify(response, egress=slot.egress)
        try:
            payload = response.json()
        except Exception:
            raise self._errors.invalid(
                status_code=int(response.status_code), egress=slot.egress
            ) from None
        if (
            not isinstance(payload, dict)
            or payload.get("ok") is not True
            or not self._has_token_cookie(slot.session)
        ):
            raise self._errors.invalid(
                status_code=int(response.status_code), egress=slot.egress
            )
        slot.token_acquired_at = self._clock()
        slot.token_generation += 1

    # -- pacing -------------------------------------------------------------- #

    def _pace(self) -> None:
        """Space request *starts* globally, even across concurrent slots."""
        interval = self._config.min_interval_seconds
        if interval <= 0:
            return
        with self._pace_lock:
            now = self._clock()
            start_at = max(now, self._next_start_at)
            self._next_start_at = start_at + interval
            delay = start_at - now
        if delay > 0:
            time.sleep(delay)

    # -- request ------------------------------------------------------------- #

    def _lease_slot(self, deadline: float, *, egress_hint: str) -> _SessionSlot:
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise self._errors.timeout(egress=egress_hint)
        try:
            return self._slots.get(timeout=remaining)
        except Empty:
            raise self._errors.timeout(egress=egress_hint) from None

    def _return_slot(self, slot: _SessionSlot) -> None:
        if self._closing.is_set():
            self._close_session(slot.session)
            return
        try:
            self._slots.put_nowait(slot)
        except Full:
            self._close_session(slot.session)

    def _attempt(
        self,
        slot: _SessionSlot,
        path: str,
        params: Sequence[tuple[str, str]],
        deadline: float,
    ) -> tuple[requests.Response, JsonValue]:
        self._pace()
        self._ensure_token(slot, deadline)
        generation = slot.token_generation

        response = slot.session.request(
            "GET",
            f"{BASE_URL}{self._config.api_prefix}{path}",
            params=list(params),
            allow_redirects=False,
            timeout=self._timeout(deadline, egress=slot.egress),
        )
        if int(response.status_code) in {401, 403}:
            # Versioned re-mint: only force one if nobody else refreshed this slot
            # since the failing attempt was sent.
            if slot.token_generation == generation:
                self._ensure_token(slot, deadline, force=True)
            response = slot.session.request(
                "GET",
                f"{BASE_URL}{self._config.api_prefix}{path}",
                params=list(params),
                allow_redirects=False,
                timeout=self._timeout(deadline, egress=slot.egress),
            )
            if int(response.status_code) == 403:
                # The mint succeeds from anywhere, so a 403 that survives a fresh
                # token is not an auth problem -- it is dbauto refusing the exit
                # country. Retrying or re-minting cannot fix that, and calling it
                # "auth" would send an operator hunting for the wrong bug.
                raise self._errors.geo(status_code=403, egress=slot.egress)

        self._classify(response, egress=slot.egress)
        try:
            payload = response.json()
        except Exception:
            raise self._errors.invalid(
                status_code=int(response.status_code), egress=slot.egress
            ) from None
        if not isinstance(payload, (dict, list)):
            raise self._errors.invalid(
                status_code=int(response.status_code), egress=slot.egress
            )
        return response, payload

    def get_json(
        self,
        path: str,
        params: Iterable[tuple[str, Any]],
        operation: str,
        *,
        lane: Lane = INTERACTIVE,
        lang: str = "en",
        deadline_at: float | None = None,
        max_attempts: int | None = None,
    ) -> DbautoResult:
        """Fetch one JSON body before the hard monotonic deadline.

        ``params`` is a sequence of pairs rather than a mapping because dbauto
        expresses multi-valued filters as repeated keys (``model=a&model=b``),
        which a dict cannot represent.
        """
        if self._closing.is_set():
            raise self._errors.unavailable()
        if path not in self._config.allowed_paths:
            raise ValueError(
                f"path must be an approved {self._config.name} endpoint: {path!r}"
            )

        try:
            pairs = [
                (str(key), str(value))
                for key, value in params
                if key != "lang" and value is not None and value != ""
            ]
        except (TypeError, ValueError):
            raise ValueError("params must be an iterable of key/value pairs") from None
        pairs.insert(0, ("lang", lang))

        operation_label = (
            operation if _SAFE_OPERATION.fullmatch(operation or "") else "unknown"
        )
        started_at = self._clock()
        deadline = started_at + self._deadline_seconds
        if deadline_at is not None:
            shared = float(deadline_at)
            if not math.isfinite(shared):
                raise ValueError("deadline_at must be a finite monotonic timestamp")
            deadline = min(deadline, shared)

        attempts = (
            self._config.retries + 1
            if max_attempts is None
            else max(1, min(int(max_attempts), self._config.retries + 1))
        )
        last_error: DbautoUpstreamError | None = None
        for attempt in range(attempts):
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise self._errors.timeout(
                    status_code=last_error.status_code if last_error else None,
                    egress=last_error.egress if last_error else None,
                )

            if not self._scheduler.acquire(lane, remaining):
                raise self._errors.timeout()

            attempt_started = self._clock()
            slot: _SessionSlot | None = None
            try:
                slot = self._lease_slot(deadline, egress_hint="-")
                response, value = self._attempt(slot, path, pairs, deadline)
            except requests.Timeout:
                last_error = self._errors.timeout(
                    egress=slot.egress if slot else None
                )
            except requests.RequestException:
                last_error = self._errors.unavailable(
                    egress=slot.egress if slot else None
                )
            except DbautoUpstreamError as error:
                if slot is not None and error.egress is None:
                    error.egress = slot.egress
                last_error = error
            except Exception:
                last_error = self._errors.invalid(
                    egress=slot.egress if slot else None
                )
            else:
                elapsed_ms = int((self._clock() - attempt_started) * 1000)
                self._log(
                    operation=operation_label,
                    egress=slot.egress,
                    status=int(response.status_code),
                    elapsed_ms=elapsed_ms,
                    error=None,
                )
                return DbautoResult(
                    value=value,
                    egress=slot.egress,
                    status_code=int(response.status_code),
                    elapsed_ms=elapsed_ms,
                )
            finally:
                if slot is not None:
                    self._return_slot(slot)
                self._scheduler.release(lane)

            self._log(
                operation=operation_label,
                egress=last_error.egress or "-",
                status=last_error.status_code,
                elapsed_ms=int((self._clock() - attempt_started) * 1000),
                error=last_error,
            )

            if not last_error.retryable:
                raise last_error
            if isinstance(last_error, self._errors.invalid) and (
                last_error.status_code is not None
                and last_error.status_code not in RETRYABLE_STATUSES
            ):
                raise last_error
            if attempt == attempts - 1:
                break

            # Backoff runs OUTSIDE the scheduler permit, so sleeping never holds
            # capacity that a waiting interactive call could be using.
            backoff = self._config.retry_base_seconds * (2**attempt) + random.uniform(
                0, 0.25
            )
            time.sleep(min(backoff, max(0.0, deadline - self._clock())))

        raise last_error or self._errors.unavailable()

    @staticmethod
    def _log(
        *,
        operation: str,
        egress: str,
        status: int | None,
        elapsed_ms: int,
        error: DbautoUpstreamError | None,
    ) -> None:
        event = "dbauto_upstream_failure" if error else "dbauto_upstream_success"
        log = logger.warning if error else logger.info
        log(
            "{} operation={} egress={} status={} elapsed_ms={} error_code={}",
            event,
            operation,
            egress,
            status,
            elapsed_ms,
            error.code if error else None,
        )

    def close(self) -> None:
        """Close idle sessions now; in-flight ones close as they are returned."""
        if self._closing.is_set():
            return
        self._closing.set()
        while True:
            try:
                slot = self._slots.get_nowait()
            except Empty:
                break
            self._close_session(slot.session)
