"""P3.2A versioned asset library for Cinematic 2D Cartoon Supernatural Horror.

Local, deterministic data only: SVG path data, procedural backdrops and keyframe
presets that resolve into the existing `story_video` contract (StoryVideo, Actor,
two-bone IK). Nothing here renders, animates or calls a remote service.

Every asset has a stable `id` and integer `revision`. A content hash in the
manifest exposes silent edits: changing an asset's data requires a new revision.
Bindings pin `id@revision`; resolving a different revision fails closed.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re

from tools.character import horror_environments as envs
from tools.character.story_video import ARM, LEG

LIBRARY_ID = "openmontage.cinematic_cartoon_horror"
LIBRARY_VERSION = "p3.2a.1"
SAFE_TOP_Y = 40  # rig-space minimum y for anything the camera must keep in frame

RIGS = {
    "biped_v1": {"id": "biped_v1", "revision": 1, "kind": "rig",
                 "description": "Existing motion.ts two-bone IK biped (StoryVideo actorState).",
                 "arm": list(ARM), "leg": list(LEG), "default_posture": [5, -99, 10, -160],
                 "skins": ["cartoon_horror"], "face_track": ["brow", "gaze_x", "gaze_y", "mouth", "lid", "tilt"]},
}

# Head-local paths: head centre (0, 0), character faces +x, chin near y=+40.
CHARACTERS = {
    "nora_vale": {
        "id": "nora_vale", "revision": 1, "kind": "character", "rig": "biped_v1",
        "summary": "Adult woman, early thirties; long dark auburn hair, heart-shaped face, belted trench coat, ankle boots.",
        "rest_posture": [5, -99, 10, -160],
        "design": {
            "palette": {"skin": "#c9a58a", "hair": "#4a2a22", "top": "#3d4a44", "top_shade": "#222b27",
                        "bottom": "#2a2d36", "shoes": "#1c1a1d", "accent": "#7d6446"},
            "build": {"shoulder": 20, "hip": 22, "sleeve": 16, "leg": 18, "head": .96, "hand": .92},
            "outfit": "long_coat", "footwear": "boots",
            "face": {"outline": "M -28 -16 Q -26 -42 2 -42 Q 30 -41 31 -16 L 31 -2 L 37 6 L 30 11 Q 27 29 12 38 Q 0 42 -12 34 Q -25 23 -29 6 Z",
                     "shade": "M 22 -26 Q 34 -12 30 12 Q 27 28 12 37 Q 26 30 29 10 L 36 6 L 31 -2 L 31 -16 Z",
                     "ear": [-28, 6], "nose": "M 14 -2 l -1 11 5 1",
                     "mouth": [16, 25, 13], "eyes": {"shape": "almond", "left": [3, -3, 6.6], "right": [23, -4, 5.6],
                                                     "iris": "#4c5a4a"},
                     "brow": {"width": 2.6}},
            "hair": {"back": "M -36 -18 Q -42 -50 -4 -53 Q 32 -55 37 -26 L 30 -18 Q 8 -30 -16 -18 Q -30 12 -22 50 Q -18 70 -4 80 L -42 82 Q -52 40 -36 -18 Z",
                     "front": "M -31 -12 Q -31 -45 4 -47 Q 34 -46 35 -20 Q 22 -35 6 -31 Q -6 -22 -18 -12 L -23 8 L -30 6 Z",
                     "highlight": "M -20 -36 Q -2 -44 18 -38"},
            "features": [{"d": "M 27 17 m -1.3 0 a 1.3 1.3 0 1 0 2.6 0 a 1.3 1.3 0 1 0 -2.6 0", "fill": "#5a3a32"},
                         {"d": "M -30 14 a 3 3 0 1 0 0.1 0", "stroke": "#b49a62", "width": 1.2}],
        },
    },
    "victor_hale": {
        "id": "victor_hale", "revision": 1, "kind": "character", "rig": "biped_v1",
        "summary": "Adult man, mid fifties; receding grey hair, square stubbled jaw, glasses, heavy knit cardigan, slight stoop.",
        "rest_posture": [8, -96, 15, -157],
        "design": {
            "palette": {"skin": "#a87e64", "hair": "#8f8b84", "top": "#5a4e34", "top_shade": "#363020",
                        "bottom": "#463b31", "shoes": "#2a211b", "accent": "#bfb8a6"},
            "build": {"shoulder": 27, "hip": 29, "sleeve": 22, "leg": 23, "head": 1.04, "hand": 1.1},
            "outfit": "cardigan", "footwear": "shoes",
            "face": {"outline": "M -31 -18 Q -29 -44 2 -44 Q 33 -43 34 -18 L 34 -4 L 41 6 L 34 12 L 34 28 Q 30 40 12 42 L -6 41 Q -24 36 -30 20 L -32 6 Z",
                     "shade": "M 24 -28 Q 37 -14 34 12 L 34 28 Q 30 40 12 42 Q 28 34 31 14 L 40 6 L 34 -4 Z",
                     "ear": [-30, 6], "nose": "M 14 -5 l -3 16 9 2",
                     "mouth": [16, 27, 15], "eyes": {"shape": "round", "left": [3, -2, 5.2], "right": [24, -3, 4.6],
                                                     "iris": "#3d4246"},
                     "brow": {"width": 4.4, "color": "#5d5a55"}},
            "hair": {"front": "M -34 6 L -36 -20 Q -34 -40 -14 -44 L -4 -42 Q -12 -36 -17 -24 L -25 -20 L -27 4 Z",
                     "highlight": "M -30 -22 Q -26 -36 -14 -40"},
            "features": [{"d": "M -22 18 Q -10 40 12 42 Q 30 40 34 26 L 34 14 Q 26 22 20 20 Q 14 16 8 20 Q 0 24 -10 18 Z",
                          "fill": "#55524c", "opacity": .24},
                         {"d": "M 8 20 Q 15 15 25 20 Q 16 22 8 20 Z", "fill": "#6a665e"},
                         {"d": "M -6 -10 H 12 V 4 H -6 Z M 17 -11 H 31 V 3 H 17 Z M 12 -4 H 17 M -6 -6 L -28 -2",
                          "stroke": "#202426", "width": 1.8},
                         {"d": "M -3 7 q 6 3 12 0 M 19 6 q 5 2 10 0", "stroke": "#7d5d4e", "width": 1}],
        },
    },
}

SILHOUETTES = {
    "featureless_figure": {"id": "featureless_figure", "revision": 1, "kind": "silhouette",
                           "summary": "Faceless head-and-shoulders shape used for occluded window reveals (P3.1 v2 shape).",
                           "path": "M -10 -7 Q -11 -26 1 -29 Q 15 -28 13 -10 L 9 5 Q 29 14 29 62 H -27 Q -26 18 -9 7 Z",
                           "bottom": 62, "color": "#02080d"},
    "tall_hooded": {"id": "tall_hooded", "revision": 1, "kind": "silhouette",
                    "summary": "Tall, narrow, hooded full-body shape for dark openings; no face or limbs.",
                    "path": "M -9 -30 Q -12 -46 0 -48 Q 13 -46 10 -30 Q 22 -22 20 0 L 24 40 Q 20 52 16 62 H -16 Q -22 50 -24 38 L -20 0 Q -22 -22 -9 -30 Z",
                    "bottom": 62, "color": "#010406"},
}

PROPS = {
    "interior_door": {"id": "interior_door", "revision": 1, "kind": "prop",
                      "summary": "StoryVideo door leaf; closed handle at (x+16, y+120) for a right hinge.",
                      "anchors": ["handle", "seam"]},
    "sash_window": {"id": "sash_window", "revision": 1, "kind": "prop",
                    "summary": "StoryVideo glass with a central mullion cross; four pane polygons.", "anchors": ["panes", "centre"]},
    "ceiling_lamp": {"id": "ceiling_lamp", "revision": 1, "kind": "prop",
                     "summary": "Fixture bulb point; light cone to the floor.", "anchors": ["bulb", "pool"]},
    "floor_lamp": {"id": "floor_lamp", "revision": 1, "kind": "prop",
                   "summary": "Standing lamp; bulb under the shade.", "anchors": ["bulb", "pool"]},
}

ENVIRONMENTS = {
    "old_apartment_room": {"id": "old_apartment_room", "revision": 1, "kind": "environment",
                           "summary": "Worn apartment room: sash window, interior door, floor lamp, armchair, side table.",
                           "builder": envs.old_apartment_room, "props": ["interior_door", "sash_window", "floor_lamp"]},
    "dark_apartment_corridor": {"id": "dark_apartment_corridor", "revision": 1, "kind": "environment",
                                "summary": "Narrow apartment corridor: interactive door 4C, neighbour door, three ceiling lamps, dark far opening.",
                                "builder": envs.dark_apartment_corridor, "props": ["interior_door", "ceiling_lamp"]},
}

ACTING = {
    "cautious_walk": {"id": "cautious_walk", "revision": 1, "kind": "acting",
                      "summary": "Planted-foot walk_clip with guarded hands and a forward-tense posture."},
    "startled_reaction": {"id": "startled_reaction", "revision": 1, "kind": "acting",
                          "summary": "Quick recoil: crouch, shoulders back, hands drawn in, gaze to the source; feet stay planted."},
    "listening_freeze": {"id": "listening_freeze", "revision": 1, "kind": "acting",
                         "summary": "Root and feet locked; gaze/tilt toward a target; sub-pixel hand tremor."},
    "guarded_reach": {"id": "guarded_reach", "revision": 1, "kind": "acting",
                      "summary": "Feet planted; hesitant approach, small withdrawal, then contact held at an anchor."},
}

LIGHTING = {
    "cold_moonlight": {"id": "cold_moonlight", "revision": 1, "kind": "lighting", "requires": "window",
                       "summary": "Cool window key with a floor beam, negative fill elsewhere and warm door-seam spill."},
    "dim_corridor": {"id": "dim_corridor", "revision": 1, "kind": "lighting", "requires": "lamp",
                     "summary": "Weak overhead cones and floor pools; everything between lamps falls off."},
    "flickering_interior": {"id": "flickering_interior", "revision": 1, "kind": "lighting", "requires": "lamp",
                            "summary": "Dim interior where one lamp follows a deterministic flicker track."},
}

REGISTRIES = {"rig": RIGS, "character": CHARACTERS, "silhouette": SILHOUETTES, "prop": PROPS,
              "environment": ENVIRONMENTS, "acting": ACTING, "lighting": LIGHTING}
HEX = re.compile(r"^#[0-9a-f]{6}$")

# Stored revision fingerprints, never generated from mutable data at import time.
# Keep an existing revision's fingerprint: changed artwork/data needs a new revision.
REVISION_HASHES = {
    ('rig', 'biped_v1', 1): '2f7d00bd2d0aab5accad06da1a5cad3fdd8c85f337c0dc9bc6fee2602a165bc8',
    ('character', 'nora_vale', 1): '83eadee65a281e93571f3b14bcaad88aa427b2b219f5e3b476465732941873dc',
    ('character', 'victor_hale', 1): '5d2a90748af37a8006a6c445fc2c07d6047404e088bdb1ab86b178964f134052',
    ('silhouette', 'featureless_figure', 1): '75caaa9b0b23832534435982b5fdd1472928a1e41e15f326790abe556e6f1170',
    ('silhouette', 'tall_hooded', 1): 'e8c86bb20ba49670c800592646f035c4ed640a0c9c77a10b3776bfa7e2268191',
    ('prop', 'ceiling_lamp', 1): 'bf6bb04d04d411b625a5145442945db665b5e4b625aae2966d210caa63a693c1',
    ('prop', 'floor_lamp', 1): '4290a863d09fce23c66329010ba6fddcdc6bf64fb6cd5f8357911c5d5c9687ef',
    ('prop', 'interior_door', 1): 'db40023ff16c70785f5b4ca8ce27040928376ace436631d77e48d61665fe1ee4',
    ('prop', 'sash_window', 1): '1be071078c1c9316b2a322ec5ed63def7abfb0f8151a63c3719daa018aa038c8',
    ('environment', 'dark_apartment_corridor', 1): '3d825c5a7878504e37a2aa01f439bfa168656728f0d4a74b6c15d510f8bc3aad',
    ('environment', 'old_apartment_room', 1): 'd6aa383c42ab58ebec9e5e5e4edd7ebd2afa7d80167518deaa5c307fd6d653f2',
    ('acting', 'cautious_walk', 1): 'd22f4eb74b58045b2d77b5da114c85d5d754f3de74cba707995cad43e6aeea43',
    ('acting', 'guarded_reach', 1): 'd6ba0421adae79b3fc3381f711f487c9437221cc37e0d49e675b0f3cbdd080b5',
    ('acting', 'listening_freeze', 1): '80a92c8d07d08d1eab9d2e7b5abc58bb7b1b984b7f5b8d49a20d2bea07c96629',
    ('acting', 'startled_reaction', 1): '150598b04112b8beda70d533e3e32530adac4c91fb136a240d669778552ed4a9',
    ('lighting', 'cold_moonlight', 1): '4a586b1d6cba9a178b1632a1e977200d28da202372f9a211cf050ad9b189b9f8',
    ('lighting', 'dim_corridor', 1): '02f5e9d8e0cca2d4769b4b25742deb2d55ba3075771f2ed4f6efe4fbb4a1e566',
    ('lighting', 'flickering_interior', 1): '1e465fd4553d3d5e9a87c8061af0bce348de90d53a6416470dc0648368d1c988',
}


def _hashable(entry: dict) -> dict:
    data = {k: v for k, v in entry.items() if k != "builder"}
    if "builder" in entry:
        data["resolved"] = entry["builder"]()
    return data


def content_hash(entry: dict) -> str:
    return hashlib.sha256(json.dumps(_hashable(entry), sort_keys=True).encode()).hexdigest()


def get(kind: str, asset_id: str, revision: int | None = None) -> dict:
    if not isinstance(kind, str) or not isinstance(asset_id, str):
        raise ValueError("Asset kind and id must be strings")
    if revision is not None and (type(revision) is not int or revision < 1):
        raise ValueError("Asset revision must be a positive integer")
    registry = REGISTRIES.get(kind)
    if registry is None or asset_id not in registry:
        raise ValueError(f"Unknown {kind} asset: {asset_id}")
    entry = registry[asset_id]
    if revision is not None and revision != entry["revision"]:
        raise ValueError(f"{kind} {asset_id}@{revision} is not available (library has revision {entry['revision']})")
    _check_revision(entry)
    return copy.deepcopy(entry)


def _check_revision(entry: dict) -> None:
    key = (entry["kind"], entry["id"], entry["revision"])
    if REVISION_HASHES.get(key) != content_hash(entry):
        raise ValueError(f"Asset {key[0]} {key[1]}@{key[2]} content hash mismatch; changed content needs a new revision")


def check_library() -> None:
    """Fail on malformed assets: rig mismatch, bad colors, unreachable rest posture."""
    for kind, registry in REGISTRIES.items():
        for asset_id, entry in registry.items():
            if entry["id"] != asset_id or entry["kind"] != kind or type(entry["revision"]) is not int or entry["revision"] < 1:
                raise ValueError(f"Bad registry entry {kind}/{asset_id}")
            _check_revision(entry)
    for c in CHARACTERS.values():
        rig = get("rig", c["rig"])
        if rig["arm"] != list(ARM) or rig["leg"] != list(LEG):
            raise ValueError(f"{c['id']}: rig bones differ from the shared IK")
        if not all(HEX.match(v) for v in c["design"]["palette"].values()):
            raise ValueError(f"{c['id']}: palette must be #rrggbb")
        sdx, sdy, hdx, hdy = c["rest_posture"]
        for hand, (u, dy) in (("left", (-17, 3)), ("right", (27, 3))):
            d = math.dist((sdx, sdy), (u, dy))
            if not abs(ARM[0] - ARM[1]) < d < sum(ARM):
                raise ValueError(f"{c['id']}: rest posture makes the {hand} hand unreachable")
        if hdy * c["design"]["build"]["head"] < -175 or not 0.8 <= c["design"]["build"]["head"] <= 1.2:
            raise ValueError(f"{c['id']}: head placement/scale outside the safe range")


def manifest() -> dict:
    check_library()
    assets = []
    for kind, registry in REGISTRIES.items():
        for asset_id in sorted(registry):
            entry = registry[asset_id]
            assets.append({"kind": kind, "id": asset_id, "revision": entry["revision"],
                           "summary": entry.get("summary", entry.get("description", "")),
                           "sha256": content_hash(entry)})
    return {"library": LIBRARY_ID, "version": LIBRARY_VERSION, "assets": assets}


def character_look(character_id: str, revision: int | None = None) -> dict:
    """StoryVideo `look` for a character; `design` selects the data-driven cast artwork."""
    c = get("character", character_id, revision)
    d = copy.deepcopy(c["design"])
    p = d["palette"]
    return {"shirt": p["top"], "skin": p["skin"], "hair": p["hair"], "treatment": "cinematic",
            "design": {"id": c["id"], "revision": c["revision"], **d}}


def environment(env_id: str, revision: int | None = None) -> dict:
    entry = get("environment", env_id, revision)
    built = entry["builder"]()
    return {"id": entry["id"], "revision": entry["revision"], **built}


# ---------------------------------------------------------------- lighting

def _presence_geometry(env: dict, anchor: str, silhouette_id: str) -> dict:
    anchors = env["features"]["presence_anchors"]
    if anchor not in anchors:
        raise ValueError(f"{env['id']} has no presence anchor '{anchor}'")
    a, s = anchors[anchor], get("silhouette", silhouette_id)
    y = a["y"] - s["bottom"] * a["scale"] if a["kind"] == "opening" else a["y"]
    out = {"silhouette": s["id"], "revision": s["revision"], "path": s["path"], "color": s["color"],
           "x": a["x"], "y": y, "scale": a["scale"], "clip": a["clip"]}
    if a["kind"] == "window":
        out["backdrop"] = {"color": "#384b50", "opacity": .47}
    return out


def lighting_geometry(env: dict, preset_id: str, *, flicker_lamp: str | None = None,
                      presence: tuple[str, str] | None = None) -> dict:
    """Resolve a lighting preset against an environment's own light features.

    Returns StoryVideo `location.cinematic` geometry. Raises when the environment
    lacks the feature the preset needs (no silent room-specific fallback).
    """
    preset = get("lighting", preset_id)
    f = env["features"]
    floor = f["floor_y"]
    geom = {"version": 1, "preset": preset_id, "revision": preset["revision"],
            "negative_fill": {"color": "#02080e", "opacity": .5}, "pools": [], "beams": [], "lamps": [], "seams": []}
    if preset["requires"] == "window" and not f["windows"]:
        raise ValueError(f"{preset_id} needs a window; {env['id']} has none")
    if preset["requires"] == "lamp" and not f["lamps"]:
        raise ValueError(f"{preset_id} needs a lamp; {env['id']} has none")
    for door in f["doors"]:
        x0, x1, y = door["seam"]
        geom["seams"].append({"x0": x0, "x1": x1, "y": y, "color": "#c5ad72", "driver": "spill"})
        if door["interactive"]:
            r = door["rect"]
            geom["pools"].append({"cx": r["x"] + r["w"] / 2, "cy": floor - 110, "rx": 120, "ry": 150,
                                  "driver": "spill", "strength": .55})
    if preset_id == "cold_moonlight":
        win = f["windows"][0]["rect"]
        run = floor - win["y"]
        dx = run * .55
        geom["beams"].append({"points": [[win["x"], win["y"] + 8], [win["x"] + win["w"], win["y"]],
                                         [win["x"] + win["w"] + dx, floor], [win["x"] + dx * .7, floor]],
                              "color": "#8da7a0", "opacity": .16, "driver": "constant"})
        geom["pools"].append({"cx": win["x"] + win["w"] / 2 + dx * .45, "cy": win["y"] + run * .55,
                              "rx": 175, "ry": 215, "driver": "constant", "strength": .95})
        geom["haze"] = {"cx": win["x"] + win["w"] / 2 + dx * .6, "cy": floor - 14, "rx": 150, "ry": 20,
                        "color": "#75918f", "opacity": .03}
    else:
        flicker_ids = set()
        if preset_id == "flickering_interior":
            flicker_ids = {flicker_lamp or f["lamps"][0]["id"]}
            if not flicker_ids <= {l["id"] for l in f["lamps"]}:
                raise ValueError(f"Unknown flicker lamp {flicker_lamp} in {env['id']}")
        geom["negative_fill"]["opacity"] = .56
        for lamp in f["lamps"]:
            driver = "flicker" if lamp["id"] in flicker_ids else "constant"
            x, y = lamp["x"], lamp["y"]
            spread = 150 if lamp["kind"] == "ceiling" else 120
            geom["lamps"].append({"id": lamp["id"], "x": x, "y": y, "r": 70, "color": "#d8c48a", "driver": driver})
            geom["beams"].append({"points": [[x - 16, y + 4], [x + 16, y + 4], [x + spread, floor], [x - spread, floor]],
                                  "color": "#cdb984", "opacity": .1, "driver": driver})
            # Wide, overlapping pools: separated ellipses leave rounded dark columns that read as figures.
            geom["pools"].append({"cx": x, "cy": floor - 170, "rx": spread + 110, "ry": 330,
                                  "driver": driver, "strength": .85})
    if presence:
        geom["presence"] = _presence_geometry(env, *presence)
    return geom


def flicker_track(duration: float, bursts: list[float]) -> list[list[float]]:
    """Deterministic lamp intensity: steady at 1 with fixed stutter shapes at `bursts`."""
    shape = [(0, 1), (.033, .12), (.1, .85), (.133, .04), (.233, .7), (.3, .18), (.4, 1)]
    keys = [[0, 1.0]]
    for b in sorted(bursts):
        for dt, v in shape:
            t = round(b + dt, 4)
            if t <= keys[-1][0] or t >= duration:
                continue
            keys.append([t, v])
    keys.append([duration, 1.0])
    return keys


# ---------------------------------------------------------------- bindings

BINDING_KEYS = {"story_id", "library", "library_version", "cast", "locations"}


def validate_binding(binding: dict) -> None:
    """Minimum asset binding a future Story Visual Bible must provide (see docs)."""
    def fields(value, required, optional=(), *, label):
        if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
            raise ValueError(f"{label}: required keys {sorted(required)}, optional keys {sorted(optional)}")

    def pinned(value, id_key, kind, *, optional=(), label):
        fields(value, {id_key, "revision"}, optional, label=label)
        if type(value["revision"]) is not int or value["revision"] < 1:
            raise ValueError(f"{label}: revision must be a positive integer")
        return get(kind, value[id_key], value["revision"])

    fields(binding, BINDING_KEYS, label="Binding")
    if not isinstance(binding["story_id"], str) or not binding["story_id"].strip():
        raise ValueError("Binding needs a nonblank story_id")
    if binding["library"] != LIBRARY_ID or binding["library_version"] != LIBRARY_VERSION:
        raise ValueError("Binding targets a different asset library/version")
    if any(not isinstance(binding[k], dict) or not binding[k] for k in ("cast", "locations")):
        raise ValueError("Binding needs at least one cast member and one location")
    check_library()
    for role, ref in binding["cast"].items():
        if not isinstance(role, str) or not role.strip():
            raise ValueError("Cast role must be a nonblank string")
        pinned(ref, "character", "character", label=f"Cast {role}")
    characters = [ref["character"] for ref in binding["cast"].values()]
    if len(set(characters)) != len(characters):
        raise ValueError("One character asset cannot play two roles in the same story")
    for key, ref in binding["locations"].items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Location key must be a nonblank string")
        env_ref = pinned(ref, "environment", "environment", optional={"lighting", "presence"}, label=f"Location {key}")
        if "lighting" not in ref:
            raise ValueError(f"Location {key}: lighting required")
        light = ref["lighting"]
        pinned(light, "id", "lighting", optional={"flicker_lamp"}, label=f"Location {key}.lighting")
        env = {"id": env_ref["id"], **env_ref["builder"]()}
        if "flicker_lamp" in light and (light["id"] != "flickering_interior" or
                light["flicker_lamp"] not in [lamp["id"] for lamp in env["features"]["lamps"]]):
            raise ValueError(f"Location {key}: invalid flicker_lamp for this lighting/environment")
        presence = ref.get("presence")
        if "presence" in ref:
            pinned(presence, "silhouette", "silhouette", optional={"anchor"}, label=f"Location {key}.presence")
            if not isinstance(presence.get("anchor"), str) or presence["anchor"] not in env["features"]["presence_anchors"]:
                raise ValueError(f"Location {key}: unknown presence anchor")
        lighting_geometry(env, light["id"], flicker_lamp=light.get("flicker_lamp"),
                          presence=(presence["anchor"], presence["silhouette"]) if presence else None)


def resolve_binding(binding: dict) -> dict:
    validate_binding(binding)
    cast = {role: character_look(ref["character"], ref["revision"]) for role, ref in binding["cast"].items()}
    locations = {}
    for key, ref in binding["locations"].items():
        env = environment(ref["environment"], ref["revision"])
        presence = ref.get("presence")
        geom = lighting_geometry(env, ref["lighting"]["id"], flicker_lamp=ref["lighting"].get("flicker_lamp"),
                                 presence=(presence["anchor"], presence["silhouette"]) if presence else None)
        locations[key] = {"kind": "room", "svg": env["svg"], "outdoor": False, "door": env["door"],
                          "window": env["window"], "atmosphere": "tense_apartment", "cinematic": geom,
                          "asset": {"environment": env["id"], "revision": env["revision"]},
                          "anchors": env["features"]}
    return {"cast": cast, "locations": locations}
