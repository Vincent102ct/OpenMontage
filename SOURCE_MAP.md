# Source map — story-to-action pilot

Windows compatibility extension (2026-10-22, baseline `coding` / `877a12b`):
`scripts/story_to_video.py` selects installed offline speech through
`tools/audio/local_narration.py`; `local_wav.py` defines measured mono 24 kHz PCM16.
Native adapters remain `macos_say_tts.py` and `windows_sapi_tts.py` (Windows
PowerShell/PowerShell 7 inventories are distinct); `piper_tts.py` accepts only
local, language-declared models. Tests: `tests/tools/test_local_narration.py` and
the existing native-provider/story suites. Setup/evidence:
`docs/WINDOWS_STORY_TO_VIDEO.md`, `docs/WINDOWS_M11_HANDOFF_2026-10-22.md`.
Story Planner, Remotion templates and pre-existing evidence/FFmpeg WIP are untouched.

Verified 2026-10-21 on branch `coding`, HEAD `fe4157f`. Existing dirty cinematic,
surveillance and footage-led work is outside this change and must be preserved.

## Existing execution path

| Responsibility | Actual source | Finding before implementation |
| --- | --- | --- |
| Pipeline and stages | `pipeline_defs/character-animation.yaml`, `skills/pipelines/character-animation/` | Beta, ten stages; no automatic Python orchestrator |
| Discovery | `tools/tool_registry.py` | Six local character tools available |
| Character identity/rig/poses | `tools/character/character_animation.py` | Structured artifacts work; unknown actions get empty placeholder poses |
| Action compiler | same file, `ActionTimelineCompiler` | Ignores semantic action sequences; emits anticipate/perform/settle |
| Character renderer | same file, `CharacterRigRenderer` | Generic SVG/GSAP bounce; does not render timeline actions or prop contact |
| Preview capture | same file, `_render_preview_mp4` | Wall-clock screenshots; not a deterministic final character render |
| Composition | `tools/video/video_compose.py` | Existing Remotion project-local entry/props/public-dir handoff; preserve dirty file |
| Remotion | `remotion-composer/package.json`, `src/Root.tsx` | Installed 4.0.484; cached Chrome exists |
| HyperFrames | `tools/video/hyperframes_compose.py` | Preflight package resolution timeout; not selected |
| TTS | `tools/audio/tts_selector.py`, `piper_tts.py`, `windows_sapi_tts.py` | No available Vietnamese provider at initial preflight; macOS `say` lists Linh vi_VN |
| Subtitles | `tools/subtitle/subtitle_gen.py` | Supports measured segment timestamps, no need to invent word timestamps |
| Audio | `tools/audio/audio_mixer.py` | FFmpeg delay/mix/padding already implemented |
| Evidence/state | `lib/checkpoint.py`, `schemas/artifacts/` | Schema validation, checkpoints, history, board |
| Existing audit | `docs/ARCHITECTURE_RESET_AUDIT.md` | Earlier footage-led audit; retained unchanged, availability refreshed |

Baseline: `.venv/bin/python -m pytest tests/contracts/test_character_animation_pipeline.py -q`: 7 passed.

## Planned narrow extension (recorded before source changes)

Retain the instruction-driven pipeline. Extend the existing compiler with explicit
timed action input; extend the existing character renderer with a Remotion package
for authored skeletal tracks and prop attachment. Use the existing `video_compose`
dispatcher for final rendering. Add a native macOS TTS provider following the
Windows SAPI provider contract. Keep apartment geometry and pilot choreography in
an explicit fixture, separate from frame evaluation. No alternate render engine,
cloud generation, model download, publishing, or generalized story planner.

Implementation/evidence links: `docs/features/story-to-action-animation.md`,
`WORKLOG.md`, `DECISIONS.md`, `ROADMAP.md`.

## Implemented extension

- `tools/character/character_animation.py`: explicit `timed_actions` compiler
  input and opt-in `story_motion` package handoff; existing generic path retained.
- `tools/character/story_motion.py`: bounded keys, entities/actions, grip/release
  continuity and existing Remotion entry/props/edit handoff.
- `tools/character/remotion/{motion.ts,Scene.tsx,index.tsx}`: seekable track/IK
  mechanics and filled cartoon rig; original apartment is separate SVG data.
- `examples/story-to-action/`: authored artwork, motion and required actions.
- `tools/audio/macos_say_tts.py`: installed voice/locale matching and sample-count
  validation; no service substitution, model or credential dependency.
- `tests/tools/test_story_motion.py`, `test_macos_say_tts.py`: contact/continuity
  regression checks and TTS failure cases. Existing character contracts retained.
- `schemas/artifacts/decision_log.schema.json`: accepts documented
  `approval_policy` category, which the guide already requires for scoped run
  preauthorization. Pilot log distinguishes execution authorization from visual acceptance.

Opening episode extension (2026-10-21, `docs/features/story-to-action-opening-episode.md`):

- `tools/character/remotion/motion.ts`: optional facing/face/attachments, nullable
  grip and wash window; pilot path unchanged.
- `tools/character/remotion/Actor.tsx` (extracted Minh v1 drawing, used by `Scene.tsx`),
  `shots.ts` (pure multi-shot evaluator), `Episode.tsx` + `index.tsx` (`StoryEpisode`).
- `tools/character/story_motion.py`: gait/pose helpers, `validate_episode`,
  `write_episode_package`; `character_animation.py`: `story_episode` route.
- `tools/audio/procedural_sfx.py`: local FFmpeg sound cues.
- `examples/story-to-action/`: source opening, narration split, builder, extension art.
- `tests/tools/test_story_episode.py`.

