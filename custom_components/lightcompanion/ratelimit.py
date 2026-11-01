"""Per-transport rate limiting for light commands.

Frames are never queued: ``acquire`` either grants a slot within the frame
budget or returns ``False`` so the caller drops the (stale) frame.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

DEFAULT_TRANSPORT = "generic"
# Longest a frame may wait for a slot before it is considered stale.
DEFAULT_MAX_WAIT_S = 0.5


@dataclass(frozen=True, slots=True)
class TransportProfile:
    """Rate-limit and behaviour profile of a light transport class."""

    name: str
    max_per_s: float
    min_transition: float = 0.0
    prefer_group: bool = False
    native_effects_first: bool = False


TRANSPORTS: dict[str, TransportProfile] = {
    # Hue bridge limit is ~10 commands/s; Innr bulbs on the bridge are "hue" too.
    "hue": TransportProfile("hue", 8, 0.4, prefer_group=True),
    "zigbee": TransportProfile("zigbee", 2, 0.5),
    "wled": TransportProfile("wled", 10, 0.0, native_effects_first=True),
    "lifx": TransportProfile("lifx", 10),
    "nanoleaf": TransportProfile("nanoleaf", 5, 0.0, native_effects_first=True),
    "wifi_slow": TransportProfile("wifi_slow", 1, 1.0),
    "generic": TransportProfile("generic", 2, 0.5),
}


class RateLimiter:
    """Global plus per-transport spacing limiter (slot reservation, no queue)."""

    def __init__(self, global_per_s: int, *, max_wait_s: float = DEFAULT_MAX_WAIT_S) -> None:
        self._global_interval = 1.0 / max(float(global_per_s), 0.1)
        self._max_wait = max_wait_s
        self._global_next = 0.0
        self._next: dict[str, float] = {}

    def profile(self, transport: str) -> TransportProfile:
        """Return the profile for a transport (unknown names -> generic)."""
        return TRANSPORTS.get(transport) or TRANSPORTS[DEFAULT_TRANSPORT]

    async def acquire(self, transport: str) -> bool:
        """Wait for a slot; False means the caller must drop this frame."""
        profile = self.profile(transport)
        interval = 1.0 / profile.max_per_s
        key = profile.name
        now = time.monotonic()
        slot = max(now, self._global_next, self._next.get(key, 0.0))
        wait = slot - now
        if wait > self._max_wait:
            return False
        # Reserve before sleeping so concurrent callers serialise.
        self._global_next = slot + self._global_interval
        self._next[key] = slot + interval
        if wait > 0:
            await asyncio.sleep(wait)
        return True
