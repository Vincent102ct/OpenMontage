"""Procedural original backdrops (1280x720 SVG) with named interaction anchors.

Same palette and line weight as the approved Apartment v1 art, but generic: one
template per location kind, no story-specific objects. Movable things (doors,
props, vehicles, window sky, rain) are drawn by the Remotion composition, so the
SVG only contains static scenery. Anchors are world coordinates the planner uses:
items rest at `surface` points, hands target `reach` points, actors sit at `seat`.
Ground (feet) is y=620; a standing actor's shoulder is ~y=415 and reaches ~133 px.
Every seat's sitting surface is at y=556 (`SEAT_TOP`); `width` tells whether there is
room to set a bag down beside the sitter.
"""
from __future__ import annotations

from tools.story.lexicon import OUTDOOR_KINDS

W, H = 1280, 720
INK = "#1d303b"
SEAT_TOP = 556
SEAT_WIDTH = {"chair": 68, "stool": 60, "bench": 140, "sofa": 264}

DEFS = """<defs>
 <linearGradient id="wall" x2="0" y2="1"><stop stop-color="#606d86"/><stop offset="1" stop-color="#87909f"/></linearGradient>
 <linearGradient id="wallwarm" x2="0" y2="1"><stop stop-color="#7a7286"/><stop offset="1" stop-color="#9a919a"/></linearGradient>
 <linearGradient id="floor" x2="0" y2="1"><stop stop-color="#495555"/><stop offset="1" stop-color="#293940"/></linearGradient>
 <linearGradient id="wood" x2="0" y2="1"><stop stop-color="#7f6957"/><stop offset="1" stop-color="#5f4d40"/></linearGradient>
 <linearGradient id="sky" x2="0" y2="1"><stop stop-color="#7d93a6"/><stop offset="1" stop-color="#b3bec3"/></linearGradient>
 <linearGradient id="asphalt" x2="0" y2="1"><stop stop-color="#3a4247"/><stop offset="1" stop-color="#2b3236"/></linearGradient>
 <pattern id="tile" width="42" height="40" patternUnits="userSpaceOnUse"><rect width="42" height="40" fill="#70817e"/><path d="M 0 0 H 42 V 40" fill="none" stroke="#526a6c" stroke-width="2"/></pattern>
</defs>"""


def _room_shell(wall: str = "url(#wall)") -> str:
    return f"""<rect width="{W}" height="{H}" fill="{wall}"/>
<path d="M 0 96 L 90 104 130 88 210 108 300 94 380 112 470 96 560 116 650 92 740 110 830 95 930 113 1030 90 1120 108 1280 92 V 0 H 0 Z" fill="#3d4a63" opacity=".6"/>
<path d="M 0 430 l 36 -14 22 16 28 -30 20 12 8 70 30 12 -10 40 28 30 H 0 Z" fill="#566681" opacity=".45"/>
<path d="M 0 0 L 160 70 H 1280 V 0" fill="#263d48"/>
<path d="M 0 570 H {W} V {H} H 0" fill="url(#floor)"/>
<g fill="none" stroke="#71807a" stroke-opacity=".18"><path d="M 0 614 H 1280 M 0 673 H 1280 M 250 570 L 40 720 M 560 570 L 510 720 M 840 570 L 960 720 M 1080 570 L 1280 690"/></g>
<path d="M 0 562 H {W}" stroke="#22373e" stroke-width="12"/>"""


def _window(x, y, w, h) -> str:
    # Frame only; the composition paints sky/rain into the inner glass rect.
    return (f'<rect x="{x - 12}" y="{y - 12}" width="{w + 24}" height="{h + 24}" rx="2" fill="#24363f" stroke="{INK}" stroke-width="8"/>'
            f'<path d="M {x - 30} {y - 22} Q {x - 8} {y + h * .45} {x - 22} {y + h + 14} L {x + 14} {y + h + 8} Q {x + 26} {y + h * .45} {x + 8} {y - 22} Z" fill="#394d58" stroke="#243a45" stroke-width="3"/>'
            f'<path d="M {x + w + 30} {y - 22} Q {x + w + 8} {y + h * .45} {x + w + 22} {y + h + 14} L {x + w - 14} {y + h + 8} Q {x + w - 26} {y + h * .45} {x + w - 8} {y - 22} Z" fill="#394d58" stroke="#243a45" stroke-width="3"/>')


