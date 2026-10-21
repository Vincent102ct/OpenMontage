"""Post-render checks for an automatically planned story video (local FFmpeg + Pillow).

Measures what can be measured without a human: container/stream facts, full
decode, planned vs actual cuts, loudness, narration audibility and pixel motion
inside every body-action window. Writes keyframes (one per narration beat) and a
contact sheet for the human visual pass. It does not judge taste or acting.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

BODY_ACTIONS = {"walk", "run", "enter", "exit", "approach", "sit", "stand_up", "pick_up", "put_down", "give",
                "open", "close", "knock", "wave", "point", "dress", "operate", "lights_on", "board",
                "vehicle_arrive", "read", "hold"}


def _run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def probe(path: Path) -> dict:
    out = _run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)])
    if out.returncode:
        raise RuntimeError(out.stderr.strip())
    data = json.loads(out.stdout)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    num, den = video["r_frame_rate"].split("/")
    return {"duration_seconds": float(data["format"]["duration"]), "width": video["width"],
            "height": video["height"], "fps": float(num) / float(den), "video_codec": video["codec_name"],
            "pix_fmt": video.get("pix_fmt"), "frames": int(video.get("nb_frames", 0) or 0),
            "audio_codec": audio["codec_name"] if audio else None,
            "audio_sample_rate": int(audio["sample_rate"]) if audio else None,
            "size_bytes": int(data["format"]["size"])}


def frame_at(path: Path, t: float, out: Path, width: int | None = None) -> Path:
    vf = ["-vf", f"scale={width}:-2"] if width else []
    res = _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1", *vf, str(out)])
    if res.returncode or not out.exists():
        raise RuntimeError(f"frame extraction failed at {t:.3f}s: {res.stderr.strip()}")
    return out


def gray_frames(path: Path, t0: float, t1: float, step: float = 0.1) -> list[np.ndarray]:
    """Low-resolution grayscale frames in [t0, t1] for motion measurement."""
    n = max(2, int((t1 - t0) / step) + 1)
    res = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-t", f"{t1 - t0 + 0.05:.3f}", "-i", str(path),
                          "-vf", f"fps={1 / step:.4f},scale=160:90,format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, timeout=300)
    raw = np.frombuffer(res.stdout, dtype=np.uint8)
    frames = [raw[i * 14400:(i + 1) * 14400].reshape(90, 160).astype(np.float32)
              for i in range(len(raw) // 14400)]
    return frames[:n]


def detect_cuts(path: Path, threshold: float = 0.3) -> list[float]:
    res = _run(["ffmpeg", "-v", "info", "-i", str(path), "-vf", f"select='gt(scene,{threshold})',showinfo",
                "-f", "null", "-"])
    return [float(m) for m in re.findall(r"pts_time:([0-9.]+)", res.stderr)]


def loudness(path: Path) -> float | None:
    res = _run(["ffmpeg", "-v", "info", "-i", str(path), "-af", "ebur128", "-f", "null", "-"])
    found = re.findall(r"I:\s+(-?[0-9.]+) LUFS", res.stderr)
    return float(found[-1]) if found else None


def window_volume(path: Path, t0: float, t1: float) -> float | None:
    res = _run(["ffmpeg", "-v", "info", "-ss", f"{t0:.3f}", "-t", f"{max(0.05, t1 - t0):.3f}", "-i", str(path),
                "-vn", "-af", "volumedetect", "-f", "null", "-"])
    m = re.search(r"mean_volume:\s+(-?[0-9.]+|-inf) dB", res.stderr)
    if not m or m.group(1) == "-inf":
        return None
    return float(m.group(1))


def run_qa(video_path: str | Path, story_video: dict, timeline: dict, out_dir: str | Path) -> dict:
    video_path, out_dir = Path(video_path), Path(out_dir)
    keyframes = out_dir / "keyframes"
    keyframes.mkdir(parents=True, exist_ok=True)
    report: dict = {"video": str(video_path), "checks": {}, "issues": [], "warnings": []}
    facts = probe(video_path)
    report["checks"]["probe"] = facts
    planned = story_video["duration_seconds"]
    expected = {"width": 1280, "height": 720, "fps": float(story_video["fps"]), "video_codec": "h264"}
    for key, value in expected.items():
        if facts[key] != value:
            report["issues"].append(f"{key} is {facts[key]}, expected {value}")
    if abs(facts["duration_seconds"] - planned) > 0.2:
        report["issues"].append(f"duration {facts['duration_seconds']:.2f}s differs from plan {planned:.2f}s")
    if not facts["audio_codec"]:
        report["issues"].append("no audio stream")
    decode = _run(["ffmpeg", "-v", "error", "-i", str(video_path), "-f", "null", "-"], timeout=1800)
    report["checks"]["full_decode"] = {"ok": decode.returncode == 0 and not decode.stderr.strip(),
                                       "stderr": decode.stderr.strip()[:500]}
    if not report["checks"]["full_decode"]["ok"]:
        report["issues"].append("full decode reported errors")
    # Planned hard cuts: boundaries between shots that are not faded.
    shots = story_video["shots"]
    hard = []
    for prev, nxt in zip(shots, shots[1:]):
        fades = prev["light"][-1][2] > 0.5 or nxt["light"][0][2] > 0.5
        if not fades:
            hard.append(nxt["start_seconds"])
    cuts = detect_cuts(video_path)
    matched = [c for c in hard if any(abs(c - d) < 0.1 for d in cuts)]
    extra = [d for d in cuts if not any(abs(d - s["start_seconds"]) < 0.1 for s in shots)]
    report["checks"]["cuts"] = {"planned_hard_cuts": len(hard), "detected": len(cuts), "matched": len(matched),
                                "unplanned": [round(x, 2) for x in extra]}
    if extra:
        report["warnings"].append(f"{len(extra)} visual jumps outside shot boundaries: {extra[:5]}")
    # Audio: integrated loudness, narration windows vs. gaps.
    lufs = loudness(video_path)
    narration = story_video["narration"]
    voiced = [window_volume(video_path, n["start_seconds"] + 0.05, n["end_seconds"] - 0.05) for n in narration]
    silent_beats = [n["id"] for n, v in zip(narration, voiced) if v is None or v < -45]
    report["checks"]["audio"] = {"integrated_lufs": lufs,
                                 "narration_mean_db_median": float(np.median([v for v in voiced if v is not None]))
                                 if any(v is not None for v in voiced) else None,
                                 "near_silent_narration": silent_beats}
    if silent_beats:
        report["issues"].append(f"near-silent narration windows: {silent_beats}")
    # Motion inside body-action windows (mean absolute luma change per 0.1 s, 160x90 gray).
    motion = []
    for scene in timeline["scenes"]:
        for act in scene["actions"]:
            if act["action"] not in BODY_ACTIONS or act["duration_seconds"] < 0.3:
                continue
            frames = gray_frames(video_path, act["at_seconds"], act["at_seconds"] + act["duration_seconds"])
            if len(frames) < 2:
                continue
            diffs = [float(np.mean(np.abs(b - a))) for a, b in zip(frames, frames[1:])]
            motion.append({"scene": scene["scene_id"], "action": act["action"], "character": act["character_id"],
                           "at": round(act["at_seconds"], 2), "mean_delta": round(float(np.mean(diffs)), 3),
                           "max_delta": round(float(np.max(diffs)), 3)})
    still = [m for m in motion if m["max_delta"] < 0.15]
    report["checks"]["action_motion"] = {"windows": len(motion), "without_visible_change": still,
                                        "median_mean_delta": float(np.median([m["mean_delta"] for m in motion]))
                                        if motion else None, "per_action": motion}
    if still:
        report["warnings"].append(f"{len(still)} body-action windows show no pixel change (possibly off-camera)")
    # Keyframes: middle of each narration beat, plus a contact sheet.
    paths = []
    for n in narration:
        t = (n["start_seconds"] + n["end_seconds"]) / 2
        paths.append(frame_at(video_path, t, keyframes / f"{n['id']}.png", width=640))
    thumbs = [Image.open(p).convert("RGB") for p in paths]
    if thumbs:
        cols = 4
        w, h = thumbs[0].size
        sheet = Image.new("RGB", (cols * w, ((len(thumbs) + cols - 1) // cols) * h), "black")
        for i, im in enumerate(thumbs):
            sheet.paste(im, ((i % cols) * w, (i // cols) * h))
        sheet_path = out_dir / "contact_sheet.jpg"
        sheet.save(sheet_path, quality=85)
        report["contact_sheet"] = str(sheet_path)
    report["keyframes"] = [str(p) for p in paths]
    report["status"] = "fail" if report["issues"] else "pass"
    return report
