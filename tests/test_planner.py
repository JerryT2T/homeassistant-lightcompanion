"""Planner: chat flow, validation gate, budget, music follow."""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from ai_helpers import FakeHass, FakeLight, FakeState, imp, make_settings

planner_mod = imp("planner")
music_mod = imp("music")
llm_base = imp("llm.base")
AiBudget = imp("ai_budget").AiBudget
Planner = planner_mod.Planner
EffectBlockedError = planner_mod.EffectBlockedError
LLMError = llm_base.LLMError

LIGHTS = [FakeLight("light.a"), FakeLight("light.b", effect_list=("Rainbow",))]


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def async_generate(self, *, task_name, instructions, schema):
        self.calls.append((task_name, instructions, schema))
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return dict(item)


class FakeEngine:
    def __init__(self):
        self.applied = []
        self.stopped = []
        self.error = None

    async def async_apply(self, area_id, plan, lights, *, source):
        if self.error:
            raise self.error
        self.applied.append((area_id, plan, [light.entity_id for light in lights], source))

    async def async_stop(self, area_id, *, restore=True):
        self.stopped.append((area_id, restore))


class FakeMusic:
    def __init__(self):
        self.current = None
        self.cb = None
        self.unsubscribed = 0
        self.bpm = (120.0, "deezer")
        self.palette = ((200, 20, 20),)

    def track(self, area_id):
        return self.current

    def async_track_listener(self, area_id, cb):
        self.cb = cb

        def unsub():
            self.unsubscribed += 1

        return unsub

    async def async_cover_palette(self, track):
        return self.palette

    async def async_bpm(self, track):
        return self.bpm


def track(uri="spotify://track/1", playing=True, title="Song"):
    return music_mod.TrackInfo(
        "media_player.k", uri, title, "Artist", None, 100.0, 0.0, None, playing
    )


GOOD = {
    "reply": "Cozy!",
    "action": "apply",
    "palette": [[255, 120, 0]],
    "pattern": "breathe",
    "tempo": "slow",
    "intensity": 2,
    "brightness_pct": 40,
}


def build(*responses, limit=50, **settings):
    hass = FakeHass()
    st = make_settings(**settings)
    client = FakeClient(*(responses or (GOOD,)))
    engine, mus = FakeEngine(), FakeMusic()
    p = Planner(hass, st, AiBudget(limit), engine, mus, client=client)
    return p, hass, client, engine, mus


@pytest.fixture(autouse=True)
def patch_lights(monkeypatch):
    monkeypatch.setattr(planner_mod, "_area_lights", lambda hass, area, st: list(LIGHTS))
    monkeypatch.setattr(planner_mod, "_area_name", lambda hass, area: "Living Room")


def run(coro):
    return asyncio.run(coro)


def test_chat_applies_valid_plan():
    p, _, client, engine, _ = build()
    res = run(p.async_chat("room", "cozy please", "en"))
    assert res.applied and res.error is None and res.reply == "Cozy!"
    assert res.plan["pattern"] == "breathe"
    area, _plan, ids, source = engine.applied[0]
    assert (area, ids, source) == ("room", ["light.a", "light.b"], "chat")
    assert "cozy please" in client.calls[0][1] and "Living Room" in client.calls[0][1]


def test_chat_target_subset_passed_to_engine():
    p, _, _, engine, _ = build({**GOOD, "targets": ["light.b"]})
    run(p.async_chat("room", "x", None))
    assert engine.applied[0][2] == ["light.b"]


@pytest.mark.parametrize(
    "bad",
    [
        {"action": "apply", "palette": [[999, 0, 0]]},
        {"action": "apply"},
        {"action": "explode"},
        {**GOOD, "targets": ["light.ghost"]},
        {**GOOD, "native_effects": {"light.a": "Rainbow"}},
        {**GOOD, "intensity": 11},
    ],
)
def test_invalid_plan_applies_nothing(bad):
    p, _, _, engine, _ = build(bad)
    res = run(p.async_chat("room", "x", "de"))
    assert not res.applied and res.error == "invalid_plan" and res.plan is None
    assert engine.applied == [] and engine.stopped == []
    assert "nichts" in res.reply


def test_strobe_is_capped_without_permission():
    p, _, _, engine, _ = build({**GOOD, "pattern": "strobe", "party": False})
    res = run(p.async_chat("room", "strobe!", "en"))
    plan = engine.applied[0][1]
    assert plan.pattern == "pulse" and plan.strobe_capped
    assert res.plan["strobe_capped"] is True


