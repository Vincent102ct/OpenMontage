"""M2.3 contract/graph/timing failures, generic compilation and read-only CLI.

Tests use explicit synthetic PCM fixtures, never claim generated speech quality.
The separate pilot CLI run verifies the existing real M2.2 audio.
"""
import copy
import json
import subprocess
import sys
import wave
from pathlib import Path

import pytest

from lib import master_story as ms
from lib import master_story_short as mss
from lib import visual_scene_plan as vsp

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "examples/master-story/lead-masks-1966/master_story.json"
BRIEF = PILOT.with_name("short_visual_brief.json")


def _wav(path, samples):
    with wave.open(str(path), "wb") as f:
        f.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        f.writeframes(b"\x10\x00" * samples)
    return path


def _manifest(package, folder, counts):
    beats = mss.canonical_beats(package)
    paths = {b["segment_id"]: _wav(folder / (b["segment_id"]+".wav"), n) for b, n in zip(beats, counts)}
    timed = mss.build_timeline(beats, paths)
    track = folder / "narration.wav"
    mss.write_concatenated_wav(timed, track)
    def clock(seconds):
        milliseconds = round(seconds*1000)
        return f"{milliseconds//3600000:02}:{milliseconds//60000%60:02}:{milliseconds//1000%60:02},{milliseconds%1000:03}"
    srt = "\n\n".join(f"{i}\n{clock(c['start'])} --> {clock(c['end'])}\n{c['text']}"
                       for i, c in enumerate(mss.subtitle_segments(timed), 1)) + "\n"
    subtitles = folder / "subtitles.srt"
    subtitles.write_text(srt, encoding="utf-8")
    return {"schema_version": "1.0", "package_id": package["package_id"], "package_version": package["package_version"],
        "language": package["language"], "format": "short", "aspect_ratio": "9:16",
        "tts": {"provider": "synthetic_test_fixture", "tool": "no_synthesis", "settings": {}}, **timed,
        "narration_track": {"path": str(track), "sha256": mss.sha256(track)},
        "subtitles": {"path": str(subtitles), "sha256": mss.sha256(subtitles)},
        "approvals": {k: vsp.PENDING for k in ("factual", "publication", "listening")}}, srt


@pytest.fixture(scope="module")
def pilot_data(tmp_path_factory):
    package, brief = ms.load(PILOT), ms.load(BRIEF)
    timed, srt = _manifest(package, tmp_path_factory.mktemp("visual-pilot"), [293448, 239295, 283219, 323951])
    return package, timed, brief, srt


@pytest.fixture
def data(pilot_data):
    return copy.deepcopy(pilot_data)


@pytest.fixture
def plan(data):
    return vsp.build_plan(*data)


def test_pilot_has_meaningful_shots_covering_exact_measured_total(data, plan):
    report = vsp.validate_plan(plan, *data)
    assert report["status"] == "technical_pass"
    assert report["scenes"] == 11 and report["total_seconds"] == 49.496375
    assert report["claims"] == 11 and report["sources"] == 11
    assert [sum(s["segment_id"] == sid for s in plan["scenes"]) for sid in report["segments"]] == [3, 2, 3, 3]
    assert report["coverage"] == {"start_seconds": 0, "end_seconds": 49.496375, "gaps": [], "overlaps": []}
    durations = {round(s["end_seconds"]-s["start_seconds"], 3) for s in plan["scenes"]}
    assert len(durations) > 5  # Meaning/cue boundaries, not equal-duration partitions.


def test_all_original_text_and_claim_mappings_are_preserved(data, plan):
    for beat in data[1]["beats"]:
        scenes = [s for s in plan["scenes"] if s["segment_id"] == beat["segment_id"]]
        assert "".join(s["narration"]["text"] for s in scenes) == beat["text"]
        assert {c for s in scenes for c in s["claim_ids"]} == set(beat["claim_ids"])
        assert all(set(s["claim_ids"]) <= set(beat["claim_ids"]) for s in scenes)
    assert plan["scenes"][5]["narration"]["text"].strip() == "Mười tám giờ ba mươi: uống viên nang."
    assert plan["timing"]["word_alignment_verified"] is False


