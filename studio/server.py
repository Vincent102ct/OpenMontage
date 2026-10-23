"""Studio input routes alongside the unchanged read-only Backlot application."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backlot.server import create_app as create_backlot_app
from lib.paths import PROJECTS_DIR, REPO_ROOT
from studio.catalog import ApprovedPackages
from studio.fiction import FictionPackageError, build_fiction_package, read_fiction_package
from studio.review import ReviewError, record_decision, review_view
from studio.reviewed import (ReviewedPackageError, approve_reviewed_story, materialize_reviewed_story,
                             read_reviewed_story)
from studio.intake import FILES as INTAKE_FILES, OUTPUT_DIR as INTAKE_DIR
from studio.intake import IntakeError, prepare_story_intake, read_story_intake
from studio.models import NewProduction
from studio.store import ProductionStore, ProjectExistsError

UI_DIR = Path(__file__).parent / "ui"
MAX_BODY_BYTES = 2_000_000
INTAKE_STATUS = {"invalid_project_id": 422, "not_found": 404, "not_prepared": 404, "invalid_request": 422,
                 "source_mismatch": 409, "unsupported_input_mode": 422, "existing_output_invalid": 409}
FICTION_STATUS = {"intake_missing": 409, "package_missing": 404, "invalid_draft": 422, "package_exists": 409,
                  "existing_output_invalid": 409, "invalid_request": 422}
REVIEW_STATUS = {"unknown_target": 404, "invalid_decision": 422, "stale_decision": 409, "log_invalid": 409}
REVIEWED_STATUS = {"reviewed_missing": 404, "invalid_version": 422, "reviewed_invalid": 409,
                   "stale_reviewed": 409, "approval_blocked": 409}


def workspace_key(root: Path) -> str:
    return hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()


def create_app(store: ProductionStore | None = None):
    # One origin keeps /p/<id>, /api/project/* and /ui/* URLs intact. No Backlot source edits.
    app = create_backlot_app()
    service = store or ProductionStore(PROJECTS_DIR, ApprovedPackages(REPO_ROOT))
    app.state.studio_store = service
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @app.middleware("http")
    async def studio_headers(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/studio"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
            )
        return response

    @app.get("/studio", include_in_schema=False)
    @app.get("/studio/", include_in_schema=False)
    async def studio_page():
        return FileResponse(UI_DIR / "index.html", media_type="text/html; charset=utf-8")

    @app.get("/studio/api/health")
    async def health():
        return {"ok": True, "app": "openmontage-studio", "workspace": workspace_key(service.root)}

    @app.get("/studio/api/packages")
    async def packages():
        items, warnings = await run_in_threadpool(service.catalog.available)
        return {"packages": items, "warnings": warnings}

    @app.get("/studio/api/productions")
    async def productions():
        rows = await run_in_threadpool(service.list_productions)
        for row in rows:  # Presence only; GET .../intake verifies hashes before showing a draft.
            if row["kind"] == "studio":
                report = service.root / row["project_id"] / INTAKE_DIR / INTAKE_FILES["report"]
                row["intake_status"] = "prepared" if report.is_file() else "not_prepared"
        return rows

    @app.get("/studio/api/productions/{project_id}")
    async def production(project_id: str):
        try:
            return await run_in_threadpool(service.detail, project_id)
        except FileNotFoundError:
            raise HTTPException(404, "Saved Studio production not found.")
        except (ValueError, OSError):
            raise HTTPException(400, "Saved Studio production is invalid or its input changed.")

    @app.post("/studio/api/productions", status_code=201)
    async def save(request: Request):
        require_local_json_post(request)
        length = 0
        chunks = []
        async for chunk in request.stream():
            length += len(chunk)
            if length > MAX_BODY_BYTES:
                raise HTTPException(413, "Production request exceeds the 2 MB request limit.")
            chunks.append(chunk)
        try:
            data = NewProduction.model_validate_json(b"".join(chunks))
        except ValidationError as exc:
            return JSONResponse(status_code=422, content={"detail": exc.errors(
                include_url=False, include_context=False, include_input=False)})
        try:
            return await run_in_threadpool(service.create, data)
        except ProjectExistsError as exc:
            raise HTTPException(409, str(exc))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        except OSError:
            raise HTTPException(500, "Could not save the request. Check local disk access; no production was started.")

    @app.post("/studio/api/productions/{project_id}/intake")
    async def prepare_intake(project_id: str, request: Request):
        # User-triggered only: intake never runs on save, list or page load.
        require_local_json_post(request)
        try:
            result = await run_in_threadpool(prepare_story_intake, service, project_id)
        except IntakeError as exc:
            raise HTTPException(INTAKE_STATUS.get(exc.code, 422), {"code": exc.code, "message": str(exc)})
        except OSError:
            raise HTTPException(500, {"code": "write_failed", "message": "Could not write the story draft. Check "
                                      "local disk access; the original story is unchanged."})
        return JSONResponse(status_code=201 if result["status"] == "created" else 200, content=result)

    @app.get("/studio/api/productions/{project_id}/intake")
    async def intake(project_id: str):
        try:
            return {"status": "prepared", **await run_in_threadpool(read_story_intake, service, project_id)}
        except IntakeError as exc:
            raise HTTPException(INTAKE_STATUS.get(exc.code, 422), {"code": exc.code, "message": str(exc)})

    def story_error(exc):
        if isinstance(exc, ReviewedPackageError):
            return HTTPException(REVIEWED_STATUS.get(exc.code, 422),
                                 {"code": exc.code, "message": str(exc), "blockers": exc.blockers})
        if isinstance(exc, IntakeError):
            return HTTPException(INTAKE_STATUS.get(exc.code, 422), {"code": exc.code, "message": str(exc)})
        if isinstance(exc, FictionPackageError):
            return HTTPException(FICTION_STATUS.get(exc.code, 422),
                                 {"code": exc.code, "message": str(exc), "problems": exc.problems})
        return HTTPException(REVIEW_STATUS.get(exc.code, 422), {"code": exc.code, "message": str(exc)})

    async def json_body(request: Request):
        require_local_json_post(request)
        chunks, length = [], 0
        async for chunk in request.stream():
            length += len(chunk)
            if length > MAX_BODY_BYTES:
                raise HTTPException(413, "Request exceeds the 2 MB limit.")
            chunks.append(chunk)
        try:
            return json.loads(b"".join(chunks))
        except ValueError:
            raise HTTPException(422, {"code": "invalid_json", "message": "Send valid JSON."})

    @app.post("/studio/api/productions/{project_id}/fiction-package")
    async def build_package(project_id: str, request: Request):
        # Explicit import of an authored Story Bible draft; never triggered by intake or review.
        draft = await json_body(request)
        try:
            result = await run_in_threadpool(build_fiction_package, service, project_id, draft)
        except (IntakeError, FictionPackageError) as exc:
            raise story_error(exc)
        except OSError:
            raise HTTPException(500, {"code": "write_failed", "message": "Could not write the fiction package; "
                                      "the original story is unchanged."})
        return JSONResponse(status_code=201 if result["status"] == "created" else 200, content=result)

    @app.get("/studio/api/productions/{project_id}/fiction-package")
    async def fiction_package(project_id: str):
        try:
            return await run_in_threadpool(read_fiction_package, service, project_id)
        except (IntakeError, FictionPackageError) as exc:
            raise story_error(exc)

    @app.get("/studio/api/productions/{project_id}/review")
    async def review(project_id: str):
        try:
            return await run_in_threadpool(review_view, service, project_id)
        except (IntakeError, FictionPackageError, ReviewError) as exc:
            raise story_error(exc)

    @app.post("/studio/api/productions/{project_id}/review/decisions", status_code=201)
    async def decide(project_id: str, request: Request):
        payload = await json_body(request)
        if not isinstance(payload, dict):
            raise HTTPException(422, {"code": "invalid_decision", "message": "Send a decision object."})
        try:
            return await run_in_threadpool(record_decision, service, project_id, payload)
        except (IntakeError, FictionPackageError, ReviewError) as exc:
            raise story_error(exc)
        except OSError:
            raise HTTPException(500, {"code": "write_failed", "message": "Could not record the decision."})

    @app.get("/studio/api/productions/{project_id}/reviewed-story")
    async def reviewed_story(project_id: str):
        try:
            return await run_in_threadpool(read_reviewed_story, service, project_id)
        except (IntakeError, FictionPackageError, ReviewError, ReviewedPackageError) as exc:
            raise story_error(exc)

    @app.get("/studio/api/productions/{project_id}/reviewed-story/{version}")
    async def reviewed_version(project_id: str, version: str):
        try:
            return await run_in_threadpool(read_reviewed_story, service, project_id, version)
        except (IntakeError, FictionPackageError, ReviewError, ReviewedPackageError) as exc:
            raise story_error(exc)

    @app.post("/studio/api/productions/{project_id}/reviewed-story")
    async def materialize_reviewed(project_id: str, request: Request):
        if await json_body(request) != {}:
            raise HTTPException(422, "Send an empty JSON object; inputs come from the verified production.")
        try:
            result = await run_in_threadpool(materialize_reviewed_story, service, project_id)
            return JSONResponse(status_code=201 if result["status"] == "created" else 200, content=result)
        except (IntakeError, FictionPackageError, ReviewError, ReviewedPackageError) as exc:
            raise story_error(exc)
        except OSError:
            raise HTTPException(500, "Could not save the reviewed version. No production was started.")

    @app.post("/studio/api/productions/{project_id}/reviewed-story/{version}/approve")
    async def approve_reviewed(project_id: str, version: str, request: Request):
        body = await json_body(request)
        if (not isinstance(body, dict) or set(body) != {"package_sha256", "manifest_sha256"}
                or not all(isinstance(value, str) and len(value) == 64 for value in body.values())):
            raise HTTPException(422, "Approval requires the exact displayed package and manifest hashes.")
        try:
            return await run_in_threadpool(approve_reviewed_story, service, project_id, version,
                                           body["package_sha256"], body["manifest_sha256"])
        except (IntakeError, FictionPackageError, ReviewError, ReviewedPackageError) as exc:
            raise story_error(exc)
        except OSError:
            raise HTTPException(500, "Could not record approval. No production was started.")

    app.mount("/studio/static", StaticFiles(directory=UI_DIR), name="studio-static")
    return app


def require_local_json_post(request: Request) -> None:
    origin = request.headers.get("origin")
    expected = urlsplit(str(request.base_url))
    if origin:
        supplied = urlsplit(origin)
        if (supplied.scheme, supplied.netloc) != (expected.scheme, expected.netloc):
            raise HTTPException(403, "Use Studio from this local origin.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Cross-site requests are not allowed.")
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
        raise HTTPException(415, "Send a JSON request.")
