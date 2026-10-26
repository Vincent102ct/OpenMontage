"""P3.4: approved synthetic canon + Visual Bible -> complete, source-traceable Short/Long scene plans."""
import copy
import hashlib
import inspect
import json
import re
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from lib import story_scene_plan as planner
from lib.story_scene_plan import ScenePlanError
from lib.story_visual_bible import VisualBibleError
from studio.catalog import ApprovedPackages
from studio.review import current_decisions, load_log, record_decision
from studio.reviewed import read_reviewed_story
from studio.scene_plan import (OUTPUT_DIR, approve_scene_plan, prepare_scene_plan, read_scene_plan,
                               scene_plan_handoff)
from studio.server import create_app
from studio.store import ProductionStore
from studio.visual_bible import approve_visual_bible, prepare_visual_bible, read_visual_bible
from tests.studio.scene_plan_fixture import STORY, prepare, requested_actions, resolved_choices, shot_id, synthetic_measurements
from tests.studio.test_fiction import tree
from tools.story import story_planner

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def store(tmp_path):
    return ProductionStore(tmp_path / "projects", ApprovedPackages(ROOT))


def save(store, view, choices):
    return prepare_scene_plan(store, "fx", {"base_version": view["version"], "package_sha256": view["package_sha256"],
                                            "manifest_sha256": view["manifest_sha256"], "choices": choices})


def approved(store):
    prepare(store)
    v1 = prepare_scene_plan(store, "fx", {})
    v2 = save(store, v1, resolved_choices(v1))
    assert not v2["package"]["blockers"], v2["package"]["blockers"]
    return approve_scene_plan(store, "fx", v2["version"], v2["package_sha256"], v2["manifest_sha256"])


def shots(plan, fmt, kind=None):
    return [s for s in plan["formats"][fmt]["shots"] if kind is None or s["kind"] == kind]


def test_complete_long_and_short_coverage_from_one_canon(store):
    prepare(store)
    before = tree(store.root / "fx")
    view = prepare_scene_plan(store, "fx", {})
    plan, reviewed = view["package"], read_reviewed_story(store, "fx")
    canon = reviewed["package"]["canonical_story"]
    for fmt, aspect in (("long", "16:9"), ("short", "9:16")):
        fp, beats = plan["formats"][fmt], [b for ch in canon["formats"][fmt]["chapters"] for b in ch["beats"]]
        assert fp["aspect_ratio"] == aspect
        narrative = shots(plan, fmt, "narrative")
        # Every reviewed beat has exactly one narrative shot, in the approved order, with verbatim source fields.
        assert [s["source"]["beat_id"] for s in narrative] == [b["id"] for b in beats]
        for s, b in zip(narrative, beats):
            assert s["source"]["narration"]["text"] == b["narration"]["text"]
            assert s["source"]["narration"]["sources"] == b["narration"]["sources"]
            assert (s["source"]["event_ids"], s["source"]["character_ids"], s["source"]["object_ids"]) == (
                b["event_ids"], b["character_ids"], b["object_ids"])
        assert [c["chapter_id"] for c in fp["chapters"]] == [c["id"] for c in canon["formats"][fmt]["chapters"]]
        assert [s["shot_id"] for s in fp["shots"]] == [sid for sc in fp["scenes"] for sid in sc["shot_ids"]]
        assert [s["shot_id"] for s in fp["shots"]] == sorted(s["shot_id"] for s in fp["shots"])
        assert "\n".join(s["source"]["narration"]["text"] for s in narrative) == "\n".join(b["narration"]["text"] for b in beats)
    cov = plan["coverage"]["formats"]
    assert cov["long"]["allocated_beats"] == cov["long"]["reviewed_beats"] == 14
    assert cov["long"]["working_text"]["covered"] == cov["long"]["working_text"]["non_whitespace_characters"] > 1000
    assert not cov["long"]["events_missing"] and not cov["long"]["dialogue_missing"] and not cov["long"]["sound_cues_missing"]
    assert cov["short"]["allocated_beats"] == 7 and cov["short"]["sources_within_long"] and cov["short"]["events_within_long"]
    assert {e["id"] for e in canon["events"]} == set(cov["long"]["events"])
    # The Short preserves its unresolved ending; the Long ends on the same final beat.
    assert shots(plan, "short", "narrative")[-1]["source"]["event_ids"] == ["EVT_KNOCKS_AGAIN"]
    assert shots(plan, "long", "narrative")[-1]["source"]["event_ids"] == ["EVT_KNOCKS_AGAIN"]
    assert plan["shared_identity"] == {"characters": read_visual_bible(store, "fx")["package"]["formats"]["short"]["characters"],
                                       "locations": read_visual_bible(store, "fx")["package"]["formats"]["short"]["locations"]}
    assert all(tree(store.root / "fx")[p] == h for p, h in before.items())  # Inputs untouched.
    assert not list(store.root.rglob("*.wav")) and not list(store.root.rglob("*.mp4"))
    assert not list(store.root.rglob("checkpoint_*.json"))
    assert str(store.root) not in json.dumps(plan) and "C:\\" not in json.dumps(plan)


