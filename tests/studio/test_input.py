"""Studio request validation/persistence and unchanged Backlot compatibility."""

import ast
import hashlib
import json
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from backlot import server as board_server, state as board_state
from studio.catalog import ApprovedPackages
from studio.models import NewProduction, ProductionRequest
from studio.server import create_app
from studio.store import ProductionStore, derive_title
from tests.studio.fixtures import fixture_catalog

ROOT = Path(__file__).resolve().parents[2]
TEXT = "  Đêm ấy, tôi nghe tiếng gõ cửa.\r\n\r\n“Có ai ở đó không?”\n\tKhông có tiếng trả lời.  "


@pytest.fixture
def context(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    package = fixture_catalog(repo)
    projects = tmp_path / "projects"
    projects.mkdir()
    store = ProductionStore(projects, ApprovedPackages(repo))
    monkeypatch.setattr(board_state, "PROJECTS_DIR", projects)
    monkeypatch.setattr(board_server, "PROJECTS_DIR", projects)
    monkeypatch.setattr(board_server, "_summary_cache", {})
    monkeypatch.setattr(board_server, "THUMB_CACHE_DIR", tmp_path / "thumbs")
    async def no_watch():
        return
    monkeypatch.setattr(board_server, "_watch_projects", no_watch)
    with TestClient(create_app(store), base_url="http://127.0.0.1") as client:
        yield client, store, repo, package


def payload(**overrides):
    return {"project_id": "test-story", "input_mode": "story", "content": TEXT,
            "formats": ["short", "long"], **overrides}


def test_vietnamese_original_bytes_hash_schema_and_board(context):
    client, store, _, _ = context
    response = client.post("/studio/api/productions", json=payload())
    assert response.status_code == 201, response.text
    saved = response.json()
    req = saved["request"]
    assert req["content"] == TEXT
    assert req["content_sha256"] == hashlib.sha256(TEXT.encode("utf-8")).hexdigest()
    assert (store.root / "test-story/input/story.md").read_bytes() == TEXT.encode("utf-8")
    assert req["formats"] == ["short", "long"]
    assert req["status"] == "production_not_started"
    assert req["review_status"] == "pending_human_review"
    assert req["publishing_enabled"] is False
    assert req["style"] == "stickman_horror_2d"
    assert req["created_at"].endswith("Z")
    schema = json.loads((ROOT / "schemas/studio/production_request.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(req)
    assert schema == ProductionRequest.model_json_schema()
    assert client.get("/studio/api/productions/test-story").json() == saved
    state = client.get("/api/project/test-story/state").json()
    assert state["has_marker"] and not state["has_pipeline_state"]
    assert all(s["status"] == "pending" for s in state["stages"])
    assert state["events"] == [] and not state["artifacts"]
    assert client.get(saved["backlot_url"]).status_code == 200
    actual_files = {p.relative_to(store.root / "test-story").as_posix()
                    for p in (store.root / "test-story").rglob("*") if p.is_file()}
    assert actual_files == set(saved["saved_files"])


@pytest.mark.parametrize("formats", [["short"], ["long"], ["short", "long"]])
def test_topic_readiness_formats_and_auto_ids(context, formats):
    client, store, _, _ = context
    response = client.post("/studio/api/productions", json=payload(
        project_id=None, input_mode="topic", content="Bí ẩn một ngọn hải đăng", formats=formats))
    assert response.status_code == 201
    req = response.json()["request"]
    assert req["project_id"].startswith("studio-") and req["formats"] == formats
    assert req["input_readiness"] == "unresearched_topic"
    assert req["canonical_package"] is None
    assert not (store.root / req["project_id"] / "artifacts/research_brief.json").exists()


def test_canonical_saves_only_bound_reference(context):
    client, store, _, package = context
    original = package.read_bytes()
    listing = client.get("/studio/api/packages").json()
    assert len(listing["packages"]) == 1
    response = client.post("/studio/api/productions", json=payload(
        input_mode="canonical", content=None, canonical_package_id="test-canonical"))
    assert response.status_code == 201, response.text
    req = response.json()["request"]
    assert req["content"] is None and req["canonical_package"]["package_id"] == "STORY_999"
    assert req["content_sha256"] == hashlib.sha256(original).hexdigest()
    assert "claims" not in json.dumps(req)
    assert package.read_bytes() == original
    assert json.loads((store.root / "test-story/input/canonical-reference.json").read_text()) == req["canonical_package"]
    assert req["review_status"] == "pending_human_review"


def test_changed_or_unapproved_package_is_not_selectable(context):
    client, store, repo, package = context
    package.write_bytes(package.read_bytes() + b"\n")
    listing = client.get("/studio/api/packages").json()
    assert listing["packages"] == [] and listing["warnings"]
    response = client.post("/studio/api/productions", json=payload(
        input_mode="canonical", content=None, canonical_package_id="test-canonical"))
    assert response.status_code == 422 and not list(store.root.iterdir())
    assert ApprovedPackages(ROOT).available() == ([], [])  # No production packages self-approved.


@pytest.mark.parametrize("patch", [
    {"input_mode": "unknown"}, {"content": "\r\n \t"}, {"content": "x\0y"},
    {"content": "x" * 200001}, {"formats": []}, {"formats": ["both"]},
    {"formats": ["short", "short"]}, {"formats": ["short", "long", "short"]},
    {"style": "documentary_motion_graphics"}, {"review_mode": "auto"},
    {"publishing_enabled": True}, {"publishing_enabled": 0},
    {"status": "completed"}, {"canonical_package_id": "test-canonical"},
    {"input_mode": "canonical", "content": None, "canonical_package_id": "missing"},
    {"input_mode": "canonical", "canonical_package_id": "test-canonical"},
    {"source_filename": "../story.md"}, {"source_filename": "C:\\story.md"},
    {"source_filename": "story.html"}, {"title": "\n"},
])
def test_mode_and_contract_validation_never_writes(context, patch):
    client, store, _, _ = context
    response = client.post("/studio/api/productions", json=payload(**patch))
    assert response.status_code == 422, response.text
    assert list(store.root.iterdir()) == []


@pytest.mark.parametrize("project_id", ["..", "../outside", "a/b", "a\\b", "C:", "c:evil", "/root",
                                        "con", "nul", "com1", "lpt1", "UPPER", "a.b", "a" * 65, "a\0b"])
def test_project_id_safety(context, project_id):
    client, store, _, _ = context
    assert client.post("/studio/api/productions", json=payload(project_id=project_id)).status_code == 422
    assert not list(store.root.iterdir())


def test_no_overwrite_even_empty_or_legacy_projects(context):
    client, store, _, _ = context
    assert client.post("/studio/api/productions", json=payload()).status_code == 201
    original = {p: p.read_bytes() for p in (store.root / "test-story").rglob("*") if p.is_file()}
    assert client.post("/studio/api/productions", json=payload(content="Other")).status_code == 409
    assert all(p.read_bytes() == raw for p, raw in original.items())
    (store.root / "empty").mkdir()
    assert client.post("/studio/api/productions", json=payload(project_id="empty")).status_code == 409
    legacy = store.root / "old-project"
    legacy.mkdir()
    marker = b'{"title":"Legacy workspace","pipeline_type":"cinematic"}'
    (legacy / "project.json").write_bytes(marker)
    assert client.post("/studio/api/productions", json=payload(project_id="old-project")).status_code == 409
    rows = client.get("/studio/api/productions").json()
    assert next(r for r in rows if r["project_id"] == "old-project")["kind"] == "existing_workspace"
    assert (legacy / "project.json").read_bytes() == marker


def test_concurrent_save_reserves_id_once(context):
    _, store, _, _ = context
    from studio.store import ProjectExistsError
    def save(_):
        try:
            return store.create(NewProduction(**payload()))["request"]["project_id"]
        except ProjectExistsError:
            return "conflict"
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(save, range(4)))
    assert results.count("test-story") == 1 and results.count("conflict") == 3
    store.detail("test-story")


def test_xss_is_literal_text_and_markdown_filename_is_metadata(context):
    client, store, _, _ = context
    script = '<script>window.injected = true</script>\r\nTiếng Việt <img src=x onerror=alert(1)>'
    response = client.post("/studio/api/productions", json=payload(content=script, source_filename="truyện.md"))
    assert response.status_code == 201
    assert response.json()["request"]["content"] == script
    assert (store.root / "test-story/input/story.md").read_bytes() == script.encode("utf-8")
    assert not (store.root / "test-story/truyện.md").exists()


def test_cross_origin_non_json_and_large_requests_rejected(context):
    client, store, _, _ = context
    assert client.post("/studio/api/productions", json=payload(), headers={"Origin": "https://evil.invalid"}).status_code == 403
    assert client.post("/studio/api/productions", json=payload(), headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.post("/studio/api/productions", content="x", headers={"Content-Type": "text/plain"}).status_code == 415
    assert client.post("/studio/api/productions", content=b"x" * 2_000_001,
                       headers={"Content-Type": "application/json"}).status_code == 413
    assert client.get("/studio", headers={"Host": "evil.invalid"}).status_code == 400
    assert not list(store.root.iterdir())


def test_saving_cannot_invoke_production_or_network(context, monkeypatch):
    client, store, _, _ = context
    def forbidden(*args, **kwargs):
        raise AssertionError("Input MVP must not run processes or make external requests")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    from tools.tool_registry import registry
    monkeypatch.setattr(registry, "ensure_discovered", forbidden)
    for mode in ["topic", "story", "canonical"]:
        response = client.post("/studio/api/productions", json=payload(project_id=f"no-run-{mode}",
            input_mode=mode, content=None if mode == "canonical" else TEXT,
            canonical_package_id="test-canonical" if mode == "canonical" else None))
        assert response.status_code == 201, response.text
    assert not list(store.root.rglob("checkpoint_*.json"))
    assert not list(store.root.rglob("events.jsonl"))
    assert not list(store.root.rglob("*.mp4")) and not list(store.root.rglob("*.wav"))
    # Import boundary is part of the no-production guarantee (Backlot is monitoring only).
    for name in ["models.py", "catalog.py", "store.py", "server.py"]:
        tree = ast.parse((ROOT / "studio" / name).read_text(encoding="utf-8"))
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not any(m.startswith(("tools", "lib.checkpoint", "lib.canonical_assets")) for m in imports)


def test_ui_routes_health_empty_loading_security_and_no_write_backlot(context):
    client, _, _, _ = context
    page = client.get("/studio")
    assert page.status_code == 200
    for text in ["New Production", "My Productions", "Production not started", "Publishing", "Open Backlot"]:
        assert text in page.text
    assert "default-src 'self'" in page.headers["Content-Security-Policy"]
    assert client.get("/studio/static/studio.js").status_code == 200
    assert client.get("/studio/api/health").json()["app"] == "openmontage-studio"
    assert client.get("/studio/api/productions").json() == []
    assert client.get("/").status_code == 200
    assert client.post("/api/projects", json=payload()).status_code == 405
    assert client.get("/studio/api/productions/missing").status_code == 404


def test_catalog_path_escape_and_duplicate_ids_fail_closed(context):
    client, _, repo, _ = context
    path = repo / "studio/approved_packages.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["packages"][0]["path"] = "examples/master-story/../../secret.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert client.get("/studio/api/packages").json()["packages"] == []
    data["packages"].append(data["packages"][0])
    path.write_text(json.dumps(data), encoding="utf-8")
    assert client.get("/studio/api/packages").json()["warnings"]


def test_tampered_persistence_is_rejected(context):
    client, store, _, _ = context
    client.post("/studio/api/productions", json=payload())
    (store.root / "test-story/input/story.md").write_text("Changed", encoding="utf-8")
    assert client.get("/studio/api/productions/test-story").status_code == 400


@pytest.mark.parametrize("content, title", [
    ("# Căn phòng cuối hành lang\r\n\r\nĐêm ấy.", "Căn phòng cuối hành lang"),
    ("## Chapter One\nText", "Chapter One"),
    ("###### Deep\n", "Deep"),
    ("   # Indented heading", "Indented heading"),
    ("# Closed heading ##\n", "Closed heading"),
    ("# C# notes\n", "C# notes"),
    ("\n\n  # After blank lines\n", "After blank lines"),
    ("Ordinary story title\n# Later heading", "Ordinary story title"),
    ("#hashtag is not a heading", "#hashtag is not a heading"),
    ("####### seven hashes", "####### seven hashes"),
    ("    # code block indent", "# code block indent"),
    ("Room #407 at night", "Room #407 at night"),
    ("#\nBody", "#"),
    ("# " + "x" * 200, "x" * 120),
])
def test_derived_title_drops_only_markdown_heading_marker(content, title):
    assert derive_title(content) == title


def test_heading_title_is_clean_while_source_bytes_and_hash_are_unchanged(context):
    client, store, _, _ = context
    story = "# Căn phòng cuối hành lang\r\n\r\nPhòng #406.\r\n\r\n## Phần hai\r\n"
    response = client.post("/studio/api/productions", json=payload(content=story, title=None,
                                                                   source_filename="truyen.vi.md"))
    assert response.status_code == 201, response.text
    req = response.json()["request"]
    assert req["title"] == "Căn phòng cuối hành lang"
    assert req["content"] == story
    assert req["content_sha256"] == hashlib.sha256(story.encode("utf-8")).hexdigest()
    assert (store.root / "test-story/input/story.md").read_bytes() == story.encode("utf-8")
    marker = json.loads((store.root / "test-story/project.json").read_text(encoding="utf-8"))
    assert marker["title"] == "Căn phòng cuối hành lang"
    assert client.get("/api/project/test-story/state").json()["title"] == "Căn phòng cuối hành lang"
    assert next(r for r in client.get("/studio/api/productions").json()
                if r["project_id"] == "test-story")["title"] == "Căn phòng cuối hành lang"


def test_explicit_title_is_kept_verbatim(context):
    client, _, _, _ = context
    response = client.post("/studio/api/productions", json=payload(content="# Heading\nBody", title="# Literal title"))
    assert response.json()["request"]["title"] == "# Literal title"
