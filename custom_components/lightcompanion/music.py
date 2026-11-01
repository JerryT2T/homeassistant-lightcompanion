"""Read-only Music Assistant context: current track, cover palette, BPM, energy.

Music Assistant is a prerequisite, never controlled: no media_player or
music_assistant *control* service is ever called from here.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import CALLBACK_TYPE, HomeAssistant

    from .settings import Settings

_LOGGER = logging.getLogger(__name__)

MA_PLATFORM = "music_assistant"
MAX_IMAGE_BYTES = 5_000_000
HTTP_TIMEOUT_S = 8
MA_COMMAND_TIMEOUT_S = 5
PROFILE_CACHE_SIZE = 500
BPM_MIN, BPM_MAX = 40.0, 250.0
ENVELOPE_POINTS = 256
DEEZER_SEARCH = "https://api.deezer.com/search"
DEEZER_TRACK = "https://api.deezer.com/track/{id}"
DEEZER_ISRC = "https://api.deezer.com/track/isrc:{isrc}"
RECCOBEATS_URL = "https://api.reccobeats.com/v1/audio-features"
BACKOFF_S = 3600.0
NEGATIVE_TTL_S = 600.0
BPM_CACHE_SIZE = 500
REPOLL_INTERVAL_S = 10
REPOLL_ATTEMPTS = 3

Color = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class TrackInfo:
    player_entity_id: str
    uri: str | None
    title: str | None
    artist: str | None
    album: str | None
    duration_s: float | None
    position_s: float | None
    image_url: str | None
    is_playing: bool


@dataclass(frozen=True, slots=True)
class MusicProfile:
    genre: str
    mood: str
    energy: int
    tempo_class: str
    bpm: float | None
    bpm_source: str | None
    cover_palette: tuple[Color, ...]
    estimated: bool = True


class ProfileCache:
    """Small LRU of music profiles keyed by track uri."""

    def __init__(self, size: int = PROFILE_CACHE_SIZE) -> None:
        self._size = size
        self._data: OrderedDict[str, MusicProfile] = OrderedDict()

    def get(self, uri: str) -> MusicProfile | None:
        profile = self._data.get(uri)
        if profile is not None:
            self._data.move_to_end(uri)
        return profile

    def put(self, uri: str, profile: MusicProfile) -> None:
        self._data[uri] = profile
        self._data.move_to_end(uri)
        while len(self._data) > self._size:
            self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def track_from_state(entity_id: str, state: Any, now: float | None = None) -> TrackInfo | None:
    """TrackInfo from a media_player state object; None if nothing is loaded."""
    if state is None or state.state in ("unavailable", "unknown", "off"):
        return None
    attrs = state.attributes
    title, uri = _str(attrs.get("media_title")), _str(attrs.get("media_content_id"))
    if title is None and uri is None:
        return None
    playing = state.state == "playing"
    position = _float(attrs.get("media_position"))
    updated = attrs.get("media_position_updated_at")
    if position is not None and playing and updated is not None and hasattr(updated, "timestamp"):
        elapsed = (now if now is not None else time.time()) - updated.timestamp()
        position += max(0.0, elapsed)
    return TrackInfo(
        player_entity_id=entity_id,
        uri=uri,
        title=title,
        artist=_str(attrs.get("media_artist")),
        album=_str(attrs.get("media_album_name")),
        duration_s=_float(attrs.get("media_duration")),
        position_s=position,
        image_url=_str(attrs.get("entity_picture")),
        is_playing=playing,
    )


def pick_palette(counted: list[tuple[int, Color]], limit: int = 5) -> tuple[Color, ...]:
    """Dominant, distinct, usable colors from ``(pixel_count, rgb)`` pairs.

    Very dark colors and greys are dropped while enough vivid ones remain;
    near-duplicates are merged.
    """
    ordered = [c for _, c in sorted(counted, key=lambda p: -p[0])]

    def vivid(c: Color) -> bool:
        return max(c) >= 60 and max(c) - min(c) >= 25  # noqa: PLR2004

    def usable(c: Color) -> bool:
        return max(c) >= 40  # noqa: PLR2004

    chosen: list[Color] = []
    for pool in (
        [c for c in ordered if vivid(c)],
        [c for c in ordered if usable(c) and not vivid(c)],
        [c for c in ordered if not usable(c)],
    ):
        for color in pool:
            if len(chosen) >= limit:
                break
            if all(
                sum((a - b) ** 2 for a, b in zip(color, o, strict=True)) > 50**2 for o in chosen
            ):
                chosen.append(color)
    return tuple(chosen[:limit])


def dominant_colors(data: bytes, limit: int = 5) -> tuple[Color, ...]:
    """Up to ``limit`` dominant colors of an image (Pillow, imported lazily)."""
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        _LOGGER.debug("Pillow not available, no cover palette")
        return ()
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            img.thumbnail((64, 64))
            quant = img.quantize(colors=10)
            palette = quant.getpalette() or []
            counts = quant.getcolors() or []
        counted = [(n, (palette[i * 3], palette[i * 3 + 1], palette[i * 3 + 2])) for n, i in counts]
        return pick_palette(counted, limit)
    except Exception:  # noqa: BLE001 - broken image must never break a chat
        _LOGGER.debug("Cover image could not be decoded", exc_info=True)
        return ()


def normalize_envelope(values: Any) -> list[float] | None:
    """0..1 floats, at most ENVELOPE_POINTS long; None if unusable."""
    if not isinstance(values, (list, tuple)) or not values:
        return None
    nums = [float(v) for v in values if _float(v) is not None]
    if not nums:
        return None
    if len(nums) > ENVELOPE_POINTS:
        step = len(nums) / ENVELOPE_POINTS
        nums = [
            max(nums[int(i * step) : max(int(i * step) + 1, int((i + 1) * step))])
            for i in range(ENVELOPE_POINTS)
        ]
    lo, hi = min(nums), max(nums)
    if hi - lo < 1e-9:  # noqa: PLR2004
        return None
    return [(v - lo) / (hi - lo) for v in nums]


def split_uri(uri: str | None) -> tuple[str, str] | None:
    """Music Assistant uri ``provider://type/item_id`` -> (provider, item_id)."""
    if not uri or "://" not in uri:
        return None
    provider, rest = uri.split("://", 1)
    item_id = rest.rsplit("/", 1)[-1]
    if not provider or not item_id:
        return None
    return provider, item_id


