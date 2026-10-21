"""Story analysis + measured narration -> multi-shot `story_video` plan.

Generic choreography: every beat's actions are expanded into skeletal tracks with
the existing rig mechanics (`story_motion.walk_clip`, two-bone IK in motion.ts),
items follow the holding hand key-for-key, and the camera frames whoever acts.
Timing comes from the real narration WAV durations; an action starts when its verb
is spoken (character offset in the sentence), never before the beat.
Nothing here knows any particular story: it only reads the closed vocabulary.
"""
from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool, Determinism, ExecutionMode, ResourceProfile, ToolResult,
    ToolRuntime, ToolStability, ToolStatus, ToolTier,
)
from tools.character.story_motion import GROUND_Y, walk_clip
from tools.story.lexicon import BAKERY_NAMES, RUN_WORDS, VEHICLE_KINDS
from tools.story.locations import build_location

FPS = 30
STAND_Y, SIT_Y, CROUCH_Y = 514, 547, 574  # body-space root heights (sit: pelvis on a y=556 seat)
TITLE_SECONDS = 2.4
LEAD, TAIL = 0.3, 0.4
WALK_SPEED, RUN_SPEED = 115.0, 200.0
LIMBS = ("root", "left_hand", "right_hand", "left_foot", "right_foot")
NEUTRAL = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # brow, gazeX, gazeY, mouth, lid, tilt
EXPRESSIONS = {
    "smile": [0.2, 0, 0, 1.0, 0, 2], "sad": [0.8, 0, 1.5, -0.5, 0.35, 4], "surprise": [1.4, 0, -0.5, -0.2, 0, -2],
    "fear": [1.2, -2, 0, -0.4, 0, -3], "think": [-0.5, -1.5, -2.5, 0, 0, -4], "sleep": [0, 0, 1, 0, 1.0, 5],
}
# Hand offsets relative to the root in the actor's local (right-facing) frame.
REST = {"left_hand": (-17, 3), "right_hand": (27, 3)}
SIT_HANDS = {"left_hand": (24, -8), "right_hand": (34, -10)}
CARRY = {"left_hand": (-14, 2), "right_hand": (26, 2)}
# Open umbrella grip above shoulder height: the canopy rim (grip - 128) clears the head top (root - 211).
# The grip is held forward of the face (face spans -25..+57) so the shaft never runs across it.
UMBRELLA_UP = (64, -112)
UMBRELLA_OVER = (66, -124)  # held out over someone else
TWO_HANDED = {"bread", "box", "tray"}  # carried in front with both hands
TWO_HANDED_GRIP = {"right_hand": (30, -38), "left_hand": (30, -38)}
TWO_HANDED_SUPPORT = {"right_hand": (24, -33), "left_hand": (24, -33)}
DEPTH_LANE = 16.0  # feet this much higher = one step further from the camera
SPACE = 105.0      # minimum root distance between two standing people who are not touching
GIVE_GAP = 112.0   # root distance for a hand-over
CHILD_SCALE = 0.72
# Largest visual dimension (px) and visual centre below the grip, for close-up framing.
ITEM_SIZE = {"umbrella": 118, "bag": 50, "phone": 20, "letter": 36, "book": 36, "newspaper": 44, "cup": 40,
             "bread": 48, "coin": 16, "key": 22, "box": 40, "bottle": 53, "tray": 72, "flower": 51}
ITEM_CENTER_DY = {"umbrella": 59, "bag": 29}
WRITTEN = {"letter", "newspaper", "book"}
# Vehicle geometry relative to (center x, ground y 600); must match StoryVideo.tsx.
VEHICLE = {"bus": {"door_dx": -305, "step_lift": 26, "floor_lift": 50, "inside_dx": 120, "stop_x": 720},
           "car": {"door_dx": -40, "step_lift": 14, "floor_lift": 30, "inside_dx": 40, "stop_x": 720}}
READ_HANDS = {"right_hand": (38, -62), "left_hand": (30, -58)}
# Grip point height above the surface an item rests on (drawing origin = grip).
REST_DY = {"umbrella": 118, "bag": 50, "phone": 3, "letter": 2, "book": 5, "newspaper": 4, "cup": 18,
           "bread": 11, "coin": 2, "key": 3, "box": 17, "bottle": 25, "tray": 4, "flower": 20}
DEFAULT_SURFACES = ("table", "counter", "shelf", "corner")
PALETTE = [  # shirt, hair
    ("#52778c", "#303c42"), ("#9a5b4f", "#3a2a24"), ("#6b7f4e", "#2b2622"), ("#7a5a9a", "#2a2430"),
    ("#b07a3c", "#4a3424"), ("#4f6f9a", "#222a30"),
]


def q(t: float) -> float:
    return round(t * FPS) / FPS


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def sample(keys: list, t: float) -> list:
    """Python twin of motion.ts sample(): per-segment smoothstep, clamped ends."""
    if t <= keys[0][0]:
        return list(keys[0][1:])
    for a, b in zip(keys, keys[1:]):
        if t <= b[0]:
            u = (t - a[0]) / (b[0] - a[0])
            u = u * u * (3 - 2 * u)
            return [x + (y - x) * u for x, y in zip(a[1:], b[1:])]
    return list(keys[-1][1:])


def step(keys: list, t: float) -> float:
    value = keys[0][1]
    for k in keys:
        if k[0] <= t + 1e-9:
            value = k[1]
    return value


# ---------------------------------------------------------------------------
# World state carried across shots
# ---------------------------------------------------------------------------

class Person:
    def __init__(self, info: dict, index: int):
        self.id = info["id"]
        shirt, hair = PALETTE[index % len(PALETTE)]
        if info.get("color"):
            shirt = info["color"]
        if info.get("age") == "elder":
            hair = "#cfd2cf"
        style = "long" if info.get("gender") == "female" else "short"
        self.look = {"shirt": shirt, "skin": ["#deded2", "#e3cdb6", "#d2b59a"][index % 3], "hair": hair,
                     "hair_style": style}
        self.scale = CHILD_SCALE if info.get("age") == "child" else 1.0
        self.location = None
        self.x, self.facing, self.posture = 640.0, 1, "stand"
        self.held: dict[str, str | None] = {"right_hand": None, "left_hand": None}
        self.last_item: str | None = None
        self.reading: str | None = None  # item held up in the reading pose
        self.present = False

    def latest_held(self) -> str | None:
        if self.last_item in self.held.values():
            return self.last_item
        return self.held["right_hand"] or self.held["left_hand"]


class Thing:
    def __init__(self, info: dict):
        self.id, self.kind = info["id"], info["kind"]
        self.color = info.get("color")
        self.location = None
        self.x = self.y = 0.0
        self.holder: tuple[str, str] | None = None
        self.visible = False
        self.inside = False


# ---------------------------------------------------------------------------
# Per-shot builders
# ---------------------------------------------------------------------------

