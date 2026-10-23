"""Validation and Remotion handoff for automatically planned `story_video` packages.

Same contract style as `story_motion.validate_episode`, but generic (any locations,
actors and items). Fails closed on anything that would render a broken frame:
coverage gaps, camera outside the artwork, unreachable limbs (motion.ts would
throw), items leaving the holding hand, narration that differs from the source or
is not linked to an overlapping action.
"""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

from schemas.artifacts import validate_artifact
from tools.base_tool import ToolResult

ARM, LEG = (65, 68), (57, 58)
LIMBS = ("root", "left_hand", "right_hand", "left_foot", "right_foot")
GROUND = 620
# Staging: torsos overlapping while both stand still, or while one walks through the other
# on the same depth lane, is a staging error (passing behind on a deeper lane is fine).
MIN_SEPARATION, STILL_SPEED, MAX_STILL_OVERLAP = 62.0, 25.0, 0.3
# Face occlusion: item boxes relative to the grip (must match StoryVideo.tsx drawings).
# Actor.tsx draws the head 1.18x about (x + 10, y - 161): the face spans about x - 25 .. x + 57.
FACE_DX, FACE_RADIUS, MAX_OCCLUSION = 16.0, 38.0, 0.25
ITEM_BOX = {  # kind -> (held box, resting box) as (x0, y0, x1, y1)
    "umbrella": ((-9, 0, 9, 118), (-9, 0, 9, 118)), "bag": ((-23, 8, 23, 50), (-23, 8, 23, 50)),
    "phone": ((-6, -10, 6, 10), (-6, -10, 6, 10)), "letter": ((-13, -17, 13, 17), (-18, -6, 18, 0)),
    "book": ((-22, -18, 22, 18), (-18, -5, 18, 5)), "newspaper": ((-30, -22, 30, 26), (-22, -5, 22, 0)),
    "cup": ((-17, -17, 32, 20), (-17, -17, 32, 20)), "bread": ((-24, -11, 24, 11), (-24, -11, 24, 11)),
    "coin": ((-7, -7, 7, 7), (-8, -3, 8, 3)), "key": ((-10, -5, 12, 5), (-10, -5, 12, 5)),
    "box": ((-20, -17, 20, 17), (-20, -17, 20, 17)), "bottle": ((-12, -25, 12, 28), (-12, -25, 12, 28)),
    "tray": ((-36, -14, 36, 4), (-36, -14, 36, 4)), "flower": ((-15, -21, 15, 30), (-15, -21, 15, 30)),
}
UMBRELLA_OPEN_BOX = (-92, -230, 92, -124)
UMBRELLA_SHAFT_BOX = (-3, -168, 3, 0)


def _sample(keys, t):
    if t <= keys[0][0]:
        return list(keys[0][1:])
    for a, b in zip(keys, keys[1:]):
        if t <= b[0]:
            u = (t - a[0]) / (b[0] - a[0])
            u = u * u * (3 - 2 * u)
            return [x + (y - x) * u for x, y in zip(a[1:], b[1:])]
    return list(keys[-1][1:])


def _step(keys, t):
    value = keys[0][1]
    for k in keys:
        if k[0] <= t + 1e-9:
            value = k[1]
    return value


def _check_keys(name, keys, width, length):
    previous = -1.0
    for key in keys:
        if len(key) != width or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in key):
            raise ValueError(f"Invalid numeric key in {name}")
        if not previous < key[0] <= length + 1e-6:
            raise ValueError(f"Unordered/out-of-range keys in {name}")
        previous = key[0]
    if not keys or abs(keys[0][0]) > 1e-9 or abs(keys[-1][0] - length) > 1e-6:
        raise ValueError(f"{name} must cover [0, {length:.3f}]")


