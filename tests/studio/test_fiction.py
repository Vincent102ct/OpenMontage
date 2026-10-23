"""P2.2 fiction package, validator and human review log."""

import copy
import hashlib
import json
import shutil
import socket
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backlot import server as board_server, state as board_state
from lib import master_story
from lib.fiction_story import FictionStoryError, validate_package
from studio import __main__ as studio_cli
from studio.catalog import ApprovedPackages
from studio.fiction import (MAX_DRAFT_BYTES, PACKAGE_DIR, PACKAGE_FILES, FictionPackageError,
                            build_fiction_package, read_fiction_package, read_local_draft)
from studio.intake import OUTPUT_DIR as INTAKE_DIR, prepare_story_intake
from studio.models import NewProduction
from studio.review import DECISION_DIR, ReviewError, record_decision, review_view, targets, _context
from studio.server import create_app
from studio.store import ProductionStore
from tests.studio.fiction_fixture import STORY, draft

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def tree(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def store(tmp_path):
    s = ProductionStore(tmp_path / "projects", ApprovedPackages(ROOT))
    s.root.mkdir()
    return s


def saved(store, project_id="fx", intake=True, content=STORY):
    store.create(NewProduction(project_id=project_id, input_mode="story", content=content, formats=["short", "long"]))
    if intake:
        prepare_story_intake(store, project_id, NOW)
    return store.root / project_id


def built(store, project_id="fx", **overrides):
    saved(store, project_id)
    return build_fiction_package(store, project_id, draft(**overrides), NOW)


def problems_for(store, mutate) -> list[str]:
    saved(store)
    d = draft()
    mutate(d)
    with pytest.raises(FictionPackageError) as exc:
        build_fiction_package(store, "fx", d, NOW)
    assert exc.value.code == "invalid_draft"
    assert not (store.root / "fx" / PACKAGE_DIR).exists()
    return exc.value.problems


# --- package building -------------------------------------------------------

def test_package_is_source_linked_versioned_and_pending(store):
    result = built(store)
    assert result["status"] == "created"
    pkg = result["package"]
    out = store.root / "fx" / PACKAGE_DIR
    assert sorted(p.name for p in out.iterdir()) == sorted(PACKAGE_FILES.values())
    assert (pkg["package_kind"], pkg["status"], pkg["review_status"], pkg["approved"]) == (
        "fiction", "draft", "pending_human_review", False)
    assert pkg["authorship"]["author"] == "production_requester" and pkg["coverage"]["complete"] is False
    source = STORY.encode("utf-8")
    assert pkg["provenance"]["source"]["sha256"] == hashlib.sha256(source).hexdigest()
    intake_report = store.root / "fx" / INTAKE_DIR / "story_intake_report.json"
    assert pkg["provenance"]["intake"]["sha256"] == hashlib.sha256(intake_report.read_bytes()).hexdigest()
    for seg in pkg["segments"]:
        assert STORY[seg["char_start"]:seg["char_end"]] == seg["text"]
    texts = {s["id"]: s["text"] for s in pkg["segments"]}
    for name in ("characters", "facts", "events", "dialogue", "motifs", "ambiguities"):
        for item in pkg[name]:
            for e in item["evidence"]:
                assert texts[e["segment_id"]][e["char_start"]:e["char_end"]] == e["quote"]
    long_beats = [b for ch in pkg["formats"]["long"]["chapters"] for b in ch["beats"]]
    assert long_beats[1]["narration"]["text"].startswith("Nhãn kho A.\n")  # Partial span avoids the stray "\".
    short = pkg["formats"]["short"]
    assert short["aspect_ratio"] == "9:16" and short["target_seconds"] == {"min": 45, "max": 60}
    assert pkg["formats"]["long"]["target_seconds"] is None
    assert short["duration"]["status"] == "estimate_pending_tts_measurement"
    authored = [b for ch in short["chapters"] for b in ch["beats"] if b["narration"]["mode"] == "authored_proposal"]
    assert authored and authored[0]["narration"]["sources"][0]["segment_id"] == "SEG_0010"
    assert "outside 45-60" in " ".join(result["report"]["validation"]["warnings"])
    assert any("SEG_0011" in m for m in pkg["coverage"]["missing"])
    assert any("DLG_WRITING" in m for m in pkg["coverage"]["missing"])
    assert not list(store.root.rglob("checkpoint_*.json"))


def test_inputs_from_p1_and_p21_are_never_modified(store):
    project = saved(store)
    before = tree(project)
    build_fiction_package(store, "fx", draft(), NOW)
    record_decision(store, "fx", {"target_id": "CHG_0001", "decision": "accept", "supersedes": None}, NOW)
    after = tree(project)
    assert {k: v for k, v in after.items() if k in before} == before


def test_same_draft_is_idempotent_and_deterministic(store, tmp_path):
    project = saved(store)
    other = ProductionStore(tmp_path / "other", store.catalog)
    other.root.mkdir()
    shutil.copytree(project, other.root / "fx")
    first = build_fiction_package(store, "fx", draft(), NOW)
    out = project / PACKAGE_DIR
    stamp = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in out.iterdir()}
    reordered = json.loads(json.dumps(draft(), sort_keys=True))  # Same content, different key order.
    assert build_fiction_package(store, "fx", reordered)["status"] == "already_prepared"
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in out.iterdir()} == stamp
    build_fiction_package(other, "fx", draft(), NOW)
    for name in PACKAGE_FILES.values():
        assert (other.root / "fx" / PACKAGE_DIR / name).read_bytes() == (out / name).read_bytes()
    assert first["package_sha256"] == hashlib.sha256((out / PACKAGE_FILES["package"]).read_bytes()).hexdigest()


