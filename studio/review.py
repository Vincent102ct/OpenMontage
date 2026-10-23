"""Human editorial review: an append-only, hash-chained decision log over intake and fiction package targets.

Each decision is a new file (never edited) recording the input hashes it was made
against. Changing a decision requires naming the decision it supersedes, so a
stale page cannot silently replace a newer one. Questions are only answered by an
explicit answer; open or deferred questions stay unresolved. No decision starts
TTS, asset generation, rendering or publishing.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from lib.fiction_story import REVIEWABLE
from studio.fiction import FictionPackageError, intake_context, read_fiction_package
from studio.intake import apply_changes
from studio.models import plain_text
from studio.store import ProductionStore

DECISION_DIR = "artifacts/story_review/v1/decisions"
CHOICES = {"edit": ("accept", "reject", "defer"), "item": ("accept", "reject", "defer"),
           "format": ("accept", "reject", "defer"), "question": ("answer", "preserve_ambiguity", "defer")}
MAX_ANSWER = 4000
MAX_NOTE = 2000


class ReviewError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_review_path(project: Path, relative: str) -> Path:
    path = project
    for part in Path(relative).parts:
        if part in ("..", "."):
            raise ReviewError("log_invalid", "Unsafe review path.")
        path = path / part
        try:
            reparse = getattr(path.lstat(), "st_file_attributes", 0) & 0x400
        except FileNotFoundError:
            reparse = 0
        if path.is_symlink() or reparse or not path.resolve().is_relative_to(project):
            raise ReviewError("log_invalid", "Review paths must be plain files and folders inside the project.")
    return path


@contextmanager
def review_lock(project: Path):
    """Serialize local decision, materialization and approval writes across processes."""
    lock = safe_review_path(project, "artifacts/story_review/.write-lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        stream = lock.open("xb")
    except FileExistsError as exc:
        raise ReviewError("stale_decision", "Another review write is in progress; retry after it finishes.") from exc
    try:
        with stream:
            yield
    finally:
        lock.unlink()


def write_once(path: Path, raw: bytes):
    """Publish a complete file atomically without replacing an existing file."""
    tmp = path.parent.parent / f".tmp-{uuid.uuid4().hex}"
    try:
        with tmp.open("xb") as f:
            f.write(raw)
        os.link(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _record_hash(record: dict) -> str:
    content = {k: v for k, v in record.items() if k != "integrity_sha256"}
    return _sha(json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _context(store: ProductionStore, project_id: str) -> dict:
    ctx = intake_context(store, project_id)
    try:
        ctx["fiction"] = read_fiction_package(store, project_id, ctx)
    except FictionPackageError as exc:
        if exc.code != "package_missing":
            raise
        ctx["fiction"] = None
    return ctx


def targets(ctx: dict) -> dict[str, dict]:
    """Every reviewable target, keyed by stable ID."""
    out: dict[str, dict] = {}
    for c in ctx["changes"]:
        out[c["id"]] = {"kind": "edit", "source": "intake"}
    for q in ctx["inventory"]["human_interpretation"]:
        out[q["id"]] = {"kind": "question", "source": "intake"}
    fiction = ctx["fiction"]
    if fiction:
        pkg = fiction["package"]
        for name in REVIEWABLE:
            for item in pkg[name]:
                out[item["id"]] = {"kind": "question" if name == "ambiguities" else "item", "source": "package",
                                   "collection": name}
        for plan in pkg["formats"].values():
            out[plan["id"]] = {"kind": "format", "source": "package"}
    return out


def _input_hashes(ctx: dict, target: dict) -> dict:
    hashes = {"source": ctx["loaded"]["request"]["content_sha256"],
              "production_request": ctx["loaded"]["request_sha256"],
              "intake_report": ctx["intake_report_sha256"]}
    if target["source"] == "package":
        hashes["fiction_package"] = ctx["fiction"]["package_sha256"]
    return hashes


def load_log(project: Path) -> list[dict]:
    """Verify the chain: contiguous sequence, previous-hash links and well-formed records."""
    folder = safe_review_path(project, DECISION_DIR)
    if not folder.exists():
        return []
    if folder.is_symlink() or not folder.is_dir():
        raise ReviewError("log_invalid", "Review log path is not a plain folder.")
    names = sorted(p.name for p in folder.iterdir())
    decisions, previous = [], None
    for i, name in enumerate(names, 1):
        if name != f"{i:06d}.json":
            raise ReviewError("log_invalid", f"Review log is not contiguous at {name}; no decision was recorded.")
        try:
            raw = safe_review_path(project, f"{DECISION_DIR}/{name}").read_bytes()
            d = json.loads(raw)
            ok = (d["sequence"] == i and d["decision_id"] == f"DEC_{i:06d}" and d["previous_sha256"] == previous
                  and d["artifact"] == "story_review_decision" and isinstance(d["target_id"], str)
                  and d["decision"] in CHOICES[d["target_kind"]] and isinstance(d["input_hashes"], dict)
                  and d["production_effect"] == "none" and d["reviewer"] == "local Studio user"
                  and isinstance(d["recorded_at"], str)
                  and (d["decision"] != "answer" or isinstance(d["answer"], str) and bool(d["answer"].strip()))
                  and (d["decision"] == "answer" or d["answer"] is None)
                  and ("integrity_sha256" not in d or d["integrity_sha256"] == _record_hash(d)))
        except (OSError, ValueError, KeyError, TypeError):
            ok = False
        if not ok:
            raise ReviewError("log_invalid", f"Review log entry {name} failed verification; it was not changed.")
        d["_sha256"] = _sha(raw)
        decisions.append(d)
        previous = d["_sha256"]
    current: dict[str, str] = {}
    for d in decisions:  # Supersede links must follow the order decisions were actually made.
        if d["supersedes"] != current.get(d["target_id"]):
            raise ReviewError("log_invalid", f"{d['decision_id']} supersedes the wrong decision.")
        current[d["target_id"]] = d["decision_id"]
    return decisions


def current_decisions(decisions: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for d in decisions:
        latest[d["target_id"]] = d
    return latest


def record_decision(store: ProductionStore, project_id: str, payload: dict, now: datetime | None = None) -> dict:
    ctx = _context(store, project_id)
    with review_lock(ctx["loaded"]["project"]):
        return _record_decision(store, project_id, payload, now)


def _record_decision(store: ProductionStore, project_id: str, payload: dict, now: datetime | None = None) -> dict:
    ctx = _context(store, project_id)
    all_targets = targets(ctx)
    target_id = payload.get("target_id")
    target = all_targets.get(target_id) if isinstance(target_id, str) else None
    if not target:
        raise ReviewError("unknown_target", "That review item does not exist for this production.")
    decision = payload.get("decision")
    if decision not in CHOICES[target["kind"]]:
        raise ReviewError("invalid_decision", f"Allowed decisions here: {', '.join(CHOICES[target['kind']])}.")
    answer = payload.get("answer")
    note = payload.get("note") or None
    if decision == "answer":
        if not isinstance(answer, str) or not answer.strip() or len(answer) > MAX_ANSWER:
            raise ReviewError("invalid_decision", "An answer needs text (up to 4000 characters); an empty answer "
                              "leaves the question unresolved.")
    elif answer:
        raise ReviewError("invalid_decision", "Only an answer decision carries answer text.")
    for text in (answer, note):
        if text is not None:
            if not isinstance(text, str) or len(text) > max(MAX_ANSWER, MAX_NOTE):
                raise ReviewError("invalid_decision", "Text is too long.")
            try:
                plain_text(text)
            except ValueError as exc:
                raise ReviewError("invalid_decision", str(exc)) from exc
    project = ctx["loaded"]["project"]
    for attempt in range(2):
        decisions = load_log(project)
        current = current_decisions(decisions).get(target_id)
        expected = current["decision_id"] if current else None
        if payload.get("supersedes") != expected:
            raise ReviewError("stale_decision", "This item already has a newer decision (" + (expected or "none")
                              + "). Reload the review; nothing was changed.")
        seq = len(decisions) + 1
        record = {
            "schema_version": "1.0", "artifact": "story_review_decision", "sequence": seq,
            "decision_id": f"DEC_{seq:06d}", "target_id": target_id, "target_kind": target["kind"],
            "decision": decision, "answer": answer if decision == "answer" else None, "note": note,
            "supersedes": expected, "previous_sha256": decisions[-1]["_sha256"] if decisions else None,
            "input_hashes": _input_hashes(ctx, target), "reviewer": "local Studio user",
            "recorded_at": (now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z"),
            "production_effect": "none",
        }
        record["integrity_sha256"] = _record_hash(record)
        folder = safe_review_path(project, DECISION_DIR)
        folder.mkdir(parents=True, exist_ok=True)
        try:
            write_once(folder / f"{seq:06d}.json", (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            return record
        except FileExistsError:
            if attempt:
                raise ReviewError("stale_decision", "Another decision was recorded at the same time; reload.")
    raise ReviewError("stale_decision", "Could not record the decision; reload.")


def _status(target: dict, d: dict | None, stale: bool) -> str:
    if d is None:
        return "open" if target["kind"] == "question" else "undecided"
    if stale:
        return "stale"
    return {"accept": "accepted", "reject": "rejected", "defer": "deferred", "answer": "answered",
            "preserve_ambiguity": "intentionally_unresolved"}[d["decision"]]


def review_view(store: ProductionStore, project_id: str) -> dict:
    """Everything the Studio review screen shows, with decisions folded in and gaps listed explicitly."""
    try:
        ctx = _context(store, project_id)
    except FictionPackageError as exc:
        if exc.code == "intake_missing":
            return {"state": "intake_missing", "message": str(exc), "production_started": False}
        raise
    decisions = load_log(ctx["loaded"]["project"])
    latest = current_decisions(decisions)
    all_targets = targets(ctx)

    def decorate(target_id: str) -> dict:
        d = latest.get(target_id)
        stale = bool(d) and d["input_hashes"] != _input_hashes(ctx, all_targets[target_id])
        return {"status": _status(all_targets[target_id], d, stale),
                "decision_id": d["decision_id"] if d else None,
                "answer": d["answer"] if d else None, "note": d["note"] if d else None,
                "history": [h["decision_id"] for h in decisions if h["target_id"] == target_id]}

    accepted = [c for c in ctx["changes"] if decorate(c["id"])["status"] == "accepted"]
    source = ctx["loaded"]["source"].decode("utf-8")
    fiction = ctx["fiction"]
    questions = [{**q, "origin": "intake", "review": decorate(q["id"])}
                 for q in ctx["inventory"]["human_interpretation"]]
    package = None
    if fiction:
        pkg = fiction["package"]
        questions += [{**a, "origin": "fiction_package", "review": decorate(a["id"])} for a in pkg["ambiguities"]]
        package = {"package_id": pkg["package_id"], "title": pkg["title"], "provenance": pkg["provenance"],
                   "coverage": pkg["coverage"], "validation": fiction["report"]["validation"],
                   "stickman_production": pkg["stickman_production"], "saved_files": fiction["saved_files"],
                   "collections": {name: [{**item, "review": decorate(item["id"])} for item in pkg[name]]
                                   for name in REVIEWABLE if name != "ambiguities"},
                   "formats": {k: {**v, "review": decorate(v["id"])} for k, v in pkg["formats"].items()}}
    statuses = [decorate(t)["status"] for t in all_targets]
    counts = {s: statuses.count(s) for s in ("accepted", "rejected", "deferred", "answered", "open",
                                              "undecided", "stale", "intentionally_unresolved")}
    semantic = ctx["intake"]["report"]["analysis_coverage"]["semantic"]
    missing = [f"Story Intake semantic analysis {semantic['status'].replace('_', ' ')}: {semantic['reason']}"]
    if fiction:
        missing += fiction["package"]["coverage"]["missing"]
    else:
        missing.append("No fiction Story Bible package has been built yet (import a Story Bible draft).")
    unresolved = counts["open"] + counts["deferred"] + counts["undecided"] + counts["stale"]
    if unresolved:
        missing.append(f"{unresolved} review items are still open, deferred, undecided or stale.")
    complete = fiction is not None and unresolved == 0
    return {
        "state": "ready", "project_id": project_id,
        "review_status": "decisions_recorded" if complete else "pending_human_review",
        "approval_scope": "Decisions record editorial choices only. They never start TTS, assets, rendering "
                          "or publishing.",
        "production_started": False, "counts": counts, "decision_count": len(decisions),
        "original_story": source,
        "working_text_proposal": ctx["proposal"],
        "working_text_accepted_only": apply_changes(source, accepted),
        "changes": [{**c, "review": decorate(c["id"])} for c in ctx["changes"]],
        "questions": questions, "package": package, "missing_coverage": missing,
    }