def actor_limb_distances(actor: dict, t: float) -> dict[str, float]:
    """Python twin of StoryVideo.tsx actorState(): world tracks are mapped back to the rig
    (scaled about the ground line), then motion.ts limb spans in the mirrored local frame."""
    s = actor.get("scale", 1.0)

    def body(p):
        return [p[0] / s, GROUND + (p[1] - GROUND) / s]

    root = body(_sample(actor["root"], t))
    facing = -1 if _step(actor["facing_keys"], t) < 0 else 1

    def local(p):
        p = body(p)
        return p if facing > 0 else [2 * root[0] - p[0], p[1]]

    posture = _sample(actor["posture"], t) if "posture" in actor else [5, -99, 10, -160]
    shoulder = [root[0] + posture[0], root[1] + posture[1]]
    out = {}
    for hand in ("left_hand", "right_hand"):
        out[hand] = math.dist(shoulder, local(_sample(actor[hand], t)))
    for foot in ("left_foot", "right_foot"):
        out[foot] = math.dist(root, local(_sample(actor[foot], t)))
    return out


def head_center(actor: dict, t: float) -> tuple[float, float, float]:
    """World centre and radius of the drawn face (Actor.tsx head at x + 10, y - 161, scaled 1.18)."""
    s = actor.get("scale", 1.0)
    root = _sample(actor["root"], t)
    facing = -1 if _step(actor["facing_keys"], t) < 0 else 1
    return root[0] + facing * FACE_DX * s, root[1] - 161 * s, FACE_RADIUS * s


def item_boxes(item: dict, t: float) -> list[tuple[float, float, float, float]]:
    x, y, rot = _sample(item["track"], t)
    if abs(rot) > 15:
        return []
    if item["kind"] == "umbrella" and _sample(item.get("open", [[0, 0]]), t)[0] > 0.5:
        boxes = [UMBRELLA_OPEN_BOX, UMBRELLA_SHAFT_BOX]  # the shaft counts too
    else:
        held = _step(item.get("held", [[0, 0]]), t) > 0
        boxes = [ITEM_BOX.get(item["kind"], ((-12, -12, 12, 12),) * 2)[0 if held else 1]]
    return [(x + b[0], y + b[1], x + b[2], y + b[3]) for b in boxes]


def _box_hits_circle(box, cx, cy, r) -> bool:
    nx, ny = min(max(cx, box[0]), box[2]), min(max(cy, box[1]), box[3])
    return (nx - cx) ** 2 + (ny - cy) ** 2 < r * r


def _visible(actor: dict, t: float) -> bool:
    return _sample(actor["opacity"], t)[0] >= 0.5 and _step(actor.get("layer", [[0, 0]]), t) == 0


def _reachable(name: str, d: float) -> bool:
    upper, lower = ARM if name.endswith("hand") else LEG
    return abs(upper - lower) + 0.001 < d < upper + lower - 0.001


GEOMETRY_KEYS = {"version", "preset", "revision", "negative_fill", "pools", "beams", "lamps", "seams", "haze", "presence"}
DRIVERS = {"constant", "spill", "flicker"}


