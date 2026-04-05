"""
Cross-worker authentication coordinator for Lotte auction service.

Prevents race conditions when multiple Gunicorn workers try to authenticate
simultaneously with the same credentials. Uses file-based locking to ensure
only one worker authenticates at a time; other workers load the shared session.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from filelock import FileLock, Timeout
from loguru import logger

if TYPE_CHECKING:
    from app.services.lotte_service import LotteService

SESSIONS_DIR = Path("cache/sessions")
LOCK_PATH = SESSIONS_DIR / "lotte_auth.lock"
STATE_PATH = SESSIONS_DIR / "lotte_auth_state.json"
LOCK_TIMEOUT = 60  # Max seconds to wait for lock
AUTH_COOLDOWN = 30  # Min seconds between system-wide auth attempts
LOCKOUT_DURATION = 900  # 15 min lockout after errOverPassCnt


def _read_auth_state() -> dict:
    """Read the shared auth state file."""
    try:
        if STATE_PATH.exists():
            with open(STATE_PATH, "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.debug(f"Auth state read error (will reset): {e}")
    return {}


def _write_auth_state(state: dict) -> None:
    """Write the shared auth state file."""
    try:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        with open(STATE_PATH, "w") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        logger.error(f"Failed to write auth state: {e}")


def _is_locked_out(state: dict) -> bool:
    """Check if system-wide lockout is active (errOverPassCnt)."""
    lockout_until = state.get("lockout_until", 0)
    if time.time() < lockout_until:
        remaining = int(lockout_until - time.time())
        logger.warning(f"System-wide auth lockout active ({remaining}s remaining)")
        return True
    return False


def _was_recent_success(state: dict, max_age_minutes: float) -> bool:
    """Check if another worker recently authenticated successfully."""
    if not state.get("last_success_time"):
        return False
    age = time.time() - state["last_success_time"]
    return age < (max_age_minutes * 60)


def ensure_authenticated(service: "LotteService") -> bool:
    """
    Cross-worker-safe authentication for Lotte auction service.

    Flow:
    1. If already authenticated and session valid -> return True
    2. Check if another worker recently succeeded -> load shared session
    3. Acquire file lock (blocks other workers)
    4. Double-check after acquiring lock -> maybe other worker just finished
    5. Perform actual authentication
    6. Save session and state -> release lock
    """
    # Fast path: already authenticated and session not expired
    if service.authenticated and service.session and not service._is_session_expired():
        return True

    # Even if authenticated, session might be expired — try lightweight validation
    if service.authenticated and service.session:
        if service._validate_session():
            service.session_created_at = datetime.now()
            logger.info("Session expired by age but still valid, extended")
            return True

    # Check shared state for lockout and cooldown
    state = _read_auth_state()
    if _is_locked_out(state):
        return False

    # Cooldown: don't hammer Lotte server after recent failure
    last_attempt = state.get("last_attempt_time", 0)
    last_success = state.get("last_success_time", 0)
    if last_attempt > last_success and (time.time() - last_attempt) < AUTH_COOLDOWN:
        # Last attempt was a failure and it was recent — try shared session only
        if service._load_shared_session():
            return True
        remaining = int(AUTH_COOLDOWN - (time.time() - last_attempt))
        logger.warning(f"Auth cooldown active ({remaining}s remaining after recent failure)")
        return False

    # Try loading shared session from another worker
    if _was_recent_success(state, service.session_max_age_minutes):
        if service._load_shared_session():
            logger.info(
                f"Loaded shared session from worker PID {state.get('last_success_pid', '?')}"
            )
            return True

    # Need to authenticate — acquire cross-worker lock
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(LOCK_PATH), timeout=LOCK_TIMEOUT)

    try:
        with lock:
            # Double-check: another worker may have just finished while we waited
            state = _read_auth_state()
            if _is_locked_out(state):
                return False

            if _was_recent_success(state, service.session_max_age_minutes):
                if service._load_shared_session():
                    logger.info("Loaded shared session after waiting for lock")
                    return True

            # We are the designated authenticator — perform login
            logger.info(f"Worker PID {os.getpid()} acquired auth lock, authenticating...")

            try:
                success = service._do_authenticate()
            except Exception as auth_err:
                # _do_authenticate raises on retriable failures (network, redirect, etc.)
                # Write failure state so other workers don't immediately retry
                logger.error(f"Auth raised exception (PID {os.getpid()}): {auth_err}")
                service.authenticated = False
                service.session = None
                _write_auth_state({
                    "last_attempt_time": time.time(),
                    "last_failure_pid": os.getpid(),
                    "last_failure_error": str(auth_err),
                    "last_success_time": state.get("last_success_time", 0),
                    "last_success_pid": state.get("last_success_pid", 0),
                    "lockout_until": state.get("lockout_until", 0),
                })
                return False

            if success:
                service.authenticated = True
                service.session_created_at = datetime.now()
                service.consecutive_failures = 0
                service._save_session()
                _write_auth_state({
                    "last_success_time": time.time(),
                    "last_success_pid": os.getpid(),
                    "last_attempt_time": time.time(),
                    "lockout_until": 0,
                })
                logger.info(f"Auth succeeded (PID {os.getpid()}), session shared")
                return True
            else:
                # Non-retriable failure (wrong credentials, account locked, etc.)
                service.authenticated = False
                service.session = None
                _write_auth_state({
                    "last_attempt_time": time.time(),
                    "last_failure_pid": os.getpid(),
                    "last_success_time": state.get("last_success_time", 0),
                    "last_success_pid": state.get("last_success_pid", 0),
                    "lockout_until": state.get("lockout_until", 0),
                })
                logger.error(f"Auth failed (PID {os.getpid()})")
                return False

    except Timeout:
        logger.error(f"Auth lock timeout ({LOCK_TIMEOUT}s) — another worker may be stuck")
        return False


def set_lockout(duration: int = LOCKOUT_DURATION) -> None:
    """Set system-wide auth lockout (called on errOverPassCnt)."""
    state = _read_auth_state()
    state["lockout_until"] = time.time() + duration
    _write_auth_state(state)
    logger.warning(f"System-wide auth lockout set for {duration}s")
