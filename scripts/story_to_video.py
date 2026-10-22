"""One command: story text file -> analysed, planned, narrated, animated MP4.

    python scripts/story_to_video.py path/to/story.md [--analyzer auto|rules|ollama]

The repository is agent-driven; this script is the single-command entry point the
user asked for. It only calls registered tools in stage order and writes their
canonical artifacts under projects/<id>/ (analysis, plan, timeline, edit
decisions, render report, QA). No paid API, no network except an optional local
Ollama endpoint. Narration uses an installed, language-matched offline voice.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import unicodedata
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemas.artifacts import validate_artifact  # noqa: E402
from tools.story.story_analyzer import DEFAULT_MODEL, DEFAULT_OLLAMA  # noqa: E402
from tools.story.story_qa import run_qa  # noqa: E402
from tools.tool_registry import registry  # noqa: E402
from tools.audio.local_narration import select_local_voice, narration_key, file_hash  # noqa: E402
from tools.audio.local_wav import wav_duration  # noqa: E402


def slug(text: str) -> str:
    base = unicodedata.normalize("NFKD", text.replace("\u0111", "d").replace("\u0110", "D"))
    base = "".join(c for c in base if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:48] or "story"


def log(step: str, detail: str = "") -> None:
    print(f"[story-to-video] {step}{': ' + detail if detail else ''}", flush=True)


def tool(name: str):
    registry.ensure_discovered()
    t = registry.get(name)
    if t is None:
        raise SystemExit(f"Tool {name} is not registered")
    return t


def write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def narrate(analysis: dict, audio_dir: Path, selection: dict) -> dict:
    """Cache by provider/model/settings/text and verify the actual WAV on every run."""
    manifest_path = audio_dir / "narration_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    tts = tool(selection["tool"])
    out = {}
    for beat in analysis["beats"]:
        key = narration_key(selection, beat["text"])
        wav = audio_dir / f"{beat['id']}.wav"
        entry = manifest.get(beat["id"])
        cached = False
        if entry and entry.get("key") == key and wav.exists():
            try:
                cached = file_hash(wav) == entry.get("sha256")
                if cached:
                    wav_duration(wav)
            except (OSError, ValueError, EOFError, wave.Error):
                cached = False
        if not cached:
            res = tts.execute({**selection["settings"], "text": beat["text"], "output_path": str(wav)})
            if not res.success:
                raise SystemExit(f"Narration failed for {beat['id']}: {res.error}")
        try:
            duration = wav_duration(wav)
        except (OSError, ValueError, EOFError, wave.Error) as exc:
            raise SystemExit(f"Invalid narration WAV for {beat['id']}: {exc}") from exc
        entry = {"key": key, "duration_seconds": duration, "sha256": file_hash(wav), **selection}
        manifest[beat["id"]] = entry
        write(manifest_path, manifest)
        out[beat["id"]] = {"path": str(wav), "duration_seconds": duration}
    return out


def render_sfx(video: dict, sfx_dir: Path) -> None:
    gen = tool("procedural_sfx")
    cues, cache = [], {}
    for i, cue in enumerate(video["sfx"]):
        duration = round(max(0.05, cue["duration"]), 3)
        fade = min(cue.get("fade", 0.0), duration / 2)
        name = f"{cue['recipe']}-{duration:.3f}-{fade:.2f}.wav"
        path = sfx_dir / name
        if name not in cache and not path.exists():
            res = gen.execute({"recipe": cue["recipe"], "duration_seconds": duration, "fade_seconds": fade,
                               "output_path": str(path)})
            if not res.success:
                raise SystemExit(f"SFX {cue['recipe']} failed: {res.error}")
        cache[name] = path
        cues.append({"id": f"{cue['recipe']}-{i:03d}", "path": str(path), "start_seconds": round(cue["t"], 4),
                     "duration_seconds": duration, "volume": cue["volume"]})
    video["sfx"] = cues


def subtitles(video: dict, path: Path) -> None:
    segs = [{"text": n["text"], "start": n["start_seconds"], "end": n["end_seconds"]} for n in video["narration"]]
    res = tool("subtitle_gen").execute({"segments": segs, "format": "srt", "output_path": str(path),
                                        "max_words_per_cue": 1, "max_chars_per_line": 1})
    if not res.success:
        raise SystemExit(f"Subtitles failed: {res.error}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Story text file -> local animated MP4")
    parser.add_argument("story", type=Path, help="UTF-8 text/markdown; optional '# Title' first line")
    parser.add_argument("--project-id")
    parser.add_argument("--analyzer", choices=["auto", "rules", "ollama"], default="auto")
    parser.add_argument("--ollama-endpoint", default=DEFAULT_OLLAMA)
    parser.add_argument("--ollama-model", default=DEFAULT_MODEL)
    parser.add_argument("--tts-provider", choices=["auto", "windows_sapi", "macos_say", "piper"], default="auto")
    parser.add_argument("--voice", help="exact installed native voice; must match story language")
    parser.add_argument("--rate", type=float, help="provider units: SAPI -10..10; macOS 80..300 WPM; Piper length_scale 0.25..4")
    parser.add_argument("--piper-model", default=os.environ.get("OPENMONTAGE_PIPER_MODEL"), help="local .onnx + adjacent .onnx.json")
    parser.add_argument("--draft", action="store_true", help="render at half resolution for a quick look")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--no-render", action="store_true", help="synthesize real narration and validate package; skip browser/MP4")
    mode.add_argument("--dry-run", action="store_true", help="analyze only; no TTS, SFX, timeline, package or render")
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()
    started = time.monotonic()
    story_path = args.story.resolve()
    if not story_path.is_file():
        raise SystemExit(f"Story file not found: {story_path}")
    project_id = args.project_id or f"{slug(story_path.stem)}-auto"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", project_id):
        parser.error("--project-id must contain only letters, digits, underscores or hyphens")
    if args.dry_run:
        project_id += "-dry-run"
    project = ROOT / "projects" / project_id
    artifacts, audio, renders = project / "artifacts", project / "assets/audio", project / "renders"
    for d in (artifacts, audio / "sfx", renders):
        d.mkdir(parents=True, exist_ok=True)
    shutil.copy2(story_path, artifacts / "source_story.md")
    timings: dict[str, float] = {}

    def lap(name: str, since: float) -> float:
        timings[name] = round(time.monotonic() - since, 2)
        return time.monotonic()

    t = time.monotonic()
    log("analyze", f"{story_path.name} (analyzer={args.analyzer})")
    res = tool("story_analyzer").execute({"story_path": str(artifacts / "source_story.md"), "backend": args.analyzer,
                                          "endpoint": args.ollama_endpoint, "model": args.ollama_model,
                                          "output_path": str(artifacts / "story_analysis.json"),
                                          "llm_raw_path": str(artifacts / "llm_labels_raw.json")})
    if not res.success:
        raise SystemExit(res.error)
    analysis = res.data["story_analysis"]
    log("analysis", f"{len(analysis['beats'])} beats, characters={[c['id'] for c in analysis['characters']]}, "
                    f"locations={[x['id'] for x in analysis['locations']]}, backend={analysis['analyzer']['backend']}")
    t = lap("analyze", t)

    if args.dry_run:
        write(artifacts / "dry_run_report.json", {"mode": "analysis-only", "language": analysis["language"],
              "beats": len(analysis["beats"]), "timing": "not computed; measured narration required"})
        log("done (dry run)", f"{project}; no timeline or narration generated")
        return
    try:
        selection = select_local_voice(tool, analysis["language"], provider=args.tts_provider,
                                       voice=args.voice, rate=args.rate, piper_model=args.piper_model)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    write(artifacts / "tts_selection.json", selection)
    log("narrate", json.dumps(selection, ensure_ascii=False))
    narration = narrate(analysis, audio, selection)
    t = lap("narrate", t)

    log("plan")
    res = tool("story_planner").execute({"story_analysis": analysis, "narration": narration})
    if not res.success:
        raise SystemExit(res.error)
    video, timeline = res.data["story_video"], res.data["action_timeline"]
    render_sfx(video, audio / "sfx")
    write(artifacts / "story_video.json", video)
    write(artifacts / "action_timeline.json", timeline)
    log("plan", f"{video['duration_seconds']:.1f}s, {len(video['shots'])} shots, "
                f"{sum(len(s['actions']) for s in timeline['scenes'])} actions, {len(video['sfx'])} sound cues")
    t = lap("plan", t)

    log("package + validate")
    res = tool("character_rig_renderer").execute({"action_timeline": timeline, "story_video": video,
                                                  "workspace_path": str(project / "composition"),
                                                  "concurrency": args.concurrency,
                                                  **({"scale": 0.5} if args.draft else {})})
    if not res.success:
        raise SystemExit(res.error)
    edit, assets = res.data["edit_decisions"], res.data["asset_manifest"]
    write(artifacts / "edit_decisions.json", edit)
    write(artifacts / "asset_manifest.json", assets)
    validate_artifact("edit_decisions", edit)
    validate_artifact("asset_manifest", assets)
    log("validated", json.dumps(res.data["validation"]))
    validation = res.data["validation"]
    subtitles(video, project / "assets/subtitles.srt")
    t = lap("package", t)
    if args.no_render:
        log("done (no render)", str(project))
        return

    output = renders / ("draft.mp4" if args.draft else "final.mp4")
    log("render", f"Remotion via video_compose -> {output.relative_to(ROOT)}")
    res = tool("video_compose").execute({"operation": "render", "edit_decisions": edit, "asset_manifest": assets,
                                         "output_path": str(output),
                                         "script_text": " ".join(n["text"] for n in video["narration"])})
    write(artifacts / "compose_tool_result.json", {"success": res.success, "error": res.error, "data": res.data})
    if not res.success:
        raise SystemExit(f"Render failed: {res.error}")
    t = lap("render", t)

    log("qa")
    qa = run_qa(output, video, timeline, renders)
    write(artifacts / "qa_report.json", qa)
    t = lap("qa", t)
    facts = qa["checks"]["probe"]
    tts_settings = selection["settings"]
    voice_label = (f"{tts_settings.get('voice', tts_settings.get('model'))} "
                   f"{tts_settings['language_code']} rate "
                   f"{tts_settings.get('rate', tts_settings.get('length_scale'))}")
    report = {"version": "1.0",
              "outputs": [{"path": str(output), "format": "mp4", "codec": facts["video_codec"],
                           "audio_codec": facts["audio_codec"], "resolution": f"{facts['width']}x{facts['height']}",
                           "fps": facts["fps"], "duration_seconds": facts["duration_seconds"],
                           "file_size_bytes": facts["size_bytes"]}],
              "render_time_seconds": timings["render"], "render_grammar": "animation-first",
              "warnings": qa["warnings"] + qa["issues"] + video["planner_notes"],
              "verification_notes": [f"pre-render validator: {validation}; QA status {qa['status']}",
                                     "Technical QA only; pronunciation and listening review pending."],
              "metadata": {"pipeline": "story-to-video M1", "analyzer": analysis["analyzer"],
                           "voice": voice_label, "tts": selection, "stage_seconds": timings,
                           "total_seconds": round(time.monotonic() - started, 1), "API_cost_usd": 0,
                           "human_visual_approved": False, "human_listening_approved": False}}
    validate_artifact("render_report", report)
    write(artifacts / "render_report.json", report)
    log("done", f"{output} ({facts['duration_seconds']:.1f}s, QA {qa['status']}, "
                f"{len(qa['warnings'])} warnings) in {report['metadata']['total_seconds']}s")
    if qa["status"] != "pass":
        raise SystemExit(f"QA failed; see {artifacts / 'qa_report.json'}")


if __name__ == "__main__":
    main()