class ActorTrack:
    """Keyframes for one person in one shot (shot-local seconds, world coordinates)."""

    def __init__(self, person: Person, visible: bool, shot: "ShotBuilder | None" = None):
        self.p = person
        self.shot = shot
        # A smaller person is the same rig scaled about the ground line: world = W(body).
        self.s = person.scale
        self.lift = 0.0          # world vertical offset (standing on a step / vehicle floor)
        self.layer = [[0.0, 0]]  # 1 = inside a vehicle (drawn behind its body)
        self.keys = {k: [] for k in LIMBS}
        self.facing = [[0.0, person.facing]]
        self.opacity = [[0.0, 1.0 if visible else 0.0]]
        self.face_events: list[tuple] = []
        self.hand_mode = dict.fromkeys(("left_hand", "right_hand"))  # local offset overrides
        if person.reading in person.held.values():
            self.hand_mode.update(READ_HANDS)
        self.t = 0.0
        self.pose = self.rest_pose()
        self.key(0.0)

    # -- body (rig) space <-> world ------------------------------------------
    def W(self, p) -> list:
        return [self.s * p[0], GROUND_Y + self.s * (p[1] - GROUND_Y) + self.lift]

    def B(self, p) -> list:
        return [p[0] / self.s, GROUND_Y + (p[1] - self.lift - GROUND_Y) / self.s]

    def body_point(self, u: float, y_body: float) -> list:
        """World point at local offset u (facing-relative) and absolute body height y_body."""
        return self.W([self.p.x / self.s + self.p.facing * u, y_body])

    def shoulder_y(self) -> float:
        return self.W([0, STAND_Y - 99])[1]

    # -- poses --------------------------------------------------------------
    def held_kind(self, hand: str) -> str | None:
        item = self.p.held[hand]
        return self.shot.pl.things[item].kind if item and self.shot is not None else None

    def offset(self, hand: str) -> tuple[float, float]:
        if self.hand_mode[hand]:
            return self.hand_mode[hand]
        other = "left_hand" if hand == "right_hand" else "right_hand"
        kind = self.held_kind(hand)
        if self.p.held[hand]:
            shot = self.shot
            if kind == "umbrella" and shot is not None and shot.loc["outdoor"] and shot.weather == "rain":
                return UMBRELLA_UP  # open umbrella held above the head in the rain
            if kind in TWO_HANDED and self.p.posture != "sit":
                return TWO_HANDED_GRIP[hand]
            return CARRY[hand]
        if self.held_kind(other) in TWO_HANDED and self.p.posture != "sit" and not self.hand_mode[other]:
            return TWO_HANDED_SUPPORT[hand]
        return SIT_HANDS[hand] if self.p.posture == "sit" else REST[hand]

    def rest_pose(self, x: float | None = None) -> dict:
        x = (self.p.x if x is None else x) / self.s
        f = self.p.facing
        y = {"stand": STAND_Y, "sit": SIT_Y, "crouch": CROUCH_Y}[self.p.posture]
        pose = {"root": [x, y]}
        for hand in ("left_hand", "right_hand"):
            u, dy = self.offset(hand)
            pose[hand] = [x + f * u, y + dy]
        if self.p.posture == "sit":
            pose["left_foot"], pose["right_foot"] = [x + f * 44, GROUND_Y], [x + f * 56, GROUND_Y]
        else:
            pose["left_foot"], pose["right_foot"] = [x - f * 12, GROUND_Y], [x + f * 12, GROUND_Y]
        return {k: self.W(v) for k, v in pose.items()}

    def key(self, t: float, pose: dict | None = None) -> None:
        pose = pose or self.pose
        for k in LIMBS:
            track = self.keys[k]
            if track and t < track[-1][0] - 1e-9:
                raise ValueError(f"{self.p.id}: key at {t:.3f} before {track[-1][0]:.3f}")
            if track and abs(track[-1][0] - t) < 1e-9:
                track[-1] = [track[-1][0], *pose[k]]
            else:
                track.append([t, *pose[k]])
        self.pose = {k: list(v) for k, v in pose.items()}
        self.t = max(self.t, t)

    def hold_to(self, t: float) -> None:
        if t > self.t + 1e-9:
            self.key(t)

    def move(self, t0: float, t1: float, pose: dict) -> None:
        self.hold_to(t0)
        self.key(t1, pose)

    def face(self, t0: float, t1: float, kind: str, value=None) -> None:
        self.face_events.append((t0, t1, kind, value))

    def turn(self, t: float, facing: int) -> float:
        if facing == self.p.facing:
            return t
        self.hold_to(t)
        self.p.facing = facing
        self.facing.append([t + 0.12, facing])
        self.key(t + 0.25, self.rest_pose())
        return t + 0.25

    def set_posture(self, t0: float, duration: float, posture: str) -> float:
        self.hold_to(t0)
        self.p.posture = posture
        self.key(t0 + duration, self.rest_pose())
        return t0 + duration

    def fade(self, t0: float, t1: float, value: float) -> None:
        last = self.opacity[-1]
        if t0 > last[0] + 1e-9:
            self.opacity.append([t0, last[1]])
        self.opacity.append([max(t1, self.opacity[-1][0] + 1e-3), value])

    # -- walking -------------------------------------------------------------
    def walk(self, t0: float, x1: float, speed: float = WALK_SPEED) -> tuple[float, list]:
        """Planted-foot walk (existing walk_clip) with held items carried at the side."""
        x0 = self.p.x
        if abs(x1 - x0) < 24:
            return t0, []
        if self.p.posture != "stand":
            t0 = self.set_posture(t0, 0.6, "stand")
        facing = 1 if x1 > x0 else -1
        t0 = self.turn(t0, facing)
        period = 0.42 if speed <= WALK_SPEED else 0.3
        duration = max(1.0, abs(x1 - x0) / (speed * self.s))
        xb0, xb1 = x0 / self.s, x1 / self.s  # the clip is built for the rig, then scaled
        clip = None
        for _ in range(60):
            try:
                candidate = walk_clip(xb0, xb1, t0, t0 + duration, facing, period=period)
            except ValueError:
                duration += 0.1
                continue
            # Legs are 57+58 px: slow the walk down until no planted foot over-stretches.
            tracks = candidate["tracks"]
            frames = [t0 + i / FPS for i in range(int(duration * FPS) + 1)]
            if all(math.dist(sample(tracks["root"], t), sample(tracks[f], t)) < 114.0
                   for t in frames for f in ("left_foot", "right_foot")):
                clip = candidate
                break
            duration *= 1.12
        if clip is None:
            raise ValueError(f"{self.p.id}: cannot build walk {x0}->{x1}")
        self.hold_to(t0)
        tracks = clip["tracks"]
        for hand in ("left_hand", "right_hand"):
            if self.p.held[hand] or self.hand_mode[hand] or self.offset(hand) != REST[hand]:
                u, dy = self.offset(hand)
                tracks[hand] = [[t, x + facing * u, STAND_Y + dy] for t, x, _ in tracks["root"]]
        # Passing someone who stands in the way: walk a little deeper in the room (feet higher,
        # drawn behind them; StoryVideo sorts people by foot height) instead of through them.
        depth = 0.0
        if self.shot is not None and any(min(x0, x1) + 30 < o.p.x < max(x0, x1) - 30
                                         for o in self.shot.visible_standing({self.p.id})):
            depth = -DEPTH_LANE
            self.shot.notes.append(f"{self.p.id} passes behind at {t0:.2f}s")
        end = t0 + duration
        times = sorted({k[0] for name in LIMBS for k in tracks[name]})
        for t in times:
            if t <= self.t + 1e-9:
                continue
            ramp = depth * min(1.0, (t - t0) / 0.4, (end - t) / 0.4) if depth else 0.0
            pose = {name: self.W(sample(tracks[name], t)) for name in LIMBS}
            self.key(t, {name: [p[0], p[1] + ramp] for name, p in pose.items()})
        self.p.x = x1
        self.key(end, self.rest_pose())
        return end, clip["landings"]


