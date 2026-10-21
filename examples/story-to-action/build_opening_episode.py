"""Author the opening episode as data, from measured narration and the approved pilot.

Choreography only: shots, camera, light, item states and actor tracks are written
here explicitly; nothing is inferred from the narration text. Narration timing
comes from the real WAV durations. Run from the repository root:

    .venv/bin/python examples/story-to-action/build_opening_episode.py \
        --narration-dir projects/<id>/assets/audio --sfx-dir projects/<id>/assets/audio/sfx \
        --out projects/<id>/artifacts
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.character.story_motion import (  # noqa: E402
    concat_tracks, fridge_handle, hold_tracks, stand_pose, walk_clip,
)

FIX = ROOT / "examples/story-to-action"
FPS = 30
MONDAY_CUP = [500, 478, 0]     # inside the basin; the near basin wall hides its foot
RACK_CUP = [645, 466, 180]     # pilot end pose: inverted on the rack
WORLD = {
    "x0": -1280, "width": 3200,
    "layers": [{"path": str(FIX / "apartment_west.svg"), "x": -1280},
               {"path": str(FIX / "apartment.svg"), "x": 0},
               {"path": str(FIX / "apartment_east.svg"), "x": 1280}],
    "items_over": [{"path": str(FIX / "apartment_west_overlay.svg"), "x": -1280}],
    # Near wall of the v1 basin (between its inner and outer ellipses): hides the foot of a cup in the sink.
    "cup_occluder": "M 454 486 A 57 12 0 0 0 568 486 L 554 486 A 43 7 0 0 1 468 486 Z",
    "foreground": [{"path": str(FIX / "foreground.svg"), "x": 0}],
    "day_window": {"path": str(FIX / "window_day.svg"), "x": 0},
    "fridge": {"hinge_x": -238, "width": 152, "top": 334, "bottom": 560, "handle_inset": 14, "handle_y": 425},
    "chair_a": {"x": -772, "y": 564},
    "chair_b": {"x": -508, "y": 564},
}
CHAIR_PULLED = [120, -6]
NEUTRAL = [0, 0, 0, 0, 0, 0]
SUPPORTED_ACTIONS = [
    "insert_close_up", "camera_pull_back", "camera_pan", "camera_push_in", "camera_hold",
    "stand_idle", "walk_to_sink", "look_down", "recall", "dismiss_thought",
    "reach_grasp", "wash", "invert_place", "walk_to_bedroom", "fade",
    "walk_to_fridge", "open_fridge", "stand_recall", "uncertain", "tired",
]
ENTITIES = [
    "minh", "camera", "white-cup", "sink", "rack", "bedroom", "living-room", "kitchen",
    "bathroom", "apartment", "kitchen-shelf", "dining-chair-a", "dining-chair-b",
    "fridge", "water-bottle",
]


def q(t: float) -> float:
    """Snap to the frame grid so shot cuts land exactly on frames."""
    return round(t * FPS) / FPS


def measure(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        if audio.getnframes() == 0:
            raise ValueError(f"Empty narration WAV: {path}")
        return audio.getnframes() / audio.getframerate()


def static(value: list, length: float) -> list:
    return [[0, *value], [length, *value]]


def face_keys(length: float, *keys) -> list:
    out = [[0, *NEUTRAL]] + [[t, *v] for t, v in keys if 0 < t < length]
    out.append([length, *out[-1][1:]])
    return out


class Builder:
    def __init__(self, narration: dict, narration_dir: Path, sfx_dir: Path):
        self.text = {s["id"]: s["text"] for s in narration["segments"]}
        self.order = [s["id"] for s in narration["segments"]]
        self.dur = {i: measure(narration_dir / f"{i}.wav") for i in self.order}
        self.narration_dir, self.sfx_dir = narration_dir, sfx_dir
        self.t = 0.0
        self.shots, self.scenes, self.narration, self.links, self.cues = [], [], [], [], []

    # -- narration and cues ------------------------------------------------
    def say(self, sid: str, at: float) -> tuple[float, float]:
        start = self.t + at
        end = start + self.dur[sid]
        self.narration.append({"id": sid, "path": str(self.narration_dir / f"{sid}.wav"),
                               "text": self.text[sid], "start_seconds": start, "end_seconds": end})
        return at, at + self.dur[sid]

    def cue(self, recipe: str, at: float, duration: float, volume: float, fade: float = 0) -> None:
        name = f"{recipe}-{duration:.3f}-{fade:.2f}"
        self.cues.append({"id": f"{recipe}-{len(self.cues):03d}", "recipe": recipe,
                          "path": str(self.sfx_dir / f"{name}.wav"), "start_seconds": round(at, 4),
                          "duration_seconds": duration, "volume": volume, "fade_seconds": fade})

    # -- shots -------------------------------------------------------------
    def fit(self, length: float) -> float:
        """Shot length that ends exactly on a frame of the episode clock."""
        return q(self.t + length) - self.t

    def shot(self, sid: str, length: float, *, view: str, camera: list, light: list, motion: dict,
             actions: list, links: dict, offset: float = 0, insert: str | None = None,
             chair: list | None = None, door: list | None = None, stain_until: float | None = None,
             drip_from: float | None = None, actor_visible: bool = True) -> None:
        if abs(self.fit(length) - length) > 1e-9:
            raise ValueError(f"Shot {sid} does not end on a frame")
        start, end = self.t, self.t + length
        shot = {"id": sid, "start_seconds": start, "end_seconds": end, "view": view,
                "camera": self._fit(camera, length), "light": self._fit(light, length),
                "motion": motion, "motion_offset": offset, "actor_visible": actor_visible and view == "world",
                "chair_b": self._fit(chair or static([0, 0], 1), length),
                "fridge_door": self._fit(door or static([0], 1), length),
                "stain_until": stain_until, "drip_from": drip_from}
        if insert:
            shot["insert_path"] = str(FIX / insert)
        self.shots.append(shot)
        scene_actions = []
        for index, (character, action, target, at, duration, notes) in enumerate(actions):
            at, duration = max(0.0, at), min(duration, length - max(0.0, at))
            scene_actions.append({"at_seconds": start + at, "duration_seconds": duration,
                                  "character_id": character, "action": action, "target": target,
                                  "notes": notes})
        for narration_id, action_index in links.items():
            self.links.append({"narration_id": narration_id, "scene_id": sid, "action_index": action_index})
        self.scenes.append({"scene_id": sid, "start_seconds": start, "end_seconds": end,
                            "camera": {"keys_local": shot["camera"]}, "actions": scene_actions})
        self.t = end

    @staticmethod
    def _fit(keys: list, length: float) -> list:
        """Clamp authored keys to the snapped shot length and close the track at its end."""
        out = [k for k in keys if k[0] < length - 1e-9]
        out.append([length, *keys[-1][1:]] if keys[-1][0] >= length - 1e-9 else [length, *out[-1][1:]])
        return out


def motion(length: float, tracks: dict, *, facing: int = 1, face: list | None = None,
           cup: list | None = None, attachments: list | None = None) -> dict:
    actor = {"id": "minh", **tracks, "shirt": "#52778c", "skin": "#deded2", "hair": "#303c42", "facing": facing,
             "face": face or face_keys(length)}
    return {"duration_seconds": length, "actor": actor,
            "prop": {"id": "white-cup", "track": cup or static(MONDAY_CUP, length),
                     "grip_seconds": None, "release_seconds": None, "handle_offset": [24, 0]},
            "wash_window": None, "attachments": attachments or []}


def adapt_pilot_pickup(pilot: dict) -> dict:
    """Episode-local copy of the approved pilot motion; the fixture file is unchanged.

    The pilot cup started on the counter beside the basin, but the story puts it
    in the sink. Only the pickup is re-targeted: the cup rests in the basin and
    is lifted straight out, Minh shifts his weight toward it while reaching, and
    the grip point follows the new handle position. Wash, inversion, release and
    walk keys are the pilot's own.
    """
    motion = json.loads(json.dumps({k: pilot[k] for k in ("duration_seconds", "actor", "prop", "wash_window")}))
    prop, actor = motion["prop"], motion["actor"]
    grip_t = prop["grip_seconds"]
    track = [k for k in prop["track"] if k[0] > 2.8]
    prop["track"] = [[0, *MONDAY_CUP], [grip_t, *MONDAY_CUP], [2.8, 505, 446, 0]] + track
    handle = [MONDAY_CUP[0] + prop["handle_offset"][0], MONDAY_CUP[1] + prop["handle_offset"][1]]
    actor["right_hand"] = [[0, 432, 517], [0.6, 432, 517], [1.6, 488, 480], [grip_t, *handle]] + [
        k for k in actor["right_hand"] if k[0] > grip_t]
    actor["root"] = [[0, 405, 514], [1.0, 405, 514], [grip_t, 428, 514]] + [k for k in actor["root"] if k[0] > grip_t]
    motion["attachments"] = []
    return motion


def footsteps(b: Builder, shot_start: float, landings: list) -> None:
    for t in landings:
        b.cue("footstep", shot_start + t, 0.3, 0.42)


def pilot_landings(keys: list, t0: float, t1: float) -> list:
    return [b[0] for a, b in zip(keys, keys[1:]) if a[2] < b[2] == 620 and t0 <= b[0] <= t1]


def build(narration_dir: Path, sfx_dir: Path) -> tuple[dict, dict, list]:
    narration = json.loads((FIX / "opening.narration.json").read_text(encoding="utf-8"))
    pilot = json.loads((FIX / "pilot.motion.json").read_text(encoding="utf-8"))
    b = Builder(narration, narration_dir, sfx_dir)

    # S01 cold open: the cup the narrator names, top-down in the sink, still dim.
    L = b.fit(0.5 + b.dur["n01"] + 0.35)
    a = b.say("n01", 0.5)
    b.shot("s01_cup_cold_open", L, view="insert", insert="insert_sink_cup.svg",
           camera=[[0, 640, 360, 1.0], [L, 580, 400, 1.3]], light=[[0, 0.3, 1], [0.6, 0.3, 0], [L, 0.3, 0]],
           motion=motion(L, hold_tracks(stand_pose(-940, 1), 0, L)), stain_until=1e6,
           actions=[("camera", "insert_close_up", "white-cup", 0, L, "Slow push on the single white cup in the sink")],
           links={"n01": 0})
    b.cue("low_drone", 0, L + 0.3, 0.5, fade=0.8)

    # S02 alone, then the apartment layout named room by room (pan settles on each).
    s = {}
    s["n02"] = b.say("n02", 0.3)
    s["n03a"] = b.say("n03a", s["n02"][1] + 0.3)
    s["n03b"] = b.say("n03b", s["n03a"][1] + 0.2)
    s["n03c"] = b.say("n03c", s["n03b"][1] + 0.25)
    s["n03d"] = b.say("n03d", s["n03c"][1] + 0.25)
    L = b.fit(s["n03d"][1] + 0.4)
    cam = [[0, -880, 410, 1.7], [s["n02"][1], -880, 410, 1.7], [s["n03a"][1], -640, 360, 1.0],
           [s["n03b"][1], -160, 360, 1.0], [s["n03c"][1], 760, 360, 1.0], [s["n03d"][1], 1280, 360, 1.0],
           [L, 1280, 360, 1.0]]
    face = face_keys(L, (0.2, [0, 0, 0.5, -0.2, 0.15, 0]))
    b.shot("s02_alone_layout", L, view="world", camera=cam, light=static([1, 0], 1), stain_until=1e6,
           motion=motion(L, hold_tracks(stand_pose(-940, 1), 0, L), face=face),
           actions=[("minh", "stand_idle", "living-room", 0, s["n02"][1] + 0.2, "Minh alone in the living room, medium shot"),
                    ("camera", "camera_pull_back", "apartment", s["n02"][1], s["n03a"][1] - s["n02"][1], "Pull back to the whole small apartment"),
                    ("camera", "camera_pan", "kitchen", s["n03a"][1], s["n03b"][1] - s["n03a"][1], "Living room joined to the kitchen"),
                    ("camera", "camera_pan", "bedroom", s["n03b"][1], s["n03c"][1] - s["n03b"][1], "Settle on the bedroom"),
                    ("camera", "camera_pan", "bathroom", s["n03c"][1], L - s["n03c"][1], "Settle on the small bathroom door")],
           links={"n02": 0, "n03a": 1, "n03b": 2, "n03c": 3, "n03d": 4})

    # S03 kitchen shelf: ordinary jars, no coffee things; the sink stays out of frame.
    a = b.say("n04", 0.2)
    L = b.fit(a[1] + 0.3)
    b.shot("s03_kitchen_shelf", L, view="world", camera=[[0, 380, 240, 2.4], [L, 430, 250, 2.6]],
           light=static([1, 0], 1), motion=motion(L, hold_tracks(stand_pose(-940, 1), 0, L)), stain_until=1e6,
           actions=[("camera", "camera_pan", "kitchen-shelf", 0, L, "Slow drift across the kitchen shelf")],
           links={"n04": 0})

    # S04 Monday morning: Minh walks to the sink and sees the cup.
    s["n05a"] = b.say("n05a", 0.25)
    s["n05b"] = b.say("n05b", s["n05a"][1] + 0.25)
    L = b.fit(s["n05b"][1] + 0.35)
    walk = walk_clip(40, 405, 0.1, 4.3, 1)
    tracks = concat_tracks(hold_tracks(stand_pose(40, 1), 0, 0.1), walk["tracks"],
                           hold_tracks(stand_pose(405, 1), 4.3, L))
    face = face_keys(L, (4.3, NEUTRAL), (4.8, [0, 1.5, 2.5, 0, 0, 7]))
    b.shot("s04_monday_sink", L, view="world", camera=[[0, 560, 400, 1.4], [4.1, 560, 400, 1.4], [L, 470, 430, 2.0]],
           light=static([1, 0], 1), motion=motion(L, tracks, face=face), stain_until=1e6,
           actions=[("minh", "walk_to_sink", "sink", 0.1, 4.2, "Monday morning, Minh walks into the kitchen"),
                    ("minh", "look_down", "white-cup", 4.3, L - 4.3, "Stops and looks down into the sink"),
                    ("camera", "camera_push_in", "white-cup", 4.1, L - 4.1, "Push toward the cup in the sink")],
           links={"n05a": 0, "n05b": 1})
    footsteps(b, b.shots[-1]["start_seconds"], walk["landings"])

    # S05 insert: the dried brown ring inside the cup.
    a = b.say("n06", 0.2)
    L = b.fit(a[1] + 0.3)
    b.shot("s05_stain_insert", L, view="insert", insert="insert_sink_cup.svg",
           camera=[[0, 560, 400, 1.15], [L, 560, 405, 1.55]], light=static([1, 0], 1),
           motion=motion(L, hold_tracks(stand_pose(405, 1), 0, L)), stain_until=1e6,
           actions=[("camera", "insert_close_up", "white-cup", 0, L, "Top-down close-up of the dried brown ring")],
           links={"n06": 0})

    # S06 Minh stares, rationalises, dismisses it; fade to the evening.
    s["n07"] = b.say("n07", 0.2)
    s["n08"] = b.say("n08", s["n07"][1] + 1.0)
    s["n09"] = b.say("n09", s["n08"][1] + 0.35)
    L = b.fit(s["n09"][1] + 0.75)
    look = [0, 1.5, 2.5, 0, 0, 7]
    think = [0.5, -1.5, -2.5, 0, 0, -2]
    eased = [0, 0.5, 0, 0.6, 0, 0]
    settle = [0, 1, 0, 0.3, 0, -3]
    face = face_keys(L, (0.05, look), (s["n08"][0], look), (s["n08"][0] + 0.5, think),
                     (s["n08"][0] + 0.68 * b.dur["n08"], think), (s["n08"][1], eased),
                     (s["n09"][0] + 0.3, settle))
    b.shot("s06_stare_dismiss", L, view="world",
           camera=[[0, 450, 400, 2.6], [s["n09"][0], 450, 400, 2.6], [L, 470, 420, 1.6]],
           light=[[0, 1, 0], [L - 0.6, 1, 0], [L, 1, 1]],
           motion=motion(L, hold_tracks(stand_pose(405, 1), 0, L), face=face), stain_until=1e6,
           actions=[("minh", "look_down", "white-cup", 0, s["n08"][0], "Holds still, staring at the cup"),
                    ("minh", "recall", "white-cup", s["n08"][0], b.dur["n08"], "Glances up, thinking of a weekend visitor, then eases"),
                    ("minh", "dismiss_thought", "white-cup", s["n09"][0], L - s["n09"][0], "Lifts his head; camera pulls back"),
                    ("camera", "fade", "apartment", L - 0.6, 0.6, "Fade out: Monday ends")],
           links={"n07": 0, "n08": 1, "n09": 2})

    # S07 evening: the approved pilot choreography, reframed for a readable inversion.
    off, end_m = 1.6, 14.2
    L = b.fit(end_m - off)
    for sid, m_at in (("n10a", 3.5), ("n10b", 8.0), ("n10c", 11.7)):
        b.say(sid, m_at - off)
    pilot_motion = adapt_pilot_pickup(pilot)
    cam = [[0, 500, 420, 1.5], [5.4, 520, 430, 1.6], [8.0, 630, 440, 2.4], [8.8, 645, 452, 3.4],
           [9.6, 645, 452, 3.4], [10.6, 640, 360, 1.0], [L, 700, 360, 1.0]]
    m = lambda t: t - off  # noqa: E731 - pilot motion time to shot-local time
    b.shot("s07_evening_wash", L, view="world", camera=cam, light=[[0, 0, 1], [0.5, 0, 0], [L - 0.6, 0, 0], [L, 0, 1]],
           motion=pilot_motion, offset=off, stain_until=5.0, drip_from=pilot["prop"]["release_seconds"],
           actions=[("minh", "reach_grasp", "white-cup", 0, m(3.3), "Pilot reach and grasp of the same cup"),
                    ("minh", "wash", "sink", m(3.3), 3.7, "Washes the cup under running water"),
                    ("minh", "invert_place", "rack", m(7.0), 3.2, "Turns the cup upside down and sets it on the rack"),
                    ("camera", "camera_push_in", "rack", m(9.6), 1.6, "Close-up: foot of the cup on top, mouth down, water dripping"),
                    ("minh", "walk_to_bedroom", "bedroom", m(11.5), L - m(11.5), "Walks toward the bedroom to sleep")],
           links={"n10a": 1, "n10b": 2, "n10c": 4})
    shot_start = b.shots[-1]["start_seconds"]
    b.cue("ceramic_clink", shot_start + m(2.2), 0.4, 0.35)
    b.cue("tap_water", shot_start + m(3.3), 3.7, 0.3, fade=0.2)
    b.cue("ceramic_clink", shot_start + m(10.2), 0.4, 0.6)
    pl = pilot_landings(pilot["actor"]["left_foot"], 11.5, end_m) + pilot_landings(pilot["actor"]["right_foot"], 11.5, end_m)
    footsteps(b, shot_start, sorted(m(t) for t in pl))

    # S08 next morning: the pulled-out chair, then the usual tucked chair and the narrow space.
    s["n11"] = b.say("n11", 0.5)
    s["n12"] = b.say("n12", s["n11"][1] + 0.35)
    L = b.fit(s["n12"][1] + 0.35)
    b.shot("s08_chair", L, view="world",
           camera=[[0, -600, 430, 1.4], [s["n11"][1], -470, 470, 2.0], [s["n12"][0] + 0.2, -470, 470, 2.0], [L, -760, 470, 1.8]],
           light=[[0, 1, 1], [0.5, 1, 0], [L, 1, 0]], chair=static(CHAIR_PULLED, 1),
           motion=motion(L, hold_tracks(stand_pose(932, 1), 0, L), cup=static(RACK_CUP, L)),
           actions=[("camera", "camera_push_in", "dining-chair-b", 0, s["n11"][1], "Pulled-out dining chair"),
                    ("camera", "camera_pan", "dining-chair-a", s["n12"][0], L - s["n12"][0], "The other chair tucked tight; little room to the sofa")],
           links={"n11": 0, "n12": 1})

    # S09 Minh walks past without noticing, then opens the fridge.
    rest = stand_pose(-28, -1)
    s["n13"] = b.say("n13", 0.3)
    reach, attach_from, attach_to, withdraw = 4.7, 5.1, 5.9, 6.5
    s["n14"] = b.say("n14", 4.6)
    L = b.fit(max(s["n14"][1], withdraw) + 0.3)
    walk = walk_clip(380, -28, 0.0, reach, -1)
    open_angle = 52
    handle_closed = fridge_handle(WORLD["fridge"], 0)
    handle_open = fridge_handle(WORLD["fridge"], open_angle)
    tracks = concat_tracks(walk["tracks"], hold_tracks(rest, reach, L))
    tracks["right_hand"] = [k for k in tracks["right_hand"] if k[0] <= reach] + [
        [attach_from, *handle_closed], [attach_to, *handle_open], [withdraw, *rest["right_hand"]], [L, *rest["right_hand"]]]
    door = [[0, 0], [attach_from, 0], [attach_to, open_angle], [6.6, 105], [L, 105]]
    b.shot("s09_fridge", L, view="world",
           camera=[[0, -300, 360, 1.0], [4.3, -300, 360, 1.0], [6.4, -150, 410, 1.6], [L, -150, 410, 1.6]],
           light=static([1, 0], 1), chair=static(CHAIR_PULLED, 1), door=door,
           motion=motion(L, tracks, facing=-1, cup=static(RACK_CUP, L),
                         attachments=[{"hand": "right", "item": "fridge_door", "from": attach_from, "to": attach_to}]),
           actions=[("minh", "walk_to_fridge", "fridge", 0, reach, "Walks past the pulled-out chair without looking at it"),
                    ("minh", "open_fridge", "fridge", reach, 6.6 - reach, "Grips the handle and pulls the fridge door open")],
           links={"n13": 0, "n14": 1})
    shot_start = b.shots[-1]["start_seconds"]
    footsteps(b, shot_start, walk["landings"])
    b.cue("fridge_door_open", shot_start + attach_from + 0.1, 0.8, 0.6)
    fridge_open_at = shot_start + attach_to

    # S10 insert: the 2 L bottle about a third down.
    a = b.say("n15", 0.2)
    L = b.fit(a[1] + 0.35)
    b.shot("s10_bottle_insert", L, view="insert", insert="insert_fridge_bottle.svg",
           camera=[[0, 640, 360, 1.0], [L, 640, 390, 1.35]], light=static([1, 0], 1),
           chair=static(CHAIR_PULLED, 1), door=static([105], 1),
           motion=motion(L, hold_tracks(rest, 0, L), facing=-1, cup=static(RACK_CUP, L)),
           actions=[("camera", "insert_close_up", "water-bottle", 0, L, "Water level about two thirds of the bottle")],
           links={"n15": 0})
    drone_at = b.shots[-1]["start_seconds"]

    # S11 Minh in the fridge light trying to remember; ends unresolved.
    s["n16"] = b.say("n16", 0.2)
    s["n17"] = b.say("n17", s["n16"][1] + 0.45)
    s["n18"] = b.say("n18", s["n17"][1] + 0.6)
    L = b.fit(s["n18"][1] + 1.8)
    recall = [-0.5, -1.5, -3, 0, 0, -4]
    doubt = [0.3, 1, 2, -0.4, 0.1, 2]
    tired = [0.1, 0.8, 1.5, -0.2, 0.35, 3]
    face = face_keys(L, (0.4, recall), (s["n16"][1], recall), (s["n17"][0] + 0.15, doubt),
                     (s["n18"][0], doubt), (s["n18"][0] + 0.6, tired))
    b.shot("s11_recall", L, view="world", camera=[[0, -80, 390, 2.3], [L, -60, 370, 2.9]],
           light=[[0, 1, 0], [L - 1.0, 1, 0], [L, 1, 1]], chair=static(CHAIR_PULLED, 1), door=static([105], 1),
           motion=motion(L, hold_tracks(rest, 0, L), facing=-1, face=face, cup=static(RACK_CUP, L)),
           actions=[("minh", "stand_recall", "fridge", 0, s["n16"][1] + 0.2, "Looks up, frowning, trying to remember"),
                    ("minh", "uncertain", "fridge", s["n17"][0], s["n18"][0] - s["n17"][0], "Eyes drop: maybe"),
                    ("minh", "tired", "fridge", s["n18"][0], L - s["n18"][0], "Heavy lids; slow push in, fade out")],
           links={"n16": 0, "n17": 1, "n18": 2})

    duration = b.t
    b.cue("room_tone", 0, duration, 0.6, fade=0.5)
    b.cue("fridge_hum", 0, duration, 0.12, fade=0.5)
    b.cue("fridge_hum", fridge_open_at, duration - fridge_open_at, 0.4, fade=0.4)
    b.cue("low_drone", drone_at, duration - drone_at, 0.45, fade=1.0)

    episode = {"duration_seconds": duration, "fps": FPS, "world": WORLD,
               "look": {"shirt": "#52778c", "skin": "#deded2", "hair": "#303c42"},
               "shots": b.shots, "narration": b.narration,
               "sfx": [{k: c[k] for k in ("id", "path", "start_seconds", "duration_seconds", "volume")} for c in b.cues],
               "supported_actions": SUPPORTED_ACTIONS, "entities": ENTITIES,
               "source_text_path": str(FIX / "source_story_opening.md"),
               "art_direction": "Approved Minh v1 / Apartment v1 cartoon horror; one persistent world, "
                                "multiple camera shots, measured narration."}
    timeline = {"version": "1.0", "fps": FPS, "scenes": b.scenes,
                "metadata": {"narration_links": b.links, "source": "examples/story-to-action/build_opening_episode.py"}}
    renders = sorted({(c["recipe"], c["duration_seconds"], c["fade_seconds"], c["path"]) for c in b.cues})
    return episode, timeline, [{"recipe": r, "duration_seconds": d, "fade_seconds": f, "output_path": p}
                               for r, d, f, p in renders]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--narration-dir", type=Path, required=True)
    parser.add_argument("--sfx-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    episode, timeline, renders = build(args.narration_dir.resolve(), args.sfx_dir.resolve())
    args.out.mkdir(parents=True, exist_ok=True)
    for name, data in (("story_episode.json", episode), ("action_timeline.json", timeline), ("sfx_renders.json", renders)):
        (args.out / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"duration_seconds": round(episode["duration_seconds"], 3), "shots": len(episode["shots"]),
                      "narration": len(episode["narration"]), "sfx_cues": len(episode["sfx"]),
                      "speech_seconds": round(sum(n["end_seconds"] - n["start_seconds"] for n in episode["narration"]), 3)}))


if __name__ == "__main__":
    main()
