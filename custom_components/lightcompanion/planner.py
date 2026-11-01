"""Chat + music-follow orchestration: LLM call -> validation -> engine."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .llm import LLMClient, LLMError, create_client
from .music import MusicProfile, ProfileCache, TrackInfo
from .plan import LightPlan, PlanValidationError, normalize_raw_plan, validate_plan
from .prompt import (
    TASK_CHAT,
    TASK_MUSIC,
    build_chat_instructions,
    build_music_instructions,
    plan_structure,
)

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

_REPLIES: dict[str, dict[str, str]] = {
    "rate_limited": {
        "en": "I have used up my AI calls for this hour. The current lights stay as they are.",
        "de": "Mein KI-Kontingent für diese Stunde ist aufgebraucht. Das aktuelle Licht bleibt, wie es ist.",
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
}


def _msg(key: str, language: str | None, **kwargs: str) -> str:
    table = _REPLIES[key]
    lang = (language or "en").lower()[:2]
    return table.get(lang, table["en"]).format(**kwargs)


def _area_lights(hass: HomeAssistant, area_id: str, settings: Settings) -> list[LightInfo]:
    from .lights import async_area_lights  # noqa: PLC0415

    return async_area_lights(hass, area_id, settings)


def _area_name(hass: HomeAssistant, area_id: str) -> str:
    try:
        from homeassistant.helpers import area_registry as ar  # noqa: PLC0415

        area = ar.async_get(hass).async_get_area(area_id)
        return area.name if area else area_id
    except Exception:  # noqa: BLE001
        return area_id


def _friendly_name(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    name = state.attributes.get("friendly_name") if state else None
    return str(name) if name else entity_id


@dataclass(frozen=True, slots=True)
class ChatResult:
    reply: str
    applied: bool
    plan: dict[str, Any] | None
    error: str | None


@dataclass(slots=True)
class _Follow:
    unsub: Callable[[], None]
    track: TrackInfo | None = None
    last_uri: str | None = None
    error: str | None = None
    profile: MusicProfile | None = None
    task: asyncio.Task | None = None


class Planner:
    def __init__(
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
            except Exception:  # noqa: BLE001
                _LOGGER.debug("planner listener failed", exc_info=True)

    # -- chat ------------------------------------------------------------------

    async def async_chat(self, area_id: str, text: str, language: str | None) -> ChatResult:
        lights = _area_lights(self.hass, area_id, self._settings)
        if not lights:
            return ChatResult(_msg("no_lights", language), False, None, "no_lights")
        if not self._budget.try_spend():
            self._notify()
            return ChatResult(_msg("rate_limited", language), False, None, "rate_limited")

        track = self._music.track(area_id)
        instructions = build_chat_instructions(
            area_name=_area_name(self.hass, area_id),
            lights=lights,
            settings=self._settings,
            text=text,
            language=language,
            track=track,
            current_plan=self._last_plan[area_id].as_dict() if area_id in self._last_plan else None,
        )
        try:
            raw = await self._generate(TASK_CHAT, instructions, plan_structure())
        except LLMError as err:
            return ChatResult(_msg("llm", language, code=err.code), False, None, err.code)
        self._notify()
        try:
            plan = validate_plan(normalize_raw_plan(raw), lights, self._settings)
        except PlanValidationError as err:
            _LOGGER.warning("Rejected LLM plan for %s: %s", area_id, err)
            return ChatResult(_msg("invalid_plan", language), False, None, "invalid_plan")

        result = await self._execute(area_id, plan, lights, source="chat", language=language)
        if result.error is None:
            self._last_text[area_id] = text
        if result.applied and plan.action == "apply":
            self._last_plan[area_id] = plan
            if plan.follow_music:
                self._follow_area(area_id)
            else:
                self._unfollow(area_id)
        elif plan.action == "stop" and result.applied:
            self._last_plan.pop(area_id, None)
            self._unfollow(area_id)
        self._notify()
        return result

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
        chosen = [light for light in lights if not plan.targets or light.entity_id in plan.targets]
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
            try:
                self._client = create_client(self.hass, self._settings)
            except LLMError:
                raise
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
            except Exception:  # noqa: BLE001 - background task must not crash HA
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
            )
            try:
                raw = await self._generate(
                    TASK_MUSIC, instructions, plan_structure(with_profile=profile is None)
                )
            except LLMError as err:
                follow.error = err.code
                return
            if profile is None:
                profile = self._profile_from(raw, bpm, cover)
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
        if plan.action != "apply" or self._follow.get(area_id) is not follow:
            return
        plan = dataclasses.replace(plan, follow_music=True)
        chosen = [light for light in lights if not plan.targets or light.entity_id in plan.targets]
        try:
            await self._engine.async_apply(area_id, plan, chosen, source="music")
        except EffectBlockedError as err:
            _LOGGER.debug("Music replan skipped, %s blocks effects", err.entity_id)
            return
        self._last_plan[area_id] = plan

    @staticmethod
    def _profile_from(
        raw: dict[str, Any], bpm: tuple[float, str] | None, cover: Any
    ) -> MusicProfile:
        energy = raw.get("music_energy")
        energy_i = (
            max(1, min(5, round(energy)))
            if isinstance(energy, (int, float)) and not isinstance(energy, bool)
            else 3
        )
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