def test_pauses_are_explicit_holds_not_missing_visual_time(data, plan):
    assert plan["scenes"][0]["start_seconds"] == 0
    assert plan["scenes"][0]["narration"]["start_seconds"] == .3
    assert plan["scenes"][2]["end_seconds"] == data[1]["beats"][1]["start_seconds"]
    assert plan["scenes"][-1]["end_seconds"]-plan["scenes"][-1]["narration"]["end_seconds"] == .5


def test_every_reference_and_status_is_from_the_canon(data, plan):
    context = ms.resolve_format(data[0], "short")
    for key in vsp.CANON_FIELDS:
        assert plan["canon"][key] == context[key]
    canonical = {c["id"]: c for c in data[0]["claims"]}
    for scene in plan["scenes"]:
        assert scene["historical_evidence"] == [canonical[c] for c in scene["claim_ids"]]
        expected = {s for c in scene["claim_ids"] for s in canonical[c]["supporting_source_ids"]+canonical[c].get("contradicting_source_ids", [])}
        assert set(scene["source_ids"]) == expected


def test_assets_remain_unresolved_and_human_rules_stay_pending(data, plan):
    assert plan["continuity_review"] == {r: vsp.PENDING for r in ("CR_006", "CR_007", "CR_008", "CR_010")}
    assert set(plan["approvals"].values()) == {vsp.PENDING}
    for s in plan["scenes"]:
        assert s["purpose"].strip() and s["review_status"] == vsp.PENDING
        for asset in s["asset_requirements"]:
            assert asset["status"] == "unresolved" and asset["resolved_asset"] is None
            assert not {"url", "path", "license", "creator", "publisher"} & set(asset)
    assert plan["source_priority"] == vsp.SOURCE_PRIORITY


def test_determinism_and_no_input_mutation(data):
    before = copy.deepcopy(data)
    a, b = vsp.build_plan(*data), vsp.build_plan(*data)
    assert data == before
    assert vsp.content_hash(a) == vsp.content_hash(b)
    a["canon"]["claims"][0]["text"] = "Changed output only"
    assert data == before


@pytest.mark.parametrize("field,value", [("start_seconds", .1), ("end_seconds", 100), ("end_seconds", -1)])
def test_visual_timing_outside_contract_is_rejected(data, plan, field, value):
    plan["scenes"][0][field] = value
    with pytest.raises(vsp.VisualScenePlanError):
        vsp.validate_plan(plan, *data)


@pytest.mark.parametrize("delta", [-.01, .01])
def test_gaps_and_overlaps_rejected(data, plan, delta):
    plan["scenes"][1]["start_seconds"] += delta
    with pytest.raises(vsp.VisualScenePlanError, match="COVERAGE"):
        vsp.validate_plan(plan, *data)


@pytest.mark.parametrize("change", ["segment", "text", "claim", "source", "entity", "event", "status", "qualifier", "audio", "start", "speech", "package", "selection", "nan"])
def test_input_manifest_and_canonical_drift_is_rejected(data, change):
    package, timed, brief, srt = data
    beat = timed["beats"][0]
    if change == "segment": beat["segment_id"] = "SEG_FAKE"
    elif change == "text": beat["text"] += " Invented narration."
    elif change == "claim": beat["claim_ids"] = ["CLM_999"]
    elif change == "source": beat["source_ids"].append("SRC_999")
    elif change == "entity": beat["entity_ids"]["characters"] = []
    elif change == "event": beat["event_ids"] = []
    elif change == "status": beat["claims"][1]["status"] = "DOCUMENTED_FACT"
    elif change == "qualifier": beat["claims"][0]["qualifier"] = "Approved"
    elif change == "audio": beat["audio"]["samples"] += 100
    elif change == "start": beat["start_seconds"] += .1
    elif change == "speech": timed["speech_seconds"] += 1
    elif change == "package": timed["package_version"] = "v2"
    elif change == "selection": package["formats"]["short"]["segment_ids"] = ["SEG_01", "SEG_02", "SEG_03", "SEG_45"]
    elif change == "nan": beat["audio"]["duration_seconds"] = float("nan")
    with pytest.raises((vsp.VisualScenePlanError, ms.MasterStoryError)):
        vsp.build_plan(package, timed, brief, srt)


