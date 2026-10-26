"""Immutable P3.4 scene-plan versions bound to current approved canon and Visual Bible, with explicit approval."""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone

from lib.story_scene_plan import (ScenePlanError, acting_pin, action_timeline, compile_plan, coverage_report,
                                  handoff_coverage, measurement_contract, rebase_choices, retime, vocabulary)
from lib.story_visual_bible import VisualBibleError, fingerprint
from studio.review import _record_hash, review_lock, safe_review_path, write_once
from studio.intake import _project_dir
from studio.reviewed import _bytes, _sha, read_reviewed_story
from studio.visual_bible import canonical_ref, handoff_from_view, read_visual_bible, scene_planning_handoff

OUTPUT_DIR = "artifacts/story_scene_plan"
VERSION = re.compile(r"v[1-9][0-9]*\Z")
ACTING = ("cautious_walk", "guarded_reach", "listening_freeze", "startled_reaction")
MANIFEST_KEYS = {"schema_version", "artifact", "project_id", "version", "created_at", "inputs", "choices",
                 "package_sha256", "previous_manifest_sha256"}
NOT_READY = {"canonical_not_ready": "A current, explicitly approved Reviewed Story is required.",
             "visual_not_ready": "A current, explicitly approved Visual Bible for that story is required."}


def _inputs(project, reviewed, visual):
    """Exact pins: reviewed story, Visual Bible (incl. approval file), library, selected assets, acting presets."""
    handoff = handoff_from_view(visual)
    approval = safe_review_path(project, f"artifacts/story_visual_bible/{visual['version']}/approval.json")
    selected = [r["asset"] for r in handoff["characters"] + handoff["props"] if r["asset"]]
    selected += [r[k] for r in handoff["locations"] for k in ("environment", "lighting") if r[k]]
    unique = {(a["kind"], a["id"], a["revision"]): a for a in selected}
    return {"reviewed_story": canonical_ref(project, reviewed),
            "visual_bible": {"version": visual["version"], "package_sha256": visual["package_sha256"],
                             "manifest_sha256": visual["manifest_sha256"], "approval_sha256": _sha(approval.read_bytes()),
                             "handoff_sha256": fingerprint(handoff)},
            "library": handoff["library"], "assets": [unique[k] for k in sorted(unique)],
            "acting_presets": [acting_pin(a) for a in ACTING]}, handoff


def _current(store, project_id):
    """Current eligible inputs, or the reason they are not eligible."""
    project = _project_dir(store, project_id)  # Invalid IDs raise the existing IntakeError codes.
    reviewed = read_reviewed_story(store, project_id)
    if not reviewed.get("ready_for_next_stage"):
        return project, None, "canonical_not_ready"
    visual = read_visual_bible(store, project_id)
    if not visual.get("ready_for_next_stage"):
        return project, None, "visual_not_ready"
    inputs, handoff = _inputs(project, reviewed, visual)
    return project, {"inputs": inputs, "handoff": handoff, "reviewed": reviewed}, None


def _versions(project):
    folder = safe_review_path(project, OUTPUT_DIR)
    if not folder.exists():
        return []
    if not folder.is_dir():
        raise ScenePlanError("plan_invalid", "Scene-plan storage must be a plain version folder.")
    names = [p.name for p in folder.iterdir() if not p.name.startswith(".tmp-")]
    if any(not VERSION.fullmatch(name) for name in names):
        raise ScenePlanError("plan_invalid", "Unexpected scene-plan version entry; nothing was overwritten.")
    names.sort(key=lambda v: int(v[1:]))
    if names != [f"v{i}" for i in range(1, len(names) + 1)]:
        raise ScenePlanError("plan_invalid", "Scene-plan versions are missing or renumbered.")
    return names


