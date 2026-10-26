"""P3.4 canonical story-to-scene planning over verified reviewed canon and an approved Visual Bible.

Source facts (chapters, beats, narration, canonical IDs and evidence) are copied
read-only from the reviewed Short/Long format plans; nothing here reinterprets the
story text. Staging (framing, camera, blocking, performance, lighting state, prop
interaction) is a creative proposal from a closed vocabulary. Executable motion is
limited to P3.2A acting presets and is dry-run through `ActorBuilder`; anything the
renderer cannot act becomes an explicit blocker or an editorial decision. Timing is
a provisional estimate: no TTS, measured audio, rendering or publishing happens here.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

import jsonschema

from lib.fiction_story import DURATION_BASIS, SYLLABLES_PER_SECOND, syllables
from lib.reviewed_fiction import mapped_spans
from lib.story_visual_bible import fingerprint, library_ref
from tools.character import horror_assets as assets
from tools.character.horror_acting import MAX_CAUTIOUS_SPEED, ActorBuilder

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas/story/story_scene_plan.schema.json"
ACTION_TIMELINE_SCHEMA = ROOT / "schemas/artifacts/action_timeline.schema.json"
STYLE = "cinematic_2d_cartoon_supernatural_horror"
FPS, LEAD, TAIL, MIN_SHOT = 30, 0.3, 0.4, 1.5  # Same frame grid and narration lead/tail as story_planner.
WALK_SPEED = 45.0  # Below P3.2A's cautious-walk cap.
WORLD_W, WORLD_H, PAD = 1280, 720, 80
FRAMES = {"short": {"format_id": "FMT_SHORT", "aspect_ratio": "9:16", "viewport": {"width": 1080, "height": 1920}},
          "long": {"format_id": "FMT_LONG", "aspect_ratio": "16:9", "viewport": {"width": 1920, "height": 1080}}}
SHORT_TARGET = {"min": 45, "max": 60}

# Capability statuses, least to most severe.
STATUSES = ("supported_direct", "supported_parameterized", "editorial_review", "requires_new_capability")
SHOT_SIZES = {"establishing_wide": (1.0, 360), "wide": (1.15, 380), "medium": (1.55, 450),
              "medium_close": (1.9, 410), "close_up": (2.4, 370)}  # zoom, camera centre y
CAMERA_MOVES = {
    "static": ("supported_direct", "Static StoryVideo camera keys."),
    "slow_push_in": ("supported_parameterized", "Camera zoom keys (+18%) kept inside the artwork."),
    "slow_pull_out": ("supported_parameterized", "Camera zoom keys (-18%) kept inside the artwork."),
    "slow_pan": ("supported_parameterized", "Camera x keys from the start to the end subjects."),
    "handheld_drift": ("requires_new_capability", "StoryVideo has no camera-shake/handheld track."),
    "dolly_zoom": ("requires_new_capability", "The 2D camera has no focal-length/perspective model."),
}
PERFORMANCES = {  # status, P3.2A acting asset, minimum seconds, basis
    "hold": ("supported_direct", None, 0.5, "ActorBuilder.hold keeps the current pose."),
    "listening_freeze": ("supported_parameterized", "listening_freeze", 1.2, "P3.2A preset; gaze/tilt parameters."),
    "startled_reaction": ("supported_parameterized", "startled_reaction", 1.2, "P3.2A preset; direction/strength parameters."),
    "turn_around": ("requires_new_capability", None, 0, "Facing flips instantly; no articulated body rotation."),
    "grasp_object": ("requires_new_capability", None, 0, "No independently animated fingers or grasp contact."),
    "run": ("requires_new_capability", None, 0, f"cautious_walk is capped at {MAX_CAUTIOUS_SPEED} px/s; no run cycle."),
    "offscreen_action": ("editorial_review", None, 0, "The action is implied off-frame or across a cut."),
}
EMOTIONS = ("wary", "tense", "fearful", "startled", "resolute", "numb")
ENTRIES = ("present_at_cut", "revealed_by_framing", "enter_walk")
TRANSITIONS = ("cut", "time_ellipsis", "continuous")
LIGHTING_STATES = {
    "steady": ("supported_direct", "Pinned Visual Bible lighting without bursts."),
    "flicker_bursts": ("supported_parameterized", "Deterministic flicker_track bursts; needs flickering_interior."),
    "blackout": ("requires_new_capability", "No sustained blackout track; flicker bursts only dip briefly."),
}
PRESENCE = ("visible_partial", "hidden")
DIALOGUE_DELIVERY = {
    "on_screen_speech": ("requires_new_capability", "No lip-sync or dialogue acting preset exists."),
    "voice_over_narration": ("editorial_review", "The narrator reads the line; the speaker does not lip-sync."),
    "offscreen_voice": ("editorial_review", "The speaker is heard while kept out of frame."),
}
PROP_INTERACTIONS = {  # prop asset -> interaction -> (status, resulting state, basis)
    "interior_door": {
        "visible_in_set": ("supported_direct", None, "Door is shown in its current state."),
        "reach_handle": ("supported_parameterized", None, "guarded_reach to the pinned handle anchor."),
        "reach_then_opened_across_cut": ("editorial_review", "open", "guarded_reach to the handle; the door is open after "
                                         "the next cut. The opening itself is not animated."),
        "open_door": ("requires_new_capability", "open", "No hand-to-door coupling; acting cannot drive the door leaf."),
        "door_opened_across_cut": ("editorial_review", "open", "Closed before, open after a cut; opening is not animated."),
        "door_closed_across_cut": ("editorial_review", "closed", "Open before, closed after a cut; closing is not animated."),
    },
    "sash_window": {"visible_in_set": ("supported_direct", None, "Window shown as designed."),
                    "open_window": ("requires_new_capability", "open", "No window-opening animation.")},
    "ceiling_lamp": {"visible_in_set": ("supported_direct", None, "Lamp state follows the shot lighting state.")},
    "floor_lamp": {"visible_in_set": ("supported_direct", None, "Lamp state follows the shot lighting state.")},
}
INITIAL_PROP_STATE = {"interior_door": "closed", "sash_window": "closed", "ceiling_lamp": "lit_steady",
                      "floor_lamp": "lit_steady"}
LAMPS = ("ceiling_lamp", "floor_lamp")
REACH = ("reach_handle", "reach_then_opened_across_cut")
NOT_EXECUTABLE = "Descriptive reviewed staging text; never compiled into motion."


class ScenePlanError(ValueError):
    def __init__(self, code, message, blockers=None):
        super().__init__(message)
        self.code, self.blockers = code, blockers or []


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _frames(seconds: float) -> int:
    return int(math.ceil(round(seconds * FPS, 6)))


def half_width(fmt: str) -> float:
    v = FRAMES[fmt]["viewport"]
    return v["width"] * WORLD_H / v["height"] / 2


def vocabulary() -> dict:
    """Closed staging vocabulary with honest capability statuses, for Studio controls and reports."""
    return {"statuses": list(STATUSES), "shot_sizes": list(SHOT_SIZES),
            "camera_moves": {k: {"status": s, "basis": b} for k, (s, b) in CAMERA_MOVES.items()},
            "performances": {k: {"status": s, "acting_asset": a, "minimum_seconds": m, "basis": b}
                             for k, (s, a, m, b) in PERFORMANCES.items()},
            "emotions": list(EMOTIONS), "entries": list(ENTRIES), "transitions": list(TRANSITIONS),
            "lighting_states": {k: {"status": s, "basis": b} for k, (s, b) in LIGHTING_STATES.items()},
            "presence": list(PRESENCE),
            "dialogue_delivery": {k: {"status": s, "basis": b} for k, (s, b) in DIALOGUE_DELIVERY.items()},
            "prop_interactions": {p: {k: {"status": s, "state_after": st, "basis": b} for k, (s, st, b) in v.items()}
                                  for p, v in PROP_INTERACTIONS.items()},
            "locomotion": {"cautious_walk": {"status": "supported_parameterized", "speed_px_per_second": WALK_SPEED,
                                             "basis": "Derived from blocking marks; P3.2A cautious_walk preset."}}}


def acting_pin(preset: str) -> dict:
    a = assets.get("acting", preset, 1)
    return {"kind": "acting", "id": a["id"], "revision": a["revision"], "sha256": assets.content_hash(a)}


# ------------------------------------------------------------------ structure (canon -> skeleton)

def _by_id(rows, key="canonical_id"):
    return {r[key]: r for r in rows}


def _marks(location: dict, props: list[dict]) -> tuple[dict, dict]:
    """Blocking marks from the pinned environment walk range and door-handle anchors."""
    a, b = location["anchors"]["walk_range"]
    c = (a + b) / 2
    marks = {"left": a + .18 * (b - a), "centre_left": c - 110, "centre": c, "centre_right": c + 110,
             "right": b - .18 * (b - a)}
    facing = {}
    for p in props:
        if p["location_id"] == location["canonical_id"] and p["asset"] and p["asset"]["id"] == "interior_door" and p["point"]:
            hx = p["point"][0]
            f = 1 if hx - 68 >= a else -1
            marks[f"reach:{p['canonical_id']}"] = hx - f * 68
            facing[f"reach:{p['canonical_id']}"] = f
    return {k: round(v, 1) for k, v in marks.items()}, facing


def _dialogue_in(beat: dict, canon: dict) -> list[dict]:
    segs = {s["id"]: s for s in canon["segments"]}
    ranges = [(segs[s["segment_id"]]["char_start"] + s["char_start"], segs[s["segment_id"]]["char_start"] + s["char_end"])
              for s in beat["narration"]["sources"]]
    out = []
    for d in canon["dialogue"]:
        e = d["evidence"][0]
        start = segs[e["segment_id"]]["char_start"] + e["char_start"]
        end = segs[e["segment_id"]]["char_start"] + e["char_end"]
        if any(a <= start and end <= b for a, b in ranges):
            out.append({"id": d["id"], "channel": d["channel"], "speaker_id": d["speaker_id"], "text": d["text"],
                        "attribution_status": d["attribution_status"]})
    return out


def _related(canon: dict, ids: set[str]) -> tuple[list[str], list[str]]:
    amb = [a["id"] for a in canon["ambiguities"] if ids & set(a["related_ids"])]
    rules = [r["id"] for r in canon["continuity_rules"] if ids & set(r["related_ids"])]
    return amb, rules


def structure(reviewed: dict, handoff: dict) -> dict:
    """Deterministic skeleton: chapters -> scenes -> shots, per-shot options and default choices."""
    canon = reviewed["canonical_story"]
    chars, locs, props = _by_id(handoff["characters"]), _by_id(handoff["locations"]), handoff["props"]
    events = {e["id"]: e for e in canon["events"]}
    sounds = {s["id"]: s for s in canon["sound_cues"]}
    facts = {f["id"]: f for f in canon["facts"]}
    formats, defaults = {}, {"formats": {}, "coverage_reviewed": False, "continuity_reviewed": False}
    for fmt in ("short", "long"):
        plan = canon["formats"].get(fmt)
        if plan is None:
            raise ScenePlanError("canonical_not_ready", f"The reviewed story has no approved {fmt} plan.")
        letter = fmt[0].upper()
        scenes, shots, chapters = [], [], []
        dshots, dscenes = {}, {}
        state = {}  # character -> (location, mark), for default blocking only
        prev_loc = None
        for chapter in plan["chapters"]:
            chapter_scenes = []
            for beat in chapter["beats"]:
                loc = beat["location_id"]
                if not chapter_scenes or scenes[-1]["location_id"] != loc:
                    sid = f"SC_{letter}_{len(scenes) + 1:02d}"
                    first_events = [events[e] for e in beat["event_ids"] if e in events]
                    timed = any(e["time_markers"] for e in first_events)
                    scenes.append({"scene_id": sid, "chapter_id": chapter["id"], "location_id": loc,
                                   "beat_ids": [], "shot_ids": [], "location_change": prev_loc not in (None, loc),
                                   "canonical_time_markers": [m for e in first_events for m in e["time_markers"]]})
                    chapter_scenes.append(sid)
                    dscenes[sid] = {"transition": "time_ellipsis" if timed else "cut", "reviewed": False}
                scene = scenes[-1]
                scene["beat_ids"].append(beat["id"])
                prev_loc = loc
                location = locs.get(loc)
                marks, reach_facing = _marks(location, props) if location and location["anchors"] else ({}, {})
                cast = [c for c in beat["character_ids"] if chars.get(c, {}).get("representation") == "character"]
                partial = [c for c in beat["character_ids"] if chars.get(c, {}).get("representation") == "silhouette"]
                hidden = [c for c in beat["character_ids"] if c not in cast and c not in partial]
                presence = location.get("presence") if location else None
                ids = set(beat["event_ids"]) | set(beat["character_ids"]) | set(beat["object_ids"]) | set(beat["sound_cue_ids"])
                ids |= {f for e in beat["event_ids"] if e in events for f in events[e]["fact_ids"]}
                ambiguities, rules = _related(canon, ids)
                dialogue = _dialogue_in(beat, canon)
                prop_rows = [p for p in props if p["canonical_id"] in beat["object_ids"]]
                source = {
                    "beat_id": beat["id"], "chapter_id": chapter["id"], "event_ids": list(beat["event_ids"]),
                    "character_ids": list(beat["character_ids"]), "location_id": loc,
                    "object_ids": list(beat["object_ids"]), "sound_cue_ids": list(beat["sound_cue_ids"]),
                    "narration": {"mode": beat["narration"]["mode"], "text": beat["narration"]["text"],
                                  "sources": copy.deepcopy(beat["narration"]["sources"]),
                                  "working_spans": copy.deepcopy(beat["narration"]["working_spans"]),
                                  "attribution": "verbatim_reviewed_source" if beat["narration"]["mode"] == "verbatim"
                                  else "explicitly_accepted_authored_proposal"},
                    "dialogue": dialogue,
                    "facts": [{"id": f, "kind": facts[f]["kind"], "reported_by": facts[f]["reported_by"]}
                              for e in beat["event_ids"] if e in events for f in events[e]["fact_ids"] if f in facts],
                    "ambiguity_ids": ambiguities, "continuity_rule_ids": rules,
                    "reviewed_staging": {**copy.deepcopy(beat["staging"]), "basis": "reviewed_story_staging_proposal",
                                         "executable": False, "note": NOT_EXECUTABLE},
                    "silence_after_seconds": beat["silence_after_seconds"]}
                sounds_here = [sounds[s] for s in beat["sound_cue_ids"] if s in sounds]
                reveal = bool(beat["staging"]["reveal"])
                lighting_id = location["lighting"]["id"] if location and location["lighting"] else None
                electronic = any(s["kind"] == "electronic" for s in sounds_here)
                light_default = "flicker_bursts" if lighting_id == "flickering_interior" and electronic else "steady"
                presence_default = ("visible_partial" if presence and presence["character_id"] in partial else "hidden")
                # Default blocking: keep known marks, otherwise take the first free slot.
                taken = {m for c, (l, m) in state.items() if l == loc and c not in cast}
                dcast = {}
                for cid in cast:
                    known = state.get(cid)
                    if known and known[0] == loc and known[1] in marks:
                        mark = known[1]
                    else:
                        mark = next((m for m in ("centre", "centre_right", "centre_left", "left", "right")
                                     if m in marks and m not in taken), "centre")
                    taken.add(mark)
                    first_shot = not scene["shot_ids"]
                    if known and known[0] == loc or first_shot:
                        entry = "present_at_cut"
                    elif _earlier_event_here(canon, beat, cid, loc):
                        entry = "revealed_by_framing"
                    else:
                        entry = "enter_walk"
                    perf = "listening_freeze" if sounds_here or reveal else "hold"
                    emotion = "fearful" if reveal or presence_default == "visible_partial" else ("tense" if sounds_here else "wary")
                    dcast[cid] = {"performance": perf, "emotion": emotion, "mark": mark, "entry": entry}
                    state[cid] = (loc, mark)
                shot_options = {"marks": marks, "reach_facing": reach_facing,
                                "props": {p["canonical_id"]: sorted(PROP_INTERACTIONS.get(p["asset"]["id"], {"visible_in_set": 0}))
                                          if p["asset"] else ["visible_in_set"] for p in prop_rows},
                                "presence": list(PRESENCE) if presence and presence["character_id"] in partial else ["hidden"],
                                "lighting_states": list(LIGHTING_STATES)}
                speaker_shown = {d["id"]: ("on_screen_speech" if d["speaker_id"] in cast else "offscreen_voice")
                                 for d in dialogue if d["channel"] in ("speech", "voice_unseen")}
                n = len(shots) + 1
                primary = {"shot_id": f"SH_{letter}_{n:03d}", "kind": "narrative", "scene_id": scene["scene_id"],
                           "chapter_id": chapter["id"], "source": source, "options": shot_options,
                           "cast_ids": cast, "partial_ids": partial, "unseen_ids": hidden, "reaction_follows": False}
                shots.append(primary)
                scene["shot_ids"].append(primary["shot_id"])
                multi = len(cast) > 1
                size = ("establishing_wide" if fmt == "long" else "wide") if len(scene["shot_ids"]) == 1 else \
                    ("wide" if reveal or (multi and fmt == "short") else "medium")
                move = "slow_push_in" if reveal else ("slow_pan" if any(v["entry"] == "enter_walk" for v in dcast.values()) else "static")
                dshots[primary["shot_id"]] = {"shot_size": size, "camera_move": move, "lighting_state": light_default,
                                              "presence": presence_default, "cast": dcast,
                                              "props": {p["canonical_id"]: "visible_in_set" for p in prop_rows},
                                              "dialogue": speaker_shown, "editorial_acknowledged": False}
                if (sounds_here or reveal) and cast and beat["silence_after_seconds"] >= 1.5:
                    primary["reaction_follows"] = True
                    reaction = {"shot_id": f"SH_{letter}_{n + 1:03d}", "kind": "reaction_hold", "scene_id": scene["scene_id"],
                                "chapter_id": chapter["id"], "source": source, "options": shot_options,
                                "cast_ids": cast, "partial_ids": partial, "unseen_ids": hidden, "reaction_follows": False}
                    shots.append(reaction)
                    scene["shot_ids"].append(reaction["shot_id"])
                    dshots[reaction["shot_id"]] = {
                        "shot_size": "medium_close", "camera_move": "static", "lighting_state": light_default,
                        "presence": presence_default,
                        "cast": {c: {"performance": "listening_freeze", "emotion": dcast[c]["emotion"]} for c in cast},
                        "props": {}, "dialogue": {}, "editorial_acknowledged": False}
            chapters.append({"chapter_id": chapter["id"], "title": chapter["title"], "scene_ids": chapter_scenes})
        formats[fmt] = {"chapters": chapters, "scenes": scenes, "shots": shots}
        defaults["formats"][fmt] = {"scenes": dscenes, "shots": dshots}
    return {"formats": formats, "defaults": defaults}


def _earlier_event_here(canon, beat, cid, loc) -> bool:
    first = min((e["narrative_order"] for e in canon["events"] if e["id"] in beat["event_ids"]), default=0)
    return any(e["narrative_order"] < first and e["location_id"] == loc and cid in e["participant_ids"]
               for e in canon["events"])


def default_choices(reviewed: dict, handoff: dict) -> dict:
    return copy.deepcopy(structure(reviewed, handoff)["defaults"])


def rebase_choices(reviewed: dict, handoff: dict, previous: dict | None) -> dict:
    """Carry still-valid staging into a new canon/visual input; every review flag is cleared."""
    skeleton = structure(reviewed, handoff)
    result = copy.deepcopy(skeleton["defaults"])
    if not isinstance(previous, dict):
        return result
    for fmt, plan in result["formats"].items():
        old = (previous.get("formats") or {}).get(fmt) or {}
        shots = {s["shot_id"]: s for s in skeleton["formats"][fmt]["shots"]}
        for sid, row in plan["scenes"].items():
            value = ((old.get("scenes") or {}).get(sid) or {}).get("transition")
            if value in TRANSITIONS:
                row["transition"] = value
        for sid, row in plan["shots"].items():
            prior = (old.get("shots") or {}).get(sid)
            if not isinstance(prior, dict) or prior.get("cast", {}).keys() != row["cast"].keys():
                continue
            options = shots[sid]["options"]
            for key, allowed in (("shot_size", SHOT_SIZES), ("camera_move", CAMERA_MOVES),
                                 ("lighting_state", LIGHTING_STATES), ("presence", options["presence"])):
                if prior.get(key) in allowed:
                    row[key] = prior[key]
            for cid, cast in row["cast"].items():
                for key, allowed in (("performance", PERFORMANCES), ("emotion", EMOTIONS),
                                     ("mark", options["marks"]), ("entry", ENTRIES)):
                    if key in cast and prior["cast"][cid].get(key) in allowed:
                        cast[key] = prior["cast"][cid][key]
            for oid in row["props"]:
                if (prior.get("props") or {}).get(oid) in options["props"].get(oid, ()):
                    row["props"][oid] = prior["props"][oid]
            for did in row["dialogue"]:
                if (prior.get("dialogue") or {}).get(did) in DIALOGUE_DELIVERY:
                    row["dialogue"][did] = prior["dialogue"][did]
    return result


# ------------------------------------------------------------------ choices validation

def _exact(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ScenePlanError("invalid_choice", f"{label}: expected exactly {sorted(keys)}.")


def _one_of(value, allowed, label):
    if not isinstance(value, str) or value not in allowed:
        raise ScenePlanError("invalid_choice", f"{label}: unsupported value {value!r}.")


def check_choices(skeleton: dict, choices: dict) -> None:
    """Structure must match the canon-derived skeleton exactly; shots/beats cannot be added or removed."""
    defaults = skeleton["defaults"]
    _exact(choices, defaults, "Scene plan choices")
    for key in ("coverage_reviewed", "continuity_reviewed"):
        if type(choices[key]) is not bool:
            raise ScenePlanError("invalid_choice", f"{key} must be boolean.")
    _exact(choices["formats"], defaults["formats"], "Formats")
    for fmt, plan in defaults["formats"].items():
        given = choices["formats"][fmt]
        _exact(given, plan, fmt)
        _exact(given["scenes"], plan["scenes"], f"{fmt} scenes")
        _exact(given["shots"], plan["shots"], f"{fmt} shots")
        shots = {s["shot_id"]: s for s in skeleton["formats"][fmt]["shots"]}
        for sid, row in given["scenes"].items():
            _exact(row, {"transition", "reviewed"}, sid)
            _one_of(row["transition"], TRANSITIONS, f"{sid} transition")
            if type(row["reviewed"]) is not bool:
                raise ScenePlanError("invalid_choice", f"{sid}: review acknowledgement must be boolean.")
        for sid, row in given["shots"].items():
            default, options = plan["shots"][sid], shots[sid]["options"]
            _exact(row, default, sid)
            _one_of(row["shot_size"], SHOT_SIZES, f"{sid} shot size")
            _one_of(row["camera_move"], CAMERA_MOVES, f"{sid} camera move")
            _one_of(row["lighting_state"], LIGHTING_STATES, f"{sid} lighting state")
            _one_of(row["presence"], options["presence"], f"{sid} presence")  # Only beats listing the partial character.
            if type(row["editorial_acknowledged"]) is not bool:
                raise ScenePlanError("invalid_choice", f"{sid}: editorial acknowledgement must be boolean.")
            _exact(row["cast"], default["cast"], f"{sid} cast")
            for cid, cast in row["cast"].items():
                _exact(cast, default["cast"][cid], f"{sid}.{cid}")
                _one_of(cast["performance"], PERFORMANCES, f"{sid}.{cid} performance")
                _one_of(cast["emotion"], EMOTIONS, f"{sid}.{cid} emotion")
                if "mark" in cast:
                    _one_of(cast["mark"], options["marks"], f"{sid}.{cid} mark")
                    _one_of(cast["entry"], ENTRIES, f"{sid}.{cid} entry")
            _exact(row["props"], default["props"], f"{sid} props")
            for oid, value in row["props"].items():
                _one_of(value, options["props"][oid], f"{sid}.{oid} interaction")
            _exact(row["dialogue"], default["dialogue"], f"{sid} dialogue")
            for did, value in row["dialogue"].items():
                _one_of(value, DIALOGUE_DELIVERY, f"{sid}.{did} delivery")


# ------------------------------------------------------------------ compile

def _status(items) -> str:
    return max((i["status"] for i in items), key=STATUSES.index, default="supported_direct")


def _camera(fmt, size, move, subjects, length):
    """Executable StoryVideo camera keys [t, cx, cy, zoom]; subjects are (label, x) in priority order."""
    zoom, cy_target = SHOT_SIZES[size]
    peak = zoom * (1.18 if move in ("slow_push_in", "slow_pull_out") else 1)
    hw = half_width(fmt)
    framed, out = [], []
    for label, x in subjects:
        xs = [s[1] for s in framed] + [x]
        if not framed or max(xs) - min(xs) + 2 * PAD <= 2 * hw / peak:
            framed.append((label, x))
        else:
            out.append(label)

    def inside(value, lo, hi):  # Round inward so rounding never pushes the frame past the artwork.
        return min(max(round(value, 3), math.ceil(lo * 1000) / 1000), math.floor(hi * 1000) / 1000)

    def centre(z, xs):
        cx = (min(xs) + max(xs)) / 2 if xs else WORLD_W / 2
        return [inside(cx, hw / z, WORLD_W - hw / z), inside(cy_target, WORLD_H / 2 / z, WORLD_H - WORLD_H / 2 / z), z]

    xs, peak = [x for _, x in framed], round(peak, 4)
    if move == "slow_push_in":
        keys = [[0, *centre(zoom, xs)], [length, *centre(peak, xs)]]
    elif move == "slow_pull_out":
        keys = [[0, *centre(peak, xs)], [length, *centre(zoom, xs)]]
    else:
        keys = [[0, *centre(zoom, xs)], [length, *centre(zoom, xs)]]
    for t, cx, cy, z in keys:  # Same artwork bounds StoryVideo enforces per frame.
        if cx - hw / z < -1e-6 or cx + hw / z > WORLD_W + 1e-6 or cy - 360 / z < -1e-6 or cy + 360 / z > WORLD_H + 1e-6:
            raise ScenePlanError("plan_invalid", "Camera leaves the artwork.")
    lost = [label for label, x in framed if any(abs(x - k[1]) > hw / k[3] - 20 for k in keys)]
    shown = list(dict.fromkeys(label for label, _ in framed if label not in lost))
    return {"keys": [[round(k[0], 4), *k[1:]] for k in keys], "framed_subjects": shown,
            "framed_out": list(dict.fromkeys(label for label in out + lost if label not in shown)),
            "visible_world_width": round(2 * hw / peak, 1)}


def compile_plan(project_id: str, version: str, reviewed: dict, handoff: dict, inputs: dict, choices: dict) -> dict:
    canon = reviewed["canonical_story"]
    if library_ref() != handoff["library"]:
        raise ScenePlanError("visual_not_ready", "Pinned asset library changed; no revision was substituted.")
    skeleton = structure(reviewed, handoff)
    check_choices(skeleton, choices)
    chars, locs = _by_id(handoff["characters"]), _by_id(handoff["locations"])
    props = _by_id(handoff["props"])
    sounds = {s["id"]: s for s in canon["sound_cues"]}
    blockers, warnings = [], []
    language_note = (f" Language '{canon['language']}' differs from the Vietnamese measurement basis; low confidence."
                     if canon["language"] != "vi" else "")
    formats = {}
    for fmt in ("short", "long"):
        sk, picks = skeleton["formats"][fmt], choices["formats"][fmt]
        state = _initial_state(canon, handoff)
        scene_by_id = {s["scene_id"]: s for s in sk["scenes"]}
        shots, clock = [], 0.0
        prev_scene = None
        for raw in sk["shots"]:
            pick = picks["shots"][raw["shot_id"]]
            scene = scene_by_id[raw["scene_id"]]
            new_scene = raw["scene_id"] != prev_scene
            transition = picks["scenes"][raw["scene_id"]]["transition"]
            shot = _compile_shot(fmt, raw, pick, scene, new_scene, transition, state, chars, locs, props, sounds, canon)
            shot["order"] = len(shots) + 1
            timing = shot["timing"]
            timing["format_start_seconds"] = round(clock, 4)
            timing["frame_grid"]["estimated_start_frame"] = _frames(clock)
            if timing["narration"]["interval_seconds"]:
                a, b = timing["narration"]["interval_seconds"]
                timing["narration"]["format_interval_seconds"] = [round(clock + a, 3), round(clock + b, 3)]
            clock = (timing["frame_grid"]["estimated_start_frame"] + timing["frame_grid"]["estimated_frame_count"]) / FPS
            for b in shot["blockers"]:
                blockers.append(f"{fmt.upper()} {raw['shot_id']} {b}")
            shots.append(shot)
            prev_scene = raw["scene_id"]
        scenes = []
        for s in sk["scenes"]:
            own = [x for x in shots if x["scene_id"] == s["scene_id"]]
            location = locs.get(s["location_id"]) or {}
            row = {**copy.deepcopy(s), "order": len(scenes) + 1, "environment": copy.deepcopy(location.get("environment")),
                   "lighting": copy.deepcopy(location.get("lighting")), "atmosphere": location.get("atmosphere"),
                   "transition_in": picks["scenes"][s["scene_id"]]["transition"],
                   "reviewed": picks["scenes"][s["scene_id"]]["reviewed"],
                   "estimated_seconds": round(sum(x["timing"]["estimated_seconds"] for x in own), 3)}
            if row["location_change"] and row["transition_in"] == "continuous":
                blockers.append(f"{fmt.upper()} {s['scene_id']} ACCIDENTAL_TELEPORT: a location change cannot be a continuous "
                                "shot; use an intentional cut or time ellipsis.")
            if not row["reviewed"]:
                blockers.append(f"{fmt.upper()} {s['scene_id']} UNREVIEWED_SCENE: confirm its structured motion plans "
                                "represent the reviewed staging and narration.")
            scenes.append(row)
        total = round(clock, 3)
        narration = round(sum(x["timing"]["narration"]["estimated_seconds"] for x in shots), 3)
        silence = round(sum(x["timing"]["planned_silence_seconds"] for x in shots), 3)
        timing = {"status": "provisional_estimate_pending_measured_narration",
                  "estimate_basis": DURATION_BASIS + language_note, "estimated_seconds": total,
                  "estimated_narration_seconds": narration, "planned_silence_seconds": silence,
                  "action_and_framing_seconds": round(total - narration - silence, 3)}
        if fmt == "short":
            target = "within" if SHORT_TARGET["min"] <= total <= SHORT_TARGET["max"] else (
                "below" if total < SHORT_TARGET["min"] else "above")
            timing["target"] = {**SHORT_TARGET, "estimate_relation": target, "enforced": False,
                                "policy": "Never pad, cut or rewrite story content to reach the target; confirm after "
                                          "P3.5 measured narration."}
            if target != "within":
                warnings.append(f"SHORT estimate {total} s is {target} the 45-60 s target; no content was changed.")
        else:
            timing["target"] = None
        formats[fmt] = {"format": fmt, **copy.deepcopy(FRAMES[fmt]), "fps": FPS,
                        "intent": canon["formats"][fmt].get("intent", ""), "chapters": copy.deepcopy(sk["chapters"]),
                        "scenes": scenes, "shots": shots, "timing": timing,
                        "capability_summary": {s: sum(1 for x in shots if x["capability"]["status"] == s) for s in STATUSES},
                        "end_state": state}
    result = {
        "schema_version": "1.0", "artifact": "story_scene_plan", "project_id": project_id, "version": version,
        "style": STYLE, "inputs": copy.deepcopy(inputs), "language": canon["language"], "title": canon["title"],
        "source_facts_policy": "Source fields are copied read-only from the approved reviewed format plans.",
        "staging_policy": "Staging fields are creative proposals, not canonical facts; no invented events, identities, "
                          "dialogue or supernatural explanations.",
        "formats": formats,
        "shared_identity": {"characters": copy.deepcopy(handoff["formats"]["long"]["characters"]),
                            "locations": copy.deepcopy(handoff["formats"]["long"]["locations"])},
        "retiming_contract": None, "coverage": None, "continuity": None,
        "review": {"coverage_reviewed": choices["coverage_reviewed"], "continuity_reviewed": choices["continuity_reviewed"]},
        "warnings": warnings, "blockers": [],
        "review_status": "pending_explicit_scene_plan_approval", "approval_scope": "scene_plan_only",
        "tts_started": False, "rendering_started": False, "production_started": False, "publishing_enabled": False}
    result["coverage"] = coverage(result, reviewed)
    result["continuity"] = continuity(result, canon, handoff)
    result["retiming_contract"] = retiming_contract(result)
    for fmt in formats:
        result["formats"][fmt].pop("end_state")
    blockers += result["coverage"]["blockers"] + result["continuity"]["blockers"]
    if not choices["coverage_reviewed"]:
        blockers.append("UNREVIEWED_COVERAGE: review Short and Long story-to-shot coverage.")
    if not choices["continuity_reviewed"]:
        blockers.append("UNREVIEWED_CONTINUITY: review character, prop, lighting and revelation continuity.")
    result["blockers"] = list(dict.fromkeys(blockers))
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(result)
    return result


def _initial_state(canon, handoff):
    props = {}
    for p in handoff["props"]:
        kind = p["asset"]["id"] if p["asset"] else None
        props[p["canonical_id"]] = {"location_id": p["location_id"], "anchor": p["anchor"],
                                    "state": INITIAL_PROP_STATE.get(kind, "as_designed"), "owner_id": None}
    return {"characters": {c["canonical_id"]: {"location_id": None, "mark": None, "x": None, "facing": None,
                                               "visible": False, "performance": None, "emotion": None,
                                               "representation": c["representation"]} for c in handoff["characters"]},
            "props": props,
            "lighting": {l["canonical_id"]: {"preset": l["lighting"]["id"] if l["lighting"] else None, "state": "steady"}
                         for l in handoff["locations"]},
            "presence": {c["canonical_id"]: "not_shown" for c in handoff["characters"] if c["representation"] == "silhouette"},
            "revelation": {a["id"]: a["status"] for a in canon["ambiguities"]}}


def _snapshot(state, loc, ids):
    return {"characters": {c: copy.deepcopy(v) for c, v in state["characters"].items()
                           if c in ids or v["location_id"] == loc},
            "props": {o: copy.deepcopy(v) for o, v in state["props"].items() if v["location_id"] == loc},
            "lighting": {loc: copy.deepcopy(state["lighting"].get(loc))},
            "presence": copy.deepcopy(state["presence"]), "revelation": copy.deepcopy(state["revelation"])}


def _compile_shot(fmt, raw, pick, scene, new_scene, transition, state, chars, locs, props, sounds, canon):
    src, opts = raw["source"], raw["options"]
    loc = src["location_id"]
    location = locs.get(loc) or {}
    items, blockers, notes = [], [], []
    before = _snapshot(state, loc, set(src["character_ids"]))

    def need(kind, subject, status, basis, **extra):
        items.append({"requirement": kind, "subject": subject, "status": status, "basis": basis, **extra})

    if not location.get("environment") or not location.get("geometry"):
        need("environment", loc, "requires_new_capability", "No approved environment/lighting binding for this location.")
    marks, reach_facing = opts["marks"], opts["reach_facing"]
    # Prop interactions (reach actor is the first visible cast member).
    prop_rows, reach = [], None
    for oid in src["object_ids"]:
        p = props.get(oid)
        choice = pick["props"].get(oid, "visible_in_set")
        kind = p["asset"]["id"] if p and p["asset"] else None
        status, state_after, basis = PROP_INTERACTIONS.get(kind, {}).get(
            choice, ("requires_new_capability", None, "No supported prop asset/anchor."))
        actor = None
        if p is None or p["point"] is None:
            need("prop", oid, "requires_new_capability", "Prop has no supported asset and interaction anchor.")
        elif p["location_id"] != loc:
            need("prop", oid, "requires_new_capability", "Prop is bound to another location; moving props need new states.")
        if choice in REACH:
            actor = raw["cast_ids"][0] if raw["cast_ids"] else None
            if actor is None:
                status, basis = "requires_new_capability", "No visible character can reach this anchor."
            else:
                reach = (actor, oid, p["point"])
        need("prop_interaction", oid, status, basis, interaction=choice)
        prop_rows.append({"object_id": oid, "asset": copy.deepcopy(p["asset"]) if p else None,
                          "anchor": p["anchor"] if p else None, "point": copy.deepcopy(p["point"]) if p else None,
                          "interaction": choice, "actor_id": actor, "state_after": state_after})
    # Lighting.
    lighting_id = location["lighting"]["id"] if location.get("lighting") else None
    status, basis = LIGHTING_STATES[pick["lighting_state"]]
    if pick["lighting_state"] == "flicker_bursts" and lighting_id != "flickering_interior":
        status, basis = "requires_new_capability", "Flicker needs the Visual Bible flickering_interior lighting here."
    need("lighting_state", loc, status, basis, value=pick["lighting_state"])
    flicker_lamp = next((l["id"] for l in (location.get("geometry") or {}).get("lamps", []) if l["driver"] == "flicker"), None)
    # Presence: only a canonical partial character in this beat, never an identity reveal.
    presence = None
    if pick["presence"] == "visible_partial":
        bound = location.get("presence")
        if not bound or bound["character_id"] not in raw["partial_ids"]:
            blockers.append("REVELATION: partial presence is only allowed in beats where that canonical character appears.")
        else:
            presence = {"character_id": bound["character_id"], "anchor": bound["anchor"], "visibility": "partial_silhouette",
                        "x": location["geometry"]["presence"]["x"], "identity_revealed": False}
            need("presence", bound["character_id"], "supported_parameterized", "Pinned silhouette at a presence anchor.")
    for cid in raw["partial_ids"]:
        bound = location.get("presence")
        if not bound or bound["character_id"] != cid:
            need("presence", cid, "editorial_review", "No presence anchor is bound here; the figure stays implied/off-frame.")
    for cid in raw["unseen_ids"]:
        need("offscreen_character", cid, "supported_direct", "Unseen by Visual Bible policy; implied only.")
    # Cast blocking and performance; dry-run through P3.2A ActorBuilder.
    narration_text = src["narration"]["text"] if raw["kind"] == "narrative" else ""
    narr_seconds = round(syllables(narration_text) / SYLLABLES_PER_SECOND, 3) if narration_text else 0.0
    cast_rows, motion, steps_by_actor = [], [], {}
    for cid in raw["cast_ids"]:
        c, choice = chars[cid], pick["cast"][cid]
        cur = state["characters"][cid]
        if raw["kind"] == "reaction_hold":
            mark, entry = cur["mark"], "present_at_cut"
        else:
            mark, entry = choice["mark"], choice["entry"]
        if reach and reach[0] == cid:
            mark = f"reach:{reach[1]}"
            if mark not in marks:
                blockers.append(f"INTERACTION_UNREACHABLE {cid}: no reach mark for {reach[1]} in this location.")
                mark = choice.get("mark", cur["mark"])
        end_x = marks.get(mark)
        here = cur["location_id"] == loc
        if entry == "enter_walk":
            a, b = location["anchors"]["walk_range"]
            start_x = a if abs(end_x - a) < abs(end_x - b) else b
            if here and cur["visible"] and not new_scene:
                blockers.append(f"TELEPORT {cid}: already visible here; cannot re-enter from the edge without an exit.")
        elif entry == "present_at_cut":
            if not here and not new_scene:
                blockers.append(f"TELEPORT {cid}: appears mid-scene without an entry; choose enter_walk or "
                                "revealed_by_framing.")
            continuous = here and (not new_scene or transition == "continuous")
            start_x = cur["x"] if continuous and cur["x"] is not None else end_x
        else:  # revealed_by_framing
            if not here and not _earlier_event_here(canon, _beat(canon, src["beat_id"]), cid, loc):
                blockers.append(f"TELEPORT {cid}: not established in {loc}; it cannot be revealed by framing.")
            start_x = cur["x"] if here and cur["x"] is not None else end_x
        if new_scene and not here and transition == "continuous" and cur["location_id"] is not None:
            blockers.append(f"ACCIDENTAL_TELEPORT {cid}: continuous transition from {cur['location_id']} to {loc}.")
        elif not here and cur["location_id"] is not None:
            notes.append(f"{cid} exits {cur['location_id']} and enters {loc} across an intentional {transition}.")
        if new_scene and here and cur["x"] is not None and abs(start_x - cur["x"]) > 1 and transition != "continuous":
            notes.append(f"{cid} repositioned across an intentional {transition} in the same location.")
        moving = abs(end_x - start_x) > 1
        if reach and reach[0] == cid:
            facing = reach_facing.get(mark, 1)
            if moving and (end_x - start_x) * facing < 0:
                items.append({"requirement": "locomotion", "subject": cid, "status": "requires_new_capability",
                              "basis": "Walking away from the reach direction needs an articulated turn."})
        elif moving:
            facing = 1 if end_x > start_x else -1
        else:
            facing = _facing(cid, end_x, cur, presence, raw["cast_ids"], marks, pick)
        if cur["facing"] is not None and facing != cur["facing"] and not new_scene and raw["kind"] == "narrative" and not moving:
            notes.append(f"{cid} facing flips across the cut.")
        steps, t = [], LEAD
        if moving:
            walk = max(1.0, abs(end_x - start_x) / WALK_SPEED)
            steps.append({"preset": "cautious_walk", "acting_asset": acting_pin("cautious_walk"), "t0": t,
                          "t1": round(t + walk, 3), "params": {"from_x": start_x, "to_x": end_x}})
            need("locomotion", cid, "supported_parameterized", "P3.2A cautious_walk between blocking marks.",
                 minimum_seconds=round(walk, 3))
            t += walk
        if reach and reach[0] == cid:
            steps.append({"preset": "guarded_reach", "acting_asset": acting_pin("guarded_reach"), "t0": round(t, 3),
                          "t1": round(t + 1.4, 3), "params": {"target": list(reach[2]), "hand": "right_hand"}})
            t += 1.4
        perf = choice["performance"]
        pstatus, acting, minimum, pbasis = PERFORMANCES[perf]
        need("performance", cid, pstatus, pbasis, value=perf)
        if pstatus in ("supported_direct", "supported_parameterized"):
            steps.append({"preset": perf, "acting_asset": acting_pin(acting) if acting else None, "t0": round(t, 3),
                          "t1": round(t + minimum, 3), "params": _perf_params(perf, presence, end_x)})
            t += minimum
        steps_by_actor[cid] = (steps, start_x, facing, round(t, 3))
        start_mark = ("walk_range_edge" if entry == "enter_walk" else
                      cur["mark"] if abs(start_x - (cur["x"] if cur["x"] is not None else end_x + 9)) < 1 else mark)
        cast_rows.append({"character_id": cid, "representation": "character", "asset": copy.deepcopy(c["asset"]),
                          "entry": entry, "start_mark": start_mark, "end_mark": mark, "start_x": round(start_x, 1),
                          "end_x": round(end_x, 1), "facing": facing, "performance": perf, "emotion": choice["emotion"],
                          "visible": True})
    # Dialogue delivery.
    for d in src["dialogue"]:
        if d["id"] in pick["dialogue"]:
            mode = pick["dialogue"][d["id"]]
            status, basis = DIALOGUE_DELIVERY[mode]
            need("dialogue_delivery", d["id"], status, basis, value=mode, speaker_id=d["speaker_id"])
    # Camera and framing.
    status, basis = CAMERA_MOVES[pick["camera_move"]]
    need("camera_move", raw["shot_id"], status, basis, value=pick["camera_move"])
    action_end = max([v[3] for v in steps_by_actor.values()] + [0])
    body = max(LEAD + narr_seconds + TAIL, action_end + TAIL, MIN_SHOT) if raw["kind"] == "narrative" else 0.0
    silence = float(src["silence_after_seconds"])
    reaction_follows = raw["kind"] == "narrative" and raw["reaction_follows"]
    planned_silence = 0.0 if reaction_follows else silence
    length = body + planned_silence if raw["kind"] == "narrative" else max(silence, 1.0)
    frames = _frames(length)
    length = frames / FPS
    # A reveal frames the presence first; its reaction hold frames the reacting cast first.
    lead_presence = presence and src["reviewed_staging"]["reveal"] and raw["kind"] == "narrative"
    subjects = [("presence:" + presence["character_id"], presence["x"])] if lead_presence else []
    for row in cast_rows:
        subjects.append((row["character_id"], row["start_x"]))
        if row["end_x"] != row["start_x"]:
            subjects.append((row["character_id"], row["end_x"]))
    if presence and not lead_presence:
        subjects.append(("presence:" + presence["character_id"], presence["x"]))
    subjects += [("prop:" + p["object_id"], p["point"][0]) for p in prop_rows if p["actor_id"]]
    camera = _camera(fmt, pick["shot_size"], pick["camera_move"], subjects, round(length, 4))
    for row in cast_rows:
        row["visible"] = row["character_id"] in camera["framed_subjects"]
        if not row["visible"]:
            notes.append(f"{row['character_id']} is framed out in {fmt} ({camera['visible_world_width']} world px wide).")
    if presence and "presence:" + presence["character_id"] not in camera["framed_subjects"]:
        notes.append(f"Presence {presence['character_id']} is outside this framing.")
    for d in src["dialogue"]:
        if pick["dialogue"].get(d["id"]) == "on_screen_speech" and d["speaker_id"] not in camera["framed_subjects"]:
            blockers.append(f"DIALOGUE_FRAMING {d['id']}: on-screen speech needs the speaker in frame.")
    # Executable dry run: every preset must compile with the real P3.2A ActorBuilder.
    for cid, (steps, start_x, facing, _) in steps_by_actor.items():
        c = chars[cid]
        rest = assets.get("character", c["asset"]["id"], c["asset"]["revision"])["rest_posture"]
        try:
            b = ActorBuilder(cid, c["appearance"], start_x, rest_posture=rest, facing=facing)
            for i, step in enumerate(steps):
                if i == len(steps) - 1 and step["preset"] in ("listening_freeze", "hold"):
                    step["t1"] = round(max(step["t1"], length - TAIL), 3)
                _run(b, step)
            b.build(length)
        except ValueError as exc:
            blockers.append(f"MOTION_PLAN_INVALID {cid}: {exc}")
        motion.append({"character_id": cid, "steps": steps})
    # Capability verdict.
    shot_status = _status(items)
    unsupported = [i for i in items if i["status"] == "requires_new_capability"]
    editorial = [i for i in items if i["status"] == "editorial_review"]
    for i in unsupported:
        blockers.append(f"REQUIRES_NEW_CAPABILITY {i['requirement']} {i['subject']}: {i['basis']}")
    if editorial and not pick["editorial_acknowledged"]:
        blockers.append("EDITORIAL_REVIEW: acknowledge " + "; ".join(f"{i['requirement']} {i['subject']}" for i in editorial))
    # Continuity transitions.
    for row in cast_rows:
        cs = state["characters"][row["character_id"]]
        cs.update(location_id=loc, mark=row["end_mark"], x=row["end_x"], facing=row["facing"], visible=row["visible"],
                  performance=row["performance"], emotion=row["emotion"])
    for cid, cs in state["characters"].items():
        if cid not in raw["cast_ids"] and cs["location_id"] == loc:
            cs["visible"] = False
    for p in prop_rows:  # Requested state applies even when blocked, so continuity reflects the request.
        if p["state_after"] and p["object_id"] in state["props"]:
            old = state["props"][p["object_id"]]["state"]
            notes.append(f"{p['object_id']} {old} -> {p['state_after']} ({p['interaction']})." if old != p["state_after"]
                         else f"{p['object_id']} is already {old}; {p['interaction']} changes nothing.")
            state["props"][p["object_id"]]["state"] = p["state_after"]
    state["lighting"].setdefault(loc, {"preset": lighting_id, "state": "steady"})["state"] = pick["lighting_state"]
    for oid, p in props.items():  # Lamp props follow the shot lighting state; only the flicker lamp flickers.
        if p["location_id"] == loc and p["asset"] and p["asset"]["id"] in LAMPS and oid in state["props"]:
            lamp = (p["anchor"] or "").split(".")[1] if (p["anchor"] or "").count(".") == 2 else None
            state["props"][oid]["state"] = ("dark" if pick["lighting_state"] == "blackout" else
                                            "flickering" if pick["lighting_state"] == "flicker_bursts" and lamp == flicker_lamp
                                            else "lit_steady")
    if presence:
        state["presence"][presence["character_id"]] = "partial_shown_identity_unrevealed"
    after = _snapshot(state, loc, set(src["character_ids"]))
    reason = {"supported_direct": "Executable with existing renderer data.",
              "supported_parameterized": "Executable with P3.2A presets/camera parameters (dry-run compiled).",
              "editorial_review": "Representable only through an explicit editorial choice.",
              "requires_new_capability": "Not executable until a new animation capability exists."}[shot_status]
    return {
        "shot_id": raw["shot_id"], "order": 0, "kind": raw["kind"], "scene_id": raw["scene_id"],
        "chapter_id": raw["chapter_id"], "source": copy.deepcopy(src), "options": copy.deepcopy(opts),
        "staging": {"basis": "creative_proposal_not_canonical_fact", "shot_size": pick["shot_size"],
                    "camera_move": pick["camera_move"], "camera": camera,
                    "lighting": {"preset": copy.deepcopy(location.get("lighting")), "state": pick["lighting_state"],
                                 "flicker_lamp": flicker_lamp, "flicker_bursts_seconds":
                                     [round(LEAD + narr_seconds * .4, 3)] if pick["lighting_state"] == "flicker_bursts" else []},
                    "atmosphere": location.get("atmosphere"), "presence": presence, "cast": cast_rows,
                    "offscreen": [{"character_id": c, "representation": chars[c]["representation"] if c in chars else "unbound"}
                                  for c in raw["unseen_ids"] + [p for p in raw["partial_ids"] if not presence]],
                    "props": prop_rows, "dialogue_delivery": copy.deepcopy(pick["dialogue"]),
                    "sound": {"cues": [{"id": s, "label": sounds[s]["label"], "kind": sounds[s]["kind"],
                                        "canonical_treatment": sounds[s].get("proposed_treatment", ""),
                                        "placement": "in_silence" if sounds[s]["kind"] == "silence" else "at_shot_start"}
                                       for s in src["sound_cue_ids"] if s in sounds] if raw["kind"] == "narrative" else [],
                              "silence_seconds": round(planned_silence if raw["kind"] == "narrative" else length, 3),
                              "silence_role": "reaction_hold" if raw["kind"] == "reaction_hold" else "after_narration"},
                    "reveal": {"canonical_reveal_beat": bool(src["reviewed_staging"]["reveal"]), "identity_reveal_allowed": False,
                               "uncertainty": src["reviewed_staging"]["uncertainty"]}},
        "motion_plan": {"kind": "executable_estimate", "basis": "P3.2A ActorBuilder dry run at provisional timing",
                        "actors": motion},
        "descriptive_proposal": {"text": src["reviewed_staging"]["action"], "executable": False, "note": NOT_EXECUTABLE},
        "capability": {"status": shot_status, "reason": reason, "items": items},
        "editorial_acknowledged": pick["editorial_acknowledged"],
        "continuity": {"transition_in": transition if new_scene else "within_scene", "before": before, "after": after,
                       "notes": notes},
        "timing": {"status": "provisional_estimate", "narration_unit_id": src["beat_id"] if raw["kind"] == "narrative" else None,
                   "narration": {"syllables": syllables(narration_text) if narration_text else 0,
                                 "estimated_seconds": narr_seconds,
                                 "interval_seconds": [LEAD, round(LEAD + narr_seconds, 3)] if narration_text else None,
                                 "format_interval_seconds": None},
                   "lead_seconds": LEAD if narration_text else 0, "tail_seconds": TAIL if narration_text else 0,
                   "planned_silence_seconds": round(planned_silence if raw["kind"] == "narrative" else length, 3),
                   "action": {"minimum_seconds": round(action_end, 3),
                              "steps": [{"character_id": cid, "preset": s["preset"], "seconds": round(s["t1"] - s["t0"], 3)}
                                        for cid, (st, *_r) in steps_by_actor.items() for s in st]},
                   "estimated_seconds": round(length, 4), "format_start_seconds": 0.0,
                   "frame_grid": {"fps": FPS, "estimated_start_frame": 0, "estimated_frame_count": frames,
                                  "quantization": "ceil to whole frames; cuts on the 30 fps grid"},
                   "pending_measurement": {"required": bool(narration_text),
                                           "dependency": f"P3.5 measured narration duration for {src['beat_id']}"
                                           if narration_text else None}},
        "blockers": blockers}


def _beat(canon, beat_id):
    return next(b for p in canon["formats"].values() for ch in p["chapters"] for b in ch["beats"] if b["id"] == beat_id)


def _facing(cid, x, cur, presence, cast, marks, pick) -> int:
    if presence:
        return 1 if presence["x"] >= x else -1
    others = [marks.get(pick["cast"][o].get("mark")) for o in cast if o != cid and pick["cast"][o].get("mark") in marks]
    if others:
        return 1 if others[0] >= x else -1
    return cur["facing"] or 1


def _perf_params(perf, presence, x):
    if perf == "listening_freeze":
        return {"gaze": [5, 0], "tilt": 6, "target": "presence" if presence else "offscreen_unknown_source"}
    if perf == "startled_reaction":
        return {"toward": 1, "hold": 1.0, "strength": 0.8}
    return {}


def _run(builder, step):
    p = step["params"]
    if step["preset"] == "cautious_walk":
        builder.cautious_walk(p["to_x"], step["t0"], step["t1"])
    elif step["preset"] == "guarded_reach":
        builder.guarded_reach(p["target"], step["t0"], step["t1"], hand=p["hand"])
    elif step["preset"] == "listening_freeze":
        builder.listening_freeze(step["t0"], step["t1"], gaze=tuple(p["gaze"]), tilt=p["tilt"])
    elif step["preset"] == "startled_reaction":
        builder.startled_reaction(step["t0"], toward=p["toward"], hold=p["hold"], strength=p["strength"])
        step["t1"] = round(step["t0"] + .2 + p["hold"], 3)
    else:
        builder.hold(step["t1"])


# ------------------------------------------------------------------ coverage, continuity, timing contract

def _non_ws(text, ranges, start, end):
    """Non-whitespace characters in [start, end) and those not covered by ranges."""
    total, missing = 0, 0
    for i in range(start, end):
        if not text[i].isspace():
            total += 1
            if not any(a <= i < b for a, b in ranges):
                missing += 1
    return total, missing


def coverage(plan: dict, reviewed: dict) -> dict:
    """Independent re-check from the plan's own shots against the approved reviewed format plans."""
    canon, working, mapping = reviewed["canonical_story"], reviewed["working_text"], reviewed["source_mapping"]
    out, blockers, ranges, events = {}, [], {}, {}
    for fmt, fp in plan["formats"].items():
        beats = [b for ch in canon["formats"][fmt]["chapters"] for b in ch["beats"]]
        expected = [b["id"] for b in beats]
        primary = [s for s in fp["shots"] if s["kind"] == "narrative"]
        allocated = [s["source"]["beat_id"] for s in primary]
        mismatched = [b["id"] for b, s in zip(beats, primary)
                      if b["id"] != s["source"]["beat_id"] or b["narration"]["text"] != s["source"]["narration"]["text"]
                      or b["narration"]["sources"] != s["source"]["narration"]["sources"]
                      or b["event_ids"] != s["source"]["event_ids"] or b["character_ids"] != s["source"]["character_ids"]
                      or b["location_id"] != s["source"]["location_id"] or b["object_ids"] != s["source"]["object_ids"]
                      or b["sound_cue_ids"] != s["source"]["sound_cue_ids"]]
        order = [s["shot_id"] for s in fp["shots"]]
        by_scene = [sid for sc in fp["scenes"] for sid in sc["shot_ids"]]
        by_chapter = [sc for ch in fp["chapters"] for sc in ch["scene_ids"]]
        orphans = [s["shot_id"] for i, s in enumerate(fp["shots"]) if s["kind"] == "reaction_hold"
                   and (i == 0 or fp["shots"][i - 1]["source"]["beat_id"] != s["source"]["beat_id"])]
        problems = []
        if [b for b in expected if b not in allocated]:
            problems.append("missing beats " + ", ".join(b for b in expected if b not in allocated))
        if allocated != expected:
            problems.append("beat order or duplicate allocation differs from the reviewed plan")
        if mismatched:
            problems.append("source fields changed for " + ", ".join(mismatched))
        if order != by_scene or [s["scene_id"] for s in fp["scenes"]] != by_chapter:
            problems.append("scene/shot ordering is inconsistent")
        if [c["chapter_id"] for c in fp["chapters"]] != [c["id"] for c in canon["formats"][fmt]["chapters"]]:
            problems.append("chapter order differs from the reviewed plan")
        if orphans:
            problems.append("reaction shots without their beat: " + ", ".join(orphans))
        for p in problems:
            blockers.append(f"COVERAGE {fmt.upper()}: {p}.")
        ranges[fmt] = [(s["char_start"], s["char_end"]) for shot in primary if shot["source"]["narration"]["mode"] == "verbatim"
                       for g in shot["source"]["narration"]["working_spans"] for s in g]
        events[fmt] = {e for s in primary for e in s["source"]["event_ids"]}
        sounds = {c for s in primary for c in s["source"]["sound_cue_ids"]}
        dialogue = {d["id"] for s in primary for d in s["source"]["dialogue"]}
        row = {"reviewed_beats": len(expected), "allocated_beats": len(set(allocated) & set(expected)),
               "narrative_shots": len(primary), "reaction_shots": len(fp["shots"]) - len(primary),
               "scenes": len(fp["scenes"]), "chapters": len(fp["chapters"]),
               "beat_order_preserved": allocated == expected, "source_fields_verbatim": not mismatched,
               "events": sorted(events[fmt]), "sound_cues": sorted(sounds), "dialogue": sorted(dialogue),
               "narration_characters": sum(len(s["source"]["narration"]["text"]) for s in primary)}
        if fmt == "long":
            row["events_missing"] = [e["id"] for e in canon["events"] if e["id"] not in events[fmt]]
            row["sound_cues_missing"] = [c["id"] for c in canon["sound_cues"] if c["id"] not in sounds]
            row["dialogue_missing"] = [d["id"] for d in canon["dialogue"] if d["id"] not in dialogue]
            total = missing = 0
            gaps = []
            for seg in canon["segments"]:
                if seg["kind"] == "heading":
                    continue
                seg_missing = 0
                for span in mapped_spans(mapping, seg["char_start"], seg["char_end"]):
                    t, m = _non_ws(working, ranges[fmt], span["char_start"], span["char_end"])
                    total, missing, seg_missing = total + t, missing + m, seg_missing + m
                if seg_missing:
                    gaps.append(seg["id"])
            row["working_text"] = {"non_whitespace_characters": total, "covered": total - missing,
                                   "missing_segments": gaps}
            if gaps:
                blockers.append("LONG_SOURCE_OMITTED: retained story text is not narrated: " + ", ".join(gaps) + ".")
            for key, label in (("events_missing", "events"), ("sound_cues_missing", "sound cues"),
                               ("dialogue_missing", "dialogue lines")):
                if row[key]:
                    blockers.append(f"LONG_UNSTAGED {label}: " + ", ".join(row[key]) + ".")
        out[fmt] = row
    if "short" in ranges and "long" in ranges:
        missing = sum(_non_ws(working, ranges["long"], a, b)[1] for a, b in ranges["short"])
        extra = sorted(events["short"] - events["long"])
        out["short"]["sources_within_long"] = not missing
        out["short"]["events_within_long"] = not extra
        if missing or extra:
            blockers.append("FORMAT_CONSISTENCY: Short uses source text or events absent from Long.")
    return {"formats": out, "blockers": blockers,
            "basis": "Every reviewed beat has one narrative shot in order; Long retained text is checked per character."}