def test_strobe_allowed_in_party_mode_when_enabled():
    p, _, _, engine, _ = build({**GOOD, "pattern": "strobe", "party": True}, allow_strobe=True)
    run(p.async_chat("room", "party", "en"))
    assert engine.applied[0][1].pattern == "strobe"


def test_rate_limited_keeps_everything_and_skips_llm():
    p, _, client, engine, _ = build(limit=1)
    run(p.async_chat("room", "one", "en"))
    res = run(p.async_chat("room", "two", "de"))
    assert res.error == "rate_limited" and not res.applied
    assert len(client.calls) == 1 and len(engine.applied) == 1
    assert "Kontingent" in res.reply
    assert p.status()["ai"] == {"used": 1, "limit": 1}


@pytest.mark.parametrize(
    "code", ["timeout", "request_failed", "no_answer", "invalid_json", "not_configured"]
)
def test_llm_errors_are_reported(code):
    p, _, _, engine, _ = build(LLMError(code))
    res = run(p.async_chat("room", "x", "en"))
    assert res.error == code and not res.applied and engine.applied == []


def test_no_lights(monkeypatch):
    monkeypatch.setattr(planner_mod, "_area_lights", lambda *a: [])
    p, _, client, _, _ = build()
    res = run(p.async_chat("room", "x", "en"))
    assert res.error == "no_lights" and client.calls == []


def test_action_none_and_stop():
    p, _, _, engine, _ = build({"action": "none", "reply": "It is 3 lights."})
    res = run(p.async_chat("room", "how many?", "en"))
    assert not res.applied and res.error is None and res.reply == "It is 3 lights."
    assert engine.applied == []
    p, _, _, engine, _ = build({"action": "stop", "reply": "Stopped"})
    res = run(p.async_chat("room", "stop", "en"))
    assert res.applied and engine.stopped == [("room", True)]


def test_blocked_effect_reports_friendly_name():
    p, hass, _, engine, _ = build()
    engine.error = EffectBlockedError("light.tv")
    hass.states.data["light.tv"] = FakeState("on", {"friendly_name": "TV Lamp"})
    res = run(p.async_chat("room", "x", "de"))
    assert res.error == "blocked" and not res.applied
    assert res.reply == "Effekte sind gerade pausiert: TV Lamp ist an."
    assert p.status()["follow"] == {}


def test_prompt_mentions_current_track():
    p, _, client, _, mus = build()
    mus.current = track(title="Thunderstruck")
    run(p.async_chat("room", "x", "en"))
    assert "Thunderstruck" in client.calls[0][1]


# --- music follow ---


MUSIC_PLAN = {
    **GOOD,
    "pattern": "wave",
    "follow_music": True,
    "music_genre": "rock",
    "music_mood": "driving",
    "music_energy": 4,
    "music_tempo_class": "fast",
}


async def settle(hass):
    await asyncio.gather(*hass.tasks)


def follow_setup(*extra):
    p, hass, client, engine, mus = build({**GOOD, "follow_music": True}, *extra)
    return p, hass, client, engine, mus


def test_follow_subscribes_and_replans_on_new_track_with_last_instruction():
    async def go():
        p, hass, client, engine, mus = build({**GOOD, "follow_music": True}, MUSIC_PLAN)
        mus.current = track("u1")
        await p.async_chat("room", "aber dunkle Farben", "de")
        assert mus.cb is not None and client.calls[0][0] == planner_mod.TASK_CHAT
        mus.cb(track("u1"))  # same track as at chat time: no replan
        await settle(hass)
        assert len(client.calls) == 1
        mus.cb(track("u2", title="New Song"))
        await settle(hass)
        return p, client, engine

    p, client, engine = run(go())
    assert len(client.calls) == 2
    task, instructions, schema = client.calls[1]
    assert task == planner_mod.TASK_MUSIC
    assert "aber dunkle Farben" in instructions and "New Song" in instructions
    assert "Measured BPM: 120" in instructions and "#c81414" in instructions
    assert "music_genre" in schema
    _area, plan, _, source = engine.applied[-1]
    assert source == "music" and plan.follow_music and plan.pattern == "wave"
    prof = p.status()["follow"]["room"]["profile"]
    assert prof["genre"] == "rock" and prof["bpm"] == 120.0 and prof["bpm_source"] == "deezer"
    assert prof["energy"] == 4


