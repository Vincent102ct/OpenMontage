"""P3.2A synthetic proof: two unrelated stories bound to the same asset library.

No real story, Story Bible, pilot or reviewed package is read. Every visual comes
from `horror_assets` (pinned `id@revision` bindings) and every performance from
`horror_acting` presets over the existing StoryVideo/IK contract.
"""
from __future__ import annotations

from pathlib import Path
import copy

from tools.character import horror_assets as lib
from tools.character.horror_acting import ActorBuilder

FPS = 30
DURATION = 10.0
AUDIO_RECIPES = (("room_tone", 10), ("knock", .3), ("footstep", .17), ("switch", .12), ("low_drone", 2.4))

STORY_A_BINDING = {
    "story_id": "synthetic-third-knock", "library": lib.LIBRARY_ID, "library_version": lib.LIBRARY_VERSION,
    "cast": {"tenant": {"character": "nora_vale", "revision": 1}},
    "locations": {"flat": {"environment": "old_apartment_room", "revision": 1,
                           "lighting": {"id": "cold_moonlight", "revision": 1}}},
}
STORY_B_BINDING = {
    "story_id": "synthetic-lamp-four", "library": lib.LIBRARY_ID, "library_version": lib.LIBRARY_VERSION,
    "cast": {"resident": {"character": "victor_hale", "revision": 1}},
    "locations": {"hall": {"environment": "dark_apartment_corridor", "revision": 1,
                           "lighting": {"id": "flickering_interior", "revision": 1, "flicker_lamp": "lamp_mid"},
                           "presence": {"anchor": "corridor_end", "silhouette": "tall_hooded", "revision": 1}}},
}


def _shot(sid, start, end, location, camera, light, actor):
    return {"id": sid, "start_seconds": start, "end_seconds": end, "view": "world", "location": location,
            "weather": None, "camera": camera, "light": light, "door": [[0, 0], [end - start, 0]],
            "actors": [actor], "items": [], "vehicles": []}


def _timeline(shots, builders, notes):
    scenes = []
    for shot, builder in zip(shots, builders):
        actions = [{"at_seconds": round(shot["start_seconds"] + e["from"], 4),
                    "duration_seconds": round(e["to"] - e["from"], 4), "character_id": builder.id,
                    "action": e["preset"], "notes": notes.get((shot["id"], e["preset"]), "Preset " + e["preset"] + ".")}
                   for e in builder.log]
        scenes.append({"scene_id": shot["id"], "start_seconds": shot["start_seconds"],
                       "end_seconds": shot["end_seconds"], "actions": actions})
    return scenes


def _landings(shots, builders):
    return sorted(round((shot["start_seconds"] + t) * FPS) / FPS
                  for shot, b in zip(shots, builders) for t in getattr(b, "walk_landings", []))


def _video(binding, resolved, title, art, viewport, shots, sfx, horror):
    return {"duration_seconds": DURATION, "fps": FPS, "title": title, "character_skin": "cartoon_horror",
            "viewport": viewport, "audio_mode": "sfx_only", "narration": [], "sfx": sfx, "art_direction": art,
            "locations": resolved["locations"], "shots": shots, "horror": horror,
            "asset_binding": binding}