def test_different_draft_or_tampering_never_overwrites(store):
    built(store)
    out = store.root / "fx" / PACKAGE_DIR
    snapshot = tree(out)
    with pytest.raises(FictionPackageError) as exc:
        build_fiction_package(store, "fx", draft(title="Another title"))
    assert exc.value.code == "package_exists" and tree(out) == snapshot
    pkg = json.loads((out / PACKAGE_FILES["package"]).read_text(encoding="utf-8"))
    pkg["characters"][0]["name"] = "Changed"
    (out / PACKAGE_FILES["package"]).write_text(json.dumps(pkg), encoding="utf-8")
    snapshot = tree(out)
    for action in (lambda: read_fiction_package(store, "fx"), lambda: build_fiction_package(store, "fx", draft())):
        with pytest.raises(FictionPackageError) as exc:
            action()
        assert exc.value.code == "existing_output_invalid"
    assert tree(out) == snapshot


def test_missing_intake_is_reported_not_fabricated(store):
    saved(store, intake=False)
    with pytest.raises(FictionPackageError) as exc:
        build_fiction_package(store, "fx", draft())
    assert exc.value.code == "intake_missing"
    assert review_view(store, "fx")["state"] == "intake_missing"
    view_before_package = (saved(store, "fx2"), review_view(store, "fx2"))[1]
    assert view_before_package["package"] is None and view_before_package["review_status"] == "pending_human_review"
    assert any("No fiction Story Bible package" in m for m in view_before_package["missing_coverage"])


# --- validator: anti-fabrication and consistency ----------------------------

