# Story-to-video pipeline (M1: automatic story → MP4)

## Goal

One command turns a new story text file into a narrated 2D cartoon MP4, fully local:

```sh
python scripts/story_to_video.py path/to/story.md [--analyzer auto|rules|ollama] [--draft] [--no-render | --dry-run]
```

Input: UTF-8 text/markdown, optional `# Title` first line, paragraphs separated by blank
lines, Vietnamese or English. Output: `projects/<slug>-auto/renders/final.mp4` plus the
artifacts listed below. No paid API, no cloud, no UI, no Shorts (out of M1 scope).

## Stages (all registered tools, called in order by the script)

| Stage | Tool / code | Output artifact |
| --- | --- | --- |
| Analyze | `story_analyzer` (`tools/story/story_analyzer.py`, `lexicon.py`) | `artifacts/story_analysis.json`, `llm_labels_raw.json` |
| Narrate | Installed offline provider selected by OS + actual voice language (`windows_sapi_tts`, `macos_say_tts`, explicitly configured `piper_tts`); measured PCM WAV, provider/settings/content-aware cache | `assets/audio/bNN.wav`, `narration_manifest.json`, `artifacts/tts_selection.json` |
| Plan | `story_planner` (`tools/story/story_planner.py`, `locations.py`) | `artifacts/story_video.json`, `action_timeline.json` |
| Sound | `procedural_sfx` (8 new generic recipes, existing ones unchanged) | `assets/audio/sfx/*.wav` |
| Validate + package | `character_rig_renderer` `story_video` route → `tools/character/story_video.py` | `composition/`, `edit_decisions.json`, `asset_manifest.json` |
| Render | `video_compose` atelier → Remotion `StoryVideo` (`tools/character/remotion/StoryVideo.tsx`) | `renders/final.mp4` |
| QA | `tools/story/story_qa.py` | `artifacts/qa_report.json`, `renders/keyframes/`, `renders/contact_sheet.jpg` |
| Report | script | `artifacts/render_report.json`, `assets/subtitles.srt` |

## Analysis

Windows setup and speed units: [Windows guide](../WINDOWS_STORY_TO_VIDEO.md).
`--dry-run` is analysis-only and emits no timeline or assumed narration durations.
`--no-render` generates real narration/SFX and a validated package, skipping only
browser rendering. Missing matching offline speech blocks package/render, never
falls back across languages or to a paid service. macOS Linh/Samantha defaults
and native normalization are preserved.

- **Narration text is never generated.** Deterministic segmentation (quote-aware sentence
  split, long sentences split at the comma nearest the middle) must reproduce the source
  exactly; the validator re-reads the source file and compares.
- **Rule pass (primary):** closed vocabularies in `lexicon.py` for 36 animatable actions,
  8 location kinds, 16 prop kinds, 11 location features, person nouns, pronouns, colours,
  day/night, rain, time jumps. Names: capitalised tokens that the text never writes in
  lowercase (mid-sentence, or repeated/followed by a verb). Per clause: subject (name,
  person noun or pronoun with gender learning), verbs in order with their character offset,
  targets (prop / character / feature), `give` object. Quoted speech is masked for
  detection; dialogue becomes a `talk` action for the speaker. Negated (`không ai`,
  `nobody`) and indefinite (`ai đó`, `someone`) subjects are handled.
- **Local LLM (optional, `auto` default):** Ollama `qwen2.5:7b-instruct`, JSON-schema
  constrained to the same enums, temperature 0, seed 7. Measured on the two test stories,
  replacing rule labels with model labels made results worse (invented exits, swapped the
  actor of "bước lên xe", dropped "biến mất"). So the merge is **fill-only**: the model may
  enrich gender/age and fill beats where rules found nothing, only with actors named or
  referred to in that beat. Agreement with rule actions is reported
  (`analyzer.merge.rule_actions_confirmed`). Unreachable endpoint → rules only (`auto`) or
  hard error (`ollama`).

## Planning

- Shots: consecutive beats in one location, at most 3 beats per shot; a new shot on
  location change or time jump (time jumps fade through black). 2.4 s title card first.
- Timing: beat = 0.3 s lead + measured WAV + 0.4 s tail, extended if actions need longer.
  Body actions start when their verb is spoken (offset ÷ sentence length × WAV length).
