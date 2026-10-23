"""P3.2A deterministic acting presets over the existing seekable actor tracks.

`ActorBuilder` keeps one current pose and appends keys for each preset in time
order. Output is a plain StoryVideo actor (root/hands/feet/face/posture/opacity)
for the existing two-bone IK; walking reuses `story_motion.walk_clip`. Presets
only shape keyframes: whether a performance reads as convincing must still be
judged on the rendered video.
"""
from __future__ import annotations

import math

from tools.character.story_motion import REST, stand_pose, walk_clip
from tools.character.story_video import ARM

TRACKS = ("root", "left_hand", "right_hand", "left_foot", "right_foot")
NEUTRAL_FACE = [.2, 1, 0, -.2, .1, 0]
MAX_CAUTIOUS_SPEED = 55  # world px/s; P3.1's guarded approach averaged ~36


class ActorBuilder:
    def __init__(self, actor_id: str, look: dict, x: float, *, rest_posture: list[float], facing: int = 1):
        if facing not in (1, -1):
            raise ValueError("facing must be ±1")
        self.id, self.look, self.facing = actor_id, look, facing
        self.rest = list(rest_posture)
        self.pose = {k: list(v) for k, v in stand_pose(x, facing).items()}
        self.posture = list(rest_posture)
        self.face = list(NEUTRAL_FACE)
        self.t = 0.0
        self.keys: dict[str, list] = {name: [] for name in (*TRACKS, "posture", "face")}
        self.log: list[dict] = []
        self._key(0.0)

    # -- primitives
    def _key(self, t: float, **override) -> None:
        values = {**{k: self.pose[k] for k in TRACKS}, "posture": self.posture, "face": self.face, **override}
        for name, value in values.items():
            keys = self.keys[name]
            t = round(t, 4)
            if keys and t <= keys[-1][0] + 1e-9:
                if abs(t - keys[-1][0]) < 1e-9:
                    keys[-1] = [t, *value]
                    continue
                raise ValueError(f"{self.id}: preset keys go back in time at {t}")
            keys.append([t, *value])

    def _start(self, preset: str, t0: float, t1: float, **detail) -> None:
        if t0 < self.t - 1e-9 or t1 <= t0:
            raise ValueError(f"{preset} must start after {self.t:.3f}s and have positive length")
        if t0 > self.t + 1e-9:
            self._key(t0)
        self.log.append({"preset": preset, "from": t0, "to": t1, **detail})

    def _shoulder(self) -> list[float]:
        return [self.pose["root"][0] + self.facing * self.posture[0], self.pose["root"][1] + self.posture[1]]

    # -- presets
    def hold(self, t1: float) -> "ActorBuilder":
        self._key(t1)
        self.t = t1
        return self

    def cautious_walk(self, x1: float, t0: float, t1: float, *, period: float = .72) -> "ActorBuilder":
        self._start("cautious_walk", t0, t1, to_x=x1)
        x0, y = self.pose["root"]
        for foot in ("left_foot", "right_foot"):
            if math.dist(self.pose[foot], [x0 + self.facing * REST[foot][0], self.pose[foot][1]]) > 1e-6:
                raise ValueError(f"{self.id}: walk must start from a planted rest stance")
        speed = abs(x1 - x0) / (t1 - t0)
        if speed > MAX_CAUTIOUS_SPEED:
            raise ValueError(f"{self.id}: {speed:.0f} px/s is not a cautious walk (max {MAX_CAUTIOUS_SPEED})")
        # A planted foot trails the root by about peak speed x period; keep that inside leg reach.
        peak = speed / .82
        period = min(period, 26 / peak) if peak else period
        clip = walk_clip(x0, x1, t0, t1, self.facing, y=y, fps=30, period=period, swing=min(.24, period * .45), lift=10)
        guard = {"left_hand": (-14 * self.facing + 6 * self.facing, -14), "right_hand": (-10 * self.facing, -36)}
        start = {h: [self.pose[h][0] - clip["tracks"][h][0][1], self.pose[h][1] - clip["tracks"][h][0][2]]
                 for h in ("left_hand", "right_hand")}
        tense = [self.rest[0] + 3, self.rest[1] - 2, self.rest[2] + 4, self.rest[3] - 2]
        for name in TRACKS:
            for t, x, yy in clip["tracks"][name]:
                if name.endswith("hand"):
                    a = min(1.0, (t - t0) / .4)
                    a = a * a * (3 - 2 * a)
                    gx, gy = guard[name]
                    x += (1 - a) * start[name][0] + a * gx
                    yy += (1 - a) * start[name][1] + a * gy
                if round(t, 4) > self.keys[name][-1][0] + 1e-9:
                    self.keys[name].append([round(t, 4), x, yy])
        last = {name: self.keys[name][-1][1:] for name in TRACKS}
        self.posture = tense
        self.keys["posture"].append([round(min(t1, t0 + .35), 4), *tense])
        self.face = [.9, 5, 0, -.4, .1, 2]
        self.keys["face"].append([round(min(t1, t0 + .4), 4), *self.face])
        self.pose.update({k: list(v) for k, v in last.items()})
        self._key(t1)
        self.t = t1
        self.walk_landings = getattr(self, "walk_landings", []) + clip["landings"]
        return self

    def startled_reaction(self, t0: float, *, toward: int = 1, hold: float = 1.0, strength: float = 1.0) -> "ActorBuilder":
        """Recoil away from a sound/event; gaze turns toward it (+1 = facing side)."""
        t1 = t0 + .2 + hold
        self._start("startled_reaction", t0, t1, toward=toward)
        rx, ry = self.pose["root"]
        f = self.facing
        root = [rx - 6 * f * toward * strength, ry + 8 * strength]
        posture = [self.rest[0] - 8 * strength, self.rest[1] - 6 * strength, self.rest[2] - 12 * strength, self.rest[3] - 6 * strength]
        hands = {"left_hand": [root[0] + 19 * f, root[1] - 69], "right_hand": [root[0] + 40 * f, root[1] - 62]}
        face = [1.4, 6 * toward, -1, -.85, 0, -12 * toward]
        tp = t0 + .2
        self._key(tp, root=root, posture=posture, face=face, **hands)
        self._key(tp + hold * .55, root=root, posture=posture, face=face, **hands)
        # Recover onto the planted stance (feet never moved) but stay wary.
        settled = {"left_hand": rest_hand(rx, ry, "left_hand", f), "right_hand": rest_hand(rx, ry, "right_hand", f)}
        self.pose.update(root=[rx, ry], **settled)
        self.posture = [self.rest[0] + 3, self.rest[1] - 2, self.rest[2] + 4, self.rest[3] - 2]
        self.face = [1.1, 6 * toward, -1, -.6, 0, -8 * toward]
        self._key(t1)
        self.t = t1
        return self

    def listening_freeze(self, t0: float, t1: float, *, gaze: tuple[float, float] = (5, 0), tilt: float = 6,
                         tremor: float = .7) -> "ActorBuilder":
        """Root and both feet stay exactly fixed; only gaze, head lean and a tiny hand tremor move."""
        self._start("listening_freeze", t0, t1, gaze=list(gaze))
        settle = min(t1, t0 + .3)
        posture = [self.posture[0] - 2, self.posture[1] - 3, self.posture[2] - 4, self.posture[3] - 3]
        face = [1.1, gaze[0], gaze[1], -.65, 0, tilt]
        self._key(settle, posture=posture, face=face)
        self.posture, self.face = posture, face
        steps = max(0, int((t1 - settle) / .13))
        base = {h: list(self.pose[h]) for h in ("left_hand", "right_hand")}
        for i in range(1, steps):
            s = tremor * (1 if i % 2 else -1) * (1 - i / steps)
            self._key(settle + i * .13, left_hand=[base["left_hand"][0] + s, base["left_hand"][1] - s * .6],
                      right_hand=[base["right_hand"][0] - s, base["right_hand"][1] + s * .5])
        self._key(t1)
        self.t = t1
        return self

    def guarded_reach(self, target: list[float], t0: float, t1: float, *, hand: str = "right_hand") -> "ActorBuilder":
        """Hesitant reach to a world anchor; feet planted; contact is held exactly from t1."""
        self._start("guarded_reach", t0, t1, target=list(target), hand=hand)
        posture = [self.rest[0] + 5, self.rest[1] - 2, self.rest[2] + 8, self.rest[3] - 1]
        root = self.pose["root"]
        shoulder = [root[0] + self.facing * posture[0], root[1] + posture[1]]
        reach = math.dist(shoulder, target)
        if not abs(ARM[0] - ARM[1]) + 1 < reach < sum(ARM) - 3:
            raise ValueError(f"{self.id}: anchor {target} unreachable from stance x={root[0]:.0f} ({reach:.1f})")
        start = list(self.pose[hand])
        lerp = lambda a, u: [start[0] + (target[0] - start[0]) * u, start[1] + (target[1] - start[1]) * u]  # noqa: E731
        span = t1 - t0
        for u, at, jitter in ((.45, .3, (0, 0)), (.42, .42, (-1.5, 2)), (.62, .6, (0, 0)), (.6, .7, (1, -1)), (.88, .86, (0, 0))):
            p = lerp(start, u)
            self._key(t0 + span * at, **{hand: [p[0] + jitter[0], p[1] + jitter[1]]},
                      posture=[self.posture[i] + (posture[i] - self.posture[i]) * at for i in range(4)])
        self.posture = posture
        self.face = [1, 5, -1, -.5, 0, -2]
        self.pose[hand] = list(target)
        self._key(t1)
        self.t = t1
        return self

    def build(self, length: float) -> dict:
        if length < self.t - 1e-9:
            raise ValueError("Shot shorter than the performance")
        self._key(length)
        return {"id": self.id, "look": self.look, **{k: self.keys[k] for k in TRACKS},
                "posture": self.keys["posture"], "face": self.keys["face"],
                "facing_keys": [[0, self.facing]], "opacity": [[0, 1], [length, 1]]}


def rest_hand(x: float, y: float, hand: str, facing: int = 1) -> list[float]:
    u, dy = REST[hand]
    return [x + facing * u, y + dy]
