"""Simple token-bucket style rate limiter for synchronous clients."""

from __future__ import annotations

import time
from collections import deque
from threading import Lock
from typing import Callable, Deque


class RateLimiter:
    """Permit at most ``max_calls`` within ``period`` seconds."""

    def __init__(
        self,
        max_calls: int,
        period: float,
        now_func: Callable[[], float] | None = None,
        sleep_func: Callable[[float], None] | None = None,
    ) -> None:
        if max_calls <= 0:
            raise ValueError("max_calls must be positive")
        if period <= 0:
            raise ValueError("period must be positive")

        self._max_calls = max_calls
        self._period = period
        self._now = now_func or time.monotonic
        self._sleep = sleep_func or time.sleep
        self._events: Deque[float] = deque()
        self._lock = Lock()

    def acquire(self) -> None:
        """Block until a new call is permitted."""

        while True:
            with self._lock:
                now = self._now()

                while self._events and now - self._events[0] >= self._period:
                    self._events.popleft()

                if len(self._events) < self._max_calls:
                    self._events.append(now)
                    return

                earliest = self._events[0]
                wait_time = self._period - (now - earliest)

            if wait_time > 0:
                self._sleep(wait_time)
            else:
                # In extremely rare race conditions, loop immediately.
                continue


__all__ = ["RateLimiter"]