def test_replayed_track_costs_no_llm_call():
    async def go():
        p, hass, client, engine, mus = build({**GOOD, "follow_music": True}, MUSIC_PLAN)
        await p.async_chat("room", "party", "en")
        for uri in ("u1", "u2", "u1"):
            mus.cb(track(uri))
            await settle(hass)
        return client, engine, p

    client, engine, p = run(go())
    assert len(client.calls) == 3  # chat + u1 + u2, replay of u1 served from the plan cache
    assert len([a for a in engine.applied if a[3] == "music"]) == 3
    assert p.status()["ai"]["used"] == 3


def test_second_track_with_known_profile_does_not_ask_for_profile():
    async def go():
        p, hass, client, _engine, mus = build({**GOOD, "follow_music": True}, MUSIC_PLAN)
        await p.async_chat("room", "x", "en")
        mus.cb(track("u1"))
        await settle(hass)
        p._plan_cache.clear()  # force a new call for the same known uri
        mus._ = None
        p._follow["room"].last_uri = None
        mus.cb(track("u1", title="again"))
        await settle(hass)
        return client

    client = run(go())
    assert "music_genre" in client.calls[1][2]
    assert "music_genre" not in client.calls[2][2]
    assert "Known profile: genre=rock" in client.calls[2][1]


def test_budget_exhausted_keeps_plan_and_reports():
    async def go():
        p, hass, client, engine, mus = build({**GOOD, "follow_music": True}, MUSIC_PLAN, limit=1)
        await p.async_chat("room", "x", "en")
        mus.cb(track("u9"))
        await settle(hass)
        return p, client, engine

    p, client, engine = run(go())
    assert len(client.calls) == 1
    assert [a[3] for a in engine.applied] == ["chat"]
    assert p.status()["follow"]["room"]["error"] == "rate_limited"
    assert p.status()["ai"] == {"used": 1, "limit": 1}


def test_invalid_music_plan_keeps_running_plan():
    async def go():
        p, hass, _client, engine, mus = build(
            {**GOOD, "follow_music": True}, {"action": "apply", "palette": [[1, 2]]}
        )
        await p.async_chat("room", "x", "en")
        mus.cb(track("u2"))
        await settle(hass)
        return p, engine

    p, engine = run(go())
    assert [a[3] for a in engine.applied] == ["chat"]
    assert p.status()["follow"]["room"]["error"] == "invalid_plan"


def test_music_llm_error_is_status_only():
    async def go():
        p, hass, client, _engine, mus = build({**GOOD, "follow_music": True}, LLMError("timeout"))
        await p.async_chat("room", "x", "en")
        client.responses = [LLMError("timeout")]
        mus.cb(track("u2"))
        await settle(hass)
        return p

    assert run(go()).status()["follow"]["room"]["error"] == "timeout"


def test_music_replan_blocked_is_skipped_silently():
    async def go():
        p, hass, _client, engine, mus = build({**GOOD, "follow_music": True}, MUSIC_PLAN)
        await p.async_chat("room", "x", "en")
        engine.error = EffectBlockedError("light.tv")
        mus.cb(track("u2"))
        await settle(hass)
        return engine

    assert [a[3] for a in run(go()).applied] == ["chat"]


def test_paused_or_missing_track_does_not_replan():
    async def go():
        p, hass, client, _engine, mus = build({**GOOD, "follow_music": True}, MUSIC_PLAN)
        await p.async_chat("room", "x", "en")
        mus.cb(None)
        mus.cb(track("u3", playing=False))
        await settle(hass)
        return client

    assert len(run(go()).calls) == 1


def test_non_follow_chat_and_stop_unsubscribe():
    async def go():
        p, _hass, _client, _engine, mus = build(
            {**GOOD, "follow_music": True},
            GOOD,
            {**GOOD, "follow_music": True},
            {"action": "stop", "reply": "x"},
        )
        await p.async_chat("room", "follow", "en")
        assert "room" in p.status()["follow"]
        await p.async_chat("room", "just blue", "en")
        assert p.status()["follow"] == {} and mus.unsubscribed == 1
        await p.async_chat("room", "follow", "en")
        assert "room" in p.status()["follow"]
        await p.async_chat("room", "stop", "en")
        return p, mus

    p, mus = run(go())
    assert p.status()["follow"] == {} and mus.unsubscribed == 2