@pytest.mark.parametrize("change", ["duplicate", "missing", "reorder", "bad_cue", "cue_gap", "cue_overlap", "segment", "claim", "entity", "event", "grounding", "dropped_claim"])
def test_bad_brief_references_or_coverage_rejected(data, change):
    directions = data[2]["directions"]
    if change == "duplicate": directions[1]["id"] = directions[0]["id"]
    elif change == "missing": directions.pop()
    elif change == "reorder": directions[0], directions[1] = directions[1], directions[0]
    elif change == "bad_cue": directions[0]["cue_end"] = 99
    elif change == "cue_gap": directions[2]["cue_start"] = 4
    elif change == "cue_overlap": directions[1]["cue_start"] = 1
    elif change == "segment": directions[0]["segment_id"] = "SEG_FAKE"
    elif change == "claim": directions[0]["claim_ids"] = ["CLM_FAKE"]
    elif change == "entity": directions[0]["required_elements"][0]["entity_id"] = "LOC_FAKE"
    elif change == "event": directions[0]["event_ids"] = ["EVT_FAKE"]
    elif change == "grounding": directions[1]["claim_ids"] = ["CLM_010"]
    elif change == "dropped_claim": directions[1]["claim_ids"].remove("CLM_002")
    with pytest.raises(vsp.VisualScenePlanError):
        vsp.build_plan(*data)


@pytest.mark.parametrize("change", ["claim", "source", "entity", "event", "status", "narration", "offset", "asset_license", "asset_url", "resolved", "approval", "rule_approved", "rule_deleted", "context", "fingerprint"])
def test_stored_plan_cannot_drift_or_approve_itself(data, plan, change):
    scene = plan["scenes"][0]
    if change == "claim": scene["claim_ids"] = ["CLM_FAKE"]
    elif change == "source": scene["source_ids"] = ["SRC_FAKE"]
    elif change == "entity": scene["entity_ids"] = ["LOC_FAKE"]
    elif change == "event": scene["event_ids"] = ["EVT_FAKE"]
    elif change == "status": scene["historical_evidence"][0]["status"] = "UNKNOWN"
    elif change == "narration": scene["narration"]["text"] = "Invented line."
    elif change == "offset": scene["narration"]["char_end"] += 1
    elif change == "asset_license": scene["asset_requirements"][0]["license"] = "CC0"
    elif change == "asset_url": scene["asset_requirements"][0]["url"] = "https://example.invalid/fake.jpg"
    elif change == "resolved": scene["asset_requirements"][0]["resolved_asset"] = {"path": "fake.jpg"}
    elif change == "approval": plan["approvals"]["factual"] = "approved"
    elif change == "rule_approved": plan["continuity_review"]["CR_006"] = "approved"
    elif change == "rule_deleted": del plan["continuity_review"]["CR_006"]
    elif change == "context": plan["canon"]["sources"][0]["title"] = "New source"
    elif change == "fingerprint": plan["inputs"]["timed_manifest_content_sha256"] = "0"*64
    with pytest.raises(vsp.VisualScenePlanError):
        vsp.validate_plan(plan, *data)


@pytest.mark.parametrize("index", [0, 2])
def test_context_or_illustration_needs_visible_classification(data, index):
    data[2]["directions"][index]["on_screen_text"] = []
    with pytest.raises(vsp.VisualScenePlanError, match="LABEL"):
        vsp.build_plan(*data)


def test_future_reconstruction_is_explicit_unresolved_and_pending(data):
    d = data[2]["directions"][2]
    d["representation"] = "reconstruction"
    d["asset_requests"][0]["preferred_category"] = "ai_reconstruction_future_fallback"
    d["on_screen_text"][0]["text"] = "Reconstruction — not evidence"
    plan = vsp.build_plan(*data)
    vsp.validate_plan(plan, *data)
    assert "reconstruction_not_documentary_evidence" in plan["scenes"][2]["risk_flags"]
    assert plan["scenes"][2]["asset_requirements"][0]["status"] == "unresolved"
    d["representation"] = "authentic_evidence"
    with pytest.raises(vsp.VisualScenePlanError, match="RECONSTRUCTION"):
        vsp.build_plan(*data)