def build_story_a(audio: dict[str, Path], *, character_id: str = "nora_vale") -> tuple[dict, dict]:
    """Vertical room story: Nora hears knocks, listens, approaches and touches the closed door."""
    binding = copy.deepcopy(STORY_A_BINDING)
    binding["cast"]["tenant"]["character"] = character_id
    if character_id != "nora_vale":
        binding["story_id"] += "-" + character_id
    resolved = lib.resolve_binding(binding)
    look = resolved["cast"]["tenant"]
    posture = lib.get("character", character_id, 1)["rest_posture"]
    handle = resolved["locations"]["flat"]["anchors"]["doors"][0]["handle"]
    a1 = (ActorBuilder("tenant", look, 470, rest_posture=posture).hold(1.15)
          .startled_reaction(1.15, toward=1, hold=1.0).listening_freeze(2.35, 3.4, gaze=(6, 0), tilt=4)
          .cautious_walk(530, 3.4, 5.0))
    # The cut elides time: shot 2 resumes nearer the door rather than replaying the whole crossing.
    a2 = (ActorBuilder("tenant", look, 690, rest_posture=posture).hold(.2)
          .cautious_walk(770, .2, 2.6).listening_freeze(2.6, 3.4, gaze=(5, -1), tilt=-3)
          .guarded_reach(handle, 3.4, 4.6))
    shots = [_shot("a1-listen", 0, 5, "flat", [[0, 450, 400, 1.25], [3.4, 450, 400, 1.25], [5, 520, 400, 1.25]],
                   [[0, .17, 0], [5, .17, 0]], a1.build(5)),
             _shot("a2-door", 5, 10, "flat", [[0, 680, 420, 1.3], [2.6, 720, 420, 1.3], [5, 724, 420, 1.3]],
                   [[0, .17, 0], [5, .17, 0]], a2.build(5))]
    landings = _landings(shots, [a1, a2])
    sfx = [{"id": "room", "path": str(audio["room_tone"]), "start_seconds": 0, "duration_seconds": 10,
            "volume": .16, "role": "ambience"}]
    sfx += [{"id": f"knock-{i}", "path": str(audio["knock"]), "start_seconds": t, "duration_seconds": .3, "volume": .7}
            for i, t in enumerate((1.1, 1.4, 1.7))]
    sfx += [{"id": f"foot-{i}", "path": str(audio["footstep"]), "start_seconds": t, "duration_seconds": .17, "volume": .26}
            for i, t in enumerate(landings)]
    horror = {"presence": [[0, 0, 0], [DURATION, 0, 0]],
              "spill": [[0, .85], [7.5, .85], [7.7, .15], [8.5, .15], [8.9, .6], [DURATION, .6]]}
    video = _video(binding, resolved, "The Third Knock (synthetic P3.2A)",
                   f"Cinematic 2D cartoon horror; library character {character_id}@1 in old_apartment_room@1 under "
                   "cold_moonlight@1. Knock, recoil, listening freeze, guarded approach and touch. No presence figure.",
                   {"width": 720, "height": 1280}, shots, sfx, horror)
    video["audio_qa"] = {"room_window": [.3, .9], "quiet_windows": [[2.5, 3.3]]}
    notes = {("a1-listen", "startled_reaction"): "Three knocks; recoil and look toward the unseen door.",
             ("a2-door", "listening_freeze"): "Door-seam light dims while she holds still.",
             ("a2-door", "guarded_reach"): "Hesitant hand to the real closed-door handle; no opening."}
    timeline = {"version": "1.0", "fps": FPS, "scenes": _timeline(shots, [a1, a2], notes),
                "metadata": {"synthetic": True, "narration": False, "foot_landings": landings,
                             "asset_binding": binding["story_id"]}}
    return video, timeline


def build_story_b(audio: dict[str, Path], *, character_id: str = "victor_hale") -> tuple[dict, dict]:
    """Horizontal corridor story: Victor, a flickering lamp and a figure in the far opening."""
    binding = copy.deepcopy(STORY_B_BINDING)
    binding["cast"]["resident"]["character"] = character_id
    if character_id != "victor_hale":
        binding["story_id"] += "-" + character_id
    resolved = lib.resolve_binding(binding)
    look = resolved["cast"]["resident"]
    posture = lib.get("character", character_id, 1)["rest_posture"]
    handle = resolved["locations"]["hall"]["anchors"]["doors"][0]["handle"]
    b1 = (ActorBuilder("resident", look, 380, rest_posture=posture).hold(.8)
          .cautious_walk(500, .8, 3.6).hold(3.75).startled_reaction(3.75, toward=1, hold=.8, strength=.8))
    b2 = (ActorBuilder("resident", look, 500, rest_posture=posture)
          .listening_freeze(0, 1.8, gaze=(7, -1), tilt=5).cautious_walk(570, 1.8, 3.5)
          .guarded_reach(handle, 3.5, 4.6))
    shots = [_shot("b1-corridor", 0, 5, "hall", [[0, 640, 360, 1.0], [5, 640, 360, 1.0]],
                   [[0, .12, 0], [5, .12, 0]], b1.build(5)),
             _shot("b2-opening", 5, 10, "hall", [[0, 760, 400, 1.45], [2.0, 760, 400, 1.45], [5, 724, 404, 1.45]],
                   [[0, .12, 0], [5, .12, 0]], b2.build(5))]
    landings = _landings(shots, [b1, b2])
    bursts = (3.7, 4.3, 8.2)
    sfx = [{"id": "room", "path": str(audio["room_tone"]), "start_seconds": 0, "duration_seconds": 10,
            "volume": .14, "role": "ambience"},
           {"id": "drone", "path": str(audio["low_drone"]), "start_seconds": 5.2, "duration_seconds": 2.4,
            "volume": .18, "role": "ambience"}]
    sfx += [{"id": f"flicker-{i}", "path": str(audio["switch"]), "start_seconds": t, "duration_seconds": .12, "volume": .35}
            for i, t in enumerate(bursts)]
    sfx += [{"id": f"foot-{i}", "path": str(audio["footstep"]), "start_seconds": t, "duration_seconds": .17, "volume": .26}
            for i, t in enumerate(landings)]
    horror = {"presence": [[0, 0, 0], [5.4, 0, 0], [6.0, .8, 4], [6.6, .8, 4], [7.0, 0, 4], [DURATION, 0, 4]],
              "spill": [[0, .5], [5.9, .5], [6.05, .1], [6.6, .1], [7.0, .5], [DURATION, .5]],
              "flicker": lib.flicker_track(DURATION, list(bursts))}
    video = _video(binding, resolved, "Lamp Four (synthetic P3.2A)",
                   f"Cinematic 2D cartoon horror; library character {character_id}@1 in dark_apartment_corridor@1 under "
                   "flickering_interior@1; tall_hooded@1 presence in the far opening. Restrained, no jump cut.",
                   {"width": 1280, "height": 720}, shots, sfx, horror)
    video["audio_qa"] = {"room_window": [.1, .7], "quiet_windows": []}
    notes = {("b1-corridor", "startled_reaction"): "Overhead lamp stutters; he flinches and looks up the corridor.",
             ("b2-opening", "listening_freeze"): "A hooded shape stands in the dark opening, then is gone.",
             ("b2-opening", "guarded_reach"): "Hesitant hand to door 4C's handle; door stays closed."}
    timeline = {"version": "1.0", "fps": FPS, "scenes": _timeline(shots, [b1, b2], notes),
                "metadata": {"synthetic": True, "narration": False, "foot_landings": landings,
                             "asset_binding": binding["story_id"]}}
    return video, timeline


