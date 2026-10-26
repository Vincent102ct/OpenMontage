"""P3.4 lossless conversion and retiming failures, using explicitly synthetic values only."""
import copy
import hashlib
import inspect
import math
import shutil
from pathlib import Path

import pytest

from lib import story_scene_plan as planner
from lib.story_scene_plan import ScenePlanError
from lib.story_visual_bible import fingerprint
from studio.catalog import ApprovedPackages
from studio.review import current_decisions, load_log, record_decision
from studio.reviewed import read_reviewed_story
from studio.scene_plan import (approve_scene_plan, prepare_scene_plan, read_scene_plan, retime_scene_plan,
                               scene_plan_handoff)
from studio.store import ProductionStore
from studio.visual_bible import approve_visual_bible, prepare_visual_bible, read_visual_bible
from tests.studio.scene_plan_fixture import prepare, resolved_choices, synthetic_measurements
from tools.story import story_planner

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def case(tmp_path_factory):
    store = ProductionStore(tmp_path_factory.mktemp("handoff") / "projects", ApprovedPackages(ROOT))
    prepare(store)
    first = prepare_scene_plan(store, "fx", {})
    second = prepare_scene_plan(store, "fx", {"base_version": first["version"], "package_sha256": first["package_sha256"],
        "manifest_sha256": first["manifest_sha256"], "choices": resolved_choices(first)})
    view = approve_scene_plan(store, "fx", second["version"], second["package_sha256"], second["manifest_sha256"])
    return store, view, read_reviewed_story(store, "fx")["package"]


@pytest.fixture
def isolated_store(case, tmp_path):
    source, _, _ = case
    shutil.copytree(source.root, tmp_path / "projects")
    return ProductionStore(tmp_path / "projects", ApprovedPackages(ROOT))


def seal(value):
    value["manifest_sha256"] = fingerprint({k: v for k, v in value.items() if k != "manifest_sha256"})
    return value


def derivative(view, fmt="short", seconds=2.0):
    return planner.retime(view["package"], fmt, synthetic_measurements(view, fmt, seconds), approved=view)


@pytest.mark.parametrize("fault", ["missing", "duplicate", "reorder", "missing_final", "missing_reaction", "missing_dialogue",
    "shot_id", "source", "event", "dialogue", "sound", "uncertainty", "scene_boundary", "prop_anchor", "capability",
    "character", "environment", "narration_link", "camera", "lighting"])
def test_post_conversion_rejects_loss_or_corruption(case, fault):
    _, view, _ = case
    plan = view["package"]
    ir = planner.action_timeline(plan, "long", approved=view)
    shots = ir["scenes"]
    fmt = ir["metadata"]["approved_format"]
    source_shots = fmt["shots"]
    if fault == "missing": shots.pop(0)
    elif fault == "duplicate": shots[1] = copy.deepcopy(shots[0])
    elif fault == "reorder": shots[0], shots[1] = shots[1], shots[0]
    elif fault == "missing_final": shots.pop()
    elif fault == "missing_reaction": shots.pop(next(i for i, s in enumerate(source_shots) if s["kind"] == "reaction_hold"))
    elif fault == "missing_dialogue": shots.pop(next(i for i, s in enumerate(source_shots) if s["source"]["dialogue"]))
    elif fault == "shot_id": shots[0]["scene_id"] = "SH_L_999"
    elif fault == "source": source_shots[0]["source"]["narration"]["text"] = "An invented explanation."
    elif fault == "event": source_shots[0]["source"]["event_ids"] = []
    elif fault == "dialogue": next(s for s in source_shots if s["source"]["dialogue"])["source"]["dialogue"] = []
    elif fault == "sound": next(s for s in source_shots if s["source"]["sound_cue_ids"])["source"]["sound_cue_ids"] = []
    elif fault == "uncertainty": ir["metadata"]["continuity"]["canonical_ambiguities"][0]["status"] = "resolved"
    elif fault == "scene_boundary": fmt["scenes"][0]["shot_ids"].pop()
    elif fault == "prop_anchor": source_shots[0]["staging"]["props"][0]["anchor"] = "wrong.anchor"
    elif fault == "capability": next(s for s in source_shots if s["capability"]["status"] == "editorial_review")["capability"]["status"] = "supported_direct"
    elif fault == "character": shots[0]["actions"][0]["character_id"] = "CHR_INVENTED"
    elif fault == "environment": fmt["scenes"][0]["environment"]["sha256"] = "0" * 64
    elif fault == "narration_link": ir["metadata"]["timed_shots"][0]["narration"]["action_indices"] = []
    elif fault == "camera": shots[0]["camera"]["keys"][-1][0] += 100
    elif fault == "lighting": shots[0]["effects"] = ["lighting:blackout"]
    with pytest.raises(ScenePlanError) as exc:
        planner.validate_action_timeline(plan, "long", ir, approved=view)
    assert exc.value.code == "handoff_invalid" and exc.value.blockers


