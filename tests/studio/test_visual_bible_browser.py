"""Real Chrome against a synthetic approved-fiction flow; no real production is loaded."""
import json
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from studio.catalog import ApprovedPackages
from studio.store import ProductionStore
from studio.visual_bible import read_visual_bible, scene_planning_handoff
from tests.studio.visual_bible_fixture import prepare_story

ROOT = Path(__file__).resolve().parents[2]


def test_visual_bible_real_browser(tmp_path):
    chrome = os.environ.get("STUDIO_TEST_CHROME", "C:/Program Files/Google/Chrome/Application/chrome.exe")
    if not Path(chrome).is_file() or not shutil.which("node") or not (ROOT / "remotion-composer/node_modules/@remotion/renderer").is_dir():
        pytest.skip("Needs installed Chrome/Node/Remotion; nothing is downloaded.")
    projects = tmp_path / "p"
    store = ProductionStore(projects, ApprovedPackages(ROOT))
    story = prepare_story(store, approve=False)
    assert not story["ready_for_next_stage"]
    output = Path(os.environ.get("STUDIO_SCREENSHOT_DIR", str(tmp_path / "screenshots"))) / "p33"
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    runner = tmp_path / "server.py"
    runner.write_text(f"import sys\nfrom pathlib import Path\nsys.path.insert(0,{str(ROOT)!r})\n"
                      "import uvicorn\nfrom studio.server import create_app\nfrom studio.store import ProductionStore\n"
                      "from studio.catalog import ApprovedPackages\n"
                      f"uvicorn.run(create_app(ProductionStore(Path({str(projects)!r}),ApprovedPackages(Path({str(ROOT)!r})))),host='127.0.0.1',port={port},log_level='warning')\n", encoding="utf-8")
    env = {**os.environ, "OPENMONTAGE_PROJECTS_DIR": str(projects), "PYTHONDONTWRITEBYTECODE": "1",
           "REMOTION_BROWSER_EXECUTABLE": chrome}
    with (tmp_path / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-B", str(runner)], cwd=ROOT, env=env, stdout=log, stderr=log,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            url = f"http://127.0.0.1:{port}/studio"
            for _ in range(100):
                try:
                    urllib.request.urlopen(url + "/api/health", timeout=.3).close(); break
                except OSError: time.sleep(.1)
            result = subprocess.run(["node", str(ROOT / "tests/studio/visual_bible_browser.cjs"), url, chrome, str(output)],
                                    cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=240,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            assert result.returncode == 0, result.stdout + result.stderr + "\nServer: " + (tmp_path / "server.log").read_text()
            qa = json.loads((output / "visual-results.json").read_text())
            assert len(qa["checks"]) >= 10 and not qa["externalRequests"] and not qa["pageErrors"]
            current = read_visual_bible(store, "fx")
            assert current["ready_for_next_stage"] and current["version"] == "v7"
            assert not read_visual_bible(store, "fx", "v5")["ready_for_next_stage"]
            assert read_visual_bible(store, "fx", "v3")["approval"]
            assert read_visual_bible(store, "fx", "v5")["approval"]
            reports = list((projects / "fx/assets/visual_bible_refs").glob("*/references.json"))
            assert len(reports) == 1
            references = json.loads(reports[0].read_bytes())
            assert len(references["references"]) == 10
            for ref in references["references"]:
                raw = (reports[0].parent / ref["file"]).read_bytes()
                assert raw.startswith(b"\x89PNG\r\n\x1a\n")
                assert hashlib.sha256(raw).hexdigest() == ref["sha256"]
            # The local Remotion public root contains no story, approval, audio or private files.
            assert list((reports[0].parent / "work/public").iterdir()) == []
            (output / "example.visual-bible.json").write_text(json.dumps(current["package"], ensure_ascii=False, indent=2), encoding="utf-8")
            (output / "scene-planning-handoff.json").write_text(json.dumps(scene_planning_handoff(store, "fx"), ensure_ascii=False, indent=2), encoding="utf-8")
            (output / "approval.json").write_text(json.dumps(current["approval"], ensure_ascii=False, indent=2), encoding="utf-8")
            assert not list(projects.rglob("*.mp4")) and not list(projects.rglob("*.wav"))
            assert not list(projects.rglob("checkpoint_*.json"))
        finally:
            process.terminate(); process.wait(timeout=10)
