"""Synthetic canon -> immutable visual review -> verified scene-planning handoff."""
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lib.story_visual_bible import VisualBibleError, catalog
from studio.catalog import ApprovedPackages
from studio.review import ReviewError, load_log, record_decision, review_lock
from studio.reviewed import materialize_reviewed_story, approve_reviewed_story
from studio.server import create_app
from studio.store import ProductionStore
from studio.visual_bible import (OUTPUT_DIR, approve_visual_bible, prepare_visual_bible, read_visual_bible,
                                 scene_planning_handoff)
from tests.studio.test_fiction import tree
from tests.studio.visual_bible_fixture import STORY, bound_choices, draft, prepare_story
from tools.character import horror_assets as assets

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def store(tmp_path):
    return ProductionStore(tmp_path / "projects", ApprovedPackages(ROOT))


def save(store, base, choices=None):
    return prepare_visual_bible(store, "fx", {"base_version": base["version"],
        "package_sha256": base["package_sha256"], "manifest_sha256": base["manifest_sha256"],
        "choices": choices or bound_choices(base)})


def approved(store):
    prepare_story(store)
    candidate = save(store, prepare_visual_bible(store, "fx", {}))
    assert not candidate["package"]["blockers"], candidate["package"]["blockers"]
    return approve_visual_bible(store, "fx", candidate["version"], candidate["package_sha256"], candidate["manifest_sha256"])


def test_synthetic_two_characters_two_locations_shared_formats_and_handoff(store):
    reviewed = prepare_story(store)
    before = tree(store.root / "fx")
    initial = prepare_visual_bible(store, "fx", {})
    assert initial["package"]["blockers"] and not initial["ready_for_next_stage"]
    with pytest.raises(VisualBibleError, match="blockers"):
        approve_visual_bible(store, "fx", initial["version"], initial["package_sha256"], initial["manifest_sha256"])
    view = save(store, initial)
    assert not view["package"]["blockers"] and not view["approval"]
    assert len(view["package"]["characters"]) == len(view["package"]["locations"]) == 2
    assert view["package"]["formats"]["short"] == view["package"]["formats"]["long"]
    assert view["package"]["canonical_input"]["package_sha256"] == reviewed["package_sha256"]
    assert view["package"]["canonical_input"]["approval_sha256"]
    assert "C:\\" not in json.dumps(view["package"]) and str(store.root) not in json.dumps(view["package"])
    assert all(c["provenance"]["design_basis"] == "creative_proposal_not_canonical_fact" for c in view["package"]["characters"])
    assert all("presence" not in l["geometry"] for l in view["package"]["locations"])
    result = approve_visual_bible(store, "fx", view["version"], view["package_sha256"], view["manifest_sha256"])
    assert result["ready_for_next_stage"] and result["approval"]["approval_scope"] == "scene_planning_only"
    assert result["package"]["review_status"] == "pending_explicit_visual_approval"  # File cannot approve itself.
    assert scene_planning_handoff(store, "fx")["characters"] == result["package"]["characters"]
    assert all(tree(store.root / "fx")[p] == h for p, h in before.items())
    assert not list(store.root.rglob("checkpoint_*.json")) and not list(store.root.rglob("*.mp4"))
    assert not list(store.root.rglob("*.wav"))


def test_unapproved_and_no_longer_current_story_cannot_prepare(store):
    prepare_story(store, approve=False)
    with pytest.raises(VisualBibleError, match="current explicitly approved"):
        prepare_visual_bible(store, "fx", {})
    assert not (store.root / "fx" / OUTPUT_DIR).exists()


@pytest.mark.parametrize("mutation", ["missing_character", "missing_location", "duplicate_identity", "unreviewed",
                                     "bad_light", "bad_anchor", "prop_location", "unseen_required", "unbound_prop"])