def valid_bpm(value: Any) -> float | None:
    number = _float(value)
    if number is None or not BPM_MIN <= number <= BPM_MAX:
        return None
    return round(number, 1)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _find_bpm(data: Any, depth: int = 0) -> float | None:
    """Look for a bpm/tempo number in a (nested) MA item dict."""
    if depth > 3 or not isinstance(data, dict):  # noqa: PLR2004
        return None
    for key, value in data.items():
        if isinstance(key, str) and key.lower() in ("bpm", "tempo"):
            found = valid_bpm(value)
            if found:
                return found
    for key in ("metadata", "extra_attributes", "audio_format"):
        found = _find_bpm(data.get(key), depth + 1)
        if found:
            return found
    return None


# ---------------------------------------------------------------------------
# BPM source registry
# ---------------------------------------------------------------------------

BpmSource = Callable[["MusicService", TrackInfo], Awaitable[float | None]]
_BPM_SOURCES: list[tuple[str, BpmSource]] = []


def register_bpm_source(name: str, source: BpmSource, *, first: bool = False) -> None:
    """Add a measured-BPM source (replaces one with the same name). Never LLM-guess."""
    _BPM_SOURCES[:] = [s for s in _BPM_SOURCES if s[0] != name]
    if first:
        _BPM_SOURCES.insert(0, (name, source))
    else:
        _BPM_SOURCES.append((name, source))


def bpm_source_names() -> list[str]:
    return [name for name, _ in _BPM_SOURCES]


def _isrc_from(raw: Any) -> str | None:
    """ISRC out of MA ``external_ids``: list of ``[type, value]`` pairs."""
    ids = raw.get("external_ids") if isinstance(raw, dict) else None
    for pair in ids or []:
        if isinstance(pair, (list, tuple)) and len(pair) == 2 and str(pair[0]).lower() == "isrc":  # noqa: PLR2004
            value = str(pair[1]).strip().upper()
            if value:
                return value
    return None


def _bpm_from_raw(raw: Any) -> float | None:
    """``raw["audio_metadata"]["bpm"]`` (raw dict, independent of the models version)."""
    meta = raw.get("audio_metadata") if isinstance(raw, dict) else None
    found = valid_bpm(meta.get("bpm")) if isinstance(meta, dict) else None
    return found or (_find_bpm(raw) if isinstance(raw, dict) else None)


