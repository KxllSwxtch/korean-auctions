"""Environment-managed proxy configuration for legacy auction services."""

from __future__ import annotations

import os
import random
import string
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote


class ProxyConfigurationError(RuntimeError):
    """Raised when the shared proxy pool is not secret-managed."""


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


def _entries_from_environment() -> List[ProxyEntry]:
    """Build the shared legacy pool without source-managed credentials."""
    host = os.getenv("AUCTION_PROXY_HOST", "").strip()
    username = os.getenv("AUCTION_PROXY_USERNAME", "").strip()
    password = os.getenv("AUCTION_PROXY_PASSWORD", "").strip()
    if not host or not username or not password:
        raise ProxyConfigurationError("proxy configuration unavailable")

    name = os.getenv("AUCTION_PROXY_NAME", "auction-proxy").strip()
    if not name:
        name = "auction-proxy"
    supports_sticky = (
        os.getenv("AUCTION_PROXY_SUPPORTS_STICKY", "false").strip().lower()
        == "true"
    )
    return [
        ProxyEntry(
            name=name,
            host=host,
            username_template=username,
            password=password,
            supports_sticky=supports_sticky,
        )
    ]


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