def _check_geometry(name: str, g: dict, horror: dict) -> None:
    """P3.2A location lighting/presence geometry (CinematicHorror.tsx HorrorOverlay); fail closed."""
    def fail(why):
        raise ValueError(f"{name}.cinematic: {why}")

    def num(v, lo, hi, what):
        if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
            fail(f"{what} must be a finite number in [{lo}, {hi}]")

    def point(q, what):
        if not isinstance(q, list) or len(q) != 2:
            fail(f"{what} must be [x, y]")
        num(q[0], 0, 1280, f"{what}.x")
        num(q[1], 0, 720, f"{what}.y")

    def color(v, what):
        if not isinstance(v, str) or len(v) != 7 or v[0] != "#" or any(c not in "0123456789abcdef" for c in v[1:]):
            fail(f"{what} must be #rrggbb")

    def driver(d, what):
        if d not in DRIVERS:
            fail(f"{what}: unknown driver {d!r}")
        if d == "flicker" and "flicker" not in horror:
            fail(f"{what} uses the flicker driver without a horror.flicker track")

    if not isinstance(g, dict) or set(g) - GEOMETRY_KEYS or g.get("version") != 1:
        fail("unsupported geometry version or keys")
    if not isinstance(g.get("preset"), str) or type(g.get("revision")) is not int:
        fail("preset id and integer revision required")
    color(g["negative_fill"]["color"], "negative_fill.color")
    num(g["negative_fill"]["opacity"], 0, 1, "negative_fill.opacity")
    for i, q in enumerate(g["pools"]):
        point([q["cx"], q["cy"]], f"pools[{i}]")
        num(q["rx"], 1, 1280, f"pools[{i}].rx")
        num(q["ry"], 1, 720, f"pools[{i}].ry")
        num(q["strength"], 0, 1, f"pools[{i}].strength")
        driver(q["driver"], f"pools[{i}]")
    for i, b in enumerate(g["beams"]):
        if len(b["points"]) != 4:
            fail(f"beams[{i}] needs four points")
        for j, q in enumerate(b["points"]):
            point(q, f"beams[{i}].points[{j}]")
        color(b["color"], f"beams[{i}].color")
        num(b["opacity"], 0, 1, f"beams[{i}].opacity")
        driver(b["driver"], f"beams[{i}]")
    for i, lamp in enumerate(g["lamps"]):
        point([lamp["x"], lamp["y"]], f"lamps[{i}]")
        num(lamp["r"], 1, 400, f"lamps[{i}].r")
        color(lamp["color"], f"lamps[{i}].color")
        driver(lamp["driver"], f"lamps[{i}]")
    for i, seam in enumerate(g["seams"]):
        point([seam["x0"], seam["y"]], f"seams[{i}]")
        point([seam["x1"], seam["y"]], f"seams[{i}]")
        color(seam["color"], f"seams[{i}].color")
        driver(seam["driver"], f"seams[{i}]")
    if "haze" in g:
        point([g["haze"]["cx"], g["haze"]["cy"]], "haze")
        color(g["haze"]["color"], "haze.color")
        num(g["haze"]["opacity"], 0, 1, "haze.opacity")
    if "presence" in g:
        pr = g["presence"]
        if not isinstance(pr.get("path"), str) or not pr["path"].startswith("M "):
            fail("presence.path must be an SVG path")
        color(pr["color"], "presence.color")
        point([pr["x"], pr["y"]], "presence")
        num(pr["scale"], .1, 10, "presence.scale")
        if not pr["clip"] or any(len(polygon) < 3 for polygon in pr["clip"]):
            fail("presence.clip needs polygons of at least three points")
        for polygon in pr["clip"]:
            for q in polygon:
                point(q, "presence.clip")


def source_paragraphs(path: str) -> list[str]:
    from tools.story.story_analyzer import load_story
    return load_story(path)["paragraphs"]


