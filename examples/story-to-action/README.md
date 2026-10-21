# Minh cup pilot

Original SVG artwork and authored world-space motion for the existing
`character-animation` pipeline, using native Remotion composition. Visual
specification: `docs/features/story-to-action-visual-style.md`.

- `apartment.svg`, `foreground.svg`: stable 1280×720 room and occlusion layers.
- `pilot.motion.json`: one actor, one cup, point/rotation keys, ownership and
  wash window. Keys are `[seconds, x, y]`, cup keys add rotation in degrees.
- `pilot.actions.json`: the four mandatory actions, exact times and targets.

`ActionTimelineCompiler` accepts `timed_actions={scene_id: actions}`. The
existing `CharacterRigRenderer` accepts `story_motion` with that timeline and a
project-local `workspace_path`. It emits an existing `video_compose` Remotion
handoff. The legacy generic SVG/GSAP path remains available when this field is
absent. Follow `AGENT_GUIDE.md` and pipeline stages/checkpoints before production.

The example has no narration until the assets stage supplies actual measured
WAV paths/intervals. It does not infer speech timing, reinterpret arbitrary
narration or fabricate audio. Reuse the rig/IK/attachment mechanics and retarget
authored tracks explicitly; there is no automatic action-clip retargeter yet.

Opening episode (`docs/features/story-to-action-opening-episode.md`):

- `source_story_opening.md`: user-supplied opening text (not the whole story).
- `opening.narration.json`: the source split into 24 narration segments, text exact.
- `opening.durations.json`: measured sample counts of those WAVs (test fixture).
- `build_opening_episode.py`: authored shots, camera, light, item states, actor
  tracks, sound cues and narration→action links, timed from real WAV durations.
- `apartment_west*.svg`, `apartment_east.svg`, `window_day.svg`: Apartment v1
  extensions; `insert_sink_cup.svg`, `insert_fridge_bottle.svg`: close-up inserts.

Verified pilot: `projects/minh-cup-cartoon-pilot/` (generated, gitignored).
Opening run: `projects/minh-under-bed-opening/` (generated, gitignored).
Reproducibility and checks: root `WORKLOG.md`. Do not ship this fixture as proof
that untested stories, props or rooms are supported.