def test_no_fabricated_content_and_uncertainty_is_preserved(store):
    prepare(store)
    plan = prepare_scene_plan(store, "fx", {})["package"]
    reviewed = read_reviewed_story(store, "fx")["package"]
    canon = reviewed["canonical_story"]
    known = {item["id"] for name in ("characters", "locations", "objects", "events", "sound_cues", "dialogue", "facts",
                                     "ambiguities", "continuity_rules") for item in canon[name]}
    for fmt in ("short", "long"):
        for s in shots(plan, fmt):
            src = s["source"]
            assert src["narration"]["text"] in reviewed["working_text"] or all(
                part in reviewed["working_text"] for part in src["narration"]["text"].split("\n"))
            for ids in (src["event_ids"], src["character_ids"], src["object_ids"], src["sound_cue_ids"],
                        src["ambiguity_ids"], src["continuity_rule_ids"], [d["id"] for d in src["dialogue"]]):
                assert set(ids) <= known
            assert {c["character_id"] for c in s["staging"]["cast"]} <= set(src["character_ids"])
            assert s["staging"]["basis"] == "creative_proposal_not_canonical_fact"
            assert src["reviewed_staging"]["executable"] is False and s["descriptive_proposal"]["executable"] is False
            assert s["staging"]["reveal"]["identity_reveal_allowed"] is False
            if s["staging"]["presence"]:
                assert "CHR_SHAPE" in src["character_ids"] and s["staging"]["presence"]["identity_revealed"] is False
            assert all(c["character_id"] != "CHR_TENANT" for c in s["staging"]["cast"])
    for fmt in ("short", "long"):
        final = plan["continuity"]["formats"][fmt]["final_state"]["revelation"]
        assert final == {"AMB_KNOCKER": "intentionally_unresolved", "AMB_SHAPE": "intentionally_unresolved"}
    # The "after the dark" beat does not list the shape, so it stays hidden there.
    assert shots(plan, "long", "narrative")[10]["staging"]["presence"] is None


def test_capability_blockers_are_explicit_and_resolvable_without_deleting_story(store):
    prepare(store)
    v1 = prepare_scene_plan(store, "fx", {})
    # Canon-structured dialogue on screen needs lip-sync: an explicit blocker, never silently "supported".
    assert any("DLG_WHO" in b and "REQUIRES_NEW_CAPABILITY" in b for b in v1["package"]["blockers"])
    v2 = save(store, v1, requested_actions(v1))
    blocking = [b for b in v2["package"]["blockers"] if "REQUIRES_NEW_CAPABILITY" in b]
    assert len(blocking) == 5 and sum("OBJ_ROOM_DOOR" in b for b in blocking) == 2
    assert any("CHR_OWEN" in b and "fingers" in b for b in blocking)
    with pytest.raises(ScenePlanError, match="blockers"):
        approve_scene_plan(store, "fx", v2["version"], v2["package_sha256"], v2["manifest_sha256"])
    choices = resolved_choices(v2)
    door = choices["formats"]["long"]["shots"][shot_id(v2, "long", "BEAT_L05")]
    door["editorial_acknowledged"] = False  # Editorial representation needs an explicit acknowledgement.
    v3 = save(store, v2, choices)
    assert [b for b in v3["package"]["blockers"]] == [f"LONG {shot_id(v2, 'long', 'BEAT_L05')} EDITORIAL_REVIEW: "
                                                      "acknowledge prop_interaction OBJ_ROOM_DOOR"]
    v4 = save(store, v3, resolved_choices(v3))
    assert not v4["package"]["blockers"]
    long = v4["package"]["formats"]["long"]
    assert len(shots(v4["package"], "long", "narrative")) == 14  # Nothing deleted to satisfy capability.
    reach = next(s for s in long["shots"] if s["source"]["beat_id"] == "BEAT_L05")
    steps = reach["motion_plan"]["actors"][0]["steps"]
    assert [s["preset"] for s in steps] == ["cautious_walk", "guarded_reach", "hold"]  # Continuous: Lena crosses the room.
    handle = next(p for p in read_visual_bible(store, "fx")["package"]["props"] if p["canonical_id"] == "OBJ_ROOM_DOOR")["point"]
    assert steps[1]["params"]["target"] == handle and steps[1]["acting_asset"]["id"] == "guarded_reach"
    assert reach["capability"]["status"] == "editorial_review" and reach["editorial_acknowledged"]
    summary = {k: v for k, v in long["capability_summary"].items() if v}
    assert set(summary) <= set(planner.STATUSES) and sum(summary.values()) == len(long["shots"])


