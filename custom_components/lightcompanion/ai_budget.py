"""Sliding-window limit on LLM calls per hour."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

WINDOW_S = 3600.0


class AiBudget:
    """Allows ``calls_per_hour`` spends within any rolling 60 minutes."""

    def __init__(
        self, calls_per_hour: int, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._limit = max(0, int(calls_per_hour))
        self._clock = clock
        self._spent: deque[float] = deque()

    def _prune(self) -> None:
        cutoff = self._clock() - WINDOW_S
        while self._spent and self._spent[0] <= cutoff:
            self._spent.popleft()

    def try_spend(self) -> bool:
        """Reserve one call; False when the window is full."""
        self._prune()
        if len(self._spent) >= self._limit:
            return False
        self._spent.append(self._clock())
        return True

    @property
    def used_last_hour(self) -> int:
        self._prune()
        return len(self._spent)

    @property
    def limit(self) -> int:
        return self._limit