async def _ma_bpm(service: MusicService, track: TrackInfo) -> float | None:
    """Music Assistant analyses played tracks; bpm may be empty on first play."""
    state = service.hass.states.get(track.player_entity_id)
    if state is not None:
        found = _find_bpm(dict(state.attributes))
        if found:
            return found
    raw = await service.async_ma_track(track)
    if raw is None:
        return None
    isrc = _isrc_from(raw)
    if isrc and track.uri:
        service.isrc_cache[track.uri] = isrc
    found = _bpm_from_raw(raw)
    if found is None:
        service.schedule_ma_repoll(track)
    return found


async def _reccobeats_bpm(service: MusicService, track: TrackInfo) -> float | None:
    isrc = service.isrc_cache.get(track.uri or "")
    if not isrc or time.monotonic() < service.reccobeats_blocked_until:
        return None
    import aiohttp  # noqa: PLC0415
    from homeassistant.helpers.aiohttp_client import async_get_clientsession  # noqa: PLC0415

    session = async_get_clientsession(service.hass)
    try:
        async with session.get(
            RECCOBEATS_URL,
            params={"ids": isrc},
            timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_S),
        ) as resp:
            if resp.status != 200:  # noqa: PLR2004
                service.reccobeats_blocked_until = time.monotonic() + BACKOFF_S
                return None
            body = await resp.json(content_type=None)
    except Exception:
        service.reccobeats_blocked_until = time.monotonic() + BACKOFF_S
        raise
    content = body.get("content") if isinstance(body, dict) else body
    item = content[0] if isinstance(content, list) and content else content
    if not isinstance(item, dict):
        return None
    features = {
        key: float(item[key])
        for key in ("energy", "danceability")
        if _float(item.get(key)) is not None and 0 <= item[key] <= 1
    }
    if features:
        service.features[track.uri or ""] = features
    return valid_bpm(item.get("tempo"))


async def _deezer_bpm(service: MusicService, track: TrackInfo) -> float | None:
    import aiohttp  # noqa: PLC0415
    from homeassistant.helpers.aiohttp_client import async_get_clientsession  # noqa: PLC0415

    session = async_get_clientsession(service.hass)
    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_S)
    isrc = service.isrc_cache.get(track.uri or "")
    if isrc:
        async with session.get(DEEZER_ISRC.format(isrc=isrc), timeout=timeout) as resp:
            if resp.status == 200:  # noqa: PLR2004
                detail = await resp.json(content_type=None)
                found = valid_bpm((detail or {}).get("bpm"))
                if found:
                    return found
    if not track.title or not track.artist:
        return None
    query = 'artist:"{}" track:"{}"'.format(
        track.artist.replace('"', " "), track.title.replace('"', " ")
    )
    async with session.get(DEEZER_SEARCH, params={"q": query, "limit": 3}, timeout=timeout) as resp:
        if resp.status != 200:  # noqa: PLR2004
            return None
        found_items = await resp.json(content_type=None)
    wanted = _norm(track.title)
    track_id = None
    for item in (found_items or {}).get("data", []) or []:
        title = _norm(str(item.get("title", "")))
        if title and (wanted in title or title in wanted):
            track_id = item.get("id")
            break
    if track_id is None:
        return None
    async with session.get(DEEZER_TRACK.format(id=track_id), timeout=timeout) as resp:
        if resp.status != 200:  # noqa: PLR2004
            return None
        detail = await resp.json(content_type=None)
    return valid_bpm((detail or {}).get("bpm"))