def continuity(plan: dict, canon: dict, handoff: dict) -> dict:
    blockers, formats, after_event = [], {}, {}
    statuses = {a["id"]: a["status"] for a in canon["ambiguities"]}
    for fmt, fp in plan["formats"].items():
        states = {}
        for shot in fp["shots"]:
            for e in shot["source"]["event_ids"]:
                states[e] = {o: v["state"] for o, v in shot["continuity"]["after"]["props"].items()}
        after_event[fmt] = states
        final = fp["end_state"]
        formats[fmt] = {"final_state": final,
                        "notes": [f"{s['shot_id']}: {n}" for s in fp["shots"] for n in s["continuity"]["notes"]],
                        "transitions": [{"scene_id": sc["scene_id"], "transition": sc["transition_in"],
                                         "location_change": sc["location_change"]} for sc in fp["scenes"]]}
        changed = [a for a, v in final["revelation"].items() if v != statuses.get(a)]
        if changed:
            blockers.append(f"REVELATION {fmt.upper()}: canonical uncertainty changed for " + ", ".join(changed) + ".")
    shared = sorted(set(after_event.get("short", {})) & set(after_event.get("long", {})))
    transient = {p["canonical_id"] for p in handoff["props"] if p["asset"] and p["asset"]["id"] in LAMPS}
    mismatches = []
    for e in shared:  # Persistent prop states only; lamp output follows each shot's lighting choice.
        a, b = after_event["short"][e], after_event["long"][e]
        for o in sorted((set(a) & set(b)) - transient):
            if a[o] != b[o]:
                mismatches.append({"event_id": e, "object_id": o, "short": a[o], "long": b[o]})
                blockers.append(f"FORMAT_CONTINUITY {o} after {e}: Short is {a[o]}, Long is {b[o]}.")
    if handoff["formats"]["short"] != handoff["formats"]["long"]:
        blockers.append("FORMAT_IDENTITY: Short and Long character/environment digests differ.")
    return {"formats": formats, "shared_events_checked": shared, "format_mismatches": mismatches,
            "identity": {"rule": "Same Visual Bible identity, costume and environment digests in every shot of both formats.",
                         "characters": copy.deepcopy(handoff["formats"]["long"]["characters"]),
                         "locations": copy.deepcopy(handoff["formats"]["long"]["locations"])},
            "canonical_rules": copy.deepcopy(canon["continuity_rules"]),
            "canonical_ambiguities": [{"id": a["id"], "question": a["question"], "status": a["status"]}
                                      for a in canon["ambiguities"]],
            "blockers": blockers}


