"""Canonical Short narration: mapping, gates, timing/subtitles and provider language (no real TTS)."""
import copy
import json
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from lib import master_story as ms
from lib import master_story_short as mss
from scripts import master_story_short as driver
from scripts import story_to_video as stv
from tools.base_tool import ToolResult

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "examples/master-story/lead-masks-1966/master_story.json"


def _wav(path: Path, seconds: float, rate: int = 24000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\x10\x00" * int(seconds * rate))
    return path


def _subtitle_gen():
    from tools.subtitle.subtitle_gen import SubtitleGen
    return SubtitleGen()


def _timed(package, tmp_path, seconds=8.0):
    beats = mss.canonical_beats(package)
    wavs = {b["segment_id"]: _wav(tmp_path / f"{b['segment_id']}.wav", seconds) for b in beats}
    return mss.build_timeline(beats, wavs)


def _srt(timed, tmp_path, words_per_cue=1):
    out = tmp_path / "s.srt"
    result = _subtitle_gen().execute({"segments": mss.subtitle_segments(timed), "format": "srt",
                                      "output_path": str(out), "max_words_per_cue": words_per_cue,
                                      "max_chars_per_line": 1 if words_per_cue == 1 else 100_000})
    assert result.success
    return out.read_text(encoding="utf-8")


def synthetic_package(language="en", text="Marker"):
    """Neutral two-segment package (not STORY 053) used to prove the flow is generic."""
    segments = [{"id": f"SEG_{i}", "role": "body", "text": f"{text} {i} was reported. Nothing else is known.",
                 "claim_ids": ["CLM_1", "CLM_2"], "entity_ids": ["OBJ_1"], "event_ids": ["EVT_1"],
                 "source_ids": ["SRC_1"], "estimated_seconds": 24.0} for i in (1, 2)]
    plan = lambda kind, ratio, low, high: {"format": kind, "package_id": "STORY_900", "package_version": "v1",
                                           "aspect_ratio": ratio, "target_seconds": {"min": low, "max": high},
                                           "segment_ids": ["SEG_1", "SEG_2"]}
    return {"schema_version": "1.0", "package_id": "STORY_900", "package_version": "v1", "title": "Synthetic",
            "language": language, "case": {"name": "Synthetic", "place": "Nowhere", "year": 2000},
            "sources": [{"id": "SRC_1", "title": "Synthetic record", "reference": "fixture", "source_type": "fixture",
                         "reliability": "primary", "verification": {"status": "not_checked", "checked_on": "2026-10-22",
                                                                   "method": "fixture"}}],
            "claims": [{"id": "CLM_1", "text": "A marker was reported.", "status": "REPORTED_ACCOUNT",
                        "supporting_source_ids": ["SRC_1"], "qualifier": "Account only.", "event_id": "EVT_1"},
                       {"id": "CLM_2", "text": "Nothing else is known.", "status": "UNKNOWN", "supporting_source_ids": []}],
            "timeline": [{"id": "EVT_1", "date_start": "2000-01-01", "precision": "day", "description": "Report",
                          "claim_ids": ["CLM_1"]}],
            "entities": {"characters": [], "locations": [], "objects": [{"id": "OBJ_1", "name": "Marker", "claim_ids": ["CLM_1"]}]},
            "continuity_rules": [{"id": "CR_1", "check": "requires_claims", "when_claim_ids": ["CLM_1"],
                                  "require_claim_ids": ["CLM_2"], "description": "Pair the account with the unknown."}],
            "master_narrative": {"segments": segments},
            "formats": {"short": plan("short", "9:16", 45, 60), "long": plan("long", "16:9", 45, 900)}}


# Gate tests use the fixed six-segment M2.2 selection so they do not depend on later editorial choices.
M22_SELECTION = ["SEG_01", "SEG_02", "SEG_03", "SEG_07", "SEG_23", "SEG_45"]


@pytest.fixture
def pilot():
    package = ms.load(PILOT)
    package["formats"]["short"]["segment_ids"] = list(M22_SELECTION)
    return package


# --- M2.2.1 editorial selection on the real package -------------------------------------------

def test_package_short_is_the_m221_selection_with_full_claim_coverage():
    package = ms.load(PILOT)
    summary = ms.validate_package(package)
    short = package["formats"]["short"]
    assert short["segment_ids"] == ["SEG_01", "SEG_02", "SEG_19", "SEG_45"]
    assert [s["id"] for s in package["master_narrative"]["segments"]] == package["formats"]["long"]["segment_ids"]
    old = {**short, "segment_ids": M22_SELECTION}
    assert ms.format_claims(package, short) == ms.format_claims(package, old)  # no claim lost vs. M2.2
    beats = mss.canonical_beats(package)
    assert [b["role"] for b in beats] == ["hook", "hook", "note", "ending"]
    assert not ms._rule_problems(package, ms.format_claims(package, short), "short")
    assert any(w.startswith("DURATION_ESTIMATE short") for w in summary["warnings"])


def test_human_review_rules_stay_pending(tmp_path):
    package = ms.load(PILOT)
    timed = _timed(package, tmp_path, seconds=12)
    gate = mss.quality_gates(package, timed, _srt(timed, tmp_path))["qualifiers_and_continuity"]
    assert gate["pass"] and gate["pass_covers"] == "automatic checks only"
    assert gate["human_review_rules"] and set(gate["human_review_rules"].values()) == {"pending_human_review"}


# --- canonical mapping ----------------------------------------------------------------------

def test_pilot_short_beats_keep_order_text_and_every_reference(pilot):
    beats = mss.canonical_beats(pilot)
    segments = {s["id"]: s for s in pilot["master_narrative"]["segments"]}
    claims = {c["id"]: c for c in pilot["claims"]}
    assert [b["segment_id"] for b in beats] == pilot["formats"]["short"]["segment_ids"]
    for beat in beats:
        seg = segments[beat["segment_id"]]
        assert beat["text"] == seg["text"] and beat["claim_ids"] == seg["claim_ids"]
        assert [c["id"] for c in beat["claims"]] == seg["claim_ids"]
        for c in beat["claims"]:
            assert (c["status"], c.get("qualifier")) == (claims[c["id"]]["status"], claims[c["id"]].get("qualifier"))
        cited = {s for c in beat["claims"] for s in c["supporting_source_ids"] + c["contradicting_source_ids"]}
        assert set(beat["source_ids"]) == cited and set(beat["cited_source_ids"]) <= cited
        assert sorted(sum(beat["entity_ids"].values(), [])) == sorted(seg["entity_ids"])
        assert beat["event_ids"] == seg["event_ids"]
    assert {c for b in beats for c in b["claim_ids"]} == ms.format_claims(pilot, pilot["formats"]["short"])
    assert "CR_001" in {r for b in beats for r in b["continuity_rule_ids"]}


def test_invalid_package_is_rejected_before_narration(pilot):
    pilot["formats"]["short"]["segment_ids"] = ["SEG_01", "SEG_01"]
    with pytest.raises(ms.MasterStoryError):
        mss.canonical_beats(pilot)


# --- language ------------------------------------------------------------------------------

def test_narration_language_is_declared_and_checked_against_text(pilot):
    assert mss.narration_language(pilot) == "vi"
    english = synthetic_package("en")
    assert mss.narration_language(english) == "en"
    mislabelled = copy.deepcopy(pilot)
    mislabelled["language"] = "en"
    with pytest.raises(mss.ShortNarrationError, match="declares en"):
        mss.narration_language(mislabelled)
    with pytest.raises(mss.ShortNarrationError, match="declares vi"):
        mss.narration_language(synthetic_package("vi"))
    with pytest.raises(mss.ShortNarrationError, match="no verified offline"):
        mss.narration_language(synthetic_package("fr"))


# --- gates: segments, text, claims, qualifiers -----------------------------------------------

def test_pilot_gates_pass_for_content_and_timing_with_measured_audio(pilot, tmp_path):
    timed = _timed(pilot, tmp_path)
    gates = mss.quality_gates(pilot, timed, _srt(timed, tmp_path))
    assert all(gates[g]["pass"] for g in gates), gates
    assert gates["duration_target"]["total_seconds"] == pytest.approx(0.3 + 6 * 8 + 5 * 0.4 + 0.5)


def test_missing_and_duplicate_segments_fail(pilot, tmp_path):
    timed = _timed(pilot, tmp_path)
    timed["beats"] = timed["beats"][:2] + [timed["beats"][1]] + timed["beats"][4:]
    gate = mss.quality_gates(pilot, timed, _srt(timed, tmp_path))["segments_complete"]
    assert not gate["pass"] and gate["duplicated"] == ["SEG_02"] and gate["missing"] == ["SEG_03", "SEG_07"]


def test_rewritten_text_and_new_claims_fail(pilot, tmp_path):
    timed = _timed(pilot, tmp_path)
    timed["beats"][0]["text"] += " Extra sentence."
    timed["beats"][1]["claim_ids"].append("CLM_026")
    timed["beats"][1]["source_ids"].append("SRC_013")
    gates = mss.quality_gates(pilot, timed, _srt(timed, tmp_path))
    assert gates["text_verbatim"]["changed"] == ["SEG_01"]
    gate = gates["no_new_claims_or_sources"]
    assert not gate["pass"] and gate["extra_claims"] == ["CLM_026"] and gate["extra_sources"] == ["SRC_013"]


def test_changed_status_or_dropped_qualifier_fails(pilot, tmp_path):
    timed = _timed(pilot, tmp_path)
    claim = timed["beats"][2]["claims"][0]
    claim["status"] = "DOCUMENTED_FACT"
    timed["beats"][0]["claims"][0].pop("qualifier")
    gate = mss.quality_gates(pilot, timed, _srt(timed, tmp_path))["qualifiers_and_continuity"]
    assert not gate["pass"] and claim["id"] in gate["altered_claims"]
    assert timed["beats"][0]["claims"][0]["id"] in gate["altered_claims"]


def test_losing_the_qualifying_segment_breaks_continuity(pilot, tmp_path):
    # SEG_03 and SEG_45 carry CLM_032 ("capsule contents unknown") required by CR_001.
    timed = _timed(pilot, tmp_path)
    timed["beats"] = [b for b in timed["beats"] if b["segment_id"] not in ("SEG_03", "SEG_45")]
    gate = mss.quality_gates(pilot, timed, _srt(timed, tmp_path))["qualifiers_and_continuity"]
    assert not gate["pass"] and any("CR_001" in v for v in gate["violations"])


# --- audio timing and subtitles -----------------------------------------------------------

def test_timeline_uses_pcm_samples_not_estimates(pilot, tmp_path):
    beats = mss.canonical_beats(pilot)
    wavs = {b["segment_id"]: _wav(tmp_path / f"{b['segment_id']}.wav", 5 + i, rate=24000) for i, b in enumerate(beats)}
    timed = mss.build_timeline(beats, wavs, {"lead_in_seconds": 0, "gap_seconds": 0, "tail_seconds": 0})
    assert [b["audio"]["samples"] for b in timed["beats"]] == [24000 * (5 + i) for i in range(6)]
    assert timed["total_seconds"] == pytest.approx(sum(5 + i for i in range(6)))
    assert timed["beats"][1]["start_seconds"] == pytest.approx(5)
    track = mss.write_concatenated_wav(timed, tmp_path / "track.wav")
    assert track == pytest.approx(timed["total_seconds"])


def test_tampered_or_missing_audio_fails(pilot, tmp_path):
    timed = _timed(pilot, tmp_path)
    timed["beats"][0]["audio"]["samples"] += 1
    Path(timed["beats"][1]["audio"]["path"]).write_bytes(b"RIFF-broken")
    timed["beats"][2]["end_seconds"] += 0.5
    gate = mss.quality_gates(pilot, timed, _srt(timed, tmp_path))["audio_measured"]
    assert not gate["pass"]
    assert any(p.startswith("SEG_01: manifest samples") for p in gate["problems"])
    assert any(p.startswith("SEG_02:") for p in gate["problems"])
    assert any(p.startswith("SEG_03: window") for p in gate["problems"])


def test_track_length_must_match_timeline(pilot, tmp_path):
    timed = _timed(pilot, tmp_path)
    track = _wav(tmp_path / "short.wav", 10)
    gate = mss.quality_gates(pilot, timed, _srt(timed, tmp_path), track=track)["audio_measured"]
    assert "concatenated track length differs from timeline total" in gate["problems"]


def test_subtitles_are_sentence_cues_inside_measured_windows(pilot, tmp_path):
    timed = _timed(pilot, tmp_path)
    cues = mss.parse_srt(_srt(timed, tmp_path))
    assert len(cues) > len(timed["beats"])
    for beat in timed["beats"]:
        inside = [c for c in cues if beat["start_seconds"] - 0.002 <= c["start"] and c["end"] <= beat["end_seconds"] + 0.002]
        assert " ".join(c["text"] for c in inside) == beat["text"]


def test_merged_or_edited_subtitles_fail(pilot, tmp_path):
    timed = _timed(pilot, tmp_path)
    merged = _srt(timed, tmp_path, words_per_cue=10_000)  # regression: one cue spanning the whole Short
    assert not mss.quality_gates(pilot, timed, merged)["subtitles_aligned"]["pass"]
    edited = _srt(timed, tmp_path).replace("Brazil", "Brasil", 1)
    gate = mss.quality_gates(pilot, timed, edited)["subtitles_aligned"]
    assert not gate["pass"] and "SEG_01: subtitle text differs from narration" in gate["problems"]


def test_overlong_short_reports_overage_and_longest_segments(pilot, tmp_path):
    timed = _timed(pilot, tmp_path, seconds=11.5)
    gate = mss.quality_gates(pilot, timed, _srt(timed, tmp_path))["duration_target"]
    assert not gate["pass"]
    assert gate["over_by_seconds"] == pytest.approx(0.3 + 6 * 11.5 + 2 + 0.5 - 60, abs=1e-3)
    assert len(gate["longest_segments"]) == 3


# --- driver: provider language and end-to-end on a synthetic package -------------------------

def _run_driver(tmp_path, monkeypatch, package, voice_language, seconds=24.0):
    path = tmp_path / "package.json"
    path.write_text(json.dumps(package), encoding="utf-8")
    calls = {}
    selection = {"provider": "fake", "tool": "fake_tts", "version": "1",
                 "settings": {"voice": "Fixture", "language_code": voice_language}, "model_identity": "fixture"}
    def select(get_tool, language, **kwargs):
        calls["language"] = language
        return selection
    real_tool = stv.tool
    def tool(name):
        if name == "fake_tts":
            return SimpleNamespace(execute=lambda p: (_wav(Path(p["output_path"]), seconds), ToolResult(success=True))[1])
        return real_tool(name)
    monkeypatch.setattr(driver, "select_local_voice", select)
    monkeypatch.setattr(stv, "tool", tool)
    monkeypatch.setattr(stv, "ROOT", tmp_path)
    code = driver.main([str(path), "--project-id", "synthetic-short"])
    return code, calls, tmp_path / "projects/synthetic-short"


def test_english_package_runs_end_to_end_with_an_english_voice(tmp_path, monkeypatch):
    code, calls, project = _run_driver(tmp_path, monkeypatch, synthetic_package("en"), "en-US")
    assert code == 0 and calls["language"] == "en"
    manifest = json.loads((project / "artifacts/short_timed_manifest.json").read_text(encoding="utf-8"))
    report = json.loads((project / "artifacts/short_report.json").read_text(encoding="utf-8"))
    assert manifest["package_id"] == "STORY_900" and [b["segment_id"] for b in manifest["beats"]] == ["SEG_1", "SEG_2"]
    assert manifest["approvals"] == {"factual": "pending_human_review", "publication": "pending_human_review",
                                     "listening": "pending_human_review"}
    assert report["status"] == "technical_pass" and manifest["total_seconds"] == pytest.approx(49.2)
    assert (project / "assets/subtitles.srt").is_file() and (project / "assets/audio/short_narration.wav").is_file()


def test_voice_in_another_language_is_blocked(tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="does not match narration language en"):
        _run_driver(tmp_path, monkeypatch, synthetic_package("en"), "vi")
    assert not list(tmp_path.glob("projects/**/*.wav"))


def test_failed_gate_returns_nonzero_and_keeps_report(tmp_path, monkeypatch):
    code, _, project = _run_driver(tmp_path, monkeypatch, synthetic_package("en"), "en-US", seconds=40)
    report = json.loads((project / "artifacts/short_report.json").read_text(encoding="utf-8"))
    assert code == 1 and report["status"] == "technical_fail"
    assert report["gates"]["duration_target"]["over_by_seconds"] > 0


def test_missing_voice_is_a_blocker(tmp_path, monkeypatch):
    path = tmp_path / "p.json"
    path.write_text(json.dumps(synthetic_package("en")), encoding="utf-8")
    def select(*args, **kwargs):
        raise ValueError("No offline TTS for language 'en'")
    monkeypatch.setattr(driver, "select_local_voice", select)
    monkeypatch.setattr(stv, "ROOT", tmp_path)
    with pytest.raises(SystemExit, match="Blocked: no verified offline voice for 'en'"):
        driver.main([str(path)])
