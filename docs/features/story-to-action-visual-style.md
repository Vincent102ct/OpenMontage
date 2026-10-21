---
name: "Minh — After the dishes"
version: "1.0"
style_prompt_short: "Original simplified 2D cartoon horror in a detailed, dim apartment. Readable acting and grounded prop contact."
style_prompt_full: "Original adult Vietnamese cartoon character, large pale oval face, side-swept dark hair, simple tired eyes, dusty blue long-sleeve shirt and slate trousers. Filled rounded forms with dark outlines, articulated hands and shoes. A detailed lived-in apartment with cool blue-gray plaster patches: tiled kitchen, sink and curved faucet, dish rack, cupboards, window, clear aisle and bedroom opening with a bed. Cold night fill and a small warm kitchen lamp. Restrained shadows and low saturation; keep the white cup and hands readable. Animate reach, grasp, washing, inversion, release and walking continuously. No stick limbs, slides, unrelated motion or borrowed artwork."
colors:
  primary:
    - {name: "Night", hex: "#172630", role: "Deep shadows and bedroom"}
    - {name: "Wall", hex: "#758199", role: "Muted apartment plaster"}
    - {name: "Dusty blue", hex: "#52778c", role: "Minh shirt"}
  accent:
    - {name: "Lamp", hex: "#e4b574", role: "Warm practical light"}
    - {name: "Skin", hex: "#deded2", role: "Face and hands"}
    - {name: "Ceramic", hex: "#f2efe5", role: "Single white cup"}
---

Status: **visual style approved by the user on 2026-10-21** after reviewing
`projects/minh-cup-cartoon-pilot/renders/final.mp4`. This style, Minh v1 and
Apartment v1 are locked for follow-up episodes; extend them, do not redesign.
The approval covers the look only. Gait, narration pacing and pronunciation were
not stated as approved and remain open review items.

Reference: `docs/references/openmontage_style_reference.png`, inspected 2026-10-21.
The screenshot has a compact cartoon with a large light round face, dark simple
eyes/brows, dark hair, blue shirt, gray trousers, and a much more detailed room.
Cool blue-gray midtones, irregular plaster patches and broad shaded areas carry
the horror atmosphere. The reference shows a traditional room; our original
modern apartment keeps that contrast of simple actor / detailed environment.
The original actor uses an oval head, asymmetric hair, pajamas and separate
hands/shoes; no character outline, room layout, logo, player UI or artwork is
traced or copied. A still does not establish motion quality or animation timing.

Minh v1: one adult, large pale oval face, short dark side-swept hair, simple eyes,
dusty blue long-sleeve shirt, dark trousers, brown shoes. Maintain silhouette, skin,
hair and costume throughout; no on-scene redesign. One side/three-quarter rig.
Reusable strategies: reach/grasp with two-bone IK, support/scrub, carry, invert,
place/release, planted-foot walk, gaze and blink. They use data, not a Minh-only
renderer branch.

Apartment v1: 1280×720, fixed wide camera. Kitchen left/center, dish rack right of
sink, unobstructed foreground aisle, bedroom opening right. Draw cupboards,
tile grout, shelf contents, sink basin, plumbing, worn wall lines, wall switch,
night window, door jamb, bed and lamp as layered SVG. Foreground jamb occludes
the actor only when entering the bedroom. Never relocate furniture between beats.

Lighting: cool desaturated night fill, warm pool over sink, darker bedroom;
stable cast/ambient shadows. No flicker that hides the contact points. White
ceramic keeps its silhouette and 180-degree orientation after release.

Line: dark 2–3 px outlines, filled 13–22 px limbs and rounded joints; no one-pixel
stick limbs. Face detail and pajama seam/cuffs remain readable at 720p. Modest
SVG gradients for room depth; no heavy raster filters, 3D or AI video models.
Captions: one bottom rail in Arial, white with dark backing, measured clause
timings. No decorative duplicated narration text.

Motion: restrained, slow-in/out on reach and placement, linear planted foot
holds with curved swing; anticipation, real grip, physical carry and settle.
Use pauses between narration clauses to complete actions. One uninterrupted shot
makes object permanence auditable. Horror is atmosphere here; no new scare or
story event is added to the supplied sentence.

Reference-derived palette revision: plaster `#758199`, shadow `#3d4a63`, shirt
`#52778c`, face `#deded2`, hair `#303c42`. These supersede the warmer initial draft.
Add original irregular plaster patches and broad window shadows; retain warm
sink lighting only as a small accent for cup readability.

Target: MacBook Air M4/16 GB; 1280×720, 30 fps, two render workers. Measure actual
host and render process resources before claiming target-device performance.