RETIME_RULES = [
    "Measured durations come only from actual P3.5 offline narration audio; provisional estimates are never measurements.",
    "Each measurement must name a narration unit, match its exact text_sha256 and this approved plan's package hash.",
    "Narrative shot seconds = whole frames of max(lead + measured + tail, action minimum + tail, minimum shot) + planned silence.",
    "Reaction-hold shots keep their planned silence; shot order, IDs, narration and staging never change while retiming.",
    "Results are written as a new P3.5 artifact; the approved scene plan is never edited. A new plan version voids measurements.",
    "story_planner keeps requiring measured WAV durations; this contract does not feed it estimated timing.",
]


def retiming_contract(plan: dict) -> dict:
    units = [{"unit_id": s["timing"]["narration_unit_id"], "format": fmt, "shot_id": s["shot_id"],
              "text_sha256": _sha(s["source"]["narration"]["text"]),
              "estimated_seconds": s["timing"]["narration"]["estimated_seconds"]}
             for fmt, fp in plan["formats"].items() for s in fp["shots"] if s["timing"]["narration_unit_id"]]
    return {"artifact": "scene_plan_retiming_contract", "contract_version": "1.0",
            "status": "awaiting_p3_5_measured_narration", "fps": FPS, "lead_seconds": LEAD, "tail_seconds": TAIL,
            "minimum_shot_seconds": MIN_SHOT, "narration_units": units,
            "measurement_fields": ["unit_id", "text_sha256", "duration_seconds", "audio_sha256", "sample_rate_hz"],
            "rules": list(RETIME_RULES)}


