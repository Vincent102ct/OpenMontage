# Story-to-Action worklog

## 2026-10-21 — context and baseline

Checkout of this repository (OpenMontage), branch `coding`,
HEAD `fe4157f`. Six tracked paths were already dirty, with additional footage-led
and surveillance files untracked. Those source changes were preserved. No commit,
staging, cleanup, provider credentials, heavy model installation or publish action.

Consulted `AGENTS.md`, `AGENT_GUIDE.md`, `PROJECT_CONTEXT.md`, existing
`docs/ARCHITECTURE_RESET_AUDIT.md`, architecture/README/config material,
`pipeline_defs/{character-animation,animation}.yaml`, character stage directors,
checkpoint/reviewer/runtime/taste/bespoke guidance, source/schema/contract tests,
and relevant rig/SVG/pose/QA/Remotion/visual-style skills. Prior local memory
helped locate the venv and warned about gates; current availability was checked live.
No existing SOURCE_MAP, feature spec, decisions, roadmap or worklog was overwritten.

Baseline character pipeline contracts: **7 PASS**. Live preflight: character tools
6/6, subtitles 2/2, audio processing 2/2, video post 8/9; Remotion and FFmpeg
available, HyperFrames npm resolution timeout. Initial TTS 0/11; Piper executable
exists in `.venv/bin` but is absent from PATH, and the local voice files are English.

## Implementation and visual revision

Created the source map before changes, then the feature spec. User revised the
look from stickman to simplified cartoon horror and supplied the reference path.
Inspected the image: large light face, compact simple cartoon, cool blue-gray
detailed room, broad irregular shadows. Authored original SVG apartment and Minh;
no tracing, screenshot reuse, logos, player controls or AI image/video calls.

Extended explicit timed actions and native Remotion package handoff in the
existing character tool. Added deterministic track/IK evaluation, cup ownership,
filled cartoon parts, independent apartment layers and per-clause captions/audio.
Added macOS speech provider and regressions; retained the existing generic path.

The first speech probe returned a WAV header with zero samples despite process
success. Fixed adapter validation. Speech works with authorized access outside
the sandbox. macOS also changed the displayed voice name to a decorated locale
name; exact locale plus unambiguous alias resolution handles both forms.
Measured real clause WAV durations: **2.076833 / 1.135208 / 1.071750 s**.

The first frame test caught unreachable leg targets; corrected the authored foot
tracks. The first MP4 showed raised elbows obscuring water and crossed knees;
corrected IK bend signs and re-rendered. V1 remains in `renders/review-v1.mp4`.
The final frames show the reach, water contact, cup inversion/rack placement,
withdrawal and bedroom entry. The same cup remains inverted at the ending.

## Verification

Commands (run from repository root):

```sh
.venv/bin/python -m pytest tests/tools/test_story_motion.py tests/tools/test_macos_say_tts.py tests/contracts/test_character_animation_pipeline.py tests/tools/test_subtitle_timestamps.py -q
remotion-composer/node_modules/.bin/tsc --noEmit --strict --esModuleInterop --jsx react-jsx --skipLibCheck --target ES2020 --moduleResolution node remotion-composer/projects/minh-cup-cartoon-pilot/index.tsx
ffprobe -v error -show_format -show_streams -of json projects/minh-cup-cartoon-pilot/renders/final.mp4
ffmpeg -v error -i projects/minh-cup-cartoon-pilot/renders/final.mp4 -f null -
git diff --check
```

Results: **23 tests PASS**, focused TypeScript check PASS, full decode PASS,
diff whitespace check PASS. All **14 canonical artifact schemas and 9 stage
checkpoints validate**. No full-repository test/build claim.
Tests evaluate 555 rendered-time states plus the analytic endpoint: bone length,
grip continuity, no prop jumps, washing-hand motion, planted-foot intervals and
cup immobility/inversion after release. Invalid/missing actions, bad targets,
keys and attachment boundaries fail closed.

Native `registry['video_compose'].execute(operation='render')` output:
`projects/minh-cup-cartoon-pilot/renders/final.mp4`, **1280×720, 30 fps, 555 video
frames, H.264/yuv420p, AAC**, container **18.56 s** (18.5 s picture plus AAC padding).
Final render tool call including built-in QC: **32.57 s**. Host verified
**Apple M4, 17,179,869,184 bytes RAM (16 GiB)**, two workers. Air chassis and peak
memory/thermal/long-story performance were not measured.

Rendered-pixel ROI frame deltas confirm visible motion in all four actions;
the cup region is stable after the actor clears it. Mean gray-pixel changes per
0.1 s: reach 4.93, wash 20.99, inversion/placement 12.84, walk 4.39; final cup
0.028. ROI tests complement, not replace, the seven action keyframes.

## Artifacts and limitations

- Feature/visual specification: `docs/features/story-to-action*.md`.
- Original reusable data/art: `examples/story-to-action/`.
- Run artifacts/checkpoints: `projects/minh-cup-cartoon-pilot/artifacts/` and
  `checkpoint_*.json`; decision log records pilot execution scope, not a claim
  that the user reviewed stage artwork or accepted the result.
- Measured narration, SRT: `assets/audio/`, `assets/subtitles.srt` under that run.
- Seven reviewed action frames: `renders/keyframes/` under that run.
- Built-in review incorrectly infers music presence and misses inline captions;
  retain its raw result, then correct the final review using known media inputs
  and visible rendered subtitles. Do not expand this task into dispatcher cleanup.
- Native board open timed out; production continued. Browser and speech need
  access outside the sandbox. HyperFrames remains unavailable in this environment.
- Gait is basic and the SVG texture is flatter than the painted reference.
  No word-level alignment, automated transcript comparison or manual listening
  pass is claimed. Human style/pronunciation acceptance remains pending.
- These are authored trajectories and reusable skeletal mechanics, not a general
  automatic narration-to-action planner. No full-story production was started.

Next step: user reviews this pilot, then parameterize the four action clips by
world anchors while keeping it as the regression fixture.

## Affected paths in this task

Modified existing source/docs: `PROJECT_CONTEXT.md`,
`tools/character/character_animation.py`,
`schemas/artifacts/decision_log.schema.json`.

Added source: `tools/character/story_motion.py`,
`tools/character/remotion/{motion.ts,Scene.tsx,index.tsx}`,
`tools/audio/macos_say_tts.py`.

Added tests: `tests/tools/test_story_motion.py`,
`tests/tools/test_macos_say_tts.py`.

Added authored example: `examples/story-to-action/{README.md,apartment.svg,
foreground.svg,pilot.motion.json,pilot.actions.json}`.

