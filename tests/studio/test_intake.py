"""P2.1 Story Intake: exact provenance, proposals only, no overwrite and no production."""

import ast
import hashlib
import json
import shutil
import socket
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backlot import server as board_server, state as board_state
from studio import __main__ as studio_cli
from studio.catalog import ApprovedPackages
from studio.intake import FILES, OUTPUT_DIR, IntakeError, prepare_story_intake, read_story_intake
from studio.models import NewProduction
from studio.server import create_app
from studio.store import ProductionStore
from tests.studio.fixtures import fixture_catalog

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "projects/can-phong-cuoi-hanh-lang-p1"
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
STORY = ("# Tiếng gõ lúc nửa đêm\r\n\r\n"
         "Tôi thuê phòng 301 ở tầng ba.\r\n\r\n"
         "Đúng 1 giờ 13 phút, có tiếng gõ cửa.\r\n\r\n"
         "Cốc.\r\n\r\nCốc.\r\n\r\n"
         "Bà chủ nói: “Phòng 302 bỏ trống lâu rồi.”\r\n\r\n"
         "Theo lời Lan, người mẹ đã rời đi lúc 1:13.\r\n\r\n"
         "Biển số 302. \\\r\n\r\n\r\n"
         "Sáng hôm sau tôi kiểm tra phòng 302.\r\n\r\n"
         "**1:13 mẹ về.**\r\n\r\n\r\n\r\n"
         "đây là câu chuyện tôi muốn kể")
EXPECTED_PROPOSAL = (STORY.replace("Biển số 302. \\", "Biển số 302.")
                     .replace("\r\n\r\n\r\n\r\nđây là câu chuyện tôi muốn kể", ""))


