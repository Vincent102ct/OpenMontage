"""Save input-only requests in normal project workspaces. Never run tools."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from studio.catalog import ApprovedPackages
from studio.models import NewProduction, ProductionRequest, content_hash, safe_project_id

REQUEST_FILE = "artifacts/production_request.json"
# CommonMark ATX heading: up to 3 spaces, 1-6 '#', then whitespace or end; optional closing '#' run.
ATX_HEADING = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
LAYOUT = ("input", "artifacts", "assets/images", "assets/video", "assets/audio", "assets/music", "renders")


class ProjectExistsError(ValueError):
    pass


def derive_title(content: str) -> str:
    """Display title from the first nonblank line; drops only a Markdown heading marker."""
    line = next(raw for raw in content.splitlines() if raw.strip())  # Keep indentation for the heading check.
    match = ATX_HEADING.match(line)
    heading = (match.group(1) or "").strip() if match else ""
    return (heading or line.strip())[:120]


class ProductionStore:
    def __init__(self, projects_root: Path, catalog: ApprovedPackages):
        self.root = projects_root.resolve()
        self.catalog = catalog

    def _project(self, project_id: str) -> Path:
        safe_project_id(project_id)
        path = self.root / project_id
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ValueError("Project path escapes the workspace.")
        return path

    def create(self, data: NewProduction) -> dict:
        now = datetime.now(timezone.utc)
        project_id = data.project_id or f"studio-{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
        project = self._project(project_id)
        canonical = None
        title = data.title
        if data.input_mode == "canonical":
            package_title, canonical = self.catalog.select(data.canonical_package_id)
            title = title or package_title
            sha = canonical.sha256
            input_file, readiness = "input/canonical-reference.json", "canonical_reference"
        else:
            title = title or derive_title(data.content)
            sha = content_hash(data.content)
            input_file, readiness = (("input/topic.txt", "unresearched_topic") if data.input_mode == "topic"
                                     else ("input/story.md", "unreviewed_story"))
        request = ProductionRequest(project_id=project_id, title=title, input_mode=data.input_mode,
                                    content=data.content, content_sha256=sha, input_file=input_file,
                                    source_filename=data.source_filename, formats=data.formats,
                                    input_readiness=readiness, created_at=now, canonical_package=canonical)
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            project.mkdir()  # Atomic reservation: includes existing empty/legacy project directories.
        except FileExistsError as exc:
            raise ProjectExistsError("Project ID already exists. Choose another ID; nothing was overwritten.") from exc
        # No init_project/checkpoint import: init_project merges existing files, while Studio must refuse overwrite.
        for sub in LAYOUT:
            (project / sub).mkdir(parents=True, exist_ok=True)
        with (project / input_file).open("x", encoding="utf-8", newline="") as f:
            if canonical:
                f.write(json.dumps(canonical.model_dump(mode="json"), ensure_ascii=False, indent=2))
            else:
                f.write(data.content)
        with (project / REQUEST_FILE).open("x", encoding="utf-8", newline="\n") as f:
            f.write(request.model_dump_json(indent=2))
        # Marker is written last; no pipeline checkpoints, events or research artifacts are created.
        marker = {"version": "1.0", "project_id": project_id, "title": title,
                  "pipeline_type": "character-animation", "created_at": now.isoformat(),
                  "status": "production_not_started", "production_started": False,
                  "studio_request": REQUEST_FILE, "human_review_required": True, "publishing_enabled": False}
        with (project / "project.json").open("x", encoding="utf-8", newline="\n") as f:
            json.dump(marker, f, ensure_ascii=False, indent=2)
        return self.detail(project_id)

    def detail(self, project_id: str) -> dict:
        project = self._project(project_id)
        request_file = project / REQUEST_FILE
        if not request_file.resolve().is_relative_to(project) or request_file.is_symlink():
            raise ValueError("Saved request path escapes the project.")
        request = ProductionRequest.model_validate_json(request_file.read_bytes())
        if request.project_id != project_id:
            raise ValueError("Saved project ID does not match its directory.")
        source = project / request.input_file
        if source.is_symlink() or not source.resolve().is_relative_to(project):
            raise ValueError("Saved input path escapes the project.")
        raw = source.read_bytes()
        if request.input_mode == "canonical":
            if json.loads(raw) != request.canonical_package.model_dump(mode="json"):
                raise ValueError("Saved canonical reference changed.")
        elif raw != request.content.encode("utf-8"):
            raise ValueError("Saved input file differs from the original input.")
        return {"request": request.model_dump(mode="json"),
                "saved_files": ["project.json", REQUEST_FILE, request.input_file],
                "backlot_url": f"/p/{quote(project_id, safe='')}", "production_started": False}

    def list_productions(self) -> list[dict]:
        if not self.root.is_dir():
            return []
        rows = []
        for project in self.root.iterdir():
            if (not project.is_dir() or project.is_symlink()
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", project.name)
                    or not (project / "project.json").is_file()):
                continue
            try:
                marker = json.loads((project / "project.json").read_text(encoding="utf-8"))
                row = {"project_id": project.name, "title": marker.get("title") or project.name,
                       "created_at": marker.get("created_at"), "kind": "existing_workspace",
                       "status": "existing_workspace", "input_mode": None, "formats": [],
                       "review_status": "see_backlot", "backlot_url": f"/p/{quote(project.name, safe='')}"}
                if (project / REQUEST_FILE).is_file():
                    req = self.detail(project.name)["request"]
                    row.update({k: req[k] for k in ("title", "created_at", "input_mode", "formats", "review_status", "status")})
                    row["kind"] = "studio"
                rows.append(row)
            except (ValueError, OSError, TypeError, AttributeError):
                continue  # Malformed existing workspaces are not rewritten or reinitialized.
        return sorted(rows, key=lambda r: str(r["created_at"] or ""), reverse=True)