def _door_frame(x, y, w, h) -> str:
    return (f'<rect x="{x - 10}" y="{y - 10}" width="{w + 20}" height="{h + 10}" fill="#3a4a52" stroke="{INK}" stroke-width="4"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#0d171d"/>'
            f'<rect x="{x - 34}" y="{y + 92}" width="12" height="20" rx="2" fill="#c9cfc6" stroke="{INK}" stroke-width="2"/>')


def _table(x0, x1, top, legs_to=566, fill="url(#wood)") -> str:
    return (f'<g stroke="{INK}" stroke-width="3" stroke-linejoin="round">'
            f'<rect x="{x0}" y="{top}" width="{x1 - x0}" height="14" fill="{fill}"/>'
            f'<path d="M {x0 + 14} {top + 14} V {legs_to} M {x1 - 14} {top + 14} V {legs_to}" stroke="#3a3230" stroke-width="9"/></g>')


def _seat_front(x, kind="chair", fill="#6d5a4c") -> str:
    """Seat in the front plane: sitting surface y=556, legs to the actor ground."""
    if kind == "sofa":
        return (f'<g stroke="{INK}" stroke-width="3" stroke-linejoin="round">'
                f'<path d="M {x - 120} 486 Q {x} 470 {x + 120} 486 V 566 H {x - 120} Z" fill="#4c6670"/>'
                f'<rect x="{x - 132}" y="556" width="264" height="44" rx="10" fill="#587680"/>'
                f'<rect x="{x - 146}" y="520" width="30" height="84" rx="10" fill="#4c6670"/>'
                f'<rect x="{x + 116}" y="520" width="30" height="84" rx="10" fill="#4c6670"/>'
                f'<path d="M {x - 120} 604 v 14 M {x + 120} 604 v 14" stroke-width="7"/></g>')
    if kind == "bench":
        return (f'<g stroke="{INK}" stroke-width="3"><rect x="{x - 70}" y="556" width="140" height="12" fill="{fill}"/>'
                f'<rect x="{x - 70}" y="520" width="140" height="10" fill="{fill}"/>'
                f'<path d="M {x - 60} 568 V 620 M {x + 60} 568 V 620 M {x - 60} 530 V 556 M {x + 60} 530 V 556" stroke="#3a3230" stroke-width="7"/></g>')
    if kind == "stool":
        return (f'<g stroke="{INK}" stroke-width="3"><ellipse cx="{x}" cy="560" rx="30" ry="7" fill="{fill}"/>'
                f'<path d="M {x - 20} 564 L {x - 26} 620 M {x + 20} 564 L {x + 26} 620" stroke="#3a3230" stroke-width="7"/></g>')
    return (f'<g stroke="{INK}" stroke-width="3" stroke-linejoin="round">'
            f'<path d="M {x - 34} 556 H {x + 34} V 568 H {x - 34} Z" fill="{fill}"/>'
            f'<path d="M {x - 30} 568 V 620 M {x + 30} 568 V 620" stroke="#3a3230" stroke-width="7"/>'
            f'<path d="M {x - 34} 556 V 470 Q {x - 30} 462 {x - 22} 466 V 556" fill="{fill}"/></g>')


def _shelf(x0, x1, ys, goods="jars") -> str:
    out = [f'<g stroke="{INK}" stroke-width="3">']
    for y in ys:
        out.append(f'<rect x="{x0}" y="{y}" width="{x1 - x0}" height="10" fill="#6d5a4c"/>')
        step = 34
        for i, gx in enumerate(range(x0 + 10, x1 - 24, step)):
            if goods == "bread":
                out.append(f'<ellipse cx="{gx + 12}" cy="{y - 9}" rx="15" ry="9" fill="#c9965a"/>'
                           f'<path d="M {gx + 4} {y - 13} l 5 6 M {gx + 12} {y - 15} l 5 6" stroke="#8a5e34" stroke-width="2"/>')
            elif goods == "books":
                hh = 30 + (i * 7) % 14
                out.append(f'<rect x="{gx}" y="{y - hh}" width="{14 + i % 2 * 6}" height="{hh}" fill="{["#7b5b4e", "#4d6a73", "#8a8064", "#5c5a7a"][i % 4]}"/>')
            else:
                out.append(f'<rect x="{gx}" y="{y - 26}" width="20" height="26" rx="4" fill="{["#a6a28a", "#7f9294", "#b59a73"][i % 3]}"/>')
    out.append("</g>")
    return "".join(out)


