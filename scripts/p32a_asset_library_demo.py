"""Render the P3.2A synthetic asset-library proof through the registered local tools.

Run from the repository root: .venv/Scripts/python scripts/p32a_asset_library_demo.py
Writes only gitignored projects/p32a-* directories. Synthetic material only: no real
story, Story Bible, pilot, TTS, paid API, publication or production checkpoint.
"""
from __future__ import annotations

import hashlib
import argparse
from functools import partial
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from stickman_horror_preview import run_tool, save  # noqa: E402
from tools.character import horror_assets as lib  # noqa: E402
from tools.character.asset_library_demo import AUDIO_RECIPES, build_story_a, build_story_b  # noqa: E402
from tools.tool_registry import ToolRegistry  # noqa: E402

STORIES = {"p32a-story-a-room": (build_story_a, [0, 1.35, 2.9, 4.4, 5.8, 7.9, 8.6, 9.9]),
           "p32a-story-b-corridor": (build_story_b, [0, 2.0, 3.8, 4.5, 5.5, 6.3, 8.0, 9.9])}
LIBRARY_PROJECT = "p32a-asset-library"
SWAPS = {
    "p32a-swap-nora-corridor": (partial(build_story_b, character_id="nora_vale"), STORIES["p32a-story-b-corridor"][1]),
    "p32a-swap-victor-room": (partial(build_story_a, character_id="victor_hale"), STORIES["p32a-story-a-room"][1]),
}


def _project(project_id: str) -> Path:
    project = ROOT / "projects" / project_id
    marker = {"project_id": project_id, "synthetic": True, "milestone": "P3.2A"}
    if project.exists() and (not (project / "preview-scope.json").is_file()
                             or json.loads((project / "preview-scope.json").read_text()) != marker):
        raise RuntimeError(f"Refusing to overwrite {project} without the matching synthetic marker")
    if subprocess.run(["git", "check-ignore", "--quiet", str(project / "preview.mp4")]).returncode:
        raise RuntimeError("Output must be gitignored")
    project.mkdir(parents=True, exist_ok=True)
    save(project / "preview-scope.json", marker)
    return project


