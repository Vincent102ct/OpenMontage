"""P3.1 synthetic style proof. No real story or reviewed package is read."""
from pathlib import Path

from tools.character.stickman_preview import build_preview as build_motion_preview
from tools.character.story_motion import walk_clip

ROOM = '''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
<defs>
 <linearGradient id="wall" x2="0" y2="1"><stop stop-color="#101c2a"/><stop offset=".65" stop-color="#344751"/><stop offset="1" stop-color="#23343d"/></linearGradient>
 <linearGradient id="floor" x2="0" y2="1"><stop stop-color="#3d4647"/><stop offset="1" stop-color="#111c28"/></linearGradient>
 <linearGradient id="moon" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#a2cedc" stop-opacity=".15"/><stop offset="1" stop-color="#7eafc2" stop-opacity="0"/></linearGradient>
 <radialGradient id="warm"><stop stop-color="#c08b4c" stop-opacity=".2"/><stop offset="1" stop-color="#c08b4c" stop-opacity="0"/></radialGradient>
 <radialGradient id="cool"><stop stop-color="#729aaa" stop-opacity=".25"/><stop offset="1" stop-color="#729aaa" stop-opacity="0"/></radialGradient>
</defs>
<rect width="1280" height="620" fill="url(#wall)"/>
<path d="M 0 159 H 1280 M 0 166 H 1280" stroke="#7a878c" stroke-opacity=".12" stroke-width="3"/>
<path d="M 350 166 l -5 48 7 10 -5 42 m 5 -42 14 -9 M 530 165 l -2 50 9 21 -5 36 M 554 405 l -7 27 5 19"
 stroke="#0c1925" stroke-width="2" fill="none" opacity=".65"/>
<path d="M 380 330 v 276 M 465 330 v 276 M 550 330 v 276" stroke="#8a9ca0" stroke-opacity=".035" stroke-width="24"/>
<rect y="620" width="1280" height="100" fill="url(#floor)"/>
<path d="M 0 610 H 1280 M 0 621 H 1280" stroke="#111e29" stroke-width="7"/>
<path d="M 0 614 H 1280" stroke="#8e9b99" opacity=".2"/>
<path d="M 290 620 L 235 720 M 370 620 L 350 720 M 450 620 L 475 720 M 530 620 L 590 720 M 610 620 L 705 720 M 0 668 H 1280 M 0 714 H 1280"
 stroke="#7a8380" opacity=".15" fill="none"/>
<path d="M 282 255 L 352 255 L 535 620 L 355 620 Z" fill="url(#moon)"/>
<path d="M 280 382 L 352 382 L 499 679 L 348 679 Z" fill="url(#moon)" opacity=".55"/>
<ellipse cx="390" cy="478" rx="145" ry="206" fill="url(#cool)"/>
<ellipse cx="607" cy="626" rx="93" ry="49" fill="url(#warm)"/>
<rect x="272" y="244" width="87" height="146" fill="#091626" stroke="#52646e" stroke-width="5"/>
<path d="M 278 254 L 351 244 M 278 271 L 351 261 M 278 288 L 351 278" stroke="#9ab6bf" opacity=".25"/>
<path d="M 278 389 H 362" stroke="#61767e" stroke-width="6"/>
<g transform="rotate(-5 464 263)">
 <rect x="438" y="226" width="48" height="70" fill="#101c25" stroke="#6c6557" stroke-width="4"/>
 <rect x="443" y="232" width="38" height="58" fill="#354046"/>
 <ellipse cx="462" cy="249" rx="8" ry="10" fill="#26313a"/>
 <path d="M 449 282 Q 449 260 463 262 Q 478 261 478 282" fill="#212e38"/>
</g>
<path d="M 280 522 H 326 V 531 H 280 Z M 284 531 V 616 M 323 531 V 616" stroke="#111c27" stroke-width="6" fill="#24343e"/>
<path d="M 292 519 l -4 -15 h 12 l -3 15" fill="#606d6b" stroke="#172530" stroke-width="2"/>
<rect x="558" y="292" width="104" height="328" fill="#09131b" stroke="#5c6c6c" stroke-width="5"/>
<path d="M 554 622 H 667" stroke="#9d9174" stroke-width="3" opacity=".55"/>
</svg>'''