def test_long_is_reserved_but_not_implemented(data):
    data[1]["format"], data[1]["aspect_ratio"] = "long", "16:9"
    with pytest.raises(vsp.VisualScenePlanError, match="Long planning is not implemented"):
        vsp.build_plan(*data)


def test_unrelated_english_package_runs_without_pilot_ids(data, tmp_path):
    package = data[0]
    # Retain schema-valid records but select a neutral independent narrative.
    package["package_id"], package["title"] = "STORY_900", "Neutral marker fixture"
    package["language"] = "en"
    package["sources"] = [{"id": "SRC_A", "title": "Fixture record", "reference": "test only", "source_type": "fixture",
                            "reliability": "primary", "verification": {"status": "not_checked", "checked_on": "2026-10-22", "method": "fixture"}}]
    package["claims"] = [{"id": "CLM_A", "text": "A marker was reported.", "status": "REPORTED_ACCOUNT", "supporting_source_ids": ["SRC_A"]}]
    package["timeline"] = []
    package["entities"] = {"characters": [], "locations": [], "objects": [{"id": "OBJ_A", "name": "Marker", "claim_ids": ["CLM_A"]}]}
    package["continuity_rules"] = [{"id": "CR_A", "check": "human_review", "claim_ids": ["CLM_A"], "description": "Report, not independently verified fact."}]
    package["master_narrative"]["segments"] = [{"id": "SEG_A", "role": "body", "text": "A marker was reported. Its appearance needs review.",
        "claim_ids": ["CLM_A"], "entity_ids": ["OBJ_A"], "source_ids": ["SRC_A"], "event_ids": [], "estimated_seconds": 48}]
    for fmt in package["formats"].values():
        fmt["package_id"], fmt["segment_ids"] = "STORY_900", ["SEG_A"]
    timed, srt = _manifest(package, tmp_path, [48*24000])
    d = copy.deepcopy(data[2]["directions"][2])
    d.update(id="SC_901", segment_id="SEG_A", cue_start=1, cue_end=2, claim_ids=["CLM_A"], event_ids=[],
             required_elements=[{"entity_id": "OBJ_A", "visual_constraint": "Neutral fixture only"}])
    brief = {"schema_version": "1.0", "package_id": "STORY_900", "package_version": "v1", "format": "short", "directions": [d]}
    plan = vsp.build_plan(package, timed, brief, srt)
    assert vsp.validate_plan(plan, package, timed, brief, srt)["scenes"] == 1
    assert plan["language"] == "en"
    assert plan["scenes"][0]["source_ids"] == ["SRC_A"] and plan["continuity_review"] == {"CR_A": vsp.PENDING}


def test_real_file_verification_detects_hash_mismatch(data):
    data[1]["beats"][0]["audio"]["sha256"] = "0"*64
    with pytest.raises(vsp.VisualScenePlanError, match="FILE_HASH"):
        vsp.verify_timed_files(data[0], data[1], ROOT)


def test_cli_verifies_reads_and_writes_only_review_artifacts(data, tmp_path):
    paths = [tmp_path / name for name in ("package.json", "timed.json", "brief.json")]
    for path, value in zip(paths, data[:3]):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    before = {p: mss.sha256(p) for p in paths}
    out = tmp_path / "review output"
    cmd = [sys.executable, str(ROOT / "scripts/visual_scene_plan.py"), *map(str, paths), "--output-dir", str(out)]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert {p: mss.sha256(p) for p in paths} == before
    report = ms.load(out / "validation_report.json")
    assert report["input_files"]["file_hashes_verified"] == 6 and report["input_files"]["wav_files_measured"] == 5
    assert all(g["pass"] for g in report["input_files"]["M2.2_gates"].values())
    assert {p.suffix for p in out.iterdir()} == {".json", ".md"}
    original = {p.name: p.read_bytes() for p in out.iterdir()}
    stored_plan = ms.load(out / "visual_scene_plan.json")
    assert ms.load(out / "asset_requirements.json")["requirements"] == [
        a for s in stored_plan["scenes"] for a in s["asset_requirements"]]
    repeat = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert repeat.returncode == 0 and {p.name: p.read_bytes() for p in out.iterdir()} == original


