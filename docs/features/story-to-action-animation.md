# Story-to-action animation

## Goal and scope

One local 2D simplified cartoon horror pilot, using the existing character-animation pipeline:
“Tối hôm đó tôi rửa chiếc cốc, úp lên giá rồi đi ngủ.”
Minh reaches for one white cup, washes it beneath running water, inverts and
releases it onto the rack, then walks into the bedroom. The cup stays inverted.
Visual update: filled face, hair, clothing and articulated limbs replace the
stickman appearance. See `story-to-action-visual-style.md`. The reference at
`docs/references/openmontage_style_reference.png` has been visually inspected.
This is an authored pilot, not arbitrary-text action inference or a complete
horror-story product. A fixed camera makes continuity inspectable.

## Reuse and extension

See `SOURCE_MAP.md` for the inspected source and baseline. Reuse character design,
rig/pose artifacts, registry discovery, pipeline manifests, subtitle generation,
audio mixer, checkpoint validation and the native Remotion compose handoff.
Extend `ActionTimelineCompiler` and `CharacterRigRenderer`; do not modify the
existing dirty cinematic dispatcher. Skeletal frame evaluation is deterministic.
Unknown story actions must fail rather than render the old generic bounce.

## Contracts

- Input: schema-valid scene plan plus explicit per-scene timed actions; each names
  a character, action, target, start and duration. Actions stay within scene bounds.
- Render input: action timeline plus a `story_motion` package containing stable
  actor/prop IDs, scene SVG, skeletal point tracks, prop ownership intervals,
  measured narration segments and captions. All times are seconds, coordinates
  are in one 1280×720 world. Scene artwork is authored data, not guessed scenery.
- Output: project-local Remotion entry, props, asset manifest, edit decisions with
  `render_runtime=remotion`, then MP4 via registry `video_compose`.
- Native macOS TTS: explicit installed voice and locale, WAV output, zero network;
  unavailable or mismatched voices return a failed ToolResult, never English fallback.

## Narration alignment

Generate the original text as three clauses: “Tối hôm đó tôi rửa chiếc cốc,”,
“úp lên giá”, “rồi đi ngủ.” Measure each real WAV with ffprobe. Schedule each clause
over its action window; add natural silence between clauses to finish contact and
placement. Caption intervals use these measured starts/ends. No fabricated word
alignment or claimed ASR/forced alignment. The reach anticipates “rửa”; washing
continues while that clause is spoken. Inversion/placement accompanies “úp lên
giá”; walking accompanies “rồi đi ngủ”. Full narration words and order stay intact.

## Identity, rig and timeline

One actor `minh`, one prop `white-cup`, one apartment. Shoulder/hip tracks define
the body; two-bone inverse kinematics resolves elbows and knees without changing
bone lengths. Hands follow authored targets. Walking feet alternate planted and
swing phases; no sliding root-only walk. One continuous cup trajectory controls
grip position and rotation. When held, the hand follows the same cup handle
transform; release is continuous at the rack. Ownership is explicit: counter →
Minh → rack. Rotation reaches 180 degrees before release and persists thereafter.
Water is visible only during washing. Furniture is drawn behind the work plane;
the actor walks along the clear foreground aisle and through the bedroom opening.

## Failure modes

Reject missing/duplicate entities, nonfinite or unordered keys, unreachable limb
targets, out-of-range timings, missing actions/targets, discontinuous attachment,
unsupported runtime and missing narration media. No silent generic animation or
static fallback. A schema-valid QA report is not proof of motion: report numerical
continuity checks separately from actual rendered-frame visual inspection.

## Acceptance and verification

1. Existing character contract smoke remains passing.
2. Explicit actions preserve names/order/timing; unknown/out-of-bounds actions fail.
3. Sample every output frame: finite coordinates, fixed bone lengths, continuous
   cup/grip, no cup movement after release, 180-degree persistent inversion,
   nonzero hand motion while washing, alternating foot contacts while walking.
4. Captions match the generated clause text and measured audio duration; each audio
   interval is inside its corresponding action window.
5. Native `video_compose` outputs playable H.264 MP4 with narration and captions;
   ffprobe and full decode pass. Extract reach/wash/place/walk/end frames and
   inspect actual visual evidence. Do not mark human review as completed.
6. No edits to MoneyPrinter, upload/publish paths or pre-existing dirty source.

Status and actual commands/results are recorded in `WORKLOG.md` after execution.
