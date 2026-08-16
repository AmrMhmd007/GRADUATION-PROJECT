"""
In-memory login throttling (Phase 5 — closes the "no rate limiting on
/api/auth/login" gap flagged in the Phase 3 README).

Scope note: this is per-process, in-memory state, keyed by email. That's
fine for a single-instance deployment (which is what this project targets)
but would need to move to a shared store (Redis, or a DB table) behind a
load balancer with multiple backend instances, since each process would
otherwise track its own attempt counts independently. IP-based throttling
and broader abuse protection is normally handled by a reverse proxy or API
gateway in front of the app, not the app itself — out of scope here.
"""
import threading
import time

from .config import settings

_lock = threading.Lock()
_attempts: dict[str, list[float]] = {}
_locked_until: dict[str, float] = {}


def _now() -> float:
    return time.time()


def is_locked_out(email: str) -> tuple[bool, float]:
    """Returns (locked, seconds_remaining)."""
    with _lock:
        until = _locked_until.get(email)
        if until is None:
            return False, 0.0
        remaining = until - _now()
        if remaining <= 0:
            _locked_until.pop(email, None)
            _attempts.pop(email, None)
            return False, 0.0
        return True, remaining


def record_failure(email: str) -> None:
    with _lock:
        window_start = _now() - settings.LOGIN_LOCKOUT_SECONDS
        recent = [t for t in _attempts.get(email, []) if t > window_start]
        recent.append(_now())
        _attempts[email] = recent
        if len(recent) >= settings.LOGIN_MAX_ATTEMPTS:
            _locked_until[email] = _now() + settings.LOGIN_LOCKOUT_SECONDS


def record_success(email: str) -> None:
    with _lock:
        _attempts.pop(email, None)
        _locked_until.pop(email, None)


def reset_all() -> None:
    """Test-only helper so each test starts with a clean throttle state."""
    with _lock:
        _attempts.clear()
        _locked_until.clear()
