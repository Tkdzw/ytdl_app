"""
Engine: one shared guard against "HTTP 429 Too Many Requests".

Running several videos at once, each over several connections, multiplies the
number of requests YouTube sees. Every download in the app goes through this
guard, which:

* caps the total number of connections across *all* downloads
  (``acquire_connection`` / ``release_connection``),
* spaces out the start of each video (``wait_turn_to_start``),
* on a 429 pauses everything for a cool-down (the server's Retry-After when it
  sends one, otherwise 30 s, doubling while 429s keep coming, up to 5 min),
  and halves both the connection cap and the number of videos at once,
* creeps back to full speed after a quiet minute with no 429s.

The guard lives for the whole app session, so a slow-down learned by one batch
carries over to the next.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from utils.logger import AppLogger

_log = AppLogger.get_logger(__name__)

# Upper bound on simultaneous connections across every download.
MAX_TOTAL_CONNECTIONS = 16
_MIN_CONNECTIONS = 2
_BASE_COOLDOWN = 30.0
_MAX_COOLDOWN = 300.0
_RECOVER_AFTER = 60.0          # quiet seconds before raising the caps a step
_START_SPACING = 1.5           # seconds between starting two videos


class RateGuard:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._conn_cap = MAX_TOTAL_CONNECTIONS
        self._conns_in_use = 0
        self._video_cap: Optional[int] = None      # None = whatever the user set
        self._cooldown_until = 0.0
        self._next_cooldown = _BASE_COOLDOWN
        self._last_429 = 0.0
        self._last_step = 0.0
        self._last_start = 0.0

    # ── Reporting a 429 ───────────────────────────────────────────────────────

    def note_429(self, retry_after: Optional[float] = None, running_videos: int = 1) -> float:
        """Record a 429. Returns how long everything now pauses (seconds)."""
        with self._cond:
            now = time.monotonic()
            # Several connections usually hit the same 429 together: count a
            # burst once, so one event doesn't collapse the caps to the floor.
            if now - self._last_429 > 5.0:
                self._conn_cap = max(_MIN_CONNECTIONS, self._conn_cap // 2)
                current = self._video_cap or running_videos
                self._video_cap = max(1, min(current, running_videos) // 2 or 1)
                wait = retry_after if retry_after and retry_after > 0 else self._next_cooldown
                wait = min(max(wait, 5.0), _MAX_COOLDOWN)
                self._next_cooldown = min(self._next_cooldown * 2, _MAX_COOLDOWN)
                self._cooldown_until = max(self._cooldown_until, now + wait)
                _log.warning("HTTP 429: pausing %.0fs; caps now %d connections, %d video(s)",
                             wait, self._conn_cap, self._video_cap)
            self._last_429 = self._last_step = now
            self._cond.notify_all()
            return max(0.0, self._cooldown_until - now)

    # ── Status ────────────────────────────────────────────────────────────────

    def cooldown_left(self) -> float:
        with self._cond:
            return max(0.0, self._cooldown_until - time.monotonic())

    def videos_allowed(self, wanted: int) -> int:
        with self._cond:
            self._recover()
            return max(1, min(wanted, self._video_cap or wanted))

    def is_slowed(self) -> bool:
        with self._cond:
            self._recover()
            return self._video_cap is not None or self._conn_cap < MAX_TOTAL_CONNECTIONS

    def _recover(self) -> None:
        """Raise the caps one step per quiet minute. Caller holds the lock."""
        now = time.monotonic()
        if self._video_cap is None and self._conn_cap >= MAX_TOTAL_CONNECTIONS:
            self._next_cooldown = _BASE_COOLDOWN
            return
        if now - self._last_step < _RECOVER_AFTER:
            return
        self._last_step = now
        self._conn_cap = min(MAX_TOTAL_CONNECTIONS, self._conn_cap * 2)
        if self._video_cap is not None:
            self._video_cap += 1
            if self._video_cap >= 16:
                self._video_cap = None
        self._next_cooldown = max(_BASE_COOLDOWN, self._next_cooldown / 2)
        self._cond.notify_all()

    # ── Waiting ───────────────────────────────────────────────────────────────

    def wait_cooldown(self, stop: Optional[threading.Event] = None) -> bool:
        """Block until any cool-down ends. Returns False if *stop* was set."""
        while True:
            left = self.cooldown_left()
            if left <= 0:
                return True
            if stop is not None:
                if stop.wait(min(left, 0.5)):
                    return False
            else:
                time.sleep(min(left, 0.5))

    def wait_turn_to_start(self, stop: Optional[threading.Event] = None) -> bool:
        """Wait out any cool-down plus the spacing between video starts."""
        while True:
            if not self.wait_cooldown(stop):
                return False
            with self._cond:
                gap = self._last_start + _START_SPACING - time.monotonic()
                if gap <= 0 and self._cooldown_until <= time.monotonic():
                    self._last_start = time.monotonic()
                    return True
            pause = max(gap, 0.05)
            if stop is not None:
                if stop.wait(pause):
                    return False
            else:
                time.sleep(pause)

    def acquire_connection(self, stop: Optional[threading.Event] = None) -> bool:
        """Take one connection slot, waiting for cool-downs and free slots."""
        with self._cond:
            while True:
                if stop is not None and stop.is_set():
                    return False
                now = time.monotonic()
                self._recover()
                if self._cooldown_until <= now and self._conns_in_use < self._conn_cap:
                    self._conns_in_use += 1
                    return True
                timeout = 0.5
                if self._cooldown_until > now:
                    timeout = min(timeout, self._cooldown_until - now)
                self._cond.wait(max(timeout, 0.05))

    def release_connection(self) -> None:
        with self._cond:
            self._conns_in_use = max(0, self._conns_in_use - 1)
            self._cond.notify_all()


GUARD = RateGuard()


def is_429(text: str) -> bool:
    t = (text or "").lower()
    return "429" in t and ("too many" in t or "http error" in t) or "too many requests" in t


def retry_after_seconds(headers) -> Optional[float]:
    """Parse a Retry-After header given in seconds (the HTTP-date form is ignored)."""
    try:
        value = headers.get("Retry-After") if headers is not None else None
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
