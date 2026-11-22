"""Room matching: map free text or model output onto the fixed list of rooms.

Pure helpers without Home Assistant imports. The deterministic matcher only
*hints* which rooms a request may mean (typos, aliases); the final choice from
the fixed list is made by the LLM and re-checked here.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

FUZZY_RATIO = 0.84
RESOLVE_RATIO = 0.8
MIN_FUZZY_LEN = 4
MIN_CONTAINED_LEN = 5
MIN_LABEL_LEN = 2

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class Room:
    """One entry of the fixed room list."""

    area_id: str
    name: str
    aliases: tuple[str, ...] = ()
    floor: str | None = None
    light_count: int = 0


def fold(text: Any) -> str:
    """Lowercase, accents stripped, everything but letters and digits -> one space."""
    folded = unicodedata.normalize("NFKD", str(text or "").casefold())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return _NON_ALNUM.sub(" ", folded).strip()


def _labels(room: Room) -> list[str]:
    """Folded names a room answers to, longest first."""
    raw: Iterable[str] = (room.name, room.area_id, *room.aliases)
    labels = {fold(label) for label in raw}
    return sorted((label for label in labels if len(label) >= MIN_LABEL_LEN), key=len, reverse=True)


def _similar(a: str, b: str, threshold: float) -> bool:
    if a == b:
        return True
    if min(len(a), len(b)) < MIN_FUZZY_LEN:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


def _label_in_tokens(label: str, tokens: Sequence[str]) -> bool:
    words = label.count(" ") + 1
    for start in range(len(tokens) - words + 1):
        window = " ".join(tokens[start : start + words])
        if _similar(window, label, FUZZY_RATIO):
            return True
    # Compounds such as "kuechenlicht" still name the kitchen.
    return (
        words == 1
        and len(label) >= MIN_CONTAINED_LEN
        and any(token.startswith(label) for token in tokens)
    )


def match_rooms(text: Any, rooms: Sequence[Room]) -> list[str]:
    """Area ids whose name, id or alias appears in ``text`` (typos tolerated)."""
    tokens = fold(text).split()
    if not tokens:
        return []
    return [
        room.area_id
        for room in rooms
        if any(_label_in_tokens(label, tokens) for label in _labels(room))
    ]


def resolve_room(value: Any, rooms: Sequence[Room]) -> str | None:
    """Map one model-provided room (id, name or alias) to an area id of the list."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    for room in rooms:
        if room.area_id == raw:
            return room.area_id
    wanted = fold(raw)
    if not wanted:
        return None
    best: tuple[float, str] | None = None
    for room in rooms:
        for label in _labels(room):
            if label == wanted:
                return room.area_id
            if min(len(label), len(wanted)) < MIN_FUZZY_LEN:
                continue
            ratio = difflib.SequenceMatcher(None, label, wanted).ratio()
            if ratio >= RESOLVE_RATIO and (best is None or ratio > best[0]):
                best = (ratio, room.area_id)
    return best[1] if best else None


def resolve_rooms(values: Any, rooms: Sequence[Room]) -> list[str]:
    """Distinct area ids for a model-provided list; unknown entries are dropped."""
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)):
        return []
    out: list[str] = []
    for value in values:
        area_id = resolve_room(value, rooms)
        if area_id and area_id not in out:
            out.append(area_id)
    return out