def _read(store, project_id, project, current, version, previous, latest):
    try:
        base = f"{OUTPUT_DIR}/{version}"
        raw = safe_review_path(project, f"{base}/manifest.json").read_bytes()
        manifest = json.loads(raw)
        if (set(manifest) != MANIFEST_KEYS or manifest["schema_version"] != "1.0"
                or manifest["artifact"] != "story_scene_plan_manifest" or manifest["version"] != version
                or manifest["project_id"] != project_id or manifest["previous_manifest_sha256"] != previous):
            raise ValueError("Manifest/version chain mismatch")
        # Re-verify both pinned inputs and their own histories, then recompile byte-for-byte.
        reviewed = read_reviewed_story(store, project_id, manifest["inputs"]["reviewed_story"]["version"])
        visual = read_visual_bible(store, project_id, manifest["inputs"]["visual_bible"]["version"])
        if not visual["approval"] or visual["manifest"]["canonical_input"] != canonical_ref(project, reviewed):
            raise ValueError("Pinned Visual Bible is unapproved or bound to other canon")
        inputs, handoff = _inputs(project, reviewed, visual)
        if inputs != manifest["inputs"]:
            raise ValueError("Pinned inputs, library or asset revisions changed")
        package = compile_plan(project_id, version, reviewed["package"], handoff, inputs, manifest["choices"])
        package_raw = safe_review_path(project, f"{base}/scene_plan.json").read_bytes()
        if package_raw != _bytes(package) or _sha(package_raw) != manifest["package_sha256"]:
            raise ValueError("Scene plan differs from pinned inputs/choices")
        approval_path = safe_review_path(project, f"{base}/approval.json")
        approval = json.loads(approval_path.read_bytes()) if approval_path.exists() else None
        hashes = {"package_sha256": _sha(package_raw), "manifest_sha256": _sha(raw)}
        if approval is not None:
            expected = {"artifact": "story_scene_plan_approval", "project_id": project_id, "version": version, **hashes,
                        "approval_scope": "scene_plan_only", "approved": True, "reviewer": "local Studio user",
                        "tts_started": False, "rendering_started": False, "production_started": False,
                        "publishing_enabled": False}
            if (set(approval) != set(expected) | {"recorded_at", "integrity_sha256"} or package["blockers"]
                    or any(approval.get(k) != v for k, v in expected.items())
                    or not isinstance(approval["recorded_at"], str)
                    or approval["integrity_sha256"] != _record_hash(approval)):
                raise ValueError("Approval mismatch")
        is_current = version == latest and current is not None and current["inputs"] == manifest["inputs"]
        return {"state": "approved_scene_plan" if approval else "candidate", "version": version, "package": package,
                "manifest": manifest, "approval": approval, **hashes, "is_current": bool(is_current),
                "ready_for_next_stage": bool(approval) and bool(is_current), "tts_started": False,
                "rendering_started": False, "production_started": False, "publishing_enabled": False}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ScenePlanError("plan_invalid", "Scene-plan inputs, version chain, content or approval failed "
                             "verification; nothing was overwritten.") from exc


def read_scene_plan(store, project_id, version=None):
    if version is not None and (not isinstance(version, str) or not VERSION.fullmatch(version)):
        raise ScenePlanError("invalid_version", "Use a scene-plan version such as v1.")
    project, current, reason = _current(store, project_id)
    versions = _versions(project)
    status = {"canonical_ready": reason != "canonical_not_ready", "visual_ready": reason is None,
              "not_ready_reason": NOT_READY.get(reason), "vocabulary": vocabulary()}
    if not versions:
        if version:
            raise ScenePlanError("plan_missing", "Prepare Scene Plans first.")
        return {"state": "missing", "versions": [], "ready_for_next_stage": False, "tts_started": False,
                "rendering_started": False, "production_started": False, "publishing_enabled": False, **status}
    results, previous = {}, None
    for v in versions:
        results[v] = _read(store, project_id, project, current, v, previous, versions[-1])
        previous = results[v]["manifest_sha256"]
    if version and version not in results:
        raise ScenePlanError("plan_missing", "Scene-plan version does not exist.")
    return {**results[version or versions[-1]], "versions": versions, **status}