@pytest.mark.parametrize("fault", ["missing", "duplicate", "reorder", "missing_final", "wrong_shot", "overlap", "gap",
    "negative", "off_grid", "narration_crosses_cut", "action_overrun", "scene_overrun", "final_duration"])
def test_retimed_derivative_cannot_be_reduced_or_retimed_again_by_accident(case, fault):
    _, view, _ = case
    value = derivative(view)
    rows = value["shots"]
    if fault == "missing": rows.pop(0)
    elif fault == "duplicate": rows[1] = copy.deepcopy(rows[0])
    elif fault == "reorder": rows[0], rows[1] = rows[1], rows[0]
    elif fault == "missing_final": rows.pop()
    elif fault == "wrong_shot": rows[0]["shot_id"] = "SH_S_999"
    elif fault == "overlap": rows[1]["start_frame"] = rows[0]["end_frame"] - 1
    elif fault == "gap": rows[1]["start_frame"] += 1
    elif fault == "negative": rows[0]["start_frame"] = -1
    elif fault == "off_grid": rows[0]["start_frame"] = 0.25
    elif fault == "narration_crosses_cut": rows[0]["narration"]["end_frame"] = rows[1]["end_frame"]
    elif fault == "action_overrun": rows[-1]["motion"][0]["end_frame"] = value["duration_frames"] + 100
    elif fault == "scene_overrun": value["scenes"][-1]["end_frame"] += 1
    elif fault == "final_duration": value["duration_seconds"] -= 1
    with pytest.raises(ScenePlanError) as exc:
        planner.action_timeline(view["package"], "short", value, approved=view)
    assert exc.value.code == "handoff_invalid"


@pytest.mark.parametrize("fault", ["missing", "duplicate", "unknown", "reorder", "text_hash", "shot_id", "plan_version",
    "package_hash", "manifest_hash", "inputs_hash", "format", "fingerprint", "nonhex_audio", "fake_audio_claim",
    "missing_audio_metadata", "provenance"])
def test_measurement_binding_and_order_are_strict(case, fault):
    _, view, _ = case
    value = synthetic_measurements(view, "short")
    if fault == "missing": value["units"].pop()
    elif fault == "duplicate": value["units"][1] = copy.deepcopy(value["units"][0])
    elif fault == "unknown": value["units"][0]["unit_id"] = "BEAT_UNKNOWN"
    elif fault == "reorder": value["units"].reverse()
    elif fault == "text_hash": value["units"][0]["text_sha256"] = "0" * 64
    elif fault == "shot_id": value["units"][0]["shot_id"] = "SH_S_999"
    elif fault == "plan_version": value["plan"]["version"] = "v99"
    elif fault == "package_hash": value["plan"]["package_sha256"] = "0" * 64
    elif fault == "manifest_hash": value["plan"]["manifest_sha256"] = "0" * 64
    elif fault == "inputs_hash": value["plan"]["inputs_sha256"] = "0" * 64
    elif fault == "format": value["format"] = "long"
    elif fault == "nonhex_audio": value["units"][0]["audio_sha256"] = "z" * 64
    elif fault == "fake_audio_claim": value["units"][0].update(audio_sha256="a" * 64, sample_rate_hz=22050)
    elif fault == "missing_audio_metadata": value["provenance"]["kind"] = "measured_audio"
    elif fault == "provenance": value["provenance"]["recorded_at"] = "not-a-timestamp"
    seal(value)
    if fault == "fingerprint": value["manifest_sha256"] = "0" * 64
    with pytest.raises(ScenePlanError) as exc:
        planner.retime(view["package"], "short", value, approved=view)
    assert exc.value.code in {"invalid_measurement", "stale_measurement"}


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf"), -float("inf"), True, 1e308])
def test_invalid_durations_fail_closed(case, seconds):
    _, view, _ = case
    value = synthetic_measurements(view, "short")
    value["units"][0]["duration_seconds"] = seconds
    # Non-JSON NaN/Infinity cannot have a legitimate canonical-JSON fingerprint.
    if isinstance(seconds, bool) or math.isfinite(seconds): seal(value)
    with pytest.raises(ScenePlanError) as exc:
        planner.retime(view["package"], "short", value, approved=view)
    assert exc.value.code == "invalid_measurement"


