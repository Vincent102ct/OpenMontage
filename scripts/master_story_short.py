"""Master Story Package -> narrated, timed Short review package (no images/video).

    python scripts/master_story_short.py examples/master-story/<story>/master_story.json [--project-id ID]

Flow: validate package -> resolve Short -> check narration language -> select an
installed offline voice for that language (existing selector: Korva first for
Vietnamese when installed, native/Piper otherwise) -> synthesize each master
segment verbatim (existing cached narrate()) -> timeline from PCM sample counts ->
SRT (existing subtitle_gen) -> quality gates -> timed manifest + report under
projects/<id>/. Story Analyzer is not used, so canonical IDs are never lost.
Exit code 1 when any automatic gate fails; factual/publication approval is never set.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jsonschema  # noqa: E402

from lib import master_story as ms  # noqa: E402
from lib import master_story_short as mss  # noqa: E402
from scripts import story_to_video as stv  # noqa: E402
from tools.audio.local_narration import language_matches, select_local_voice  # noqa: E402

MANIFEST_SCHEMA = ROOT / "schemas/story/timed_format_manifest.schema.json"


def log(step: str, detail: str = "") -> None:
    print(f"[master-story-short] {step}{': ' + detail if detail else ''}", flush=True)


def write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def build(args) -> int:
    started = time.monotonic()
    package = ms.load(args.package)
    try:
        ms.validate_package(package)
        language = mss.narration_language(package)
    except (ms.MasterStoryError, mss.ShortNarrationError) as exc:
        raise SystemExit("Package rejected:\n  " + "\n  ".join(exc.problems)) from exc
    project_id = args.project_id or f"{package['package_id'].lower().replace('_', '-')}-short"
    project = stv.ROOT / "projects" / project_id
    artifacts, audio = project / "artifacts", project / "assets/audio"
    beats = mss.canonical_beats(package, "short")
    view = ms.resolve_format(package, "short")
    write(artifacts / "short_resolved.json", {**view, "beats": beats})
    log("resolved", f"{package['package_id']}@{package['package_version']} short: {len(beats)} segments, "
                    f"{len(view['claims'])} claims, {len(view['sources'])} sources, language {language}")

    try:
        selection = select_local_voice(stv.tool, language, provider=args.tts_provider, voice=args.voice,
                                       rate=args.rate, piper_model=args.piper_model,
                                       korva_python=args.korva_python, korva_assets=args.korva_assets)
    except ValueError as exc:
        raise SystemExit(f"Blocked: no verified offline voice for {language!r}. {exc}") from exc
    if not language_matches(selection["settings"]["language_code"], language):
        raise SystemExit(f"Blocked: selected voice language {selection['settings']['language_code']} "
                         f"does not match narration language {language}")
    write(artifacts / "tts_selection.json", selection)
    log("narrate", f"{selection['provider']} {selection['settings'].get('voice', selection['settings'].get('model'))}")
    t = time.monotonic()
    narration = stv.narrate({"beats": [{"id": b["segment_id"], "text": b["text"]} for b in beats]}, audio, selection)
    narrate_seconds = round(time.monotonic() - t, 2)

    timing = {"lead_in_seconds": args.lead_in, "gap_seconds": args.gap, "tail_seconds": args.tail}
    timed = mss.build_timeline(beats, {k: Path(v["path"]) for k, v in narration.items()}, timing)
    track = audio / "short_narration.wav"
    mss.write_concatenated_wav(timed, track)
    srt = project / "assets/subtitles.srt"
    result = stv.tool("subtitle_gen").execute({"segments": mss.subtitle_segments(timed), "format": "srt",
                                               "output_path": str(srt), "max_words_per_cue": 1,
                                               "max_chars_per_line": 1})
    if not result.success:
        raise SystemExit(f"Subtitles failed: {result.error}")
    srt_text = srt.read_text(encoding="utf-8")
    gates = mss.quality_gates(package, timed, srt_text, track=track)

    manifest = {"schema_version": "1.0", "package_id": package["package_id"],
                "package_version": package["package_version"], "format": "short", "language": language,
                "aspect_ratio": package["formats"]["short"]["aspect_ratio"], "tts": selection,
                "timing_policy": timed["timing_policy"], "speech_seconds": timed["speech_seconds"],
                "total_seconds": timed["total_seconds"], "beats": timed["beats"],
                "narration_track": {"path": str(track), "sha256": mss.sha256(track)},
                "subtitles": {"path": str(srt), "sha256": mss.sha256(srt)},
                "approvals": {"factual": "pending_human_review", "publication": "pending_human_review",
                              "listening": "pending_human_review"}}
    jsonschema.validate(manifest, json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8")))
    write(artifacts / "short_timed_manifest.json", manifest)
    passed = all(g["pass"] for g in gates.values())
    used_sources = {s for b in timed["beats"] for s in b["source_ids"]}
    report = {"status": "technical_pass" if passed else "technical_fail", "gates": gates,
              "narration": stv.narration_summary(audio, [{"id": b["segment_id"]} for b in beats]),
              "narrate_stage_seconds": narrate_seconds, "total_run_seconds": round(time.monotonic() - started, 2),
              "source_scope": {"package_sources": len(package["sources"]), "short_sources": sorted(used_sources),
                               "package_sources_not_in_short": sorted({s["id"] for s in package["sources"]} - used_sources)},
              "approvals": manifest["approvals"],
              "notes": ["Timing is measured from PCM samples; package estimated_seconds are not used.",
                        "Subtitle sentence times are split by character share inside each measured segment window, "
                        "not word alignment.",
                        "ASR, if run, is a listening aid only."]}
    write(artifacts / "short_report.json", report)
    duration = gates["duration_target"]
    log("done" if passed else "gates failed",
        f"{project} total {duration['total_seconds']}s (speech {duration['speech_seconds']}s, target "
        f"{duration['target'][0]}-{duration['target'][1]}s); failed gates: "
        f"{[k for k, g in gates.items() if not g['pass']] or 'none'}")
    return 0 if passed else 1


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Master Story Package -> timed Short narration package")
    parser.add_argument("package", type=Path)
    parser.add_argument("--project-id")
    parser.add_argument("--tts-provider", choices=["auto", "korva", "windows_sapi", "macos_say", "piper"], default="auto")
    parser.add_argument("--voice")
    parser.add_argument("--rate", type=float)
    parser.add_argument("--piper-model", default=os.environ.get("OPENMONTAGE_PIPER_MODEL"))
    parser.add_argument("--korva-python")
    parser.add_argument("--korva-assets")
    parser.add_argument("--lead-in", type=float, default=mss.TIMING_DEFAULTS["lead_in_seconds"])
    parser.add_argument("--gap", type=float, default=mss.TIMING_DEFAULTS["gap_seconds"])
    parser.add_argument("--tail", type=float, default=mss.TIMING_DEFAULTS["tail_seconds"])
    return build(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
