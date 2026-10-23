"""User-triggered reference PNGs through the existing rig/StoryVideo/Remotion renderer."""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from lib.story_visual_bible import VisualBibleError, fingerprint
from studio.review import review_lock, safe_review_path
from studio.reviewed import _bytes, _sha
from studio.visual_bible import _displayed, read_visual_bible
from tools.character.asset_library_demo import build_environment_still, build_pose_reel
from tools.tool_registry import ToolRegistry

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = "assets/visual_bible_refs"


def _read(project, key):
    if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key):
        raise VisualBibleError("invalid_reference", "Invalid reference identifier.")
    folder = f"{OUTPUT_DIR}/{key}"
    try:
        report = json.loads(safe_review_path(project, f"{folder}/references.json").read_bytes())
        if report["key"] != key or report["integrity_sha256"] != fingerprint({k: v for k, v in report.items()
                                                                            if k != "integrity_sha256"}):
            raise ValueError("Reference manifest mismatch")
        for ref in report["references"]:
            if not re.fullmatch(r"ref-[0-9]+\.png", ref["file"]):
                raise ValueError("Unsafe reference filename")
            raw = safe_review_path(project, f"{folder}/{ref['file']}").read_bytes()
            if not raw.startswith(b"\x89PNG\r\n\x1a\n") or _sha(raw) != ref["sha256"]:
                raise ValueError("Reference PNG changed")
        return report
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise VisualBibleError("invalid_reference", "Reference files failed verification; nothing was overwritten.") from exc


def reference_file(store, project_id, key, name):
    # Verify story input/path protections too; a stale design is never served as current.
    view = read_visual_bible(store, project_id)
    if not view.get("is_current"):
        raise VisualBibleError("stale_visual", "Reload the current approved story and visual candidate.")
    project = store._project(project_id)
    report = _read(project, key)
    if ((report["package_sha256"], report["manifest_sha256"]) != (view["package_sha256"], view["manifest_sha256"])
            or name not in [r["file"] for r in report["references"]]):
        raise VisualBibleError("invalid_reference", "Reference does not belong to this displayed visual candidate.")
    return safe_review_path(project, f"{OUTPUT_DIR}/{key}/{name}")


def prepare_references(store, project_id, version, package_sha256, manifest_sha256):
    project = store._project(project_id)
    with review_lock(project):
        view = read_visual_bible(store, project_id, version)
        _displayed(view, package_sha256, manifest_sha256)
        sources = {p.name: _sha(p.read_bytes()) for p in (ROOT / "tools/character/remotion").glob("*.ts*")}
        sources["render_reference.cjs"] = _sha((ROOT / "tools/character/render_reference.cjs").read_bytes())
        for name in ("tools/character/asset_library_demo.py", "tools/character/horror_acting.py",
                     "tools/character/story_video.py", "studio/visual_references.py"):
            sources[name] = _sha((ROOT / name).read_bytes())
        key = fingerprint({"package_sha256": package_sha256, "manifest_sha256": manifest_sha256, "sources": sources})
        target = safe_review_path(project, f"{OUTPUT_DIR}/{key}")
        if target.exists():
            return _read(project, key)
        chrome = Path(os.environ.get("REMOTION_BROWSER_EXECUTABLE", "C:/Program Files/Google/Chrome/Application/chrome.exe"))
        if not chrome.is_file() or not shutil.which("node"):
            raise VisualBibleError("reference_unavailable", "Reference preview needs installed Chrome and Node; nothing is downloaded.")
        if not (ROOT / "remotion-composer/node_modules/@remotion/renderer").is_dir():
            raise VisualBibleError("reference_unavailable", "Installed Remotion dependencies are unavailable; text/palette inspection remains available.")
        p, jobs = view["package"], []
        characters = [c for c in p["characters"] if c["representation"] == "character" and c["asset"]]
        for loc in p["locations"]:
            if not loc["geometry"] or not loc["environment"] or not loc["lighting"]:
                continue
            env_id = loc["environment"]["id"]
            env_video, env_timeline = build_environment_still(env_id, loc["lighting"]["id"])
            env_video["locations"]["env"]["cinematic"] = copy.deepcopy(loc["geometry"])
            intensity = .85 if loc["presence"] else 0
            env_video["horror"]["presence"] = [[0, intensity, 0], [1, intensity, 0]]
            jobs.append((f"Environment {loc['canonical_id']} · {env_id}", env_video, env_timeline, 15))
            for c in characters:
                video, timeline = build_pose_reel(c["asset"]["id"], env_id)
                video["locations"]["ref-loc"]["cinematic"] = copy.deepcopy(loc["geometry"])
                video["horror"] = {"presence": [[0, 0, 0], [4, 0, 0]], "spill": [[0, .7], [4, .7]],
                                   "flicker": [[0, 1], [4, 1]]}
                for frame in (6, 57):
                    jobs.append((f"{c['canonical_id']} · {loc['canonical_id']} · frame {frame}", video, timeline, frame))
        if not jobs or len(jobs) > 40:
            raise VisualBibleError("reference_unavailable", "Bind compatible environments first. A reference batch supports at most 40 stills.")
        folder = safe_review_path(project, OUTPUT_DIR)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = safe_review_path(project, f"{OUTPUT_DIR}/.tmp-{uuid.uuid4().hex}")
        tmp.mkdir()
        try:
            registry = ToolRegistry()
            registry.discover("tools.character.character_animation")
            renderer = registry.get("character_rig_renderer")
            # This tool only prepares an audio-free reference workspace; no story is produced.
            package = renderer.execute({"story_video": jobs[0][1], "action_timeline": jobs[0][2],
                                        "workspace_path": str(tmp / "work")})
            if not package.success:
                raise VisualBibleError("reference_unavailable", package.error)
            refs = [{"label": label, "props": video, "frame": frame, "output": str(tmp / f"ref-{i}.png")}
                    for i, (label, video, _, frame) in enumerate(jobs)]
            job = {"chrome": str(chrome), "entry": str(tmp / "work/index.tsx"),
                   "publicDir": str(tmp / "work/public"), "bundle": str(tmp / "bundle"), "references": refs}
            (tmp / "job.json").write_bytes(_bytes(job))
            result = subprocess.run(["node", str(ROOT / "tools/character/render_reference.cjs"), str(tmp / "job.json")],
                                    capture_output=True, text=True, timeout=180,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode:
                raise VisualBibleError("reference_unavailable", "Local Remotion reference rendering failed; no alternate renderer was substituted.")
            _displayed(read_visual_bible(store, project_id, version), package_sha256, manifest_sha256)
            report = {"key": key, "package_sha256": package_sha256, "manifest_sha256": manifest_sha256,
                      "renderer": "character_rig_renderer/StoryVideo/Remotion renderStill", "source_hashes": sources,
                      "full_story_rendered": False,
                      "references": [{"file": f"ref-{i}.png", "label": r["label"],
                                      "sha256": _sha((tmp / f"ref-{i}.png").read_bytes())} for i, r in enumerate(refs)]}
            report["integrity_sha256"] = fingerprint(report)
            (tmp / "references.json").write_bytes(_bytes(report))
            os.rename(tmp, target)
            return _read(project, key)
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise VisualBibleError("reference_unavailable", "Local reference rendering unavailable; no production was started.") from exc
        finally:
            if tmp.exists():
                assert tmp.resolve().is_relative_to(folder.resolve())
                shutil.rmtree(tmp)
