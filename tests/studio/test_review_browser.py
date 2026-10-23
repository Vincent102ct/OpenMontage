"""P2.2 review UI in real Chrome against an isolated fixture workspace."""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from studio.catalog import ApprovedPackages
from studio.intake import prepare_story_intake
from studio.models import NewProduction
from studio.review import DECISION_DIR
from studio.store import ProductionStore
from tests.studio.fiction_fixture import STORY, draft

ROOT = Path(__file__).resolve().parents[2]


def test_review_flow_in_real_chrome(tmp_path):
    chrome = os.environ.get("STUDIO_TEST_CHROME") or next((str(p) for p in [
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    ] if p.is_file()), None)
    node = shutil.which("node")
    if not chrome or not node or not (ROOT / "remotion-composer/node_modules/@remotion/renderer").is_dir():
        pytest.skip("Needs installed Chrome, Node and the existing Remotion browser driver; no downloads.")
    projects = tmp_path / "projects"
    projects.mkdir()
    store = ProductionStore(projects, ApprovedPackages(ROOT))
    store.create(NewProduction(project_id="fixture-review", input_mode="story", content=STORY,
                               formats=["short", "long"]))
    prepare_story_intake(store, "fixture-review")
    draft_path = tmp_path / "story_bible.draft.json"
    draft_path.write_text(json.dumps(draft(), ensure_ascii=False), encoding="utf-8")
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
        f"store=ProductionStore(Path({str(projects)!r}), ApprovedPackages(Path({str(ROOT)!r})))\n"
        f"uvicorn.run(create_app(store), host='127.0.0.1', port={port}, log_level='warning')\n",
        encoding="utf-8")
    env = {**os.environ, "OPENMONTAGE_PROJECTS_DIR": str(projects), "PYTHONDONTWRITEBYTECODE": "1"}
    with (tmp_path / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-B", str(runner)], cwd=ROOT, env=env, stdout=log, stderr=log,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            url = f"http://127.0.0.1:{port}/studio"
            for _ in range(100):
                try:
                    with urllib.request.urlopen(url + "/api/health", timeout=0.3):
                        break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.1)
            result = subprocess.run([node, str(ROOT / "tests/studio/review_browser.cjs"), url, chrome,
                                     str(screenshots), str(draft_path), "fixture-review"],
                                    cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            assert result.returncode == 0, result.stdout + result.stderr
            findings = json.loads((screenshots / "review-results.json").read_text(encoding="utf-8"))
            assert len(findings["checks"]) >= 9 and not findings["externalRequests"] and not findings["pageErrors"]
            decisions = sorted((projects / "fixture-review" / DECISION_DIR).glob("*.json"))
            records = [json.loads(p.read_text(encoding="utf-8")) for p in decisions]
            assert [(r["target_id"], r["decision"]) for r in records] == [
                ("CHG_0001", "accept"), ("CHG_0001", "reject"), ("AMB_WRITER", "answer"), ("FMT_SHORT", "defer")]
            assert records[1]["supersedes"] == "DEC_000001"
            assert records[2]["answer"] == "Chưa xác định; giữ bí ẩn."
            assert not list(projects.rglob("checkpoint_*.json"))
            assert not list(projects.rglob("*.wav")) and not list(projects.rglob("*.mp4"))
        finally:
            process.terminate()
            process.wait(timeout=10)