def tree_hashes(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def store(tmp_path):
    repo = tmp_path / "repo"
    fixture_catalog(repo)
    projects = tmp_path / "projects"
    projects.mkdir()
    return ProductionStore(projects, ApprovedPackages(repo))


def save(store, project_id="fixture-story", content=STORY, mode="story", **extra):
    data = {"project_id": project_id, "input_mode": mode, "formats": ["short", "long"], **extra}
    if mode == "canonical":
        data["canonical_package_id"] = "test-canonical"
    else:
        data["content"] = content
    return store.create(NewProduction(**data))


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


def test_outputs_keep_exact_spans_hashes_and_pending_review(store):
    save(store)
    project = store.root / "fixture-story"
    before = tree_hashes(project)
    result = prepare_story_intake(store, "fixture-story", NOW)
    assert result["status"] == "created"
    out = project / OUTPUT_DIR
    assert sorted(p.name for p in out.iterdir()) == sorted(FILES.values())
    after = tree_hashes(project)
    assert {k: v for k, v in after.items() if not k.startswith(OUTPUT_DIR)} == before  # Inputs untouched.

    report = json.loads((out / FILES["report"]).read_text(encoding="utf-8"))
    assert report["review"] == {"status": "pending_human_review", "required": True, "approved": False,
                                "approved_by": None}
    assert report["production_started"] is False and report["publishing_enabled"] is False
    assert report["analysis_coverage"]["overall"] == "incomplete"
    assert report["analysis_coverage"]["semantic"]["status"] == "not_performed"
    assert report["checkpoint_integration"]["checkpoint_written"] is False
    assert report["canonical_compatibility"]["compatible_without_fabrication"] is False
    assert report["formats"] == ["short", "long"] and report["style"] == "stickman_horror_2d"
    source = STORY.encode("utf-8")
    prov = report["provenance"]
    assert prov["source"]["sha256"] == hashlib.sha256(source).hexdigest()
    assert prov["source"]["line_endings"] == "CRLF" and prov["source"]["bytes"] == len(source)
    assert prov["production_request"]["sha256"] == hashlib.sha256(
        (project / "artifacts/production_request.json").read_bytes()).hexdigest()
    for name, meta in report["outputs"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == meta["sha256"]
        if name.endswith(".json"):
            assert json.loads((out / name).read_text(encoding="utf-8"))["provenance"] == prov

    assert (out / FILES["proposal"]).read_bytes() == EXPECTED_PROPOSAL.encode("utf-8")
    changes = json.loads((out / FILES["changes"]).read_text(encoding="utf-8"))
    assert [c["rule"] for c in changes["changes"]] == ["stray_line_end_backslash", "trailing_meta_note"]
    for c in changes["changes"]:
        span = c["source_span"]
        assert c["status"] == "proposed" and c["approved"] is False
        assert STORY[span["char_start"]:span["char_end"]] == c["removed_text"]
        assert source[span["byte_start"]:span["byte_end"]] == c["removed_text"].encode("utf-8")
    assert changes["changes"][0]["removed_text"] == " \\"
    assert changes["changes"][1]["removed_text"] == "\r\n\r\n\r\n\r\nđây là câu chuyện tôi muốn kể"
    assert [o["kind"] for o in changes["observations"]] == ["multiple_blank_lines"]  # Reported, not changed.

    segments = json.loads((out / FILES["segments"]).read_text(encoding="utf-8"))["segments"]
    for s in segments:
        assert STORY[s["char_start"]:s["char_end"]] == s["text"]
        assert source[s["byte_start"]:s["byte_end"]] == s["text"].encode("utf-8")
    assert segments[0]["kind"] == "heading" and segments[-1]["proposed_change_ids"] == ["CHG_0002"]
    assert len({s["id"] for s in segments}) == len(segments)

    inventory = json.loads((out / FILES["inventory"]).read_text(encoding="utf-8"))
    times = {t["key"]: t for t in inventory["motifs"]["time_expressions"]}
    assert times["01:13"]["count"] == 3 and times["01:13"]["recurring"]
    numbers = {n["key"]: n["count"] for n in inventory["motifs"]["numbers"]}
    assert numbers["302"] == 3 and numbers["301"] == 1
    assert any(line["key"] == "Cốc." and line["count"] == 2 for line in inventory["motifs"]["repeated_lines"])
    labels = {c["label"] for c in inventory["characters"]}
    assert {"bà chủ", "người mẹ", "mẹ"} <= labels
    assert all(c["status"] == "candidate" and "gender" not in c for c in inventory["characters"])
    assert [d["text"] for d in inventory["dialogue"]] == ["“Phòng 302 bỏ trống lâu rồi.”"]
    assert all(d["speaker_candidate"] is None for d in inventory["dialogue"])
    assert [e["text"] for e in inventory["emphasized_text"]] == ["**1:13 mẹ về.**"]
    kinds = {h["kind"] for h in inventory["human_interpretation"]}
    assert {"semantic_analysis_not_performed", "recurring_time", "recurring_number", "reported_accounts",
            "dialogue_attribution", "emphasized_text", "coreference"} <= kinds
    assert all(h["status"] == "open" for h in inventory["human_interpretation"])
    for item in inventory["characters"] + inventory["locations"] + inventory["objects"]:
        for o in item["occurrences"]:
            assert STORY[o["char_start"]:o["char_end"]] == o["text"]
    assert not list(store.root.rglob("checkpoint_*.json"))


def test_ordinary_text_gets_no_editorial_proposals(store):
    story = ("Dòng có dấu \\ ở giữa vẫn giữ nguyên.\r\n\r\n#hashtag không phải tiêu đề.\r\n\r\n\r\n\r\n"
             "Cuối cùng, cánh cửa đóng lại.")
    save(store, "plain", story)
    prepare_story_intake(store, "plain", NOW)
    out = store.root / "plain" / OUTPUT_DIR
    changes = json.loads((out / FILES["changes"]).read_text(encoding="utf-8"))
    assert changes["changes"] == []
    assert {o["kind"] for o in changes["observations"]} == {"final_paragraph_after_large_gap", "multiple_blank_lines"}
    assert (out / FILES["proposal"]).read_bytes() == story.encode("utf-8")


def test_repeat_runs_return_existing_output_without_rewriting(store):
    save(store)
    first = prepare_story_intake(store, "fixture-story", NOW)
    out = store.root / "fixture-story" / OUTPUT_DIR
    stamp = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in out.iterdir()}
    second = prepare_story_intake(store, "fixture-story")
    assert second["status"] == "already_prepared" and second["report"] == first["report"]
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in out.iterdir()} == stamp
    assert [p.name for p in out.parent.iterdir()] == ["v1"]


