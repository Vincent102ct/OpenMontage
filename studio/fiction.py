"""Build a reviewable Fiction Story Package from verified Story Intake output and an authored draft.

The draft (human- or agent-authored JSON) carries every interpretation, citing
quotes from the story; this module only resolves, validates and stores it. No
story plot lives in code. Outputs are written once under
artifacts/fiction_package/v1/ and stay pending human review. Nothing here starts
TTS, asset generation, rendering or publishing.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path

from lib.fiction_story import FictionStoryError, resolve_draft, validate_package
from studio.intake import FILES as INTAKE_FILES, OUTPUT_DIR as INTAKE_DIR
from studio.intake import IntakeError, load_story_request, read_story_intake
from studio.models import plain_text
from studio.store import REQUEST_FILE, ProductionStore

PACKAGE_DIR = "artifacts/fiction_package/v1"
PACKAGE_FILES = {"package": "fiction_story_package.json", "draft": "story_bible_draft.json",
                 "report": "fiction_package_report.json"}
MAX_DRAFT_BYTES = 2_000_000
PRIVATE_DRAFT_DIR = "_private_story_drafts"


class FictionPackageError(ValueError):
    def __init__(self, code: str, message: str, problems: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.problems = problems or []


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_local_draft(projects_root: Path, draft_path: str) -> dict:
    """CLI import only: bounded JSON under the configured private draft folder.

    HTTP imports receive JSON content from a browser file picker, never a path.
    Reject traversal and all symlink/junction components before opening a file.
    """
    root = projects_root.resolve()
    path = Path(draft_path)
    invalid = "Use a plain .json file under projects/_private_story_drafts; no links or traversal."
    try:
        if ".." in path.parts:
            raise ValueError(invalid)
        path = path.absolute()
        relative = path.relative_to(root)
        if (len(relative.parts) < 2 or relative.parts[0] != PRIVATE_DRAFT_DIR
                or path.suffix.lower() != ".json" or ":" in relative.as_posix()):
            raise ValueError(invalid)
        current = root
        for part in relative.parts:
            current = current / part
            info = current.lstat()
            if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400
                    or not current.resolve().is_relative_to(root / PRIVATE_DRAFT_DIR)):
                raise ValueError(invalid)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(invalid)
        with path.open("rb") as f:
            raw = f.read(MAX_DRAFT_BYTES + 1)
        if len(raw) > MAX_DRAFT_BYTES:
            raise ValueError("The Story Bible draft exceeds the 2 MB limit.")
        draft = json.loads(raw)
        canonical_draft(draft)
        return draft
    except (OSError, ValueError) as exc:
        raise FictionPackageError("invalid_draft", invalid) from exc


def _json_bytes(data) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def canonical_draft(draft) -> bytes:
    """Formatting-independent bytes, so the same draft content always has the same hash."""
    if not isinstance(draft, dict):
        raise FictionPackageError("invalid_draft", "The Story Bible draft must be a JSON object.")
    data = json.dumps(draft, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_DRAFT_BYTES:
        raise FictionPackageError("invalid_draft", "The Story Bible draft exceeds the 2 MB limit.")
    try:
        plain_text(data.decode("utf-8"))
    except ValueError as exc:
        raise FictionPackageError("invalid_draft", str(exc)) from exc
    return data


def intake_context(store: ProductionStore, project_id: str) -> dict:
    """Verified request, source and intake; raise intake_missing when intake has not run."""
    try:
        loaded = load_story_request(store, project_id)
        intake = read_story_intake(store, project_id, loaded)
    except IntakeError as exc:
        if exc.code == "not_prepared":
            raise FictionPackageError("intake_missing", "Prepare Story Draft (Story Intake) must run before a "
                                      "fiction package can be built.") from exc
        raise
    out = loaded["project"] / INTAKE_DIR

    def read(key):
        return json.loads((out / INTAKE_FILES[key]).read_bytes())

    return {"loaded": loaded, "intake": intake, "segments": read("segments")["segments"],
            "inventory": read("inventory"), "changes": read("changes")["changes"],
            "proposal": (out / INTAKE_FILES["proposal"]).read_bytes().decode("utf-8"),
            "intake_report_sha256": _sha((out / INTAKE_FILES["report"]).read_bytes())}


def _provenance(ctx: dict, draft: dict, draft_sha: str) -> dict:
    loaded = ctx["loaded"]
    return {"project_id": loaded["request"]["project_id"],
            "source": {"path": loaded["request"]["input_file"], "sha256": loaded["request"]["content_sha256"]},
            "production_request": {"path": REQUEST_FILE, "sha256": loaded["request_sha256"]},
            "intake": {"path": f"{INTAKE_DIR}/{INTAKE_FILES['report']}", "sha256": ctx["intake_report_sha256"]},
            "draft": {"sha256": draft_sha, "authored_by": str(draft.get("authored_by") or "unspecified"),
                      "basis": str(draft.get("basis") or "unspecified")}}


def build_outputs(ctx: dict, draft: dict, created_at: datetime) -> dict[str, bytes]:
    draft_bytes = canonical_draft(draft)
    draft_sha = _sha(draft_bytes)
    try:
        package = resolve_draft(draft, segments=ctx["segments"], language=ctx["intake"]["report"]["language"],
                                provenance=_provenance(ctx, draft, draft_sha),
                                intake_dialogue=ctx["inventory"]["dialogue"])
        summary = validate_package(package, source_text=ctx["loaded"]["source"].decode("utf-8"),
                                   changes=ctx["changes"])
    except FictionStoryError as exc:
        raise FictionPackageError("invalid_draft", "The Story Bible draft failed validation; nothing was written.",
                                  exc.problems) from exc
    files = {PACKAGE_FILES["package"]: _json_bytes(package), PACKAGE_FILES["draft"]: _json_bytes(draft)}
    report = {
        "schema_version": "1.0", "artifact": "fiction_package_report", "status": "prepared",
        "created_at": created_at.isoformat().replace("+00:00", "Z"), "package_id": package["package_id"],
        "provenance": package["provenance"],
        "review": {"status": "pending_human_review", "approved": False},
        "production_started": False, "publishing_enabled": False, "validation": summary,
        "coverage": package["coverage"],
        "outputs": {name: {"path": f"{PACKAGE_DIR}/{name}", "sha256": _sha(data), "bytes": len(data)}
                    for name, data in files.items()},
    }
    files[PACKAGE_FILES["report"]] = _json_bytes(report)
    return files


def read_fiction_package(store: ProductionStore, project_id: str, ctx: dict | None = None) -> dict:
    ctx = ctx or intake_context(store, project_id)
    out = ctx["loaded"]["project"] / PACKAGE_DIR
    if not out.exists():
        raise FictionPackageError("package_missing", "No fiction package has been built for this production.")
    invalid = ("Saved fiction package failed verification; it was not overwritten. Move "
               "artifacts/fiction_package/v1 aside to rebuild it.")
    try:
        report = json.loads((out / PACKAGE_FILES["report"]).read_bytes())
        if set(report["outputs"]) != {PACKAGE_FILES["package"], PACKAGE_FILES["draft"]}:
            raise ValueError("output list")
        for name, meta in report["outputs"].items():
            if _sha((out / name).read_bytes()) != meta["sha256"]:
                raise ValueError(f"{name} changed")
        package = json.loads((out / PACKAGE_FILES["package"]).read_bytes())
        prov = package["provenance"]
        draft = json.loads((out / PACKAGE_FILES["draft"]).read_bytes())
        if prov != _provenance(ctx, draft, _sha(canonical_draft(draft))):
            raise ValueError("draft or source provenance changed")
        if (report["provenance"] != prov or report["review"] != {
                "status": "pending_human_review", "approved": False}
                or report["production_started"] is not False or report["publishing_enabled"] is not False):
            raise ValueError("report no longer describes an unapproved draft")
        if (prov["source"]["sha256"], prov["production_request"]["sha256"], prov["intake"]["sha256"]) != (
                ctx["loaded"]["request"]["content_sha256"], ctx["loaded"]["request_sha256"],
                ctx["intake_report_sha256"]):
            raise ValueError("inputs changed after the package was built")
        validate_package(package, source_text=ctx["loaded"]["source"].decode("utf-8"), changes=ctx["changes"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise FictionPackageError("existing_output_invalid", invalid) from exc
    return {"package": package, "report": report,
            "package_sha256": report["outputs"][PACKAGE_FILES["package"]]["sha256"],
            "saved_files": [f"{PACKAGE_DIR}/{name}" for name in PACKAGE_FILES.values()]}


def build_fiction_package(store: ProductionStore, project_id: str, draft: dict, now: datetime | None = None) -> dict:
    """Build once; the same draft again returns the existing package, a different draft is refused."""
    ctx = intake_context(store, project_id)
    out = ctx["loaded"]["project"] / PACKAGE_DIR
    draft_sha = _sha(canonical_draft(draft))
    if out.exists():
        existing = read_fiction_package(store, project_id, ctx)
        if existing["package"]["provenance"]["draft"]["sha256"] != draft_sha:
            raise FictionPackageError("package_exists", "A different fiction package already exists for this "
                                      "production; it was not overwritten.")
        return {"status": "already_prepared", **existing}
    files = build_outputs(ctx, draft, now or datetime.now(timezone.utc))
    for parent in (out.parent.parent, out.parent):
        if parent.is_symlink():
            raise FictionPackageError("invalid_request", "Package output path is a symlink; nothing was written.")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.parent / f".tmp-{uuid.uuid4().hex}"
    tmp.mkdir()
    try:
        for name, data in files.items():
            with (tmp / name).open("xb") as f:
                f.write(data)
        try:
            os.rename(tmp, out)  # Atomic publish; a concurrent build that won is verified below.
        except OSError:
            if not out.exists():
                raise
            return build_fiction_package(store, project_id, draft)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    return {"status": "created", **read_fiction_package(store, project_id, ctx)}