def validate_story_video(video: dict, timeline: dict) -> dict:
    """Raise ValueError on any contract break; return counters for the QA report."""
    # Opt-in only: old packages never import or depend on the reusable registry.
    if "asset_binding" in video:
        from tools.character.horror_assets import resolve_binding

        resolved = resolve_binding(video["asset_binding"])
        if video.get("character_skin") != "cartoon_horror" or video["locations"] != resolved["locations"]:
            raise ValueError("Asset binding: skin/locations differ from pinned environment and geometry")
        for shot in video["shots"]:
            for actor in shot["actors"]:
                if actor["id"] not in resolved["cast"] or actor["look"] != resolved["cast"][actor["id"]]:
                    raise ValueError(f"Asset binding: {actor['id']} appearance differs from pinned character revision")
    validate_artifact("action_timeline", timeline)
    fps = video["fps"]
    duration = video["duration_seconds"]
    viewport = video.get("viewport", {"width": 1280, "height": 720})
    if (not isinstance(viewport, dict) or set(viewport) != {"width", "height"} or any(type(v) is not int or v < 2 or v > 4096 or v % 2
                                                 for v in viewport.values())):
        raise ValueError("Viewport requires even integer width/height in [2, 4096]")
    if video.get("character_skin", "cartoon") not in {"cartoon", "stickman_horror", "cartoon_horror"}:
        raise ValueError("Unknown character skin")
    half_width = viewport["width"] * 720 / viewport["height"] / 2
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Positive finite duration required")
    if "horror" in video:
        if video.get("character_skin") != "cartoon_horror":
            raise ValueError("Cinematic horror requires the cartoon character skin")
        for name, width in (("presence", 3), ("spill", 2), ("flicker", 2)):
            if name == "flicker" and name not in video["horror"]:
                continue
            _check_keys(f"horror.{name}", video["horror"][name], width, duration)
            if any(not 0 <= key[1] <= 1 for key in video["horror"][name]):
                raise ValueError(f"horror.{name} intensity must be in [0,1]")
    for name, location in video["locations"].items():
        if "cinematic" in location:
            if "horror" not in video:
                raise ValueError(f"{name}: cinematic geometry requires horror tracks")
            _check_geometry(name, location["cinematic"], video["horror"])
    shots = video["shots"]
    if not shots or shots[0]["start_seconds"] != 0 or abs(shots[-1]["end_seconds"] - duration) > 1e-6:
        raise ValueError("Shots must cover the whole video")
    for prev, shot in zip(shots, shots[1:]):
        if abs(prev["end_seconds"] - shot["start_seconds"]) > 1e-9:
            raise ValueError(f"Gap or overlap before shot {shot['id']}")
    if len({s["id"] for s in shots}) != len(shots):
        raise ValueError("Duplicate shot IDs")
    frames_checked = 0
    for shot in shots:
        sid = shot["id"]
        length = shot["end_seconds"] - shot["start_seconds"]
        if length <= 0:
            raise ValueError(f"Empty shot {sid}")
        if abs(shot["start_seconds"] * fps - round(shot["start_seconds"] * fps)) > 1e-6:
            raise ValueError(f"{sid}: cut not on the frame grid")
        _check_keys(f"{sid}.camera", shot["camera"], 4, length)
        _check_keys(f"{sid}.light", shot["light"], 3, length)
        _check_keys(f"{sid}.door", shot["door"], 2, length)
        if shot["view"] == "world" and shot["location"] not in video["locations"]:
            raise ValueError(f"{sid}: unknown location {shot['location']}")
        for actor in shot["actors"]:
            name = f"{sid}.{actor['id']}"
            for limb in LIMBS:
                _check_keys(f"{name}.{limb}", actor[limb], 3, length)
            _check_keys(f"{name}.face", actor["face"], 7, length)
            _check_keys(f"{name}.opacity", actor["opacity"], 2, length)
            if "posture" in actor:
                _check_keys(f"{name}.posture", actor["posture"], 5, length)
            if any(k[1] not in (1, -1) for k in actor["facing_keys"]) or actor["facing_keys"][0][0] != 0:
                raise ValueError(f"{name}: facing keys must be ±1 from t=0")
        for item in shot["items"]:
            name = f"{sid}.{item['id']}"
            _check_keys(f"{name}.track", item["track"], 4, length)
            _check_keys(f"{name}.visible", item["visible"], 2, length)
        for vehicle in shot["vehicles"]:
            _check_keys(f"{sid}.{vehicle['id']}", vehicle["track"], 3, length)
        # Every render frame: camera inside the artwork, limbs reachable, held items in the hand.
        actors = {a["id"]: a for a in shot["actors"]}
        for ins in shot.get("inserts", []):
            if not 0 <= ins["start"] < ins["end"] <= length + 1e-6 or not ins.get("text"):
                raise ValueError(f"{sid}: invalid insert")
        still_overlap: dict[tuple, float] = {}
        occluded: dict[tuple, float] = {}
        contacts = shot.get("contacts", [])
        for i in range(int(math.ceil(length * fps - 1e-9)) + 1):
            t = min(length, i / fps)
            cx, cy, zoom = _sample(shot["camera"], t)
            dark, fade = _sample(shot["light"], t)
            if zoom < 1 - 1e-9 or not (0 <= dark <= 1 and 0 <= fade <= 1):
                raise ValueError(f"{sid}: invalid zoom or light at {t:.3f}s")
            if (cx - half_width / zoom < -1e-6 or cx + half_width / zoom > 1280 + 1e-6
                    or cy - 360 / zoom < -1e-6 or cy + 360 / zoom > 720 + 1e-6):
                raise ValueError(f"{sid}: camera leaves the artwork at {t:.3f}s")
            for actor in shot["actors"]:
                for limb, d in actor_limb_distances(actor, t).items():
                    if not _reachable(limb, d):
                        raise ValueError(f"{sid}.{actor['id']}: unreachable {limb} ({d:.1f}) at {t:.3f}s")
            # Staging: no two people standing still inside each other (hand-overs are exempt).
            shown = [a for a in shot["actors"] if _visible(a, t)]
            for ai, a in enumerate(shown):
                for b in shown[ai + 1:]:
                    pair = (a["id"], b["id"])
                    xa, xb = _sample(a["root"], t)[0], _sample(b["root"], t)[0]
                    sep = MIN_SEPARATION * max(a.get("scale", 1), b.get("scale", 1))
                    moving = any(abs(_sample(c["root"], min(length, t + 0.1))[0] - _sample(c["root"], max(0, t - 0.1))[0])
                                 / 0.2 > STILL_SPEED for c in (a, b))
                    touching = any({c["a"], c["b"]} == set(pair) and c["from"] - 1e-6 <= t <= c["to"] + 1e-6
                                   for c in contacts)
                    planted = lambda c: max(_sample(c["left_foot"], t)[1], _sample(c["right_foot"], t)[1])  # noqa: E731
                    same_lane = abs(planted(a) - planted(b)) < 6
                    # Standing still inside each other, or walking through each other on the same
                    # depth lane (a passer must step behind), are both staging errors.
                    if abs(xa - xb) < sep and not touching and (not moving or same_lane):
                        still_overlap[pair] = still_overlap.get(pair, 0.0) + 1 / fps
                        if still_overlap[pair] > MAX_STILL_OVERLAP:
                            raise ValueError(f"{sid}: {pair[0]} and {pair[1]} overlap ({abs(xa - xb):.0f} px) at {t:.3f}s")
                    else:
                        still_overlap[pair] = 0.0
            # Props must not cover a visible face for more than a moment.
            for item in shot["items"]:
                # Resting items sit on wall furniture and are drawn behind people.
                if _sample(item["visible"], t)[0] < 0.5 or _step(item.get("held", [[0, 0]]), t) <= 0:
                    continue
                boxes = item_boxes(item, t)
                for a in shown:
                    key = (item["id"], a["id"])
                    if any(_box_hits_circle(box, *head_center(a, t)) for box in boxes):
                        occluded[key] = occluded.get(key, 0.0) + 1 / fps
                        if occluded[key] > MAX_OCCLUSION:
                            raise ValueError(f"{sid}: {item['id']} covers {a['id']}'s face at {t:.3f}s")
                    else:
                        occluded[key] = 0.0
            for item in shot["items"]:
                for hold in item.get("holds", []):
                    if hold["from"] - 1e-9 <= t <= hold["to"] + 1e-9:
                        hand = _sample(actors[hold["actor"]][hold["hand"]], t)
                        pos = _sample(item["track"], t)[:2]
                        if math.dist(hand, pos) > 0.5:
                            raise ValueError(f"{sid}.{item['id']}: leaves {hold['actor']}'s hand at {t:.3f}s")
            frames_checked += 1
    # Narration: ordered, inside one shot, real files, exactly the source text.
    narration = video["narration"]
    previous_end = 0.0
    for seg in narration:
        start, end = seg["start_seconds"], seg["end_seconds"]
        if not previous_end - 1e-9 <= start < end <= duration:
            raise ValueError(f"Narration {seg['id']} overlaps or leaves the video")
        if not any(s["start_seconds"] <= start and end <= s["end_seconds"] + 1e-9 for s in shots):
            raise ValueError(f"Narration {seg['id']} crosses a cut")
        if not Path(seg["path"]).is_file():
            raise ValueError(f"Missing narration: {seg['path']}")
        previous_end = end
    audio_mode = video.get("audio_mode", "narrated")
    if audio_mode not in {"narrated", "sfx_only"} or (audio_mode == "sfx_only" and narration):
        raise ValueError("SFX-only mode requires an empty narration list")
    if audio_mode == "narrated" and " ".join(n["text"] for n in narration) != " ".join(source_paragraphs(video["source_path"])):
        raise ValueError("Narration does not reproduce the source text exactly")
    for cue in video["sfx"]:
        if not (0 <= cue["start_seconds"] < duration and cue["duration_seconds"] > 0 and 0 <= cue["volume"] <= 1):
            raise ValueError(f"Invalid sound cue {cue['id']}")
        if not Path(cue["path"]).is_file():
            raise ValueError(f"Missing sound cue: {cue['path']}")
    # Timeline: one scene per shot, actions inside, each narration linked to an overlapping action.
    scenes = timeline["scenes"]
    if [s["scene_id"] for s in scenes] != [s["id"] for s in shots]:
        raise ValueError("Timeline scenes must match shots")
    for scene, shot in zip(scenes, shots):
        if (abs(scene["start_seconds"] - shot["start_seconds"]) > 1e-6
                or abs(scene["end_seconds"] - shot["end_seconds"]) > 1e-6):
            raise ValueError(f"Scene {scene['scene_id']} bounds differ from shot")
        if not scene["actions"]:
            raise ValueError(f"Scene {scene['scene_id']} has no actions")
        for action in scene["actions"]:
            at = action["at_seconds"]
            if not scene["start_seconds"] - 1e-6 <= at <= at + action.get("duration_seconds", 0) <= scene["end_seconds"] + 1e-6:
                raise ValueError(f"Action outside scene bounds in {scene['scene_id']}")
    by_scene = {s["scene_id"]: s for s in scenes}
    links = timeline.get("metadata", {}).get("narration_links", [])
    for seg in narration:
        linked = [l for l in links if l["narration_id"] == seg["id"]]
        if not linked:
            raise ValueError(f"Narration {seg['id']} is not linked to an action")
        for link in linked:
            actions = by_scene[link["scene_id"]]["actions"]
            if not 0 <= link["action_index"] < len(actions):
                raise ValueError(f"Narration {seg['id']} links to a missing action")
            action = actions[link["action_index"]]
            a0, a1 = action["at_seconds"], action["at_seconds"] + action.get("duration_seconds", 0)
            if a1 <= seg["start_seconds"] or a0 >= seg["end_seconds"]:
                raise ValueError(f"Narration {seg['id']} and its action do not overlap")
    return {"frames_checked": frames_checked, "shots": len(shots), "narration": len(narration),
            "actions": sum(len(s["actions"]) for s in scenes)}