def _displayed(result, package_sha256, manifest_sha256):
    if not result.get("is_current") or (result["package_sha256"], result["manifest_sha256"]) != (
            package_sha256, manifest_sha256):
        raise ScenePlanError("stale_plan", "The displayed scene-plan version, hashes, story or Visual Bible changed. "
                             "Reload first.")


def prepare_scene_plan(store, project_id, payload, now=None):
    project = _project_dir(store, project_id)
    with review_lock(project):
        project, current, reason = _current(store, project_id)
        if current is None:
            raise ScenePlanError(reason, NOT_READY[reason])
        try:  # The P3.3 consumer contract: use the verified handoff function at handoff time.
            verified = scene_planning_handoff(store, project_id)
        except VisualBibleError as exc:
            raise ScenePlanError("visual_not_ready", NOT_READY["visual_not_ready"]) from exc
        if verified != current["handoff"]:
            raise ScenePlanError("visual_not_ready", "Visual handoff changed during preparation; reload.")
        latest = read_scene_plan(store, project_id)
        reviewed = current["reviewed"]["package"]
        if payload == {}:
            if latest["state"] != "missing" and latest["is_current"]:
                return {"status": "already_prepared", **latest}
            # New inputs: carry still-valid staging forward; every review acknowledgement is cleared.
            choices = rebase_choices(reviewed, verified, latest["manifest"]["choices"] if latest["state"] != "missing" else None)
        else:
            if not isinstance(payload, dict) or set(payload) != {"base_version", "package_sha256", "manifest_sha256", "choices"}:
                raise ScenePlanError("invalid_choice", "Send staging choices with the exact displayed base version and hashes.")
            if latest["state"] == "missing" or payload["base_version"] != latest["version"]:
                raise ScenePlanError("stale_plan", "Reload the latest scene-plan version before saving changes.")
            _displayed(latest, payload["package_sha256"], payload["manifest_sha256"])
            choices = payload["choices"]
            if choices == latest["manifest"]["choices"]:
                return {"status": "already_prepared", **latest}
        version = f"v{len(latest['versions']) + 1}"
        package = compile_plan(project_id, version, reviewed, verified, current["inputs"], choices)
        raw = _bytes(package)
        manifest = {"schema_version": "1.0", "artifact": "story_scene_plan_manifest", "project_id": project_id,
                    "version": version, "created_at": (now or datetime.now(timezone.utc)).isoformat(),
                    "inputs": current["inputs"], "choices": choices, "package_sha256": _sha(raw),
                    "previous_manifest_sha256": latest.get("manifest_sha256")}
        folder = safe_review_path(project, OUTPUT_DIR)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = safe_review_path(project, f"{OUTPUT_DIR}/.tmp-{uuid.uuid4().hex}")
        tmp.mkdir()
        try:
            for name, data in {"scene_plan.json": raw, "manifest.json": _bytes(manifest)}.items():
                with (tmp / name).open("xb") as f:
                    f.write(data)
            target = safe_review_path(project, f"{OUTPUT_DIR}/{version}")
            if target.exists():
                raise ScenePlanError("stale_plan", "Scene-plan version already exists; reload without overwriting.")
            os.rename(tmp, target)
        finally:
            if tmp.exists():
                assert tmp.resolve().is_relative_to(folder.resolve())
                shutil.rmtree(tmp)
        return {"status": "created", **read_scene_plan(store, project_id, version)}


def approve_scene_plan(store, project_id, version, package_sha256, manifest_sha256, now=None):
    project = _project_dir(store, project_id)
    with review_lock(project):
        result = read_scene_plan(store, project_id, version)
        _displayed(result, package_sha256, manifest_sha256)
        if result["package"]["blockers"]:
            raise ScenePlanError("approval_blocked", "Resolve the listed scene-plan blockers before approving.",
                                 result["package"]["blockers"])
        if result["approval"]:
            return {"status": "already_approved", **result}
        record = {"artifact": "story_scene_plan_approval", "project_id": project_id, "version": version,
                  "package_sha256": package_sha256, "manifest_sha256": manifest_sha256,
                  "approval_scope": "scene_plan_only", "approved": True, "reviewer": "local Studio user",
                  "recorded_at": (now or datetime.now(timezone.utc)).isoformat(), "tts_started": False,
                  "rendering_started": False, "production_started": False, "publishing_enabled": False}
        record["integrity_sha256"] = _record_hash(record)
        write_once(safe_review_path(project, f"{OUTPUT_DIR}/{version}/approval.json"), _bytes(record))
        return {"status": "approved", **read_scene_plan(store, project_id, version)}