@pytest.mark.parametrize("seconds", [0.1, 2.0, 40.123])
def test_all_shots_actions_camera_silence_and_final_boundaries_are_safe(case, seconds):
    _, view, reviewed = case
    plan = view["package"]
    frozen = copy.deepcopy(plan)
    timelines = {}
    for fmt, fp in plan["formats"].items():
        timed = derivative(view, fmt, seconds)
        ir = planner.action_timeline(plan, fmt, timed, approved=view)
        timelines[fmt] = ir
        assert [s["scene_id"] for s in ir["scenes"]] == [s["shot_id"] for s in fp["shots"]]
        assert timed["duration_frames"] == timed["shots"][-1]["end_frame"] == timed["scenes"][-1]["end_frame"]
        assert timed["chapters"][-1]["end_frame"] == timed["duration_frames"]
        assert not timed["renderable"] and timed["timing_status"] == "synthetic_test_not_measured_audio"
        assert timed["approved_format"] == fp and timed["continuity"] == plan["continuity"]
        end = 0
        for original, window, output in zip(fp["shots"], timed["shots"], ir["scenes"]):
            assert window["start_frame"] == end and window["frame_count"] > 0
            end = window["end_frame"]
            assert window["frame_count"] >= original["timing"]["frame_grid"]["estimated_frame_count"]
            assert output["end_seconds"] == pytest.approx(end / 30)
            assert len(output["actions"]) == sum(len(a["steps"]) for a in original["motion_plan"]["actors"])
            for action in output["actions"]:
                assert output["start_seconds"] <= action["at_seconds"] < action["at_seconds"] + action["duration_seconds"] <= output["end_seconds"] + 1e-8
                assert action["at_seconds"] * 30 == pytest.approx(round(action["at_seconds"] * 30))
                assert action["duration_seconds"] * 30 == pytest.approx(round(action["duration_seconds"] * 30))
            for key in output["camera"]["keys"]:
                assert 0 <= key[0] <= window["frame_count"] / 30
            assert output["camera"]["keys"][-1][0] == window["frame_count"] / 30
            if original["kind"] == "narrative":
                n = window["narration"]
                assert window["start_frame"] <= n["start_frame"] < n["end_frame"] <= window["end_frame"]
                assert (window["end_frame"] - n["end_frame"]) / 30 + 1e-8 >= original["timing"]["tail_seconds"] + original["timing"]["planned_silence_seconds"]
            else:
                assert window["frame_count"] == original["timing"]["frame_grid"]["estimated_frame_count"]
        if seconds > 40:
            assert timed["duration_seconds"] > fp["timing"]["estimated_seconds"]
        assert ir["metadata"]["approved_format"] == fp
    cov = planner.handoff_coverage(plan, reviewed, timelines, approved=view)
    assert cov["formats"]["long"]["working_text"] == {"non_whitespace_characters": 1083, "covered": 1083, "missing_segments": []}
    assert cov["formats"]["long"]["allocated_beats"] == 14 and cov["formats"]["short"]["allocated_beats"] == 7
    assert len(cov["formats"]["long"]["dialogue"]) == 2 and len(cov["formats"]["long"]["events"]) == 10
    assert len(cov["formats"]["long"]["sound_cues"]) == 4
    assert cov["formats"]["short"]["sources_within_long"] and cov["formats"]["short"]["events_within_long"]
    assert plan == frozen


def test_old_partial_timing_list_and_unapproved_retiming_are_rejected(case):
    _, view, _ = case
    with pytest.raises(ScenePlanError, match="complete bound"):
        planner.action_timeline(view["package"], "short", [{"shot_id": "SH_S_001"}], approved=view)
    with pytest.raises(ScenePlanError) as exc:
        planner.retime(view["package"], "short", synthetic_measurements(view, "short"))
    assert exc.value.code == "stale_measurement"
    with pytest.raises(ScenePlanError) as exc:
        planner.action_timeline(view["package"], "short")
    assert exc.value.code == "stale_measurement"


@pytest.mark.parametrize("fault", ["source", "actor", "narration_unit", "inventory"])
def test_corrupted_plan_cannot_bypass_approval_binding(case, fault):
    _, view, _ = case
    plan = copy.deepcopy(view["package"])
    first = plan["formats"]["short"]["shots"][0]
    if fault == "source": first["source"]["narration"]["text"] = "Rewritten source."
    elif fault == "actor": first["motion_plan"]["actors"][0]["character_id"] = "CHR_OTHER"
    elif fault == "narration_unit": first["timing"]["narration_unit_id"] = "BEAT_UNKNOWN"
    else: plan["formats"]["short"]["shots"].pop()
    with pytest.raises(ScenePlanError) as exc:
        planner.action_timeline(plan, "short", approved=view)
    assert exc.value.code in {"stale_measurement", "handoff_invalid"}


