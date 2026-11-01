"""AiBudget sliding window."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from ai_helpers import imp  # noqa: E402

AiBudget = imp("ai_budget").AiBudget


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_spend_until_limit():
    b = AiBudget(3, clock=Clock())
    assert [b.try_spend() for _ in range(4)] == [True, True, True, False]
    assert b.used_last_hour == 3
    assert b.limit == 3


def test_window_slides():
    clock = Clock()
    b = AiBudget(2, clock=clock)
    assert b.try_spend()
    clock.now += 1800
    assert b.try_spend()
    assert not b.try_spend()
    clock.now += 1800  # first spend is now exactly an hour old
    assert b.used_last_hour == 1
    assert b.try_spend()
    assert not b.try_spend()


def test_failed_spend_does_not_count():
    clock = Clock()
    b = AiBudget(1, clock=clock)
    b.try_spend()
    for _ in range(5):
        assert not b.try_spend()
    clock.now += 3600
    assert b.try_spend()


def test_zero_limit_blocks_everything():
    assert not AiBudget(0, clock=Clock()).try_spend()


def test_default_clock_works():
    b = AiBudget(50)
    assert b.try_spend() and b.used_last_hour == 1
