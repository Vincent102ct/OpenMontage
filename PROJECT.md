# OpenMontage — Stickman Horror Product Contract

Effective 2026-10-22. This is the authoritative project-specific product contract
for this repository. The user explicitly selected this identity; it supersedes
conflicting visual-direction assumptions and earlier product/style decisions.
Upstream OpenMontage remains a general video production platform. Its generic
architecture, tool contracts, pipelines and agent protocols remain applicable;
this document defines the selected product built with that infrastructure.
The Master Story Package remains the authority for story content and claims.

## Product identity

**OpenMontage in this project is an Automated Stickman Horror Video Production System.**

## Visual identity

Primary output is **2D Stickman Horror Animation**, with:

- Persistent stickman characters.
- Consistent character designs and proportions.
- Character acting, gestures and physical actions.
- Horror environments and atmospheric lighting.
- Cinematic framing and camera movement.
- Object interaction and scene continuity.
- Scene animation synchronized with narration.

The following are explicitly **not the primary output**:

- Documentary Motion Graphics.
- Text-only slideshows.
- Generic Pexels footage montages.
- Static images with zoom as the main storytelling method.
- Infographics replacing character-driven scenes.

Historical documents, subtitles, diagrams and archival images may appear as
supporting elements only when narratively appropriate. They do not replace
character-driven animated scenes.

## Content

Horror, ghost stories, mysteries, historical mysteries and unexplained cases.
Preserve historical accuracy, uncertainty and source attribution. Label
reconstructions explicitly; an animated depiction is not historical evidence.
Do not turn disputed or unknown actions into established events.

## Production pipeline

```text
TOPIC
→ RESEARCH
→ MASTER STORY PACKAGE
→ SHORT/LONG NARRATIVE
→ STICKMAN HORROR SCENE PLANNER
→ CHARACTER / ENVIRONMENT / PROP ASSETS
→ ACTION ANIMATION
→ NARRATION / SUBTITLES / SOUND
→ VIDEO RENDER
→ QUALITY CONTROL
→ HUMAN REVIEW
```

Short and Long must share the canonical story, claims, characters, locations,
objects and continuity constraints. Format-specific pacing and framing must
preserve that shared canon. This is the product flow, not a newly implemented
pipeline manifest or authorization to bypass existing production gates.

## Technical priorities

- Reuse existing M1/M1.1 character animation and Remotion infrastructure wherever
  feasible; inspect actual source before proposing extensions.
- Zero mandatory paid API credits. Required production capability must have a
  working path without paid API credits.
- Preserve source-first engineering: source and current contracts outrank stale
  capability descriptions; distinguish inspected code from runtime verification.
- Maintain historical accuracy and reconstruction labeling throughout production.
- Prefer working video output over documentation-only milestones. This identity
  lock itself is documentation only; it does not authorize media generation.

## Inspected reuse boundary

M1/M1.1 already supplies reusable animation mechanics. Source inspection for this
decision found the following candidates, not a completed STORY 053 integration:

| Existing source | Reusable capability / boundary |
| --- | --- |
| [motion.ts](tools/character/remotion/motion.ts), [story_motion.py](tools/character/story_motion.py) | Seekable tracks, fixed-length two-bone IK, walking and prop grip/release mechanics. |
| [story_planner.py](tools/story/story_planner.py), [locations.py](tools/story/locations.py) | Character staging, gestures, hand-over, seating, prop ownership and procedural environments; action/location vocabularies are bounded. The M1 planner can extend timing for actions, so it is not a drop-in replacement for the fixed M2.3 timeline. |
| [StoryVideo.tsx](tools/character/remotion/StoryVideo.tsx), [Actor.tsx](tools/character/remotion/Actor.tsx) | Persistent actor/world state, camera/light tracks, narration/subtitles/SFX and shared rig. Current actor artwork is a filled cartoon, not an approved Stickman Horror design. |
| [character_animation.py](tools/character/character_animation.py), [story_video.py](tools/character/story_video.py) | Existing opt-in character renderer route, validation and Remotion workspace handoff; preserve unrelated composer WIP. |
| [index.tsx](tools/character/remotion/index.tsx) | StoryAction, StoryEpisode and StoryVideo compositions currently fix the canvas at 1280×720. Vertical STORY 053 framing requires assessment. |

See the [M1/M1.1 feature contract](docs/features/story-to-video-pipeline.md) for
existing capabilities and limits. No renderer, style adaptation, vertical support,
runtime availability or STORY 053 scene coverage is certified by this inspection.

## Current milestone boundary and next task

- M2.1 Master Story Package and M2.2 narration are completed technical baselines
  and remain valid; listening, factual and publication reviews remain separate.
- M2.3 canonical scene planning is technically completed. Its timings and
  canonical references are reusable, but its Documentary Motion Graphics visual
  treatments require correction to Stickman Horror before M2.4.
- The previous documentary-oriented M2.4 prompt is cancelled. The documentary
  asset resolver is **not authorized for implementation or continuation**.
  Existing documentary M2.4 WIP and historical records are preserved, not adopted
  as the current product direction.
- **Next engineering milestone:** inspect and map the existing Stickman Animation
  renderer against STORY 053's 11 scenes, SC_001 through SC_011. Produce a
  per-scene capability/gap map covering character identity, actions, environments,
  props/contact, continuity, camera, narration timing, vertical framing and
  reconstruction labels. Identify reuse, required changes and blockers; do not
  implement the mapping's recommendations as part of this documentation task.

This task does not rewrite narration/claims, change the Master Story Package,
modify storyboard JSON/timestamps, generate images/videos, implement a renderer,
start M2.4, or authorize commit/push. Historical facts, publication rights and
human review gates are never automatically approved by this product decision.

## Related guidance and deferred dependency

- [Agent guide](AGENT_GUIDE.md) and [shared context](PROJECT_CONTEXT.md): agent entry
  and generic engineering conventions; read this contract before visual decisions.
- [Decisions](DECISIONS.md): explicit user decision and superseded directions.
- [Roadmap](ROADMAP.md): current milestone status and historical progress.
- [Source map](SOURCE_MAP.md): existing implementation inventory; older visual
  directions and M2.4 handoff descriptions are historical where they conflict.
- [Worklog](WORKLOG.md): inspection, preservation and verification evidence.
- [P1 Studio Input MVP](docs/features/p1-studio-input-mvp.md): local input-only
  creation entry point (`python -m studio open`, [Windows guide](docs/STUDIO_WINDOWS.md)).
  Saves a production request with the fixed Stickman Horror 2D style; it starts no
  production and does not change the renderer-mapping milestone above.
- [Architecture](docs/ARCHITECTURE.md): contains pre-existing uncommitted WIP and
  remains untouched. Add the product-contract reference there only after that WIP
  is reconciled separately; this dependency does not delay this contract's effect.