class ShotBuilder:
    def __init__(self, planner: "Planner", shot_id: str, loc_id: str, start: float, weather: str | None = None):
        self.pl = planner
        self.id, self.loc_id, self.start = shot_id, loc_id, start
        self.loc = planner.locations[loc_id]
        self.t = 0.0
        self.actors: dict[str, ActorTrack] = {}
        self.item_events: dict[str, list] = {}
        self.vehicle_keys: dict[str, list] = {}
        self.camera: list = []
        self.light: list = []
        self.door: list = [[0.0, 0.0]]
        self.actions: list[dict] = []
        self.arrivals: dict[str, float] = {}
        self.links: list[dict] = []
        self.sfx: list[dict] = []
        # Set before any actor pose is built: held umbrellas are raised from the first frame.
        self.weather = weather
        self.notes: list[str] = []
        self.focus_hint = self.reveal_hint = self.pending_insert = None
        self.contacts: list[dict] = []   # intentional body contact (hand-overs), exempt from spacing
        self.inserts: list[dict] = []    # full-frame close-ups of written items
        self.vehicle_door: dict[str, list] = {}
        night = planner.night
        self.dark = (0.45 if self.loc["outdoor"] else 0.22) if night else 0.0
        self.light.append([0.0, self.dark, 0.0])
        for person in planner.people.values():
            if person.location == loc_id and person.present:
                self.actors[person.id] = ActorTrack(person, visible=True, shot=self)
                for hand, item in person.held.items():
                    if item:
                        self._item_event(planner.things[item], 0.0, "attach", (person.id, hand))
        for thing in planner.things.values():
            if thing.kind in VEHICLE_KINDS:
                if thing.location == loc_id and thing.visible:
                    self.vehicle_keys[thing.id] = [[0.0, thing.x, 0]]
                    self.vehicle_door[thing.id] = [[0.0, 1.0]]
            elif thing.location == loc_id and thing.visible and not thing.inside and not thing.holder:
                self._item_event(thing, 0.0, "rest")

    # -- helpers --------------------------------------------------------------
    def actor(self, cid: str, t: float, arriving: bool = False, walk_in: bool = True) -> ActorTrack:
        if cid in self.actors:
            return self.actors[cid]
        person = self.pl.people[cid]
        if person.reading and person.location not in (None, self.loc_id):
            self.leave_behind(person)
        person.location, person.present, person.posture = self.loc_id, True, "stand"
        for hand, item in person.held.items():
            if item and self.pl.things[item].holder != (cid, hand):
                person.held[hand] = None
        if arriving:
            entry = self.loc["entry"]
            person.x = entry["x"] if entry["door"] else (-70 if person.x < 640 else 1350)
            person.facing = 1 if person.x < 640 else -1
            track = ActorTrack(person, visible=not entry["door"], shot=self)
            self.actors[cid] = track
            if entry["door"]:
                if t > 0:
                    track.hold_to(t)
                self.door_open(t, 0.5)
                track.fade(t + 0.2, t + 0.55, 1.0)
                self.door_open(t + 1.6, 0.0)
            # Step into the scene right away so the arrival is visible.
            if walk_in or not entry["door"]:
                _, landings = track.walk(max(t, track.t) + (0.3 if entry["door"] else 0.0), self.free_spot(cid))
                self.footsteps(landings)
        else:
            person.x = self.free_spot(cid)
            person.facing = 1 if person.x < 640 else -1
            track = ActorTrack(person, visible=t <= 1e-6, shot=self)
            if t > 1e-6:
                track.fade(t, t + 0.35, 1.0)
                self.notes.append(f"{cid} appears at {t:.2f}s (no entrance action in text)")
        self.actors[cid] = track
        for hand, item in person.held.items():
            if item and not any(e[1] == "attach" for e in self.item_events.get(item, [])):
                thing = self.pl.things[item]
                thing.location = self.loc_id
                self._item_event(thing, 0.0, "attach", (cid, hand))
        return track

    def leave_behind(self, person: Person) -> None:
        """Reading material stays where it was read when the reader moves elsewhere."""
        thing = self.pl.things[person.reading]
        old = self.pl.locations[person.location]
        surface = next((old["anchors"][f] for f in ("table", "counter", "shelf") if f in old["anchors"]),
                       {"x": person.x, "y": 600})
        for hand, item in person.held.items():
            if item == thing.id:
                person.held[hand] = None
        thing.holder, thing.location, thing.visible, thing.inside = None, person.location, True, False
        thing.x = self.pl.slot(person.location, thing, float(surface["x"]), float(surface["y"]))
        thing.y = float(surface["y"]) - REST_DY.get(thing.kind, 10)
        person.reading = None
        self.notes.append(f"{person.id} left the {thing.id} in {person.location}")

    def stop_reading(self, a: ActorTrack, t: float) -> float:
        """Put reading material down (seat edge or near the feet) before the next body action."""
        thing = self.thing(a.p.reading)
        a.p.reading = None
        a.hand_mode = dict.fromkeys(a.hand_mode)
        if thing is None or not (thing.holder and thing.holder[0] == a.p.id):
            return t
        hand = thing.holder[1]
        a.hold_to(t)
        spot = tuple(a.body_point(34, 552.0 if a.p.posture == "sit" else 530.0))
        a.key(t + 0.45, self.reach_pose(a, hand, spot))
        self.release(a, thing, t + 0.45, *spot)
        a.key(t + 0.8, a.rest_pose())
        return t + 0.8

    def visible_standing(self, exclude=()) -> list[ActorTrack]:
        return [o for o in self.actors.values() if o.p.id not in exclude and o.p.present
                and o.opacity[-1][1] >= 0.5 and o.layer[-1][1] == 0]

    def make_room(self, mover: ActorTrack, x: float, t: float, keep=()) -> None:
        """Anyone standing where `mover` is about to stop steps aside first (generic staging)."""
        for o in self.visible_standing(exclude={mover.p.id, *keep}):
            gap = SPACE * max(o.s, mover.s)
            if abs(o.p.x - x) >= gap or o.p.posture != "stand":
                continue
            side = 1 if o.p.x >= x else -1
            others = [q.p.x for q in self.visible_standing(exclude={o.p.id, mover.p.id})]
            options = [x + side * (gap + 12), x - side * (gap + 12), x + side * (2 * gap + 12)]
            nx = next((c for c in options if 60 <= c <= 1220 and all(abs(c - q) >= gap for q in others)),
                      _clamp(options[0], 60, 1220))
            _, landings = o.walk(max(o.t, t), nx)
            self.footsteps(landings, 0.3)
            self.notes.append(f"{o.p.id} steps aside for {mover.p.id} at {t:.2f}s")

    def free_spot(self, cid: str) -> float:
        taken = [a.p.x for k, a in self.actors.items() if k != cid]
        spots = sorted(self.loc["spots"], key=lambda s: abs(s - 640))
        for s in spots:
            if all(abs(s - x) > 160 for x in taken):
                return float(s)
        return float(spots[0])

    def anchor(self, feature: str | None) -> dict | None:
        anchors = self.loc["anchors"]
        if feature in anchors:
            return anchors[feature]
        aliases = {"table": ("counter", "shelf"), "counter": ("table", "shelf"), "computer": ("table",),
                   "desk": ("table",), "bed": ("seat",), "oven": ("counter",), "light": ("switch",)}
        for alt in aliases.get(feature or "", ()):
            if alt in anchors:
                return anchors[alt]
        return None

    def default_surface(self, features: list[str]) -> dict:
        for f in list(features) + list(DEFAULT_SURFACES):
            a = self.anchor(f)
            if a and f not in ("door", "window", "seat", "light", "switch"):
                return a
        return {"x": 640.0, "y": 600.0}

    def _item_event(self, thing: Thing, t: float, kind: str, value=None) -> None:
        events = self.item_events.setdefault(thing.id, [])
        if not events and kind != "rest":
            events.append((0.0, "rest", (thing.x, thing.y, thing.visible and not thing.inside)))
        if kind == "rest":
            value = (thing.x, thing.y, thing.visible and not thing.inside)
        events.append((t, kind, value))

    def door_open(self, t: float, amount: float, duration: float = 0.5) -> None:
        if not self.loc["door"]:
            return
        last = self.door[-1]
        if t > last[0] + 1e-9:
            self.door.append([t, last[1]])
        self.door.append([max(t + duration, self.door[-1][0] + 1e-3), amount])
        if amount > last[1]:
            self.cue("door_open", t, 0.8, 0.5)

    def cue(self, recipe: str, t: float, duration: float, volume: float, fade: float = 0.0) -> None:
        self.sfx.append({"recipe": recipe, "t": t, "duration": round(duration, 3), "volume": volume, "fade": fade})

    def record(self, cid, action, target, t0, t1, notes) -> int:
        self.actions.append({"at_seconds": t0, "duration_seconds": max(0.05, t1 - t0), "character_id": cid,
                             "action": action, "target": target or "", "notes": notes})
        return len(self.actions) - 1

    def stand_near(self, a: ActorTrack, point: dict, t: float, gap: float = 45.0) -> tuple[float, list]:
        """Walk so the point is within reach in front of the actor, then face it."""
        x = point["x"]
        gap *= a.s
        side = -1 if a.p.x < x else 1
        target = _clamp(x + side * gap, 50, 1230)
        if abs(target - x) < gap - 1:  # clamped at the frame edge: approach from the other side
            target = _clamp(x - side * gap, 50, 1230)
        blocked = [o for o in self.visible_standing({a.p.id}) if o.p.posture != "stand"
                   and abs(o.p.x - target) < SPACE]
        if blocked:  # a seated person cannot step aside: use the other side of the target
            target = _clamp(x - side * gap, 50, 1230)
        self.make_room(a, target, t)
        t, landings = a.walk(t, target)
        t = a.turn(t, 1 if x > a.p.x else -1)
        return t, landings

    def footsteps(self, landings: list, volume: float = 0.4) -> None:
        for t in landings:
            self.cue("footstep", t, 0.3, volume)

    def reach_pose(self, a: ActorTrack, hand: str, point: tuple[float, float]) -> dict:
        pose = a.rest_pose()
        pose[hand] = [point[0], point[1]]
        return pose

    # -- item helpers ------------------------------------------------------
    def thing(self, pid: str | None) -> Thing | None:
        return self.pl.things.get(pid) if pid else None

    def place_if_new(self, thing: Thing, features: list[str]) -> None:
        if thing.location == self.loc_id and (thing.visible or thing.holder):
            return
        if thing.holder:
            return
        surface = self.default_surface(features)
        thing.location, thing.visible, thing.inside = self.loc_id, True, False
        thing.x = self.pl.slot(self.loc_id, thing, float(surface["x"]), float(surface["y"]))
        thing.y = float(surface["y"]) - REST_DY.get(thing.kind, 10)
        self._item_event(thing, 0.0, "rest")

    def free_hand(self, a: ActorTrack) -> str:
        return "right_hand" if not a.p.held["right_hand"] else "left_hand"

    def grab(self, a: ActorTrack, thing: Thing, t: float, hand: str) -> None:
        a.p.held[hand] = thing.id
        a.p.last_item = thing.id
        thing.holder, thing.location, thing.visible, thing.inside = (a.p.id, hand), self.loc_id, True, False
        self._item_event(thing, t, "attach", (a.p.id, hand))

    def release(self, a: ActorTrack, thing: Thing, t: float, x: float, y: float, inside: bool = False) -> None:
        for hand in ("left_hand", "right_hand"):
            if a.p.held[hand] == thing.id:
                a.p.held[hand] = None
                a.hand_mode[hand] = None
        thing.holder, thing.x, thing.y, thing.inside = None, x, y, inside
        self._item_event(thing, t, "detach", (x, y))
        if inside:
            self._item_event(thing, t + 0.25, "hide")

    def spawn_in_hand(self, a: ActorTrack, thing: Thing, t: float) -> str:
        """The text uses an item that is nowhere in the scene: it fades in at the hand."""
        hand = self.free_hand(a)
        a.hold_to(t)
        if thing.id not in self.item_events:
            # Hidden until it fades in, parked at the hand (never drawn elsewhere or in flight).
            thing.visible, thing.inside = False, False
            thing.x, thing.y = a.pose[hand]
            self._item_event(thing, 0.0, "rest")
        thing.location, thing.visible = self.loc_id, True
        self.grab(a, thing, t, hand)
        self._item_event(thing, t, "fade_in")
        a.key(t + 0.3, a.rest_pose())
        self.notes.append(f"{thing.id} appears in {a.p.id}'s hand at {t:.2f}s (no earlier placement)")
        return hand

    def pick_up(self, a: ActorTrack, thing: Thing, t: float, features: list[str]) -> float:
        if thing.holder:
            if thing.holder[0] == a.p.id:
                return t
            if thing.holder[0] in self.actors:
                return self.give(self.actors[thing.holder[0]], thing, a, t)
            old = self.pl.people[thing.holder[0]]
            old.held[thing.holder[1]] = None
            thing.holder, thing.visible = None, False
            self.notes.append(f"{thing.id} moves from absent {old.id} to {a.p.id}")
            self.spawn_in_hand(a, thing, t)
            return a.t
        if thing.location != self.loc_id or not thing.visible:
            source = self.anchor(next((f for f in features if self.anchor(f)), None)) if features else None
            if source:
                thing.location, thing.visible, thing.inside = self.loc_id, True, False
                thing.x = self.pl.slot(self.loc_id, thing, float(source["x"]), float(source["y"]))
                thing.y = float(source["y"]) - REST_DY.get(thing.kind, 10)
                self._item_event(thing, 0.0, "rest")
            else:
                self.spawn_in_hand(a, thing, t)
                return a.t
        point = {"x": thing.x, "y": thing.y}
        body_y = a.B((0, thing.y))[1]
        low, high = body_y > 535, body_y < 430
        # Above the shoulder: reach out at arm's length so the item never passes over the face.
        t, landings = self.stand_near(a, point, t, gap=25 if low else 72 if high else 45)
        self.footsteps(landings)
        hand = self.free_hand(a)
        if low:
            a.p.posture = "crouch"
        pose = self.reach_pose(a, hand, (thing.x, thing.y))
        a.move(t, t + 0.5, pose)
        self.grab(a, thing, t + 0.5, hand)
        a.p.posture = "stand"
        a.key(t + 1.0, a.rest_pose())
        return t + 1.0

    def put_down(self, a: ActorTrack, thing: Thing, t: float, features: list[str]) -> float:
        if not (thing.holder and thing.holder[0] == a.p.id):
            if thing.location == self.loc_id and thing.visible and not thing.holder:
                t = self.pick_up(a, thing, t, [])
            else:
                self.spawn_in_hand(a, thing, t)
                t = a.t
        feature = next((f for f in features if self.anchor(f) and f not in ("door", "window", "seat")), None)
        surface = self.anchor(feature) if feature else self.default_surface([])
        inside = feature == "oven"
        x = float(surface["x"]) if inside else self.pl.slot(self.loc_id, thing, float(surface["x"]), float(surface["y"]))
        y = float(surface["y"]) - (0 if inside else REST_DY.get(thing.kind, 10))
        low = a.B((0, y))[1] > 535
        t, landings = self.stand_near(a, {"x": x, "y": y}, t, gap=25 if low else 45)
        self.footsteps(landings)
        hand = next(h for h in ("right_hand", "left_hand") if a.p.held[h] == thing.id)
        if low:
            a.p.posture = "crouch"
        a.move(t, t + 0.55, self.reach_pose(a, hand, (x, y)))
        self.release(a, thing, t + 0.55, x, y, inside)
        a.p.posture = "stand"
        a.key(t + 1.05, a.rest_pose())
        self.cue("ceramic_clink" if thing.kind == "cup" else "soft_place", t + 0.55, 0.35, 0.35)
        return t + 1.05

    def give(self, a: ActorTrack, thing: Thing, b: ActorTrack, t: float) -> float:
        """Hand-over: face each other at arm's length, both hands meet on the item, a short
        shared hold, ownership switches while both touch it, then the receiver draws it in."""
        if not (thing.holder and thing.holder[0] == a.p.id):
            t = self.pick_up(a, thing, t, [])
        side = 1 if b.p.x > a.p.x else -1
        gap = GIVE_GAP * max(a.s, b.s) ** 0.5
        target = _clamp(b.p.x - side * gap, 50, 1230)
        if abs(target - b.p.x) < gap - 1:
            target = _clamp(b.p.x + side * gap, 50, 1230)
        self.make_room(a, target, t, keep={b.p.id})
        t, landings = a.walk(t, target)
        self.footsteps(landings)
        t = a.turn(t, 1 if b.p.x > a.p.x else -1)
        tb = b.turn(max(b.t, t - 0.3), 1 if a.p.x > b.p.x else -1)
        if b.p.posture != "stand":
            tb = b.set_posture(tb, 0.6, "stand")
        t = max(t, tb)
        a.hold_to(t)
        b.hold_to(t)
        meet = ((a.p.x + b.p.x) / 2, (a.shoulder_y() + b.shoulder_y()) / 2 + 40 * min(a.s, b.s))
        hand_a = next(h for h in ("right_hand", "left_hand") if a.p.held[h] == thing.id)
        hand_b = self.free_hand(b)
        a.key(t + 0.6, self.reach_pose(a, hand_a, meet))
        b.hold_to(t + 0.2)
        b.key(t + 0.75, self.reach_pose(b, hand_b, meet))
        a.key(t + 1.25, self.reach_pose(a, hand_a, meet))   # both hands on the item
        b.key(t + 1.25, self.reach_pose(b, hand_b, meet))
        for hand in ("left_hand", "right_hand"):
            if a.p.held[hand] == thing.id:
                a.p.held[hand] = None
                a.hand_mode[hand] = None
        self.grab(b, thing, t + 1.25, hand_b)
        b.key(t + 1.9, b.rest_pose())
        a.key(t + 1.8, a.rest_pose())
        self.contacts.append({"a": a.p.id, "b": b.p.id, "from": t, "to": t + 1.9})
        self.focus_hint = (meet[0], meet[1], 1.9)
        return t + 1.9

    # -- seating -----------------------------------------------------------
    def sit_down(self, a: ActorTrack, t: float) -> float:
        """Stop in front of the seat, plant the feet, lower the hips back onto the seat with a
        hand on the seat edge, then hands to the lap. Large items go on the seat beside."""
        seat = self.loc["seat"]
        f = seat["facing"]
        front = seat["x"] + f * 26 * a.s
        self.make_room(a, front, t)
        t, landings = a.walk(t, front)
        self.footsteps(landings)
        t = a.turn(t, f)
        a.hold_to(t)
        feet = a.rest_pose()
        sx = seat["x"] / a.s
        feet["left_foot"], feet["right_foot"] = a.W([sx + f * 44, GROUND_Y]), a.W([sx + f * 56, GROUND_Y])
        a.key(t + 0.3, feet)                                 # feet planted where they stay
        bend = dict(feet)
        bend["root"] = a.W([sx + f * 8, 528])
        free = [h for h in ("left_hand", "right_hand") if not a.p.held[h]]
        for hand in free:                                    # hand on the seat edge
            bend[hand] = a.W([sx - f * 4, 550])
        a.key(t + 0.75, bend)
        a.p.x, a.p.posture = seat["x"], "sit"
        a.key(t + 1.15, a.rest_pose())
        t += 1.15
        if seat.get("width", 0) >= 200:
            for hand in ("right_hand", "left_hand"):
                item = self.thing(a.p.held[hand])
                if item is not None and item.kind in ("bag", "box", "tray"):
                    spot = (seat["x"] - f * 90, seat["top"] - REST_DY.get(item.kind, 10))
                    a.key(t + 0.5, self.reach_pose(a, hand, spot))
                    self.release(a, item, t + 0.5, *spot)
                    a.key(t + 0.9, a.rest_pose())
                    self.notes.append(f"{a.p.id} sets the {item.id} on the seat beside them (staging)")
                    t += 0.9
        return t

    def stand_from_seat(self, a: ActorTrack, t: float) -> float:
        seat = self.loc["seat"] or {"x": a.p.x, "facing": a.p.facing}
        f = a.p.facing
        a.hold_to(t)
        lean = a.rest_pose()
        lean["root"] = a.W([a.p.x / a.s + f * 14, 530])
        a.key(t + 0.35, lean)
        a.p.posture = "stand"
        a.p.x = seat["x"] + f * 26 * a.s
        a.key(t + 0.8, a.rest_pose())
        return t + 0.8


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