Added docs: `SOURCE_MAP.md`, `DECISIONS.md`, `ROADMAP.md`, `WORKLOG.md`,
`docs/features/story-to-action-animation.md`,
`docs/features/story-to-action-visual-style.md`.

Generated run files live only under `projects/minh-cup-cartoon-pilot/` and the
native composer staging directory. The user-supplied reference PNG was read,
not modified. Pre-existing dirty paths listed in the older audit remain outside
this change.

## 2026-10-21 — opening episode ("Có người ngủ dưới giường tôi")

User approved the pilot visual style, then supplied the story opening verbatim
(`examples/story-to-action/source_story_opening.md`; opening only). Re-read this
worklog, both feature specs and the implemented code; nothing restarted.

Narration: source split into 24 segments (`opening.narration.json`), concatenation
checked equal to the 18 paragraphs. `macos_say_tts` Linh vi_VN rate 145 (pilot
settings), run outside the sandbox. Measured speech **57.44 s**. Episode length
**80.3 s** (container 80.36 s): actions, holds and two fades; speech not sped up and
no text dropped, per user instruction. The ~60 s target is not reachable at this rate.

Implementation (see `docs/features/story-to-action-opening-episode.md`): backward-
compatible `motion.ts` (facing, face keys, attachments, nullable grip), Minh drawing
extracted to `Actor.tsx`, multi-shot `shots.ts`/`Episode.tsx` (`StoryEpisode`),
episode validator/packager and gait helpers in `story_motion.py`, `story_episode`
route in `CharacterRigRenderer`, local `procedural_sfx` tool, builder and Apartment v1
extension art. 11 shots: inserts, medium/close shots, pans, push-ins, fades.

Problems found by looking at actual frames and fixed:
- Cup appeared on the counter beside the basin while narration says "in the sink":
  cup moved into the basin (foot clipped by the near basin wall); episode copy of the
  pilot pickup re-targeted. Pilot fixture unchanged.
- First occluder layer covered Minh's body when he stood in front of the basin;
  replaced by a clip path applied to the cup only.
- Pulled and tucked chairs looked alike: tuck 36 px under the table, pull +120 px, −6°.
- Bottle insert defaulted chair/door state: now carries pulled chair and open door.
- Review finding: dried ring missing in Monday shots s02–s04 but shown in s05/s06;
  fixed, and the all-frame test now asserts the ring until the wash and never after.

Verification (repository root):

```sh
.venv/bin/python -m pytest tests/tools/test_story_motion.py tests/tools/test_story_episode.py tests/tools/test_macos_say_tts.py tests/contracts/test_character_animation_pipeline.py tests/tools/test_subtitle_timestamps.py -q -p no:cacheprovider
remotion-composer/node_modules/.bin/tsc --noEmit --strict --esModuleInterop --jsx react-jsx --skipLibCheck --target ES2020 --moduleResolution node <staged copy of tools/character/remotion>/index.tsx
ffprobe -v error -show_format -show_streams projects/minh-under-bed-opening/renders/final.mp4
ffmpeg -v error -i projects/minh-under-bed-opening/renders/final.mp4 -f null -
git diff --check
```

Results: **44 passed**; strict tsc PASS; full decode PASS; diff check PASS. Pilot
parity: six pilot frames (0–540) rendered with the old and new templates are
pixel-identical. Registry contract suites: 382 passed, 1 failed —
`test_phase3_contracts.py::test_registry_catalog_views` expects a TTS provider list
without `windows_sapi` (HEAD fe4157f) and `macos_say` (pilot task). Predates this
task; not changed here.

Render: registry `video_compose` → Remotion, two workers, 136.5 s; 1280×720, 30 fps,
2409 frames, H.264, AAC 48 kHz stereo, 16.5 MB, −17.7 LUFS integrated.
Scene-cut detection: 8 cuts exactly at the 8 hard shot boundaries, none elsewhere.
Narration windows median −19.7 dBFS RMS vs gaps −41.3 (loudest gap −30.2: footsteps).
26 keyframes in `projects/minh-under-bed-opening/renders/keyframes/` were inspected
against the narration. Built-in final review again claimed music; corrected (raw
kept). Narration↔action table: `artifacts/narration_action_timeline.md`.

Independent read-only review (DSS code review, separate agent): 0 🔴, 2 🟠, 5 🟡.
🟠 stain inconsistency fixed. Open: validator does not pre-check limb reachability per
frame (Remotion would throw at render); source-text check skipped when the key is
absent; negative/duplicate link and cue IDs; optional-field type checks; frame-grid
assumption for shot starts; ffmpeg stderr not surfaced; `story_episode` route does not
catch IndexError/jsonschema errors.

Not claimed: listening pass, pronunciation check, word-level alignment, ASR, human
acceptance of pacing/expressions/inverted-cup readability, peak memory.

## 2026-10-21 — story-to-video M1 (automatic story → MP4)

Request: new story → automatic analysis → scene/action timeline → OpenMontage animation →
MP4, one CLI command, local LLM allowed, no UI/Shorts, stop for review afterwards.
Re-read the pilot/opening docs and code first; reused rig, IK, walk, TTS, SFX, compose.
Source map and planned extension were appended to `SOURCE_MAP.md` before source changes.

Command: `.venv/bin/python scripts/story_to_video.py <story.md> [--analyzer auto|rules|ollama]`.
Design and contracts: `docs/features/story-to-video-pipeline.md`; decisions: `DECISIONS.md`.

Local LLM: no runtime was installed. Installed Ollama 0.40.7 (Homebrew), pulled
`qwen2.5:7b-instruct`, served on 127.0.0.1:11434 (started with `ollama serve`, still running).
Measured: labelling 71–81 s (vi, 21 beats), 47–49 s (en, 16 beats) on the M4. Replacing rule
labels with model labels was worse (vi: invented exits b03/b09, wrong boarding actor b17,
dropped disappearance b20). Merge is now fill-only; in the final runs the model confirmed
13/28 (vi) and 15/25 (en) rule actions, 6 and 3 of its extra actions were rejected as
ungrounded, 0 accepted. The LLM therefore did not change either final video.

Test stories (new, written for this run, never hand-built): `examples/story-to-video/stories/`
`chiec-o-mau-vang.vi.md` (vi) and `the-last-loaf.en.md` (en), plus an inline English story in
the tests (different names/rooms/props). A test asserts no story names appear in pipeline code.

Problems found by validation/frames and fixed:
- Walk at 170 px/s over-stretched the 115 px leg (validator: foot 115.6 at 4.933 s, before
  any render) → walks auto-slow per frame check; default 115 px/s.
