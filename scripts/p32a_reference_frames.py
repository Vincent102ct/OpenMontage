"""P3.2A reference frames, environment anchors and legacy-render regression (local Chrome).

Run after scripts/p32a_asset_library_demo.py. Writes only projects/p32a-asset-library.
Legacy projects (P3.0, P3.1 v1/v2) are read, never written: their saved props are
re-rendered with the current sources into this library project and compared with
frames decoded from their original MP4s.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.character import horror_assets as lib  # noqa: E402
from tools.character.asset_library_demo import (POSE_FRAMES, build_environment_still,  # noqa: E402
                                                build_pose_reel)
from tools.character.story_video import validate_story_video  # noqa: E402

LIBRARY = ROOT / "projects" / "p32a-asset-library"
STAGED = ROOT / "remotion-composer" / "projects" / "p32a-story-a-room"
CHARACTERS = ("nora_vale", "victor_hale")
ENVIRONMENTS = ("old_apartment_room", "dark_apartment_corridor")
ENV_STILLS = {"room-unlit": ("old_apartment_room", None, None, False),
              "room-cold_moonlight-window_presence": ("old_apartment_room", "cold_moonlight", ("window", "featureless_figure"), False),
              "room-flickering_interior": ("old_apartment_room", "flickering_interior", None, False),
              "corridor-unlit": ("dark_apartment_corridor", None, None, False),
              "corridor-dim_corridor": ("dark_apartment_corridor", "dim_corridor", None, False),
              "corridor-flickering_interior-off-presence": ("dark_apartment_corridor", "flickering_interior", ("corridor_end", "tall_hooded"), True)}
LEGACY = {"p30-stickman": ("p30-stickman-horror-preview", 156, False),
          "p31-v1": ("p31-cartoon-horror-preview", 156, False),
          "p31-v2-reaction": ("p31-cartoon-horror-preview-v2", 54, False),
          "p31-v2-presence": ("p31-cartoon-horror-preview-v2", 192, False),
          "default-cartoon-16x9": ("p31-cartoon-horror-preview-v2", 156, True)}


def legacy_props(project: str, horizontal: bool) -> dict:
    props = json.loads((ROOT / "projects" / project / "remotion" / "props.json").read_text(encoding="utf-8"))
    props["sfx"], props["narration"] = [], []
    if horizontal:  # Same transformation as tests/tools/stickman_browser.cjs's 16:9 regression.
        del props["viewport"], props["character_skin"]
        props["shots"][0]["camera"] = [[0, 640, 360, 1], [10, 640, 360, 1]]
    return props


def psnr(a: Path, b: Path) -> float:
    out = subprocess.run(["ffmpeg", "-v", "info", "-i", str(a), "-i", str(b), "-lavfi", "[0:v]format=rgb24[x];[1:v]format=rgb24[y];[x][y]psnr",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    value = re.search(r"average:(\S+)", out).group(1)
    return float("inf") if value == "inf" else float(value)


def anchor_overlay(still: Path, env: dict, target: Path) -> None:
    from PIL import Image, ImageDraw
    im = Image.open(still).convert("RGB")
    d = ImageDraw.Draw(im)
    f = env["features"]
    d.line([(0, f["floor_y"]), (1280, f["floor_y"])], fill=(80, 220, 120), width=2)
    x0, x1 = f["walk_range"]
    d.line([(x0, f["floor_y"] + 14), (x1, f["floor_y"] + 14)], fill=(80, 220, 120), width=4)
    for door in f["doors"]:
        r = door["rect"]
        d.rectangle([r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]], outline=(255, 170, 40), width=2)
        hx, hy = door["handle"]
        d.ellipse([hx - 7, hy - 7, hx + 7, hy + 7], outline=(255, 60, 60), width=3)
        d.line([(door["seam"][0], door["seam"][2]), (door["seam"][1], door["seam"][2])], fill=(255, 220, 90), width=3)
    for w in f["windows"]:
        for pane in w["panes"]:
            d.polygon([tuple(p) for p in pane], outline=(90, 200, 255))
    for lamp in f["lamps"]:
        d.ellipse([lamp["x"] - 9, lamp["y"] - 9, lamp["x"] + 9, lamp["y"] + 9], outline=(255, 255, 120), width=3)
    for a in f["presence_anchors"].values():
        for poly in a["clip"]:
            d.polygon([tuple(p) for p in poly], outline=(220, 90, 255))
        d.line([(a["x"] - 10, a["y"]), (a["x"] + 10, a["y"])], fill=(220, 90, 255), width=3)
    for name, (px, py) in f["props"].items():
        d.rectangle([px - 5, py - 5, px + 5, py + 5], outline=(255, 255, 255), width=2)
    im.save(target)


def sheet(paths: list[Path], cols: int, scale: float, target: Path) -> None:
    from PIL import Image
    ims = [Image.open(p).convert("RGB") for p in paths]
    w, h = int(ims[0].width * scale), int(ims[0].height * scale)
    out = Image.new("RGB", (w * cols, h * ((len(ims) + cols - 1) // cols)), "black")
    for i, im in enumerate(ims):
        out.paste(im.resize((w, h)), ((i % cols) * w, (i // cols) * h))
    out.save(target)


def main() -> None:
    os.chdir(ROOT)
    marker = json.loads((LIBRARY / "preview-scope.json").read_text())
    assert marker == {"project_id": "p32a-asset-library", "synthetic": True, "milestone": "P3.2A"}
    # The bundle must use exactly the current sources.
    for src in (ROOT / "tools/character/remotion").glob("*.ts*"):
        assert (STAGED / src.name).read_bytes() == src.read_bytes(), f"Stale staged source {src.name}"
    stills = []
    for c in CHARACTERS:
        for e in ENVIRONMENTS:
            video, timeline = build_pose_reel(c, e)
            validate_story_video(video, timeline)
            for pose, frame in POSE_FRAMES.items():
                stills.append({"name": f"char-{c}-{e}-{pose}", "props": video, "frame": frame})
    for name, (e, preset, presence, off) in ENV_STILLS.items():
        video, timeline = build_environment_still(e, preset, presence=presence, flicker_off=off)
        validate_story_video(video, timeline)
        stills.append({"name": f"env-{name}", "props": video, "frame": 15})
    for name, (project, frame, horizontal) in LEGACY.items():
        stills.append({"name": f"legacy-{name}", "props": legacy_props(project, horizontal), "frame": frame})
    spec = {"entry": str(STAGED / "index.tsx"), "publicDir": "projects/p32a-story-a-room/remotion/public",
            "playback": [{"mp4": "projects/p32a-story-a-room/preview.mp4", "width": 720, "height": 1280},
                         {"mp4": "projects/p32a-story-b-corridor/preview.mp4", "width": 1280, "height": 720}],
            "stills": stills}
    (LIBRARY / "stills.json").write_text(json.dumps(spec), encoding="utf-8")
    subprocess.run(["node", "tests/tools/asset_library_browser.cjs", str(LIBRARY)], check=True)
    out = LIBRARY / "stills"
    # Legacy packages rendered by the current code versus their original MP4 frames.
    legacy = {}
    for name, (project, frame, horizontal) in LEGACY.items():
        still = out / f"legacy-{name}.png"
        if horizontal:
            reference = ROOT / "projects" / project / "horizontal-cartoon.png"
        else:
            reference = LIBRARY / "legacy-reference" / f"{name}.png"
            reference.parent.mkdir(exist_ok=True)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(ROOT / "projects" / project / "preview.mp4"),
                            "-vf", f"select=eq(n\\,{frame})", "-frames:v", "1", str(reference)], check=True)
        legacy[name] = {"project": project, "frame": frame, "reference": str(reference.relative_to(ROOT)),
                        "psnr_db": psnr(still, reference)}
    for e in ENVIRONMENTS:
        short = "room" if e == "old_apartment_room" else "corridor"
        anchor_overlay(out / f"env-{short}-unlit.png", lib.environment(e), LIBRARY / f"anchors-{short}.png")
    for c in CHARACTERS:
        sheet([out / f"char-{c}-{e}-{p}.png" for e in ENVIRONMENTS for p in POSE_FRAMES], 4, .5,
              LIBRARY / f"character-sheet-{c}.png")
    sheet([out / f"env-{n}.png" for n in ENV_STILLS], 2, .5, LIBRARY / "environment-sheet.png")
    sheet([ROOT / "projects/p32a-story-a-room/contact-sheet.png"], 1, 1, LIBRARY / "contact-sheet-story-a.png")
    sheet([ROOT / "projects/p32a-story-b-corridor/contact-sheet.png"], 1, 1, LIBRARY / "contact-sheet-story-b.png")
    sheet([out / f"char-{c}-old_apartment_room-{p}.png" for c in CHARACTERS for p in POSE_FRAMES], 4, .4,
          LIBRARY / "contact-sheet.png")
    (LIBRARY / "legacy-regression.json").write_text(json.dumps(legacy, indent=2), encoding="utf-8")
    print(json.dumps(legacy))


if __name__ == "__main__":
    main()