def test_capability_vocabulary_is_honest():
    vocab = planner.vocabulary()
    unsupported = {"turn_around", "grasp_object", "run"}
    assert {k for k, v in vocab["performances"].items() if v["status"] == "requires_new_capability"} == unsupported
    assert vocab["prop_interactions"]["interior_door"]["open_door"]["status"] == "requires_new_capability"
    assert vocab["dialogue_delivery"]["on_screen_speech"]["status"] == "requires_new_capability"
    assert vocab["camera_moves"]["handheld_drift"]["status"] == "requires_new_capability"
    assert vocab["lighting_states"]["blackout"]["status"] == "requires_new_capability"
    # Every supported performance names a real pinned P3.2A acting preset (or the hold primitive).
    for name, v in vocab["performances"].items():
        if v["acting_asset"]:
            assert planner.acting_pin(v["acting_asset"])["revision"] == 1


def test_cross_format_prop_continuity_teleport_and_revelation(store):
    prepare(store)
    v1 = prepare_scene_plan(store, "fx", {})
    choices = resolved_choices(v1)
    short_end = choices["formats"]["short"]["shots"][shot_id(v1, "short", "BEAT_S07")]
    short_end["props"]["OBJ_ROOM_DOOR"] = "visible_in_set"
    plan = save(store, v1, choices)["package"]
    assert "FORMAT_CONTINUITY OBJ_ROOM_DOOR after EVT_KNOCKS_AGAIN: Short is open, Long is closed." in plan["blockers"]
    choices = resolved_choices(v1)
    hall = next(s["scene_id"] for s in v1["package"]["formats"]["long"]["scenes"] if "BEAT_L06" in s["beat_ids"])
    choices["formats"]["long"]["scenes"][hall]["transition"] = "continuous"
    owen = choices["formats"]["long"]["shots"][shot_id(v1, "long", "BEAT_L07")]["cast"]["CHR_OWEN"]
    owen["entry"] = "present_at_cut"
    blockers = prepare_scene_plan(store, "fx", {"base_version": "v2", "package_sha256": read_scene_plan(store, "fx")["package_sha256"],
                                                "manifest_sha256": read_scene_plan(store, "fx")["manifest_sha256"],
                                                "choices": choices})["package"]["blockers"]
    assert any("ACCIDENTAL_TELEPORT" in b and hall in b for b in blockers)
    assert any("TELEPORT CHR_OWEN" in b for b in blockers)
    bad = resolved_choices(v1)
    bad["formats"]["long"]["shots"][shot_id(v1, "long", "BEAT_L11")]["presence"] = "visible_partial"
    with pytest.raises(ScenePlanError, match="presence"):  # Not an offered option where the beat lacks the shape.
        save(store, read_scene_plan(store, "fx"), bad)


def test_choices_cannot_add_remove_or_rewrite_story(store):
    prepare(store)
    v1 = prepare_scene_plan(store, "fx", {})
    snapshot = tree(store.root / "fx")
    for mutate in (lambda c: c["formats"]["long"]["shots"].pop(shot_id(v1, "long", "BEAT_L09")),
                   lambda c: c["formats"]["long"]["shots"].__setitem__("SH_L_999", {}),
                   lambda c: c["formats"]["short"]["shots"][shot_id(v1, "short", "BEAT_S01")].__setitem__("narration", "x"),
                   lambda c: c["formats"]["short"]["shots"][shot_id(v1, "short", "BEAT_S01")]["cast"]["CHR_LENA"].__setitem__("performance", "fly"),
                   lambda c: c["formats"]["long"]["scenes"].clear()):
        choices = copy.deepcopy(v1["manifest"]["choices"])
        mutate(choices)
        with pytest.raises(ScenePlanError) as exc:
            save(store, v1, choices)
        assert exc.value.code == "invalid_choice"
    assert tree(store.root / "fx") == snapshot


