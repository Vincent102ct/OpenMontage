"""P3.2A reusable horror environment templates (procedural SVG, world coordinates).

Each template returns static scenery plus explicit interaction geometry. Movable
parts (door leaf, handle, window glass) are still drawn by StoryVideo.tsx from the
`door`/`window` rects, so every anchor below is derived from those same rects and
stays aligned under any camera move. Floor (feet) is y=620 like every rig scene.
"""
from __future__ import annotations

FLOOR_Y = 620
W, H = 1280, 720


def door_handle(door: dict, open_amount: float = 0.0) -> list[float]:
    """Python twin of StoryVideo.tsx doorHandle()."""
    w = door["w"] * (1 - 0.82 * open_amount)
    x = door["x"] if door.get("hinge") == "left" else door["x"] + door["w"] - w
    return [x + w - 16 if door.get("hinge") == "left" else x + 16, door["y"] + 120]


def window_panes(win: dict) -> list[list[list[float]]]:
    """Glass panes between the 7 px mullions StoryVideo.tsx draws through the centre."""
    x, y, w, h = win["x"], win["y"], win["w"], win["h"]
    cells = [(x + 2, y + 2, w / 2 - 7, h / 2 - 7), (x + w / 2 + 4, y + 2, w / 2 - 6, h / 2 - 7),
             (x + 2, y + h / 2 + 4, w / 2 - 7, h / 2 - 6), (x + w / 2 + 4, y + h / 2 + 4, w / 2 - 6, h / 2 - 6)]
    return [[[px, py], [px + pw, py], [px + pw, py + ph], [px, py + ph]] for px, py, pw, ph in cells]