def _lamp(x, top=310) -> str:
    return (f'<path d="M {x} {top + 30} V 566" stroke="#2a3a40" stroke-width="5"/>'
            f'<path d="M {x - 22} {top + 32} L {x - 14} {top} H {x + 14} L {x + 22} {top + 32} Z" fill="#c9a86a" stroke="{INK}" stroke-width="3"/>')


def _plant(x) -> str:
    return (f'<path d="M {x} 520 q -18 -50 -30 -70 M {x} 520 q 4 -60 -2 -84 M {x} 520 q 20 -46 34 -60" stroke="#5f8a6a" stroke-width="5" fill="none"/>'
            f'<path d="M {x - 22} 518 H {x + 22} L {x + 16} 566 H {x - 16} Z" fill="#7a5a43" stroke="{INK}" stroke-width="3"/>')


def _street(variant) -> str:
    out = [f'<rect width="{W}" height="430" fill="url(#sky)"/>']
    for i, (x, w, h) in enumerate([(0, 170, 300), (160, 140, 230), (290, 200, 330), (480, 150, 260), (620, 210, 310),
                                   (820, 160, 240), (970, 190, 340), (1150, 140, 280)]):
        top = 430 - h
        out.append(f'<rect x="{x}" y="{top}" width="{w}" height="{h}" fill="{["#3f4e5f", "#4a586a", "#394859"][i % 3]}" stroke="#2c3946" stroke-width="3"/>')
        for wy in range(top + 24, 410, 46):
            for wx in range(x + 18, x + w - 26, 40):
                out.append(f'<rect x="{wx}" y="{wy}" width="16" height="22" fill="#2a3644"/>')
    out.append(f'<rect y="430" width="{W}" height="132" fill="url(#asphalt)"/>'
               f'<path d="M 0 496 H 1280" stroke="#c9c39a" stroke-width="5" stroke-dasharray="46 38" opacity=".55"/>'
               f'<rect y="560" width="{W}" height="16" fill="#8d9592" stroke="{INK}" stroke-width="3"/>'
               f'<rect y="576" width="{W}" height="144" fill="#6c7473"/>'
               f'<g stroke="#56605f" stroke-width="2" opacity=".6"><path d="M 0 640 H 1280 M 120 576 L 90 720 M 420 576 L 410 720 M 720 576 L 730 720 M 1020 576 L 1050 720"/></g>')
    for x in (150, 640):
        out.append(f'<path d="M {x} 600 V 250 q 0 -22 26 -22 h 30" stroke="#2a3640" stroke-width="7" fill="none"/>'
                   f'<rect x="{x + 50}" y="222" width="30" height="12" rx="3" fill="#e8dcae" stroke="{INK}" stroke-width="2"/>')
    if variant == "bus_stop":
        out.append(f'<g stroke="{INK}" stroke-width="3"><rect x="830" y="300" width="240" height="16" fill="#3d5560"/>'
                   f'<path d="M 842 316 V 600 M 1058 316 V 600" stroke="#2a3640" stroke-width="8"/>'
                   f'<rect x="850" y="320" width="200" height="150" fill="#9fb4b8" opacity=".35"/>'
                   f'<path d="M 1110 600 V 330" stroke="#2a3640" stroke-width="6"/>'
                   f'<rect x="1090" y="300" width="42" height="42" rx="21" fill="#3f7fa3"/>'
                   f'<path d="M 1100 321 h 22 M 1105 312 h 12 v 18 h -12 z" stroke="#e9eee8" stroke-width="3" fill="none"/></g>')
        out.append(_seat_front(950, "bench", "#5a6f78"))
    return "".join(out)


def _park() -> str:
    out = [f'<rect width="{W}" height="470" fill="url(#sky)"/>',
           f'<path d="M 0 470 Q 320 430 640 460 T 1280 450 V 720 H 0 Z" fill="#4f6b55"/>',
           f'<path d="M 0 600 Q 640 560 1280 610 V 720 H 0 Z" fill="#8d8a76"/>']
    for x, s in ((90, 1.1), (330, .9), (1000, 1.2), (1200, .95)):
        out.append(f'<path d="M {x} 560 V {560 - 180 * s}" stroke="#4a3a30" stroke-width="{16 * s}"/>'
                   f'<circle cx="{x}" cy="{560 - 220 * s}" r="{80 * s}" fill="#3f5e48" stroke="#2c4234" stroke-width="3"/>'
                   f'<circle cx="{x - 40 * s}" cy="{560 - 180 * s}" r="{50 * s}" fill="#466a50"/>')
    out.append(_seat_front(640, "bench", "#6d5a4c"))
    out.append(_lamp(820, 300).replace("#c9a86a", "#e8dcae"))
    return "".join(out)


