"""Master Story Package: pilot validity, graph integrity and Short/Long consistency."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from lib import master_story as ms

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "examples/master-story/lead-masks-1966/master_story.json"


@pytest.fixture(scope="module")
def pilot():
    return ms.load(PILOT)


@pytest.fixture
def pkg(pilot):
    return copy.deepcopy(pilot)


def _problems(package):
    with pytest.raises(ms.MasterStoryError) as info:
        ms.validate_package(package)
    return info.value.problems


def _claim(package, claim_id):
    return next(c for c in package["claims"] if c["id"] == claim_id)


def _segment(package, segment_id):
    return next(s for s in package["master_narrative"]["segments"] if s["id"] == segment_id)


# --- the pilot ------------------------------------------------------------------------------

def test_pilot_package_is_valid_with_every_epistemic_status(pilot):
    summary = ms.validate_package(pilot)
    assert summary["package"] == "STORY_053@v1"
    assert all(summary["claim_status"][s] > 0 for s in ms.STATUSES)
    assert summary["formats"]["short"]["estimated_seconds"] <= 60
    assert 360 <= summary["formats"]["long"]["estimated_seconds"] <= 900


def test_every_non_unknown_claim_cites_a_listed_source(pilot):
    sources = {s["id"] for s in pilot["sources"]}
    for claim in pilot["claims"]:
        assert set(claim["supporting_source_ids"]) <= sources
        assert claim["status"] == "UNKNOWN" or claim["supporting_source_ids"]
    assert {s["verification"]["status"] for s in pilot["sources"]} <= {"verified", "previously_inspected", "unreachable"}


def test_short_and_long_share_one_canonical_record_per_id(pilot):
    short, long = ms.resolve_format(pilot, "short"), ms.resolve_format(pilot, "long")
    long_claims = {c["id"]: c for c in long["claims"]}
    long_entities = {e["id"]: e for e in long["entities"]}
    long_events = {e["id"]: e for e in long["events"]}
    assert short["claims"] and short["entities"] and short["events"]
    for claim in short["claims"]:
        assert claim == long_claims[claim["id"]]  # same text, status, sources and qualifier
    for entity in short["entities"]:
        assert entity == long_entities[entity["id"]]
    for event in short["events"]:
        assert event == long_events[event["id"]]
    long_text = {s["id"]: s["text"] for s in long["segments"]}
    assert all(long_text[s["id"]] == s["text"] for s in short["segments"])
    assert (short["aspect_ratio"], long["aspect_ratio"]) == ("9:16", "16:9")


def test_resolved_view_carries_applicable_rules_and_sources(pilot):
    short = ms.resolve_format(pilot, "short")
    assert "CR_001" in {r["id"] for r in short["continuity_rules"]}
    cited = {s for c in short["claims"] for s in c["supporting_source_ids"] + c["contradicting_source_ids"]}
    assert {s["id"] for s in short["sources"]} == cited


# --- package integrity ------------------------------------------------------------------------

def test_schema_rejects_status_outside_the_six_states(pkg):
    _claim(pkg, "CLM_001")["status"] = "CONFIRMED"
    assert any(p.startswith("SCHEMA claims/0/status") for p in _problems(pkg))


def test_schema_rejects_format_restating_facts(pkg):
    pkg["formats"]["short"]["claims"] = [{"id": "CLM_026", "status": "DOCUMENTED_FACT"}]
    assert any("formats/short" in p and "Additional properties" in p for p in _problems(pkg))


def test_duplicate_ids_across_collections_fail(pkg):
    pkg["entities"]["objects"][0]["id"] = "CHR_MIGUEL"
    problems = _problems(pkg)
    assert any(p.startswith("DUPLICATE_ID CHR_MIGUEL") for p in problems)
    assert any(p.startswith("ENTITY_PREFIX CHR_MIGUEL") for p in problems)


def test_unresolved_and_missing_sources_fail(pkg):
    _claim(pkg, "CLM_007")["supporting_source_ids"] = ["SRC_999"]
    _claim(pkg, "CLM_029")["supporting_source_ids"] = []
    problems = _problems(pkg)
    assert "UNRESOLVED_SOURCE CLM_007 -> SRC_999" in problems
    assert any(p.startswith("UNSUPPORTED_CLAIM CLM_029") for p in problems)


def test_unknown_claim_may_have_no_support(pkg):
    _claim(pkg, "CLM_035")["supporting_source_ids"] = []
    ms.validate_package(pkg)


def test_claim_event_links_must_agree(pkg):
    _claim(pkg, "CLM_007")["event_id"] = "EVT_006"
    problems = _problems(pkg)
    assert any(p.startswith("CLAIM_EVENT_MISMATCH CLM_007") for p in problems)


def test_timeline_must_be_chronological_and_ranges_complete(pkg):
    pkg["timeline"][1], pkg["timeline"][2] = pkg["timeline"][2], pkg["timeline"][1]
    del next(e for e in pkg["timeline"] if e["precision"] == "range")["date_end"]
    problems = _problems(pkg)
    assert any(p.startswith("TIMELINE_ORDER") for p in problems)
    assert any(p.startswith("EVENT_RANGE") for p in problems)


def test_entities_must_be_grounded_in_claims(pkg):
    pkg["entities"]["locations"][0]["claim_ids"] = ["CLM_404"]
    _segment(pkg, "SEG_01")["entity_ids"].append("LOC_SAO_PAULO")
    problems = _problems(pkg)
    assert any(p.startswith("UNRESOLVED_CLAIM LOC_CAMPOS") for p in problems)
    assert "UNGROUNDED_ENTITY SEG_01 -> LOC_SAO_PAULO: no shared claim" in problems


def test_segment_needs_claims_unless_marked_nonfactual(pkg):
    segment = _segment(pkg, "SEG_09")
    segment.update(claim_ids=[], entity_ids=[], event_ids=[], source_ids=[])
    assert any(p.startswith("UNGROUNDED_SEGMENT SEG_09") for p in _problems(pkg))
    segment["nonfactual"] = True
    ms.validate_package(pkg)


def test_segment_source_must_be_cited_by_its_claims(pkg):
    _segment(pkg, "SEG_01")["source_ids"] = ["SRC_013"]
    assert "UNGROUNDED_SOURCE SEG_01 -> SRC_013: not cited by the segment's claims" in _problems(pkg)


def test_continuity_rules_must_resolve(pkg):
    pkg["continuity_rules"][0]["require_claim_ids"] = ["CLM_777"]
    pkg["continuity_rules"][1].pop("require_claim_ids")
    problems = _problems(pkg)
    assert "UNRESOLVED_CLAIM CR_001.require_claim_ids -> CLM_777" in problems
    assert any(p.startswith("RULE_INCOMPLETE CR_002") for p in problems)


# --- Short / Long consistency -------------------------------------------------------------------

def test_format_must_target_the_same_package_version(pkg):
    pkg["formats"]["short"]["package_version"] = "v2"
    assert any(p.startswith("PACKAGE_MISMATCH short") for p in _problems(pkg))


def test_format_cannot_reference_unknown_or_reordered_segments(pkg):
    pkg["formats"]["short"]["segment_ids"] = ["SEG_03", "SEG_01", "SEG_99"]
    problems = _problems(pkg)
    assert "UNRESOLVED_SEGMENT short -> SEG_99" in problems
    assert any(p.startswith("SEGMENT_ORDER short") for p in problems)


def test_short_dropping_a_required_qualifier_fails(pkg):
    # SEG_02 uses the capsule instruction (CLM_013); SEG_03/SEG_45 carry "contents unknown" (CLM_032).
    pkg["formats"]["short"]["segment_ids"] = ["SEG_01", "SEG_02", "SEG_07", "SEG_18", "SEG_23", "SEG_24"]
    problems = _problems(pkg)
    assert any(p.startswith("CONTINUITY CR_001 in format short") for p in problems)


def test_short_with_hypothesis_must_carry_its_unknown(pkg):
    # SEG_37 states the experiment hypothesis (CLM_026) without "capsule contents unknown" (CLM_032).
    pkg["formats"]["short"]["segment_ids"] = ["SEG_01", "SEG_07", "SEG_23", "SEG_37", "SEG_40", "SEG_41"]
    problems = _problems(pkg)
    assert any(p.startswith("CONTINUITY CR_002 in format short") for p in problems)


def test_hypothesis_and_its_unknown_in_one_segment_is_enough(pkg):
    pkg["formats"]["short"]["segment_ids"] = ["SEG_01", "SEG_02", "SEG_03", "SEG_37", "SEG_39", "SEG_40"]
    ms.validate_package(pkg)


def test_short_may_not_use_claims_absent_from_long(pkg):
    # Long drops every segment about the masks (CLM_012) while Short still shows them.
    long = pkg["formats"]["long"]
    long["segment_ids"] = [s for s in long["segment_ids"] if "CLM_012" not in _segment(pkg, s)["claim_ids"]]
    long["target_seconds"]["min"] = 200
    problems = _problems(pkg)
    assert any(p.startswith("SHORT_NOT_IN_LONG") for p in problems)


def test_estimated_duration_and_shape_are_checked(pkg):
    pkg["formats"]["short"]["segment_ids"] = [f"SEG_{i:02d}" for i in range(1, 12)]
    # Estimated duration is advisory (real audio is gated in M2.2); shape is a hard error.
    assert any(w.startswith("DURATION_ESTIMATE short") for w in ms.duration_warnings(pkg))
    ms.validate_package(pkg)
    pkg["formats"]["long"]["aspect_ratio"] = "9:16"
    problems = _problems(pkg)
    assert any(p.startswith("FORMAT_SHAPE long") for p in problems)
    assert not any("DURATION" in p for p in problems)


def test_external_format_plan_validates_against_package(pilot):
    plan = copy.deepcopy(pilot["formats"]["short"])
    ms.validate_external_format(pilot, plan)
    plan["package_id"] = "STORY_054"
    with pytest.raises(ms.MasterStoryError, match="PACKAGE_MISMATCH"):
        ms.validate_external_format(pilot, plan)


def test_validation_does_not_mutate_the_package(pilot):
    before = json.dumps(pilot, sort_keys=True)
    ms.validate_package(pilot)
    ms.resolve_format(pilot, "long")
    assert json.dumps(pilot, sort_keys=True) == before


# --- CLI ----------------------------------------------------------------------------------------

def test_cli_validate_and_resolve(tmp_path, pkg):
    run = lambda *args: subprocess.run([sys.executable, "-X", "utf8", "-m", "lib.master_story", *args],
                                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    ok = run("validate", str(PILOT))
    assert ok.returncode == 0 and json.loads(ok.stdout)["status"] == "valid"
    out = tmp_path / "short.json"
    assert run("resolve", str(PILOT), "short", "-o", str(out)).returncode == 0
    assert json.loads(out.read_text(encoding="utf-8"))["format"] == "short"
    _claim(pkg, "CLM_001")["supporting_source_ids"] = ["SRC_999"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(pkg, ensure_ascii=False), encoding="utf-8")
    failed = run("validate", str(bad))
    assert failed.returncode == 1 and "UNRESOLVED_SOURCE CLM_001 -> SRC_999" in failed.stderr
