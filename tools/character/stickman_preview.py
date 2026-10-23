"""Synthetic renderer proof data; uses the existing planted-foot walk and StoryVideo contract.

No user story, inference, TTS, pipeline orchestration or approval is performed here.
"""

from __future__ import annotations

from pathlib import Path

from tools.character.story_motion import stand_pose, walk_clip

DURATION = 10.0
FPS = 30
SCRAPE_AT = 1.2
WALK_START, WALK_END = 4.0, 8.4

ROOM = '''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
<defs>
 <linearGradient id="wall" x2="0" y2="1"><stop stop-color="#101925"/><stop offset="1" stop-color="#354350"/></linearGradient>
 <linearGradient id="floor" x2="0" y2="1"><stop stop-color="#35404a"/><stop offset="1" stop-color="#101a25"/></linearGradient>
 <radialGradient id="spill"><stop stop-color="#91bbcd" stop-opacity=".20"/><stop offset="1" stop-color="#91bbcd" stop-opacity="0"/></radialGradient>
</defs>
<rect width="1280" height="620" fill="url(#wall)"/>
<path d="M 0 95 H 1280 M 0 104 H 1280" stroke="#45525d" stroke-opacity=".25"/>
<path d="M 330 145 l -3 80 7 13 -4 42 M 534 265 l 5 100 -9 23" fill="none" stroke="#101820" opacity=".4"/>
<rect y="620" width="1280" height="100" fill="url(#floor)"/>
<path d="M 0 617 H 1280 M 0 623 H 1280" stroke="#101821" stroke-width="4"/>
<path d="M 250 620 L 200 720 M 360 620 L 340 720 M 470 620 V 720 M 580 620 L 620 720 M 690 620 L 780 720"
 fill="none" stroke="#6a7379" opacity=".14"/>
<ellipse cx="370" cy="560" rx="180" ry="200" fill="url(#spill)"/>
<path d="M 276 524 H 327 V 534 H 276 Z M 281 490 V 615 M 323 490 V 615 M 281 489 H 323"
 stroke="#101a23" stroke-width="6" fill="#22313d"/>
<rect x="558" y="292" width="104" height="328" fill="#0c141c" stroke="#596970" stroke-width="5"/>
<rect x="574" y="308" width="72" height="100" fill="#728e99" opacity=".1"/>
<path d="M 555 620 H 665" stroke="#839496" stroke-width="3"/>
<rect x="272" y="244" width="87" height="146" fill="#0b1828" stroke="#4b5d6c" stroke-width="5"/>
<path d="M 278 254 L 350 244 M 278 270 L 350 260 M 278 286 L 350 276" stroke="#6c8ba4" opacity=".3"/>
</svg>'''


def build_preview(audio: dict[str, Path]) -> tuple[dict, dict]:
    """Ten seconds of explicit, seekable acting; all asset paths are supplied by the caller."""
    initial = stand_pose(365, 1)
    walking = walk_clip(365, 520, WALK_START, WALK_END, 1, fps=FPS, period=0.9, swing=0.24, lift=14)
    tracks = {}
    for limb, keys in walking["tracks"].items():
        opening = [[0, *initial[limb]], [SCRAPE_AT, *initial[limb]]]
        if limb == "root":
            opening += [[1.6, 359, 522], [2.5, 362, 518], [3.2, *initial[limb]]]
        elif limb == "left_hand":
            opening += [[1.6, 328, 457], [2.5, 333, 476], [3.2, *initial[limb]]]
        elif limb == "right_hand":
            opening += [[1.6, 406, 450], [2.5, 407, 475], [3.2, *initial[limb]]]
        tracks[limb] = opening + keys + [[DURATION, *keys[-1][1:]]]
    # A deliberate reach/hold at the door after the feet have settled.
    tracks["right_hand"][-1:] = [[8.9, 553, 441], [9.5, 555, 437], [DURATION, 555, 437]]
    actor = {"id": "preview-actor", "look": {"shirt": "#52778c", "skin": "#e2bd9b", "hair": "#303c42"},
             **tracks, "facing_keys": [[0, 1]],
             "face": [[0, 0.15, 0, 0, 0, 0, 0], [SCRAPE_AT, 0.15, 0, 0, 0, 0, 0],
                      [1.6, 1.2, -5, -1, -0.7, 0, -11], [2.4, 0.9, -5, -1, -0.4, 0, -8],
                      [3.2, 0.8, 5, 0, -0.3, 0, 6], [8.4, 0.8, 5, 0, -0.3, 0, 3],
                      [DURATION, 0.8, 5, -2, -0.4, 0, -2]],
             "opacity": [[0, 1], [DURATION, 1]]}
    cues = [{"id": "room", "path": str(audio["room_tone"]), "start_seconds": 0,
             "duration_seconds": DURATION, "volume": 0.5},
            {"id": "scrape", "path": str(audio["furniture_scrape"]), "start_seconds": SCRAPE_AT,
             "duration_seconds": 0.9, "volume": 0.85}]
    cues += [{"id": f"foot-{i}", "path": str(audio["footstep"]),
              "start_seconds": round(t * FPS) / FPS, "duration_seconds": 0.17, "volume": 0.38}
             for i, t in enumerate(walking["landings"])]
    video = {"duration_seconds": DURATION, "fps": FPS, "title": "Synthetic apartment renderer proof",
             "character_skin": "stickman_horror", "viewport": {"width": 720, "height": 1280},
             "audio_mode": "sfx_only", "narration": [], "sfx": cues,
             "art_direction": "Anonymous apartment, monochrome stickman skeletal acting, cold window light, "
                              "closed door, restrained camera; original synthetic renderer proof, no captions.",
             "locations": {"preview-room": {"kind": "room", "svg": ROOM, "outdoor": False,
                         "door": {"x": 565, "y": 300, "w": 90, "h": 320, "hinge": "right"},
                         "window": {"x": 280, "y": 252, "w": 72, "h": 130}}},
             "shots": [{"id": "preview-shot", "start_seconds": 0, "end_seconds": DURATION,
                        "view": "world", "location": "preview-room", "weather": None,
                        "camera": [[0, 475, 360, 1.0], [DURATION, 485, 360, 1.035]],
                        "light": [[0, 0.1, 0], [1.5, 0.13, 0], [3.0, 0.1, 0], [DURATION, 0.12, 0]],
                        "door": [[0, 0], [DURATION, 0]], "actors": [actor], "items": [], "vehicles": []}]}
    actions = [
        {"at_seconds": 0, "duration_seconds": SCRAPE_AT, "character_id": actor["id"], "action": "stand"},
        {"at_seconds": SCRAPE_AT, "duration_seconds": 2.8, "character_id": actor["id"], "action": "react",
         "notes": "Scrape at frame 36; flinch, head/gaze turn, settle before walking."},
        {"at_seconds": WALK_START, "duration_seconds": WALK_END - WALK_START, "character_id": actor["id"], "action": "walk"},
        {"at_seconds": WALK_END, "duration_seconds": DURATION - WALK_END, "character_id": actor["id"], "action": "reach"}]
    timeline = {"version": "1.0", "fps": FPS, "scenes": [{"scene_id": "preview-shot", "start_seconds": 0,
                "end_seconds": DURATION, "actions": actions}],
                "metadata": {"synthetic": True, "narration": False, "foot_landings": walking["landings"]}}
    return video, timeline