BODY_FREE = {"talk", "smile", "sad", "surprise", "fear", "think", "nod", "shake_head", "look", "sleep", "reveal",
             "disappear"}


class Planner:
    def __init__(self, analysis: dict, narration: dict[str, dict], max_beats_per_shot: int = 3):
        self.a = analysis
        self.narration = narration
        self.max_beats = max_beats_per_shot
        self.people = {c["id"]: Person(c, i) for i, c in enumerate(analysis["characters"])}
        self.things = {p["id"]: Thing(p) for p in analysis["props"]}
        self.locations = {}
        for loc in analysis["locations"]:
            variant = loc.get("variant")
            if loc["kind"] == "shop" and loc.get("name", "").lower() in BAKERY_NAMES:
                variant = "bakery"
            self.locations[loc["id"]] = build_location(loc["kind"], variant)
        self.night = False
        self.shots: list[dict] = []
        self.scenes: list[dict] = []
        self.links: list[dict] = []
        self.narr_out: list[dict] = []
        self.sfx: list[dict] = []
        self.notes: list[str] = []

    def slot(self, loc_id: str, thing: Thing, x: float, surface_y: float) -> float:
        """Free x on a surface: items never rest on top of each other (generic placement)."""
        others = [o for o in self.things.values() if o is not thing and o.location == loc_id
                  and o.visible and not o.holder and not o.inside and o.kind not in VEHICLE_KINDS
                  and abs((o.y + REST_DY.get(o.kind, 10)) - surface_y) < 12]
        for step_ in (0, 1, -1, 2, -2, 3, -3):
            cx = x + step_ * 46
            if all(abs(cx - o.x) >= 40 for o in others):
                return cx
        return x

    # -- grouping ---------------------------------------------------------------
    def groups(self) -> list[list[dict]]:
        out: list[list[dict]] = []
        for beat in self.a["beats"]:
            if (not out or beat["location_id"] != out[-1][-1]["location_id"] or beat["time_jump"]
                    or len(out[-1]) >= self.max_beats):
                out.append([beat])
            else:
                out[-1].append(beat)
        return out

    def plan(self) -> tuple[dict, dict]:
        t_global = TITLE_SECONDS
        self._title_shot()
        groups = self.groups()
        for gi, beats in enumerate(groups):
            self.night = beats[0]["time_of_day"] == "night"
            if beats[0]["time_jump"]:
                for person in self.people.values():
                    person.posture = "stand"
            sb = ShotBuilder(self, f"s{gi + 1:02d}", beats[0]["location_id"], t_global, beats[0]["weather"])
            moving = {"walk", "enter", "run", "approach", "open", "exit", "board"}
            for beat in beats:
                for cid in beat["characters"]:
                    if cid in sb.actors or cid not in self.people:
                        continue
                    if not any(a["action"] in moving for a in beat["actions"] if a.get("character_id") == cid):
                        sb.actor(cid, 0.0)  # already there when the shot opens
            fade_in = gi == 0 or beats[0]["time_jump"]
            fade_out = gi == len(groups) - 1 or groups[gi + 1][0]["time_jump"]
            for beat in beats:
                self._beat(sb, beat)
            length = sb.t + (1.2 if gi == len(groups) - 1 else 0.0)
            length = q(t_global + length) - t_global
            self._finish(sb, length, fade_in, fade_out)
            t_global += length
        duration = t_global
        video = {"version": "1.0", "duration_seconds": duration, "fps": FPS, "title": self.a["title"],
                 "language": self.a["language"],
                 "locations": {k: {key: v[key] for key in ("kind", "variant", "svg", "outdoor", "door", "window",
                                                           "anchors")}
                               for k, v in self.locations.items()},
                 "cast": {p.id: p.look for p in self.people.values()},
                 "shots": self.shots, "narration": self.narr_out, "sfx": self.sfx,
                 "source_path": self.a["source_path"],
                 "art_direction": "Reused v1 cartoon rig and Apartment v1 palette; procedural original rooms; "
                                  "planned automatically from the story text and measured narration.",
                 "planner_notes": self.notes}
        timeline = {"version": "1.0", "fps": FPS, "scenes": self.scenes,
                    "metadata": {"narration_links": self.links, "source": "tools/story/story_planner.py",
                                 "analyzer": self.a.get("analyzer", {})}}
        return video, timeline

    def _title_shot(self) -> None:
        shot = {"id": "s00_title", "start_seconds": 0.0, "end_seconds": TITLE_SECONDS, "view": "title",
                "location": None, "camera": [[0, 640, 360, 1], [TITLE_SECONDS, 640, 360, 1]],
                "light": [[0, 0, 1], [0.5, 0, 0], [TITLE_SECONDS - 0.5, 0, 0], [TITLE_SECONDS, 0, 1]],
                "door": [[0, 0], [TITLE_SECONDS, 0]], "weather": None, "actors": [], "items": [], "vehicles": [],
                "contacts": [], "inserts": []}
        self.shots.append(shot)
        self.scenes.append({"scene_id": shot["id"], "start_seconds": 0.0, "end_seconds": TITLE_SECONDS,
                            "actions": [{"at_seconds": 0.0, "duration_seconds": TITLE_SECONDS,
                                         "character_id": "camera", "action": "title_card",
                                         "target": "title", "notes": self.a["title"]}]})

    # -- beats ------------------------------------------------------------------
    def _beat(self, sb: ShotBuilder, beat: dict) -> None:
        b0 = sb.t
        nar = self.narration[beat["id"]]
        d = nar["duration_seconds"]
        n0, n1 = b0 + LEAD, b0 + LEAD + d
        text_len = max(1, len(beat["text"]))
        if beat["weather"] == "rain" and sb.weather is None:
            sb.weather = "rain"
        first_action = len(sb.actions)
        sb.focus_hint = sb.reveal_hint = sb.pending_insert = None
        actions = self._order(beat["actions"])
        ends = [b0]
        focus_actors: set[str] = set()
        focus_points: list[tuple[float, float]] = []
        for act in actions:
            off = act.get("offset")
            t_verb = n0 + d * (off / text_len) if isinstance(off, (int, float)) else n0
            try:
                result = self._do(sb, beat, act, b0, max(b0 + 0.05, t_verb - 0.25), (n0, n1))
            except ValueError as exc:
                self.notes.append(f"{beat['id']} {act['action']}: skipped ({exc})")
                continue
            if result:
                t0, t1, actors, points = result
                ends.append(t1)
                focus_actors |= set(actors)
                focus_points += points
        end = max(n1 + TAIL, max(ends) + 0.25)
        if sb.pending_insert:
            ins = sb.pending_insert
            start = max(ins["from"], b0 + 0.45 * (end - b0))
            end = max(end, start + 2.5)  # long enough to read
            sb.inserts.append({"start": start, "end": end, "kind": ins["kind"], "color": ins["color"],
                               "text": ins["text"]})
        if len(sb.actions) == first_action:
            sb.record("camera", "camera_hold", beat["location_id"], b0, end, f"{beat['id']}: no visible action")
            focus_actors |= {cid for cid in beat["characters"] if cid in sb.actors}
        # Narration (shot-local -> global) and its link to the first overlapping action.
        self.narr_out.append({"id": beat["id"], "path": nar["path"], "text": beat["text"],
                              "start_seconds": sb.start + n0, "end_seconds": sb.start + n1})
        link = next((i for i in range(first_action, len(sb.actions))
                     if sb.actions[i]["at_seconds"] < n1 and
                     sb.actions[i]["at_seconds"] + sb.actions[i]["duration_seconds"] > n0), first_action)
        sb.links.append({"narration_id": beat["id"], "action_index": link})
        self._frame(sb, b0, end, focus_actors, focus_points, beat)
        sb.t = end

    @staticmethod
    def _order(actions: list[dict]) -> list[dict]:
        """Arrivals first, leaving last: a character waves before boarding, not after."""
        rank = {"vehicle_arrive": -1, "exit": 2, "board": 2}
        return sorted(actions, key=lambda a: rank.get(a["action"], 0))

    def _do(self, sb: ShotBuilder, beat: dict, act: dict, b0: float, t: float, nar: tuple[float, float]):
        name, cid, target = act["action"], act.get("character_id"), act.get("target") or {}
        features = list(act.get("features") or []) or list(beat.get("features") or [])
        tid, ttype = target.get("id"), target.get("type")
        label = f"{beat['id']}: {act.get('phrase') or name}"
        moving = name in ("walk", "enter", "run", "approach", "exit", "open", "board")
        if name == "vehicle_arrive":
            return self._vehicle_arrive(sb, tid, t, label)
        if name in ("disappear", "reveal") and cid is None:
            return self._reveal(sb, beat, None, tid, features, t, name, label)
        if name == "knock" and cid is None:
            for i in range(3):
                sb.cue("knock", t + 0.28 * i, 0.25, 0.7)
            looked = []
            door = sb.anchor("door")
            for a in sb.actors.values():
                if door and a.opacity[-1][1] > 0:
                    a.face(t + 0.3, t + 2.0, "look", (door["x"], door["y"]))
                    looked.append(a.p.id)
            idx = sb.record("world", "knock", "door", t, t + 1.0, label)
            return t, t + 1.0, looked, []
        if cid is None or cid not in self.people:
            return None
        will_move = any(x["action"] in ("walk", "enter", "run", "approach", "exit", "open", "board")
                        for x in beat["actions"] if x.get("character_id") == cid)
        arriving = cid not in sb.actors and will_move
        # Someone whose first act is opening the door comes in through it and stays there.
        requested = t
        a = sb.actor(cid, b0 if not arriving else t, arriving=arriving, walk_in=name != "open")
        t = max(t, a.t)
        if a.p.reading and name not in BODY_FREE and name != "read":
            t = sb.stop_reading(a, t)
        if arriving:
            sb.arrivals[cid] = requested
        # An arrival belongs to the first recorded action it serves (even if an earlier one was a no-op).
        t0 = min(t, sb.arrivals.get(cid, t))
        points: list[tuple[float, float]] = []
        actors = [cid]
        if name in ("walk", "run", "enter", "approach"):
            speed = RUN_SPEED if name == "run" else WALK_SPEED
            if ttype == "character" and tid in sb.actors and tid != cid or name == "approach":
                other = sb.actors.get(tid) if tid in sb.actors else next(
                    (o for k, o in sb.actors.items() if k != cid), None)
                if other is not None:
                    side = 1 if other.p.x > a.p.x else -1
                    t, landings = a.walk(t, _clamp(other.p.x - side * 125, 50, 1230), speed)
                    t = a.turn(t, side)
                    actors.append(other.p.id)
                else:
                    t, landings = a.walk(t, sb.free_spot(cid), speed)
            elif features and sb.anchor(features[0]) and features[0] not in ("window",):
                t, landings = sb.stand_near(a, sb.anchor(features[0]), t, gap=60)
            else:
                t, landings = a.walk(t, sb.free_spot(cid), speed)
            sb.footsteps(landings)
        elif name == "exit" or name == "board":
            running = (act.get("phrase") or "").lower().split(" ")[0] in RUN_WORDS
            t = self._leave(sb, a, t, name, tid, running)
        elif name == "sit":
            if sb.loc["seat"] is None:
                raise ValueError("location has no seat")
            if a.p.posture == "sit":
                return None
            t = sb.sit_down(a, t)
            points.append((sb.loc["seat"]["x"], 500.0))
        elif name == "stand_up":
            if a.p.posture == "stand":
                return None
            t = sb.stand_from_seat(a, t)
        elif name in ("pick_up", "hold"):
            thing = sb.thing(tid) if ttype == "prop" else None
            if thing is None:
                thing = sb.thing(a.p.latest_held())
            if thing is None or thing.kind in VEHICLE_KINDS:
                return None
            t = sb.pick_up(a, thing, t, features)
            if name == "hold" and ttype == "character" and tid in sb.actors:
                hand = next(h for h in ("right_hand", "left_hand") if a.p.held[h] == thing.id)
                t = a.turn(t, 1 if sb.actors[tid].p.x > a.p.x else -1)
                a.hand_mode[hand] = UMBRELLA_OVER if thing.kind == "umbrella" else (40, -40)
                a.move(t, t + 0.7, a.rest_pose())
                t += 0.7
                actors.append(tid)
            points.append((thing.x, thing.y))
        elif name == "put_down":
            thing = sb.thing(tid) if ttype == "prop" else sb.thing(a.p.latest_held())
            if thing is None:
                return None
            t = sb.put_down(a, thing, t, features)
            points.append((thing.x, thing.y))
        elif name == "give":
            obj = (act.get("object") or {}).get("id")
            thing = sb.thing(tid) if ttype == "prop" else sb.thing(obj) or sb.thing(a.p.latest_held())
            receiver = tid if ttype == "character" else next((k for k in sb.actors if k != cid), None)
            if thing is None or receiver is None:
                return None
            b = sb.actor(receiver, b0)
            t = sb.give(a, thing, b, t)
            actors.append(receiver)
        elif name in ("open", "close", "knock", "operate", "lights_on", "lights_off"):
            t = self._fixture(sb, a, name, features, t)
        elif name == "read":
            thing = sb.thing(tid) if ttype == "prop" else None
            if thing is None:
                thing = sb.thing(a.p.latest_held())
            if thing is not None and not (thing.holder and thing.holder[0] == cid):
                if thing.location == sb.loc_id and thing.visible:
                    t = sb.pick_up(a, thing, t, features)
                else:
                    sb.spawn_in_hand(a, thing, t)
                    t = a.t
            for hand, off in READ_HANDS.items():
                a.hand_mode[hand] = off
            a.p.reading = thing.id if thing is not None else None
            a.move(t, t + 0.6, a.rest_pose())
            a.face(t, max(nar[1], t + 2.0), "look", "down")
            if thing is not None:
                sb.cue("paper", t + 0.1, 0.6, 0.35)
            t += 0.6
        elif name in ("wave", "point", "dress", "talk") and a.p.posture != "crouch":
            t = self._gesture(sb, a, name, target, t, nar, beat)
        elif name == "nod" or name == "shake_head":
            a.face(t, t + 1.0, name)
            t += 1.0
        elif name in EXPRESSIONS:
            dur = max(1.5, nar[1] - t)
            a.face(t, t + dur, name)
            if name == "surprise":
                a.hold_to(t)
                jolt = a.rest_pose()
                jolt["root"][1] -= 5 * a.s
                a.key(t + 0.15, jolt)
                a.key(t + 0.45, a.rest_pose())
            t += 0.8
        elif name == "look":
            point = self._target_point(sb, target, features)
            if point is None:
                return None
            t = a.turn(t, 1 if point[0] > a.p.x else -1)
            a.face(t, max(nar[1], t + 1.5), "look", point)
            t += 0.6
        elif name in ("disappear", "reveal"):
            return self._reveal(sb, beat, a, tid, features, t, name, label)
        elif name == "idle":
            t += 0.5
        else:
            return None
        t = max(t, t0 + 0.4)
        recorded = "seat" if name in ("sit", "stand_up") else tid or (features[0] if features else "")
        sb.record(cid, name, recorded, t0, t, label)
        sb.arrivals.pop(cid, None)
        for cid2 in actors:
            if cid2 in sb.actors:
                points.append((sb.actors[cid2].p.x, 420.0))
        return t0, t, actors, points

    def _target_point(self, sb, target, features):
        tid, ttype = target.get("id"), target.get("type")
        if ttype == "character" and tid in sb.actors:
            return (sb.actors[tid].p.x, 360.0)
        if ttype == "prop" and tid in self.things:
            th = self.things[tid]
            if th.holder and th.holder[0] in sb.actors:
                holder = sb.actors[th.holder[0]]
                return (holder.pose[th.holder[1]][0], holder.pose[th.holder[1]][1])
            if th.location == sb.loc_id:
                return (th.x, th.y)
        feature = tid if ttype == "feature" else (features[0] if features else None)
        anchor = sb.anchor(feature)
        return (anchor["x"], anchor["y"]) if anchor else None

    def _gesture(self, sb, a: ActorTrack, name, target, t, nar, beat) -> float:
        hand = "right_hand" if not a.p.held["right_hand"] or name == "point" and a.p.held["left_hand"] else "left_hand"
        if a.p.held[hand] and name != "talk":
            hand = "left_hand" if hand == "right_hand" else "right_hand"
        if name == "talk":
            # Speaker and nearest listener face each other (conversation staging).
            listeners = [o for o in sb.visible_standing({a.p.id}) if abs(o.p.x - a.p.x) < 520]
            if listeners:
                lis = min(listeners, key=lambda o: abs(o.p.x - a.p.x))
                t = a.turn(t, 1 if lis.p.x > a.p.x else -1)
                lis.turn(max(lis.t, t), 1 if a.p.x > lis.p.x else -1)
            text = beat["text"]
            q0, q1 = 0.0, 1.0
            for opener in ('"', "“", "«"):
                if opener in text:
                    i = text.index(opener)
                    j = max(text.rfind('"'), text.rfind("”"), text.rfind("»"))
                    q0, q1 = i / len(text), (j + 1) / len(text) if j > i else 1.0
                    break
            n0, n1 = nar
            a.face(n0 + (n1 - n0) * q0, n0 + (n1 - n0) * q1, "talk")
            if not a.p.held[hand] and a.p.posture == "stand":
                a.hold_to(t)
                a.hand_mode[hand] = (34, -40)
                a.key(t + 0.45, a.rest_pose())
                a.hand_mode[hand] = None
                a.key(t + 1.05, a.rest_pose())
                return t + 1.05
            return t + 0.6
        if a.p.held[hand]:
            return t + 0.3
        if name == "point":
            point = self._target_point(sb, target, list(beat.get("features") or []))
            if point:
                t = self._clear_arm(sb, a, 1 if point[0] > a.p.x else -1, t)
                t = a.turn(t, 1 if point[0] > a.p.x else -1)
            a.hold_to(t)
            a.hand_mode[hand] = (110, -105)
            a.key(t + 0.45, a.rest_pose())
            a.key(t + 1.4, a.rest_pose())
            a.hand_mode[hand] = None
            a.key(t + 1.9, a.rest_pose())
            return t + 1.9
        if name == "wave":
            if target.get("type") == "character" and target.get("id") in sb.actors:
                direction = 1 if sb.actors[target["id"]].p.x > a.p.x else -1
                t = self._clear_arm(sb, a, direction, t, keep={target["id"]})
                t = a.turn(t, direction)
            a.hold_to(t)
            for i, dx in enumerate((30, 46, 14, 46, 14, 30)):
                a.hand_mode[hand] = (dx, -150)
                a.key(t + 0.35 + 0.22 * i, a.rest_pose())
            a.hand_mode[hand] = None
            a.key(t + 2.0, a.rest_pose())
            return t + 2.0
        # dress: both hands meet at the waist twice
        a.hold_to(t)
        for i in range(2):
            a.hand_mode["left_hand"], a.hand_mode["right_hand"] = (6, -12), (16, -10)
            if a.p.held["left_hand"]:
                a.hand_mode["left_hand"] = None
            if a.p.held["right_hand"]:
                a.hand_mode["right_hand"] = None
            a.key(t + 0.35 + 0.6 * i, a.rest_pose())
            a.hand_mode["left_hand"] = a.hand_mode["right_hand"] = None
            a.key(t + 0.65 + 0.6 * i, a.rest_pose())
        return t + 1.25

    def _clear_arm(self, sb, a: ActorTrack, direction: int, t: float, keep=()) -> float:
        """An outstretched arm must not go through someone: step back from a person standing
        within arm's length on that side (staging only; the gesture itself is unchanged)."""
        reach = 115 * a.s + 50  # own arm + the other person's half body and forward hand
        blockers = [o for o in sb.visible_standing({a.p.id, *keep})
                    if 0 < (o.p.x - a.p.x) * direction < reach]
        if not blockers:
            return t
        nearest = min(blockers, key=lambda o: abs(o.p.x - a.p.x))
        nx = _clamp(nearest.p.x - direction * (reach + 30), 60, 1220)
        if (nearest.p.x - nx) * direction < reach:  # no room behind: do not move
            return t
        t, landings = a.walk(max(t, a.t), nx)
        sb.footsteps(landings, 0.3)
        sb.notes.append(f"{a.p.id} steps back to gesture past {nearest.p.id}")
        return t

    def _fixture(self, sb, a: ActorTrack, name, features, t) -> float:
        feature = {"lights_on": "light", "lights_off": "light", "knock": "door"}.get(name)
        if feature is None:
            feature = next((f for f in features if sb.anchor(f)), None) or ("door" if name in ("open", "close")
                                                                           else "table")
        point = sb.anchor(feature)
        if feature == "light":
            point = sb.anchor("switch") or sb.anchor("light") if name in ("lights_on", "lights_off") else point
        if point is None or point["y"] < 260:
            point = sb.anchor("switch") or sb.anchor("table")
        if point is None:
            raise ValueError(f"no anchor for {name}")
        t, landings = sb.stand_near(a, point, t)
        sb.footsteps(landings)
        hand = "right_hand" if not a.p.held["right_hand"] else "left_hand"
        a.move(t, t + 0.45, sb.reach_pose(a, hand, (point["x"], point["y"])))
        t += 0.45
        if name == "knock":
            for i in range(3):
                a.key(t + 0.14 + 0.28 * i, sb.reach_pose(a, hand, (point["x"] - 8 * a.p.facing, point["y"])))
                a.key(t + 0.28 + 0.28 * i, sb.reach_pose(a, hand, (point["x"], point["y"])))
                sb.cue("knock", t + 0.28 * (i + 1), 0.25, 0.7)
            t += 0.9
        elif name in ("open", "close") and feature == "door":
            sb.door_open(t, 1.0 if name == "open" else 0.0, 0.7)
        elif name in ("lights_on", "lights_off"):
            level = (0.18 if name == "lights_on" else 0.72) if self.night else (0.0 if name == "lights_on" else 0.35)
            last = sb.light[-1]
            if t > last[0]:
                sb.light.append([t, last[1], last[2]])
            sb.light.append([t + 0.25, level, 0.0])
            sb.dark = level
            sb.cue("switch", t, 0.2, 0.5)
        elif name == "operate":
            a.key(t + 0.2, sb.reach_pose(a, hand, (point["x"] + 6, point["y"] + 2)))
            a.key(t + 0.4, sb.reach_pose(a, hand, (point["x"], point["y"])))
            sb.cue("switch", t + 0.2, 0.2, 0.35)
            t += 0.4
        a.key(t + 0.45, a.rest_pose())
        return t + 0.45

    def _leave(self, sb, a: ActorTrack, t, name, tid, running: bool = False) -> float:
        if name == "board":
            t = self._board(sb, a, t, tid)
        else:
            entry = sb.loc["entry"]
            if entry["door"]:
                door = sb.anchor("door")
                t, landings = sb.stand_near(a, door, t, gap=50)
                sb.footsteps(landings)
                sb.door_open(t, 1.0, 0.5)
                t, landings = a.walk(t + 0.3, entry["x"])
                sb.footsteps(landings)
                a.fade(t, t + 0.35, 0.0)
                sb.door_open(t + 0.35, 0.0, 0.5)
                t += 0.35
            else:
                edge = 1360 if a.p.facing > 0 else -80  # keep going the way they face
                t, landings = a.walk(t, edge, RUN_SPEED if running else WALK_SPEED)
                sb.footsteps(landings, 0.3)
        a.p.present = False
        a.p.location = None
        for hand, item in a.p.held.items():
            if item:
                self.things[item].location = None
        return t

    def _board(self, sb, a: ActorTrack, t, tid) -> float:
        """Walk to the open door, step up, step in (behind the body, visible through door and
        windows), the door closes and the vehicle leaves carrying the passenger."""
        vid = tid if tid in self.things and self.things[tid].kind in VEHICLE_KINDS else next(
            (k for k in sb.vehicle_keys), None)
        if vid is None or vid not in sb.vehicle_keys or sb.vehicle_keys[vid][-1][1] > 1500:
            vid = vid or next((p for p, th in self.things.items() if th.kind in VEHICLE_KINDS), None)
            if vid is None:
                raise ValueError("nothing to board")
            self._vehicle_arrive(sb, vid, t, "vehicle arrives before boarding")
        geo = VEHICLE[self.things[vid].kind]
        keys = sb.vehicle_keys[vid]
        t = max(t, keys[-1][0])
        cx = keys[-1][1]
        door_x = cx + geo["door_dx"]
        sb.make_room(a, door_x, t)
        t, landings = a.walk(t, door_x)
        sb.footsteps(landings)
        a.hold_to(t)
        a.lift = -geo["step_lift"]                       # onto the step
        a.key(t + 0.35, a.rest_pose())
        sb.cue("footstep", t + 0.3, 0.3, 0.5)
        a.layer.append([t + 0.35, 1])                    # now behind the vehicle body
        a.lift = -geo["floor_lift"]
        a.key(t + 0.7, a.rest_pose())
        sb.cue("footstep", t + 0.65, 0.3, 0.45)
        t += 0.7
        t, _ = a.walk(t, door_x + geo["inside_dx"])     # moves into the aisle
        doors = sb.vehicle_door.setdefault(vid, [[0.0, 1.0]])
        doors += [[t, 1.0], [t + 0.5, 0.0]]
        sb.cue("door_open", t, 0.8, 0.35)
        a.hold_to(t + 0.9)
        t_go, t_gone = t + 0.9, t + 4.2
        keys.append([t_go, cx, 0])
        keys.append([t_gone, -900, 0])
        # The passenger rides along: same keys, same easing, constant offset from the vehicle.
        offset = {k: [v[0] - cx, v[1]] for k, v in a.pose.items()}
        a.key(t_gone, {k: [-900 + o[0], o[1]] for k, o in offset.items()})
        a.p.x = -900 + offset["root"][0]
        sb.cue("engine", t_go - 0.2, 3.6, 0.45, fade=0.6)
        self.things[vid].location, self.things[vid].visible = None, False
        sb.focus_hint = (door_x + 60, 440.0, 1.3)
        return t_gone

    def _vehicle_arrive(self, sb, vid, t, label):
        if vid is None or vid not in self.things:
            vid = next((p for p, th in self.things.items() if th.kind in VEHICLE_KINDS), None)
        if vid is None or not sb.loc["outdoor"]:
            return None
        stop = VEHICLE[self.things[vid].kind]["stop_x"]
        keys = sb.vehicle_keys.setdefault(vid, [[0.0, 1900, 0]])
        keys.append([t, keys[-1][1], 0])
        keys.append([t + 2.6, stop, 0])
        doors = sb.vehicle_door.setdefault(vid, [[0.0, 0.0]])
        doors += [[t + 2.7, 0.0], [t + 3.2, 1.0]]
        thing = self.things[vid]
        thing.location, thing.visible, thing.x = sb.loc_id, True, float(stop)
        sb.cue("engine", t, 3.0, 0.5, fade=0.5)
        sb.cue("door_open", t + 2.7, 0.8, 0.35)
        sb.record("world", "vehicle_arrive", vid, t, t + 2.6, label)
        return t, t + 2.6, [], [(float(stop), 420.0)]

    def _reveal(self, sb, beat, a, tid, features, t, name, label):
        thing = self.things.get(tid) if tid else None
        if thing is None:
            return None
        if name == "reveal":
            if not (thing.location == sb.loc_id and (thing.visible or thing.holder)):
                surface = sb.default_surface(features)
                thing.location, thing.visible, thing.inside = sb.loc_id, True, False
                thing.x = self.slot(sb.loc_id, thing, float(surface["x"]), float(surface["y"]))
                thing.y = float(surface["y"]) - REST_DY.get(thing.kind, 10)
                sb._item_event(thing, 0.0, "rest")
            sb.cue("low_drone", t, 3.0, 0.3, fade=0.8)
        else:
            if thing.holder:
                return None
            sb._item_event(thing, 0.0, "hide")
            thing.visible = False
        point = (thing.x, thing.y)
        observers = [a] if a else [x for x in sb.actors.values() if x.opacity[-1][1] > 0 and x.layer[-1][1] == 0]
        end = t + 1.6
        # Stand where the item can be seen: outside the close-up frame, but within a few steps.
        clear = 640 / _clamp(300 / ITEM_SIZE.get(thing.kind, 40), 2.0, 4.0) + 60
        for obs in observers:
            t_obs = max(obs.t, t)
            far = abs(obs.p.x - point[0]) > clear + 150
            blocking = abs(obs.p.x - point[0]) < clear
            if obs.p.posture == "stand" and (blocking or (a is not None and far)):
                # Go over to look (or step off the item so it can be seen): staging only.
                t_obs, landings = sb.stand_near(obs, {"x": point[0], "y": point[1]}, t_obs, gap=clear / obs.s)
                sb.footsteps(landings)
            t_obs = obs.turn(t_obs, 1 if point[0] > obs.p.x else -1)
            obs.face(t_obs, t_obs + 3.0, "look", point)
            end = max(end, t_obs + 0.6)
        sb.record(a.p.id if a else "camera", name, thing.id, t, end, label)
        sb.reveal_hint = (point[0], point[1], thing.kind)
        quote = (beat.get("dialogue") or {})
        if name == "reveal" and thing.kind in WRITTEN and quote.get("text") and not quote.get("speaker_id"):
            # Written words in the text are shown on the item itself in a close-up insert.
            sb.pending_insert = {"kind": thing.kind, "color": thing.color, "text": quote["text"], "from": end}
        return t, end, [o.p.id for o in observers], [point]

    # -- camera, finishing ------------------------------------------------------
    def _frame(self, sb: ShotBuilder, b0, end, actors, points, beat) -> None:
        """Camera per beat: frame whoever acts; push in on hand-overs/boarding; size-aware
        close-up on revealed items; a beat with nothing new keeps the previous framing."""
        def clamp_cam(cx, cy, z):
            z = max(1.0, z)
            return [_clamp(cx, 640 / z, 1280 - 640 / z), _clamp(cy, 360 / z, 720 - 360 / z), z]

        xs = [x for x, _ in points]
        for cid in actors:
            if cid in sb.actors:
                track = sb.actors[cid].keys["root"]
                xs += [k[1] for k in track if b0 - 1e-6 <= k[0] <= end + 1e-6 and -100 < k[1] < 1380] or \
                      [sb.actors[cid].p.x]
        close = None
        if sb.reveal_hint:
            px, py, kind = sb.reveal_hint
            close = clamp_cam(px, py + ITEM_CENTER_DY.get(kind, 0) - 8,
                              _clamp(300 / ITEM_SIZE.get(kind, 40), 2.0, 4.0))
        if xs:
            lo, hi = min(xs) - 150, max(xs) + 150
            zoom = _clamp(1280 / max(1.0, hi - lo), 1.0, 1.6)
            framing = ((lo + hi) / 2, 420 if zoom > 1.2 else 380, zoom)
        elif sb.camera:
            framing = tuple(sb.camera[-1][1:])  # hold: the sentence adds nothing to look at
        else:
            framing = (640, 360, 1.0)
        if sb.focus_hint:
            fx, fy, fz = sb.focus_hint
            framing = (fx, fy, max(fz, framing[2]))
        target = clamp_cam(*framing)
        if not sb.camera:
            sb.camera.append([0.0, 640, 360, 1.0])
        last = sb.camera[-1]
        move = min(1.0, max(0.4, (end - b0) * 0.3))
        if b0 > last[0] + 1e-9:
            sb.camera.append([b0, *last[1:]])
        if close:
            mid = b0 + max(move + 0.3, 0.4 * (end - b0))
            sb.camera.append([b0 + move, *target])
            sb.camera.append([min(mid, end - 0.2), *close])
            sb.camera.append([end, *clamp_cam(close[0], close[1], close[2] * 1.02)])
            return
        sb.camera.append([b0 + move, *target])
        sb.camera.append([end, *clamp_cam(target[0], target[1], target[2] * 1.03)])

    def _finish(self, sb: ShotBuilder, length: float, fade_in: bool, fade_out: bool) -> None:
        # Close every track at the shot length.
        for a in sb.actors.values():
            if a.t > length + 1e-6:
                raise ValueError(f"{sb.id}: actor keys beyond shot")
            a.hold_to(length)
            a.key(length)
        cam = [k for k in sb.camera if k[0] < length - 1e-9]
        cam.append([length, *sb.camera[-1][1:]])
        base = [k for k in sb.light if k[0] < length - 1e-9] + [[length, sb.light[-1][1], 0.0]]
        times = {k[0] for k in base}
        if fade_in:
            times |= {0.0, min(0.6, length / 3)}
        if fade_out:
            times |= {max(0.0, length - 0.8), length}

        def fade_at(t):
            v = 0.0
            if fade_in and t < 0.6:
                v = max(v, 1 - t / min(0.6, length / 3))
            if fade_out and t > length - 0.8:
                v = max(v, (t - (length - 0.8)) / 0.8)
            return _clamp(v, 0.0, 1.0)

        light = [[t, sample([[k[0], k[1]] for k in base], t)[0], fade_at(t)] for t in sorted(times)]
        door = [k for k in sb.door if k[0] < length - 1e-9]
        door.append([length, sb.door[-1][1]])
        for k in sb.door:
            if k[0] > length:
                door[-1][1] = k[1]
        actors_out = []
        for cid, a in sb.actors.items():
            face = self._face_keys(a, length)
            opacity = [k for k in a.opacity if k[0] < length - 1e-9] or [[0.0, a.opacity[0][1]]]
            opacity.append([length, a.opacity[-1][1]])
            actors_out.append({"id": cid, "look": a.p.look, "scale": a.s, **{k: a.keys[k] for k in LIMBS},
                               "facing_keys": a.facing, "face": face, "opacity": opacity,
                               "layer": [k for k in a.layer if k[0] <= length + 1e-9]})
        items_out = []
        for pid, events in sb.item_events.items():
            items_out.append(self._item_track(sb, self.things[pid], events, length))
        vehicles = []
        for vid, keys in sb.vehicle_keys.items():
            ks = [k for k in keys if k[0] <= length + 1e-9]
            if ks[-1][0] < length:
                ks.append([length, *ks[-1][1:]])
            doors = [k for k in sb.vehicle_door.get(vid, [[0.0, 0.0]]) if k[0] <= length + 1e-9]
            if doors[-1][0] < length:
                doors.append([length, doors[-1][1]])
            vehicles.append({"id": vid, "kind": self.things[vid].kind, "color": self.things[vid].color,
                             "track": _dedupe(ks), "door": _monotone(doors)})

        shot = {"id": sb.id, "start_seconds": sb.start, "end_seconds": sb.start + length, "view": "world",
                "location": sb.loc_id, "camera": _dedupe(cam), "light": _dedupe(light), "door": _dedupe(door),
                "weather": sb.weather, "actors": actors_out, "items": items_out,
                "vehicles": vehicles, "contacts": sb.contacts,
                "inserts": [i for i in sb.inserts if i["start"] < length]}
        self.shots.append(shot)
        scene_actions = []
        for act in sb.actions:
            at = min(act["at_seconds"], length - 0.05)
            dur = min(act["duration_seconds"], length - at)
            scene_actions.append({**act, "at_seconds": sb.start + at, "duration_seconds": max(0.05, dur)})
        self.scenes.append({"scene_id": sb.id, "start_seconds": sb.start, "end_seconds": sb.start + length,
                            "background": sb.loc_id, "camera": {"keys_local": shot["camera"]},
                            "effects": [e for e in (sb.weather,) if e], "actions": scene_actions})
        for link in sb.links:
            self.links.append({**link, "scene_id": sb.id})
        indoor = not sb.loc["outdoor"]
        self.sfx.append({"recipe": "room_tone" if indoor else "street_ambience", "t": sb.start, "duration": length,
                         "volume": 0.5, "fade": 0.3})
        if sb.weather == "rain":
            self.sfx.append({"recipe": "rain", "t": sb.start, "duration": length, "volume": 0.22 if indoor else 0.55,
                             "fade": 0.4})
        for cue in sb.sfx:
            if cue["t"] < length - 0.05:
                self.sfx.append({**cue, "t": sb.start + cue["t"], "duration": min(cue["duration"], length - cue["t"])})
        self.notes += [f"{sb.id}: {n}" for n in sb.notes]

    def _face_keys(self, a: ActorTrack, length: float) -> list:
        events = sorted(a.face_events, key=lambda e: e[0])
        keys = []
        n = max(2, int(math.ceil(length * 10)) + 1)
        for i in range(n):
            t = min(length, i / 10)
            face = list(NEUTRAL)
            for t0, t1, kind, value in events:
                if t < t0:
                    continue
                if kind in EXPRESSIONS and t <= t1 + 0.6:
                    w = min(1.0, (t - t0) / 0.3, max(0.0, (t1 + 0.6 - t) / 0.6))
                    face = [f + w * (e - f) for f, e in zip(face, EXPRESSIONS[kind])]
                elif kind == "look" and t <= t1 + 0.5:
                    w = min(1.0, (t - t0) / 0.25, max(0.0, (t1 + 0.5 - t) / 0.5))
                    if value == "down":
                        gx, gy = 0.0, 2.5
                    else:
                        root = sample(a.keys["root"], t)
                        dx, dy = value[0] - root[0], value[1] - (root[1] - 160 * a.s)
                        gx = _clamp(abs(dx) / 60, 0.0, 2.5)  # local frame: positive is "forward"
                        gy = _clamp(dy / 90, -2.5, 2.5)
                    face[1] += w * (gx - face[1])
                    face[2] += w * (gy - face[2])
                elif kind == "talk" and t0 <= t <= t1:
                    face[3] = 0.75 if int(t * 10) % 2 == 0 else -0.1
                elif kind == "nod" and t <= t1:
                    face[5] += 6 * math.sin(math.pi * (t - t0) / 0.25) ** 2
                elif kind == "shake_head" and t <= t1:
                    face[1] += 2.5 * math.sin(2 * math.pi * (t - t0) / 0.5)
            keys.append([t, *[round(v, 4) for v in face]])
        return _dedupe(keys)

    def _item_track(self, sb: ShotBuilder, thing: Thing, events: list, length: float) -> dict:
        events = sorted(events, key=lambda e: (e[0], {"rest": 0, "detach": 1, "attach": 2, "fade_in": 3,
                                                      "hide": 4}[e[1]]))
        track: list = []
        state: list = []
        holds: list = []
        pos = None
        attached = None
        rest_rot = -8 if thing.kind == "umbrella" else 0

        def add(t, x, y, rot):
            if track and abs(track[-1][0] - t) < 1e-9:
                track[-1] = [t, x, y, rot]
            else:
                track.append([t, x, y, rot])

        changes: list[tuple[float, float, float]] = []  # (t, value, ramp)

        def vis(t, v, ramp=0.0):
            changes.append((t, v, ramp))

        def close_attachment(t_end):
            cid, hand, t_start = attached
            keys = sb.actors[cid].keys[hand]
            for k in keys:
                if t_start - 1e-9 <= k[0] <= t_end + 1e-9:
                    add(k[0], k[1], k[2], 0)
            holds.append({"actor": cid, "hand": hand, "from": t_start, "to": t_end})

        for t, kind, value in events:
            if kind == "rest":
                x, y, v = value
                if attached is None:
                    pos = (x, y)
                    add(t, x, y, rest_rot)
                    vis(t, 1.0 if v else 0.0)
            elif kind == "attach":
                if attached:
                    close_attachment(t)
                attached = (value[0], value[1], t)
                state.append([t, 1])
            elif kind == "detach":
                if attached:
                    close_attachment(t)
                    attached = None
                pos = value
                add(t, value[0], value[1], rest_rot)
                state.append([t, 0])
            elif kind == "fade_in":
                vis(t, 0.0)
                vis(t, 1.0, 0.25)
            elif kind == "hide":
                vis(t, 0.0, 0.2 if t > 0 else 0.0)
        if attached:
            close_attachment(length)
        if not track:
            add(0.0, thing.x, thing.y, rest_rot)
        if track[0][0] > 0:
            track.insert(0, [0.0, *track[0][1:]])
        if track[-1][0] < length:
            add(length, *track[-1][1:])
        value = 1.0
        for t, v, ramp in changes:
            if t <= 1e-9 and ramp == 0:
                value = v
        visible = [[0.0, value]]
        for t, v, ramp in changes:
            if t <= 1e-9 and ramp == 0:
                continue
            if t > visible[-1][0] + 1e-9:
                visible.append([t, visible[-1][1]])
            visible.append([max(t + ramp, visible[-1][0] + 1e-3), v])
        visible = [k for k in visible if k[0] <= length + 1e-9]
        if visible[-1][0] < length:
            visible.append([length, visible[-1][1]])
        state = state or [[0.0, 0]]
        if state[0][0] > 0:
            state.insert(0, [0.0, 0 if state[0][1] else 1])
        open_keys = [[0.0, 0.0]]
        if thing.kind == "umbrella" and sb.loc["outdoor"] and sb.weather == "rain":
            open_keys = [[0.0, 1.0 if any(h["from"] <= 0.0 for h in holds) else 0.0]]
            for h in holds:
                if h["from"] > 0:
                    open_keys += [[h["from"], 0.0], [h["from"] + 0.6, 1.0]]
        return {"id": thing.id, "kind": thing.kind, "color": thing.color, "track": _dedupe(track),
                "visible": _monotone(visible), "held": state, "open": open_keys, "holds": holds}


