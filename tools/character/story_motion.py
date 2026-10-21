"""Validated authored-motion handoff for the existing character renderer.

No story inference or stage orchestration: visual assets and choreography are data.
"""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

from schemas.artifacts import validate_artifact
from tools.base_tool import ToolResult


def validate_motion(motion: dict, timeline: dict) -> None:
    validate_artifact("action_timeline", timeline)
    duration = motion["duration_seconds"]
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Positive finite duration required")
    actor = motion["actor"]
    prop = motion["prop"]
    if not actor["id"] or not prop["id"] or actor["id"] == prop["id"]:
        raise ValueError("Distinct stable entity IDs required")
    tracks = {**{k: actor[k] for k in ("root", "left_hand", "right_hand", "left_foot", "right_foot")},
              "prop": prop["track"]}
    for name, keys in tracks.items():
        previous = -1
        for key in keys:
            if len(key) != (4 if name == "prop" else 3) or not all(math.isfinite(v) for v in key):
                raise ValueError(f"Invalid numeric key in {name}")
            if not previous < key[0] <= duration:
                raise ValueError(f"Unordered/out-of-range keys in {name}")
            previous = key[0]
        if not keys or keys[0][0] != 0 or keys[-1][0] != duration:
            raise ValueError(f"{name} must cover the whole scene")
    grip, release = prop["grip_seconds"], prop["release_seconds"]
    if not 0 <= grip < release <= duration:
        raise ValueError("Invalid grip/release interval")
    # Ownership switches cannot be used to teleport a wrist.
    def sample(keys, t):
        for a, b in zip(keys, keys[1:]):
            if a[0] <= t <= b[0]:
                u = (t-a[0])/(b[0]-a[0]); u = u*u*(3-2*u)
                return [x+(y-x)*u for x,y in zip(a[1:], b[1:])]
        return keys[-1][1:]
    for t in (grip, release):
        x, y, angle = sample(prop["track"], t)
        r = math.radians(angle)
        offset = prop["handle_offset"]
        hand = sample(actor["right_hand"], t)
        expected = [x + offset[0]*math.cos(r)-offset[1]*math.sin(r),
                    y + offset[0]*math.sin(r)+offset[1]*math.cos(r)]
        if math.dist(hand, expected) > .1:
            raise ValueError("Discontinuous hand/prop ownership boundary")
    used_actions = set()
    for scene in timeline["scenes"]:
        if scene["end_seconds"] > duration:
            raise ValueError("Scene exceeds motion duration")
        for action in scene["actions"]:
            used_actions.add(action["action"])
            if action["action"] not in motion["supported_actions"]:
                raise ValueError(f"Unsupported story action: {action['action']}")
            if action["character_id"] != actor["id"] or action.get("target") not in motion["entities"]:
                raise ValueError("Unknown actor/target")
            at = action["at_seconds"]
            if not scene["start_seconds"] <= at < at + action.get("duration_seconds", 0) <= scene["end_seconds"]:
                raise ValueError("Action outside scene bounds")
    if used_actions != set(motion["supported_actions"]):
        raise ValueError("Timeline is missing an authored story action")
    for segment in motion.get("narration", []):
        if not 0 <= segment["start_seconds"] < segment["end_seconds"] <= duration:
            raise ValueError("Narration outside scene")
        if not Path(segment["path"]).is_file():
            raise ValueError(f"Missing narration: {segment['path']}")
    for key in ("background_svg", "foreground_svg"):
        if not Path(motion[key]).is_file():
            raise ValueError(f"Missing artwork: {key}")


