"""Chat + music-follow orchestration: LLM call -> validation -> engine."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .llm import LLMClient, LLMError, create_client
from .music import MusicProfile, ProfileCache, TrackInfo
from .plan import MAX_REPLY, LightPlan, PlanValidationError, normalize_raw_plan, validate_plan
from .prompt import (
    TASK_CHAT,
    TASK_MUSIC,
    RoomSection,
    build_chat_instructions,
    build_music_instructions,
    build_rooms_instructions,
    plan_structure,
)
from .rooms import Room, match_rooms, resolve_rooms

try:  # engine owner defines it; guard so this module stands alone
    from .engine import EffectBlockedError
except ImportError:  # pragma: no cover

    class EffectBlockedError(Exception):  # type: ignore[no-redef]
        """Fallback stand-in: ``entity_id`` is the light that blocks effects."""

        def __init__(self, entity_id: str = "") -> None:
            super().__init__(entity_id)
            self.entity_id = entity_id


if TYPE_CHECKING:
    from homeassistant.core import CALLBACK_TYPE, HomeAssistant

    from .ai_budget import AiBudget
    from .engine import EffectEngine
    from .lights import LightInfo
    from .music import MusicService
    from .settings import Settings

_LOGGER = logging.getLogger(__name__)

PLAN_CACHE_SIZE = 100
TEMPO_CLASSES = ("slow", "medium", "fast")
# Without a selected or named room every room is described, up to this many lights.
MAX_AUTO_LIGHTS = 60
_ENTITY_LIST_KEYS = ("targets", "special_targets")

_REPLIES: dict[str, dict[str, str]] = {
    "rate_limited": {
        "en": "I have used up my AI calls for this hour. The current lights stay as they are.",
        "de": (
            "Mein KI-Kontingent für diese Stunde ist aufgebraucht. "
            "Das aktuelle Licht bleibt, wie es ist."
        ),
    },
    "no_lights": {
        "en": "This room has no lights I may control.",
        "de": "In diesem Raum gibt es keine Lichter, die ich steuern darf.",
    },
    "invalid_plan": {
        "en": "I could not turn that into a safe lighting plan, so nothing was changed.",
        "de": "Daraus konnte ich keinen sicheren Lichtplan machen, deshalb wurde nichts verändert.",
    },
    "llm": {
        "en": "The AI did not answer ({code}). Nothing was changed.",
        "de": "Die KI hat nicht geantwortet ({code}). Es wurde nichts verändert.",
    },
    "blocked": {
        "en": "Effects are paused right now: {name} is on.",
        "de": "Effekte sind gerade pausiert: {name} ist an.",
    },
    "no_room": {
        "en": "I could not tell which room you mean. Pick a room or name it.",
        "de": (
            "Ich konnte nicht erkennen, welcher Raum gemeint ist. Wähle einen Raum oder nenne ihn."
        ),
    },
}


def _msg(key: str, language: str | None, **kwargs: str) -> str:
    table = _REPLIES[key]
    lang = (language or "en").lower()[:2]
    return table.get(lang, table["en"]).format(**kwargs)


def _area_lights(hass: HomeAssistant, area_id: str, settings: Settings) -> list[LightInfo]:
    from .lights import async_area_lights

    return async_area_lights(hass, area_id, settings)


def _area_name(hass: HomeAssistant, area_id: str) -> str:
    try:
        from homeassistant.helpers import area_registry as ar

        area = ar.async_get(hass).async_get_area(area_id)
        return area.name if area else area_id
    except Exception:
        return area_id


def _friendly_name(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    name = state.attributes.get("friendly_name") if state else None
    return str(name) if name else entity_id


def _room_directory(hass: HomeAssistant, settings: Settings) -> list[Room]:
    """The fixed room list: every area that has a light Light Companion may control."""
    from homeassistant.helpers import area_registry as ar

    from .lights import async_list_areas

    area_reg = ar.async_get(hass)
    rooms: list[Room] = []
    for area in async_list_areas(hass, settings):
        count = sum(1 for light in area["lights"] if not light["excluded"])
        if not count:
            continue
        entry = area_reg.async_get_area(area["area_id"])
        aliases = tuple(sorted(a for a in (entry.aliases if entry else ()) if a and a.strip()))
        rooms.append(
            Room(
                area_id=area["area_id"],
                name=area["name"],
                aliases=aliases,
                floor=area.get("floor_name"),
                light_count=count,
            )
        )
    return rooms


def _raw_for_room(
    raw: dict[str, Any], lights: list[LightInfo], *, listed: bool
) -> dict[str, Any] | None:
    """The shared plan narrowed to one room; None when the plan skips that room.

    ``listed`` says whether the model saw this room's lights. A plan whose
    ``targets`` name lights, but none of a listed room, leaves that room alone;
    a room the model chose without seeing its lights gets the plan on all its
    normal lights.
    """
    ids = {light.entity_id for light in lights if not light.excluded}
    out = dict(raw)
    out.pop("rooms", None)
    for key in _ENTITY_LIST_KEYS:
        value = raw.get(key)
        if isinstance(value, (list, tuple)):
            out[key] = [item for item in value if item in ids]
    effects = raw.get("native_effects")
    if isinstance(effects, dict):
        out["native_effects"] = {k: v for k, v in effects.items() if k in ids}
    targeted = isinstance(raw.get("targets"), (list, tuple)) and bool(raw["targets"])
    if listed and targeted and not any(out.get(key) for key in _ENTITY_LIST_KEYS):
        return None
    return out


def _unknown_entities(raw: dict[str, Any], known: set[str]) -> list[Any]:
    """Light ids of the plan that belong to none of the rooms in play."""
    named: list[Any] = []
    for key in _ENTITY_LIST_KEYS:
        value = raw.get(key)
        if isinstance(value, (list, tuple)):
            named.extend(value)
    effects = raw.get("native_effects")
    if isinstance(effects, dict):
        named.extend(effects)
    return [item for item in named if not isinstance(item, str) or item not in known]


@dataclass(frozen=True, slots=True)
class ChatResult:
    reply: str
    applied: bool
    plan: dict[str, Any] | None
    error: str | None
    areas: tuple[str, ...] = ()


@dataclass(slots=True)
class _Follow:
    unsub: Callable[[], None]
    track: TrackInfo | None = None
    last_uri: str | None = None
    error: str | None = None
    profile: MusicProfile | None = None
    task: asyncio.Task | None = None


class Planner:
    def __init__(  # noqa: PLR0913 - contract signature
        self,
        hass: HomeAssistant,
        settings: Settings,
        budget: AiBudget,
        engine: EffectEngine,
        music: MusicService,
        *,
        client: LLMClient | None = None,
    ) -> None:
        self.hass = hass
        self._settings = settings
        self._budget = budget
        self._engine = engine
        self._music = music
        self._client = client
        self._last_text: dict[str, str] = {}
        self._last_plan: dict[str, LightPlan] = {}
        self._follow: dict[str, _Follow] = {}
        self._profiles = ProfileCache()
        self._plan_cache: OrderedDict[tuple[str, str, str], dict[str, Any]] = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = {}
        self._listeners: list[Callable[[], None]] = []

    # -- lifecycle -------------------------------------------------------------

    async def async_start(self) -> None:
        if self._client is None:
            try:
                self._client = create_client(self.hass, self._settings)
            except LLMError as err:
                _LOGGER.warning("LLM provider not usable: %s", err.code)

    async def async_stop(self) -> None:
        for area_id in list(self._follow):
            self._unfollow(area_id)

    # -- listeners (extra, additive: lets the WS subscription push planner changes) ----

    def async_add_listener(self, cb: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(cb)

        def _remove() -> None:
            if cb in self._listeners:
                self._listeners.remove(cb)

        return _remove

    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                _LOGGER.debug("planner listener failed", exc_info=True)

    # -- chat ------------------------------------------------------------------

    async def async_chat(self, area_id: str, text: str, language: str | None) -> ChatResult:
        """Chat for exactly one room (services, automations): the text cannot re-route."""
        return await self.async_chat_rooms([area_id], text, language, route=False)

    async def async_chat_rooms(  # noqa: PLR0911, PLR0912, PLR0915 - one linear chat flow
        self,
        area_ids: Sequence[str],
        text: str,
        language: str | None,
        *,
        route: bool = True,
    ) -> ChatResult:
        """Chat for the selected rooms with ONE AI call.

        With ``route`` the AI picks the rooms the request means from the fixed room
        list (loose wording allowed); the selected rooms are the default. The one
        plan is then validated and applied per room.
        """
        settings = self._settings
        directory = _room_directory(self.hass, settings) if route else []
        known = {room.area_id for room in directory}
        selected = [a for a in dict.fromkeys(area_ids) if not route or a in known]
        hinted = match_rooms(text, directory) if route else []
        listed = list(dict.fromkeys([*selected, *hinted]))
        if route and not listed and sum(r.light_count for r in directory) <= MAX_AUTO_LIGHTS:
            listed = [room.area_id for room in directory]
        lights_by_area = {a: _area_lights(self.hass, a, settings) for a in listed}
        if not (directory if route else any(lights_by_area.values())):
            return ChatResult(_msg("no_lights", language), False, None, "no_lights")
        if not self._budget.try_spend():
            self._notify()
            return ChatResult(_msg("rate_limited", language), False, None, "rate_limited")

        if route:
            names = {room.area_id: room.name for room in directory}
            running = next((a for a in selected if a in self._last_plan), None)
            instructions = build_rooms_instructions(
                rooms=directory,
                selected=selected,
                sections=[
                    RoomSection(a, names[a], lights, self._media(a), self._music.track(a))
                    for a, lights in lights_by_area.items()
                    if lights
                ],
                settings=settings,
                text=text,
                language=language,
                current_plan=self._last_plan[running].as_dict() if running else None,
            )
        else:
            area_id = selected[0]
            instructions = build_chat_instructions(
                area_name=_area_name(self.hass, area_id),
                lights=lights_by_area[area_id],
                settings=settings,
                text=text,
                language=language,
                track=self._music.track(area_id),
                current_plan=(
                    self._last_plan[area_id].as_dict() if area_id in self._last_plan else None
                ),
                media=self._media(area_id),
            )
        try:
            raw = await self._generate(TASK_CHAT, instructions, plan_structure(with_rooms=route))
        except LLMError as err:
            return ChatResult(_msg("llm", language, code=err.code), False, None, err.code)
        self._notify()
        raw = normalize_raw_plan(raw)

        rooms = selected
        if route:
            wanted = raw.get("rooms") if isinstance(raw, dict) else None
            rooms = resolve_rooms(wanted, directory) or selected or hinted
        if not rooms:
            asked = raw.get("reply") if isinstance(raw, dict) else None
            if isinstance(raw, dict) and raw.get("action") == "none" and isinstance(asked, str):
                return ChatResult(asked.strip()[:MAX_REPLY], False, None, None)
            return ChatResult(_msg("no_room", language), False, None, "no_room")

        plans: list[tuple[str, LightPlan, list[LightInfo]]] = []
        try:
            for area in rooms:
                if area not in lights_by_area:
                    lights_by_area[area] = _area_lights(self.hass, area, settings)
            if route and isinstance(raw, dict):
                in_play = {
                    light.entity_id
                    for lights in lights_by_area.values()
                    for light in lights
                    if not light.excluded
                }
                if unknown := _unknown_entities(raw, in_play):
                    raise PlanValidationError(f"unknown or excluded target: {unknown[0]!r}")
            for area in rooms:
                lights = lights_by_area[area]
                if not lights:
                    continue
                room_raw: Any = raw
                if route and isinstance(raw, dict):
                    room_raw = _raw_for_room(raw, lights, listed=area in listed)
                    if room_raw is None:
                        continue
                plans.append((area, validate_plan(room_raw, lights, settings), lights))
        except PlanValidationError as err:
            _LOGGER.warning("Rejected LLM plan for %s: %s", ", ".join(rooms), err)
            return ChatResult(_msg("invalid_plan", language), False, None, "invalid_plan")
        if not plans:
            return ChatResult(_msg("no_lights", language), False, None, "no_lights")

        head = plans[0][1]
        applied: list[str] = []
        failure: ChatResult | None = None
        for area, plan, lights in plans:
            result = await self._execute(area, plan, lights, source="chat", language=language)
            if result.error is not None:
                failure = failure or result
                continue
            self._last_text[area] = text
            if not result.applied:
                continue
            applied.append(area)
            if plan.action == "apply":
                self._last_plan[area] = plan
                if plan.follow_music:
                    self._follow_area(area)
                else:
                    self._unfollow(area)
            elif plan.action == "stop":
                self._last_plan.pop(area, None)
                self._unfollow(area)
        self._notify()
        if failure is not None and not applied:
            return failure
        return ChatResult(head.reply, bool(applied), head.as_dict(), None, tuple(applied))

    def _media(self, area_id: str) -> list[dict[str, str]] | None:
        """Active media players of the room, or None when that cannot be read."""
        reader = getattr(self._music, "media_context", None)
        if reader is None:
            return None
        try:
            return list(reader(area_id))
        except Exception:
            _LOGGER.debug("Media context unavailable for %s", area_id, exc_info=True)
            return None

    async def _execute(
        self,
        area_id: str,
        plan: LightPlan,
        lights: list[LightInfo],
        *,
        source: str,
        language: str | None = None,
    ) -> ChatResult:
        as_dict = plan.as_dict()
        if plan.action == "none":
            return ChatResult(plan.reply, False, as_dict, None)
        if plan.action == "stop":
            await self._engine.async_stop(area_id, restore=True)
            return ChatResult(plan.reply, True, as_dict, None)
        chosen = plan.chosen(lights)
        if not chosen:  # e.g. a room that only has opt-in lights the plan leaves out
            return ChatResult(plan.reply, False, as_dict, None)
        try:
            await self._engine.async_apply(area_id, plan, chosen, source=source)
        except EffectBlockedError as err:
            name = _friendly_name(self.hass, err.entity_id)
            return ChatResult(_msg("blocked", language, name=name), False, None, "blocked")
        return ChatResult(plan.reply, True, as_dict, None)

    async def _generate(
        self, task: str, instructions: str, structure: dict[str, Any]
    ) -> dict[str, Any]:
        if self._client is None:
            self._client = create_client(self.hass, self._settings)
        return await self._client.async_generate(
            task_name=task, instructions=instructions, schema=structure
        )

    # -- music follow ------------------------------------------------------------

    def _follow_area(self, area_id: str) -> None:
        current = self._music.track(area_id)
        existing = self._follow.get(area_id)
        if existing is not None:
            existing.track = current
            existing.last_uri = current.uri if current else existing.last_uri
            existing.error = None
            return

        def _on_track(track: TrackInfo | None) -> None:
            self._on_track(area_id, track)

        unsub = self._music.async_track_listener(area_id, _on_track)
        self._follow[area_id] = _Follow(
            unsub=unsub, track=current, last_uri=current.uri if current else None
        )

    def _unfollow(self, area_id: str) -> None:
        follow = self._follow.pop(area_id, None)
        if follow is None:
            return
        follow.unsub()
        if follow.task is not None and not follow.task.done():
            follow.task.cancel()

    def _on_track(self, area_id: str, track: TrackInfo | None) -> None:
        follow = self._follow.get(area_id)
        if follow is None:
            return
        follow.track = track
        self._notify()
        if track is None or not track.is_playing or not track.uri:
            return  # keep the running plan
        if track.uri == follow.last_uri:
            return
        follow.last_uri = track.uri
        if follow.task is not None and not follow.task.done():
            follow.task.cancel()
        follow.task = self.hass.async_create_task(self._async_replan(area_id, track))

    async def _async_replan(self, area_id: str, track: TrackInfo) -> None:
        follow = self._follow.get(area_id)
        if follow is None:
            return
        lock = self._locks.setdefault(area_id, asyncio.Lock())
        async with lock:
            try:
                await self._replan(area_id, track, follow)
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception("Music replan failed for %s", area_id)
            self._notify()

    async def _replan(self, area_id: str, track: TrackInfo, follow: _Follow) -> None:
        lights = _area_lights(self.hass, area_id, self._settings)
        if not lights:
            return
        last_text = self._last_text.get(area_id, "")
        uri = track.uri or ""
        cache_key = (uri, last_text, self._settings.llm_provider)
        raw = self._plan_cache.get(cache_key)
        profile = self._profiles.get(uri)

        if raw is None:
            cover, bpm = await asyncio.gather(
                self._music.async_cover_palette(track),
                self._music.async_bpm(track),
                return_exceptions=True,
            )
            cover = () if isinstance(cover, BaseException) else cover
            bpm = None if isinstance(bpm, BaseException) else bpm
            if not self._budget.try_spend():
                follow.error = "rate_limited"
                return
            previous = self._last_plan.get(area_id)
            instructions = build_music_instructions(
                area_name=_area_name(self.hass, area_id),
                lights=lights,
                settings=self._settings,
                last_text=last_text,
                language=None,
                track=track,
                profile=profile,
                bpm=bpm,
                cover_palette=cover,
                current_plan=previous.as_dict() if previous else None,
                need_profile=profile is None,
                media=self._media(area_id),
            )
            try:
                raw = await self._generate(
                    TASK_MUSIC, instructions, plan_structure(with_profile=profile is None)
                )
            except LLMError as err:
                follow.error = err.code
                return
            if profile is None:
                features = getattr(self._music, "audio_features", lambda _t: None)(track)
                profile = self._profile_from(raw, bpm, cover, features)
                self._profiles.put(uri, profile)
            self._plan_cache[cache_key] = raw
            while len(self._plan_cache) > PLAN_CACHE_SIZE:
                self._plan_cache.popitem(last=False)
        follow.profile = profile
        follow.error = None

        try:
            plan = validate_plan(normalize_raw_plan(raw), lights, self._settings)
        except PlanValidationError as err:
            _LOGGER.warning("Rejected music plan for %s: %s", area_id, err)
            follow.error = "invalid_plan"
            return
        chosen = plan.chosen(lights)
        if plan.action != "apply" or not chosen or self._follow.get(area_id) is not follow:
            return
        plan = dataclasses.replace(plan, follow_music=True)
        try:
            await self._engine.async_apply(area_id, plan, chosen, source="music")
        except EffectBlockedError as err:
            _LOGGER.debug("Music replan skipped, %s blocks effects", err.entity_id)
            return
        self._last_plan[area_id] = plan

    @staticmethod
    def _profile_from(
        raw: dict[str, Any],
        bpm: tuple[float, str] | None,
        cover: Any,
        features: dict[str, float] | None = None,
    ) -> MusicProfile:
        energy = raw.get("music_energy")
        energy_i = (
            max(1, min(5, round(energy)))
            if isinstance(energy, (int, float)) and not isinstance(energy, bool)
            else 3
        )
        if features and "energy" in features:  # measured beats the LLM estimate
            parts = [features["energy"], features.get("danceability", features["energy"])]
            energy_i = max(1, min(5, round(1 + 4 * (0.7 * parts[0] + 0.3 * parts[1]))))
        tempo = raw.get("music_tempo_class")
        return MusicProfile(
            genre=str(raw.get("music_genre") or "")[:60],
            mood=str(raw.get("music_mood") or "")[:60],
            energy=energy_i,
            tempo_class=tempo if tempo in TEMPO_CLASSES else "medium",
            bpm=bpm[0] if bpm else None,
            bpm_source=bpm[1] if bpm else None,
            cover_palette=tuple(tuple(c) for c in cover),  # type: ignore[misc]
        )

    # -- status ----------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        follow: dict[str, Any] = {}
        for area_id, state in self._follow.items():
            track = state.track
            profile = state.profile
            follow[area_id] = {
                "track": (
                    {
                        "title": track.title,
                        "artist": track.artist,
                        "album": track.album,
                        "uri": track.uri,
                        "image_url": track.image_url,
                        "is_playing": track.is_playing,
                    }
                    if track
                    else None
                ),
                "profile": (
                    {
                        "genre": profile.genre,
                        "mood": profile.mood,
                        "energy": profile.energy,
                        "tempo_class": profile.tempo_class,
                        "bpm": profile.bpm,
                        "bpm_source": profile.bpm_source,
                    }
                    if profile
                    else None
                ),
                "error": state.error,
            }
        return {
            "ai": {"used": self._budget.used_last_hour, "limit": self._budget.limit},
            "follow": follow,
        }
