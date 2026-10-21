# Story-to-action: opening episode

## Goal and scope

Extend the approved Minh cup pilot into the opening of "Có người ngủ dưới giường tôi"
(source: `examples/story-to-action/source_story_opening.md`, opening only, supplied
verbatim by the user). Same style, Minh v1 and Apartment v1; no full story, no
publish, no paid API. Narration reproduces the 18 source paragraphs exactly.

## Reuse and extension

- Same `character-animation` pipeline, `CharacterRigRenderer` → Remotion package →
  registry `video_compose`, `macos_say_tts` (Linh vi_VN, rate 145, as the pilot).
- `motion.ts` (backward compatible): optional `facing` (mirrored rig), `face` keys
  `[t, brow, gazeX, gazeY, mouth, lid, tilt]`, nullable grip/release/wash window and
  hand `attachments` to world items. Pilot motion evaluates unchanged.
- `Actor.tsx`: Minh v1 drawing extracted from `Scene.tsx`; with a neutral face it emits
  the same SVG. Six pilot frames rendered with old and new templates are pixel-identical.
- `shots.ts` + `Episode.tsx` (`StoryEpisode` composition): one persistent world, many
  shots. A shot only chooses time, camera `[t, cx, cy, zoom]`, light `[t, day, fade]`,
  view (world or full-frame insert) and item states (chair offset, fridge door angle).
- `story_motion.py`: `walk_clip` (planted-foot gait between rest poses),
  `stand_pose`, `hold_tracks`, `concat_tracks`, `validate_episode`, `write_episode_package`.
- `tools/audio/procedural_sfx.py`: deterministic FFmpeg lavfi cues (room tone, fridge
  hum, tap water, ceramic clink, footstep, fridge door, low drone). $0, offline.
- Apartment extension art (same palette/line): `apartment_west.svg` (living room, dining
  table, fridge), `apartment_west_overlay.svg` (table over chairs), `apartment_east.svg`
  (bathroom door), `window_day.svg` (morning window), inserts `insert_sink_cup.svg`,
  `insert_fridge_bottle.svg`. `apartment.svg` and `foreground.svg` are untouched.

## Pilot reuse and the inverted cup

Shot `s07_evening_wash` plays pilot motion 1.6–14.2 s. One adaptation is made to an
episode-local copy (`adapt_pilot_pickup`): the story puts the cup *in the sink*, but
the pilot cup started on the counter beside the basin. The cup now rests inside the
basin (its foot clipped by the near basin wall), Minh shifts his weight while reaching,
and the grip targets the new handle. Wash, inversion, release and walk keys are the
pilot's. The inversion is made readable by drawing and framing: the episode cup shows
its mouth only when upright and its flat foot disc on top when inverted, water drips
after release, and the camera pushes to 3.4× on the rack.

## World state contract

Monday shots: cup upright in the basin with a dried ring; chair B tucked; fridge closed.
After the evening release: cup inverted at the rack for every later frame. Next morning:
chair B pulled out (+120 px, −6°), chair A tucked; fridge door opens only in `s09` and
stays open. Inserts carry the same state. The all-frame test asserts each rule.

## Contracts and failure modes

`validate_episode` fails closed on: gaps/overlaps between shots, keys not covering a shot,
camera framing beyond the artwork on any render frame, zoom < 1, light outside [0, 1],
narration crossing a cut or not reproducing the source text, missing media, narration
without an overlapping linked action (`timeline.metadata.narration_links`), unknown
actions/entities, hand/cup or hand/handle discontinuity at ownership boundaries.

## Pacing

Durations come from the real WAVs (speech 57.44 s). With actions, holds and two fades the
episode is 80.3 s. Speech is not sped up and no text is dropped (user instruction).

Status, commands and results: `WORKLOG.md`.