def test_concurrent_runs_publish_once(store):
    save(store)
    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(lambda _: prepare_story_intake(store, "fixture-story")["status"], range(4)))
    assert statuses.count("created") == 1 and statuses.count("already_prepared") == 3
    assert [p.name for p in (store.root / "fixture-story" / OUTPUT_DIR).parent.iterdir()] == ["v1"]
    read_story_intake(store, "fixture-story")


def test_outputs_are_deterministic_across_workspaces(store, tmp_path):
    other = ProductionStore(tmp_path / "other", store.catalog)
    save(store)  # Same saved request bytes in both workspaces (request created_at is part of provenance).
    shutil.copytree(store.root / "fixture-story", other.root / "fixture-story")
    for target in (store, other):
        prepare_story_intake(target, "fixture-story", NOW)
    a, b = (s.root / "fixture-story" / OUTPUT_DIR for s in (store, other))
    for name in FILES.values():
        assert (a / name).read_bytes() == (b / name).read_bytes()


@pytest.mark.parametrize("tamper", ["story", "request", "missing_story"])
def test_tampered_or_missing_input_is_refused_before_writing(store, tamper):
    save(store)
    project = store.root / "fixture-story"
    if tamper == "story":
        (project / "input/story.md").write_bytes(STORY.replace("\r\n", "\n").encode("utf-8"))
    elif tamper == "request":
        data = json.loads((project / "artifacts/production_request.json").read_text(encoding="utf-8"))
        data["style"] = "documentary_motion_graphics"
        (project / "artifacts/production_request.json").write_text(json.dumps(data), encoding="utf-8")
    else:
        (project / "input/story.md").unlink()
    with pytest.raises(IntakeError) as exc:
        prepare_story_intake(store, "fixture-story")
    assert exc.value.code == ("invalid_request" if tamper == "request" else "source_mismatch")
    assert not (project / "artifacts/story_intake").exists()