@pytest.mark.parametrize("mutate, expected", [
    (lambda d: d["characters"][0].update(description="Born in 1998 in Hanoi."), "FABRICATION calendar year"),
    (lambda d: d["facts"][0].update(statement="Recorded on 2024-05-01."), "FABRICATION calendar"),
    (lambda d: d["locations"][0].update(description="See https://example.com/house"), "FABRICATION URL"),
    (lambda d: d["formats"]["short"]["chapters"][0]["beats"][1]["narration"].update(text="Năm 1987, đèn sáng."),
     "FABRICATION calendar year"),
    (lambda d: d["facts"][0].update(date="1998-01-01"), "SCHEMA"),
    (lambda d: d.update(sources=[{"id": "SRC"}]) or d["events"][0].update(timeline="x"), "SCHEMA"),
    (lambda d: d["characters"][0].update(aliases=["Nguyễn Văn A"]), "ALIAS_NOT_IN_SOURCE"),
    (lambda d: d["characters"][0].update(evidence=["Câu không có trong truyện."]), "QUOTE_NOT_FOUND"),
    (lambda d: d["objects"][0].update(evidence=["Tách."]), "QUOTE_AMBIGUOUS"),
    (lambda d: d["facts"][2].update(revealed_at="SEG_0003"), "REVELATION_BEFORE_CLAIM"),
    (lambda d: d["facts"][1].update(reported_by=None), "CLAIM_WITHOUT_REPORTER"),
    (lambda d: d["facts"][1].update(conflicts_with=[]), "ASYMMETRIC_CONFLICT"),
    (lambda d: d["ambiguities"][0].update(status="resolved"), "SCHEMA"),
    (lambda d: d["dialogue"][1].update(speaker_id="CHR_NARRATOR"), "ATTRIBUTION_STATUS"),
    (lambda d: d["events"][0].update(time_markers=["3 giờ 45 phút"]), "TIME_MARKER_NOT_IN_SOURCE"),
    (lambda d: d["formats"]["long"]["chapters"][0]["beats"].pop(1), "LONG_COVERAGE"),
    (lambda d: d["formats"]["long"].update(depends_on_changes=["CHG_0002"]), "depends_on_changes"),
    (lambda d: d["formats"]["short"]["chapters"][0]["beats"][0]["character_ids"].append("CHR_KEEPER"),
     "FORMAT_CONSISTENCY"),
    (lambda d: d["stickman_production"].update(forbidden_primary_treatments=["text_slideshow"]), "STICKMAN"),
    (lambda d: d["stickman_production"].update(style="documentary_motion_graphics"), "SCHEMA"),
    (lambda d: d["events"].reverse(), "EVENT_ORDER"),
    (lambda d: d["facts"][0].update(kind="ambiguous"), "AMBIGUOUS_FACT_WITHOUT_QUESTION"),
])
def test_validator_rejects_fabrication_and_inconsistency(store, mutate, expected):
    assert any(expected in p for p in problems_for(store, mutate)), expected


def test_validator_detects_edited_package_text(store):
    result = built(store)
    pkg = copy.deepcopy(result["package"])
    beat = pkg["formats"]["long"]["chapters"][0]["beats"][0]
    beat["narration"]["text"] = beat["narration"]["text"].replace("Tách.", "Rầm.")
    with pytest.raises(FictionStoryError) as exc:
        validate_package(pkg, source_text=STORY)
    assert any("VERBATIM_MISMATCH" in p for p in exc.value.problems)
    pkg = copy.deepcopy(result["package"])
    pkg["segments"][2]["text"] += " thêm"
    with pytest.raises(FictionStoryError) as exc:
        validate_package(pkg, source_text=STORY)
    assert any("SEGMENT_HASH" in p for p in exc.value.problems)


def test_story_053_semantics_unchanged():
    before = tree(ROOT / "examples/master-story")
    package = master_story.load(ROOT / "examples/master-story/lead-masks-1966/master_story.json")
    summary = master_story.validate_package(package)
    assert summary["claims"] > 0 and summary["sources"] > 0
    with pytest.raises(FictionStoryError):
        validate_package(package)  # A historical package is not a fiction package, and vice versa.
    assert tree(ROOT / "examples/master-story") == before


# --- review log -------------------------------------------------------------

def decide(store, target, decision, supersedes=None, answer=None):
    return record_decision(store, "fx", {"target_id": target, "decision": decision, "supersedes": supersedes,
                                         "answer": answer}, NOW)


