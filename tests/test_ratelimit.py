"""Tests for the per-transport rate limiter."""

from __future__ import annotations

import time

import pytest

from custom_components.lightcompanion.ratelimit import TRANSPORTS, RateLimiter


def test_profiles_match_contract() -> None:
    assert TRANSPORTS["hue"].max_per_s == 8
    assert TRANSPORTS["hue"].prefer_group
    assert TRANSPORTS["zigbee"].max_per_s == 2
    assert TRANSPORTS["wled"].native_effects_first
    assert TRANSPORTS["wifi_slow"].min_transition == 1.0
    assert TRANSPORTS["generic"].max_per_s == 2


def test_unknown_transport_is_generic() -> None:
    assert RateLimiter(4).profile("nope") is TRANSPORTS["generic"]


async def test_first_frame_is_immediate() -> None:
    limiter = RateLimiter(4)
    start = time.monotonic()
    assert await limiter.acquire("hue")
    assert time.monotonic() - start < 0.05


async def test_global_cap_spaces_frames() -> None:
    limiter = RateLimiter(4)  # 0.25 s spacing although hue allows 8/s
    start = time.monotonic()
    assert await limiter.acquire("hue")
    assert await limiter.acquire("hue")
    assert time.monotonic() - start >= 0.2


async def test_slow_transport_drops_instead_of_queueing() -> None:
    limiter = RateLimiter(10)
    assert await limiter.acquire("wifi_slow")
    start = time.monotonic()
    assert await limiter.acquire("wifi_slow") is False  # next slot is 1 s away
    assert time.monotonic() - start < 0.05


async def test_dropped_frame_does_not_consume_slot() -> None:
    limiter = RateLimiter(10)
    assert await limiter.acquire("wifi_slow")
    assert not await limiter.acquire("wifi_slow")
    assert not await limiter.acquire("wifi_slow")
    # other transports are unaffected
    assert await limiter.acquire("hue")


@pytest.mark.parametrize("rate", [1, 4, 10])
async def test_global_rate_is_respected(rate: int) -> None:
    limiter = RateLimiter(rate, max_wait_s=5)
    start = time.monotonic()
    for _ in range(3):
        assert await limiter.acquire("lifx")
    assert time.monotonic() - start >= 2 / rate * 0.9