def test_async_stop_unsubscribes_all():
    async def go():
        p, _hass, _client, _engine, mus = build({**GOOD, "follow_music": True})
        await p.async_chat("room", "x", "en")
        await p.async_stop()
        return p, mus

    p, mus = run(go())
    assert mus.unsubscribed == 1 and p.status()["follow"] == {}


def test_status_is_json_serializable():
    import json

    async def go():
        p, hass, _client, _engine, mus = build({**GOOD, "follow_music": True}, MUSIC_PLAN)
        mus.current = track("u1")
        await p.async_chat("room", "x", "en")
        mus.cb(track("u2"))
        await settle(hass)
        return p.status()

    json.dumps(run(go()))


def test_listener_notified():
    p, _, _, _, _ = build()
    hits = []
    remove = p.async_add_listener(lambda: hits.append(1))
    run(p.async_chat("room", "x", "en"))
    assert hits
    remove()
    hits.clear()
    run(p.async_chat("room", "x", "en"))
    assert not hits


# --- special (opt-in) lights ---


STAR = FakeLight("light.star", name="Star projector", special=True, note="Not while a film runs.")


def test_special_light_is_not_part_of_all_lights(monkeypatch):
    monkeypatch.setattr(planner_mod, "_area_lights", lambda *a: [*LIGHTS, STAR])
    p, _, client, engine, _ = build()
    run(p.async_chat("room", "cozy", "en"))
    assert engine.applied[0][2] == ["light.a", "light.b"]
    prompt_text = client.calls[0][1]
    assert '"special":true' in prompt_text and "Not while a film runs." in prompt_text


def test_special_light_joins_only_when_named(monkeypatch):
    monkeypatch.setattr(planner_mod, "_area_lights", lambda *a: [*LIGHTS, STAR])
    p, _, _, engine, _ = build({**GOOD, "special_targets": ["light.star"]})
    res = run(p.async_chat("room", "stars please", "en"))
    assert engine.applied[0][2] == ["light.a", "light.b", "light.star"]
    assert res.plan["special_targets"] == ["light.star"]

    p, _, _, engine, _ = build({**GOOD, "targets": ["light.star"]})
    run(p.async_chat("room", "only the stars", "en"))
    assert engine.applied[0][2] == ["light.star"]


def test_special_targets_ignore_normal_lights_and_reject_unknown(monkeypatch):
    monkeypatch.setattr(planner_mod, "_area_lights", lambda *a: [*LIGHTS, STAR])
    p, _, _, engine, _ = build({**GOOD, "targets": ["light.a"], "special_targets": ["light.b"]})
    run(p.async_chat("room", "x", "en"))
    assert engine.applied[0][2] == ["light.a"]

    p, _, _, engine, _ = build({**GOOD, "special_targets": ["light.ghost"]})
    res = run(p.async_chat("room", "x", "en"))
    assert res.error == "invalid_plan" and engine.applied == []


def test_media_context_reaches_the_prompt():
    p, _, client, _, mus = build()
    mus.media_context = lambda area: [{"name": "TV", "state": "playing", "app": "YouTube"}]
    run(p.async_chat("room", "x", "en"))
    assert '"app": "YouTube"' in client.calls[0][1]
    mus.media_context = lambda area: []
    run(p.async_chat("room", "x", "en"))
    assert "nothing is playing" in client.calls[1][1]


# --- several rooms, rooms picked from the text ---

Room = imp("rooms").Room
HOME = [
    Room("cinema", "Heimkino", light_count=2),
    Room("kitchen", "Küche", aliases=("Kochecke",), light_count=1),
    Room("bath", "Badezimmer", light_count=1),
]
ROOM_LIGHTS = {
    "cinema": [FakeLight("light.c1", area_id="cinema"), STAR],
    "kitchen": [FakeLight("light.k1", area_id="kitchen", effect_list=("Rainbow",))],
    "bath": [FakeLight("light.b1", area_id="bath")],
}


@pytest.fixture
def home(monkeypatch):
    monkeypatch.setattr(planner_mod, "_room_directory", lambda hass, st: list(HOME))
    monkeypatch.setattr(
        planner_mod, "_area_lights", lambda hass, area, st: list(ROOM_LIGHTS.get(area, []))
    )


def applied_map(engine):
    return {area: ids for area, _plan, ids, _source in engine.applied}


