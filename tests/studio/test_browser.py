"""End-to-end browser input checks against isolated fictional workspaces."""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from tests.studio.fixtures import fixture_catalog

ROOT = Path(__file__).resolve().parents[2]


def test_real_chrome_input_flows(tmp_path):
    chrome = os.environ.get("STUDIO_TEST_CHROME") or next((str(p) for p in [
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    ] if p.is_file()), None)
    node = shutil.which("node")
    if not chrome or not node or not (ROOT / "remotion-composer/node_modules/@remotion/renderer").is_dir():
        pytest.skip("Needs installed Chrome, Node and the existing Remotion browser driver; no downloads.")
    repo = tmp_path / "fixture-repo"
    package = fixture_catalog(repo)
    original = package.read_bytes()
    projects = tmp_path / "projects"
    projects.mkdir()
    screenshots = Path(os.environ.get("STUDIO_SCREENSHOT_DIR") or tmp_path / "screenshots").resolve()
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    runner = tmp_path / "run_studio.py"
    runner.write_text(
        "import sys\nfrom pathlib import Path\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from studio.catalog import ApprovedPackages\n"
        "from studio.store import ProductionStore\nfrom studio.server import create_app\nimport uvicorn\n"
        f"store=ProductionStore(Path({str(projects)!r}), ApprovedPackages(Path({str(repo)!r})))\n"
        f"uvicorn.run(create_app(store), host='127.0.0.1', port={port}, log_level='warning')\n",
        encoding="utf-8",
    )
    env = {**os.environ, "OPENMONTAGE_PROJECTS_DIR": str(projects), "PYTHONDONTWRITEBYTECODE": "1"}
    with (tmp_path / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-B", str(runner)], cwd=ROOT, env=env,
                                   stdout=log, stderr=log,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            url = f"http://127.0.0.1:{port}/studio"
            ready = False
            for _ in range(100):
                try:
                    with urllib.request.urlopen(url + "/api/health", timeout=0.3) as response:
                        ready = response.status == 200
                        break
                except (OSError, urllib.error.URLError):
                    if process.poll() is not None:
                        break
                    time.sleep(0.1)
            assert ready, (tmp_path / "server.log").read_text(encoding="utf-8")
            result = subprocess.run([node, str(ROOT / "tests/studio/browser.cjs"), url, chrome, str(screenshots)],
                                    cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=90,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            (tmp_path / "browser.log").write_text(result.stdout + result.stderr, encoding="utf-8")
            assert result.returncode == 0, result.stdout + result.stderr
            findings = json.loads((screenshots / "browser-results.json").read_text(encoding="utf-8"))
            assert len(findings["checks"]) >= 20
            reports = list(projects.glob("*/artifacts/story_intake/v1/story_intake_report.json"))
            assert [r.parents[3].name for r in reports] == ["fixture-vietnamese"]
            report = json.loads(reports[0].read_text(encoding="utf-8"))
            assert report["review"]["status"] == "pending_human_review" and report["production_started"] is False
            assert findings["externalRequests"] == [] and findings["pageErrors"] == []
            assert package.read_bytes() == original
            assert len(list(projects.glob("*/artifacts/production_request.json"))) == 4
            assert not list(projects.rglob("checkpoint_*.json"))
            assert not list(projects.rglob("*.wav")) and not list(projects.rglob("*.mp4"))
        finally:
            process.terminate()
            process.wait(timeout=10)