def write_remotion_package(inputs: dict) -> ToolResult:
    motion = inputs["story_motion"]
    validate_motion(motion, inputs["action_timeline"])
    workspace = Path(inputs["workspace_path"]).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    public = workspace / "public"
    public.mkdir(exist_ok=True)
    props = json.loads(json.dumps(motion))
    for key in ("background_svg", "foreground_svg"):
        props[key] = Path(motion[key]).read_text(encoding="utf-8")
    for index, segment in enumerate(props.get("narration", [])):
        source = Path(segment["path"])
        name = f"narration-{index}{source.suffix}"
        shutil.copy2(source, public / name)
        segment["path"] = name
    templates = Path(__file__).parent / "remotion"
    for source in templates.iterdir():
        if source.suffix in {".tsx", ".ts"}:
            shutil.copy2(source, workspace / source.name)
    props_path = workspace / "props.json"
    props_path.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
    edit = {"version": "1.0", "render_runtime": "remotion", "renderer_family": "animation-first",
            "composition_mode": "atelier", "cuts": [], "bespoke": {
                "entry": str(workspace / "index.tsx"), "composition_id": "StoryAction",
                "props_path": str(props_path), "public_dir": str(public),
                "art_direction": motion["art_direction"], "concurrency": 2, "crf": 18},
            "metadata": {"proposal_render_runtime": "remotion", "source": "character_rig_renderer"}}
    assets = {"version": "1.0", "assets": [{"id": "story-motion", "type": "animation",
              "path": str(workspace / "index.tsx"), "source_tool": "character_rig_renderer",
              "scene_id": inputs["action_timeline"]["scenes"][0]["scene_id"], "format": "tsx",
              "duration_seconds": motion["duration_seconds"]}], "total_cost_usd": 0}
    return ToolResult(success=True, data={"render_package": "remotion_workspace",
                      "workspace_path": str(workspace), "props_path": str(props_path),
                      "edit_decisions": edit, "asset_manifest": assets},
                      artifacts=[str(workspace / "index.tsx"), str(props_path)], cost_usd=0)


# ---------------------------------------------------------------------------
# Multi-shot episodes: one persistent world, many camera/time shots.
# ---------------------------------------------------------------------------

REST = {"left_hand": (-17, 3), "right_hand": (27, 3), "left_foot": (-12, None), "right_foot": (12, None)}
GROUND_Y = 620
FRIDGE_ITEM = "fridge_door"


def _sample(keys, t):
    """Python twin of motion.ts sample(): per-segment smoothstep, clamped ends."""
    if t <= keys[0][0]:
        return list(keys[0][1:])
    for a, b in zip(keys, keys[1:]):
        if t <= b[0]:
            u = (t - a[0]) / (b[0] - a[0])
            u = u * u * (3 - 2 * u)
            return [x + (y - x) * u for x, y in zip(a[1:], b[1:])]
    return list(keys[-1][1:])


def _check_keys(name, keys, width, duration):
    previous = -1
    for key in keys:
        if len(key) != width or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in key):
            raise ValueError(f"Invalid numeric key in {name}")
        if not previous < key[0] <= duration + 1e-9:
            raise ValueError(f"Unordered/out-of-range keys in {name}")
        previous = key[0]
    if not keys or keys[0][0] != 0 or abs(keys[-1][0] - duration) > 1e-6:
        raise ValueError(f"{name} must cover [0, {duration}]")


def fridge_handle(fridge: dict, angle: float) -> list[float]:
    return [fridge["hinge_x"] + (fridge["width"] - fridge["handle_inset"]) * math.cos(math.radians(angle)),
            fridge["handle_y"]]


def stand_pose(x: float, facing: int, y: float = 514) -> dict:
    """Rest pose (world coordinates) shared with the pilot's opening stance."""
    pose = {"root": [x, y]}
    for track, (u, dy) in REST.items():
        pose[track] = [x + facing * u, GROUND_Y if dy is None else y + dy]
    return pose