- First Remotion attempt with concurrency 4 failed ("no response" from the bundle page);
  concurrency 2 works. Render/speech need access outside the command sandbox (as before).
- Draft frames: open umbrella at waist height → raised grip outdoors in rain, longer shaft;
  characters overlapping on "approach" → 125 px gap.
- Tests: names only at sentence starts (Mai, Tom) were missed (lowercased-word set bug);
  `give` lost its object ("gave him the box"); "and left" exit missing. Fixed.
- English final v1: Ben carried the newspaper all story (reading state lost across shots);
  the girl stayed off-frame at x=1350 in the street. Fixed: reading state on the person,
  dropped before the next body action or left where read; arrivals walk into frame; exits
  continue in the facing direction; "ran" exits at run speed; arrival time counts toward
  the action it serves (narration link).
- Org rule (no Vietnamese in code): Vietnamese vocabulary confined to the data file
  `tools/story/lexicon.py`; literals removed from analyzer/planner/CLI/tests. Behaviour
  check: regenerated timelines byte-identical to the rendered runs.

Verification (repository root):

```sh
.venv/bin/python -m pytest tests/tools/test_story_to_video.py tests/tools/test_story_motion.py tests/tools/test_story_episode.py tests/tools/test_macos_say_tts.py tests/contracts/test_character_animation_pipeline.py tests/tools/test_subtitle_timestamps.py -q -p no:cacheprovider
.venv/bin/python -m pytest tests/contracts -q -p no:cacheprovider
remotion-composer/node_modules/.bin/tsc --noEmit --strict --esModuleInterop --jsx react-jsx --skipLibCheck --target ES2020 --moduleResolution node <staged copy of tools/character/remotion>/index.tsx
git diff --check
```

Results: **76 passed** (24 new); contracts **1304 passed, 2 failed, 7 skipped** — both
pre-existing and outside this change: `test_registry_catalog_views` (TTS list, already noted
above) and `test_runtime_presentation_contract[footage-led-cinematic]` (untracked footage-led
pipeline from before this task). Strict tsc PASS. diff check PASS. Pilot/opening suites pass;
`motion.ts`, `Actor.tsx`, `Episode.tsx`, `shots.ts`, `Scene.tsx` unchanged.

Final renders (registry `video_compose` → Remotion, 2 workers, analyzer `auto`):

| | Vietnamese | English |
| --- | --- | --- |
| Output | `projects/chiec-o-mau-vang-vi-auto/renders/final.mp4` | `projects/the-last-loaf-en-auto/renders/final.mp4` |
| Picture | 1280×720, 30 fps, 3366 frames, H.264 yuvj420p | 1280×720, 30 fps, 2607 frames, H.264 yuvj420p |
| Audio | AAC 48 kHz, −17.9 LUFS, narration median −19.9 dB | AAC 48 kHz, −16.6 LUFS, narration median −18.5 dB |
| Duration (speech) | 112.3 s (72.4 s) | 87.0 s (43.1 s) |
| Plan | 9 shots, 21 beats, 35 actions, 150 cues | 9 shots, 16 beats, 27 actions, 202 cues |
| Pre-render validator | 3375 frames | 2616 frames |
| Full decode | PASS | PASS |
| Hard cuts detected / planned | 3/5 matched, 0 unplanned | 2/6 matched, 0 unplanned |
| Body-action windows with pixel change | 15/15 | 17/17 |
| Time (analyze/render/QA/total) | 71.5 / 192.9 / 5.9 / 270.7 s | 47.6 / 149.1 / 4.4 / 201.5 s |
| QA status | pass, 0 warnings | pass, 0 warnings |

Undetected planned cuts are same-room cuts whose frames differ too little for the scene
threshold, not missing cuts. All 37 beat keyframes (contact sheets in each `renders/`) were
looked at. Not claimed: listening pass, pronunciation, word alignment, ASR, human acceptance.

Still hardcoded / limits (M1):
- Vocabulary is closed: 36 actions, 8 location kinds, 16 prop kinds; verbs/props outside
  `lexicon.py` are ignored (beat becomes a camera hold). Vietnamese name detection relies on
  capitalisation; one location per kind per story; no lying down, crowds, fights, driving.
- One rig and body size for everyone (children are not smaller); identity by palette/hair.
- Same narrator voice for all speech; dialogue is shown by mouth flap only.
- Walk speed is rig-limited, so walk-heavy stories run long (en: 87 s video for 43 s speech).
- Visual issues seen in frames: characters overlap while talking/handing over in tight
  rooms; reveal close-ups can crop a character at the frame edge; a carried bag is never put
  down unless the text says so; an item the text never placed fades in at the hand
  (logged in `planner_notes`); umbrella lowers in front of the face during a talk gesture.
- `pix_fmt` is yuvj420p (Remotion default), not yuv420p as in the pilot render.
- Generated projects live under `projects/*-auto/` and are staged by `video_compose` into
  `remotion-composer/projects/<id>/`.

Next: user review of M1 (blocking). Next milestone not started.

## 2026-10-21 — story-to-video M1.1 quality pass

Request: fix six visual problems reported in the M1 MP4s with generic mechanisms, add
regression tests, re-render both stories with the same pipeline, verify in real frames.
M1 renders kept as `renders/m1-final.mp4`; before/after strips in each project's
`renders/review/` (`<issue>-before-after.png`, red = M1, green = M1.1).

Root causes (code read + plan data at the reported timestamps, see SOURCE_MAP M1.1):
1. Overlap EN 0:27–0:49 — staging: walking to a fixture ignored people standing there;
   pointing went through the person between pointer and window; no spacing rule anywhere.
2. Child as tall as adult — one rig size.
3. Hand-over EN 0:48–0:55 — 92 px apart, hands met for one instant, camera ≤ 1.55×.
4. Umbrella over the face VI 1:16 — measured: grip at (759, 516) = hip carry while the
   umbrella was open; `ShotBuilder` built poses before `weather` was assigned.
5. Boarding VI 1:20 — `board` = walk 100 px and fade out in front of a bus that was
   shorter than a person.