def test_accept_reject_defer_persist_and_chain(store):
    built(store)
    a = decide(store, "CHG_0001", "accept")
    b = decide(store, "CHG_0002", "reject")
    c = decide(store, "CHR_MINH", "defer")
    folder = store.root / "fx" / DECISION_DIR
    assert sorted(p.name for p in folder.iterdir()) == ["000001.json", "000002.json", "000003.json"]
    assert b["previous_sha256"] == hashlib.sha256((folder / "000001.json").read_bytes()).hexdigest()
    assert c["input_hashes"]["fiction_package"] and "fiction_package" not in a["input_hashes"]
    assert all(d["production_effect"] == "none" for d in (a, b, c))
    view = review_view(store, "fx")
    status = {x["id"]: x["review"]["status"] for x in view["changes"]}
    assert status == {"CHG_0001": "accepted", "CHG_0002": "rejected"}
    lan = next(i for i in view["package"]["collections"]["characters"] if i["id"] == "CHR_MINH")
    assert lan["review"]["status"] == "deferred"
    assert view["working_text_accepted_only"] == STORY.replace("Nhãn kho A. \\", "Nhãn kho A.")
    assert view["review_status"] == "pending_human_review" and view["production_started"] is False


def test_previous_decisions_never_change_silently(store):
    built(store)
    first = decide(store, "FMT_SHORT", "accept")
    with pytest.raises(ReviewError) as exc:
        decide(store, "FMT_SHORT", "reject")  # Stale page: does not name the decision it replaces.
    assert exc.value.code == "stale_decision"
    with pytest.raises(ReviewError):
        decide(store, "FMT_SHORT", "reject", supersedes="DEC_999999")
    second = decide(store, "FMT_SHORT", "reject", supersedes=first["decision_id"])
    assert second["supersedes"] == first["decision_id"]
    original = json.loads((store.root / "fx" / DECISION_DIR / "000001.json").read_text(encoding="utf-8"))
    assert original["decision"] == "accept"  # The first record is kept as history.
    fmt = review_view(store, "fx")["package"]["formats"]["short"]["review"]
    assert fmt["status"] == "rejected" and fmt["history"] == ["DEC_000001", "DEC_000002"]


@pytest.mark.parametrize("damage", ["edit", "delete_middle", "reorder"])
def test_tampered_review_log_is_refused(store, damage):
    built(store)
    decide(store, "CHG_0001", "accept")
    decide(store, "CHG_0002", "defer")
    decide(store, "CHR_MINH", "accept")
    folder = store.root / "fx" / DECISION_DIR
    if damage == "edit":
        d = json.loads((folder / "000001.json").read_text(encoding="utf-8"))
        d["decision"] = "reject"
        (folder / "000001.json").write_text(json.dumps(d, indent=2), encoding="utf-8")
    elif damage == "delete_middle":
        (folder / "000002.json").unlink()
    else:
        (folder / "000003.json").rename(folder / "000004.json")
    snapshot = tree(folder)
    for action in (lambda: review_view(store, "fx"), lambda: decide(store, "CHR_NARRATOR", "accept")):
        with pytest.raises(ReviewError) as exc:
            action()
        assert exc.value.code == "log_invalid"
    assert tree(folder) == snapshot


def test_questions_stay_unresolved_without_an_answer(store):
    built(store)
    for bad in (dict(decision="answer", answer=""), dict(decision="answer", answer="   "),
                dict(decision="accept"), dict(decision="answer", answer="x" * 4001)):
        with pytest.raises(ReviewError) as exc:
            decide(store, "AMB_WRITER", **bad)
        assert exc.value.code == "invalid_decision"
    view = review_view(store, "fx")
    q = next(x for x in view["questions"] if x["id"] == "AMB_WRITER")
    assert q["review"]["status"] == "open"
    deferred = decide(store, "AMB_WRITER", "defer")
    assert next(x for x in review_view(store, "fx")["questions"] if x["id"] == "AMB_WRITER")["review"]["status"] == "deferred"
    decide(store, "AMB_WRITER", "answer", supersedes=deferred["decision_id"], answer="Chưa rõ; giữ bí ẩn.")
    q = next(x for x in review_view(store, "fx")["questions"] if x["id"] == "AMB_WRITER")
    assert q["review"] == {**q["review"], "status": "answered", "answer": "Chưa rõ; giữ bí ẩn."}
    with pytest.raises(ReviewError) as exc:
        decide(store, "CHG_0001", "answer", answer="x")
    assert exc.value.code == "invalid_decision"
    with pytest.raises(ReviewError) as exc:
        decide(store, "NOT_A_TARGET", "accept")
    assert exc.value.code == "unknown_target"