def test_immutable_versions_reapproval_and_stale_inputs(store):
    view = approved(store)
    assert view["ready_for_next_stage"] and view["approval"]["approval_scope"] == "scene_plan_only"
    assert view["package"]["review_status"] == "pending_explicit_scene_plan_approval"  # The file cannot approve itself.
    assert approve_scene_plan(store, "fx", view["version"], view["package_sha256"], view["manifest_sha256"])["status"] == "already_approved"
    assert prepare_scene_plan(store, "fx", {})["status"] == "already_prepared"
    handoff = scene_plan_handoff(store, "fx")
    assert handoff["retiming_contract"]["status"] == "awaiting_p3_5_measured_narration"
    assert len(handoff["retiming_contract"]["narration_units"]) == 21
    for fmt in ("short", "long"):
        ir = handoff["formats"][fmt]["provisional_action_timeline"]
        assert ir["metadata"]["renderable"] is False and len(ir["scenes"]) == len(view["package"]["formats"][fmt]["shots"])
    v1_bytes = (store.root / "fx" / OUTPUT_DIR / "v1/scene_plan.json").read_bytes()
    # A newer Visual Bible makes the approved plan stale and its handoff unavailable.
    vb = read_visual_bible(store, "fx")
    choices = copy.deepcopy(vb["manifest"]["choices"])
    choices["locations"]["LOC_HALL"]["flicker_lamp"] = "lamp_west"
    new_vb = prepare_visual_bible(store, "fx", {"base_version": vb["version"], "package_sha256": vb["package_sha256"],
                                               "manifest_sha256": vb["manifest_sha256"], "choices": choices})
    assert not read_scene_plan(store, "fx")["is_current"]
    with pytest.raises(ScenePlanError, match="current approved"):
        scene_plan_handoff(store, "fx")
    with pytest.raises(ScenePlanError) as exc:
        prepare_scene_plan(store, "fx", {})
    assert exc.value.code == "visual_not_ready"
    approve_visual_bible(store, "fx", new_vb["version"], new_vb["package_sha256"], new_vb["manifest_sha256"])
    with pytest.raises(ScenePlanError) as exc:
        approve_scene_plan(store, "fx", view["version"], view["package_sha256"], view["manifest_sha256"])
    assert exc.value.code == "stale_plan"
    rebased = prepare_scene_plan(store, "fx", {})
    assert rebased["version"] == "v3" and rebased["package"]["inputs"]["visual_bible"]["version"] == new_vb["version"]
    assert any("UNREVIEWED_SCENE" in b for b in rebased["package"]["blockers"])  # Reviews never carry over.
    assert rebased["manifest"]["choices"]["formats"]["long"]["shots"][shot_id(rebased, "long", "BEAT_L05")]["props"][
        "OBJ_ROOM_DOOR"] == "reach_then_opened_across_cut"  # Staging carries over.
    assert read_scene_plan(store, "fx", "v2")["approval"] and not read_scene_plan(store, "fx", "v2")["ready_for_next_stage"]
    assert (store.root / "fx" / OUTPUT_DIR / "v1/scene_plan.json").read_bytes() == v1_bytes
    # A newer story decision makes even a fresh plan stale (canon not ready until re-approved).
    target = next(t for t in current_decisions(load_log(store.root / "fx")).values() if t["target_id"] == "MOT_THREE_KNOCKS")
    record_decision(store, "fx", {"target_id": "MOT_THREE_KNOCKS", "decision": "reject", "supersedes": target["decision_id"]})
    assert not read_scene_plan(store, "fx")["is_current"] and not read_scene_plan(store, "fx")["canonical_ready"]
    with pytest.raises(ScenePlanError) as exc:
        prepare_scene_plan(store, "fx", {})
    assert exc.value.code == "canonical_not_ready"


def test_unapproved_story_or_visual_bible_cannot_prepare(store, tmp_path):
    prepare(store, approve_story=False)
    with pytest.raises(ScenePlanError) as exc:
        prepare_scene_plan(store, "fx", {})
    assert exc.value.code == "canonical_not_ready"
    other = ProductionStore(tmp_path / "other", ApprovedPackages(ROOT))
    prepare(other, approve_visual=False)
    with pytest.raises(ScenePlanError) as exc:
        prepare_scene_plan(other, "fx", {})
    assert exc.value.code == "visual_not_ready"
    for s in (store, other):
        assert not (s.root / "fx" / OUTPUT_DIR).exists()