def test_invalid_srt_is_not_silently_repaired(data):
    with pytest.raises(vsp.VisualScenePlanError, match="SUBTITLES"):
        vsp.build_plan(*data[:3], data[3].replace("Brazil", "Rewritten"))


def test_srt_interior_time_cannot_change_under_an_old_hash(data):
    with pytest.raises(vsp.VisualScenePlanError, match="SUBTITLES_HASH"):
        vsp.build_plan(*data[:3], data[3].replace("00:00:03,873", "00:00:03,880"))


def test_srt_crlf_and_lf_readings_preserve_the_same_plan(data):
    assert vsp.build_plan(*data) == vsp.build_plan(*data[:3], data[3].replace("\n", "\r\n"))


def test_m231_preserves_all_approved_scene_objects_and_entire_timeline(data, plan):
    baseline = ms.load(PILOT.with_name("short_visual_editorial_baseline.json"))
    scenes = {s["id"]: s for s in plan["scenes"]}
    directions = {d["id"]: d for d in data[2]["directions"]}
    for identity, locked in baseline["approved_scenes"].items():
        assert vsp.content_hash(scenes[identity]) == locked["scene_content_sha256"]
        assert vsp.content_hash(directions[identity]) == locked["direction_content_sha256"]
    assert [{key: s[key] for key in ("id", "segment_id", "start_seconds", "end_seconds", "narration")} for s in plan["scenes"]] == baseline["timeline"]


def test_m231_distinguishes_external_options_local_specs_and_fallbacks(plan):
    breakdown = vsp.asset_breakdown(plan)
    assert breakdown["counts"] == {"external_media": 4, "local_graphics": 10, "conditional_fallbacks": 3, "reconstruction_requests": 0}
    assert sum(a["scope"] == "conditional_alternative" for a in breakdown["external_media"]) == 3
    assert breakdown["supported_local_rendering_recipes"] == 0
    assert {a["recipe_status"] for a in breakdown["local_graphics"]} == {"not_implemented"}
    assert breakdown["asset_license_approval"] == vsp.PENDING
    for sid in ("SC_002", "SC_004", "SC_005"):
        scene = next(s for s in plan["scenes"] if s["id"] == sid)
        assert scene["representation"] == "illustration"
        a = scene["asset_requirements"][0]
        assert a["production"]["fallback_for"] == a["alternatives"][0]["id"]
        assert a["alternatives"][0]["status"] == "unresolved" and a["resolved_asset"] is None


def test_m231_progressive_questions_and_distinct_composition(plan):
    scenes = {s["id"]: s for s in plan["scenes"]}
    scene = scenes["SC_009"]
    blocks = [b for b in scene["presentation"]["text_blocks"] if scene["on_screen_text"][b["overlay_index"]]["role"] == "question"]
    assert len(blocks) == 4
    assert all(a["end_offset"] == b["start_offset"] for a, b in zip(blocks, blocks[1:]))
    assert min(b["end_offset"]-b["start_offset"] for b in blocks) >= 1.4
    assert len({scenes[sid]["presentation"]["composition_key"] for sid in ("SC_008", "SC_009", "SC_010")}) == 3
    assert scenes["SC_010"]["on_screen_text"] == []
    assert scenes["SC_010"]["presentation"]["text_blocks"] == []
    instruction = scenes["SC_006"]
    assert instruction["representation"] == "illustration"
    assert any("Bản chép chỉ dẫn" in o["text"] for o in instruction["on_screen_text"])
    assert any("Chưa xác nhận đã uống" in o["text"] for o in instruction["on_screen_text"])


@pytest.mark.parametrize("change", ["subtitle_overlap", "text_outside_safe", "time_overrun", "bad_index", "duplicate_index", "too_many_lines", "tiny_font", "contrast", "simultaneous_questions"])
def test_bad_vertical_design_is_rejected(data, change):
    d = data[2]["directions"][8]
    p = d["presentation"]
    if change == "subtitle_overlap": p["subtitle_reserved"] = dict(p["safe_area"])
    elif change == "text_outside_safe": p["text_blocks"][1]["box"]["x"] = 0
    elif change == "time_overrun": p["text_blocks"][1]["end_offset"] = 100
    elif change == "bad_index": p["text_blocks"][1]["overlay_index"] = 99
    elif change == "duplicate_index": p["text_blocks"][1]["overlay_index"] = 0
    elif change == "too_many_lines": p["text_blocks"][1]["line_height_px"] = 200
    elif change == "tiny_font": p["text_blocks"][1]["font_size_px"] = 10
    elif change == "contrast": p["text_color"] = p["background_color"]
    elif change == "simultaneous_questions": p["text_blocks"][2]["start_offset"] = .5
    with pytest.raises(vsp.VisualScenePlanError):
        vsp.build_plan(*data)