def write_story_video_package(inputs: dict) -> ToolResult:
    video = inputs["story_video"]
    counters = validate_story_video(video, inputs["action_timeline"])
    workspace = Path(inputs["workspace_path"]).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    public = workspace / "public"
    public.mkdir(exist_ok=True)
    props = json.loads(json.dumps(video))
    for kind in ("narration", "sfx"):
        for seg in props.get(kind, []):
            source = Path(seg["path"])
            name = f"{kind}-{seg['id']}{source.suffix}"
            shutil.copy2(source, public / name)
            seg["path"] = name
    for shot in props["shots"]:
        for item in shot["items"]:
            item.pop("holds", None)
    templates = Path(__file__).parent / "remotion"
    for source in templates.iterdir():
        if source.suffix in {".tsx", ".ts"}:
            shutil.copy2(source, workspace / source.name)
    props_path = workspace / "props.json"
    props_path.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    edit = {"version": "1.0", "render_runtime": "remotion", "renderer_family": "animation-first",
            "composition_mode": "atelier", "cuts": [], "bespoke": {
                "entry": str(workspace / "index.tsx"), "composition_id": "StoryVideo",
                "props_path": str(props_path), "public_dir": str(public),
                "art_direction": video["art_direction"], "concurrency": inputs.get("concurrency", 2),
                "crf": 18, **({"scale": inputs["scale"]} if inputs.get("scale") else {})},
            "metadata": {"proposal_render_runtime": "remotion", "source": "character_rig_renderer",
                         "shots": len(video["shots"])}}
    assets = {"version": "1.0", "assets": [{"id": "story-video", "type": "animation",
              "path": str(workspace / "index.tsx"), "source_tool": "character_rig_renderer",
              "scene_id": video["shots"][0]["id"], "format": "tsx",
              "duration_seconds": video["duration_seconds"]}], "total_cost_usd": 0}
    return ToolResult(success=True, data={"render_package": "remotion_workspace", "workspace_path": str(workspace),
                      "props_path": str(props_path), "edit_decisions": edit, "asset_manifest": assets,
                      "validation": counters},
                      artifacts=[str(workspace / "index.tsx"), str(props_path)], cost_usd=0)
