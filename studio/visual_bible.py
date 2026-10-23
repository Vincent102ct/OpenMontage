"""Immutable, canon/asset-bound visual candidates and explicit scene-planning approvals."""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone

from lib.story_visual_bible import (VisualBibleError, compile_bible, default_choices, fingerprint,
                                    library_ref)
from studio.review import _record_hash, review_lock, safe_review_path, write_once
from studio.reviewed import (_bytes, _sha, read_reviewed_story)

OUTPUT_DIR = "artifacts/story_visual_bible"
VERSION = re.compile(r"v[1-9][0-9]*\Z")


def _project(store, project_id):
    # P2.3 verifies the source/request, decision history and every reviewed version.
    reviewed = read_reviewed_story(store, project_id)
    return store._project(project_id), reviewed


def canonical_ref(project, view):
    if not view.get("approval") or view["package"]["blockers"]:
        raise VisualBibleError("canonical_not_ready", "Explicit preproduction-story approval is required.")
    p = view["package"]
    approval = safe_review_path(project, f"artifacts/reviewed_fiction/{view['version']}/approval.json")
    return {"kind": "reviewed_fiction", "version": view["version"], "source_sha256": p["source_sha256"],
            "working_text_sha256": p["working_text_sha256"], "package_sha256": view["package_sha256"],
            "manifest_sha256": view["manifest_sha256"], "approval_sha256": _sha(approval.read_bytes()),
            "decision_history_sha256": fingerprint(view["manifest"]["inputs"]["decisions"])}


def _versions(project):
    folder = safe_review_path(project, OUTPUT_DIR)
    if not folder.exists():
        return []
    if not folder.is_dir():
        raise VisualBibleError("visual_invalid", "Visual storage must be a plain version folder.")
    names = [p.name for p in folder.iterdir() if not p.name.startswith(".tmp-")]
    if any(not VERSION.fullmatch(name) for name in names):
        raise VisualBibleError("visual_invalid", "Unexpected visual version entry; nothing was overwritten.")
    names.sort(key=lambda v: int(v[1:]))
    if names != [f"v{i}" for i in range(1, len(names) + 1)]:
        raise VisualBibleError("visual_invalid", "Visual versions are missing or renumbered.")
    return names


def _read(store, project_id, project, current, version, previous, latest):
    try:
        base = f"{OUTPUT_DIR}/{version}"
        raw = safe_review_path(project, f"{base}/manifest.json").read_bytes()
        manifest = json.loads(raw)
        if (set(manifest) != {"schema_version", "artifact", "project_id", "version", "created_at", "canonical_input",
                              "library", "choices", "package_sha256", "previous_manifest_sha256"}
                or manifest["schema_version"] != "1.0" or manifest["artifact"] != "story_visual_bible_manifest"
                or manifest["version"] != version or manifest["project_id"] != project_id
                or manifest["previous_manifest_sha256"] != previous):
            raise ValueError("Manifest/version chain mismatch")
        pinned = read_reviewed_story(store, project_id, manifest["canonical_input"]["version"])
        if canonical_ref(project, pinned) != manifest["canonical_input"] or library_ref() != manifest["library"]:
            raise ValueError("Pinned canon or library changed")
        package = compile_bible(project_id, version, pinned["package"]["canonical_story"],
                                manifest["canonical_input"], manifest["choices"])
        package_raw = safe_review_path(project, f"{base}/visual_bible.json").read_bytes()
        if package_raw != _bytes(package) or _sha(package_raw) != manifest["package_sha256"]:
            raise ValueError("Visual output differs from pinned inputs/choices")
        approval_path = safe_review_path(project, f"{base}/approval.json")
        approval = json.loads(approval_path.read_bytes()) if approval_path.exists() else None
        hashes = {"package_sha256": _sha(package_raw), "manifest_sha256": _sha(raw)}
        if approval is not None:
            expected = {"artifact": "story_visual_bible_approval", "project_id": project_id, "version": version,
                        **hashes, "approval_scope": "scene_planning_only", "approved": True,
                        "reviewer": "local Studio user", "production_started": False, "publishing_enabled": False}
            if (set(approval) != set(expected) | {"recorded_at", "integrity_sha256"} or package["blockers"]
                    or any(approval.get(k) != v for k, v in expected.items())
                    or not isinstance(approval["recorded_at"], str)
                    or approval["integrity_sha256"] != _record_hash(approval)):
                raise ValueError("Approval mismatch")
        is_current = (version == latest and current.get("ready_for_next_stage", False)
                      and canonical_ref(project, current) == manifest["canonical_input"])
        return {"state": "approved_for_scene_planning" if approval else "candidate", "version": version,
                "package": package, "manifest": manifest, "approval": approval, **hashes,
                "is_current": bool(is_current), "ready_for_next_stage": bool(approval) and bool(is_current),
                "production_started": False, "publishing_enabled": False}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, VisualBibleError) and exc.code == "invalid_version":
            raise
        raise VisualBibleError("visual_invalid", "Visual inputs, asset revisions, version chain, output or approval "
                               "failed verification; nothing was overwritten.") from exc


