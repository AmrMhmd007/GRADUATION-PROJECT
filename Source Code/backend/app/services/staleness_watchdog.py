"""
Door staleness watchdog (Phase 7 — found during full system integration
testing).

Bug this closes: `Door.online` was only ever flipped to False by an
explicit "offline" message — either a directly-connected node's MQTT
last-will firing on an ungraceful disconnect, or the Building Gateway
(Phase 6) explicitly publishing "offline" after several missed polls. Both
of those assume *something* is still alive to send that message. If the
gateway process itself is killed, crashes, or the host loses power, nothing
ever publishes "offline" for the RS-485 nodes it was relaying — those doors
stayed `online=True` in the database indefinitely, which is exactly the
kind of stale-but-plausible-looking dashboard state that's dangerous for an
access-control system (an admin seeing "online" has no reason to suspect a
door's status hasn't updated in an hour).

Fix: a periodic, transport-agnostic sweep. It doesn't care whether a door
talks directly or through a gateway — it only looks at `last_seen`. Any
door still marked online whose last_seen is older than
`DOOR_STALE_AFTER_SECONDS` gets flipped to offline. This is a deliberately
simple backstop, not a replacement for the existing LWT/explicit-offline
paths (those are still faster when they do fire).
"""
import datetime
import logging
import threading

from ..config import settings
from ..database import SessionLocal
from .. import models

logger = logging.getLogger("staleness_watchdog")

_stop_event = threading.Event()
_thread: threading.Thread | None = None


def sweep_once(db) -> list[str]:
    """Runs one staleness sweep against the given DB session. Returns the
    list of door codes that were just marked offline (empty if none were
    stale) — factored out like this so it can be unit-tested directly
    without waiting on a real timer/thread."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(seconds=settings.DOOR_STALE_AFTER_SECONDS)
    stale_doors = (
        db.query(models.Door)
        .filter(models.Door.online.is_(True))
        .filter(models.Door.last_seen.isnot(None))
        .filter(models.Door.last_seen < cutoff)
        .all()
    )
    codes = []
    for door in stale_doors:
        door.online = False
        codes.append(door.code)
    if stale_doors:
        db.commit()
        logger.warning("Marked %d door(s) offline (stale last_seen): %s", len(stale_doors), codes)
    return codes


def _loop():
    while not _stop_event.is_set():
        db = SessionLocal()
        try:
            sweep_once(db)
        except Exception:
            logger.exception("Staleness sweep failed")
        finally:
            db.close()
        _stop_event.wait(settings.DOOR_STALENESS_CHECK_INTERVAL_SECONDS)


def start():
    global _thread
    if settings.DISABLE_MQTT:
        # No live status transport is running in this mode (tests, or MQTT
        # deliberately disabled) — nothing to sweep, and starting the
        # background thread would just be dead weight.
        logger.info("DISABLE_MQTT set — staleness watchdog not started")
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()
    logger.info("Staleness watchdog started (stale after %ss, checked every %ss)",
                settings.DOOR_STALE_AFTER_SECONDS, settings.DOOR_STALENESS_CHECK_INTERVAL_SECONDS)


def stop():
    _stop_event.set()
