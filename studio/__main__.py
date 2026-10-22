"""python -m studio open — serve locally and open the input interface."""

from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.request
import webbrowser

DEFAULT_PORT = 4760


def open_browser_when_ready(port: int, expected_workspace: str) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/studio/api/health", timeout=0.5) as response:
                health = json.load(response)
            if health.get("app") == "openmontage-studio" and health.get("workspace") == expected_workspace:
                webbrowser.open(f"http://127.0.0.1:{port}/studio")
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.15)
    print("Studio browser did not open automatically; use the printed local URL.")


def run_intake(projects_dir, project_id: str) -> int:
    """Prepare Story Draft from the terminal: same checks and outputs as the Studio button."""
    from lib.paths import REPO_ROOT
    from studio.catalog import ApprovedPackages
    from studio.intake import IntakeError, prepare_story_intake
    from studio.store import ProductionStore

    try:
        result = prepare_story_intake(ProductionStore(projects_dir, ApprovedPackages(REPO_ROOT)), project_id)
    except IntakeError as exc:
        print(json.dumps({"status": "refused", "code": exc.code, "message": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    report = result["report"]
    print(json.dumps({"status": result["status"], "project_id": project_id, "review": report["review"]["status"],
                      "analysis_coverage": report["analysis_coverage"]["overall"], "counts": report["counts"],
                      "saved_files": result["saved_files"]}, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["open", "serve", "intake"])
    parser.add_argument("project_id", nargs="?", help="intake only: saved Studio production ID")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    from lib.paths import PROJECTS_DIR
    if args.command == "intake":
        if not args.project_id:
            parser.error("intake needs a project ID")
        return run_intake(PROJECTS_DIR, args.project_id)
    if args.project_id:
        parser.error("project ID is only used with intake")
    from studio.server import create_app, workspace_key
    import uvicorn

    print(f"OpenMontage Studio: http://127.0.0.1:{args.port}/studio", flush=True)
    print("Input only. Production not started. Keep this terminal open; Ctrl+C stops Studio.", flush=True)
    if args.command == "open":
        threading.Thread(target=open_browser_when_ready, args=(args.port, workspace_key(PROJECTS_DIR)),
                         daemon=True).start()
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
