"""Immutable reviewed versions and an explicit, hash-bound preproduction approval.

No pipeline/checkpoint/provider dependencies. v1 inputs are read only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone

from lib.reviewed_fiction import materialize_content
from studio.fiction import PACKAGE_DIR, PACKAGE_FILES, FictionPackageError
from studio.intake import FILES as INTAKE_FILES, OUTPUT_DIR as INTAKE_DIR
from studio.review import (_context, _input_hashes, _record_hash, current_decisions, load_log,
                           review_lock, safe_review_path, targets, write_once)

OUTPUT_DIR = "artifacts/reviewed_fiction"
PACKAGE_FILE = "reviewed_package.json"
MANIFEST_FILE = "manifest.json"
TEXT_FILE = "reviewed_working_text.md"
APPROVAL_FILE = "approval.json"
VERSION = re.compile(r"v([2-9]|[1-9][0-9]+)\Z")


class ReviewedPackageError(ValueError):
    def __init__(self, code, message, blockers=None):
        super().__init__(message)
        self.code = code
        self.blockers = blockers or []


def _bytes(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _snapshot(ctx, log):
    project = ctx["loaded"]["project"]
    files = [f"{INTAKE_DIR}/{name}" for name in INTAKE_FILES.values()]
    files += [f"{PACKAGE_DIR}/{name}" for name in PACKAGE_FILES.values()]
    return {"source": ctx["loaded"]["request"]["content_sha256"],
            "production_request": ctx["loaded"]["request_sha256"],
            "artifacts": {name: _sha(safe_review_path(project, name).read_bytes()) for name in files},
            "decisions": [{"decision_id": d["decision_id"], "sha256": d["_sha256"]} for d in log]}


def _context_log(store, project_id):
    ctx = _context(store, project_id)
    if ctx["fiction"] is None:
        raise FictionPackageError("package_missing", "Import a Fiction Story Package draft first.")
    return ctx, load_log(ctx["loaded"]["project"])


def _dispositions(ctx, log):
    current = current_decisions(log)
    questions = {q["id"]: q["question"] for q in ctx["inventory"]["human_interpretation"]
                 + ctx["fiction"]["package"]["ambiguities"]}
    result = []
    for target_id, target in targets(ctx).items():
        d = current.get(target_id)
        choice = d["decision"] if d else "undecided"
        if d and (d["input_hashes"] != _input_hashes(ctx, target) or d["target_kind"] != target["kind"]):
            choice = "stale"
        result.append({"target_id": target_id, "kind": target["kind"], "decision": choice,
                       "decision_id": d["decision_id"] if d else None,
                       "answer": d["answer"] if d and choice == "answer" else None,
                       "question": questions.get(target_id)})
    return result


def _compile(ctx, log, version):
    return materialize_content(ctx["fiction"]["package"], ctx["loaded"]["source"].decode("utf-8"),
                               ctx["changes"], _dispositions(ctx, log), version)


def _versions(project):
    folder = safe_review_path(project, OUTPUT_DIR)
    if not folder.exists():
        return []
    names = [p.name for p in folder.iterdir() if not p.name.startswith(".tmp-")]
    if any(not VERSION.fullmatch(name) for name in names):
        raise ReviewedPackageError("reviewed_invalid", "Unexpected reviewed version entry; nothing was overwritten.")
    names.sort(key=lambda s: int(s[1:]))
    if names != [f"v{i}" for i in range(2, len(names) + 2)]:
        raise ReviewedPackageError("reviewed_invalid", "Reviewed versions are missing or renumbered.")
    return names


def _read(ctx, log, version):
    if not VERSION.fullmatch(version):
        raise ReviewedPackageError("invalid_version", "Use a reviewed version such as v2.")
    project = ctx["loaded"]["project"]
    folder = safe_review_path(project, f"{OUTPUT_DIR}/{version}")
    if not folder.exists():
        raise ReviewedPackageError("reviewed_missing", "Materialize Reviewed Story first.")
    try:
        manifest_raw = safe_review_path(project, f"{OUTPUT_DIR}/{version}/{MANIFEST_FILE}").read_bytes()
        manifest = json.loads(manifest_raw)
        snapshot = manifest["inputs"]
        count = len(snapshot["decisions"])
        if count > len(log) or snapshot != _snapshot(ctx, log[:count]):
            raise ValueError("Inputs or pinned decisions changed")
        package = _compile(ctx, log[:count], version)
        raw = _bytes(package)
        outputs = {PACKAGE_FILE: _sha(raw), TEXT_FILE: _sha(package["working_text"].encode("utf-8"))}
        if (manifest["artifact"] != "reviewed_fiction_manifest" or manifest["version"] != version
                or manifest["outputs"] != outputs or manifest["applied_decisions"] != package["dispositions"]
                or manifest["approval_scope"] != "preproduction_story_only"
                or manifest["production_started"] is not False or manifest["publishing_enabled"] is not False):
            raise ValueError("Manifest mismatch")
        for name, expected in outputs.items():
            if _sha(safe_review_path(project, f"{OUTPUT_DIR}/{version}/{name}").read_bytes()) != expected:
                raise ValueError("Output changed")
        approval_path = safe_review_path(project, f"{OUTPUT_DIR}/{version}/{APPROVAL_FILE}")
        approval = json.loads(approval_path.read_bytes()) if approval_path.exists() else None
        if approval is not None:
            expected = {"artifact": "reviewed_story_approval", "version": version, "package_sha256": _sha(raw),
                        "manifest_sha256": _sha(manifest_raw), "approval_scope": "preproduction_story_only",
                        "reviewer": "local Studio user", "approved": True, "production_started": False,
                        "publishing_enabled": False}
            if (package["blockers"] or any(approval.get(k) != v for k, v in expected.items())
                    or not isinstance(approval.get("recorded_at"), str)
                    or approval.get("integrity_sha256") != _record_hash(approval)):
                raise ValueError("Approval mismatch")
        current = snapshot == _snapshot(ctx, log)
        return {"state": "approved_for_preproduction" if approval else "materialized",
                "version": version, "package_sha256": _sha(raw), "manifest_sha256": _sha(manifest_raw),
                "package": package, "manifest": manifest, "approval": approval, "is_current": current,
                "ready_for_next_stage": bool(approval) and current,
                "production_started": False, "publishing_enabled": False,
                "saved_files": [f"{OUTPUT_DIR}/{version}/{name}" for name in
                                [PACKAGE_FILE, MANIFEST_FILE, TEXT_FILE] + ([APPROVAL_FILE] if approval else [])]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ReviewedPackageError("reviewed_invalid", "Reviewed inputs, decisions, manifest, content or approval "
                                   "failed verification; nothing was overwritten.") from exc


def read_reviewed_story(store, project_id, version=None):
    ctx, log = _context_log(store, project_id)
    versions = _versions(ctx["loaded"]["project"])
    if not versions:
        if version:
            raise ReviewedPackageError("reviewed_missing", "Materialize Reviewed Story first.")
        return {"state": "missing", "versions": [], "production_started": False, "publishing_enabled": False,
                "ready_for_next_stage": False}
    # Verify frozen history too: deleted/reordered/tampered versions must never be skipped.
    results = {v: _read(ctx, log, v) for v in versions}
    if version is not None and version not in results:
        raise ReviewedPackageError("reviewed_missing", "Reviewed version does not exist.")
    return {**results[version or versions[-1]], "versions": versions}


def materialize_reviewed_story(store, project_id, now=None):
    ctx, log = _context_log(store, project_id)
    project = ctx["loaded"]["project"]
    with review_lock(project):
        ctx, log = _context_log(store, project_id)
        latest = read_reviewed_story(store, project_id)
        if latest["state"] != "missing" and latest["is_current"]:
            return {"status": "already_materialized", **latest}
        version = f"v{len(latest['versions']) + 2}"
        package = _compile(ctx, log, version)
        raw, text = _bytes(package), package["working_text"].encode("utf-8")
        manifest = {"schema_version": "1.0", "artifact": "reviewed_fiction_manifest", "version": version,
                    "created_at": (now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z"),
                    "inputs": _snapshot(ctx, log), "applied_decisions": package["dispositions"],
                    "outputs": {PACKAGE_FILE: _sha(raw), TEXT_FILE: _sha(text)},
                    "approval_scope": "preproduction_story_only", "production_started": False,
                    "publishing_enabled": False}
        folder = safe_review_path(project, OUTPUT_DIR)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / f".tmp-{uuid.uuid4().hex}"
        tmp.mkdir()
        try:
            for name, data in {PACKAGE_FILE: raw, TEXT_FILE: text, MANIFEST_FILE: _bytes(manifest)}.items():
                with (tmp / name).open("xb") as f:
                    f.write(data)
            os.rename(tmp, folder / version)
        finally:
            if tmp.exists():
                shutil.rmtree(tmp)
        return {"status": "created", **read_reviewed_story(store, project_id, version)}


def approve_reviewed_story(store, project_id, version, package_sha256, manifest_sha256, now=None):
    ctx, log = _context_log(store, project_id)
    project = ctx["loaded"]["project"]
    with review_lock(project):
        result = read_reviewed_story(store, project_id, version)
        if not result["is_current"] or (package_sha256, manifest_sha256) != (
                result["package_sha256"], result["manifest_sha256"]):
            raise ReviewedPackageError("stale_reviewed", "The version, hash or decisions changed. Reload and "
                                       "materialize a new version before approving.")
        if result["package"]["blockers"]:
            raise ReviewedPackageError("approval_blocked", "Resolve the listed blockers before approval.",
                                       result["package"]["blockers"])
        if result["approval"]:
            return {"status": "already_approved", **result}
        record = {"artifact": "reviewed_story_approval", "version": version,
                  "package_sha256": package_sha256, "manifest_sha256": manifest_sha256,
                  "approval_scope": "preproduction_story_only", "approved": True,
                  "reviewer": "local Studio user",
                  "recorded_at": (now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z"),
                  "production_started": False, "publishing_enabled": False}
        record["integrity_sha256"] = _record_hash(record)
        path = safe_review_path(project, f"{OUTPUT_DIR}/{version}/{APPROVAL_FILE}")
        write_once(path, _bytes(record))
        return {"status": "approved", **read_reviewed_story(store, project_id, version)}