def build_preview(audio: dict[str, Path]) -> tuple[dict, dict]:
    video, timeline = build_motion_preview(audio)
    video.update(title="P3.1 — The sound behind the door (synthetic)", character_skin="cartoon_horror",
                 art_direction="2D cel cartoon horror; tousled hair, rust hoodie, navy trousers, expressive eyes. "
                               "Cold moonlight, warm door seam, cautious body acting and restrained dolly. Synthetic only.")
    room = video["locations"]["preview-room"]
    room.update(svg=ROOM, atmosphere="tense_apartment")
    shot = video["shots"][0]
    shot["camera"] = [[0, 480, 360, 1.0], [10, 493, 375, 1.07]]
    # Stay on the same side of the shared window's day/night threshold (.15).
    # A small continuous exposure change should not hard-switch the window color.
    shot["light"] = [[0, .17, 0], [1.45, .20, 0], [3.0, .17, 0], [10, .18, 0]]
    actor = shot["actors"][0]
    actor["look"] = {"shirt": "#95655c", "skin": "#d6b199", "hair": "#242d38"}
    # Anticipation and a held recoil, then a small forward lean after the last footfall.
    actor["posture"] = [[0, 5, -99, 10, -160], [1.2, 5, -99, 10, -160],
                        [1.6, -1, -104, 0, -165], [2.3, 0, -102, 2, -163],
                        [3.2, 5, -99, 13, -160], [8.4, 5, -99, 13, -160],
                        [9.35, 10, -101, 18, -161], [10, 10, -101, 18, -161]]
    actor["face"] = [[0, .15, 1, 0, -.1, .1, 0], [1.2, .15, 1, 0, -.1, .1, 0],
                     [1.6, 1.5, -5, -1, -.95, 0, -11], [2.3, 1.1, -5, -1, -.7, 0, -8],
                     [3.2, .9, 5, 0, -.4, 0, 6], [8.4, .9, 5, 0, -.4, 0, 3],
                     [9.35, 1, 5, -1, -.45, 0, -2], [10, 1, 5, -1, -.45, 0, -2]]
    # Door's closed handle is (x+16,y+120). Contact finishes without a wrist snap.
    actor["right_hand"] = [k for k in actor["right_hand"] if k[0] <= 8.4] + [
        [8.65, 550, 498], [9.1, 575, 439], [9.35, 581, 420], [10, 581, 420]]
    timeline["scenes"][0]["actions"][-1]["notes"] = "Feet settle; lean and reach, then hold the closed door handle. No opening."
    return video, timeline


