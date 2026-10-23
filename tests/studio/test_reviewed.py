"""P2.3 immutable content, traceability, explicit approval and tamper regression checks."""

import copy
import hashlib
import json
import socket
import subprocess
import urllib.request
from pathlib import Path

import pytest

from lib.reviewed_fiction import validate_reviewed_package, working_copy
from studio.catalog import ApprovedPackages
from studio.fiction import PACKAGE_DIR
from studio.review import DECISION_DIR, ReviewError, load_log, record_decision, review_lock, review_view
from studio.reviewed import (APPROVAL_FILE, MANIFEST_FILE, OUTPUT_DIR, PACKAGE_FILE, TEXT_FILE,
                             ReviewedPackageError, approve_reviewed_story, materialize_reviewed_story,
                             read_reviewed_story)
from studio.store import ProductionStore
from tests.studio.fiction_fixture import STORY, draft
from tests.studio.reviewed_fixture import complete, prepare
from tests.studio.test_fiction import client, tree  # Shared isolated HTTP fixture and SHA-256 helper.

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def store(tmp_path):
    return ProductionStore(tmp_path / "projects", ApprovedPackages(ROOT))


def ready(store, override=None):
    prepare(store, override=override)
    complete(store)
    return materialize_reviewed_story(store, "fx")


def change(store, target_id, decision, **extra):
    current = next(d for d in reversed(load_log(store.root / "fx")) if d["target_id"] == target_id)
    return record_decision(store, "fx", {"target_id": target_id, "decision": decision,
                                         "supersedes": current["decision_id"], **extra})


def approve(store, result):
    return approve_reviewed_story(store, "fx", result["version"], result["package_sha256"], result["manifest_sha256"])


def test_complete_materialization_keeps_inputs_and_maps_crlf_unicode(store):
    prepare(store)
    before = tree(store.root / "fx")
    complete(store)
    result = materialize_reviewed_story(store, "fx")
    pkg = result["package"]
    assert result["state"] == "materialized" and not result["ready_for_next_stage"] and not result["approval"]
    assert not pkg["blockers"], pkg["blockers"]
    assert pkg["working_text"] == STORY.replace("Nhãn kho A. \\", "Nhãn kho A.").split("\r\n\r\n\r\n\r\nđây")[0]
    assert "\r\n" in pkg["working_text"] and "đèn" in pkg["working_text"]
    assert pkg["version"] == "v2"
    for m in pkg["source_mapping"]:
        if m["operation"] == "retain":
            assert STORY[m["source_start"]:m["source_end"]] == pkg["working_text"][m["working_start"]:m["working_end"]]
    assert {k: v for k, v in tree(store.root / "fx").items() if k in before} == before
    assert pkg["canonical_story"]["ambiguities"][0]["status"] == "intentionally_unresolved"
    assert pkg["canonical_story"]["dialogue"][1]["speaker_id"] is None
    assert all(d["answer"] is None for d in pkg["dispositions"] if d["decision"] == "preserve_ambiguity")


@pytest.mark.parametrize("decision", ["reject", "defer"])
def test_rejected_and_deferred_edits_preserve_text_and_block_incomplete_long(store, decision):
    ready(store)
    change(store, "CHG_0002", decision)
    result = materialize_reviewed_story(store, "fx")
    assert "đây là câu chuyện tôi muốn kể" in result["package"]["working_text"]
    assert any("UNAPPROVED_EXCLUSION" in b for b in result["package"]["blockers"])
    with pytest.raises(ReviewedPackageError) as exc:
        approve(store, result)
    assert exc.value.code == "approval_blocked"


def test_rejected_unused_semantics_are_excluded_without_approving_them(store):
    ready(store)
    change(store, "MOT_113", "reject")
    result = materialize_reviewed_story(store, "fx")
    assert result["package"]["canonical_story"]["motifs"] == []
    assert not result["package"]["blockers"]
    assert any(d["target_id"] == "MOT_113" and d["decision"] == "reject" for d in result["package"]["dispositions"])


@pytest.mark.parametrize("target", ["CHR_MINH", "LOC_STORE", "FACT_WRITING", "EVT_KNOCK", "OBJ_PANEL"])
def test_rejected_referenced_items_block_approval(store, target):
    ready(store)
    change(store, target, "reject")
    result = materialize_reviewed_story(store, "fx")
    assert any("BAD_REFERENCE" in b for b in result["package"]["blockers"])
    assert all(i["id"] != target for name in ("characters", "locations", "facts", "events", "objects")
               for i in result["package"]["canonical_story"][name])


