"""validate_plan: the safety core. Every rule has a test."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from ai_helpers import FakeLight, imp, make_settings  # noqa: E402

plan_mod = imp("plan")
validate_plan = plan_mod.validate_plan
PlanValidationError = plan_mod.PlanValidationError
normalize_raw_plan = plan_mod.normalize_raw_plan

LIGHTS = [
    FakeLight("light.a"),
    FakeLight("light.wled", effect_list=("Rainbow", "Fire")),
    FakeLight("light.aquarium", excluded=True),
]
SETTINGS = make_settings()


def base(**kw):
    plan = {
        "reply": "ok",
        "action": "apply",
        "palette": [[255, 0, 0]],
        "pattern": "pulse",
        "tempo": "slow",
        "intensity": 3,
    }
    plan.update(kw)
    return plan


def check(raw, settings=SETTINGS):
    return validate_plan(raw, LIGHTS, settings)


def bad(**kw):
    with pytest.raises(PlanValidationError):
        check(base(**kw))


def test_minimal_valid():
    plan = check(base())
    assert plan.action == "apply"
    assert plan.palette == ((255, 0, 0),)
    assert plan.targets == ()
    assert plan.brightness_pct == 60
    assert plan.strobe_capped is False
    assert plan.as_dict()["palette"] == [[255, 0, 0]]


@pytest.mark.parametrize("raw", [None, [], "x", 5, [{"action": "apply"}]])
def test_not_an_object(raw):
    with pytest.raises(PlanValidationError):
        check(raw)


@pytest.mark.parametrize("action", [None, "", "explode", 1, ["apply"], "APPLY"])
def test_bad_action(action):
    bad(action=action)


def test_missing_action():
    raw = base()
    del raw["action"]
    with pytest.raises(PlanValidationError):
        check(raw)


@pytest.mark.parametrize("action", ["stop", "none"])
def test_stop_and_none_need_no_palette(action):
    plan = check({"action": action, "reply": "bye"})
    assert plan.action == action
    assert plan.palette == ()


def test_reply_must_be_string_and_is_capped():
    bad(reply=5)
    assert len(check(base(reply="x" * 5000)).reply) <= 600
    assert check(base(reply=None)).reply == ""


def test_booleans_strict():
    bad(party="yes")
    bad(follow_music=1)
    plan = check(base(party=True, follow_music=True))
    assert plan.party and plan.follow_music


def test_targets_ok_dedup_and_subset():
    assert check(base(targets=["light.a", "light.a"])).targets == ("light.a",)
    assert check(base(targets=[])).targets == ()


@pytest.mark.parametrize(
    "targets", [["light.nope"], ["light.aquarium"], "light.a", [5], [None], ["light.a", "light.x"]]
)
def test_targets_unknown_excluded_or_bad(targets):
    bad(targets=targets)


def test_excluded_flag_on_given_lights_is_respected():
    with pytest.raises(PlanValidationError):
        validate_plan(base(targets=["light.a"]), [FakeLight("light.a", excluded=True)], SETTINGS)


def test_palette_required_for_apply():
    raw = base()
    del raw["palette"]
    with pytest.raises(PlanValidationError):
        check(raw)
    bad(palette=[])


def test_kelvin_replaces_palette():
    raw = base(color_temp_kelvin=2700)
    del raw["palette"]
    plan = check(raw)
    assert plan.color_temp_kelvin == 2700
    assert plan.palette == ()


@pytest.mark.parametrize("kelvin", [0, 999, 10001, "warm", True, 2700.5])
def test_kelvin_invalid(kelvin):
    bad(color_temp_kelvin=kelvin)


def test_palette_limits():
    assert len(check(base(palette=[[i, 0, 0] for i in range(8)])).palette) == 8
    bad(palette=[[i, 0, 0] for i in range(9)])


@pytest.mark.parametrize(
    "color",
    [[256, 0, 0], [-1, 0, 0], [1, 2], [1, 2, 3, 4], "red", [1.5, 0, 0], [True, 0, 0], ["1", 0, 0], None, [float("nan"), 0, 0]],
)
def test_palette_bad_entries(color):
    bad(palette=[color])


def test_palette_bounds_and_integral_floats():
    assert check(base(palette=[[0, 255, 0.0]])).palette == ((0, 255, 0),)


def test_palette_not_a_list():
    bad(palette="#ff0000")
    bad(palette={"r": 1})


def test_normalize_hex_and_json_strings():
    raw = normalize_raw_plan(base(palette=["#ff8000", "00FF00"]))
    assert check(raw).palette == ((255, 128, 0), (0, 255, 0))
    raw = normalize_raw_plan(base(palette="[[1,2,3]]", targets='["light.a"]'))
    plan = check(raw)
    assert plan.palette == ((1, 2, 3),)
    assert plan.targets == ("light.a",)
    assert normalize_raw_plan("x") == "x"


def test_normalize_does_not_rescue_garbage():
    with pytest.raises(PlanValidationError):
        check(normalize_raw_plan(base(palette=["#zzzzzz"])))


@pytest.mark.parametrize("pattern", ["static", "breathe", "pulse", "wave", "color_cycle", "sparkle"])
def test_patterns(pattern):
    assert check(base(pattern=pattern)).pattern == pattern


@pytest.mark.parametrize("field,value", [("pattern", "disco"), ("pattern", 3), ("tempo", "ludicrous"), ("tempo", 1)])
def test_enum_violations(field, value):
    bad(**{field: value})


@pytest.mark.parametrize("tempo", ["slow", "medium", "fast"])
def test_tempos(tempo):
    assert check(base(tempo=tempo)).tempo == tempo


def test_brightness_clamped_not_rejected():
    assert check(base(brightness_pct=500)).brightness_pct == 100
    assert check(base(brightness_pct=0)).brightness_pct == 1
    assert check(base(brightness_pct=-9)).brightness_pct == 1
    assert check(base(brightness_pct=33.4)).brightness_pct == 33


@pytest.mark.parametrize("value", ["bright", True, None.__class__, float("nan")])
def test_brightness_non_numeric(value):
    bad(brightness_pct=value)


def test_transition_clamped():
    assert check(base(transition_s=99)).transition_s == 10.0
    assert check(base(transition_s=-3)).transition_s == 0.0
    assert check(base(transition_s=2.5)).transition_s == 2.5
    bad(transition_s="fast")


@pytest.mark.parametrize("intensity", [0, 6, -1, 2.5, "3", True])
def test_intensity_out_of_range_is_error(intensity):
    bad(intensity=intensity)


def test_intensity_bounds():
    assert check(base(intensity=1)).intensity == 1
    assert check(base(intensity=5)).intensity == 5


def test_native_effects_valid():
    plan = check(base(native_effects={"light.wled": "Rainbow"}))
    assert plan.native_effects == {"light.wled": "Rainbow"}


@pytest.mark.parametrize(
    "effects",
    [
        {"light.wled": "Disco"},
        {"light.a": "Rainbow"},
        {"light.ghost": "Rainbow"},
        {"light.aquarium": "Rainbow"},
        {"light.wled": 5},
        ["Rainbow"],
        "Rainbow",
    ],
)
def test_native_effects_invalid(effects):
    bad(native_effects=effects)


def test_native_effect_must_be_in_targets():
    bad(targets=["light.a"], native_effects={"light.wled": "Rainbow"})


# --- strobe policy -----------------------------------------------------------------


@pytest.mark.parametrize(
    "allow,party,capped",
    [(False, False, True), (False, True, True), (True, False, True), (True, True, False)],
)
def test_strobe_policy(allow, party, capped):
    plan = check(base(pattern="strobe", party=party), make_settings(allow_strobe=allow))
    assert plan.strobe_capped is capped
    assert plan.pattern == ("pulse" if capped else "strobe")


def test_non_strobe_never_flagged():
    assert check(base(pattern="wave", party=True)).strobe_capped is False


def test_strobe_in_stop_action_is_capped_too():
    plan = check({"action": "stop", "pattern": "strobe"})
    assert plan.pattern == "pulse" and plan.strobe_capped


def test_plan_is_immutable():
    plan = check(base())
    with pytest.raises(AttributeError):
        plan.pattern = "strobe"  # type: ignore[misc]