def build_cinematic_preview(audio: dict[str, Path]) -> tuple[dict, dict]:
    """Opt-in v2 over P3.1: original fixture and its outputs stay available unchanged."""
    video, timeline = build_preview(audio)
    video["title"] = "P3.1 v2 — A pause behind the glass (synthetic)"
    video["art_direction"] = ("Cinematic 2D Cartoon Supernatural Horror. Adult angular face, muted clothing, "
        "directional negative fill, confined interior, partially obscured exterior presence. "
        "Scratch, listening silence, guarded steps, freeze, cautious reach. No gore, stinger or jump cut.")
    # Keep the same apartment and props; add worn surfaces and a colder, restrained palette.
    room = video["locations"]["preview-room"]
    grime = ''.join(f'<path d="M {303+i*9} {210+(i*47)%390} l {3+(i%6)} {8+i%17}" '
                    'stroke="#8e9990" stroke-width=".7" opacity=".075"/>' for i in range(40))
    room["svg"] = ROOM.replace('#344751', '#28383e').replace('#3d4647', '#333c3b').replace('</svg>', grime+'</svg>')
    shot = video["shots"][0]
    # Begin close on the listener; the sound's door stays partly offscreen until approached.
    shot["camera"] = [[0, 418, 445, 1.32], [1.2, 418, 445, 1.32], [2.4, 420, 445, 1.32],
                      [3.8, 426, 445, 1.32], [6.2, 454, 445, 1.33], [6.85, 454, 445, 1.33],
                      [8.4, 526, 445, 1.34], [10, 538, 445, 1.34]]
    shot["light"] = [[0, .17, 0], [1.2, .17, 0], [1.4, .22, 0], [2.4, .22, 0],
                     [3.8, .17, 0], [6.1, .17, 0], [6.35, .21, 0], [6.85, .21, 0],
                     [7.25, .17, 0], [10, .18, 0]]
    video["horror"] = {
        "presence": [[0, 0, -17], [5.9, 0, -17], [6.33, .78, 1], [6.85, .78, 1],
                     [7.25, 0, 1], [10, 0, 1]],
        "spill": [[0, .85], [1.2, .85], [1.4, .12], [2.4, .12], [3.8, .65],
                  [6.1, .65], [6.35, .1], [6.85, .1], [7.25, .55], [10, .55]]}
    actor = shot["actors"][0]
    actor["look"] = {"shirt": "#756359", "skin": "#c3ab91", "hair": "#20272a", "treatment": "cinematic"}
    # Draw the startled far hand toward the chest instead of throwing an elbow out.
    for key in actor["left_hand"]:
        if key[0] == 1.6: key[1:] = [384, 445]
        if key[0] == 2.5: key[1:] = [395, 452]
        if key[0] == 3.2: key[1:] = [376, 496]
    actor["left_hand"].append([1.4, 376, 480])
    actor["left_hand"].sort(key=lambda key: key[0])
    first = walk_clip(365, 440, 4, 6.2, 1, fps=30, period=.72, swing=.24, lift=12)
    second = walk_clip(440, 520, 6.9, 8.4, 1, fps=30, period=.6, swing=.26, lift=12)
    for name in first["tracks"]:
        opening = [k for k in actor[name] if k[0] < 4]
        for clip in (first, second):
            if name.endswith('hand'):
                for key in clip["tracks"][name]:
                    key[2] -= 38 if name == 'right_hand' else 14
        keys = first["tracks"][name]
        hold = [[6.9, *keys[-1][1:]]]
        if name.endswith('hand'):
            px, py = keys[-1][1:]
            hold = [[6.35, px+.7, py-.6], [6.47, px-.7, py+.5], [6.6, px+.4, py-.3],
                    [6.75, px, py], [6.9, px, py]]
        actor[name] = opening + keys + hold + second["tracks"][name][1:] + [[10, *second["tracks"][name][-1][1:]]]
    actor["right_hand"] = [k for k in actor["right_hand"] if k[0] <= 8.4] + [
        [8.65, 551, 463], [8.78, 550, 461.5], [8.9, 555, 456], [9.03, 555, 457],
        [9.18, 573, 436], [9.35, 581, 420], [10, 581, 420]]
    actor["posture"] = [[0, 5, -99, 10, -160], [1.2, 5, -99, 10, -160],
        [1.4, -3, -105, -2, -166], [1.6, -3, -105, -2, -166], [2.4, -3, -105, -2, -166],
        [3.2, 4, -101, 12, -162], [6.1, 4, -101, 12, -162], [6.33, 0, -106, 4, -164],
        [6.85, 0, -106, 4, -164], [7.2, 4, -101, 12, -162], [8.4, 4, -101, 12, -162],
        [9.35, 10, -101, 18, -161], [10, 10, -101, 18, -161]]
    actor["face"] = [[0, .3, 2, 0, -.35, .15, 2], [1.2, .3, 2, 0, -.35, .15, 2],
        [1.4, 1.4, -5, -1, -.8, 0, -12], [1.6, 1.4, -5, -1, -.8, 0, -12],
        [2.4, 1.1, -5, -1, -.65, 0, -10], [3.2, .9, 5, 0, -.4, .1, 6],
        [6.1, .9, 5, 0, -.4, .1, 6], [6.33, 1.1, -6, -1, -.7, 0, -10],
        [6.85, 1.1, -6, -1, -.7, 0, -10], [7.2, .9, 5, 0, -.4, .1, 4],
        [8.4, .9, 5, 0, -.4, .1, 3], [9.35, 1, 5, -1, -.5, 0, -2], [10, 1, 5, -1, -.5, 0, -2]]
    landings = sorted(first["landings"]+second["landings"])
    video["sfx"] = [
        {"id": "room", "path": str(audio["room_tone"]), "start_seconds": 0, "duration_seconds": 1.2, "volume": .22, "role": "ambience"},
        {"id": "room-return", "path": str(audio["room_tone"]), "start_seconds": 3.8, "duration_seconds": 2.3, "volume": .12, "role": "ambience"},
        {"id": "room-late", "path": str(audio["room_tone"]), "start_seconds": 6.9, "duration_seconds": 2.2, "volume": .1, "role": "ambience"},
        {"id": "scrape", "path": str(audio["furniture_scrape"]), "start_seconds": 1.2, "duration_seconds": .9, "volume": .65},
        {"id": "creak", "path": str(audio["door_open"]), "start_seconds": 6.1, "duration_seconds": .55, "volume": .2}]
    video["sfx"] += [{"id": f"foot-{i}", "path": str(audio["footstep"]), "start_seconds": round(t*30)/30,
                      "duration_seconds": .17, "volume": .26} for i,t in enumerate(landings)]
    video["audio_qa"] = {"quiet_windows": [[2.3, 3.5], [6.7, 6.85], [9.4, 9.9]]}
    actions = timeline["scenes"][0]["actions"]
    actions[1]["notes"] = "Shoulders tense quickly; listen and hold in silence before moving."
    actions[2]["notes"] = "Guarded walk; freeze 6.2–6.9s with gaze at the window; then approach the door."
    actions[3]["notes"] = "Hesitant hand tremor, then settled closed-door contact; no knob rotation or opening."
    timeline["metadata"]["foot_landings"] = landings
    return video, timeline