def inspect_mp4(registry: ToolRegistry, project: Path, video: dict, timestamps: list[float]) -> dict:
    """Probe, fully decode and sample the real MP4; measure SFX events against the room tone."""
    import numpy as np
    from PIL import Image
    output = project / "preview.mp4"
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json",
                                       str(output)], check=True, capture_output=True, text=True).stdout)
    v = next(s for s in probe["streams"] if s["codec_type"] == "video")
    a = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    vw, vh = video["viewport"]["width"], video["viewport"]["height"]
    assert (v["codec_name"], v["width"], v["height"], v["r_frame_rate"]) == ("h264", vw, vh, "30/1")
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(output), "-f", "null", "-"], check=True)
    w, h = vw // 8, vh // 8
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(output), "-vf", f"scale={w}:{h}", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], check=True, capture_output=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, h, w)
    assert len(frames) == 300 and float(frames.std(axis=(1, 2)).min()) > 5, "Blank or missing frame"
    unique = len({hashlib.sha256(f.tobytes()).hexdigest() for f in frames})
    sampled = run_tool(registry, "frame_sampler", {"input_path": str(output), "strategy": "timestamps",
                       "timestamps": timestamps, "format": "png", "output_dir": str(project / "frames")})
    paths = sorted(Path(p["path"] if isinstance(p, dict) else p) for p in sampled.data["frames"])
    thumbs = [Image.open(p).convert("RGB").resize((vw // 4, vh // 4)) for p in paths]
    sheet = Image.new("RGB", (thumbs[0].width * 4, thumbs[0].height * 2), "black")
    for i, im in enumerate(thumbs):
        sheet.paste(im, ((i % 4) * im.width, (i // 4) * im.height))
    sheet.save(project / "contact-sheet.png")
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(output), "-ac", "1", "-ar", "48000", "-f", "f32le", "-"],
                         check=True, capture_output=True).stdout
    samples = np.frombuffer(pcm, np.float32)

    def rms(t0, t1):
        window = samples[int(t0 * 48000):int(t1 * 48000)]
        return float(np.sqrt(np.mean(window ** 2)))

    baseline = rms(*video["audio_qa"]["room_window"])
    events = [{"id": c["id"], "at_seconds": c["start_seconds"],
               "rms": rms(c["start_seconds"], c["start_seconds"] + min(.12, c["duration_seconds"]))}
              for c in video["sfx"] if c.get("role") != "ambience"]
    assert all(e["rms"] > baseline * 2 for e in events), "Missing/mistimed SFX event"
    peak = float(np.abs(samples).max())
    assert 0.01 < peak < .99, "Silent or clipped audio"
    quiet = [{"start": a, "end": b, "rms": rms(a, b)} for a, b in video["audio_qa"]["quiet_windows"]]
    assert all(q["rms"] < baseline * 3 for q in quiet), "Listening pause is not quiet"
    return {"probe": {"video": {k: v[k] for k in ("codec_name", "profile", "width", "height", "r_frame_rate", "nb_frames", "duration", "pix_fmt")},
                      "audio": {k: a[k] for k in ("codec_name", "sample_rate", "channels", "duration")},
                      "container_seconds": probe["format"]["duration"], "bytes": int(probe["format"]["size"])},
            "full_decode": "passed", "decoded_frames": len(frames), "unique_qa_frames": unique,
            "minimum_frame_stddev": float(frames.std(axis=(1, 2)).min()), "audio_peak": peak, "room_rms": baseline,
            "audio_events": events, "quiet_windows": quiet, "sampled_frames": [str(p) for p in paths],
            "mp4_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def render_story(registry: ToolRegistry, project_id: str, builder, timestamps) -> dict:
    project = _project(project_id)
    audio = {}
    for recipe, duration in AUDIO_RECIPES:
        target = project / "audio" / f"{recipe}.wav"
        run_tool(registry, "procedural_sfx", {"recipe": recipe, "duration_seconds": duration, "output_path": str(target)})
        audio[recipe] = target
    video, timeline = builder(audio)
    save(project / "story_video.json", video)
    save(project / "action_timeline.json", timeline)
    package = run_tool(registry, "character_rig_renderer", {"story_video": video, "action_timeline": timeline,
                       "workspace_path": str(project / "remotion"), "concurrency": 2})
    save(project / "handoff.json", package.data)
    print(f"Rendering {project_id} with local Chrome.", flush=True)
    result = run_tool(registry, "video_compose", {"operation": "render", "edit_decisions": package.data["edit_decisions"],
                      "asset_manifest": package.data["asset_manifest"], "output_path": str(project / "preview.mp4")})
    save(project / "render-result.json", result.data)
    media = inspect_mp4(registry, project, video, timestamps)
    report = {"synthetic": True, "milestone": "P3.2A", "real_story_approved": False, "tts_calls": 0,
              "paid_api_calls": 0, "cost_usd": 0, "production_checkpoints": [],
              "route": ["character_rig_renderer", "video_compose", "remotion"],
              "binding": video["asset_binding"], "validation": package.data["validation"], "media": media,
              "human_visual_review": "pending", "human_audio_review": "pending"}
    save(project / "validation-report.json", report)
    return {"project": project_id, "mp4": str(project / "preview.mp4"), **report}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--swaps-only", action="store_true", help="Render only the isolated cross-story cast swaps; preserve original evidence")
    args = parser.parse_args()
    selected = SWAPS if args.swaps_only else STORIES
    os.chdir(ROOT)
    for executable in ("ffmpeg", "ffprobe", "node"):
        if not shutil.which(executable):
            raise RuntimeError(f"Local {executable} required; nothing will be downloaded")
    chrome = Path(os.environ.get("REMOTION_BROWSER_EXECUTABLE", "C:/Program Files/Google/Chrome/Application/chrome.exe"))
    if not chrome.is_file():
        raise RuntimeError("Set REMOTION_BROWSER_EXECUTABLE to installed Chrome; no browser download allowed")
    os.environ["REMOTION_BROWSER_EXECUTABLE"] = str(chrome)
    library = _project("p32a-finalization-swaps" if args.swaps_only else LIBRARY_PROJECT)
    save(library / "asset-manifest.json", lib.manifest())
    registry = ToolRegistry()
    for module in ("tools.audio.procedural_sfx", "tools.character.character_animation",
                   "tools.video.video_compose", "tools.analysis.frame_sampler"):
        registry.discover(module)
    stories = [render_story(registry, pid, builder, ts) for pid, (builder, ts) in selected.items()]
    checks = json.loads(subprocess.run(["node", "tests/tools/asset_library_checks.cjs",
                                        *[f"projects/{pid}/story_video.json" for pid in selected]],
                                       check=True, capture_output=True, text=True).stdout)
    save(library / "frame-checks.json", checks)
    save(library / "stories.json", stories)
    print(json.dumps({s["project"]: s["media"]["mp4_sha256"] for s in stories}), flush=True)


if __name__ == "__main__":
    main()
