"""
Proxy configuration for auction services.

Provides a unified, per-instance, round-robin proxy pool that rotates across
multiple upstream providers (Oxylabs + BestProxy accounts). Each consumer
calls ``get_proxy_pool()`` and gets its own pool instance, so services
maintain independent rotation state without any global locking.
"""

import os
import random
import string
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


def _random_session_id(length: int = 9) -> str:
    """Generate a random alphanumeric session id for sticky-IP providers."""
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


@dataclass(frozen=True)
class ProxyEntry:
    """A single upstream proxy provider/account.

    ``username_template`` may contain a ``{session}`` placeholder; when it
    does, the entry supports sticky sessions and ``build_url`` will substitute
    a random session id (or one provided by the caller).
    """

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
        return f"http://{user}:{self.password}@{self.host}"


# Default pool entries shared by every service.
# Order defines the round-robin sequence on a fresh pool instance.
_DEFAULT_ENTRIES: List[ProxyEntry] = [
    ProxyEntry(
        name="oxylabs-kr",
        host="pr.oxylabs.io:7777",
        username_template="customer-arman_zVdZn-cc-kr",
        password="~eEYPgwRzO+I2",
        supports_sticky=False,
    ),
    ProxyEntry(
        name="bestproxy-1",
        host="proxy.bestproxy.com:2312",
        username_template="bp-bfk2u7wtb3gy_area-KR_life-60_session-{session}",
        password="zwj1SkzW69P1nhUs",
        supports_sticky=True,
    ),
    ProxyEntry(
        name="bestproxy-2",
        host="proxy.bestproxy.com:2312",
        username_template="bp-lahzo3m0c207_area-KR_life-60_session-{session}",
        password="8IXa2Dlz8XtIy0zN",
        supports_sticky=True,
    ),
]


@dataclass
class ProxyPool:
    """Per-instance, thread-safe round-robin pool over a list of ProxyEntry.

    Each service should obtain its own pool via :func:`get_proxy_pool` so that
    rotation indices (and sticky session ids) are independent across services.
    """

    entries: List[ProxyEntry] = field(default_factory=list)
    _index: int = -1
    _current_session_id: Optional[str] = None
    _current_url: Optional[str] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        if not self.entries:
            raise ValueError("ProxyPool requires at least one entry")
        # Seed to first entry so callers can read current() before advance().
        self._advance_locked()

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def names(self) -> List[str]:
        return [e.name for e in self.entries]

    def _advance_locked(self) -> Tuple[ProxyEntry, str]:
        self._index = (self._index + 1) % len(self.entries)
        entry = self.entries[self._index]
        self._current_session_id = (
            _random_session_id() if entry.supports_sticky else None
        )
        self._current_url = entry.build_url(self._current_session_id)
        return entry, self._current_url

    def current(self) -> Tuple[ProxyEntry, str]:
        """Return the (entry, url) currently selected without advancing."""
        with self._lock:
            return self.entries[self._index], self._current_url  # type: ignore[return-value]

    def current_session_id(self) -> Optional[str]:
        with self._lock:
            return self._current_session_id

    def advance(self) -> Tuple[ProxyEntry, str]:
        """Move to the next entry, generate a fresh sticky session id, return it."""
        with self._lock:
            return self._advance_locked()

    def next_url(self) -> str:
        """Convenience: advance() and return only the URL."""
        return self.advance()[1]

    def current_dict(self) -> Dict[str, str]:
        """Return a ``{http, https}`` dict for the current entry.

        Suitable for direct assignment to ``requests.Session.proxies``.
        """
        _, url = self.current()
        return {"http": url, "https": url}


def get_proxy_pool() -> ProxyPool:
    """Return a fresh :class:`ProxyPool` instance for the caller.

    A new instance per call is intentional — each service gets its own
    rotation index and sticky session id. There is no global pool state.
    """
    return ProxyPool(entries=list(_DEFAULT_ENTRIES))


def get_proxy_config() -> Optional[Dict[str, str]]:
    """Backwards-compatible helper used by older call sites.

    Behavior preserved from the prior single-proxy implementation:
    returns ``None`` unless ``USE_PROXY=true`` is set in the environment.
    When enabled, returns the ``{http, https}`` dict for the first entry of
    a fresh pool (i.e. ``oxylabs-kr``).

    New code should call :func:`get_proxy_pool` instead so it can rotate.
    """
    use_proxy = os.getenv("USE_PROXY", "false").lower() == "true"
    if not use_proxy:
        return None
    return get_proxy_pool().current_dict()