def scene_plan_report(store, project_id, version=None):
    view = read_scene_plan(store, project_id, version)
    if view["state"] == "missing":
        raise ScenePlanError("plan_missing", "Prepare Scene Plans first.")
    return {"version": view["version"], "package_sha256": view["package_sha256"],
            "markdown": coverage_report(view["package"])}


def scene_plan_handoff(store, project_id):
    """P3.4 lossless interface; current approval/inputs are verified before every handoff."""
    view = read_scene_plan(store, project_id)
    if not view["ready_for_next_stage"]:
        raise ScenePlanError("approval_blocked", "A current approved scene plan is required.")
    plan = view["package"]
    timelines = {fmt: action_timeline(plan, fmt, approved=view) for fmt in plan["formats"]}
    coverage = handoff_coverage(plan, read_reviewed_story(store, project_id)["package"], timelines, approved=view)
    return {"artifact": "scene_plan_handoff", "schema_version": "1.0", "version": view["version"],
            "package_sha256": view["package_sha256"], "manifest_sha256": view["manifest_sha256"],
            "inputs": plan["inputs"], "retiming_contract": plan["retiming_contract"],
            "handoff_contract_version": "1.1", "coverage": coverage,
            "formats": {fmt: {"aspect_ratio": fp["aspect_ratio"], "viewport": fp["viewport"], "fps": fp["fps"],
                              "measurement_contract": measurement_contract(plan, fmt, approved=view),
                              "provisional_action_timeline": timelines[fmt]}
                        for fmt, fp in plan["formats"].items()},
            "approval_scope": "scene_plan_only", "tts_started": False, "rendering_started": False,
            "production_started": False, "publishing_enabled": False}


def retime_scene_plan(store, project_id, fmt, measurements):
    """Store a separately bound derivative; no TTS, audio probing, compiler or renderer is run."""
    project = _project_dir(store, project_id)
    with review_lock(project):
        view = read_scene_plan(store, project_id)
        if not view.get("ready_for_next_stage"):
            raise ScenePlanError("stale_measurement", "A current approved plan, canon and Visual Bible are required.")
        plan = view["package"]
        derivative = retime(plan, fmt, measurements, approved=view)
        timelines = {f: action_timeline(plan, f, derivative if f == fmt else None, approved=view)
                     for f in plan["formats"]}
        coverage = handoff_coverage(plan, read_reviewed_story(store, project_id)["package"], timelines, approved=view)
        result = {"artifact": "scene_plan_retiming_handoff", "schema_version": "1.0", "retimed_plan": derivative,
                  "action_timeline": timelines[fmt], "coverage": coverage, "renderable": False,
                  "audio_verified": False, "production_started": False, "publishing_enabled": False}
        # A review writer obeying the same project lock cannot change canon/Visual Bible during publication.
        current = read_scene_plan(store, project_id)
        _displayed(current, view["package_sha256"], view["manifest_sha256"])
        folder = safe_review_path(project, f"artifacts/scene_plan_retiming/{view['version']}/{fmt}")
        folder.mkdir(parents=True, exist_ok=True)
        path = safe_review_path(project, f"artifacts/scene_plan_retiming/{view['version']}/{fmt}/{measurements['manifest_sha256']}.json")
        raw = _bytes(result)
        if path.exists():
            if path.read_bytes() != raw:
                raise ScenePlanError("handoff_invalid", "Existing retimed evidence differs; nothing was overwritten.")
        else:
            write_once(path, raw)
        return result