@pytest.mark.parametrize("damage", ["plan", "manifest", "approval", "renumber", "asset_revision"])
def test_tampered_history_is_refused_without_overwrite(store, damage, monkeypatch):
    approved(store)
    folder = store.root / "fx" / OUTPUT_DIR
    if damage == "plan":
        path = folder / "v2/scene_plan.json"
        path.write_bytes(path.read_bytes().replace(b"Lena sat alone", b"Lena sat ALONE"))
    elif damage == "manifest":
        path = folder / "v1/manifest.json"
        data = json.loads(path.read_bytes()); data["created_at"] = "x"; path.write_text(json.dumps(data), encoding="utf-8")
    elif damage == "approval":
        path = folder / "v2/approval.json"
        data = json.loads(path.read_bytes()); data["approval_scope"] = "production"; path.write_text(json.dumps(data), encoding="utf-8")
    elif damage == "renumber":
        (folder / "v1").rename(folder / "v9")
    else:
        from tools.character import horror_assets
        monkeypatch.setitem(horror_assets.REVISION_HASHES, ("acting", "guarded_reach", 1), "0" * 64)
    snapshot = tree(store.root / "fx")
    # A changed asset fingerprint is already refused by the pinned Visual Bible verification.
    with pytest.raises(VisualBibleError if damage == "asset_revision" else ScenePlanError) as exc:
        read_scene_plan(store, "fx")
    assert exc.value.code == ("visual_invalid" if damage == "asset_revision" else "plan_invalid")
    assert tree(store.root / "fx") == snapshot


def test_independent_coverage_check_detects_omission_and_rewrite(store):
    prepare(store)
    plan = prepare_scene_plan(store, "fx", {})["package"]
    reviewed = read_reviewed_story(store, "fx")["package"]
    assert not planner.coverage(plan, reviewed)["blockers"]
    dropped = copy.deepcopy(plan)
    long = dropped["formats"]["long"]
    victim = shots(dropped, "long", "narrative")[7]  # BEAT_L08 carries a dialogue line and its source paragraph.
    long["shots"] = [s for s in long["shots"] if s["shot_id"] != victim["shot_id"]]
    for sc in long["scenes"]:
        sc["shot_ids"] = [x for x in sc["shot_ids"] if x != victim["shot_id"]]
    found = planner.coverage(dropped, reviewed)["blockers"]
    assert any("missing beats BEAT_L08" in b for b in found)
    assert any("LONG_SOURCE_OMITTED" in b and "SEG_0009" in b for b in found)
    assert any("DLG_HEARD" in b for b in found)
    rewritten = copy.deepcopy(plan)
    shots(rewritten, "short", "narrative")[0]["source"]["narration"]["text"] = "A ghost knocked."
    assert any("source fields changed for BEAT_S01" in b for b in planner.coverage(rewritten, reviewed)["blockers"])


def test_provisional_timing_and_p35_retiming_contract(store):
    prepare(store)
    plan = prepare_scene_plan(store, "fx", {})["package"]
    for fmt in ("short", "long"):
        fp = plan["formats"][fmt]
        assert fp["timing"]["status"] == "provisional_estimate_pending_measured_narration"
        assert "Estimate only" in fp["timing"]["estimate_basis"] and "low confidence" in fp["timing"]["estimate_basis"]
        frames = 0
        for s in fp["shots"]:
            t = s["timing"]
            assert t["status"] == "provisional_estimate" and t["frame_grid"]["estimated_start_frame"] == frames
            assert t["estimated_seconds"] == round(t["frame_grid"]["estimated_frame_count"] / 30, 4)
            frames += t["frame_grid"]["estimated_frame_count"]
            assert t["pending_measurement"]["required"] == (s["kind"] == "narrative")
            assert t["estimated_seconds"] >= t["action"]["minimum_seconds"]
        assert abs(fp["timing"]["estimated_seconds"] - frames / 30) < 1e-3
    assert plan["formats"]["short"]["timing"]["target"]["enforced"] is False
    owen = next(s for s in shots(plan, "long", "narrative") if s["source"]["beat_id"] == "BEAT_L07")
    assert owen["timing"]["action"]["minimum_seconds"] > owen["timing"]["narration"]["estimated_seconds"] + 1
    # Only a current approved view and a bound envelope may be retimed; these numbers are not audio.
    current = read_scene_plan(store, "fx")
    current = save(store, current, resolved_choices(current))
    current = approve_scene_plan(store, "fx", current["version"], current["package_sha256"], current["manifest_sha256"])
    plan = current["package"]
    measured = synthetic_measurements(current, "short")
    timeline = planner.retime(plan, "short", measured, approved=current)
    assert [t["shot_id"] for t in timeline["shots"]] == [s["shot_id"] for s in shots(plan, "short")]
    ir = planner.action_timeline(plan, "short", timeline, approved=current)
    assert ir["metadata"]["timing_status"] == "synthetic_test_not_measured_audio"
    broken = copy.deepcopy(measured); broken["units"][0]["text_sha256"] = "0" * 64
    with pytest.raises(ScenePlanError, match="text hashes"):
        planner.retime(plan, "short", broken, approved=current)
    missing = copy.deepcopy(measured); missing["units"].pop()
    with pytest.raises(ScenePlanError, match="exactly"):
        planner.retime(plan, "short", missing, approved=current)
    assert not list(store.root.rglob("*.wav"))
    # The measured-WAV planner API is unchanged; P3.4 does not feed it estimates.
    assert list(inspect.signature(story_planner.plan_story).parameters) == ["analysis", "narration"]