def test_visual_continuity_blockers_prevent_approval(store, mutation):
    prepare_story(store)
    initial = prepare_visual_bible(store, "fx", {})
    choices = bound_choices(initial)
    if mutation == "missing_character": choices["characters"]["CHR_AN"]["asset"] = None
    if mutation == "missing_location": choices["locations"]["LOC_ROOM"]["environment"] = None
    if mutation == "duplicate_identity": choices["characters"]["CHR_BINH"]["asset"] = choices["characters"]["CHR_AN"]["asset"]
    if mutation == "unreviewed": choices["characters"]["CHR_AN"]["reviewed"] = False
    if mutation == "bad_light": choices["locations"]["LOC_HALL"]["lighting"] = {"id": "cold_moonlight", "revision": 1}
    if mutation == "bad_anchor": choices["props"]["OBJ_DOOR"]["anchor"] = "doors.p31_room.handle"
    if mutation == "prop_location": choices["props"]["OBJ_DOOR"]["location_id"] = "LOC_HALL"
    if mutation == "unseen_required": choices["characters"]["CHR_AN"].update(representation="unseen", asset=None)
    if mutation == "unbound_prop": choices["props"]["OBJ_LAMP"]["asset"] = None
    candidate = save(store, initial, choices)
    assert candidate["package"]["blockers"]
    with pytest.raises(VisualBibleError) as error:
        approve_visual_bible(store, "fx", candidate["version"], candidate["package_sha256"], candidate["manifest_sha256"])
    assert error.value.code == "approval_blocked"
    with pytest.raises(VisualBibleError): scene_planning_handoff(store, "fx")


@pytest.mark.parametrize("bad", [None, True, 1.0, "1", 0, -1, 99])
def test_missing_or_invalid_pins_refused_before_writing(store, bad):
    prepare_story(store); initial = prepare_visual_bible(store, "fx", {})
    before = tree(store.root / "fx"); choices = bound_choices(initial)
    choices["characters"]["CHR_AN"]["asset"]["revision"] = bad
    with pytest.raises(VisualBibleError): save(store, initial, choices)
    assert tree(store.root / "fx") == before


def test_approved_design_changes_create_new_version_and_stale_old_tabs(store):
    current = approved(store); before = tree(store.root / "fx" / OUTPUT_DIR / current["version"])
    choices = copy.deepcopy(current["manifest"]["choices"])
    choices["locations"]["LOC_HALL"]["lighting"] = {"id": "flickering_interior", "revision": 1}
    choices["locations"]["LOC_HALL"]["reviewed"] = False
    newer = save(store, current, choices)
    assert newer["version"] == "v3" and not newer["ready_for_next_stage"]
    assert tree(store.root / "fx" / OUTPUT_DIR / current["version"]) == before
    assert not read_visual_bible(store, "fx", current["version"])["is_current"]
    with pytest.raises(VisualBibleError): save(store, current)
    with pytest.raises(VisualBibleError): approve_visual_bible(store, "fx", current["version"], current["package_sha256"], current["manifest_sha256"])


def test_new_story_decisions_stale_visual_and_require_new_canon_approval(store):
    visual = approved(store)
    old = next(d for d in reversed(load_log(store.root / "fx")) if d["target_id"] == "AMB_SOURCE")
    record_decision(store, "fx", {"target_id": "AMB_SOURCE", "decision": "preserve_ambiguity", "supersedes": old["decision_id"]})
    assert not read_visual_bible(store, "fx")["ready_for_next_stage"]
    with pytest.raises(VisualBibleError): prepare_visual_bible(store, "fx", {})
    with pytest.raises(VisualBibleError): scene_planning_handoff(store, "fx")
    reviewed = materialize_reviewed_story(store, "fx")
    approve_reviewed_story(store, "fx", reviewed["version"], reviewed["package_sha256"], reviewed["manifest_sha256"])
    fresh = prepare_visual_bible(store, "fx", {})
    assert fresh["package"]["canonical_input"] != visual["package"]["canonical_input"]
    assert not fresh["approval"] and fresh["package"]["blockers"]


