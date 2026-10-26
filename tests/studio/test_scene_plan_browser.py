"""Real Chrome against a synthetic approved story + Visual Bible; no real production is loaded."""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from lib.story_scene_plan import action_timeline, coverage_report
from studio.catalog import ApprovedPackages
from studio.scene_plan import read_scene_plan, scene_plan_handoff
from studio.store import ProductionStore
from tests.studio.scene_plan_fixture import prepare

ROOT = Path(__file__).resolve().parents[2]


def test_scene_plan_real_browser(tmp_path):
    chrome = os.environ.get("STUDIO_TEST_CHROME", "C:/Program Files/Google/Chrome/Application/chrome.exe")
    if not Path(chrome).is_file() or not shutil.which("node") or not (ROOT / "remotion-composer/node_modules/@remotion/renderer").is_dir():
        pytest.skip("Needs installed Chrome/Node/Remotion; nothing is downloaded.")
    projects = tmp_path / "p"
    store = ProductionStore(projects, ApprovedPackages(ROOT))
    prepare(store)  # Synthetic P2.3 + P3.3 approvals (their own browser tests cover those UI actions).
    output = Path(os.environ.get("STUDIO_SCREENSHOT_DIR", str(tmp_path / "screenshots"))) / "p34"
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    runner = tmp_path / "server.py"
    runner.write_text(f"import sys\nfrom pathlib import Path\nsys.path.insert(0,{str(ROOT)!r})\n"
                      "import uvicorn\nfrom studio.server import create_app\nfrom studio.store import ProductionStore\n"
                      "from studio.catalog import ApprovedPackages\n"
                      f"uvicorn.run(create_app(ProductionStore(Path({str(projects)!r}),ApprovedPackages(Path({str(ROOT)!r})))),host='127.0.0.1',port={port},log_level='warning')\n", encoding="utf-8")
    env = {**os.environ, "OPENMONTAGE_PROJECTS_DIR": str(projects), "PYTHONDONTWRITEBYTECODE": "1"}
    with (tmp_path / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-B", str(runner)], cwd=ROOT, env=env, stdout=log, stderr=log,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            url = f"http://127.0.0.1:{port}/studio"
            for _ in range(100):
                try:
                    urllib.request.urlopen(url + "/api/health", timeout=.3).close(); break
                except OSError: time.sleep(.1)
            result = subprocess.run(["node", str(ROOT / "tests/studio/scene_plan_browser.cjs"), url, chrome, str(output)],
                                    cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=600,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            assert result.returncode == 0, result.stdout + result.stderr + "\nServer: " + (tmp_path / "server.log").read_text()
            qa = json.loads((output / "scene-plan-results.json").read_text())
            assert len(qa["checks"]) >= 15 and not qa["externalRequests"] and not qa["pageErrors"]
            current = read_scene_plan(store, "fx")
            assert current["version"] == "v6" and current["ready_for_next_stage"]
            assert read_scene_plan(store, "fx", "v4")["approval"] and not read_scene_plan(store, "fx", "v4")["ready_for_next_stage"]
            assert all(not read_scene_plan(store, "fx", v)["approval"] for v in ("v1", "v2", "v3", "v5"))
            plan = current["package"]
            (output / "example.scene-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            (output / "scene-plan-approval.json").write_text(json.dumps(current["approval"], ensure_ascii=False, indent=2), encoding="utf-8")
            (output / "scene-plan-handoff.json").write_text(json.dumps(scene_plan_handoff(store, "fx"), ensure_ascii=False, indent=2), encoding="utf-8")
            (output / "coverage-report.md").write_text(coverage_report(plan), encoding="utf-8")
            for fmt in ("short", "long"):
                (output / f"provisional-action-timeline.{fmt}.json").write_text(
                    json.dumps(action_timeline(plan, fmt, approved=current), ensure_ascii=False, indent=2), encoding="utf-8")
            assert not list(projects.rglob("*.mp4")) and not list(projects.rglob("*.wav"))
            assert not list(projects.rglob("checkpoint_*.json"))
        finally:
            process.terminate(); process.wait(timeout=10)
