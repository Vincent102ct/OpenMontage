"""Render the isolated P3.0 synthetic proof through registered local tools.

Run from the repository root: .venv/Scripts/python scripts/stickman_horror_preview.py
This is a renderer test, never a story import, semantic approval or production run.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemas.artifacts import validate_artifact
from tools.character.stickman_preview import build_preview
from tools.tool_registry import ToolRegistry

PROJECT_ID = "p30-stickman-horror-preview"


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def run_tool(registry: ToolRegistry, name: str, inputs: dict):
    tool = registry.get(name)
    if tool is None:
        raise RuntimeError(f"Missing registered tool: {name}")
    result = tool.execute(inputs)
    if not result.success:
        raise RuntimeError(f"{name}: {result.error}")
    return result


def inspect_mp4(registry: ToolRegistry, project: Path, video: dict, timestamps=None) -> dict:
    """Probe and decode the real MP4; sample actual frames and measure audio events."""
    from PIL import Image, ImageDraw, ImageStat
    import numpy as np

    output = project / "preview.mp4"
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                                      "-of", "json", str(output)], check=True, capture_output=True, text=True).stdout)
    stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    audio = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    assert (stream["width"], stream["height"], stream["r_frame_rate"]) == (720, 1280, "30/1")
    # Installed Remotion/FFmpeg emits full-range 4:2:0 (yuvj420p) on this machine.
    assert stream["codec_name"] == "h264" and stream["pix_fmt"] in {"yuv420p", "yuvj420p"}
    assert int(stream["nb_frames"]) == 300 and abs(float(probe["format"]["duration"]) - 10) < 0.1
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(output), "-f", "null", "-"],
                   check=True, capture_output=True)
    # Decode every frame at QA resolution: catch blank frames and frozen output.
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(output), "-an", "-vf", "scale=90:160",
                          "-pix_fmt", "gray", "-f", "rawvideo", "-"], check=True, capture_output=True).stdout
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 160, 90)
    deviations = frames.std(axis=(1, 2))
    assert len(frames) == 300 and float(deviations.min()) > 5, "Blank or missing frame"
    unique = len({hashlib.sha256(f.tobytes()).hexdigest() for f in frames})
    assert unique > 240, "Unexpectedly frozen animation"
    times = timestamps or [0, 1.2, 1.8, 3.2, 5.2, 6.6, 8.4, 9.9]
    sampled = run_tool(registry, "frame_sampler", {"input_path": str(output), "strategy": "timestamps",
                       "timestamps": times, "format": "png", "output_dir": str(project / "frames")})
    assert sampled.data["frame_count"] == len(times)
    sheet = Image.new("RGB", (4 * 270, 2 * 505), "#111820")
    draw = ImageDraw.Draw(sheet)
    for i, frame in enumerate(sampled.data["frames"]):
        with Image.open(frame["path"]) as im:
            assert max(ImageStat.Stat(im).stddev) > 5
            tile = im.convert("RGB").resize((270, 480))
        x, y = i % 4 * 270, i // 4 * 505
        sheet.paste(tile, (x, y))
        draw.text((x + 8, y + 484), f"{frame['timestamp_seconds']:.2f}s", fill="white")
    sheet.save(project / "contact-sheet.png")
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(output), "-vn", "-ac", "1", "-ar", "48000",
                          "-f", "f32le", "-"], check=True, capture_output=True).stdout
    samples = np.frombuffer(pcm, dtype="<f4")
    def rms(start, end):
        window = samples[round(start * 48000):round(end * 48000)]
        return float(np.sqrt(np.mean(window ** 2)))
    events = [{"id": cue["id"], "at_seconds": cue["start_seconds"],
               "rms": rms(cue["start_seconds"], cue["start_seconds"] + min(.15, cue["duration_seconds"]))}
              for cue in video["sfx"] if cue["id"] != "room" and cue.get("role") != "ambience"]
    baseline = rms(.3, .9)
    assert all(event["rms"] > baseline * 2 for event in events), "Missing/mistimed SFX event"
    peak = float(np.abs(samples).max())
    assert 0.01 < peak < .99, "Silent or clipped audio"
    quiet = [{"start": a, "end": b, "rms": rms(a,b)} for a,b in video.get("audio_qa", {}).get("quiet_windows", [])]
    assert all(w["rms"] < baseline * .15 for w in quiet), "Listening pause is not quiet"
    return {"probe": probe, "full_decode": "passed", "decoded_frames": len(frames),
            "minimum_frame_stddev": float(deviations.min()), "unique_qa_frames": unique,
            "audio_codec": audio["codec_name"], "audio_peak": peak, "room_rms": baseline,
            "audio_events": events, "quiet_windows": quiet, "sampled_frames": sampled.data["frames"],
            "contact_sheet": str(project / "contact-sheet.png"),
            "mp4_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def main(*, project_id=PROJECT_ID, builder=build_preview,
         frame_checker="tests/tools/stickman_frame_checks.cjs", qa_timestamps=None, extra_audio=()) -> None:
    os.chdir(ROOT)
    for executable in ("ffmpeg", "ffprobe", "node"):
        if not shutil.which(executable):
            raise RuntimeError(f"Local {executable} required; nothing will be downloaded")
    chrome = Path(os.environ.get("REMOTION_BROWSER_EXECUTABLE", "C:/Program Files/Google/Chrome/Application/chrome.exe"))
    if not chrome.is_file():
        raise RuntimeError("Set REMOTION_BROWSER_EXECUTABLE to installed Chrome; no browser download allowed")
    os.environ["REMOTION_BROWSER_EXECUTABLE"] = str(chrome)
    project = ROOT / "projects" / project_id
    marker = {"project_id": project_id, "technical_renderer_proof": True, "synthetic": True}
    if project.exists() and (not (project / "preview-scope.json").is_file()
                             or json.loads((project / "preview-scope.json").read_text()) != marker):
        raise RuntimeError("Refusing to overwrite an existing project without the matching synthetic marker")
    ignored = subprocess.run(["git", "check-ignore", "--quiet", str(project / "preview.mp4")])
    if ignored.returncode:
        raise RuntimeError("Preview output must be gitignored")
    project.mkdir(parents=True, exist_ok=True)
    save(project / "preview-scope.json", marker)
    decisions = []
    for category, selected, reason in [
        ("render_runtime_selection", "remotion", "User selected existing Remotion route for the technical preview."),
        ("approval_policy", "synthetic-preview-only", "User authorized this synthetic sample, not semantic approval or production of any real story."),
        ("music_source", "local-procedural-sfx", "User authorized locally synthesized scraping, room tone and footfalls; no narration."),
    ]:
        decisions.append({"decision_id": category, "stage": "technical-preview", "category": category,
                          "subject": project_id, "selected": selected, "reason": reason,
                          "options_considered": [{"option_id": selected, "label": selected, "score": 1, "reason": reason}],
                          "user_visible": True, "user_approved": True})
    decisions[0]["options_considered"] += [
        {"option_id": "hyperframes", "label": "HyperFrames", "score": 0,
         "reason": "HTML/SVG runtime available as an alternative.",
         "rejected_because": "User explicitly requested reuse of the existing Remotion pipeline."},
        {"option_id": "ffmpeg", "label": "FFmpeg", "score": 0,
         "reason": "Used for local SFX, decode and frame QA.",
         "rejected_because": "Not the character motion renderer."}]
    log = {"version": "1.0", "project_id": project_id, "decisions": decisions}
    validate_artifact("decision_log", log)
    save(project / "decision_log.json", log)
    registry = ToolRegistry()
    for module in ("tools.audio.procedural_sfx", "tools.character.character_animation",
                   "tools.video.video_compose", "tools.analysis.frame_sampler"):
        registry.discover(module)
    audio = {}
    for recipe, duration in (("room_tone", 10), ("furniture_scrape", .9), ("footstep", .17), *extra_audio):
        target = project / "audio" / f"{recipe}.wav"
        run_tool(registry, "procedural_sfx", {"recipe": recipe, "duration_seconds": duration, "output_path": str(target)})
        audio[recipe] = target
    video, timeline = builder(audio)
    save(project / "story_video.json", video)
    save(project / "action_timeline.json", timeline)
    package = run_tool(registry, "character_rig_renderer", {"story_video": video, "action_timeline": timeline,
                       "workspace_path": str(project / "remotion"), "concurrency": 2})
    save(project / "handoff.json", package.data)
    skeleton = json.loads(subprocess.run(["node", frame_checker,
                                         str(project / "story_video.json")],
                                        check=True, capture_output=True, text=True).stdout)
    save(project / "skeleton-qa.json", skeleton)
    print("Validated synthetic tracks; rendering 300 frames with local Chrome.", flush=True)
    result = run_tool(registry, "video_compose", {"operation": "render", "edit_decisions": package.data["edit_decisions"],
                      "asset_manifest": package.data["asset_manifest"], "output_path": str(project / "preview.mp4")})
    save(project / "render-result.json", result.data)
    report = {"technical_renderer_proof": True, "synthetic": True, "real_story_approved": False,
              "tts_calls": 0, "paid_api_calls": 0, "cost_usd": 0, "production_checkpoints": [],
              "route": ["character_rig_renderer", "video_compose", "remotion"],
              "validation": package.data["validation"], "skeleton": skeleton,
              "media": inspect_mp4(registry, project, video, qa_timestamps),
              "audio_content": {"narration": False, "music": False, "sfx": True},
              "generic_review_caveat": "video_compose's generic audio presence labels do not distinguish narration/music from SFX.",
              "human_visual_review": "pending", "human_audio_review": "pending"}
    save(project / "validation-report.json", report)
    print(json.dumps({"output": str(project / "preview.mp4"), "validation": report["validation"],
                      "decoded_frames": report["media"]["decoded_frames"]}), flush=True)


if __name__ == "__main__":
    main()
