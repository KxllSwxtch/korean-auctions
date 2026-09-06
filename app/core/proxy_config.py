"""Environment-managed proxy configuration for legacy auction services."""

from __future__ import annotations

import json
import os
import random
import string
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote


class ProxyConfigurationError(RuntimeError):
    """Raised when the shared proxy pool is not secret-managed."""


# A pool host is 'host:port'. These characters mean the operator pasted a full
# URL (scheme, credentials, path or query) into a field that takes neither.
_FORBIDDEN_HOST_CHARACTERS = ("/", "@", "?", "#")


def _random_session_id(length: int = 9) -> str:
    """Generate a random alphanumeric session id for sticky-IP providers."""
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


@dataclass(frozen=True)
class ProxyEntry:
    """A single environment-managed proxy provider/account."""

    name: str
    host: str
    username_template: str
    password: str
    supports_sticky: bool = False

    def build_url(self, session_id: Optional[str] = None) -> str:
        if self.supports_sticky:
            sid = session_id or _random_session_id()
            user = self.username_template.format(session=sid)
        else:
            user = self.username_template
        return (
            f"http://{quote(user, safe='')}:{quote(self.password, safe='')}"
            f"@{self.host}"
        )


def _pool_entry_from_mapping(index: int, item: object) -> ProxyEntry:
    """Validate one AUCTION_PROXY_POOL element into a ProxyEntry."""
    if not isinstance(item, dict):
        raise ProxyConfigurationError(
            f"AUCTION_PROXY_POOL[{index}] must be a JSON object"
        )

    host = str(item.get("host") or "").strip()
    username = str(item.get("username") or "").strip()
    password = str(item.get("password") or "").strip()
    if not host or not username or not password:
        raise ProxyConfigurationError(
            f"AUCTION_PROXY_POOL[{index}] needs host, username and password"
        )
    # build_url() interpolates host verbatim after the credentials, so a scheme
    # or an embedded credential here would silently produce a malformed URL.
    if any(character in host for character in _FORBIDDEN_HOST_CHARACTERS):
        raise ProxyConfigurationError(
            f"AUCTION_PROXY_POOL[{index}] host must be 'host:port' only, "
            "without a scheme or embedded credentials"
        )

    name = str(item.get("name") or "").strip() or f"auction-proxy-{index + 2}"
    return ProxyEntry(
        name=name,
        host=host,
        username_template=username,
        password=password,
        supports_sticky=bool(item.get("supports_sticky", False)),
    )


def _entries_from_pool_json() -> List[ProxyEntry]:
    """Parse the optional JSON array of additional pool entries."""
    raw = os.getenv("AUCTION_PROXY_POOL", "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProxyConfigurationError(
            "AUCTION_PROXY_POOL is not valid JSON"
        ) from exc
    if not isinstance(payload, list):
        raise ProxyConfigurationError("AUCTION_PROXY_POOL must be a JSON array")
    return [
        _pool_entry_from_mapping(index, item)
        for index, item in enumerate(payload)
    ]


def _deduplicated(entries: List[ProxyEntry]) -> List[ProxyEntry]:
    """Reject a proxy listed twice: it would double that exit's traffic share.

    Mirrors the Glovis transport, which rejects duplicate candidates rather
    than quietly collapsing them, so a copy-paste slip surfaces at boot.
    """
    seen: set[Tuple[str, str, str]] = set()
    for entry in entries:
        identity = (entry.host, entry.username_template, entry.password)
        if identity in seen:
            raise ProxyConfigurationError(
                f"duplicate auction proxy entry: {entry.name}"
            )
        seen.add(identity)
    return entries


def _entries_from_environment() -> List[ProxyEntry]:
    """Build the shared legacy pool without source-managed credentials.

    Two sources compose into one round-robin pool: the historical
    ``AUCTION_PROXY_*`` triple, and ``AUCTION_PROXY_POOL`` -- a JSON array of
    additional entries. Either source alone is sufficient; together they stack,
    so adding a provider never requires touching the existing variables.
    """
    entries: List[ProxyEntry] = []

    host = os.getenv("AUCTION_PROXY_HOST", "").strip()
    username = os.getenv("AUCTION_PROXY_USERNAME", "").strip()
    password = os.getenv("AUCTION_PROXY_PASSWORD", "").strip()
    provided = [value for value in (host, username, password) if value]
    if provided and len(provided) != 3:
        # Fail loudly. Before AUCTION_PROXY_POOL existed a partial triple could
        # only mean an outage; now it would silently shrink the pool to whatever
        # the JSON happens to carry, which is far harder to notice.
        raise ProxyConfigurationError(
            "partial AUCTION_PROXY_* configuration: set AUCTION_PROXY_HOST, "
            "AUCTION_PROXY_USERNAME and AUCTION_PROXY_PASSWORD together"
        )
    if provided:
        name = os.getenv("AUCTION_PROXY_NAME", "auction-proxy").strip()
        if not name:
            name = "auction-proxy"
        supports_sticky = (
            os.getenv("AUCTION_PROXY_SUPPORTS_STICKY", "false").strip().lower()
            == "true"
        )
        entries.append(
            ProxyEntry(
                name=name,
                host=host,
                username_template=username,
                password=password,
                supports_sticky=supports_sticky,
            )
        )

    entries.extend(_entries_from_pool_json())
    if not entries:
        raise ProxyConfigurationError("proxy configuration unavailable")
    return _deduplicated(entries)


@dataclass
class ProxyPool:
    """Per-instance, thread-safe round-robin pool over proxy entries."""

    entries: List[ProxyEntry] = field(default_factory=list)
    _index: int = -1
    _current_session_id: Optional[str] = None
    _current_url: Optional[str] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        if not self.entries:
            raise ProxyConfigurationError("proxy configuration unavailable")
        self._advance_locked()

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def names(self) -> List[str]:
        return [entry.name for entry in self.entries]

    def _advance_locked(self) -> Tuple[ProxyEntry, str]:
        self._index = (self._index + 1) % len(self.entries)
        entry = self.entries[self._index]
        self._current_session_id = (
            _random_session_id() if entry.supports_sticky else None
        )
        self._current_url = entry.build_url(self._current_session_id)
        return entry, self._current_url

    def current(self) -> Tuple[ProxyEntry, str]:
        with self._lock:
            return self.entries[self._index], self._current_url  # type: ignore[return-value]

    def current_session_id(self) -> Optional[str]:
        with self._lock:
            return self._current_session_id

    def advance(self) -> Tuple[ProxyEntry, str]:
        with self._lock:
            return self._advance_locked()

    def next_url(self) -> str:
        return self.advance()[1]

    def current_dict(self) -> Dict[str, str]:
        _, url = self.current()
        return {"http": url, "https": url}


def get_proxy_pool() -> ProxyPool:
    """Return a fresh pool built exclusively from environment values."""
    return ProxyPool(entries=_entries_from_environment())


def get_proxy_config() -> Optional[Dict[str, str]]:
    """Return the shared proxy mapping when the legacy gate is enabled."""
    use_proxy = os.getenv("USE_PROXY", "false").lower() == "true"
    if not use_proxy:
        return None
    return get_proxy_pool().current_dict()
