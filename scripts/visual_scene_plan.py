"""Compile an M2.3 canonical visual plan from an existing measured Short (no media generation).

python scripts/visual_scene_plan.py PACKAGE TIMED_MANIFEST VISUAL_BRIEF [--output-dir DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import master_story as ms  # noqa: E402
from lib import visual_scene_plan as vsp  # noqa: E402


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("package", type=Path)
    parser.add_argument("timed_manifest", type=Path)
    parser.add_argument("visual_brief", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--media-root", type=Path, default=ROOT, help="Base for relative paths declared by the timed manifest")
    args = parser.parse_args(argv)
    try:
        package, timed, brief = (ms.load(p) for p in (args.package, args.timed_manifest, args.visual_brief))
        srt_text, input_checks = vsp.verify_timed_files(package, timed, args.media_root)
        plan = vsp.build_plan(package, timed, brief, srt_text)
        report = {**vsp.validate_plan(plan, package, timed, brief, srt_text), "input_files": input_checks}
        output = args.output_dir or ROOT / "projects" / f"{package['package_id'].lower().replace('_', '-')}-visual-plan"
        # Never overwrite any explicitly declared input, including with unusual
        # caller-provided output directories. All validation precedes file writes.
        inputs = {p.resolve() for p in (args.package, args.timed_manifest, args.visual_brief)}
        inputs.update((Path(f["path"]) if Path(f["path"]).is_absolute() else args.media_root / f["path"]).resolve()
                      for f in [timed["narration_track"], timed["subtitles"], *[b["audio"] for b in timed["beats"]]])
        names = ("visual_scene_plan.json", "storyboard.md", "asset_requirements.json", "continuity_review.json", "validation_report.json")
        if any((output / name).resolve() in inputs for name in names):
            raise vsp.VisualScenePlanError("OUTPUT_PATH: would overwrite an input")
        write(output / names[0], plan)
        (output / names[1]).write_text(vsp.storyboard_markdown(plan), encoding="utf-8")
        write(output / names[2], {"source_priority": plan["source_priority"], "media_ready": False,
              "production_breakdown": vsp.asset_breakdown(plan),
              "requirements": [a for scene in plan["scenes"] for a in scene["asset_requirements"]]})
        write(output / names[3], {"status": vsp.PENDING, "rules": plan["canon"]["continuity_rules"],
              "human_rules": plan["continuity_review"], "approvals": plan["approvals"],
              "scenes": [{"scene_id": s["id"], "continuity_rule_ids": s["continuity_rule_ids"],
                          "risk_flags": s["risk_flags"], "review_status": s["review_status"]} for s in plan["scenes"]]})
        # Validate the serialized output, not only an in-memory object.
        vsp.validate_plan(ms.load(output / names[0]), package, timed, brief, srt_text)
        write(output / names[4], report)
    except (OSError, ValueError) as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": report["status"], "output_dir": str(output), "scenes": report["scenes"],
                      "total_seconds": report["total_seconds"], "unresolved_assets": report["unresolved_asset_requirements"],
                      "human_review": vsp.PENDING}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
