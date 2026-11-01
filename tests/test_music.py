"""MusicService: track parsing, palette, BPM registry, envelope, cache."""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from ai_helpers import FakeHass, FakeState, imp, make_settings  # noqa: E402

music = imp("music")


def run(coro):
    return asyncio.run(coro)


def playing_state(**attrs):
    base = {
        "media_title": "Song",
        "media_artist": "Artist",
        "media_album_name": "Album",
        "media_duration": 200,
        "media_position": 10,
        "entity_picture": "/api/media_player_proxy/x",
        "media_content_id": "spotify://track/abc",
    }
    base.update(attrs)
    return FakeState("playing", base)


def test_track_from_state_full():
    t = music.track_from_state("media_player.k", playing_state())
    assert (t.title, t.artist, t.album, t.uri) == ("Song", "Artist", "Album", "spotify://track/abc")
    assert t.duration_s == 200.0 and t.is_playing and t.image_url.startswith("/api")


def test_track_position_advances_while_playing():
    updated = datetime(2026, 1, 1, tzinfo=UTC)
    st = playing_state(media_position_updated_at=updated)
    t = music.track_from_state("media_player.k", st, now=updated.timestamp() + 5)
    assert t.position_s == 15.0


@pytest.mark.parametrize(
    "state", [None, FakeState("off"), FakeState("unavailable"), FakeState("idle", {})]
)
def test_track_none_when_nothing_loaded(state):
    assert music.track_from_state("media_player.k", state) is None


def test_track_tolerates_garbage_attributes():
    t = music.track_from_state(
        "media_player.k",
        FakeState("paused", {"media_title": "T", "media_duration": "x", "media_artist": 5}),
    )
    assert t.duration_s is None and t.artist is None and not t.is_playing


def test_pick_palette_prefers_vivid_dedups_and_limits():
    counted = [
        (500, (10, 10, 10)),
        (400, (200, 30, 30)),
        (390, (205, 35, 32)),  # near duplicate
        (300, (30, 30, 200)),
        (200, (128, 128, 128)),
        (100, (30, 200, 30)),
        (90, (220, 200, 20)),
        (80, (200, 20, 200)),
        (70, (20, 200, 200)),
    ]
    pal = music.pick_palette(counted, 5)
    assert len(pal) == 5
    assert pal[0] == (200, 30, 30)
    assert (205, 35, 32) not in pal
    assert (10, 10, 10) not in pal


def test_pick_palette_falls_back_to_dark_when_nothing_else():
    assert music.pick_palette([(10, (5, 5, 5))]) == ((5, 5, 5),)
    assert music.pick_palette([]) == ()


def test_dominant_colors_degrades_without_pillow_or_with_garbage():
    assert music.dominant_colors(b"not an image") == ()


def test_dominant_colors_real_image():
    pytest.importorskip("PIL")
    import io

    from PIL import Image

    img = Image.new("RGB", (40, 40), (220, 20, 20))
    for x in range(20):
        for y in range(40):
            img.putpixel((x, y), (20, 20, 220))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    pal = music.dominant_colors(buf.getvalue())
    assert any(c[0] > 150 for c in pal) and any(c[2] > 150 for c in pal)


# --- helpers ----------------------------------------------------------------------------------


def test_split_uri():
    assert music.split_uri("spotify://track/abc") == ("spotify", "abc")
    assert music.split_uri("library://track/12") == ("library", "12")
    assert music.split_uri("nonsense") is None
    assert music.split_uri(None) is None


def test_normalize_envelope():
    out = music.normalize_envelope([0, 5, 10])
    assert out == [0.0, 0.5, 1.0]
    big = music.normalize_envelope(list(range(1000)))
    assert len(big) == music.ENVELOPE_POINTS and max(big) == 1.0
    assert music.normalize_envelope([]) is None
    assert music.normalize_envelope([3, 3, 3]) is None
    assert music.normalize_envelope("x") is None


@pytest.mark.parametrize(
    "value,expected",
    [(120, 120.0), (39, None), (251, None), ("120", None), (True, None), (None, None), (0, None)],
)
def test_valid_bpm(value, expected):
    assert music.valid_bpm(value) == expected