@pytest.mark.parametrize("change", ["dangling_fallback", "wrong_kind", "fake_recipe_ready", "fake_license", "fake_url", "alternative_resolved", "no_separate_approval", "duplicate_option"])
def test_false_production_readiness_or_alternative_metadata_is_rejected(data, change):
    request = data[2]["directions"][1]["asset_requests"][0]
    if change == "dangling_fallback": request["production"]["fallback_for"] = "ALT_MISSING"
    elif change == "wrong_kind": request["production"]["kind"] = "external_media"
    elif change == "fake_recipe_ready": request["production"]["recipe_status"] = "implemented"
    elif change == "fake_license": request["alternatives"][0]["license"] = "CC0"
    elif change == "fake_url": request["alternatives"][0]["url"] = "https://example.invalid/imaginary-original.jpg"
    elif change == "alternative_resolved": request["alternatives"][0]["status"] = "resolved"
    elif change == "no_separate_approval": request["alternatives"][0]["separate_approval_required"] = False
    elif change == "duplicate_option": request["alternatives"].append(copy.deepcopy(request["alternatives"][0]))
    with pytest.raises(vsp.VisualScenePlanError):
        vsp.build_plan(*data)


def test_final_attribution_corrections_reach_plan_and_asset_export(data, plan):
    scenes = {s["id"]: s for s in plan["scenes"]}
    first = scenes["SC_001"]
    assert first["asset_requirements"][0]["media_type"] == "context_art"
    assert "1892" in first["shot"]["subject"]
    assert "không phải ảnh" in first["on_screen_text"][1]["text"]
    assert "chưa xác minh" in first["asset_requirements"][0]["description"]
    assert scenes["SC_002"]["on_screen_text"][2]["text"].splitlines() == [
        "Boletim 535 [SRC_001]", "Laudo 29.375 [SRC_002]", "Diário de Notícias [SRC_004]"]
    note = scenes["SC_005"]
    assert note["on_screen_text"][2]["text"].splitlines() == [
        "Boletim 535 [SRC_001]", "Diário de Notícias [SRC_004]", "Rede Globo [SRC_009] — chưa truy cập được"]
    assert "verification.status=unreachable" in note["asset_requirements"][0]["description"]
    assert next(s for s in plan["canon"]["sources"] if s["id"] == "SRC_009")["verification"] == next(
        s for s in data[0]["sources"] if s["id"] == "SRC_009")["verification"]
    pause = scenes["SC_010"]
    assert "Nhịp dừng biên tập" in pause["shot"]["setting"]
    assert pause["shot"]["type"] == "visual_pause"
    assert "không chữ" in pause["asset_requirements"][0]["description"]
    assert pause["on_screen_text"] == pause["presentation"]["text_blocks"] == []
    exported = vsp.storyboard_markdown(plan)
    assert "context_art" in exported and "SRC_009] — chưa truy cập được" in exported


@pytest.mark.parametrize("change", ["overlay", "entity", "photo", "reconstruction", "no_layout"])
def test_unlabelled_visual_pause_cannot_hide_evidence_or_overlays(data, change):
    pause = data[2]["directions"][9]
    if change == "overlay": pause["on_screen_text"] = [{"text": "Nhịp dừng biên tập", "role": "evidence_label", "placement": "top"}]
    elif change == "entity": pause["required_elements"] = [{"entity_id": "OBJ_CAPSULES", "visual_constraint": "test"}]
    elif change == "photo": pause["asset_requests"][0]["media_type"] = "historical_photo"
    elif change == "reconstruction": pause["representation"] = "reconstruction"
    elif change == "no_layout": del pause["presentation"]
    with pytest.raises(vsp.VisualScenePlanError):
        vsp.build_plan(*data)