Live run: `projects/minh-cup-cartoon-pilot/`; native `video_compose` dispatched
to Remotion. No change to `tools/video/video_compose.py` was needed for this task.

# Source map — story-to-video M1 (automatic story → MP4)

Verified 2026-10-21, branch `coding`, HEAD `fe4157f`, same dirty tree as above (preserved).

## What exists and what is missing for "any story → MP4"

| Need | Existing source | Gap found before implementation |
| --- | --- | --- |
| Story text in | `examples/story-to-action/source_story_opening.md` (one fixed story) | No generic loader/segmenter; fidelity check hard-codes the Minh header |
| Analysis | none (pilot/opening are hand-authored) | No character/location/prop/action extraction; no local LLM adapter |
| Scene/action plan | `examples/story-to-action/build_opening_episode.py` | Every shot, key and link is hand-written for Minh |
| Skeletal mechanics | `tools/character/remotion/motion.ts`, `Actor.tsx`; `story_motion.walk_clip/stand_pose/concat_tracks` | Reusable as-is; facing is per-motion scalar |
| Multi-shot renderer | `tools/character/remotion/{shots.ts,Episode.tsx}` | World is Minh's apartment (cup, fridge, chair B fixed in code) |
| Validation | `story_motion.validate_episode` | Minh-specific items; no per-frame limb reachability check |
| Narration | `tools/audio/macos_say_tts.py` (Linh vi_VN) | Reusable; English voice selection needed |
| SFX | `tools/audio/procedural_sfx.py` | Reusable; no rain/knock/door/street/engine recipes |
| Render | `CharacterRigRenderer` → `video_compose` atelier → Remotion | Reusable unchanged |
| Local LLM | none installed at preflight | Ollama 0.40.7 installed via Homebrew for this task; model `qwen2.5:7b-instruct` |

## Planned narrow extension (recorded before source changes)

- `tools/story/`: `story_analyzer` (deterministic segmentation + rules lexicon VI/EN,
  optional Ollama labelling constrained to enums, fallback to rules), `locations`
  (procedural original SVG rooms with named anchors), `story_planner` (analysis +
  measured narration → generic multi-shot `story_video` props and `action_timeline`),
  `story_qa` (post-render probes).
- `tools/character/story_video.py` + `remotion/StoryVideo.tsx`: generic validator /
  package / composition reusing `motion.ts` + `Actor.tsx`; new `story_video` route in
  `CharacterRigRenderer`. Pilot `StoryAction` and `StoryEpisode` stay untouched.
- `procedural_sfx`: additive recipes only.
- `scripts/story_to_video.py`: one-command CLI. The repo is agent-driven ("no Python
  orchestrator"); the user explicitly asked for a single CLI, so the script only calls
  registry tools in stage order and writes the canonical artifacts (see `DECISIONS.md`).

## Implemented (story-to-video M1)

- Added `tools/story/{__init__,lexicon,story_analyzer,locations,story_planner,story_qa}.py`
  (`story_analyzer`, `story_planner` are registry tools; `story_qa` is a library).
- Added `tools/character/story_video.py` (validator + package) and
  `tools/character/remotion/StoryVideo.tsx`; `remotion/index.tsx` registers `StoryVideo`
  (existing compositions untouched); `character_animation.py` gains the `story_video` route.
- `tools/audio/procedural_sfx.py`: 8 additive recipes (rain, street_ambience, knock,
  door_open, engine, paper, switch, soft_place).
- Added `scripts/story_to_video.py` (single CLI), `tests/tools/test_story_to_video.py`,
  `examples/story-to-video/` (two new stories), `docs/features/story-to-video-pipeline.md`.
- Unchanged: `motion.ts`, `Actor.tsx`, `shots.ts`, `Episode.tsx`, `Scene.tsx`,
  `story_motion.py`, `video_compose.py`, Minh fixtures and projects.

## Story-to-video M1.1 quality pass (2026-10-21)

Root causes traced in source before changes (see WORKLOG M1.1 for the frame evidence):

| Observed in MP4 | Layer | Source |
| --- | --- | --- |
| People overlapping (EN 0:27–0:49) | Character staging | `ShotBuilder.stand_near` / `_gesture` ignored others; validator had no spacing rule |
| Child as tall as adults | Renderer / rig | one rig size; `Person` had no scale |
| Unclear hand-over (EN 0:48–0:55) | Action library + camera | `give`: 92 px gap, 0.6 s touch, no shared hold, zoom cap 1.55 |
| Umbrella over the face (VI 1:16–1:18) | Planner ordering | `ShotBuilder` built poses before `weather` was set → grip at the hip, canopy open |
| Boarding not shown (VI 1:20–1:24) | Action library + renderer | `board` = fade in front of a bus smaller than a person; no inside layer |
| Sitting (VI 1:36–1:39) | Action library | vertical drop, pelvis 10 px into the cushion, sliding feet, no seat contact |
| Letter too small (VI 1:45–1:50) | Camera | fixed 2.0× reveal zoom, no close-up for written items |
| (found while fixing) tray flying across the face | Prop interaction | `spawn_in_hand` recorded the post-spawn state as the initial rest at (0, 0) |

Changed: `tools/story/story_planner.py`, `tools/story/locations.py` (seat top/width/kind),
`tools/character/story_video.py` (rig-space reach for scaled bodies, spacing, face occlusion,
inserts), `tools/character/remotion/StoryVideo.tsx` (scale, vehicle back/front layers,
item depth, inserts), `tests/tools/test_story_to_video.py`. Pilot files unchanged.