def test_defer_is_never_preserve_ambiguity_and_answer_is_never_invented_canon(store):
    ready(store)
    change(store, "AMB_WRITER", "defer")
    deferred = materialize_reviewed_story(store, "fx")
    assert deferred["package"]["blockers"]
    assert deferred["package"]["canonical_story"]["ambiguities"][0]["status"] == "unresolved"
    change(store, "AMB_WRITER", "answer", answer="A human interpretation for this synthetic fixture.")
    answered = materialize_reviewed_story(store, "fx")
    assert not answered["package"]["blockers"]
    assert answered["package"]["canonical_story"]["dialogue"][1]["speaker_id"] is None
    assert answered["package"]["canonical_story"]["ambiguities"][0]["status"] == "human_answer_recorded"
    assert "human interpretation" not in answered["package"]["working_text"]


def test_approval_pins_exact_hashes_freezes_content_and_changes_need_new_version(store):
    result = ready(store)
    folder = store.root / "fx" / OUTPUT_DIR / "v2"
    before = tree(folder)
    with pytest.raises(ReviewedPackageError) as exc:
        approve_reviewed_story(store, "fx", "v2", "0" * 64, result["manifest_sha256"])
    assert exc.value.code == "stale_reviewed"
    approved = approve(store, result)
    assert approved["ready_for_next_stage"] and approved["approval"]["approved"]
    assert {k: v for k, v in tree(folder).items() if k in before} == before
    frozen = tree(folder)
    assert approve(store, result)["status"] == "already_approved"
    assert materialize_reviewed_story(store, "fx")["status"] == "already_materialized"
    assert tree(folder) == frozen
    change(store, "MOT_113", "reject")
    assert not read_reviewed_story(store, "fx")["ready_for_next_stage"]
    with pytest.raises(ReviewedPackageError):
        approve(store, result)
    new = materialize_reviewed_story(store, "fx")
    assert new["version"] == "v3" and not new["approval"] and not new["ready_for_next_stage"]
    assert tree(folder) == frozen
    assert approve(store, new)["ready_for_next_stage"]


@pytest.mark.parametrize("file", [PACKAGE_FILE, TEXT_FILE, MANIFEST_FILE, APPROVAL_FILE])
def test_modified_reviewed_output_or_approval_is_refused_without_overwrite(store, file):
    result = ready(store)
    approve(store, result)
    path = store.root / "fx" / OUTPUT_DIR / "v2" / file
    path.write_bytes(path.read_bytes() + b" ")
    # Whitespace is JSON-valid, but the approved manifest hash is bound to its exact bytes.
    if file == APPROVAL_FILE:
        value = json.loads(path.read_bytes())
        value["approved"] = False
        path.write_text(json.dumps(value), encoding="utf-8")
    before = tree(path.parent)
    for action in (lambda: read_reviewed_story(store, "fx"), lambda: materialize_reviewed_story(store, "fx")):
        with pytest.raises(ReviewedPackageError) as exc:
            action()
        assert exc.value.code == "reviewed_invalid"
    assert tree(path.parent) == before


@pytest.mark.parametrize("damage", ["last_edit", "last_delete", "middle_edit", "source_hash", "stale_hash"])
def test_decision_and_input_tampering_is_detected(store, damage):
    ready(store)
    folder = store.root / "fx" / DECISION_DIR
    files = sorted(folder.glob("*.json"))
    if damage == "last_delete":
        files[-1].unlink()
    elif damage == "source_hash":
        path = store.root / "fx" / PACKAGE_DIR / "fiction_package_report.json"
        data = json.loads(path.read_bytes())
        data["provenance"]["source"]["sha256"] = "0" * 64
        path.write_text(json.dumps(data), encoding="utf-8")
    else:
        path = files[0] if damage == "middle_edit" else files[-1]
        data = json.loads(path.read_bytes())
        if damage == "stale_hash":
            data["input_hashes"]["fiction_package"] = "0" * 64
        else:
            data["decision"] = "reject"
        path.write_text(json.dumps(data), encoding="utf-8")
    before = tree(store.root)
    with pytest.raises(ValueError):
        materialize_reviewed_story(store, "fx")
    assert tree(store.root) == before


def test_precise_long_coverage_and_direct_validator_mapping(store):
    result = ready(store)
    package = copy.deepcopy(result["package"])
    package["canonical_story"]["formats"]["long"]["chapters"][0]["beats"][1]["narration"]["text"] = "edited"
    assert any("REVIEWED_VERBATIM" in e for e in validate_reviewed_package(package, STORY, []))
    # Rejecting the cleanup leaves the literal backslash in the approved story, so the partial Long span is incomplete.
    change(store, "CHG_0001", "reject")
    result = materialize_reviewed_story(store, "fx")
    assert any("LONG_WORKING_COVERAGE" in b for b in result["package"]["blockers"])