POSE_STANCE = {"old_apartment_room": 770, "dark_apartment_corridor": 570}
POSE_FRAMES = {"neutral": 6, "startled": 20, "listening_back": 57, "guarded_reach": 111}


def build_pose_reel(character_id: str, env_id: str) -> tuple[dict, dict]:
    """Four-second reference reel: neutral, startle, look back, reach. Plain world light, no overlay."""
    env = lib.environment(env_id)
    look = lib.character_look(character_id)
    posture = lib.get("character", character_id)["rest_posture"]
    handle = next(d["handle"] for d in env["features"]["doors"] if d["interactive"])
    x = POSE_STANCE[env_id]
    actor = (ActorBuilder("ref", look, x, rest_posture=posture).hold(.4)
             .startled_reaction(.4, toward=1, hold=.7).listening_freeze(1.3, 2.3, gaze=(-6, -1), tilt=-6)
             .guarded_reach(handle, 2.3, 3.4)).build(4)
    location = {"kind": "room", "svg": env["svg"], "outdoor": False, "door": env["door"], "window": env["window"],
                "atmosphere": "tense_apartment", "asset": {"environment": env["id"], "revision": env["revision"]}}
    shot = _shot("ref", 0, 4, "ref-loc", [[0, x + 20, 410, 1.5], [4, x + 20, 410, 1.5]], [[0, 0, 0], [4, 0, 0]], actor)
    video = {"duration_seconds": 4, "fps": FPS, "title": f"{character_id} reference", "character_skin": "cartoon_horror",
             "viewport": {"width": 720, "height": 1280}, "audio_mode": "sfx_only", "narration": [], "sfx": [],
             "art_direction": f"Reference reel for {character_id}@{look['design']['revision']} in {env_id}.",
             "locations": {"ref-loc": location}, "shots": [shot]}
    timeline = {"version": "1.0", "fps": FPS, "scenes": [{"scene_id": "ref", "start_seconds": 0, "end_seconds": 4,
                "actions": [{"at_seconds": 0, "duration_seconds": 4, "character_id": "ref", "action": "reference"}]}]}
    return video, timeline


def build_environment_still(env_id: str, preset: str | None, *, presence: tuple[str, str] | None = None,
                            flicker_off: bool = False) -> tuple[dict, dict]:
    """Empty full-frame environment, optionally lit by a preset (with presence at full opacity)."""
    env = lib.environment(env_id)
    location = {"kind": "room", "svg": env["svg"], "outdoor": False, "door": env["door"], "window": env["window"],
                "atmosphere": "tense_apartment", "asset": {"environment": env["id"], "revision": env["revision"]},
                "anchors": env["features"]}
    video = {"duration_seconds": 1, "fps": FPS, "title": f"{env_id} reference", "character_skin": "cartoon_horror",
             "viewport": {"width": 1280, "height": 720}, "audio_mode": "sfx_only", "narration": [], "sfx": [],
             "art_direction": f"Environment reference {env_id}@{env['revision']} ({preset or 'unlit'}).",
             "locations": {"env": location},
             "shots": [{**_shot("env", 0, 1, "env", [[0, 640, 360, 1], [1, 640, 360, 1]],
                                [[0, .17 if env["window"] else .12, 0], [1, .17 if env["window"] else .12, 0]], None),
                        "actors": []}]}
    if preset:
        location["cinematic"] = lib.lighting_geometry(env, preset, presence=presence)
        video["horror"] = {"presence": [[0, .85 if presence else 0, 0], [1, .85 if presence else 0, 0]],
                           "spill": [[0, .8], [1, .8]], "flicker": [[0, .05 if flicker_off else 1], [1, .05 if flicker_off else 1]]}
    timeline = {"version": "1.0", "fps": FPS, "scenes": [{"scene_id": "env", "start_seconds": 0, "end_seconds": 1,
                "actions": [{"at_seconds": 0, "duration_seconds": 1, "character_id": "none", "action": "establish"}]}]}
    return video, timeline