def _dedupe(keys: list) -> list:
    out = []
    for k in keys:
        if out and k[0] <= out[-1][0] + 1e-9:
            out[-1] = list(k) if abs(k[0] - out[-1][0]) < 1e-9 else out[-1]
            continue
        out.append(list(k))
    return out


def _monotone(keys: list) -> list:
    out = []
    for k in keys:
        if out and k[0] <= out[-1][0] + 1e-9:
            out[-1] = [out[-1][0], k[1]]
            continue
        out.append(list(k))
    return out


def plan_story(analysis: dict, narration: dict[str, dict]) -> tuple[dict, dict]:
    return Planner(analysis, narration).plan()


class StoryPlanner(BaseTool):
    name = "story_planner"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "story_planning"
    provider = "openmontage"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL
    dependencies = []
    install_instructions = "No dependencies."
    agent_skills = ["character-rigging", "remotion-best-practices"]
    capabilities = ["shot_planning", "action_timeline", "camera_planning"]
    supports = {"offline": True}
    best_for = ["Turning a story_analysis plus measured narration into an animatable multi-shot plan"]
    not_good_for = ["Crowds, fights, lying down, vehicles driving with passengers in view"]
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=1)
    input_schema = {
        "type": "object", "required": ["story_analysis", "narration"],
        "properties": {"story_analysis": {"type": "object"},
                       "narration": {"type": "object", "description": "{beat_id: {path, duration_seconds}}"}},
    }
    side_effects = []
    user_visible_verification = ["Read the action timeline and planner notes (skipped actions)"]

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        start = time.monotonic()
        try:
            video, timeline = plan_story(inputs["story_analysis"], inputs["narration"])
        except (KeyError, ValueError, TypeError) as exc:
            return ToolResult(success=False, error=f"Story planning failed: {exc}")
        return ToolResult(success=True, data={"story_video": video, "action_timeline": timeline}, cost_usd=0,
                          duration_seconds=round(time.monotonic() - start, 2))