def test_profile_cache_lru():
    cache = music.ProfileCache(2)
    p = music.MusicProfile("g", "m", 3, "medium", None, None, ())
    cache.put("a", p)
    cache.put("b", p)
    cache.get("a")
    cache.put("c", p)
    assert cache.get("b") is None and cache.get("a") and cache.get("c")
    assert len(cache) == 2


# --- service -------------------------------------------------------------------------------------


def service(**settings):
    hass = FakeHass()
    return music.MusicService(hass, make_settings(**settings)), hass


def test_player_override_wins():
    svc, _ = service(player_overrides={"room": "media_player.mine"})
    assert svc.player_for_area("room") == "media_player.mine"


def test_player_for_area_prefers_playing(monkeypatch):
    svc, hass = service()
    monkeypatch.setattr(
        svc,
        "_ma_players",
        lambda: [
            ("media_player.a", "room"),
            ("media_player.b", "room"),
            ("media_player.c", "other"),
        ],
    )
    hass.states.data["media_player.a"] = FakeState("idle")
    hass.states.data["media_player.b"] = FakeState("playing")
    assert svc.player_for_area("room") == "media_player.b"
    assert svc.player_for_area("nowhere") is None


def test_track_for_area(monkeypatch):
    svc, hass = service()
    monkeypatch.setattr(svc, "_ma_players", lambda: [("media_player.a", "room")])
    hass.states.data["media_player.a"] = playing_state()
    assert svc.track("room").title == "Song"
    assert svc.track("none") is None


def make_track(**kw):
    base = dict(
        player_entity_id="media_player.a",
        uri="spotify://track/abc",
        title="Song",
        artist="Artist",
        album=None,
        duration_s=1.0,
        position_s=0.0,
        image_url=None,
        is_playing=True,
    )
    base.update(kw)
    return music.TrackInfo(**base)


@pytest.fixture
def clean_sources():
    saved = list(music._BPM_SOURCES)
    yield
    music._BPM_SOURCES[:] = saved


def test_default_bpm_sources_order():
    assert music.bpm_source_names()[:3] == ["music_assistant", "reccobeats", "deezer"]


def test_bpm_first_valid_source_wins_and_failures_are_skipped(clean_sources):
    async def boom(svc, t):
        raise RuntimeError("down")

    async def none(svc, t):
        return None

    async def good(svc, t):
        return 128

    music._BPM_SOURCES[:] = []
    music.register_bpm_source("a", boom)
    music.register_bpm_source("b", none)
    music.register_bpm_source("c", good)
    svc, _ = service()
    assert run(svc.async_bpm(make_track())) == (128.0, "c")


def test_bpm_none_when_all_fail_and_never_guessed(clean_sources):
    music._BPM_SOURCES[:] = []
    svc, _ = service()
    assert run(svc.async_bpm(make_track())) is None


def test_register_replaces_same_name_and_first(clean_sources):
    async def s(svc, t):
        return 100

    music.register_bpm_source("x", s, first=True)
    music.register_bpm_source("x", s)
    assert music.bpm_source_names().count("x") == 1


def test_ma_bpm_reads_attribute():
    svc, hass = service()
    hass.states.data["media_player.a"] = playing_state(bpm=140)
    assert run(music._ma_bpm(svc, make_track())) == 140.0


def test_ma_bpm_none_without_client():
    svc, hass = service()
    hass.states.data["media_player.a"] = playing_state()
    hass.config_entries = type("C", (), {"async_entries": lambda self, d: []})()
    assert run(music._ma_bpm(svc, make_track())) is None


class FakeMass:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    async def send_command(self, command, **args):
        self.calls.append((command, args))
        if self.error:
            raise self.error
        return self.result


def with_mass(svc, hass, mass):
    entry = type("E", (), {"runtime_data": type("R", (), {"mass": mass})()})()
    hass.config_entries = type("C", (), {"async_entries": lambda self, d: [entry]})()