def read_visual_bible(store, project_id, version=None):
    project, current = _project(store, project_id)
    if version is not None and (not isinstance(version, str) or not VERSION.fullmatch(version)):
        raise VisualBibleError("invalid_version", "Use a visual version such as v1.")
    versions = _versions(project)
    if not versions:
        if version:
            raise VisualBibleError("visual_missing", "Prepare Visual Bible first.")
        return {"state": "missing", "versions": [], "ready_for_next_stage": False,
                "canonical_ready": current.get("ready_for_next_stage", False),
                "production_started": False, "publishing_enabled": False}
    results, previous = {}, None
    for v in versions:
        results[v] = _read(store, project_id, project, current, v, previous, versions[-1])
        previous = results[v]["manifest_sha256"]
    if version and version not in results:
        raise VisualBibleError("visual_missing", "Visual version does not exist.")
    return {**results[version or versions[-1]], "versions": versions,
            "canonical_ready": current.get("ready_for_next_stage", False)}


def _displayed(result, package_sha256, manifest_sha256):
    if not result.get("is_current") or (result["package_sha256"], result["manifest_sha256"]) != (
            package_sha256, manifest_sha256):
        raise VisualBibleError("stale_visual", "The displayed visual version, hashes or canonical input changed. Reload first.")


def prepare_visual_bible(store, project_id, payload, now=None):
    project, _ = _project(store, project_id)
    with review_lock(project):
        project, current = _project(store, project_id)
        if not current.get("ready_for_next_stage"):
            raise VisualBibleError("canonical_not_ready", "Use the current explicitly approved Reviewed Story; resolve story blockers first.")
        ref = canonical_ref(project, current)
        latest = read_visual_bible(store, project_id)
        if payload == {}:
            if latest["state"] != "missing" and latest["is_current"]:
                return {"status": "already_prepared", **latest}
            choices = default_choices(current["package"]["canonical_story"])
        else:
            if not isinstance(payload, dict) or set(payload) != {"base_version", "package_sha256", "manifest_sha256", "choices"}:
                raise VisualBibleError("invalid_binding", "Send visual choices with the exact displayed base version and hashes.")
            if latest["state"] == "missing" or payload["base_version"] != latest["version"]:
                raise VisualBibleError("stale_visual", "Reload the latest visual version before saving changes.")
            _displayed(latest, payload["package_sha256"], payload["manifest_sha256"])
            choices = payload["choices"]
            if choices == latest["manifest"]["choices"]:
                return {"status": "already_prepared", **latest}
        version = f"v{len(latest['versions']) + 1}"
        package = compile_bible(project_id, version, current["package"]["canonical_story"], ref, choices)
        raw = _bytes(package)
        manifest = {"schema_version": "1.0", "artifact": "story_visual_bible_manifest", "project_id": project_id,
                    "version": version, "created_at": (now or datetime.now(timezone.utc)).isoformat(),
                    "canonical_input": ref, "library": library_ref(), "choices": choices, "package_sha256": _sha(raw),
                    "previous_manifest_sha256": latest.get("manifest_sha256")}
        folder = safe_review_path(project, OUTPUT_DIR)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = safe_review_path(project, f"{OUTPUT_DIR}/.tmp-{uuid.uuid4().hex}")
        tmp.mkdir()
        try:
            for name, data in {"visual_bible.json": raw, "manifest.json": _bytes(manifest)}.items():
                with (tmp / name).open("xb") as f:
                    f.write(data)
            target = safe_review_path(project, f"{OUTPUT_DIR}/{version}")
            if target.exists():
                raise VisualBibleError("stale_visual", "Visual version already exists; reload without overwriting.")
            os.rename(tmp, target)
        finally:
            if tmp.exists():
                assert tmp.resolve().is_relative_to(folder.resolve())
                shutil.rmtree(tmp)
        return {"status": "created", **read_visual_bible(store, project_id, version)}


def approve_visual_bible(store, project_id, version, package_sha256, manifest_sha256, now=None):
    project, _ = _project(store, project_id)
    with review_lock(project):
        result = read_visual_bible(store, project_id, version)
        _displayed(result, package_sha256, manifest_sha256)
        if result["package"]["blockers"]:
            raise VisualBibleError("approval_blocked", "Resolve the listed visual blockers before approving.",
                                   result["package"]["blockers"])
        if result["approval"]:
            return {"status": "already_approved", **result}
        record = {"artifact": "story_visual_bible_approval", "project_id": project_id, "version": version,
                  "package_sha256": package_sha256, "manifest_sha256": manifest_sha256,
                  "approval_scope": "scene_planning_only", "approved": True, "reviewer": "local Studio user",
                  "recorded_at": (now or datetime.now(timezone.utc)).isoformat(),
                  "production_started": False, "publishing_enabled": False}
        record["integrity_sha256"] = _record_hash(record)
        write_once(safe_review_path(project, f"{OUTPUT_DIR}/{version}/approval.json"), _bytes(record))
        return {"status": "approved", **read_visual_bible(store, project_id, version)}


def scene_planning_handoff(store, project_id):
    view = read_visual_bible(store, project_id)
    if not view["ready_for_next_stage"]:
        raise VisualBibleError("approval_blocked", "A current approved Visual Bible is required for scene planning.")
    p = view["package"]
    return {"artifact": "visual_scene_planning_handoff", "schema_version": "1.0", "version": view["version"],
            "package_sha256": view["package_sha256"], "manifest_sha256": view["manifest_sha256"],
            **{k: p[k] for k in ("project_id", "canonical_input", "library", "style", "characters", "locations", "props",
                                "continuity", "formats", "approval_scope", "production_started", "publishing_enabled")}}
