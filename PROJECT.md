# OpenMontage — Product Contract

Effective 2026-10-23, updated through the accepted P3.3 technical milestone. This is the authoritative product identity
for this checkout. It supersedes the earlier mandatory Stickman treatment and
historical documentary/motion-graphics assumptions. Generic OpenMontage pipeline,
architecture, tool and human-review contracts still apply.

## Primary visual identity

**Cinematic 2D Cartoon Supernatural Horror Animation.**

OpenMontage specializes in ghost stories, supernatural folklore, occult mysteries,
psychological horror, unexplained mysteries and murder-case storytelling.
The primary output consists of character-driven animated horror scenes with:

- Recognizable cartoon characters with faces, hair, clothing and expressions.
- Persistent, consistent character identities and proportions across Short and Long.
- Atmospheric horror environments, directional low-key lighting, deep shadows,
  controlled palettes, cinematic compositions and atmospheric depth.
- Suspenseful camera work, deliberate pacing and sound design that includes silence.
- Fear acting through shoulder tension, hesitation, listening/freezing, head/eye
  reactions, guarded hands and believable interaction with doors and props.
- Restrained supernatural events: partially obscured figures, unexplained movement,
  unnatural pauses, suspicious environmental changes and carefully timed reveals.

The target is a mature 2D animated horror film. Do not substitute friendly explainer
animation, stickman demos, infographics, comedy, slideshows, generic stock montages
or still-image zooms for character-driven scenes. Do not rely on excessive gore,
random monsters, cheap jump scares or constant darkness. Supporting documents,
subtitles, diagrams or archival material may appear when narratively appropriate.

## Canon and continuity

The Master Story Package and Story Bible remain the authority for content,
characters, claims, locations, objects and continuity. Short and Long share that
canon; their framing, pacing, poses and expressions may vary without silently
changing character identity. Preserve uncertainty and attribution. An animated
reconstruction is not historical evidence.

## Existing infrastructure and backward compatibility

Reuse existing `StoryVideo`, `Actor`, Remotion, seekable motion tracks, planted-foot
walking and two-bone IK. Character art is layered over those mechanics.

- New cinematic previews explicitly use `character_skin: "cartoon_horror"`,
  `look.treatment: "cinematic"` and optional deterministic `horror` tracks.
- `stickman_horror` remains an optional legacy renderer skin.
- Existing default `cartoon`, 16:9 compositions and explicit legacy skins remain
  supported. Establishing a primary product identity does not rewrite renderer
  defaults in saved packages or change existing composition IDs.
- Existing `stickman_horror_2d` request/package identifiers in Studio, intake and
  schemas remain compatible. Do not silently migrate, rewrite or reinterpret saved
  production requests, reviewed packages, Story Bibles or private story data.
  Any future intake/schema migration needs a separate scoped change and review.
- Keep the existing renderer and tool handoff; no required paid API or new runtime.

## P3.1 acceptance and review boundary

The user accepted **P3.1 v2 as the new visual foundation and technical milestone**.
This acceptance does not certify that future production videos are artistically
complete. Known gait, hands, viewpoint, vector-lighting, silhouette and Foley
limitations remain documented; they are not marked resolved.

Subjective audio listening has no recorded human acceptance and remains **pending**.
Automated playback is muted; audio RMS, timing and clipping checks do not replace
listening. On 2026-10-23 the user confirmed that pending audio acceptance does not
block the scoped technical-baseline commit `feat(animation): establish cinematic
cartoon horror visual baseline` and its normal push to `origin/coding`. Audio
artistic acceptance stays pending until a human listening review is recorded.

Preserve the existing synthetic evidence:

- P3.0: `projects/p30-stickman-horror-preview/` (legacy proof).
- P3.1 v1: `projects/p31-cartoon-horror-preview/` (first cartoon proof).
- Accepted P3.1 v2: `projects/p31-cartoon-horror-preview-v2/`.

Media, contact sheets, logs, ZIPs, private content and temporary workspaces stay
local and gitignored. The exact milestone file list and verification are in the
[P3.1 finalization report](docs/features/p3.1-finalization.md).

## P3.2A technical acceptance and next handoff

The user accepted **P3.2A Horror Visual Asset Library as a technical baseline**
on 2026-10-23, based on isolated regressions, registry-integrity checks, all four
Nora/Victor room/corridor combinations and actual MP4 evidence. The user authorized
the exact 15-file commit `feat(animation): add reusable cinematic horror asset
library` and a normal push to `origin/coding`. Subjective visual and audio
acceptance remain **pending**; known animation and lighting defects remain open.

The registry is opt-in: stable IDs, pinned integer revisions, stored content hashes
and explicit environment anchors resolve into the existing StoryVideo/IK/Remotion
pipeline. Old packages retain their renderer behavior without a registry binding.
The [P3.2A report](docs/features/p3.2a-asset-library.md) defines the version and
binding constraints, exact scope, evidence and limitations.

The accepted P3.3 Story Visual Bible technical milestone consumes these pinned
cast/location/lighting bindings and preserves canonical story authority. It adds
a separate Studio visual-design approval for future scene planning only; it does
not approve a real story, authorize production or imply artistic/audio acceptance.
See [P3.3](docs/features/p3.3-story-visual-bible.md). P3.4 scene planning and
end-to-end story production require their own scope and authorization.

## P3.4 scene planning (implemented, pending review)

P3.4 compiles the current approved Reviewed Story and the current approved Visual
Bible into immutable, source-traceable Short (9:16) and Long (16:9) scene plans with
a separate Studio approval scoped to scene planning only. Long covers the complete
reviewed plan; unsupported actions are explicit blockers, never deleted story.
Timing stays a provisional estimate with a P3.5 measured-narration retiming
contract. It starts no TTS, rendering, production or publishing. See
[P3.4](docs/features/p3.4-scene-planning.md).

## Production boundary

The user accepted P3.3 technically and authorized the exact 16-file commit
`feat(studio): add reviewed story visual bible workflow` and normal push to
`origin/coding`, after final verification. This covers Story Visual Bible + Studio
review, using synthetic fixtures and local reference PNGs. Artistic and audio
acceptance remain pending. Stop after this scoped commit/push. Do not begin P3.2B, P3.4, TTS,
full-story rendering, real-pilot production, publication or story-data migration.
Do not alter STORY 053, its reviewed packages, narration, scene timestamps,
private pilot or Story Bible. M2.1/M2.2 and M2.3 baselines remain preserved;
historical documentary M2.4 WIP is not the selected product direction and is not
included in this milestone. Unrelated WIP remains outside the scoped commit.

## References

- [Agent guide](AGENT_GUIDE.md) and [shared context](PROJECT_CONTEXT.md).
- [P3.1 first preview](docs/features/p3.1-cartoon-horror-preview.md).
- [P3.1 cinematic revision](docs/features/p3.1-cinematic-horror-revision.md).
- [P3.2A reusable asset library](docs/features/p3.2a-asset-library.md) (technical baseline accepted; human visual/audio review pending).
- [P3.4 scene planning](docs/features/p3.4-scene-planning.md) (implemented; pending user review, not committed).
- [P3.0 historical proof](docs/features/p3.0-stickman-renderer-proof.md).
- [M1/M1.1 character pipeline](docs/features/story-to-video-pipeline.md).

Historical decisions and reports remain evidence of their original dates. Where
older product labels conflict, this finalized identity takes precedence.