def build_location(kind: str, variant: str | None = None) -> dict:
    """Return {svg, outdoor, door, window, seat, anchors, spots, entry, light} for a kind."""
    door = window = seat = None
    anchors: dict[str, dict] = {}
    parts = [DEFS]
    if kind == "office":
        parts += [_room_shell(), _window(90, 150, 240, 230), _table(450, 800, 470),
                  f'<g stroke="{INK}" stroke-width="3"><rect x="560" y="370" width="130" height="86" rx="4" fill="#2f3d47"/>'
                  f'<rect x="568" y="378" width="114" height="68" fill="#567b86"/><path d="M 618 456 v 14 h 14 v -14" fill="#2f3d47"/>'
                  f'<rect x="590" y="462" width="80" height="8" fill="#c9cfc6"/></g>',
                  _shelf(880, 1040, [300, 380, 460, 540], "books"),
                  f'<path d="M 880 240 V 566 M 1040 240 V 566" stroke="#5a4636" stroke-width="10"/>',
                  _door_frame(1130, 330, 110, 236), _seat_front(400, "chair", "#3f5560"), _plant(1085)]
        door, window, seat = {"x": 1130, "y": 330, "w": 110, "h": 236, "hinge": "right"}, {"x": 90, "y": 150, "w": 240, "h": 230}, {"x": 400, "facing": 1, "kind": "chair"}
        anchors = {"table": {"x": 740, "y": 470}, "computer": {"x": 630, "y": 462}, "shelf": {"x": 960, "y": 380},
                   "corner": {"x": 1072, "y": 600}, "counter": {"x": 740, "y": 470}}
        spots = [260, 640, 880]
    elif kind == "street":
        parts += [_street(variant)]
        seat = {"x": 950, "facing": -1, "kind": "bench"} if variant == "bus_stop" else None
        anchors = {"corner": {"x": 1240, "y": 600}}
        spots = [330, 620, 860]
    elif kind == "living_room":
        parts += [_room_shell("url(#wallwarm)"), _window(780, 160, 200, 210), _lamp(230), _table(300, 420, 500),
                  _shelf(1030, 1160, [380]), _door_frame(60, 330, 110, 236), _seat_front(640, "sofa")]
        door, window, seat = {"x": 60, "y": 330, "w": 110, "h": 236, "hinge": "left"}, {"x": 780, "y": 160, "w": 200, "h": 210}, {"x": 640, "facing": -1, "kind": "sofa"}
        anchors = {"table": {"x": 360, "y": 500}, "shelf": {"x": 1090, "y": 380}, "corner": {"x": 1205, "y": 600},
                   "light": {"x": 230, "y": 330}}
        spots = [330, 640, 960]
    elif kind == "kitchen":
        parts += [_room_shell(), f'<rect x="280" y="310" width="480" height="170" fill="url(#tile)"/>',
                  f'<g stroke="{INK}" stroke-width="3"><rect x="280" y="150" width="480" height="150" fill="#536565"/>'
                  f'<path d="M 400 150 V 300 M 520 150 V 300 M 640 150 V 300"/>'
                  f'<rect x="270" y="480" width="500" height="18" fill="#9aa8a6"/><rect x="280" y="498" width="480" height="68" fill="#536565"/>'
                  f'<ellipse cx="420" cy="486" rx="56" ry="9" fill="#b9c4c2"/><path d="M 420 430 v -18 h 24" fill="none" stroke-width="5"/>'
                  f'<rect x="800" y="380" width="150" height="186" fill="#4a5a5e"/><rect x="814" y="420" width="122" height="100" rx="6" fill="#1f2a2f"/>'
                  f'<rect x="830" y="436" width="90" height="56" fill="#3b2a22" opacity=".8"/><path d="M 820 404 h 110" stroke="#c9cfc6" stroke-width="5"/>'
                  f'<circle cx="830" cy="392" r="6" fill="#2a3640"/><circle cx="920" cy="392" r="6" fill="#2a3640"/></g>',
                  _table(1000, 1210, 500), _shelf(300, 560, [298]), _door_frame(80, 330, 110, 236), _seat_front(1090, "stool")]
        door, window, seat = {"x": 80, "y": 330, "w": 110, "h": 236, "hinge": "left"}, None, {"x": 1090, "facing": -1, "kind": "stool"}
        anchors = {"counter": {"x": 640, "y": 480}, "oven": {"x": 875, "y": 470}, "table": {"x": 1150, "y": 500},
                   "shelf": {"x": 430, "y": 298}, "corner": {"x": 1240, "y": 600}, "light": {"x": 640, "y": 80}}
        spots = [330, 640, 960]
    elif kind == "shop":
        goods = "bread" if variant == "bakery" else "jars"
        parts += [_room_shell("url(#wallwarm)"), _window(70, 170, 320, 290),
                  _shelf(700, 1180, [280, 360, 400], goods),
                  f'<g stroke="{INK}" stroke-width="3"><rect x="690" y="480" width="380" height="18" fill="#9a7d62"/>'
                  f'<rect x="700" y="498" width="360" height="68" fill="#6d5a4c"/><rect x="720" y="510" width="320" height="44" fill="#7f6957"/></g>',
                  _door_frame(450, 330, 110, 236)]
        door, window, seat = {"x": 450, "y": 330, "w": 110, "h": 236, "hinge": "left"}, {"x": 70, "y": 170, "w": 320, "h": 290}, None
        anchors = {"counter": {"x": 800, "y": 480}, "table": {"x": 800, "y": 480}, "shelf": {"x": 940, "y": 400},
                   "corner": {"x": 640, "y": 600}, "light": {"x": 640, "y": 80}}
        spots = [300, 660, 900]
    elif kind == "bedroom":
        parts += [_room_shell("url(#wallwarm)"), _window(740, 150, 200, 200), _door_frame(60, 330, 110, 236),
                  f'<g stroke="{INK}" stroke-width="3"><rect x="980" y="230" width="150" height="336" fill="#5f4d40"/>'
                  f'<path d="M 1055 240 V 556"/><rect x="560" y="440" width="22" height="160" fill="#5f4d40"/>'
                  f'<rect x="560" y="540" width="380" height="40" rx="6" fill="#6f8c96"/><rect x="590" y="520" width="90" height="26" rx="10" fill="#e4e0d2"/>'
                  f'<path d="M 580 540 Q 760 520 940 544" fill="none"/></g>', _table(440, 530, 500)]
        door, window, seat = {"x": 60, "y": 330, "w": 110, "h": 236, "hinge": "left"}, {"x": 740, "y": 150, "w": 200, "h": 200}, {"x": 700, "facing": -1, "kind": "bed"}
        anchors = {"table": {"x": 485, "y": 500}, "bed": {"x": 760, "y": 540}, "corner": {"x": 1220, "y": 600},
                   "light": {"x": 485, "y": 420}}
        spots = [330, 700, 900]
    elif kind == "park":
        parts += [_park()]
        seat = {"x": 640, "facing": 1, "kind": "bench"}
        anchors = {"corner": {"x": 1240, "y": 600}}
        spots = [300, 640, 960]
    else:
        parts += [_room_shell(), _window(160, 160, 220, 220), _table(560, 760, 490), _door_frame(1100, 330, 110, 236),
                  _seat_front(500, "chair")]
        door, window, seat = {"x": 1100, "y": 330, "w": 110, "h": 236, "hinge": "right"}, {"x": 160, "y": 160, "w": 220, "h": 220}, {"x": 500, "facing": 1, "kind": "chair"}
        anchors = {"table": {"x": 680, "y": 490}, "corner": {"x": 1240, "y": 600}}
        spots = [300, 640, 900]
    outdoor = kind in OUTDOOR_KINDS
    if door:
        anchors["door"] = {"x": door["x"] + (door["w"] - 18 if door["hinge"] == "left" else 18), "y": 450}
        anchors.setdefault("light", {"x": door["x"] - 28 if door["hinge"] == "left" or door["x"] > 640 else door["x"] + door["w"] + 28, "y": 432})
        anchors["switch"] = {"x": door["x"] - 28, "y": 432}
    if window:
        anchors["window"] = {"x": window["x"] + window["w"] / 2, "y": window["y"] + window["h"] / 2}
    if seat:
        seat["top"] = SEAT_TOP
        seat["width"] = SEAT_WIDTH.get(seat["kind"], 340)  # a bed edge is wide
        anchors["seat"] = {"x": seat["x"], "y": SEAT_TOP}
    entry = ({"x": door["x"] + door["w"] / 2, "door": True} if door else {"x": -70, "door": False})
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
           + "".join(parts) + "</svg>")
    return {"kind": kind, "variant": variant, "svg": svg, "outdoor": outdoor, "door": door, "window": window,
            "seat": seat, "anchors": anchors, "spots": spots, "entry": entry}