def test_selected_rooms_get_one_plan_with_one_ai_call(home):
    p, _, client, engine, _ = build(limit=5)
    res = run(p.async_chat_rooms(["cinema", "kitchen"], "cozy", "de"))
    assert res.applied and res.areas == ("cinema", "kitchen")
    assert applied_map(engine) == {"cinema": ["light.c1"], "kitchen": ["light.k1"]}
    assert len(client.calls) == 1 and p.status()["ai"]["used"] == 1
    text, schema = client.calls[0][1], client.calls[0][2]
    assert "rooms" in schema
    assert "Rooms selected in the app: cinema (Heimkino), kitchen (Küche)" in text
    assert "=== Room cinema" in text and "=== Room kitchen" in text
    assert "=== Room bath" not in text and '"id":"bath"' in text


def test_room_named_in_text_wins_over_selection(home):
    p, _, client, engine, _ = build({**GOOD, "rooms": ["kitchen"]})
    res = run(p.async_chat_rooms(["cinema"], "mach die Kueche blau", "de"))
    assert res.areas == ("kitchen",) and applied_map(engine) == {"kitchen": ["light.k1"]}
    # The typo was matched, so the kitchen lights were described to the AI.
    assert "=== Room kitchen" in client.calls[0][1]


def test_ai_may_answer_with_room_names_and_pick_unlisted_rooms(home):
    p, _, client, engine, _ = build({**GOOD, "rooms": ["Badezimmer", "attic"]})
    res = run(p.async_chat_rooms(["cinema"], "da wo ich dusche", "de"))
    assert "=== Room bath" not in client.calls[0][1]
    assert res.areas == ("bath",) and applied_map(engine) == {"bath": ["light.b1"]}


def test_no_selection_lets_the_ai_choose_from_all_rooms(home):
    p, _, client, engine, _ = build({**GOOD, "rooms": ["cinema"]})
    res = run(p.async_chat_rooms([], "kino gemütlich", "de"))
    text = client.calls[0][1]
    assert "Rooms selected in the app: none" in text
    assert all(f"=== Room {a}" in text for a in ("cinema", "kitchen", "bath"))
    assert res.areas == ("cinema",) and list(applied_map(engine)) == ["cinema"]


def test_no_room_found_changes_nothing(home):
    p, _, _, engine, _ = build({"action": "none", "reply": "Welcher Raum?"})
    res = run(p.async_chat_rooms([], "gemütlich", "de"))
    assert res.reply == "Welcher Raum?" and not res.applied and res.error is None
    p, _, _, engine, _ = build(GOOD)
    res = run(p.async_chat_rooms([], "gemütlich", "de"))
    assert res.error == "no_room" and engine.applied == []


def test_targets_are_split_per_room_and_listed_rooms_without_targets_are_skipped(home):
    p, _, _, engine, _ = build(
        {**GOOD, "targets": ["light.k1"], "native_effects": {"light.k1": "Rainbow"}}
    )
    res = run(p.async_chat_rooms(["cinema", "kitchen"], "nur die Küchenlampe", "de"))
    assert res.areas == ("kitchen",) and applied_map(engine) == {"kitchen": ["light.k1"]}
    assert engine.applied[0][1].native_effects == {"light.k1": "Rainbow"}


def test_special_light_in_one_of_several_rooms(home):
    p, _, _, engine, _ = build({**GOOD, "special_targets": ["light.star"]})
    run(p.async_chat_rooms(["cinema", "kitchen"], "Sternenhimmel", "de"))
    assert applied_map(engine) == {
        "cinema": ["light.c1", "light.star"],
        "kitchen": ["light.k1"],
    }


def test_unknown_light_rejects_the_whole_multi_room_plan(home):
    p, _, _, engine, _ = build({**GOOD, "targets": ["light.c1", "light.ghost"]})
    res = run(p.async_chat_rooms(["cinema", "kitchen"], "x", "de"))
    assert res.error == "invalid_plan" and engine.applied == []


def test_unknown_selected_rooms_are_ignored_and_stop_hits_every_room(home):
    p, _, _, engine, _ = build({"action": "stop", "reply": "Aus"})
    res = run(p.async_chat_rooms(["cinema", "nowhere", "bath"], "stopp", "de"))
    assert res.areas == ("cinema", "bath")
    assert engine.stopped == [("cinema", True), ("bath", True)]


def test_follow_music_is_tracked_per_room(home):
    p, _, _, _, mus = build({**GOOD, "follow_music": True})
    mus.current = track("u1")
    run(p.async_chat_rooms(["cinema", "kitchen"], "folge der Musik", "de"))
    assert set(p.status()["follow"]) == {"cinema", "kitchen"}