@pytest.mark.parametrize("damage", ["output", "request_after", "partial"])
def test_invalid_existing_output_is_never_overwritten(store, damage):
    save(store)
    project = store.root / "fixture-story"
    out = project / OUTPUT_DIR
    if damage == "partial":
        out.mkdir(parents=True)
        (out / FILES["segments"]).write_text("{}", encoding="utf-8")
    else:
        prepare_story_intake(store, "fixture-story", NOW)
        if damage == "output":
            (out / FILES["inventory"]).write_text("{}", encoding="utf-8")
        else:  # A still-valid edit to the saved request must invalidate the derived draft.
            data = json.loads((project / "artifacts/production_request.json").read_text(encoding="utf-8"))
            data["formats"] = ["long"]
            (project / "artifacts/production_request.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    snapshot = tree_hashes(out)
    for action in (prepare_story_intake, read_story_intake):
        with pytest.raises(IntakeError) as exc:
            action(store, "fixture-story")
        assert exc.value.code == "existing_output_invalid"
    assert tree_hashes(out) == snapshot


def test_unsupported_modes_missing_projects_and_unsafe_ids(store, client):
    save(store, "topic-req", "Bí ẩn ngọn hải đăng", mode="topic")
    save(store, "canon-req", mode="canonical")
    for project_id in ("topic-req", "canon-req"):
        response = client.post(f"/studio/api/productions/{project_id}/intake", json={})
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "unsupported_input_mode"
        assert "Full story" in response.json()["detail"]["message"]
        assert not (store.root / project_id / "artifacts/story_intake").exists()
    assert client.post("/studio/api/productions/missing/intake", json={}).json()["detail"]["code"] == "not_found"
    for bad in ("..", "UPPER", "con", "a.b", "%2e%2e", "..%5Cx", "a" * 65):
        response = client.post(f"/studio/api/productions/{bad}/intake", json={})
        assert response.status_code in (404, 422), bad
    for bad in ("../x", "C:", "nul"):
        with pytest.raises(IntakeError) as exc:
            prepare_story_intake(store, bad)
        assert exc.value.code == "invalid_project_id"
    assert sorted(p.name for p in store.root.iterdir()) == ["canon-req", "topic-req"]


def test_api_ui_list_and_backlot_stay_consistent(store, client):
    save(store)
    board_before = client.get("/api/project/fixture-story/state").json()
    assert client.get("/studio/api/productions/fixture-story/intake").json()["detail"]["code"] == "not_prepared"
    row = client.get("/studio/api/productions").json()[0]
    assert row["intake_status"] == "not_prepared"
    assert client.post("/studio/api/productions/fixture-story/intake", json={},
                       headers={"Origin": "https://evil.invalid"}).status_code == 403
    assert client.post("/studio/api/productions/fixture-story/intake", content="{}",
                       headers={"Content-Type": "text/plain"}).status_code == 415
    assert not (store.root / "fixture-story/artifacts/story_intake").exists()
    created = client.post("/studio/api/productions/fixture-story/intake", json={})
    assert created.status_code == 201 and created.json()["status"] == "created"
    again = client.post("/studio/api/productions/fixture-story/intake", json={})
    assert again.status_code == 200 and again.json()["status"] == "already_prepared"
    shown = client.get("/studio/api/productions/fixture-story/intake").json()
    assert shown["report"]["review"]["status"] == "pending_human_review"
    assert shown["saved_files"] == [f"{OUTPUT_DIR}/{name}" for name in FILES.values()]
    assert client.get("/studio/api/productions").json()[0]["intake_status"] == "prepared"
    board_after = client.get("/api/project/fixture-story/state").json()
    assert not board_after["has_pipeline_state"] and board_after["artifacts"] == board_before["artifacts"]
    assert all(s["status"] == "pending" for s in board_after["stages"])
    page = client.get("/studio").text + client.get("/studio/static/studio.js").text
    assert "Prepare Story Draft" in page and "Pending human review" in page


def test_intake_runs_no_network_processes_or_production(store, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Story Intake must not use the network, processes or production tools")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    from tools.tool_registry import registry
    monkeypatch.setattr(registry, "ensure_discovered", forbidden)
    save(store)
    prepare_story_intake(store, "fixture-story")
    files = {p.suffix for p in store.root.rglob("*") if p.is_file()}
    assert files <= {".json", ".md"}
    tree = ast.parse((ROOT / "studio/intake.py").read_text(encoding="utf-8"))
    imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert all(not m.startswith(("tools", "lib")) or m.startswith("tools.story") for m in imports)
    assert "urllib" not in " ".join(imports) and "subprocess" not in imports


def test_cli_matches_studio_action(store, monkeypatch, capsys):
    import lib.paths
    monkeypatch.setattr(lib.paths, "PROJECTS_DIR", store.root)
    save(store)
    save(store, "topic-req", "Bí ẩn", mode="topic")
    assert studio_cli.main(["intake", "fixture-story"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "created"
    assert studio_cli.main(["intake", "fixture-story"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "already_prepared"
    assert studio_cli.main(["intake", "topic-req"]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == "unsupported_input_mode"


def test_story_053_and_canonical_examples_unchanged(store):
    before = tree_hashes(ROOT / "examples/master-story")
    save(store)
    prepare_story_intake(store, "fixture-story")
    assert tree_hashes(ROOT / "examples/master-story") == before


@pytest.mark.skipif(not (PILOT / "artifacts/production_request.json").is_file(),
                    reason="Real pilot workspace is local-only (projects/ is gitignored).")
def test_real_pilot_copy_preserves_twists_and_flags_two_edits(tmp_path):
    original = tree_hashes(PILOT)
    shutil.copytree(PILOT, tmp_path / PILOT.name, ignore=shutil.ignore_patterns("story_intake"))
    store = ProductionStore(tmp_path, ApprovedPackages(ROOT))
    result = prepare_story_intake(store, PILOT.name, NOW)
    assert tree_hashes(PILOT) == original  # The real pilot is read only through a copy.
    out = tmp_path / PILOT.name / OUTPUT_DIR
    source = (PILOT / "input/story.md").read_bytes()
    changes = result["changes"]
    assert [(c["rule"], c["removed_text"]) for c in changes] == [
        ("stray_line_end_backslash", " \\"),
        ("trailing_meta_note", "\r\n\r\n\r\n\r\nddaay là câu chuyện tôi muốn làm")]
    assert [source[c["source_span"]["byte_start"]:c["source_span"]["byte_end"]] for c in changes] == [
        b" \\", "\r\n\r\n\r\n\r\nddaay là câu chuyện tôi muốn làm".encode("utf-8")]
    segments = json.loads((out / FILES["segments"]).read_text(encoding="utf-8"))["segments"]
    texts = {s["text"]: s["id"] for s in segments}
    assert len(segments) == 251
    inventory = json.loads((out / FILES["inventory"]).read_text(encoding="utf-8"))
    times = {t["key"]: t for t in inventory["motifs"]["time_expressions"]}
    numbers = {n["key"]: n for n in inventory["motifs"]["numbers"]}
    assert times["02:17"]["count"] == 9 and "2:17" in times["02:17"]["variants"]
    assert texts["**2:17 mẹ về.**"] in times["02:17"]["segment_ids"]
    assert numbers["406"]["recurring"] and numbers["407"]["recurring"]
    reported = next(h for h in inventory["human_interpretation"] if h["kind"] == "reported_accounts")
    assert texts["Sau đó tôi mới biết điều bà chưa từng kể."] in reported["segment_ids"]
    people = {c["label"]: c for c in inventory["characters"]}
    assert texts["Đêm xảy ra vụ cháy, người mẹ không đi làm."] in people["người mẹ"]["segment_ids"]
    # The mother's conflicting accounts: the time claim and the later revision both stay linked for review.
    assert texts["“Con bé không chết lúc 2 giờ 17.”"] in times["02:17"]["segment_ids"]
    assert texts["2 giờ 17 phút, camera trước nhà ghi lại cảnh bà ta trở về."] in times["02:17"]["segment_ids"]
    # The voice beneath the bed.
    bed = next(loc for loc in inventory["locations"] if loc.get("vocabulary_kind") == "bedroom")
    assert texts["Rồi từ phía dưới gầm giường…"] in bed["segment_ids"]
    assert "vang lên tiếng một bé gái." in texts
    # The final woman-with-keys reveal.
    keys = next(o for o in inventory["objects"] if o.get("vocabulary_kind") == "key")
    assert texts["là một chùm chìa khóa."] in keys["segment_ids"]
    assert texts["Một người phụ nữ đứng dưới ánh đèn đường, quay lưng về phía camera."] in people["người phụ nữ"][
        "segment_ids"]
    assert (out / FILES["proposal"]).read_bytes() == source.replace(b"407. \\", b"407.").replace(
        "\r\n\r\n\r\n\r\nddaay là câu chuyện tôi muốn làm".encode("utf-8"), b"")