@pytest.mark.parametrize("file", ["visual_bible.json", "manifest.json", "approval.json"])
def test_tampered_visual_files_refused_without_overwriting(store, file):
    view = approved(store)
    path = store.root / "fx" / OUTPUT_DIR / view["version"] / file
    data = json.loads(path.read_text()); data["production_started"] = True
    path.write_text(json.dumps(data)); before = tree(store.root / "fx")
    for operation in (lambda: read_visual_bible(store, "fx"), lambda: prepare_visual_bible(store, "fx", {}),
                      lambda: scene_planning_handoff(store, "fx")):
        with pytest.raises(VisualBibleError): operation()
    assert tree(store.root / "fx") == before


def test_library_change_and_defensive_copy_and_shared_lock(store, monkeypatch):
    view = approved(store)
    with review_lock(store.root / "fx"):
        with pytest.raises(ReviewError): approve_visual_bible(store, "fx", view["version"], view["package_sha256"], view["manifest_sha256"])
    design = assets.get("character", "nora_vale", 1); design["design"]["outfit"] = "cardigan"
    assert read_visual_bible(store, "fx")["ready_for_next_stage"]
    monkeypatch.setitem(assets.CHARACTERS, "nora_vale", design)
    with pytest.raises(VisualBibleError): read_visual_bible(store, "fx")


def test_local_http_workflow_and_gets_are_read_only(store):
    prepare_story(store); client = TestClient(create_app(store), base_url="http://127.0.0.1")
    base = "/studio/api/productions/fx/visual-bible"
    before = tree(store.root / "fx")
    assert client.get(base).json()["state"] == "missing" and tree(store.root / "fx") == before
    assert client.get("/studio/api/visual-assets").json()["library"] == catalog()["library"]
    assert client.post(base, json={}, headers={"Origin": "https://elsewhere.invalid"}).status_code == 403
    assert client.post(base, content="{}", headers={"Content-Type": "text/plain"}).status_code == 415
    initial = client.post(base, json={}).json()
    payload = {"base_version": initial["version"], "package_sha256": initial["package_sha256"],
               "manifest_sha256": initial["manifest_sha256"], "choices": bound_choices(initial)}
    candidate = client.post(base, json=payload).json()
    hashes = {k: candidate[k] for k in ("package_sha256", "manifest_sha256")}
    approve = f"{base}/{candidate['version']}/approve"
    assert client.post(approve, json={**hashes, "package_sha256": "0" * 64}).status_code == 409
    assert client.post(approve, json=hashes).json()["ready_for_next_stage"]
    before = tree(store.root / "fx")
    assert client.get(base + "/handoff").json()["approval_scope"] == "scene_planning_only"
    assert client.get(base + "/v999").status_code == 404
    assert tree(store.root / "fx") == before


def test_partial_presence_requires_explicit_canonical_character_location_and_visual_review(store):
    authored = draft()
    source = STORY + "\n\nMột bóng không rõ hình dạng thoáng qua cuối hành lang."
    authored["locations"][1]["evidence"] = [{"segment_id": "SEG_0003", "quote": "hành lang"}]
    authored["characters"].append({"id": "CHR_SHAPE", "name": "Unidentified partial shape", "aliases": [],
        "description": "Partial and unidentified; no face is known.", "identity_status": "ambiguous",
        "on_screen_policy": "partial", "evidence": ["Một bóng không rõ hình dạng"]})
    authored["events"][-1]["participant_ids"].append("CHR_SHAPE")
    authored["events"][-1]["segments"].append("SEG_0006")
    for plan in authored["formats"].values():
        plan["chapters"][0]["beats"][-1]["narration"]["spans"] = ["SEG_0003..SEG_0006"]
        plan["chapters"][0]["beats"][-1]["character_ids"].append("CHR_SHAPE")
    prepare_story(store, authored=authored, source=source)
    initial = prepare_visual_bible(store, "fx", {})
    choices = bound_choices(initial)
    assert choices["characters"]["CHR_SHAPE"]["representation"] == "unseen"
    choices["characters"]["CHR_SHAPE"].update(representation="silhouette", asset={"id": "tall_hooded", "revision": 1})
    choices["locations"]["LOC_HALL"]["presence"] = {"character_id": "CHR_SHAPE", "anchor": "corridor_end"}
    view = save(store, initial, choices)
    assert not view["package"]["blockers"]
    hall = next(l for l in view["package"]["locations"] if l["canonical_id"] == "LOC_HALL")
    assert hall["geometry"]["presence"]["silhouette"] == "tall_hooded"
    bad = copy.deepcopy(choices); bad["characters"]["CHR_SHAPE"].update(representation="character", asset={"id": "nora_vale", "revision": 1})
    bad["locations"]["LOC_HALL"]["presence"] = None
    blocked = save(store, view, bad)
    assert any("UNCERTAINTY" in b for b in blocked["package"]["blockers"])