def _door_frame(d: dict, plate: bool = False) -> str:
    x, y, w, h = d["x"], d["y"], d["w"], d["h"]
    out = (f'<rect x="{x - 12}" y="{y - 12}" width="{w + 24}" height="{h + 12}" fill="#1c2629" stroke="#3f4b4b" stroke-width="3"/>'
           f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#05090c"/>')
    if plate:
        out += f'<rect x="{x + w / 2 - 9}" y="{y - 34}" width="18" height="12" rx="2" fill="#5d5440" stroke="#2a2a22" stroke-width="1.5"/>'
    return out


def _closed_door(x: float, y: float, w: float, h: float) -> str:
    # Decorative (non-interactive) neighbour door; drawn entirely in the backdrop.
    return (_door_frame({"x": x, "y": y, "w": w, "h": h}, plate=True)
            + f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#1f2a2c" stroke="#121a1c" stroke-width="3"/>'
            f'<rect x="{x + 14}" y="{y + 18}" width="{w - 28}" height="96" rx="2" fill="#192326" stroke="#2c3a3a" stroke-width="1"/>'
            f'<rect x="{x + 14}" y="{y + 150}" width="{w - 28}" height="150" rx="2" fill="#1b2528" stroke="#2c3a3a" stroke-width="1"/>'
            f'<circle cx="{x + 16}" cy="{y + 120}" r="5" fill="#6e6a5c"/>')


def old_apartment_room() -> dict:
    door = {"x": 820, "y": 300, "w": 96, "h": 320, "hinge": "right"}
    window = {"x": 300, "y": 230, "w": 110, "h": 170}
    lamp = {"id": "floor_lamp", "x": 1040, "y": 318, "kind": "floor_lamp"}
    wx, wy, ww, wh = window["x"], window["y"], window["w"], window["h"]
    stripes = "".join(f'<path d="M {x} 122 V 468" stroke="#9bb0a8" stroke-opacity=".035" stroke-width="10"/>'
                      for x in range(40, 1280, 64))
    boards = "".join(f'<path d="M {x} 620 L {x + (x - 640) * .32:.1f} 720" stroke="#868a80" stroke-opacity=".12"/>'
                     for x in range(60, 1280, 118))
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
 <linearGradient id="room-wall" x2="0" y2="1"><stop stop-color="#0f1a22"/><stop offset=".6" stop-color="#2a3a3f"/><stop offset="1" stop-color="#1f2d33"/></linearGradient>
 <linearGradient id="room-floor" x2="0" y2="1"><stop stop-color="#3a3530"/><stop offset="1" stop-color="#14161a"/></linearGradient>
 <radialGradient id="room-stain"><stop stop-color="#55513c" stop-opacity=".28"/><stop offset="1" stop-color="#55513c" stop-opacity="0"/></radialGradient>
</defs>
<rect width="{W}" height="{FLOOR_Y}" fill="url(#room-wall)"/>
{stripes}
<path d="M 0 112 H 1280 M 0 122 H 1280" stroke="#6f7c78" stroke-opacity=".18" stroke-width="4"/>
<ellipse cx="660" cy="170" rx="120" ry="70" fill="url(#room-stain)"/>
<path d="M 600 128 q 8 40 -4 70 q 10 22 2 48 M 700 126 q -6 30 6 52" stroke="#3e3a2c" stroke-opacity=".35" fill="none" stroke-width="2"/>
<rect y="468" width="{W}" height="132" fill="#1a2428" opacity=".55"/>
<path d="M 0 468 H 1280" stroke="#56635f" stroke-opacity=".35" stroke-width="5"/>
<rect y="598" width="{W}" height="22" fill="#141c1f"/>
<rect y="{FLOOR_Y}" width="{W}" height="100" fill="url(#room-floor)"/>
{boards}
<path d="M 0 621 H 1280" stroke="#0b1013" stroke-width="5"/>
<rect x="{wx - 12}" y="{wy - 12}" width="{ww + 24}" height="{wh + 24}" fill="#18242a" stroke="#4c5a5a" stroke-width="5"/>
<rect x="{wx - 20}" y="{wy + wh + 10}" width="{ww + 40}" height="10" fill="#3b4645" stroke="#1a2224" stroke-width="2"/>
<path d="M {wx - 34} {wy - 26} Q {wx - 14} {wy + 80} {wx - 30} {wy + wh + 40} L {wx - 6} {wy + wh + 34} Q {wx + 2} {wy + 80} {wx - 4} {wy - 26} Z" fill="#2c2230" opacity=".9"/>
<path d="M {wx + ww + 34} {wy - 26} Q {wx + ww + 18} {wy + 60} {wx + ww + 30} {wy + wh - 20} L {wx + ww + 10} {wy + wh - 26} Q {wx + ww + 2} {wy + 60} {wx + ww + 6} {wy - 26} Z" fill="#2c2230" opacity=".9"/>
<path d="M {wx - 44} {wy - 30} H {wx + ww + 44}" stroke="#2a2a26" stroke-width="5"/>
<g transform="rotate(-6 540 250)"><rect x="512" y="214" width="56" height="74" fill="#141c22" stroke="#6a624f" stroke-width="4"/>
<rect x="518" y="220" width="44" height="62" fill="#2d363a"/><path d="M 526 276 Q 527 252 540 251 Q 554 252 554 276" fill="#1c252c"/></g>
<path d="M 120 470 Q 118 420 150 418 H 240 Q 266 420 264 470 V 560 H 120 Z" fill="#241e24" stroke="#120e12" stroke-width="3"/>
<rect x="108" y="540" width="170" height="44" rx="10" fill="#2c252b" stroke="#120e12" stroke-width="3"/>
<path d="M 124 584 V 616 M 262 584 V 616" stroke="#120e12" stroke-width="7"/>
<rect x="556" y="514" width="80" height="10" fill="#3b2f28" stroke="#140f0c" stroke-width="2"/>
<path d="M 566 524 V 616 M 626 524 V 616" stroke="#140f0c" stroke-width="6"/>
<path d="M 578 514 q 2 -14 14 -14 h 10 q 12 0 12 14 Z" fill="#1d1c1c" stroke="#0c0b0b" stroke-width="2"/>
{_door_frame(door)}
<rect x="784" y="420" width="12" height="20" rx="2" fill="#5a5d55" stroke="#1a1d1b" stroke-width="2"/>
<path d="M {lamp["x"]} 330 V 616 M {lamp["x"] - 22} 618 H {lamp["x"] + 22}" stroke="#1b1f20" stroke-width="5"/>
<path d="M {lamp["x"] - 26} 330 L {lamp["x"] - 16} 300 H {lamp["x"] + 16} L {lamp["x"] + 26} 330 Z" fill="#4f4434" stroke="#1b1712" stroke-width="3"/>
</svg>'''
    return {"svg": svg, "door": door, "window": window,
            "features": {"floor_y": FLOOR_Y, "walk_range": [150, 1180],
                         "windows": [{"id": "sash_window", "rect": window, "panes": window_panes(window)}],
                         "doors": [{"id": "room_door", "rect": door, "interactive": True,
                                    "handle": door_handle(door), "seam": [door["x"] + 3, door["x"] + door["w"] - 3, FLOOR_Y - 1]}],
                         "lamps": [lamp],
                         "presence_anchors": {"window": {"kind": "window", "clip": window_panes(window),
                                                         "x": wx + ww * .55, "y": wy + wh * .42, "scale": 1.0}},
                         "props": {"side_table_top": [596, 514], "light_switch": [790, 430],
                                   "armchair_seat": [192, 540], "picture_frame": [540, 250]}}}


def dark_apartment_corridor() -> dict:
    door = {"x": 640, "y": 300, "w": 96, "h": 320, "hinge": "right"}
    lamps = [{"id": "lamp_west", "x": 330, "y": 112, "kind": "ceiling"},
             {"id": "lamp_mid", "x": 790, "y": 112, "kind": "ceiling"},
             {"id": "lamp_east", "x": 1090, "y": 112, "kind": "ceiling"}]
    arch = [[1010, 240], [1170, 240], [1170, 620], [1010, 620]]
    fixtures = "".join(f'<rect x="{l["x"] - 26}" y="92" width="52" height="12" rx="3" fill="#2b302e" stroke="#111515" stroke-width="2"/>'
                       f'<path d="M {l["x"] - 18} 104 Q {l["x"]} 124 {l["x"] + 18} 104 Z" fill="#6f6a55" opacity=".8"/>' for l in lamps)
    runner = "".join(f'<path d="M {x} 652 l 14 10 -14 10 -14 -10 Z" fill="#3c2324" opacity=".55"/>' for x in range(40, 1280, 64))
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
 <linearGradient id="hall-wall" x2="0" y2="1"><stop stop-color="#0c1414"/><stop offset=".55" stop-color="#253330"/><stop offset="1" stop-color="#1a2523"/></linearGradient>
 <linearGradient id="hall-floor" x2="0" y2="1"><stop stop-color="#2f2b27"/><stop offset="1" stop-color="#0e1012"/></linearGradient>
 <linearGradient id="hall-depth" x1="0" x2="1"><stop stop-color="#0a0f10"/><stop offset="1" stop-color="#010203"/></linearGradient>
</defs>
<rect width="{W}" height="{FLOOR_Y}" fill="url(#hall-wall)"/>
<rect width="{W}" height="90" fill="#070b0c"/>
<path d="M 0 90 H 1280" stroke="#3a4642" stroke-width="4"/>
{fixtures}
<rect y="455" width="{W}" height="145" fill="#16201f" opacity=".7"/>
<path d="M 0 455 H 1280" stroke="#4a5550" stroke-opacity=".4" stroke-width="5"/>
<rect y="598" width="{W}" height="22" fill="#101615"/>
<rect y="{FLOOR_Y}" width="{W}" height="100" fill="url(#hall-floor)"/>
<rect y="640" width="{W}" height="44" fill="#2a1718" opacity=".75"/>
{runner}
<path d="M 0 621 H 1280" stroke="#080b0b" stroke-width="5"/>
{_closed_door(150, 300, 96, 320)}
<rect x="410" y="330" width="96" height="84" fill="#1e2824" stroke="#3b4540" stroke-width="3"/>
<path d="M 420 344 h 30 v 24 h -30 Z M 458 340 h 38 v 30 h -38 Z M 428 380 h 46 v 22 h -46 Z" fill="#5a5c50" opacity=".35"/>
<rect x="380" y="520" width="96" height="78" fill="#1d2523" stroke="#0f1413" stroke-width="2"/>
<path d="M 392 524 V 594 M 408 524 V 594 M 424 524 V 594 M 440 524 V 594 M 456 524 V 594" stroke="#2f3a37" stroke-width="5"/>
{_door_frame(door, plate=True)}
<rect x="604" y="420" width="12" height="20" rx="2" fill="#4e524b" stroke="#141716" stroke-width="2"/>
<path d="M {arch[0][0] - 14} {arch[0][1] - 14} H {arch[1][0] + 14} V 620 H {arch[0][0] - 14} Z" fill="#1a2422" stroke="#36423e" stroke-width="3"/>
<path d="M {arch[0][0]} {arch[0][1]} H {arch[1][0]} V 620 H {arch[0][0]} Z" fill="url(#hall-depth)"/>
<path d="M 1010 240 L 1060 300 V 560 L 1010 620 M 1170 240 L 1120 300 V 560 L 1170 620 M 1060 300 H 1120 M 1060 560 H 1120"
 stroke="#1d2826" stroke-width="2" fill="none"/>
<rect x="1078" y="330" width="24" height="40" fill="#1c2a30" opacity=".6"/>
</svg>'''
    return {"svg": svg, "door": door, "window": None,
            "features": {"floor_y": FLOOR_Y, "walk_range": [120, 980], "windows": [],
                         "doors": [{"id": "apartment_4c", "rect": door, "interactive": True,
                                    "handle": door_handle(door), "seam": [door["x"] + 3, door["x"] + door["w"] - 3, FLOOR_Y - 1]},
                                   {"id": "apartment_4b", "rect": {"x": 150, "y": 300, "w": 96, "h": 320, "hinge": "right"},
                                    "interactive": False, "handle": [166, 420], "seam": [153, 243, FLOOR_Y - 1]}],
                         "lamps": lamps,
                         "presence_anchors": {"corridor_end": {"kind": "opening", "clip": [arch],
                                                               "x": 1090, "y": FLOOR_Y, "scale": 3.1}},
                         "props": {"light_switch": [610, 430], "notice_board": [458, 372],
                                   "radiator_top": [428, 520], "corridor_end": [1090, 430]}}}
