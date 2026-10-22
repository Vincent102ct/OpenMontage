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
from studio.intake import FILES as INTAKE_FILES, OUTPUT_DIR as INTAKE_DIR
from studio.intake import IntakeError, prepare_story_intake, read_story_intake
from studio.models import NewProduction
from studio.store import ProductionStore, ProjectExistsError

UI_DIR = Path(__file__).parent / "ui"
MAX_BODY_BYTES = 2_000_000
INTAKE_STATUS = {"invalid_project_id": 422, "not_found": 404, "not_prepared": 404, "invalid_request": 422,
                 "source_mismatch": 409, "unsupported_input_mode": 422, "existing_output_invalid": 409}


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