def test_missing_and_deferred_formats_block_approval(store):
    ready(store)
    change(store, "FMT_SHORT", "defer")
    result = materialize_reviewed_story(store, "fx")
    assert "short" not in result["package"]["canonical_story"]["formats"]
    assert result["package"]["blockers"]


@pytest.mark.parametrize("problem", ["rejected_sound", "short_sound_only", "short_source_only", "unlinked_attribution"])
def test_additional_format_and_ambiguity_guards(store, problem):
    data = draft()
    if problem == "short_sound_only":
        data["formats"]["long"]["chapters"][0]["beats"][0]["sound_cue_ids"] = []
    elif problem == "short_source_only":
        data["formats"]["short"]["chapters"][0]["beats"][0]["narration"]["spans"] = ["SEG_0001..SEG_0006"]
    elif problem == "unlinked_attribution":
        data["ambiguities"][0]["related_ids"] = ["FACT_WRITING"]
    result = ready(store, data)
    if problem == "rejected_sound":
        change(store, "SND_KNOCK", "reject")
        result = materialize_reviewed_story(store, "fx")
    assert result["package"]["blockers"]
    with pytest.raises(ReviewedPackageError):
        approve(store, result)


@pytest.mark.parametrize("kind", ["symlink", "reparse"])
def test_reviewed_paths_refuse_a_link_before_opening_output(store, monkeypatch, kind):
    from types import SimpleNamespace
    ready(store)
    target = store.root / "fx" / OUTPUT_DIR
    if kind == "symlink":
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda p: p == target or original(p))
    else:
        original = Path.lstat
        def reparse(p, *args, **kwargs):
            info = original(p, *args, **kwargs)
            return SimpleNamespace(st_file_attributes=0x400) if p == target else info
        monkeypatch.setattr(Path, "lstat", reparse)
    with pytest.raises(ReviewError):
        read_reviewed_story(store, "fx")


def test_missing_frozen_version_is_not_silently_replaced(store):
    ready(store)
    change(store, "MOT_113", "reject")
    materialize_reviewed_story(store, "fx")
    folder = store.root / "fx" / OUTPUT_DIR / "v2"
    folder.rename(folder.parent / ".tmp-retired-for-test")
    before = tree(store.root)
    with pytest.raises(ReviewedPackageError):
        materialize_reviewed_story(store, "fx")
    assert tree(store.root) == before


def test_no_network_processes_production_or_input_writes(store, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No production or external calls")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    from tools.tool_registry import registry
    monkeypatch.setattr(registry, "ensure_discovered", forbidden)
    result = ready(store)
    approve(store, result)
    assert {p.suffix for p in store.root.rglob('*') if p.is_file()} <= {".md", ".json"}
    assert not list(store.root.rglob("checkpoint_*.json"))


def test_busy_review_writer_cannot_race_approval(store):
    result = ready(store)
    with review_lock(store.root / "fx"):
        with pytest.raises(ReviewError):
            approve(store, result)
        with pytest.raises(ReviewError):
            change(store, "MOT_113", "reject")


def test_http_preview_requires_explicit_current_hash_approval(store, client):
    prepare(store)
    complete(store)
    url = "/studio/api/productions/fx/reviewed-story"
    before = tree(store.root)
    assert client.get(url).json()["state"] == "missing"
    assert tree(store.root) == before
    result = client.post(url, json={}).json()
    assert not result["approval"] and not result["ready_for_next_stage"]
    assert client.post(url + "/v2/approve", json={}).status_code == 422
    body = {k: result[k] for k in ("package_sha256", "manifest_sha256")}
    assert client.post(url + "/v2/approve", json=body, headers={"Origin": "https://evil.invalid"}).status_code == 403
    assert client.post(url + "/v2/approve", json=body).json()["ready_for_next_stage"]
    assert client.get(url + "/v2").json()["approval"]["approval_scope"] == "preproduction_story_only"
    assert client.get(url + "/..%2Fx").status_code in (404, 422)


def test_working_copy_rejects_overlapping_or_wrong_approved_edits():
    change = {"id": "CHG_X", "operation": "remove", "source_span": {"char_start": 1, "char_end": 3}, "removed_text": "bc"}
    with pytest.raises(ValueError):
        working_copy("abcd", [change, change])
    with pytest.raises(ValueError):
        working_copy("axyd", [change])