def walk_clip(x0: float, x1: float, t0: float, t1: float, facing: int, *, y: float = 514,
              fps: int = 30, period: float = 0.42, swing: float = 0.18, lift: float = 12,
              ramp: float = 0.18) -> dict:
    """Planted-foot walk between two rest poses.

    The root follows a trapezoidal speed profile on the frame grid; each foot
    alternates planted holds and lifted swings and lands at root + rest offset
    (the final landing of each foot targets the end pose). Hands swing opposite
    to the legs and blend from/to the rest pose. Returns tracks plus landings.
    """
    if (x1 - x0) * facing <= 0 or t1 - t0 < 2 * period:
        raise ValueError("Walk must move forward and last at least two steps")
    total = t1 - t0

    def root_x(t):
        tau = min(1.0, max(0.0, (t - t0) / total))
        k = 2 * ramp * (1 - ramp)
        if tau < ramp:
            s = tau * tau / k
        elif tau <= 1 - ramp:
            s = (tau - ramp / 2) / (1 - ramp)
        else:
            s = 1 - (1 - tau) ** 2 / k
        return x0 + (x1 - x0) * s

    frames = int(round(total * fps))
    grid = [t0 + i * total / frames for i in range(frames + 1)]
    tracks = {"root": [[t, root_x(t), y] for t in grid]}
    landings = []
    for foot, lead in (("left_foot", 0.04), ("right_foot", 0.04 + period / 2)):
        u = REST[foot][0]
        keys = [[t0, x0 + facing * u, GROUND_Y]]
        lift_t = t0 + lead
        while lift_t + swing <= t1 + 1e-9:
            land_t = lift_t + swing
            final = land_t + period > t1
            target = (x1 if final else root_x(land_t)) + facing * u
            start_x = keys[-1][1]
            keys += [[lift_t, start_x, GROUND_Y], [lift_t + swing / 2, (start_x + target) / 2, GROUND_Y - lift],
                     [land_t, target, GROUND_Y]]
            landings.append(land_t)
            if final:
                break
            lift_t += period
        if abs(keys[-1][1] - (x1 + facing * u)) > 1e-6:
            raise ValueError("Walk too short for the final step")
        if keys[-1][0] < t1 - 1e-9:
            keys.append([t1, keys[-1][1], GROUND_Y])
        tracks[foot] = [k for i, k in enumerate(keys) if i == 0 or k[0] > keys[i - 1][0] + 1e-9]
    swing_mid = t0 + 0.04 + swing / 2
    for hand, (base_u, base_dy), (walk_u, sign) in (("left_hand", REST["left_hand"], (-12, -1)),
                                                     ("right_hand", REST["right_hand"], (20, 1))):
        keys = []
        for t in grid:
            env = min(1.0, (t - t0) / 0.35, (t1 - t) / 0.35)
            env = env * env * (3 - 2 * env)
            phase = 2 * math.pi * (t - swing_mid) / period
            u = base_u + env * (walk_u + sign * 14 * math.cos(phase) - base_u)
            dy = base_dy + env * (-4 - base_dy)
            keys.append([t, root_x(t) + facing * u, y + dy])
        tracks[hand] = keys
    return {"tracks": tracks, "landings": sorted(landings)}


def concat_tracks(*segments: dict) -> dict:
    """Join per-track key lists; boundary keys at the same time must agree."""
    out: dict[str, list] = {}
    for segment in segments:
        for name, keys in segment.items():
            target = out.setdefault(name, [])
            for key in keys:
                if target and abs(target[-1][0] - key[0]) < 1e-9:
                    if any(abs(a - b) > 1e-6 for a, b in zip(target[-1][1:], key[1:])):
                        raise ValueError(f"Discontinuous {name} at {key[0]}")
                    continue
                target.append(list(key))
    return out


def hold_tracks(pose: dict, t0: float, t1: float) -> dict:
    return {name: [[t0, *p], [t1, *p]] for name, p in pose.items()}


def _check_motion_tracks(motion: dict, name: str) -> None:
    duration = motion["duration_seconds"]
    actor = motion["actor"]
    for track in ("root", "left_hand", "right_hand", "left_foot", "right_foot"):
        _check_keys(f"{name}.{track}", actor[track], 3, duration)
    if "face" in actor:
        _check_keys(f"{name}.face", actor["face"], 7, duration)
    if actor.get("facing", 1) not in (1, -1):
        raise ValueError(f"{name}: facing must be 1 or -1")
    _check_keys(f"{name}.prop", motion["prop"]["track"], 4, duration)