def test_complete_review_records_decisions_but_starts_nothing(store, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Review must not use the network, processes or production tools")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    from tools.tool_registry import registry
    monkeypatch.setattr(registry, "ensure_discovered", forbidden)
    built(store)
    all_targets = targets(_context(store, "fx"))
    for target_id, target in all_targets.items():
        if target["kind"] == "question":
            decide(store, target_id, "answer", answer="Reviewed.")
        else:
            decide(store, target_id, "accept")
    view = review_view(store, "fx")
    assert view["review_status"] == "decisions_recorded"
    assert view["counts"]["open"] == view["counts"]["undecided"] == 0
    assert view["production_started"] is False and "never start" in view["approval_scope"]
    assert {p.suffix for p in store.root.rglob("*") if p.is_file()} <= {".json", ".md"}
    pkg = json.loads((store.root / "fx" / PACKAGE_DIR / PACKAGE_FILES["package"]).read_text(encoding="utf-8"))
    assert pkg["approved"] is False and pkg["formats"]["short"]["approved"] is False  # Never rewritten.


def test_decisions_become_stale_when_the_package_is_replaced(store):
    built(store)
    decide(store, "CHR_MINH", "accept")
    decide(store, "CHG_0001", "accept")
    out = store.root / "fx" / PACKAGE_DIR
    shutil.move(out, out.parent / "v1-moved-aside")
    build_fiction_package(store, "fx", draft(title="[TEST FIXTURE] Revised"), NOW)
    view = review_view(store, "fx")
    lan = next(i for i in view["package"]["collections"]["characters"] if i["id"] == "CHR_MINH")
    assert lan["review"]["status"] == "stale"
    assert next(c for c in view["changes"] if c["id"] == "CHG_0001")["review"]["status"] == "accepted"
    assert view["counts"]["stale"] == 1


# --- API and CLI --------------------------------------------------------------

@pytest.fixture
def client(store, tmp_path, monkeypatch):
    monkeypatch.setattr(board_state, "PROJECTS_DIR", store.root)
    monkeypatch.setattr(board_server, "PROJECTS_DIR", store.root)
    monkeypatch.setattr(board_server, "_summary_cache", {})
    monkeypatch.setattr(board_server, "THUMB_CACHE_DIR", tmp_path / "thumbs")

    async def no_watch():
        return
    monkeypatch.setattr(board_server, "_watch_projects", no_watch)
    with TestClient(create_app(store), base_url="http://127.0.0.1") as c:
        yield c


def test_api_flow_and_errors(store, client):
    saved(store)
    url = "/studio/api/productions/fx"
    bad = client.post(f"{url}/fiction-package", json=draft(title=None, package_id="bad id"))
    assert bad.status_code == 422 and bad.json()["detail"]["problems"]
    assert client.post(f"{url}/fiction-package", json=draft(), headers={"Origin": "https://evil.invalid"}).status_code == 403
    assert client.post(f"{url}/fiction-package", content="{}", headers={"Content-Type": "text/plain"}).status_code == 415
    assert client.post(f"{url}/fiction-package", json=draft()).status_code == 201
    assert client.post(f"{url}/fiction-package", json=draft()).status_code == 200
    assert client.post(f"{url}/fiction-package", json=draft(title="Other")).status_code == 409
    view = client.get(f"{url}/review").json()
    assert view["package"]["package_id"] == "FIC_TEST_FIXTURE" and view["original_story"] == STORY
    ok = client.post(f"{url}/review/decisions", json={"target_id": "CHG_0001", "decision": "accept", "supersedes": None})
    assert ok.status_code == 201
    stale = client.post(f"{url}/review/decisions", json={"target_id": "CHG_0001", "decision": "reject", "supersedes": None})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "stale_decision"
    assert client.post(f"{url}/review/decisions", json=["x"]).status_code == 422
    assert client.post("/studio/api/productions/missing/review/decisions", json={}).status_code == 404
    assert client.get("/studio/api/productions/..%2Fx/review").status_code in (404, 422)
    board = client.get("/api/project/fx/state").json()
    assert not board["has_pipeline_state"] and all(s["status"] == "pending" for s in board["stages"])
    page = client.get("/studio/static/studio.js").text
    for text in ("Story Review", "Import Story Bible draft", "Authored proposal, not source text", "Record answer"):
        assert text in page


def test_api_import_accepts_content_never_a_server_path(store, client, monkeypatch):
    saved(store)
    def forbidden(*args, **kwargs):
        raise AssertionError("HTTP must never use the local draft path reader")
    monkeypatch.setattr("studio.fiction.read_local_draft", forbidden)
    url = "/studio/api/productions/fx/fiction-package"
    for body in ("../../secret.json", {"path": "../../secret.json"}):
        response = client.post(url, json=body)
        assert response.status_code == 422
    assert not (store.root / "fx" / PACKAGE_DIR).exists()


def test_cli_fiction_and_review(store, monkeypatch, capsys, tmp_path):
    import lib.paths
    monkeypatch.setattr(lib.paths, "PROJECTS_DIR", store.root)
    saved(store)
    path = store.root / "_private_story_drafts" / "fixture" / "draft.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(draft(), ensure_ascii=False), encoding="utf-8")
    assert studio_cli.main(["review", "fx"]) == 0
    assert json.loads(capsys.readouterr().out)["review_status"] == "pending_human_review"
    assert studio_cli.main(["fiction", "fx", "--draft", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "created"
    path.write_text(json.dumps(draft(title="Other")), encoding="utf-8")
    assert studio_cli.main(["fiction", "fx", "--draft", str(path)]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == "package_exists"


@pytest.mark.parametrize("location", ["outside", "traversal", "wrong_extension", "alternate_stream"])
def test_local_import_rejects_unsafe_paths_without_opening_files(store, tmp_path, monkeypatch, location):
    folder = store.root / "_private_story_drafts"
    folder.mkdir(parents=True)
    paths = {"outside": tmp_path / "secret.json", "traversal": folder / ".." / "secret.json",
             "wrong_extension": folder / "secret.txt", "alternate_stream": folder / "draft:secret.json"}
    def forbidden(*args, **kwargs):
        raise AssertionError("An unsafe draft path must never be opened")
    monkeypatch.setattr(Path, "open", forbidden)
    with pytest.raises(FictionPackageError) as exc:
        read_local_draft(store.root, str(paths[location]))
    assert exc.value.code == "invalid_draft"


@pytest.mark.parametrize("content", [b"{", b"[]", b" " * (MAX_DRAFT_BYTES + 1)],
                         ids=["malformed", "not_object", "oversized"])
def test_local_import_rejects_invalid_or_oversized_json(store, content):
    path = store.root / "_private_story_drafts" / "draft.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    with pytest.raises(FictionPackageError) as exc:
        read_local_draft(store.root, str(path))
    assert exc.value.code == "invalid_draft"


def test_local_import_rejects_reparse_components_before_open(store, monkeypatch):
    from types import SimpleNamespace
    path = store.root / "_private_story_drafts" / "draft.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")
    original = Path.lstat
    def reparse(p, *args, **kwargs):
        info = original(p, *args, **kwargs)
        if p == path.parent:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info
    monkeypatch.setattr(Path, "lstat", reparse)
    def forbidden(*args, **kwargs):
        raise AssertionError("Reparse paths must never be opened")
    monkeypatch.setattr(Path, "open", forbidden)
    with pytest.raises(FictionPackageError):
        read_local_draft(store.root, str(path))


@pytest.mark.parametrize("damage", ["draft_hash", "approved_report", "production_started"])
def test_saved_draft_hash_and_pending_report_are_verified(store, damage):
    built(store)
    out = store.root / "fx" / PACKAGE_DIR
    report_path = out / PACKAGE_FILES["report"]
    report = json.loads(report_path.read_bytes())
    if damage == "draft_hash":
        path = out / PACKAGE_FILES["draft"]
        path.write_text(json.dumps(draft(title="Changed after import")), encoding="utf-8")
        report["outputs"][path.name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif damage == "approved_report":
        report["review"]["approved"] = True
    else:
        report["production_started"] = True
    report_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(FictionPackageError) as exc:
        read_fiction_package(store, "fx")
    assert exc.value.code == "existing_output_invalid"


def test_synthetic_verbatim_short_and_long_keep_claims_and_unknowns(store):
    extension = (
        " Tôi đặt hộp linh kiện bên trái bàn, kéo tấm vải phủ khỏi mặt kính rồi kiểm tra từng bánh răng."
        " Ngoài sân, gió làm cành cây chạm nhẹ vào mái tôn. Ánh sáng từ đèn bàn chỉ đủ soi một vòng tròn nhỏ."
        " Tôi ghi số máy vào sổ, cất chiếc kính lúp trong ngăn kéo và chờ tín hiệu từ phòng trực."
        " Không ai nói gì qua bộ đàm. Kim phút trên chiếc đồng hồ thử nghiệm vẫn di chuyển đều đặn."
        " Tôi nhìn bảng điều khiển thêm một lần trước khi quay lại với công việc."
        " Một hộp cầu chì dự phòng nằm trên kệ cao, cạnh cuộn dây đồng và chiếc quạt nhỏ."
        " Tôi kéo ghế sát bàn rồi đặt cuốn sổ vào vùng sáng để đọc cho rõ."
    )
    content = STORY.replace("Tôi trực tại xưởng sửa đồng hồ trên đồi.",
                            "Tôi trực tại xưởng sửa đồng hồ trên đồi." + extension)
    saved(store, content=content)
    d = draft()
    d["formats"]["short"] = copy.deepcopy(d["formats"]["long"])
    for ch in d["formats"]["short"]["chapters"]:
        ch["id"] = "CH_SYNTHETIC_SHORT"
        for i, beat in enumerate(ch["beats"]):
            beat["id"] = f"BEAT_SYNTHETIC_S{i}"
    result = build_fiction_package(store, "fx", d, NOW)
    pkg = result["package"]
    assert result["report"]["validation"]["warnings"] == []
    assert 45 <= pkg["formats"]["short"]["duration"]["estimated_seconds"] <= 60
    facts = {f["id"]: f for f in pkg["facts"]}
    assert facts["FACT_MINH_ACCOUNT"]["kind"] == "character_claim"
    assert facts["FACT_WRITING"]["kind"] == "later_revelation"
    assert facts["FACT_WRITING"]["conflicts_with"] == ["FACT_MINH_ACCOUNT"]
    assert all(a["status"] == "unresolved" for a in pkg["ambiguities"])
    assert pkg["dialogue"][1]["speaker_id"] is None
    for plan in pkg["formats"].values():
        assert not plan["approved"] and plan["status"] == "draft"
        assert all(b["narration"]["mode"] == "verbatim" for ch in plan["chapters"] for b in ch["beats"])
    assert not list(store.root.rglob("checkpoint_*.json"))


@pytest.mark.parametrize("channel", ["voice_unseen", "text_message", "writing"])
def test_synthetic_unknown_senders_stay_unresolved(store, channel):
    d = draft()
    d["dialogue"][1]["channel"] = channel
    saved(store)
    pkg = build_fiction_package(store, "fx", d, NOW)["package"]
    assert pkg["dialogue"][1]["speaker_id"] is None
    assert pkg["dialogue"][1]["attribution_status"] == "unresolved"
    assert pkg["ambiguities"][0]["status"] == "unresolved"


@pytest.mark.parametrize("change", ["package_approved", "format_approved", "reviewed_status"])
def test_validator_never_declares_a_reviewed_package_ready(store, change):
    pkg = copy.deepcopy(built(store)["package"])
    if change == "package_approved":
        pkg["approved"] = True
    elif change == "format_approved":
        pkg["formats"]["long"]["approved"] = True
    else:
        pkg["status"] = "reviewed"
    with pytest.raises(FictionStoryError):
        validate_package(pkg, source_text=STORY)