def _handoff_error(code, message, shot_id=None):
    raise ScenePlanError(code, message, [{"code": code, "shot_id": shot_id, "message": message}])


def _file_hash(value):
    # Same bytes as studio.reviewed._bytes; no dependency from the library onto Studio.
    return hashlib.sha256((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()).hexdigest()


def _contract_schema(value, definition, code):
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    try:
        fingerprint(value)  # JSON Schema alone does not reject NaN/Infinity.
        jsonschema.Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": schema["$defs"]}).validate(value)
    except (ValueError, TypeError, jsonschema.ValidationError) as exc:
        _handoff_error(code, f"Invalid {definition}: {str(exc).splitlines()[0]}")


def _handoff_format(plan, fmt):
    """Check the declared inventory before conversion; approval verification binds it to canon."""
    if not isinstance(fmt, str) or fmt not in FRAMES:
        _handoff_error("invalid_format", "Use short or long.")
    try:
        fingerprint(plan)
        jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(plan)
        fp = plan["formats"][fmt]
        ids = [s["shot_id"] for s in fp["shots"]]
        scene_ids = [s["scene_id"] for s in fp["scenes"]]
        if (len(set(ids)) != len(ids) or ids != [i for sc in fp["scenes"] for i in sc["shot_ids"]]
                or scene_ids != [i for ch in fp["chapters"] for i in ch["scene_ids"]]
                or len(set(scene_ids)) != len(scene_ids)):
            raise ValueError("Shot/scene/chapter inventory differs or contains duplicates")
        beats = []
        for i, shot in enumerate(fp["shots"]):
            sc = next(sc for sc in fp["scenes"] if shot["shot_id"] in sc["shot_ids"])
            if (shot["order"] != i + 1 or shot["scene_id"] != sc["scene_id"]
                    or shot["chapter_id"] != sc["chapter_id"] or shot["source"]["location_id"] != sc["location_id"]):
                raise ValueError("Shot order or scene boundary differs")
            if shot["kind"] == "narrative":
                beats.append(shot["source"]["beat_id"])
            elif i == 0 or fp["shots"][i - 1]["source"]["beat_id"] != shot["source"]["beat_id"]:
                raise ValueError("Orphan reaction shot")
        if len(set(beats)) != len(beats):
            raise ValueError("Duplicate narrative beat")
    except (ValueError, TypeError, KeyError, StopIteration, jsonschema.ValidationError) as exc:
        _handoff_error("handoff_invalid", f"Invalid scene-plan inventory: {str(exc).splitlines()[0]}")
    unavailable = [{"code": "unsupported_capability", "shot_id": s["shot_id"], "requirement": item}
                   for s in fp["shots"] for item in s["capability"]["items"]
                   if item["status"] == "requires_new_capability"]
    if unavailable:
        raise ScenePlanError("unsupported_capability", "Animation capability is unavailable; no shot was removed.", unavailable)
    if plan["blockers"]:
        raise ScenePlanError("approval_blocked", "Resolve the scene-plan blockers before conversion.", plan["blockers"])
    return fp


def _approved_binding(plan, view):
    """Validate a verified view. Storage consumers must re-read current inputs at each call."""
    try:
        approval, manifest = view["approval"], view["manifest"]
        if (not view["ready_for_next_stage"] or not view["is_current"] or view["package"] != plan
                or view["version"] != plan["version"] or _file_hash(plan) != view["package_sha256"]
                or _file_hash(manifest) != view["manifest_sha256"]
                or manifest["inputs"] != plan["inputs"] or manifest["version"] != plan["version"]
                or manifest["package_sha256"] != view["package_sha256"]
                or approval["version"] != plan["version"] or approval["project_id"] != plan["project_id"]
                or approval["approved"] is not True or approval["approval_scope"] != "scene_plan_only"
                or approval["package_sha256"] != view["package_sha256"]
                or approval["manifest_sha256"] != view["manifest_sha256"]
                or approval["integrity_sha256"] != fingerprint({k: v for k, v in approval.items() if k != "integrity_sha256"})):
            raise ValueError("Approval, current inputs, package or manifest differs")
        result = {"project_id": plan["project_id"], "version": plan["version"],
                  "package_sha256": view["package_sha256"], "manifest_sha256": view["manifest_sha256"],
                  "inputs_sha256": fingerprint(plan["inputs"])}
        _contract_schema(result, "plan_binding", "stale_measurement")
        return result
    except (KeyError, TypeError, ValueError) as exc:
        _handoff_error("stale_measurement", f"A current verified approved plan is required: {exc}")


def measurement_contract(plan: dict, fmt: str, *, approved: dict) -> dict:
    """Strict future measurement envelope, separate from immutable v1 scene-plan bytes."""
    fp = _handoff_format(plan, fmt)
    return {"artifact": "scene_plan_measurement_contract", "schema_version": "1.0", "format": fmt,
            "plan": _approved_binding(plan, approved), "fps": FPS,
            "units": [{"unit_id": s["timing"]["narration_unit_id"], "shot_id": s["shot_id"],
                       "text_sha256": _sha(s["source"]["narration"]["text"])}
                      for s in fp["shots"] if s["kind"] == "narrative"],
            "measurement_schema": "schemas/story/story_scene_plan.schema.json#/$defs/measurement_set",
            "fingerprint_rule": "SHA-256 of canonical JSON excluding manifest_sha256 (story_visual_bible.fingerprint).",
            "timing_policy": "Preserve approved action durations and camera cues; extend shots when needed. "
                             "No action is sped up, truncated or removed. Original planned silence is a minimum.",
            "audio_verification": "P3.4 checks declarations only; actual audio verification belongs to a later stage. "
                                  "Synthetic fixtures are never measured audio; every handoff remains renderable=false."}


def _measurements(plan, fmt, value, approved):
    contract = measurement_contract(plan, fmt, approved=approved)
    _contract_schema(value, "measurement_set", "invalid_measurement")
    if value["plan"] != contract["plan"] or value["format"] != fmt:
        _handoff_error("stale_measurement", "Measurement plan/version/package/manifest/inputs or format differs.")
    if [{k: u[k] for k in ("unit_id", "shot_id", "text_sha256")} for u in value["units"]] != contract["units"]:
        _handoff_error("invalid_measurement", "Measurements must cover exactly the ordered narration units, shots and text hashes.")
    if value["manifest_sha256"] != fingerprint({k: v for k, v in value.items() if k != "manifest_sha256"}):
        _handoff_error("invalid_measurement", "Measurement manifest fingerprint differs.")
    from datetime import datetime
    try:
        stamp = datetime.fromisoformat(value["provenance"]["recorded_at"].replace("Z", "+00:00"))
        if stamp.utcoffset() is None:
            raise ValueError("timezone required")
    except ValueError:
        _handoff_error("invalid_measurement", "Measurement provenance needs a timestamp with a timezone.")
    synthetic = value["provenance"]["kind"] == "synthetic_test"
    for u in value["units"]:
        if not math.isfinite(u["duration_seconds"] * FPS) or u["duration_seconds"] * FPS > 2 ** 53 - 1:
            _handoff_error("invalid_measurement", "Duration cannot be represented safely on the frame grid.")
        if synthetic != (u["audio_sha256"] is None and u["sample_rate_hz"] is None):
            _handoff_error("invalid_measurement", "Synthetic fixtures must not claim audio hashes; measured declarations require audio metadata.")
        if not synthetic and (u["audio_sha256"] is None or u["sample_rate_hz"] is None):
            _handoff_error("invalid_measurement", "Measured audio needs both a content hash and a sample rate.")
    return {u["unit_id"]: u for u in value["units"]}


def _motion_frames(shot):
    """Ceil each duration without speeding up any preset or overlapping one actor's actions."""
    out = []
    for actor in shot["motion_plan"]["actors"]:
        end = 0
        for i, step in enumerate(actor["steps"]):
            if (step["preset"] not in {"hold", "cautious_walk", "guarded_reach", "listening_freeze", "startled_reaction"}
                    or not 0 <= step["t0"] < step["t1"]):
                _handoff_error("timing_blocked", "Unsupported or invalid action interval; a new reviewed staging version is required.", shot["shot_id"])
            start = max(end, _frames(step["t0"]))
            end = start + _frames(step["t1"] - step["t0"])
            out.append({"character_id": actor["character_id"], "step_index": i, "preset": step["preset"],
                        "start_frame": start, "end_frame": end})
    return sorted(out, key=lambda a: a["start_frame"])


def _boundaries(rows, groups, key):
    by_id = {r["shot_id"]: r for r in rows}
    return [{key: g[key], "start_frame": by_id[g["shot_ids"][0]]["start_frame"],
             "end_frame": by_id[g["shot_ids"][-1]]["end_frame"]} for g in groups]


def _timed_shots(plan, fmt, measured=None):
    fp = _handoff_format(plan, fmt)
    rows, frame = [], 0
    for s in fp["shots"]:
        t = s["timing"]
        motions = _motion_frames(s)
        action_end = max([m["end_frame"] for m in motions] + [0])
        count = t["frame_grid"]["estimated_frame_count"]
        narration = None
        if s["kind"] == "narrative":
            uid = t["narration_unit_id"]
            seconds = measured[uid]["duration_seconds"] if measured is not None else t["narration"]["estimated_seconds"]
            lead, tail, silence = _frames(t["lead_seconds"]), _frames(t["tail_seconds"]), _frames(t["planned_silence_seconds"])
            end = lead + _frames(seconds)
            count = max(count, end + tail + silence, action_end + tail, _frames(t["action"]["minimum_seconds"] + TAIL))
            narration = {"unit_id": uid, "text_sha256": _sha(s["source"]["narration"]["text"]),
                         "duration_seconds": seconds, "start_frame": frame + lead, "end_frame": frame + end,
                         "action_indices": [i for i, m in enumerate(motions) if m["start_frame"] < end and m["end_frame"] > lead]}
        elif action_end > count:
            _handoff_error("timing_blocked", "Action exceeds the approved reaction/silence hold; review staging first.", s["shot_id"])
        keys = copy.deepcopy(s["staging"]["camera"]["keys"])
        previous = -1
        for k in keys:
            k[0] = _frames(k[0]) / FPS
            if not previous < k[0] <= count / FPS + 1e-9:
                _handoff_error("timing_blocked", "Camera keys exceed the shot or are unordered.", s["shot_id"])
            previous = k[0]
        if not keys or keys[0][0] != 0:
            _handoff_error("timing_blocked", "Camera must start at the shot boundary.", s["shot_id"])
        if keys[-1][0] < count / FPS:
            keys.append([count / FPS, *keys[-1][1:]])  # Hold the final framing; never accelerate the move.
        rows.append({"shot_id": s["shot_id"], "start_frame": frame, "end_frame": frame + count, "frame_count": count,
                     "narration": narration, "motion": motions, "camera_keys": keys})
        frame += count
    return rows


def _retimed(plan, fmt, value, approved):
    measured = _measurements(plan, fmt, value, approved)
    rows = _timed_shots(plan, fmt, measured)
    fp = plan["formats"][fmt]
    scenes = _boundaries(rows, fp["scenes"], "scene_id")
    by_scene = {r["scene_id"]: r for r in scenes}
    chapters = [{"chapter_id": c["chapter_id"], "start_frame": by_scene[c["scene_ids"][0]]["start_frame"],
                 "end_frame": by_scene[c["scene_ids"][-1]]["end_frame"]} for c in fp["chapters"]]
    return {"artifact": "retimed_scene_plan", "schema_version": "1.0", "plan": _approved_binding(plan, approved),
            "approved_format": copy.deepcopy(fp), "inputs": copy.deepcopy(plan["inputs"]),
            "continuity": copy.deepcopy(plan["continuity"]),
            "format": fmt, "fps": FPS, "measurement_set": copy.deepcopy(value), "shots": rows,
            "scenes": scenes, "chapters": chapters, "duration_frames": rows[-1]["end_frame"],
            "duration_seconds": rows[-1]["end_frame"] / FPS, "renderable": False,
            "timing_status": "synthetic_test_not_measured_audio" if value["provenance"]["kind"] == "synthetic_test"
                             else "declared_measured_audio_pending_verification"}


def retime(plan: dict, fmt: str, measurements: dict, *, approved: dict | None = None) -> dict:
    """Pure P3.4 derivative. The Studio wrapper re-verifies current approval/canon/Visual Bible."""
    return _retimed(plan, fmt, measurements, approved)


def _build_action_timeline(plan, fmt, timeline, approved):
    fp = _handoff_format(plan, fmt)
    binding = _approved_binding(plan, approved)
    if timeline is not None:
        if not isinstance(timeline, dict) or "measurement_set" not in timeline:
            _handoff_error("handoff_invalid", "Use the complete bound retimed derivative, never a partial timing list.")
        expected = _retimed(plan, fmt, timeline["measurement_set"], approved)
        if timeline != expected:
            _handoff_error("handoff_invalid", "Retimed shots, order, source binding or timing boundaries were changed.")
        rows = timeline["shots"]
    else:
        rows = _timed_shots(plan, fmt)
    scenes = []
    for i, s in enumerate(fp["shots"]):
        w = rows[i]
        actions = []
        for m in w["motion"]:
            emotion = next(c["emotion"] for c in s["staging"]["cast"] if c["character_id"] == m["character_id"])
            actions.append({"at_seconds": (w["start_frame"] + m["start_frame"]) / FPS,
                            "duration_seconds": (m["end_frame"] - m["start_frame"]) / FPS,
                            "character_id": m["character_id"], "action": m["preset"], "emotion": emotion,
                            "notes": "provisional estimate" if timeline is None else timeline["timing_status"]})
        effects = [f"lighting:{s['staging']['lighting']['state']}"]
        if s["staging"]["presence"]:
            effects.append(f"presence:{s['staging']['presence']['character_id']}")
        scenes.append({"scene_id": s["shot_id"], "start_seconds": w["start_frame"] / FPS, "end_seconds": w["end_frame"] / FPS,
                       "camera": {"move": s["staging"]["camera_move"], "size": s["staging"]["shot_size"], "keys": w["camera_keys"]},
                       "background": s["source"]["location_id"], "effects": effects, "actions": actions})
    return {"version": "1.0", "fps": FPS, "scenes": scenes,
            "metadata": {"source": "story_scene_plan", "handoff_contract_version": "1.1", "plan_version": plan["version"],
                         "format": fmt, "timing_status": "provisional_estimate_not_renderable" if timeline is None else timeline["timing_status"],
                         "renderable": False, "plan_binding": binding,
                         "inputs": copy.deepcopy(plan["inputs"]), "approved_format": copy.deepcopy(fp),
                         "shared_identity": copy.deepcopy(plan["shared_identity"]), "continuity": copy.deepcopy(plan["continuity"]),
                         "coverage": copy.deepcopy(plan["coverage"]), "blockers": copy.deepcopy(plan["blockers"]),
                         "timed_shots": copy.deepcopy(rows), "retiming": copy.deepcopy(timeline),
                         "scene_boundaries": _boundaries(rows, fp["scenes"], "scene_id"),
                         "duration_frames": rows[-1]["end_frame"], "duration_seconds": rows[-1]["end_frame"] / FPS}}


def validate_action_timeline(plan: dict, fmt: str, output: dict, *, approved: dict | None = None) -> None:
    """Post-conversion invariant: exact inventory, source/context, motions and all timing boundaries."""
    try:
        fingerprint(output)
        jsonschema.Draft202012Validator(json.loads(ACTION_TIMELINE_SCHEMA.read_text(encoding="utf-8"))).validate(output)
        expected = _build_action_timeline(plan, fmt, output["metadata"]["retiming"], approved)
        if output != expected:
            raise ValueError("Shot inventory, source/context, action links or timing differs from the approved plan")
    except (KeyError, ValueError, TypeError, jsonschema.ValidationError) as exc:
        _handoff_error("handoff_invalid", f"Lossless scene handoff verification failed: {str(exc).splitlines()[0]}")


def action_timeline(plan: dict, fmt: str, timeline: dict | None = None, *, approved: dict | None = None) -> dict:
    """Lossless, non-renderable IR. Approved semantics stay intact beside resolved frame timings."""
    result = _build_action_timeline(plan, fmt, timeline, approved)
    validate_action_timeline(plan, fmt, result, approved=approved)
    return result


def handoff_coverage(plan: dict, reviewed: dict, timelines: dict, *, approved: dict) -> dict:
    """Independently recompute coverage from the actual converted payload, including both formats."""
    if set(timelines) != set(FRAMES):
        _handoff_error("handoff_invalid", "Short and Long must both be present in the lossless handoff.")
    converted = copy.deepcopy(plan)
    for fmt, output in timelines.items():
        validate_action_timeline(plan, fmt, output, approved=approved)
        converted["formats"][fmt] = copy.deepcopy(output["metadata"]["approved_format"])
    result = coverage(converted, reviewed)
    if result["blockers"]:
        raise ScenePlanError("coverage_failed", "Converted handoff lost canonical source coverage.", result["blockers"])
    return result


def coverage_report(plan: dict) -> str:
    """Human-readable story-to-shot coverage, continuity, capability and timing report (Markdown)."""
    inputs = plan["inputs"]
    lines = [f"# Story-to-shot coverage: {plan['title']}", "",
             f"Scene plan {plan['version']}; reviewed story {inputs['reviewed_story']['version']}; "
             f"Visual Bible {inputs['visual_bible']['version']}; library {inputs['library']['version']}.", "",
             "Timing is a provisional estimate pending P3.5 measured narration. Staging is a creative proposal.", ""]
    for fmt, fp in plan["formats"].items():
        cov, timing = plan["coverage"]["formats"][fmt], fp["timing"]
        lines += [f"## {fmt.capitalize()} ({fp['aspect_ratio']})", "",
                  f"- Beats allocated: {cov['allocated_beats']}/{cov['reviewed_beats']}; narrative shots "
                  f"{cov['narrative_shots']}; reaction shots {cov['reaction_shots']}; scenes {cov['scenes']}; "
                  f"chapters {cov['chapters']}.",
                  f"- Beat order preserved: {cov['beat_order_preserved']}; source fields verbatim: {cov['source_fields_verbatim']}.",
                  f"- Estimated duration {timing['estimated_seconds']} s: narration {timing['estimated_narration_seconds']} s, "
                  f"silence {timing['planned_silence_seconds']} s, action/framing {timing['action_and_framing_seconds']} s."]
        if "working_text" in cov:
            w = cov["working_text"]
            unstaged = cov["events_missing"] + cov["sound_cues_missing"] + cov["dialogue_missing"]
            lines.append(f"- Retained story text narrated: {w['covered']}/{w['non_whitespace_characters']} non-whitespace "
                         f"characters; missing segments: {', '.join(w['missing_segments']) or 'none'}.")
            lines.append(f"- Unstaged events, sound cues or dialogue: {', '.join(unstaged) or 'none'}.")
        else:
            lines.append(f"- Short sources within Long: {cov['sources_within_long']}; events within Long: "
                         f"{cov['events_within_long']}.")
        if timing.get("target"):
            lines.append(f"- Short target {timing['target']['min']}-{timing['target']['max']} s: estimate is "
                         f"{timing['target']['estimate_relation']} (not enforced before measurement).")
        lines += ["", "| Chapter | Scene | Shot | Beat | Sources | Events | Cast / presence | Camera | Capability | Est. s |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for s in fp["shots"]:
            src, st = s["source"], s["staging"]
            spans = ", ".join(x["segment_id"] for x in src["narration"]["sources"]) if s["kind"] == "narrative" else "(silence)"
            who = ", ".join(c["character_id"] + ("" if c["visible"] else " (framed out)") for c in st["cast"])
            if st["presence"]:
                who += f"; {st['presence']['character_id']} partial"
            lines.append(f"| {s['chapter_id']} | {s['scene_id']} | {s['shot_id']} {s['kind']} | {src['beat_id']} | {spans} | "
                         f"{', '.join(src['event_ids'])} | {who or '-'} | {st['shot_size']} / {st['camera_move']} | "
                         f"{s['capability']['status']} | {s['timing']['estimated_seconds']:.2f} |")
        lines.append("")
    lines += ["## Continuity", ""]
    for fmt, c in plan["continuity"]["formats"].items():
        props = ", ".join(f"{o}={v['state']}" for o, v in c["final_state"]["props"].items())
        lines.append(f"- {fmt.capitalize()} final props: {props}; uncertainty: "
                     + ", ".join(f"{a}={v}" for a, v in c["final_state"]["revelation"].items()) + ".")
        lines += [f"  - {n}" for n in c["notes"]]
    lines.append(f"- Shared events checked: {', '.join(plan['continuity']['shared_events_checked'])}; "
                 f"Short/Long mismatches: {len(plan['continuity']['format_mismatches'])}.")
    lines += ["", "## Capability gaps", ""]
    gaps = [f"- {fmt} {s['shot_id']}: {i['status']}, {i['requirement']} {i['subject']}: {i['basis']}"
            for fmt, fp in plan["formats"].items() for s in fp["shots"] for i in s["capability"]["items"]
            if i["status"] in ("editorial_review", "requires_new_capability")]
    lines += gaps or ["- none"]
    lines += ["", "## Blockers", ""] + ([f"- {b}" for b in plan["blockers"]] or ["- none"])
    lines += ["", "## Warnings", ""] + ([f"- {w}" for w in plan["warnings"]] or ["- none"])
    return "\n".join(lines) + "\n"
