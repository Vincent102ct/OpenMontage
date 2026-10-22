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
from studio.models import NewProduction
from studio.store import ProductionStore, ProjectExistsError

UI_DIR = Path(__file__).parent / "ui"
MAX_BODY_BYTES = 2_000_000


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
        return await run_in_threadpool(service.list_productions)

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
        origin = request.headers.get("origin")
        expected = urlsplit(str(request.base_url))
        if origin:
            supplied = urlsplit(origin)
            if (supplied.scheme, supplied.netloc) != (expected.scheme, expected.netloc):
                raise HTTPException(403, "Use Studio from this local origin to save a request.")
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Cross-site saves are not allowed.")
        if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
            raise HTTPException(415, "Send a JSON production request.")
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

    app.mount("/studio/static", StaticFiles(directory=UI_DIR), name="studio-static")
    return app