- Motion: existing `walk_clip` (auto-slowed until no planted foot exceeds the 115 px leg),
  stand/sit/crouch poses, IK-safe hand targets (stand within 45 px of what is touched),
  facing step keys with a 0.25 s re-pose on turns, face keys (expressions, gaze toward
  target, mouth flap over the quoted part of the line, nod/shake).
- Items: rest on named anchors (`REST_DY` = grip height), attach to the hand on pick-up,
  transfer hand-to-hand on `give`, follow the hand key-for-key (validator: ≤ 0.5 px on
  every frame), go inside the oven, disappear, or fade in at the hand when the text uses
  an item never placed (logged in `planner_notes`). Umbrellas open and are raised outdoors
  in rain. Vehicles arrive, are boarded (actor fades at the door) and leave.
- World state persists across shots: positions, posture, held items, door, vehicles.
- Camera frames whoever acts in the beat (zoom 1.0–1.55), 2.0× on revealed/disappeared
  items; keys are clamped so every interpolated frame stays inside the artwork.
- Sound: room tone / street ambience per shot, rain, footsteps on real landings, knock,
  door, switch, paper, place, engine, low drone on reveals. No music.

## Rendering

`StoryVideo` composition (registered next to `StoryAction`/`StoryEpisode`, which are
unchanged) reuses `motion.ts` `stateAt` IK and `Actor.tsx` (v1 rig) per actor, adds long
hair, per-kind item drawings, doors, window sky/rain, outdoor rain, bus/car, darkness and
fade overlays, captions and audio sequences. Locations are procedural original SVGs in the
Apartment v1 palette: office, street (bus-stop variant), living room, kitchen, shop (bakery
variant), bedroom, park, generic room.

## Contracts (fail closed before render)

`validate_story_video`: action_timeline schema; shots contiguous on the frame grid; all
key tracks cover their shot; on **every** frame: camera inside artwork, zoom ≥ 1, light in
range, every limb within the IK span motion.ts accepts, held items in the hand; narration
ordered, inside one shot, files exist, exact source text; each narration linked to an
overlapping action; sound cues in range with files.

## M1.1 quality pass: added capabilities

| Capability | Where | Behaviour |
| --- | --- | --- |
| Body scale (children 0.72) | `Person.scale`, `ActorTrack.W/B`, `StoryVideo.actorState` | Same rig drawn smaller about the ground line; world tracks, rig-space IK |
| Personal space | `ShotBuilder.make_room`, `visible_standing` | Someone standing at a destination steps aside (gap 105 px × scale) |
| Gesture clearance | `Planner._clear_arm` | Point/wave never passes through a person; the gesturer steps back |
| Conversation facing | `_gesture("talk")` | Speaker and nearest listener turn to each other |
| Two-handed carry | `TWO_HANDED` (bread, box, tray) | Item held in front, the free hand supports it |
| Hand-over | `ShotBuilder.give` | Arm's length, both hands on the item, shared hold, switch, draw in; contact window |
| Boarding a vehicle | `Planner._board`, `VehicleBack/Front` | Door opens, step up, step in behind the body, doors close, ride away |
| Sit down / stand up | `ShotBuilder.sit_down`, `stand_from_seat` | Plant feet, hips back and down, hand on seat edge, pelvis on y 556; bag beside on wide seats |
| Discovery staging | `Planner._reveal` | Observer goes over (or steps off the item) and looks |
| Size-aware close-ups | `ITEM_SIZE`, `ITEM_CENTER_DY`, `_frame` | Zoom 2–4× from item size, centred on its visual centre |
| Written-item insert | `pending_insert`, `Insert` | Full-frame close-up showing the quoted words of that sentence |
| Hold framing | `_frame` | A sentence with nothing new keeps the previous framing |
| Depth of items | `StoryVideo.World` | Resting items behind people, held items between body and hands |
| Depth lane | `ActorTrack.walk`, `DEPTH_LANE`, draw order by planted foot | A walker passing a standing person moves one step deeper and is drawn behind |
| Surface slots | `Planner.slot` | Items placed on an occupied surface spot move to the next free spot |
| Hidden spawn | `ShotBuilder.spawn_in_hand` | An item first used in a hand is hidden and parked at the hand until it fades in |

New fail-closed checks in `validate_story_video`: rig-space reach for scaled bodies; two
people standing still inside each other or walking through each other on the same depth
lane (outside a hand-over); a held item (including an open umbrella's canopy and shaft)
covering a face; insert bounds.

## Known limits (M1)

See `WORKLOG.md` (story-to-video M1) for measured results and the full limitation list.