def test_schema_rejects_approval_flags_and_identity_reveal(store):
    prepare(store)
    plan = prepare_scene_plan(store, "fx", {})["package"]
    schema = json.loads(planner.SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    assert not list(validator.iter_errors(plan))
    for path, value in ((("tts_started",), True), (("publishing_enabled",), True),
                        (("review_status",), "approved"), (("approval_scope",), "production")):
        bad = copy.deepcopy(plan); bad[path[0]] = value
        assert list(validator.iter_errors(bad))
    bad = copy.deepcopy(plan)
    presence = next(s for s in shots(bad, "long") if s["staging"]["presence"])
    presence["staging"]["presence"]["identity_revealed"] = True
    assert list(validator.iter_errors(bad))


def test_studio_api_routes_and_local_origin(store):
    prepare(store)
    client = TestClient(create_app(store), base_url="http://127.0.0.1")
    base = "/studio/api/productions/fx/scene-plan"
    assert client.get(base).json()["state"] == "missing"
    assert client.post(base, json={}, headers={"origin": "http://evil.example"}).status_code == 403
    created = client.post(base, json={})
    assert created.status_code == 201 and created.json()["version"] == "v1"
    view = created.json()
    assert client.get(f"{base}/handoff").status_code == 409
    report = client.get(f"{base}/v1/report").json()
    assert report["markdown"].startswith("# Story-to-shot coverage") and "Retained story text narrated" in report["markdown"]
    assert client.post(f"{base}/v1/approve", json={"package_sha256": "x"}).status_code == 422
    blocked = client.post(f"{base}/v1/approve", json={"package_sha256": view["package_sha256"],
                                                     "manifest_sha256": view["manifest_sha256"]})
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "approval_blocked"
    saved = client.post(base, json={"base_version": "v1", "package_sha256": view["package_sha256"],
                                    "manifest_sha256": view["manifest_sha256"], "choices": resolved_choices(view)})
    assert saved.status_code == 201
    stale = client.post(base, json={"base_version": "v1", "package_sha256": view["package_sha256"],
                                    "manifest_sha256": view["manifest_sha256"], "choices": resolved_choices(view)})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "stale_plan"
    v2 = saved.json()
    ok = client.post(f"{base}/v2/approve", json={"package_sha256": v2["package_sha256"], "manifest_sha256": v2["manifest_sha256"]})
    assert ok.status_code == 200 and ok.json()["ready_for_next_stage"]
    assert client.get(f"{base}/handoff").status_code == 200
    assert client.get(f"{base}/v9").status_code == 404 and client.get(f"{base}/bad").status_code == 422
    assert client.get(base).headers["cache-control"] == "no-store"
    assert client.get("/studio/api/productions/Bad_ID/scene-plan").status_code == 422
    assert client.get("/studio/api/productions/missing-project/scene-plan").status_code == 404
    assert client.post("/studio/api/productions/missing-project/scene-plan", json={}).status_code == 404


def test_story_text_is_english_only_synthetic_fixture():
    assert "[SYNTHETIC TEST]" in STORY and not re.search("[\u00c0-\u1ef9]", STORY)  # English fixture.
    assert hashlib.sha256(STORY.encode()).hexdigest()  # Fixture only; no private draft is read.
