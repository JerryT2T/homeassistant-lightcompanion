"""Room matching: loose wording onto the fixed room list."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from ai_helpers import imp

rooms = imp("rooms")
Room = rooms.Room

HOME = [
    Room("bathroom", "Badezimmer"),
    Room("guestbathroom", "Gästebadezimmer", aliases=("Gäste WC", "WC", "Klo", "Gästebad")),
    Room("cinema", "Heimkino"),
    Room("kitchen", "Küche"),
    Room("minikitchen", "Miniküche"),
    Room("livingroom", "Wohnzimmer"),
]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mach die Küche blau", ["kitchen"]),
        ("kueche und wohnzimer gemütlich", ["kitchen", "livingroom"]),
        ("HEIMKINO auf Party", ["cinema"]),
        ("Licht im WC an", ["guestbathroom"]),
        ("gäste wc dunkel", ["guestbathroom"]),
        ("Küchenlicht warm", ["kitchen"]),
        ("livingroom cozy", ["livingroom"]),
        ("Miniküche hell", ["minikitchen"]),
        ("einfach gemütlich bitte", []),
        ("", []),
    ],
)
def test_match_rooms(text, expected):
    assert rooms.match_rooms(text, HOME) == expected


def test_match_does_not_confuse_similar_rooms():
    assert rooms.match_rooms("Badezimmer hell", HOME) == ["bathroom"]
    assert rooms.match_rooms("Gästebadezimmer hell", HOME) == ["guestbathroom"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("cinema", "cinema"),
        ("Heimkino", "cinema"),
        ("heimkino ", "cinema"),
        ("Kueche", "kitchen"),
        ("Gästebad", "guestbathroom"),
        ("garage", None),
        ("", None),
        (None, None),
        (7, None),
    ],
)
def test_resolve_room(value, expected):
    assert rooms.resolve_room(value, HOME) == expected


def test_resolve_rooms_dedups_and_drops_unknown():
    assert rooms.resolve_rooms(["cinema", "Heimkino", "attic", "Küche"], HOME) == [
        "cinema",
        "kitchen",
    ]
    assert rooms.resolve_rooms("Wohnzimmer", HOME) == ["livingroom"]
    assert rooms.resolve_rooms(None, HOME) == []
    assert rooms.resolve_rooms({"a": 1}, HOME) == []


def test_fold_handles_umlauts_and_punctuation():
    assert rooms.fold("  Gäste-WC! ") == "gaste wc"
    assert rooms.fold("Straße") == "strasse"