# Order matters: measured by Music Assistant first, then ISRC based public APIs.
register_bpm_source("music_assistant", _ma_bpm)
register_bpm_source("reccobeats", _reccobeats_bpm)
register_bpm_source("deezer", _deezer_bpm)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class MusicService:
    """Reads track context of Music Assistant players; never controls them."""

    def __init__(self, hass: HomeAssistant, settings: Settings) -> None:
        self.hass = hass
        self._settings = settings
        self.isrc_cache: dict[str, str] = {}
        self.features: dict[str, dict[str, float]] = {}
        self.reccobeats_blocked_until = 0.0
        self._bpm_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._bpm_negative: dict[str, float] = {}
        self._repolls: dict[str, Any] = {}

    # -- players -----------------------------------------------------------

    def _ma_players(self) -> list[tuple[str, str | None]]:
        """``(entity_id, area_id)`` of all Music Assistant media players."""
        from homeassistant.helpers import (  # noqa: PLC0415
            device_registry as dr,
        )
        from homeassistant.helpers import (
            entity_registry as er,
        )

        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)
        players: list[tuple[str, str | None]] = []
        for entry in ent_reg.entities.values():
            if entry.platform != MA_PLATFORM or entry.domain != "media_player":
                continue
            if entry.disabled_by or entry.hidden_by:
                continue
            area = entry.area_id
            if area is None and entry.device_id:
                device = dev_reg.async_get(entry.device_id)
                area = device.area_id if device else None
            players.append((entry.entity_id, area))
        return players

    def player_for_area(self, area_id: str) -> str | None:
        override = self._settings.player_overrides.get(area_id)
        if override:
            return override
        candidates = [eid for eid, area in self._ma_players() if area == area_id]
        if not candidates:
            return None

        def rank(entity_id: str) -> int:
            state = self.hass.states.get(entity_id)
            return {"playing": 0, "paused": 1, "buffering": 1}.get(state.state if state else "", 2)

        return sorted(candidates, key=lambda e: (rank(e), e))[0]

    def track(self, area_id: str) -> TrackInfo | None:
        player = self.player_for_area(area_id)
        if player is None:
            return None
        return track_from_state(player, self.hass.states.get(player))

    # -- cover palette -----------------------------------------------------

    def _absolute_url(self, image_url: str) -> str | None:
        if image_url.startswith(("http://", "https://")):
            return image_url
        from homeassistant.helpers.network import NoURLAvailableError, get_url  # noqa: PLC0415

        try:
            base = get_url(self.hass, prefer_external=False, allow_external=True)
        except NoURLAvailableError:
            return None
        return base.rstrip("/") + image_url

    async def async_cover_palette(self, track: TrackInfo) -> tuple[Color, ...]:
        if not track.image_url:
            return ()
        try:
            import PIL  # noqa: F401, PLC0415
        except ImportError:
            return ()
        url = self._absolute_url(track.image_url)
        if url is None:
            return ()
        try:
            import aiohttp  # noqa: PLC0415
            from homeassistant.helpers.aiohttp_client import (  # noqa: PLC0415
                async_get_clientsession,
            )

            session = async_get_clientsession(self.hass)
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_S)
            ) as resp:
                if resp.status != 200:  # noqa: PLR2004
                    return ()
                data = await resp.content.read(MAX_IMAGE_BYTES)
            return await self.hass.async_add_executor_job(dominant_colors, data, 5)
        except Exception:  # noqa: BLE001 - cover art is optional
            _LOGGER.debug("Cover palette unavailable", exc_info=True)
            return ()

    # -- Music Assistant client ----------------------------------------------

    def _mass(self) -> Any | None:
        """MA client of the loaded config entry (not a public API: guard everything)."""
        try:
            for entry in self.hass.config_entries.async_entries(MA_PLATFORM):
                state = getattr(entry, "state", None)
                if state is not None and getattr(state, "value", state) != "loaded":
                    continue
                mass = getattr(getattr(entry, "runtime_data", None), "mass", None)
                if mass is not None:
                    return mass
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Music Assistant client lookup failed", exc_info=True)
        return None

    async def async_ma_command(self, command: str, **args: Any) -> Any | None:
        """Best-effort read-only MA websocket command; None on any problem."""
        mass = self._mass()
        send = getattr(mass, "send_command", None)
        if send is None:
            return None
        try:
            async with asyncio.timeout(MA_COMMAND_TIMEOUT_S):
                return await send(command, **args)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Music Assistant command %s failed", command, exc_info=True)
            return None

    async def async_energy_envelope(self, track: TrackInfo) -> list[float] | None:
        parts = split_uri(track.uri)
        if parts is None:
            return None
        provider, item_id = parts
        result = await self.async_ma_command(
            "audio_analysis/wave_form", item_id=item_id, provider=provider
        )
        if isinstance(result, dict):
            result = result.get("wave_form") or result.get("data")
        return normalize_envelope(result)

    # -- BPM -------------------------------------------------------------------

    async def async_ma_track(self, track: TrackInfo) -> dict[str, Any] | None:
        """Raw MA track dict (``music/tracks/get``) of the playing item, or None."""
        mass = self._mass()
        if mass is None:
            return None
        item_id: Any = None
        provider: Any = None
        try:
            state = self.hass.states.get(track.player_entity_id)
            queue_id = state.attributes.get("active_queue") if state else None
            if queue_id:
                media = mass.player_queues.get(queue_id).current_item.media_item
                item_id, provider = media.item_id, media.provider
        except Exception:  # noqa: BLE001
            _LOGGER.debug("MA queue lookup failed", exc_info=True)
        if not item_id and track.uri:
            found = await self.async_ma_command("music/item_by_uri", uri=track.uri)
            if isinstance(found, dict):
                item_id, provider = found.get("item_id"), found.get("provider")
        if not item_id or not provider:
            return None
        raw = await self.async_ma_command(
            "music/tracks/get", item_id=item_id, provider_instance_id_or_domain=provider
        )
        return raw if isinstance(raw, dict) else None

    def schedule_ma_repoll(self, track: TrackInfo) -> None:
        """MA analyses while playing: re-poll in the background, never block."""
        key = track.uri
        running = self._repolls.get(key)
        if not key or (running is not None and not running.done()):
            return
        self._repolls[key] = self.hass.async_create_task(self._repoll(track, key))

    async def _repoll(self, track: TrackInfo, key: str) -> None:
        try:
            for _ in range(REPOLL_ATTEMPTS):
                await asyncio.sleep(REPOLL_INTERVAL_S)
                bpm = _bpm_from_raw(await self.async_ma_track(track))
                if bpm:
                    self._remember_bpm(key, bpm, "music_assistant")
                    return
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            _LOGGER.debug("MA bpm re-poll failed", exc_info=True)

    @staticmethod
    def _bpm_key(track: TrackInfo) -> str:
        return track.uri or f"{track.artist}|{track.title}"

    def _remember_bpm(self, key: str, bpm: float, source: str) -> None:
        self._bpm_cache[key] = (bpm, source)
        self._bpm_cache.move_to_end(key)
        self._bpm_negative.pop(key, None)
        while len(self._bpm_cache) > BPM_CACHE_SIZE:
            self._bpm_cache.popitem(last=False)

    def audio_features(self, track: TrackInfo) -> dict[str, float] | None:
        """Measured ``energy``/``danceability`` (0..1) when a source delivered them."""
        return self.features.get(track.uri or "")

    async def async_bpm(self, track: TrackInfo) -> tuple[float, str] | None:
        """First measured BPM from the registered sources; never an LLM guess."""
        key = self._bpm_key(track)
        cached = self._bpm_cache.get(key)
        if cached is not None:
            self._bpm_cache.move_to_end(key)
            return cached
        if self._bpm_negative.get(key, 0.0) > time.monotonic():
            return None
        for name, source in list(_BPM_SOURCES):
            try:
                async with asyncio.timeout(HTTP_TIMEOUT_S + 2):
                    value = await source(self, track)
            except Exception:  # noqa: BLE001 - a source may fail, the next may not
                _LOGGER.debug("BPM source %s failed", name, exc_info=True)
                continue
            bpm = valid_bpm(value)
            if bpm:
                self._remember_bpm(key, bpm, name)
                return bpm, name
        self._bpm_negative[key] = time.monotonic() + NEGATIVE_TTL_S
        return None

    # -- listener ----------------------------------------------------------------

    def async_track_listener(
        self, area_id: str, cb: Callable[[TrackInfo | None], None]
    ) -> CALLBACK_TYPE:
        """Call ``cb`` whenever the area player's track or play state changes."""
        player = self.player_for_area(area_id)
        if player is None:
            return lambda: None
        from homeassistant.core import callback  # noqa: PLC0415
        from homeassistant.helpers.event import async_track_state_change_event  # noqa: PLC0415

        last: list[Any] = [object()]

        @callback
        def _changed(event: Any) -> None:
            track = track_from_state(player, event.data.get("new_state"))
            key = (track.uri, track.title, track.artist, track.is_playing) if track else None
            if key == last[0]:
                return
            last[0] = key
            cb(track)

        return async_track_state_change_event(self.hass, [player], _changed)