def test_unsupported_actions_are_structured_failures_never_reduced_plans(isolated_store):
    first = read_scene_plan(isolated_store, "fx", "v1")
    with pytest.raises(ScenePlanError) as exc:
        planner.action_timeline(first["package"], "long")
    assert exc.value.code == "unsupported_capability"
    assert all(b["shot_id"] and b["requirement"]["status"] == "requires_new_capability" for b in exc.value.blockers)


@pytest.mark.parametrize("changed", ["visual", "canon", "plan"])
def test_current_storage_boundary_rejects_stale_approved_inputs(isolated_store, changed):
    store = isolated_store
    view = read_scene_plan(store, "fx")
    measurements = synthetic_measurements(view, "short")
    if changed == "visual":
        old = read_visual_bible(store, "fx")
        choices = copy.deepcopy(old["manifest"]["choices"])
        choices["locations"]["LOC_HALL"]["flicker_lamp"] = "lamp_west"
        new = prepare_visual_bible(store, "fx", {"base_version": old["version"], "package_sha256": old["package_sha256"],
            "manifest_sha256": old["manifest_sha256"], "choices": choices})
        approve_visual_bible(store, "fx", new["version"], new["package_sha256"], new["manifest_sha256"])
    elif changed == "canon":
        target = next(t for t in current_decisions(load_log(store.root / "fx")).values() if t["target_id"] == "MOT_THREE_KNOCKS")
        record_decision(store, "fx", {"target_id": "MOT_THREE_KNOCKS", "decision": "reject", "supersedes": target["decision_id"]})
    else:
        choices = copy.deepcopy(view["manifest"]["choices"])
        choices["formats"]["long"]["shots"]["SH_L_001"]["shot_size"] = "wide"
        new = prepare_scene_plan(store, "fx", {"base_version": view["version"], "package_sha256": view["package_sha256"],
            "manifest_sha256": view["manifest_sha256"], "choices": choices})
        approve_scene_plan(store, "fx", new["version"], new["package_sha256"], new["manifest_sha256"])
    with pytest.raises(ScenePlanError) as exc:
        retime_scene_plan(store, "fx", "short", measurements)
    assert exc.value.code == "stale_measurement"
    assert not (store.root / "fx/artifacts/scene_plan_retiming").exists()


def test_separate_derivative_is_idempotent_and_never_rewrites_approved_history(isolated_store):
    store = isolated_store
    view = read_scene_plan(store, "fx")
    folder = store.root / "fx/artifacts/story_scene_plan"
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob("*.json")}
    measurements = synthetic_measurements(view, "long", 40.123)
    first = retime_scene_plan(store, "fx", "long", measurements)
    second = retime_scene_plan(store, "fx", "long", measurements)
    assert first == second and not first["audio_verified"] and not first["renderable"]
    assert first["coverage"]["formats"]["long"]["working_text"]["covered"] == 1083
    assert {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob("*.json")} == before
    artifacts = list((store.root / "fx/artifacts/scene_plan_retiming").rglob("*.json"))
    assert len(artifacts) == 1
    artifacts[0].write_bytes(b"tampered derivative")
    with pytest.raises(ScenePlanError, match="nothing was overwritten"):
        retime_scene_plan(store, "fx", "long", measurements)
    assert artifacts[0].read_bytes() == b"tampered derivative"
    assert not list(store.root.rglob("*.wav")) and not list(store.root.rglob("*.mp4"))


def test_handoff_has_full_animation_context_and_legacy_api_is_unchanged(case, monkeypatch):
    store, view, _ = case
    handoff = scene_plan_handoff(store, "fx")
    for fmt in ("short", "long"):
        ir = handoff["formats"][fmt]["provisional_action_timeline"]
        assert ir["metadata"]["approved_format"] == view["package"]["formats"][fmt]
        assert ir["metadata"]["plan_binding"] == handoff["formats"][fmt]["measurement_contract"]["plan"]
        assert ir["metadata"]["continuity"]["canonical_ambiguities"] == view["package"]["continuity"]["canonical_ambiguities"]
    assert list(inspect.signature(story_planner.plan_story).parameters) == ["analysis", "narration"]
    called = []
    class ExistingPlanner:
        def __init__(self, analysis, narration): called.append((analysis, narration))
        def plan(self): return {"existing": "video"}, {"existing": "timeline"}
    monkeypatch.setattr(story_planner, "Planner", ExistingPlanner)
    inputs, measured = {"analysis": "unchanged"}, {"measured_audio_contract": "unchanged"}
    assert story_planner.plan_story(inputs, measured) == ({"existing": "video"}, {"existing": "timeline"})
    assert called == [(inputs, measured)]