def validate_episode(episode: dict, timeline: dict) -> None:
    """Fail closed on anything that would render a discontinuous or unlinked story."""
    validate_artifact("action_timeline", timeline)
    duration = episode["duration_seconds"]
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Positive finite duration required")
    world = episode["world"]
    x0, x1 = world["x0"], world["x0"] + world["width"]
    shots = episode["shots"]
    if not shots or shots[0]["start_seconds"] != 0 or abs(shots[-1]["end_seconds"] - duration) > 1e-6:
        raise ValueError("Shots must cover the whole episode")
    for previous, shot in zip(shots, shots[1:]):
        if abs(previous["end_seconds"] - shot["start_seconds"]) > 1e-9:
            raise ValueError(f"Gap or overlap before shot {shot['id']}")
    if len({s["id"] for s in shots}) != len(shots):
        raise ValueError("Duplicate shot IDs")
    fps = episode["fps"]
    for shot in shots:
        sid, length = shot["id"], shot["end_seconds"] - shot["start_seconds"]
        if length <= 0:
            raise ValueError(f"Empty shot {sid}")
        _check_keys(f"{sid}.camera", shot["camera"], 4, length)
        _check_keys(f"{sid}.light", shot["light"], 3, length)
        _check_keys(f"{sid}.chair_b", shot["chair_b"], 3, length)
        _check_keys(f"{sid}.fridge_door", shot["fridge_door"], 2, length)
        motion = shot["motion"]
        _check_motion_tracks(motion, sid)
        offset = shot["motion_offset"]
        if offset < 0 or offset + length > motion["duration_seconds"] + 1e-6:
            raise ValueError(f"{sid}: motion does not cover the shot")
        if shot["view"] == "insert":
            if not Path(shot["insert_path"]).is_file():
                raise ValueError(f"{sid}: missing insert artwork")
            bounds = (0, 1280)
        elif shot["view"] == "world":
            bounds = (x0, x1)
        else:
            raise ValueError(f"{sid}: unknown view")
        # Sample the camera on the render clock: no frame may show beyond the art.
        for i in range(int(math.ceil(length * fps)) + 1):
            local = min(length, i / fps)
            cx, cy, zoom = _sample(shot["camera"], local)
            day, dark = _sample(shot["light"], local)
            if zoom < 1 - 1e-9 or not (0 <= day <= 1 and 0 <= dark <= 1):
                raise ValueError(f"{sid}: invalid zoom or light at {local:.3f}s")
            if (cx - 640 / zoom < bounds[0] - 1e-6 or cx + 640 / zoom > bounds[1] + 1e-6
                    or cy - 360 / zoom < -1e-6 or cy + 360 / zoom > 720 + 1e-6):
                raise ValueError(f"{sid}: camera leaves the artwork at {local:.3f}s")
        prop = motion["prop"]
        grip, release = prop.get("grip_seconds"), prop.get("release_seconds")
        if (grip is None) != (release is None) or (grip is not None and not 0 <= grip < release <= motion["duration_seconds"]):
            raise ValueError(f"{sid}: invalid grip/release interval")
        if grip is not None:
            # Ownership switches cannot be used to teleport a wrist (same rule as the pilot).
            for at in (grip, release):
                x, y, angle = _sample(prop["track"], at)
                r, offset = math.radians(angle), prop["handle_offset"]
                expected = [x + offset[0] * math.cos(r) - offset[1] * math.sin(r),
                            y + offset[0] * math.sin(r) + offset[1] * math.cos(r)]
                if math.dist(_sample(motion["actor"]["right_hand"], at), expected) > .1:
                    raise ValueError(f"{sid}: discontinuous hand/prop ownership boundary")
        for attachment in motion.get("attachments", []):
            if attachment["item"] != FRIDGE_ITEM or attachment["hand"] not in ("left", "right"):
                raise ValueError(f"{sid}: unknown attachment")
            if not 0 <= attachment["from"] < attachment["to"] <= motion["duration_seconds"]:
                raise ValueError(f"{sid}: attachment outside motion")
            for at in (attachment["from"], attachment["to"]):
                angle = _sample(shot["fridge_door"], at - offset)[0]
                hand = _sample(motion["actor"][f"{attachment['hand']}_hand"], at)
                if math.dist(hand, fridge_handle(world["fridge"], angle)) > .1:
                    raise ValueError(f"{sid}: discontinuous hand/handle attachment")
    if not isinstance(world.get("cup_occluder"), str):
        raise ValueError("World needs a cup_occluder path (may be empty)")
    for layer in world["layers"] + world["items_over"] + world["foreground"] + [world["day_window"]]:
        if not Path(layer["path"]).is_file():
            raise ValueError(f"Missing artwork: {layer['path']}")
    # Narration: ordered, inside one shot, real files, and exactly the source text.
    narration = episode["narration"]
    previous_end = 0.0
    for segment in narration:
        start, end = segment["start_seconds"], segment["end_seconds"]
        if not previous_end - 1e-9 <= start < end <= duration:
            raise ValueError(f"Narration {segment['id']} overlaps or leaves the episode")
        if not any(s["start_seconds"] <= start and end <= s["end_seconds"] for s in shots):
            raise ValueError(f"Narration {segment['id']} crosses a cut")
        if not Path(segment["path"]).is_file():
            raise ValueError(f"Missing narration: {segment['path']}")
        previous_end = end
    source = episode.get("source_text_path")
    if source:
        body = Path(source).read_text(encoding="utf-8").split("## SOURCE STORY — ORIGINAL TEXT", 1)[-1]
        paragraphs = [p.strip() for p in body.strip().split("\n\n") if p.strip()]
        if " ".join(s["text"] for s in narration) != " ".join(paragraphs):
            raise ValueError("Narration does not reproduce the source text exactly")
    for cue in episode.get("sfx", []):
        if not (0 <= cue["start_seconds"] < duration and cue["duration_seconds"] > 0 and 0 <= cue["volume"] <= 1):
            raise ValueError(f"Invalid sound cue {cue['id']}")
        if not Path(cue["path"]).is_file():
            raise ValueError(f"Missing sound cue: {cue['path']}")
    # Timeline: one scene per shot, known actions/entities, each narration linked to an overlapping action.
    scenes = timeline["scenes"]
    if [s["scene_id"] for s in scenes] != [s["id"] for s in shots]:
        raise ValueError("Timeline scenes must match shots")
    for scene, shot in zip(scenes, shots):
        if abs(scene["start_seconds"] - shot["start_seconds"]) > 1e-6 or abs(scene["end_seconds"] - shot["end_seconds"]) > 1e-6:
            raise ValueError(f"Scene {scene['scene_id']} bounds differ from shot")
        if not scene["actions"]:
            raise ValueError(f"Scene {scene['scene_id']} has no actions")
        for action in scene["actions"]:
            if action["action"] not in episode["supported_actions"]:
                raise ValueError(f"Unsupported story action: {action['action']}")
            if action["character_id"] not in episode["entities"] or action.get("target") not in episode["entities"]:
                raise ValueError("Unknown actor/target")
            at = action["at_seconds"]
            if not scene["start_seconds"] - 1e-6 <= at < at + action.get("duration_seconds", 0) <= scene["end_seconds"] + 1e-6:
                raise ValueError(f"Action outside scene bounds in {scene['scene_id']}")
    links = timeline.get("metadata", {}).get("narration_links", [])
    by_scene = {s["scene_id"]: s for s in scenes}
    for segment in narration:
        linked = [l for l in links if l["narration_id"] == segment["id"]]
        if not linked:
            raise ValueError(f"Narration {segment['id']} is not linked to an action")
        for link in linked:
            action = by_scene[link["scene_id"]]["actions"][link["action_index"]]
            a0, a1 = action["at_seconds"], action["at_seconds"] + action.get("duration_seconds", 0)
            if a1 <= segment["start_seconds"] or a0 >= segment["end_seconds"]:
                raise ValueError(f"Narration {segment['id']} and its action do not overlap")