@pytest.mark.parametrize("mutation", ["unknown_role", "custom_costume", "per_format_override", "extra_lighting", "invented_presence"])
def test_unknown_or_contradictory_design_inputs_are_refused(store, mutation):
    prepare_story(store); initial = prepare_visual_bible(store, "fx", {}); choices = bound_choices(initial)
    if mutation == "unknown_role": choices["characters"]["CHR_EXTRA"] = copy.deepcopy(choices["characters"]["CHR_AN"])
    if mutation == "custom_costume": choices["characters"]["CHR_AN"]["outfit"] = "another_costume"
    if mutation == "per_format_override": choices["formats"] = {"short": "different_character"}
    if mutation == "extra_lighting": choices["locations"]["LOC_HALL"]["lighting"]["fallback"] = "p31_room"
    if mutation == "invented_presence": choices["locations"]["LOC_HALL"]["presence"] = {"character_id": "CHR_GHOST", "anchor": "corridor_end"}
    before = tree(store.root / "fx")
    with pytest.raises(VisualBibleError): save(store, initial, choices)
    assert tree(store.root / "fx") == before


@pytest.mark.parametrize("link", ["symlink", "reparse"])
def test_visual_paths_reject_links_before_reading_or_writing(store, monkeypatch, tmp_path, link):
    approved(store); project = store.root / "fx"; outside = tmp_path / "outside"; outside.mkdir()
    if link == "symlink":
        path = project / OUTPUT_DIR / "v3"
        try: path.symlink_to(outside, target_is_directory=True)
        except OSError: pytest.skip("OS does not allow symlink creation.")
    else:
        original = Path.lstat; watched = project / OUTPUT_DIR
        def attributes(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == watched:
                class Reparse:
                    st_file_attributes = 0x400
                    def __getattr__(self, key):
                        return getattr(result, key)
                return Reparse()
            return result
        monkeypatch.setattr(Path, "lstat", attributes)
    with pytest.raises((ReviewError, VisualBibleError)): read_visual_bible(store, "fx")
    assert list(outside.iterdir()) == []


def test_more_roles_than_available_identities_stay_explicitly_unbound(store):
    from tests.studio.reviewed_fixture import prepare, complete
    prepare(store); complete(store)
    canon = materialize_reviewed_story(store, "fx")
    approve_reviewed_story(store, "fx", canon["version"], canon["package_sha256"], canon["manifest_sha256"])
    view = prepare_visual_bible(store, "fx", {})
    assert any("MISSING_ASSET CHR_MINH" in b for b in view["package"]["blockers"])
    assert not view["ready_for_next_stage"]


def test_canonical_prop_without_optional_location_is_an_explicit_visual_decision(store):
    authored = draft(); del authored["objects"][0]["location_id"]
    prepare_story(store, authored=authored)
    initial = prepare_visual_bible(store, "fx", {})
    assert initial["package"]["props"][0]["location_id"] is None
    choices = bound_choices(initial); choices["props"]["OBJ_DOOR"]["location_id"] = "LOC_ROOM"
    view = save(store, initial, choices)
    assert not view["package"]["blockers"], view["package"]["blockers"]


@pytest.fixture
def reference_cache(store):
    """Small verified cache for hostile-path/corruption tests; real PNG rendering has its own browser proof."""
    from lib.story_visual_bible import fingerprint
    from studio.reviewed import _bytes, _sha
    from studio.visual_references import OUTPUT_DIR as REFS

    view = approved(store)
    key = "a" * 64
    folder = store.root / "fx" / REFS / key
    folder.mkdir(parents=True)
    raw = b"\x89PNG\r\n\x1a\nreference-cache-test"
    (folder / "ref-0.png").write_bytes(raw)
    report = {"key": key, "package_sha256": view["package_sha256"],
              "manifest_sha256": view["manifest_sha256"],
              "references": [{"file": "ref-0.png", "sha256": _sha(raw)}]}
    report["integrity_sha256"] = fingerprint(report)
    (folder / "references.json").write_bytes(_bytes(report))
    return view, key, folder, report


@pytest.mark.parametrize("key,name", [("../artifacts", "ref-0.png"), ("https://example.invalid", "ref-0.png"),
    ("a" * 64, "../../approval.json"), ("a" * 64, "references.json"), ("a" * 64, "ref-999.png")])
def test_reference_route_refuses_traversal_urls_and_non_manifest_files(store, reference_cache, key, name):
    from studio.visual_references import reference_file
    before = tree(store.root / "fx")
    with pytest.raises(VisualBibleError):
        reference_file(store, "fx", key, name)
    assert tree(store.root / "fx") == before


@pytest.mark.parametrize("mutation", ["png", "manifest", "unsafe_filename", "foreign_visual", "stale"])
def test_reference_cache_fails_closed_for_corruption_wrong_visual_and_stale_canon(store, reference_cache, mutation):
    from lib.story_visual_bible import fingerprint
    from studio.reviewed import _bytes
    from studio.visual_references import reference_file
    view, key, folder, report = reference_cache
    assert reference_file(store, "fx", key, "ref-0.png") == folder / "ref-0.png"
    if mutation == "png":
        (folder / "ref-0.png").write_bytes(b"changed")
    elif mutation == "stale":
        old = next(d for d in reversed(load_log(store.root / "fx")) if d["target_id"] == "AMB_SOURCE")
        record_decision(store, "fx", {"target_id": "AMB_SOURCE", "decision": "preserve_ambiguity",
                                     "supersedes": old["decision_id"]})
    else:
        if mutation == "manifest": report["integrity_sha256"] = "0" * 64
        if mutation == "unsafe_filename": report["references"][0]["file"] = "../../approval.json"
        if mutation == "foreign_visual": report["package_sha256"] = "0" * 64
        if mutation != "manifest":
            report["integrity_sha256"] = fingerprint({k: v for k, v in report.items() if k != "integrity_sha256"})
        (folder / "references.json").write_bytes(_bytes(report))
    before = tree(store.root / "fx")
    with pytest.raises(VisualBibleError):
        reference_file(store, "fx", key, "ref-0.png")
    assert tree(store.root / "fx") == before


def test_reference_cache_reparse_escape_is_refused_for_read_and_generation(store, reference_cache, monkeypatch):
    from studio.visual_references import prepare_references, reference_file
    view, key, folder, _ = reference_cache
    original = Path.lstat
    def attributes(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path == folder.parent:
            class Reparse:
                st_file_attributes = 0x400
                def __getattr__(self, name):
                    return getattr(result, name)
            return Reparse()
        return result
    monkeypatch.setattr(Path, "lstat", attributes)
    with pytest.raises(VisualBibleError, match="Reference files failed verification"):
        reference_file(store, "fx", key, "ref-0.png")
    with pytest.raises(ReviewError):
        prepare_references(store, "fx", view["version"], view["package_sha256"], view["manifest_sha256"])
