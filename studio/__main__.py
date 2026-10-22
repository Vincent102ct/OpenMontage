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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["open", "serve"])
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    from lib.paths import PROJECTS_DIR
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