6. Sitting VI 1:36 — straight vertical drop, pelvis 9 px inside the cushion, feet slid.
7. Letter VI 1:45 — fixed 2× zoom on a 36 px item.
Found while fixing (validator / frames): spawned items started visible at (0, 0) and flew
to the hand (M1 EN tray crossed Ben's face); items on a shelf were drawn over faces; a
walker passed through a standing person; reveal close-ups were blocked by the observer;
two items rested at the same table spot (coin on the newspaper).

Fixes: see `docs/features/story-to-video-pipeline.md` (M1.1 capability table) and
`DECISIONS.md`. Validator gained: rig-space reach for scaled bodies, standing-still or
same-lane overlap (> 0.3 s, hand-over contacts exempt), held item/umbrella canopy+shaft over
a face (> 0.25 s), insert bounds. These rules caught the tray, shelf-bread and lane problems
before any render.

Verification (repository root):

```sh
.venv/bin/python -m pytest tests/tools/test_story_to_video.py tests/tools/test_story_motion.py tests/tools/test_story_episode.py tests/tools/test_macos_say_tts.py tests/contracts/test_character_animation_pipeline.py tests/tools/test_subtitle_timestamps.py -q -p no:cacheprovider
.venv/bin/python -m pytest tests/contracts -q -p no:cacheprovider
remotion-composer/node_modules/.bin/tsc --noEmit --strict ... <staged copy>/index.tsx
git diff --check
```

Results: **88 passed** (story-to-video file 36, of which 13 new quality regressions incl.
two control tests that rebuild with the M1 umbrella grip / without the depth lane and must
fail); contracts 1235 passed, 2 failed (same pre-existing failures as M1); strict tsc PASS;
diff check PASS. Pilot files (`motion.ts`, `Actor.tsx`, `Episode.tsx`, `shots.ts`,
`Scene.tsx`, `story_motion.py`, `examples/story-to-action/*`) not modified (mtimes predate
M1).

Final renders, same code for both (sha256 of pipeline sources before and after both runs:
`b2507a0c…2534`), analyzer `auto` (Ollama fill-only, 0 accepted, confirmed 14/28 and 15/25):

| | Vietnamese | English |
| --- | --- | --- |
| Output | `projects/chiec-o-mau-vang-vi-auto/renders/final.mp4` | `projects/the-last-loaf-en-auto/renders/final.mp4` |
| Picture / audio | 1280×720, 30 fps, 3722 frames, H.264; AAC, −18.0 LUFS | 1280×720, 30 fps, 2724 frames, H.264; AAC, −16.6 LUFS |
| Duration (M1 → M1.1) | 112.3 → 124.1 s | 87.0 → 90.9 s |
| Pre-render validator frames | 3731 | 2733 |
| QA | pass, decode OK, 0 warnings, 15/15 action windows move | pass, decode OK, 0 warnings, 17/17 |
| Time analyze / render / QA / total | 85.8 / 213.7 / 6.2 / 306.2 s | 48.3 / 155.8 / 4.5 / 209.1 s |

Frames checked in the final MP4s at the reported windows (strips in `renders/review/after/`):
no overlap 31.5–47 s EN; girl ≈ 0.72 of Ben's height; hand-over with both hands on the loaf
54.4–55.0 s; umbrella canopy above both heads, shaft clear of faces 78–79.5 s VI; boarding
87–94.4 s (door, step up, inside behind glass, bus leaves with him); sit 104.5–108.6 s (stop,
plant, hips back onto the cushion, bag set beside); letter 117–122 s (table close-up, then a
handwritten insert with the quoted words).

Still not right / limits:
- EN coin close-up (≈ 84–87 s): coin clearly framed beside the newspaper, but Ben's body
  still fills the left edge of the 3–4× frame (clearance = half frame + 60 px).
- Sitting has no torso lean or bent back (rig limitation); the hand-on-seat contact is
  brief and partly hidden by the body; a bag stays on the lap on narrow chairs.
- Bus is enlarged to fit a standing adult (not to real scale); a car cannot take a
  standing passenger (head would show above the roof).
- Depth lane is a 16 px offset, not a perspective scale; crossings read as "behind".
- Boarding and walking add time: VI is 11.8 s longer than M1 (speech 72.4 s).
- Staging is per action (no global blocking solver); three or more people in a small room
  can still crowd.
- No listening pass, pronunciation or human visual acceptance claimed.

# Windows story-to-video M1.1 compatibility — 2026-10-22

Baseline `coding` / `877a12b` verified; existing evidence/source-visual/FFmpeg WIP
preserved. Local dependencies installed in workspace venv; npm ci succeeded with
workspace cache. Native voice discovery distinguished Windows PowerShell Desktop
voices from PowerShell 7's additional Microsoft An vi-VN voice. Added offline
OS/language routing, provider-specific rates, PCM normalization, sample-measured
duration, provider/model/host/content-aware narration caching, analysis-only
`--dry-run` and accurate real-audio `--no-render` behavior. Renderer, Story Planner,
rig and both original fixture stories untouched. No paid calls, commits or M2.

EN Zira Desktop via Windows PowerShell: full 102.122667 s MP4, QA pass, 0 warnings.
VI Microsoft An via PowerShell 7: full 125.653333 s MP4, QA pass, 0 warnings.
All 37 sentence WAVs measured; subtitles exact; full decode clean; per-beat decoded
waveform sync residuals <=57.017 ms (two-frame technical tolerance; not zero).
User left pronunciation/listening review pending; no VI language-quality approval.

Clean baseline M1.1 suites 88 passed; extended focused suite 104 passed; final
native/local TTS regressions 21 passed. Contracts 1216 passed / 7 skipped after
correcting the stale exact-provider expectation. Strict template tsc and diff
check pass. Final combined unit/lib/contract run: 1967 passed, 8 skipped,
3 xfailed, 1 subtest passed (326.84 s); one SDK deprecation warning, no failures.
Full verification, output hashes, final combined test result and
remaining limits: `docs/WINDOWS_M11_HANDOFF_2026-10-22.md`.
Reusable PowerShell setup: `docs/WINDOWS_STORY_TO_VIDEO.md`.

## Windows Compatibility technical baseline finalization — 2026-10-22

The user reviewed the Windows VI image/technical result, accepted the Windows
Compatibility technical baseline, and authorized a scoped commit plus normal
push to `origin/coding`. Windows EN/VI rendering: **technical PASS**.
Vietnamese pronunciation: **pending human review**. macOS runtime regression:
**pending real-machine render**. M2 and broader creative approval are not implied.

Finalization starts at local/remote `877a12b`. Sixteen unrelated dirty/untracked
WIP files are excluded and protected by before/after checksums. The sixteen
Windows code/docs/tests files are the sole commit allowlist. No dependency,
cache, secret or generated MP4 is included. Final checks run against a clean
archive of the baseline overlaid with only those Windows files and reused local
dependencies; see the Windows handoff for final results and continuation steps.

Final clean-candidate `tests/tools tests/lib tests/contracts`: **1872 passed,
7 skipped, 3 xfailed, 1 subtest passed** in 317.01 s, with one SDK deprecation
warning and no failures. Both actual EN/VI `--no-render` checks and strict template
TypeScript passed on that candidate. The previous 1967-test result included WIP;
this release verification excludes it. Both original MP4 hashes, full decode,
measured narration/subtitle and waveform-sync checks passed again. All 16 WIP
checksums remain unchanged; the commit allowlist is only Python and Markdown.

## M1.2 Vietnamese narrative TTS listening evaluation — 2026-10-22

Verified `coding` / `5705e821c6914f1caef120bb1e756df87768251c`; read M1/M1.1
source/docs and Windows handoff. Ran an isolated CPU benchmark on Windows 11,
i5-12400 (6C/12T), 31.70 GiB RAM, Intel UHD 730, no NVIDIA/CUDA. Production
Python 3.14.5 unchanged; new SDKs use separate Python 3.11.16 venvs, wheel-only
installs without administrator/security changes. Public models fetched once;
inference used offline flags/socket guard, no hosted or paid API and no external
reference-audio cloning. Full source/model revisions, SHA256 and dependency
freezes are recorded in the ignored evaluation directory.

Same three original passages of “Chiếc ô màu vàng”, in original order and with
normalized_text identical to canonical, generated real WAVs with all providers:
- Microsoft An / SAPI via PowerShell 7, rate -1: 46.018 s speech, 3.715 s inference,
  RTF .081, sampled peak process-tree RSS 191 MiB.
- KorvaTTS 0.1.3 / hoang_nam / CPU ONNX / 32 steps / speed 1.05: 48.174 s speech,
  26.136 s inference, RTF .543, 563 MiB RSS.
- VieNeu 3.8.3 / v3 Turbo FP32 ONNX / Thanh Bình: 33.950 s speech,
  12.933 s inference, RTF .381, 1467 MiB RSS.

Model initialization is excluded from inference; An includes adapter/native host
and normalization costs. RSS is sampled, not a dedicated physical-memory/VRAM
measurement. Korva FLOAT values exceeded 1.0; benchmark export preserves FLOAT
and applies static headroom before PCM16, avoiding saturation without modifying
the SDK or production adapters. Final A/B/C clips are -20.2 LUFS, maximum .01 LUFS
error / highest -2.24 dBTP, no tempo/pitch/dynamics processing.

Listening bundle: `projects/m12-vietnamese-tts-review/review/INDEX.html`, A/B/C full
WAVs, per-passage ABC WAVs, original transcript, normalized_text, metadata, licenses,
technical CSV, score sheet and hash manifest. User replied **“Ưu tiên B”**;
B is Korva / hoang_nam. Recommend Korva for the next narrative listening round,
with commercial provenance still unresolved: publisher Apache-2.0 weights/styles
permission references PhoAudiobook, whose dataset terms restrict research/education.
VieNeu's pinned model FAQ explicitly allows monetized preset output and states
speaker consent; these are publisher statements, not independently audited contracts.
No detailed human pronunciation scores or full word-fidelity PASS claimed.
Optional local Whisper-small ASR differences are listening prompts, including
number-format artifacts, not confirmed TTS errors or an emotion ranking.

Final verification: 30 final WAVs full-decode clean; 24 PCM16 files have no extreme
samples; all transcript/source bytes and raw hashes match; listening links valid;
three isolated pip checks clean. Focused native/local/macOS-command regression
suite **21 passed in .81 s**. All 16 preexisting WIP hashes/status and 29 production/
story hashes unchanged; HEAD unchanged and index empty. Full renderer/typecheck
suites not rerun for this isolated evaluation. M1.1 runtime gates remain unchanged.
No production integration, staging, commit, push or M2. Only this worklog and
`docs/features/m1.2-vietnamese-narrative-tts-evaluation.md` are new visible docs;
benchmark scripts/models/audio stay Git ignored and require a separate local backup.

## M1.2 TTS acceptance-gate evidence — 2026-10-22

Reverified `coding` / `5705e821`; existing M1.2 WAVs and original transcript
retained. Rechecked current native/Piper narration contracts without changing
production code. Used offline, unprompted Whisper-small and Whisper-medium
(medium revision `08e178d48790749d25932bbc082711ddcfdfbc4f`) for full 3-passage
alignment: 141 original whitespace-separated Vietnamese tokens per provider,
846 alignment rows across A/B/C and both recognizers. Comparison-only expansion
of ASR 4/6/4h/6h removes previous number-format false deletion flags; canonical
and TTS normalized_text unchanged. Word timestamps/punctuation gaps and measured
pace are evidence for listening, not subjective pronunciation/emotion verdicts.

Saved 47 timestamped review candidates (A15/B5/C27), exact PCM snippets and a
local review/export page. No agent direct listening or confirmed error list is
claimed from ASR alone; related Whisper sizes can share biases. User replied
**“Đã nghe cả 5, chấp nhận được”** for the five specifically requested B/Korva
locations; these are ACCEPTABLE_TO_REVIEWER, with exact reply/scope recorded.
This supplements the earlier “Ưu tiên B” preference. Full-transcript/punctuation/
pace human acceptance and detailed A/C listening remain pending, not inferred.

Re-fetched exact-checkpoint/model/source licenses and pinned PhoAudiobook terms.
Verified Korva hoang_nam style hash and VieNeu Thanh Bình preset provenance:
the latter is bundled in SDK 3.8.3, byte-identical to pinned Apache source,
rather than a voice file loaded from the HF ONNX download. Korva's model grant
does not resolve upstream research/education restrictions or independently prove
speaker/output commercial permission. Drafted maintainer questions naming exact
checkpoint/preset and separate output/distribution obligations; **not sent**.
VieNeu remains the backup shortlist: explicit publisher monetized-output/consent
statement documented, no independent legal clearance. Source roadmap “personal
use” wording is logged for optional clarification, not treated as an NC license.

Acceptance report, timestamp CSV, licenses/draft and restore guide:
`projects/m12-vietnamese-tts-review/review/acceptance/`. Feature report updated.
Portable evidence backup is outside repository under workspace `backups/`:
`OpenMontage-M12-TTS-Acceptance-2026-10-22-v1.zip` with checksum/verification
sidecars. Payload includes WAVs, model/preset settings and hashes, reports,
source licenses, human feedback and replay scripts; excludes weights, venvs,
cache, secrets and unrelated WIP. Local verified archive only, not a claim of
off-machine backup or second-machine inference. Existing Windows baseline,
Story Planner and renderer remain unchanged. No commit/push, CLI integration
or M2. Final verification evidence is in acceptance-qa.json and backup sidecar.
Acceptance regression rerun: **21 passed in .74 s** (native/local narration and
macOS-command suites); no production code changed. No full renderer/typecheck
rerun claimed for this evidence-only follow-up.

## M1.2 Korva TTS provider integration — 2026-10-22

Verified `coding` / `5705e821`, WIP preserved (37 story/An-MP4/WIP hashes rechecked
unchanged). Added offline provider `korva_tts` (`tools/audio/korva_tts.py`) and the
Korva-side `tools/audio/korva_worker.py`, reusing the benchmarked
`korvatts.TTS(..., auto_download=False)` / `synthesize(...)` call inside the separate
Python 3.11.16 runtime over JSON lines; one model load per story. CLI:
`--tts-provider korva|auto`, `--korva-python`, `--korva-assets`; `--voice` = preset,
`--rate` = speed. Explicit Korva fails closed; auto prefers Korva only for Vietnamese
when installed. Cache key includes checkpoint/preset SHA256, SDK version, settings and
PCM export policy. Render report now carries `metadata.narration` (synthesis/load/gains).

Real-run iterations (evidence in ignored `projects/m12-korva-integration/`):
run 1 per-beat peak gain gave uneven levels → one static gain 0.6 (-1 dBFS ceiling);
leading silence (0.72 s) skewed verb timing → edge trim to 0.1 s pad; a trailing-burst
remover was added, then **reverted** after it cut real final words ("một mình") in the
second story (native-SDK ASR comparison). Final MP4s were rendered after the last change.

Results: `projects/m12-korva-chiec-o/renders/final.mp4` (21 beats, 64.53 s narration,
synthesis 49.31 s, load 2.32 s, RTF .76, MP4 118.42 s, total 175.6 s) and second story
(verbatim `source_story_opening.md` body, auto → Korva) `projects/m12-korva-second-story`
(18 beats, 52.84 s, RTF .79, MP4 73.69 s). Pipeline QA + independent QA PASS: text and
SRT equal source, 0 full-scale samples, full decode clean, beat waveform lag 30–57 ms
(same as An baseline 28–57 ms). Whisper-medium: story 1 0 omissions/insertions; story 2
flags 4 possibly omitted tokens in short sentences, also present in unmodified SDK output.
Tests: 23 new Korva tests; full suite rerun after final change (see log). No commit,
push, M2, or claim of publication-quality voice; human listening pending.

### M1.2 finalization — 2026-10-22

Finalized M1.2 Korva integration as technical baseline at the user's request: technical
PASS; Korva `hoang_nam` preferred Vietnamese provider; Windows SAPI / macOS Say / Piper
still selectable. Pronunciation and content fidelity pending human review; ASR
missing-word findings suspected, not confirmed; publisher declares Apache-2.0 while
dataset provenance stays uncertain; not publication quality-approved; M2 not started.
Pinned revision, file checksums, settings and reproduction commands are in
`docs/features/m1.2-korva-tts-integration.md`. Commit includes only M1.2 code/tests/docs;
other WIP left uncommitted, no weights/venvs/caches/audio/MP4. Verified from a clean
worktree of the commit before a normal push to `origin/coding`.

## M2.1 Canonical Master Story Package — 2026-10-22

Baseline `coding` / `5316fe9`. Read source map, roadmap, decisions, worklog, feature
specs, the uncommitted Evidence Canon / source-visual WIP and the local Lead Masks
pilot (`projects/lead-masks-1966-pilot`). SOURCE_MAP updated before implementation.
Added standalone `schemas/story/{master_story_package,format_plan}.schema.json`,
`lib/master_story.py` (validate + resolve CLI) and `tests/lib/test_master_story.py`.
WIP files, pipeline, renderer, Korva and `schemas/artifacts/*` untouched.

Pilot `examples/master-story/lead-masks-1966/master_story.json` (STORY_053@v1): 15
sources, 38 claims across all six statuses, 7 events, 17 entities, 11 continuity
rules, 45 segments; Short 6 segments ≈50.8 s (9:16), Long 45 ≈426.6 s (16:9). Claims
and narration copied verbatim (script-checked). Re-fetched 2026-10-22: SRC_001/002/003/010
consistent with claims; SRC_009 (Globo) unreachable by the tool; the rest keep the
2026-10-13 pilot inspection. SRC_002 spells "Manuel" → rule CR_007.
Tests: 25 passed; one validator crash on an incomplete rule found by a test and fixed.
Not committed; pending user review.

## M2.2 Canonical Short narration proof — 2026-10-22

Confirmed M2.1 uncommitted; hashed and archived all 28 uncommitted files before work
(`projects/m22-short-proof/logs/`). Added `lib/master_story_short.py`,
`scripts/master_story_short.py`, `schemas/story/timed_format_manifest.schema.json`,
`tests/lib/test_master_story_short.py` (18). Reused the M1.2 voice selector, cached
`narrate()` and `subtitle_gen`; no analyzer/planner/renderer/media changes.

STORY 053 Short (language vi → Korva `hoang_nam`, auto): 6 segments in order, text
verbatim, 11 claims / 11 sources unchanged, continuity intact, 21 sentence SRT cues
aligned, real WAVs measured by samples. Speech 69.88 s, total 72.68 s: **duration gate
FAIL, 12.68 s over 60 s** (SEG_45 13.50 s, SEG_23 12.62 s, SEG_01 12.23 s); not cut or
sped up. Korva is 30–45 % longer than the V2 Piper estimates. First run also exposed a
subtitle merge (one cue for the whole Short) — caught by the gate, fixed with
`max_words_per_cue=1`. ASR warnings only; SEG_07 "missing names" was an ASR miss (the
sentence is audible; confirmed with a second model and a clipped pass).
Research brief 17 sources vs package 15: SRC_016/017 visual-context files, no claims.
Not committed; approvals pending.

## M2.2.1 Short duration fix through canonical selection — 2026-10-22

Hashed/archived all 31 uncommitted files first (`projects/m221-short-selection/logs/`).
Synthesized all 45 master segments once with Korva `hoang_nam` (production selector and
cache) to compare candidates on measured audio (10.0–14.3 s each). Evaluated six options
(A–F) for coherence, qualifier/continuity risk and measured duration. Chose B: SEG_01,
SEG_02, SEG_19, SEG_45 → speech 47.496 s, total **49.496 s; all 7 gates PASS** (4 beats,
verbatim, same 11 claims/11 sources, CR_001 satisfied, audio measured, 14 SRT cues).
Rejected the in-band options C/F (capsule note never introduced) and the 59.7–59.9 s
options (fragile margin). Only `formats.short` changed (JSON diff: Long and narrative
identical); package stays `v1`. Validator: estimated duration is now an advisory warning.
Continuity gate lists human-review rules as pending. A first draft of the search note
over-claimed ("no in-band combination keeps capsule and masks"); recomputed and corrected
to "every in-band combination omits SEG_02". ASR warnings only (digits for 1966/18h30;
"Niterói" heard as "nito ở"). No speed change, media, commit, push or M2.3.

### M2.1 + M2.2 finalization — 2026-10-22

User approved the M2.2.1 editorial decisions (SEG_01/02/19/45, 49.496 s, no pause
extension, Korva 1.05, victim names unspoken). Rechecked package validation, timed
manifest schema, all 7 gates recomputed from artifacts, WAV/track hashes and resolved
Short (11 claims / 11 sources). Full suite 2094 passed, 12 skipped, 3 xfailed. Committed
only M2 source, schemas, tests, docs and the canonical example JSON; WIP, `projects/`
outputs, evaluation helpers, models, venvs and caches excluded. CR_006/007/008/010 and
listening/factual/publication approvals remain pending. M2.3 not started.

## M2.3 Canonical Visual Scene Planning — 2026-10-22

Verified `coding` / `c103533d`; read canonical M2.1/M2.2 source, contracts, current
planner/renderer/media/quality interfaces and project docs. Updated root SOURCE_MAP
before code changes. Snapshot protects 16 preexisting WIP files, 51 source files
and all 53 existing Short artifacts; WIP inspected read-only, not imported/merged.

Added standalone visual schema with shared brief definitions, deterministic
`lib/visual_scene_plan.py`, a read-only-input CLI and an authored STORY 053 visual
brief. Directions reference cue groups, canonical claims/entities/events and shot
intent, not story-specific Python logic. Exact narration character spans and
six-state claim/status/qualifier/source records are preserved. Pending approvals
and CR_006/007/008/010 cannot be promoted by the contract. All asset requirements
remain unresolved with no invented media path, URL or license metadata.

Pilot `projects/m23-visual-plan/pilot/`: 11 scenes / 11 unresolved requests,
0–49.496375 s, 4 canonical segments, 11 claims, 11 sources. Three intended
authentic-evidence shots, one contextual shot, seven labelled illustrations;
no media acquired/generated. Masks are not worn as an established placement,
wardrobe is not identical, source name spelling is preserved, local imagery
is context, and the capsule instruction is not depicted as a performed action.
No cause of death is asserted. Source transcripts do not imply possession of
original document images. Existing local-media rights labels were inspected
as metadata only, not adopted as new clearance.

SRT interior cuts remain character-distributed estimates. The first shot covers
lead-in; previous shots hold through gaps; the final shot covers existing tail.
No narration rewrite, pause extension, resynthesis, Short selection change or
word-alignment claim. Five outputs: plan JSON, complete storyboard table, asset
requirements, continuity review and validation report. CLI verifies six existing
file hashes/five measured WAVs and all seven M2.2 gates before writing outputs.

New tests: 62 passed (generic English story, deterministic/no input mutation,
refs, timing/gaps/overlaps, canon/narration/SRT drift, unresolved assets, pending
reviews, no Long execution). Focused M2/TTS/Korva/StoryVideo regressions: 187 passed.
Feature spec: `docs/features/m2.3-canonical-visual-scene-planning.md`.
Clean-candidate checks/preservation evidence follow under the same project.
No Story Planner, Remotion, Korva or old WIP changes. No asset resolution,
image/video generation/render, paid dependency, commit/push or M2.4.

Final M2.3 checks: WIP-free baseline archive plus only the ten M2.3 files ran
`pytest tests -q`: 2059 passed, 11 skipped, 3 xfailed, 1 subtest passed; two old
all-frame TS evaluator tests failed because the archive lacked node_modules/
typescript. Reused the existing local TypeScript package in the candidate and
reran those two: 2 passed in .70 s. Aggregate 2061 passed across full run/recheck,
not a second full run. No renderer/source fix or dependency installation. Full
failure log and successful recheck retained under verification. Existing SDK
deprecation warning only. Both actual pilot runs (worktree and clean candidate)
have five byte-identical exports. All 16 WIP hashes/status, 51 protected sources,
53 Short artifacts and HEAD preserved; index empty. Schema/whitespace checks pass.
Human storyboard/factual/listening/publication approval remains pending.

## M2.3.1 Editorial Storyboard Refinement — 2026-10-22

Verified `coding` / `c103533d`; inspected actual M2.3 source and all five exports,
tests, M2.1/M2.2 contracts and control documents. Backed up all 26 initial changed
files plus original M2.3 exports before editing. No resets/merges/staging.

Revised SC_002/004/005 to select explicitly labelled local digest/conceptual-mask/
note-transcription treatments; original historical image requests remain conditional
external alternatives requiring separate provenance/license/editorial decisions.
No fabricated archive, precise mask geometry/placement or false possession of a
note image. SC_008 now isolated unknown typography, SC_009 four questions replacing
one another in a single two-line slot, SC_010 a graphic empty-field visual breath.
SC_001/003/006/007/011 unchanged as full scene objects; SC_006 still visibly labels
18:30 as transcribed instruction, not confirmed ingestion. Same 11 shot IDs,
49.496375 s and exact narration/claim/entity/event/source mapping.

Optional existing-contract metadata separates 1 current external context request,
3 conditional historical alternatives and 10 local specs (3 are conditional
fallbacks, not extra assets). No reconstruction requests, supported local recipes
or resolved assets. Vertical geometry checks reserve subtitle space, prevent
simultaneous questions/text collisions and check planned contrast. Actual Arial
font metrics pass for all 17 specified text blocks without generating an image;
mobile human reading/rendered quality and font/asset rights are not auto-approved.

M2.1–M2.3 canonical suites: 127 passed (82 visual incl. 20 added editorial cases).
Old M2.3 plan still validates; real narration/SRT hashes and seven M2.2 gates pass.
Outputs: `projects/m231-editorial/pilot/`; before/after, production breakdown,
preservation/font metrics and test logs under the same project. Feature:
`docs/features/m2.3.1-editorial-storyboard-refinement.md`.
All CR_006/007/008/010 and factual/publication/license approvals pending.
No Korva/audio/Story Planner/renderer/WIP changes, media generation/render,
M2.4, commit or push.

Final M2.3.1 checks: relevant regressions 209 passed in 18.81 s (includes the 127
M2.1–M2.3 cases, TTS/Story-to-Video and two all-frame TypeScript continuity
evaluators). Contract suite 1217 passed, 7 skipped in 172.82 s; one existing
Google SDK Python deprecation warning. Worktree runs, not a full-suite rerun or
macOS runtime render. Logs preserved under `verification/`. Final preservation
and schema/whitespace checks recorded there; factual/publication/license and
mobile human-review gates remain pending.

## M2.3 + M2.3.1 editorial baseline finalization — 2026-10-22

User approved editorial progression to M2.4 subject to four attribution/presentation
corrections and explicitly authorized normal commit/push. Verified branch coding,
local and origin/coding at c103533d0993623ff7a9d971bd3b8e9ae2cc4739 before edits.
Backed up all twelve intended source/test/doc files under projects/m23-finalization/.

SC_001 now identifies the proposed 1892 Niterói painting as context_art, distinct
from photography and story date 1966; no file possession or license clearance.
SC_002 separately maps Boletim 535 [SRC_001], Laudo 29.375 [SRC_002], Diário de
Notícias [SRC_004]. SC_005 separately identifies SRC_001/004/009 and visibly
retains SRC_009's unavailable verification, leaving the canonical unreachable
record untouched. SC_010's Nhịp dừng biên tập is internal production metadata;
no on_screen_text or text_blocks. Constrained visual_pause allows that local
flat field without weakening evidence labels on depicted historical content.

Only those four directions differ from the M2.3.1 checkpoint; seven complete
scene objects unchanged. All 11 scene IDs, 49.496375 s, exact narration/canon/
claims/sources/statuses and Short selection preserved. Prior approved SC_001
hashes retained in fixture beside the authorized correction reason/current lock.
SC_006 still explicitly identifies 18:30 as a written instruction, not ingestion.

Final regressions: 215 passed in 19.47 s, including 133 M2.1–M2.3 cases plus
TTS/Korva/Story-to-Video and the two all-frame TS continuity evaluator tests.
WIP-free c103533d archive overlaid with only the twelve intended files: 133
canonical cases passed in 8.22 s. All five exports are byte-identical across two
worktree runs and the clean candidate's real-input run. Asset export matches
plan; six actual input hashes, five WAV measurements and seven M2.2 gates pass.
Sixteen final text blocks fit installed Arial metrics; no image generated.
Schema/scoped whitespace and preservation checks pass. Logs/evidence live in
projects/m23-finalization/verification/; no new full-suite/contract-suite rerun.

Precise M2.4 input contract added to the M2.3.1 feature report, including audio
bundle transfer/absolute-path caveat, bound content hashes and separate future
resolved-asset output. Inventory stays 11 unresolved primary requests plus 3
conditional external alternatives; 10 local specs include 3 fallbacks, with 0
implemented recipes. CR_006/007/008/010, factual/licensing/publication and rendered
mobile review pending. Editorial progression approval is not license clearance.

Commit scope: exactly twelve M2.3/M2.3.1 files. All sixteen unrelated WIP files,
51 protected sources and 53 existing Short artifacts retain original hashes;
generated outputs/models/media/environments/caches excluded. No M2.4 work,
media acquisition/generation or renderer/Story Planner/TTS change.

## Product identity locked: Stickman Horror — 2026-10-22

User explicitly selected an Automated Stickman Horror Video Production System.
Previous M2.3 Documentary Motion Graphics direction was an unauthorized design
deviation; the previous documentary-oriented M2.4 prompt is cancelled, and that
resolver is not authorized for implementation/continuation. Earlier entries are
preserved as history, not current product authorization. No historical facts or
publication rights are automatically approved by this decision.

Verified branch `coding`, HEAD `be736a47dcdcbb7bcfcff8052cf7692741f789af` and 27
pre-existing changed paths before editing. Read AGENTS/AGENT_GUIDE, shared
context, decisions, roadmap, source map, this worklog and architecture; PROJECT.md
did not exist. Saved exact before-copies of the five edited existing documents,
all initial WIP files, Git status/index/HEAD and 9,272 file hashes (repository
sources and existing M2 project artifacts) under
`projects/product-identity-lock-2026-10-22/` (Git ignored).

Inspected M1/M1.1 source: motion.ts IK/tracks, shared Actor artwork, story planner,
procedural locations, StoryVideo composition/validator and character renderer
package route. Mechanics support reuse; the existing filled-cartoon artwork,
fixed 1280×720 compositions and M1 action-driven timeline extension require
assessment for the fixed-timing vertical STORY 053 Short. No new renderer
capability or runtime render is claimed.

Created [PROJECT.md](PROJECT.md) with identity, visual requirements/exclusions,
content, full product flow, shared Short/Long canon, zero mandatory paid credits,
source-first priorities, inspected reuse boundaries and the next task. Updated
PROJECT_CONTEXT.md and AGENT_GUIDE.md entry guidance; added the explicit decision
and a current roadmap section above the untouched historical roadmap. M2.1 and
M2.2 remain completed/valid; M2.3 is technically complete with reusable canonical
refs/timings, but needs Stickman Horror visual correction before M2.4.

Next milestone is inspect/map the existing Stickman Animation renderer against
STORY 053's eleven scenes, producing a capability/gap map without implementing
it here. Architecture contains unrelated uncommitted WIP and is unchanged; its
future product-contract reference is an explicit dependency after reconciliation.

Affected documentation only: PROJECT.md, PROJECT_CONTEXT.md, AGENT_GUIDE.md,
DECISIONS.md, ROADMAP.md and this WORKLOG.md. No media generation, renderer/code,
narration/claims, Master Story Package, storyboard JSON/timestamps, M2.4 execution,
staging, commit or push. Validation checks local Markdown links/anchors, entry
discovery, exact before-to-after diff, whitespace, preserved WIP and input hashes.
Application tests/renders are not run for this documentation-only change.

Verification PASS: 26 local Markdown links/anchors resolve; the agent entry route
reaches PROJECT.md; existing-document edits contain additions only. All 9,267
protected files outside the five edited existing documents retain their hashes,
including all 24 pre-existing WIP files outside this edit scope and architecture.
All 27 initial WIP status entries, branch, HEAD and Git index are unchanged.
STORY 053 references match SC_001–SC_011. Whitespace checks pass. Exact scoped
before-to-after diff: `projects/product-identity-lock-2026-10-22/product-identity-lock.diff`;
machine-readable verification: `projects/product-identity-lock-2026-10-22/validation.json`.