class RoutedMass:
    """MA stand-in routing commands to canned answers."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []
        self.player_queues = None

    async def send_command(self, command, **args):
        self.calls.append((command, args))
        return self.answers.get(command)


RAW = {
    "audio_metadata": {"bpm": 99},
    "external_ids": [["isrc", "usabc1234567"], ["musicbrainz", "x"]],
}


def test_ma_bpm_via_item_by_uri_and_isrc():
    svc, hass = service()
    hass.states.data["media_player.a"] = playing_state()
    mass = RoutedMass(
        {"music/item_by_uri": {"item_id": "42", "provider": "qobuz"}, "music/tracks/get": RAW}
    )
    with_mass(svc, hass, mass)
    assert run(music._ma_bpm(svc, make_track())) == 99.0
    assert mass.calls[1] == (
        "music/tracks/get",
        {"item_id": "42", "provider_instance_id_or_domain": "qobuz"},
    )
    assert svc.isrc_cache["spotify://track/abc"] == "USABC1234567"


def test_ma_bpm_via_active_queue():
    svc, hass = service()
    hass.states.data["media_player.a"] = playing_state(active_queue="q1")
    mass = RoutedMass({"music/tracks/get": RAW})
    media = type("M", (), {"item_id": "7", "provider": "spotify"})()
    queue = type("Q", (), {"current_item": type("I", (), {"media_item": media})()})()
    mass.player_queues = type("PQ", (), {"get": lambda self, qid: queue if qid == "q1" else None})()
    with_mass(svc, hass, mass)
    assert run(music._ma_bpm(svc, make_track())) == 99.0
    assert [c[0] for c in mass.calls] == ["music/tracks/get"]


def test_ma_not_loaded_entry_is_ignored():
    svc, hass = service()
    entry = type(
        "E",
        (),
        {
            "state": type("S", (), {"value": "setup_error"})(),
            "runtime_data": type("R", (), {"mass": FakeMass({})})(),
        },
    )()
    hass.config_entries = type("C", (), {"async_entries": lambda self, d: [entry]})()
    assert svc._mass() is None


def test_ma_missing_bpm_schedules_repoll_and_fills_cache(monkeypatch):
    monkeypatch.setattr(music, "REPOLL_INTERVAL_S", 0)

    async def go():
        svc, hass = service()
        hass.states.data["media_player.a"] = playing_state()
        answers = {
            "music/item_by_uri": {"item_id": "1", "provider": "p"},
            "music/tracks/get": {"audio_metadata": {}},
        }
        mass = RoutedMass(answers)
        with_mass(svc, hass, mass)
        t = make_track()
        assert await music._ma_bpm(svc, t) is None
        answers["music/tracks/get"] = {"audio_metadata": {"bpm": 150}}
        await asyncio.gather(*hass.tasks)
        return await svc.async_bpm(t)

    assert run(go()) == (150.0, "music_assistant")


def test_reccobeats_tempo_features_and_backoff():
    svc, hass = deezer(
        None, DeezerResp(200, {"content": [{"tempo": 128.0, "energy": 0.9, "danceability": 0.7}]})
    )
    svc.isrc_cache["spotify://track/abc"] = "USABC1234567"
    t = make_track()
    assert run(music._reccobeats_bpm(svc, t)) == 128.0
    assert svc.audio_features(t) == {"energy": 0.9, "danceability": 0.7}
    assert hass.session.calls[0][1]["params"] == {"ids": "USABC1234567"}
    # HTTP 429 -> back off for an hour
    svc2, hass2 = deezer(None, DeezerResp(429, {}))
    svc2.isrc_cache["spotify://track/abc"] = "X"
    assert run(music._reccobeats_bpm(svc2, t)) is None
    assert svc2.reccobeats_blocked_until > 0
    assert run(music._reccobeats_bpm(svc2, t)) is None
    assert len(hass2.session.calls) == 1  # second call skipped


def test_reccobeats_needs_isrc_and_ignores_bad_features():
    svc, hass = deezer(None, DeezerResp(200, {"content": [{"tempo": 0, "energy": 7}]}))
    assert run(music._reccobeats_bpm(svc, make_track())) is None
    assert hass.session.calls == []
    svc.isrc_cache["spotify://track/abc"] = "X"
    assert run(music._reccobeats_bpm(svc, make_track())) is None
    assert svc.audio_features(make_track()) is None


def test_deezer_isrc_lookup_first():
    svc, hass = deezer(None, DeezerResp(200, {"bpm": 110}))
    svc.isrc_cache["spotify://track/abc"] = "USABC1234567"
    assert run(music._deezer_bpm(svc, make_track())) == 110.0
    assert hass.session.calls[0][0].endswith("isrc:USABC1234567")


def test_bpm_cache_and_negative_cache(clean_sources):
    calls = []

    async def src(svc, t):
        calls.append(1)
        return None if t.title == "Nope" else 128

    music._BPM_SOURCES[:] = []
    music.register_bpm_source("s", src)
    svc, _ = service()
    assert run(svc.async_bpm(make_track())) == (128.0, "s")
    assert run(svc.async_bpm(make_track())) == (128.0, "s")
    assert len(calls) == 1
    nope = make_track(uri="x://track/9", title="Nope")
    assert run(svc.async_bpm(nope)) is None
    assert run(svc.async_bpm(nope)) is None
    assert len(calls) == 2  # negative cache


def test_energy_envelope_command_and_args():
    svc, hass = service()
    mass = FakeMass([1, 9, 5, 5])
    with_mass(svc, hass, mass)
    out = run(svc.async_energy_envelope(make_track()))
    assert out is not None and max(out) == 1.0
    assert mass.calls[0] == ("audio_analysis/wave_form", {"item_id": "abc", "provider": "spotify"})


def test_energy_envelope_none_cases():
    svc, hass = service()
    hass.config_entries = type("C", (), {"async_entries": lambda self, d: []})()
    assert run(svc.async_energy_envelope(make_track())) is None  # no MA client
    with_mass(svc, hass, FakeMass(error=RuntimeError("no such command")))
    assert run(svc.async_energy_envelope(make_track())) is None
    with_mass(svc, hass, object())  # client without send_command
    assert run(svc.async_energy_envelope(make_track())) is None
    with_mass(svc, hass, FakeMass([1, 2]))
    assert run(svc.async_energy_envelope(make_track(uri=None))) is None


# --- Deezer ---------------------------------------------------------------------------------------------


class DeezerResp:
    def __init__(self, status, body):
        self.status, self._body = status, body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self, content_type=None):
        return self._body


class DeezerSession:
    def __init__(self, search, detail):
        self.search, self.detail, self.calls = search, detail, []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        return self.search if "search" in url else self.detail


def deezer(search, detail):
    svc, hass = service()
    hass.session = DeezerSession(search, detail)
    return svc, hass


def test_deezer_bpm_happy_path():
    svc, hass = deezer(
        DeezerResp(200, {"data": [{"id": 7, "title": "Song (Remastered)"}]}),
        DeezerResp(200, {"bpm": 123.4}),
    )
    assert run(music._deezer_bpm(svc, make_track())) == 123.4
    assert hass.session.calls[0][1]["params"]["q"] == 'artist:"Artist" track:"Song"'
    assert hass.session.calls[1][0].endswith("/track/7")


def test_deezer_zero_bpm_is_none():
    svc, _ = deezer(
        DeezerResp(200, {"data": [{"id": 7, "title": "Song"}]}), DeezerResp(200, {"bpm": 0})
    )
    assert run(music._deezer_bpm(svc, make_track())) is None


def test_deezer_rejects_unrelated_title():
    svc, _ = deezer(
        DeezerResp(200, {"data": [{"id": 7, "title": "Totally Different"}]}),
        DeezerResp(200, {"bpm": 120}),
    )
    assert run(music._deezer_bpm(svc, make_track())) is None


def test_deezer_http_error_and_missing_metadata():
    svc, _ = deezer(DeezerResp(500, {}), DeezerResp(200, {}))
    assert run(music._deezer_bpm(svc, make_track())) is None
    assert run(music._deezer_bpm(svc, make_track(artist=None))) is None


def test_cover_palette_without_image_or_pillow():
    svc, _ = service()
    assert run(svc.async_cover_palette(make_track(image_url=None))) == ()