def write_episode_package(inputs: dict) -> ToolResult:
    episode = inputs["story_episode"]
    validate_episode(episode, inputs["action_timeline"])
    workspace = Path(inputs["workspace_path"]).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    public = workspace / "public"
    public.mkdir(exist_ok=True)
    props = json.loads(json.dumps(episode))
    world = props["world"]

    def inline(layer):
        layer["svg"] = Path(layer.pop("path")).read_text(encoding="utf-8")

    for group in ("layers", "items_over", "foreground"):
        for layer in world[group]:
            inline(layer)
    inline(world["day_window"])
    for shot in props["shots"]:
        if shot["view"] == "insert":
            shot["insert_svg"] = Path(shot.pop("insert_path")).read_text(encoding="utf-8")
    for kind in ("narration", "sfx"):
        for segment in props.get(kind, []):
            source = Path(segment["path"])
            name = f"{kind}-{segment['id']}{source.suffix}"
            shutil.copy2(source, public / name)
            segment["path"] = name
    templates = Path(__file__).parent / "remotion"
    for source in templates.iterdir():
        if source.suffix in {".tsx", ".ts"}:
            shutil.copy2(source, workspace / source.name)
    props_path = workspace / "props.json"
    props_path.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    edit = {"version": "1.0", "render_runtime": "remotion", "renderer_family": "animation-first",
            "composition_mode": "atelier", "cuts": [], "bespoke": {
                "entry": str(workspace / "index.tsx"), "composition_id": "StoryEpisode",
                "props_path": str(props_path), "public_dir": str(public),
                "art_direction": episode["art_direction"], "concurrency": 2, "crf": 18},
            "metadata": {"proposal_render_runtime": "remotion", "source": "character_rig_renderer",
                         "shots": len(episode["shots"])}}
    assets = {"version": "1.0", "assets": [{"id": "story-episode", "type": "animation",
              "path": str(workspace / "index.tsx"), "source_tool": "character_rig_renderer",
              "scene_id": episode["shots"][0]["id"], "format": "tsx",
              "duration_seconds": episode["duration_seconds"]}], "total_cost_usd": 0}
    return ToolResult(success=True, data={"render_package": "remotion_workspace",
                      "workspace_path": str(workspace), "props_path": str(props_path),
                      "edit_decisions": edit, "asset_manifest": assets},
                      artifacts=[str(workspace / "index.tsx"), str(props_path)], cost_usd=0)
