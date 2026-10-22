# Decisions — Story-to-Action pilot (2026-10-21)

## M1.2 Korva TTS integration (2026-10-22)

- Integrate the user-preferred M1.2 voice (Korva `hoang_nam`) as local provider
  `korva_tts`; no other TTS model added. Baseline `coding` / `5705e821`; existing
  WIP, Story Planner, renderer, Remotion and stories unchanged.
- KorvaTTS runs in its own interpreter (benchmark: CPython 3.11.16, korvatts 0.1.3,
  onnxruntime 1.31.0); OpenMontage stays on Python 3.14. Never import `korvatts` in
  the pipeline process: `korva_worker.py` runs in the Korva runtime and speaks JSON
  lines over stdin/stdout. Native-library stdout is redirected to stderr so it
  cannot corrupt the protocol. One worker (one model load) per story via
  `KorvaTTS.session()`; single `execute()` calls start and stop their own worker.
- Inference call is the benchmarked one: `TTS(assets_dir, device="cpu",
  auto_download=False, num_threads)`, `synthesize(text, voice, lang="vi",
  total_steps=32, speed=1.05, silence_between_chunks=0.3, seed=20261022)`. The SDK's
  own sentence chunker keeps chunk order; canonical text and subtitles are untouched.
- Discovery never downloads: CLI flag → `OPENMONTAGE_KORVA_PYTHON` /
  `OPENMONTAGE_KORVA_ASSETS` (or SDK `KORVATTS_ASSETS_DIR`) → M1.2 benchmark install
  location / Hugging Face caches, preferring pinned revision `e5c8c218`. Explicit
  paths never fall through. Worker uses HF offline flags and a socket guard.
- Only bundled presets (`voice_styles/<name>.json`) are accepted; no reference audio
  or voice cloning. Default `hoang_nam`; other bundled presets were not evaluated.
- Vietnamese only. `auto` puts Korva first for `vi` only when a Korva install is
  found, then the native voice, then Piper; English selection is unchanged.
  Explicit `--tts-provider korva` fails closed — no switch to Microsoft An.
- Cache key adds checkpoint SHA256 (all ONNX/config files), preset SHA256, SDK
  version, synthesis settings, runtime paths and the worker's PCM export policy.
  `auto_skipped` diagnostics are excluded so they cannot invalidate audio.
- PCM export: Korva float output peaks above 1.0. One static gain 0.6 for every
  beat (consistent level), lowered only for a beat whose peak would exceed -1 dBFS.
  No limiter/compressor/tempo/pitch change. Edge silence below -45 dBFS is trimmed
  to a 0.1 s pad because leading silence skews the planner's verb-to-time mapping.
- Rejected after real-run evidence: dropping a "detached trailing burst" after a
  pause. On the second story it removed real final words ("một mình"). Short loud
  tail segments are now always kept; a residual vocoder click is a listening item.
- Measured, not estimated: duration = PCM16 sample count after FFmpeg mono 24 kHz
  normalization. Render report records model, preset, hashes and synthesis metrics.
- Licensing is recorded, not a technical blocker: publisher states Apache-2.0 for
  code/weights/styles; PhoAudiobook training-data commercial rights and preset
  speaker consent are not independently verified. No maintainer message sent.

### Finalization (2026-10-22)

- User asked to finalize M1.2 integration as the technical baseline and push to
  `origin/coding` (normal push, no force). Status: technical PASS; Korva `hoang_nam`
  preferred for Vietnamese; pronunciation/content fidelity pending human review;
  ASR missing-word findings suspected, not confirmed; licensing as above; M2 not started.
- Commit only M1.2 code/tests/docs (incl. the M1.2 evaluation report and worklog
  entries). Footage-led/evidence-canon/FFmpeg/schema/ARCHITECTURE WIP stays
  uncommitted. No weights, runtimes, caches, audio or MP4 in Git.

## Windows compatibility extension (2026-10-22)

- User explicitly authorized local M1.1 fixture narration/render/test runs; human
  visual and pronunciation acceptance remain separate. Initial scope excluded
  commit/push; the finalization decision below supersedes that restriction.
- Build on `coding` baseline `877a12b`; preserve pre-existing evidence/footage/FFmpeg WIP.
  Keep existing Story Planner, source stories, rig and Remotion renderer unchanged.
- Use the installed native OS voice when its actual engine inventory matches the
  language. Windows PowerShell 5.1 exposes fewer voices than PowerShell 7 here;
  enumerate both and synthesize with the host that exposed the selected voice.
  No registry edits, admin changes or paid/network TTS fallback.
- macOS keeps Linh 145 WPM / Samantha 165 WPM. Windows SAPI uses its own -10..10
  scale (default -1); never forward macOS WPM. Piper uses explicit local model
  metadata and length_scale; no model auto-download or English substitution.
- Normalize SAPI/Piper to the existing mono 24 kHz PCM16 narration contract.
  Remeasure actual samples, including cache hits; provider, model/config hashes,
  host, settings and WAV content protect against stale cached timing.
- Keep `--no-render` as the real-audio packaging check. Add separate analysis-only
  `--dry-run`, with no timing claim or generated action timeline. This resolves
  the misleading historical suggestion that no-render works without macOS TTS.
- Update the stale exact-provider contract expectation to include both existing
  local native providers. Do not loosen it to a subset or change paid-provider routing.
- Browser: reuse installed Chrome via the existing environment override; keep
  Remotion 4.0.484/concurrency 2. SFX remain local procedural FFmpeg; no music added.

### Technical baseline acceptance and publication (2026-10-22)

- The user reviewed the Windows Vietnamese video's image/technical result and
  explicitly accepted Windows Compatibility as a technical baseline, authorizing
  a scoped commit and normal push to `origin/coding`, with remote/local HEAD check.
- Windows EN/VI rendering: **technical PASS**. Vietnamese pronunciation:
  **pending human review**. macOS runtime regression: **pending real-machine render**.
  Passing mocks does not replace a Mac render. No M2 or additional renderer/planner work.
- Commit only the Windows code, tests and documentation. Keep unrelated WIP,
  secrets, dependencies, caches, generated projects and large MP4s outside the commit.
- Final checks use a clean source candidate (baseline plus only the Windows file
  allowlist), so preservation of WIP does not make it an implicit dependency.

## Pilot decisions (historical)

- Scope: one authored scene through local render/validation, as explicitly
  requested. No full-story generation, MoneyPrinter, upload or publish work.
- Preserve existing dirty cinematic/footage-led/surveillance changes on `coding`.
- Reuse `character-animation` and `video_compose`; extend its existing character
  compiler/renderer handoff rather than introducing another render engine.
- Select Remotion: installed, cached Chrome, deterministic frames, audio and
  captions. HyperFrames preflight timed out; FFmpeg remains encoding/QC only.
- Visual direction revised by the user: pure stickman → original simplified
  cartoon. Inspect supplied `docs/references/openmontage_style_reference.png`;
  reuse hierarchy, cool palette and environment detail, not artwork or identity.
- Use authored world-space tracks, fixed-length two-bone IK and cup-handle
  attachment. The pilot fixture, not free-text inference, controls the actions.
- Use native macOS Linh vi_VN for zero-cost local speech. Add a provider matching
  the existing SAPI pattern; fail if the voice/locale or real audio is absent.
- Narration and captions align by measured clauses. Word-level forced alignment
  and pronunciation review are not claimed. No music in this diagnostic pilot.
- The guide requires an `approval_policy` decision but its schema did not allow
  that category. Add the category, without weakening checkpoint enforcement.
  Record the user's explicit pilot execution scope; final human review is pending.
- Final picture was revised after actual frames revealed raised elbows hiding
  water and crossed knees. Keep fixed IK bend directions instead of changing the
  renderer, hiding the shot or removing an action.

# Decisions — opening episode (2026-10-21)

- Source of truth: user-supplied opening text saved verbatim; validator requires the
  narration segments to concatenate to it exactly. No added events.
- Length: measured speech is 57.44 s at the pilot voice/rate, so ~60 s is not reachable
  without speeding speech or dropping text, both forbidden by the user. Result 80.3 s.
- Keep Remotion (user named it); HyperFrames now resolves but would mean redesigning the
  rig. Logged with both options in the run decision log.
- One persistent world instead of per-shot redraws: shots are time/camera/light views;
  object state (cup, chairs, fridge) persists and is tested on every frame.
- Apartment v1 files untouched; new rooms are adjacent SVG panels in the same palette.
- Pilot fixture untouched; the episode adapts a copy (cup in the basin, not on the
  counter) because the story says the cup was in the sink. Inversion readability is
  fixed in the episode cup drawing and camera, not by changing pilot motion.
- No music; local procedural SFX via a new FFmpeg tool (no paid or networked source).
- Captions/SRT per measured segment; `subtitle_gen` is called per segment because it
  merges adjacent segments into one cue.

# Decisions — story-to-video M1 (2026-10-21)

- Scope (user): new story → automatic analysis → scene/action timeline → OpenMontage
  animation → MP4, one CLI command, local only. No UI, no Shorts, no next milestone.
- Single CLI despite the agent-first architecture: the user asked for one command. The
  script only sequences registered tools and writes canonical artifacts; it holds no
  creative decisions of its own.
- Narration text = deterministic segmentation of the source, validated for exact match.
  Neither rules nor the LLM may rewrite the story.
- Rules are primary, the LLM is fill-only. Evidence: with `qwen2.5:7b-instruct` labels
  replacing rule labels, the Vietnamese story got invented exits (b03, b09), the boarding
  actor swapped to the wrong character (b17) and the disappearance dropped (b20). English
  agreement with rule actions was 15/25. Recorded in each run's `story_analysis.json`.
- Ollama 0.40.7 installed with Homebrew and `qwen2.5:7b-instruct` (~4.7 GB) pulled for
  this milestone; the pipeline runs without them (`--analyzer rules` / auto fallback).
- Reuse the v1 rig (`motion.ts` IK + `Actor.tsx`) for every character; differentiate by
  palette, clothing colour from text, long hair, grey hair for elders. No new rig.
- Facing is a step track evaluated per frame in `StoryVideo.tsx` (motion.ts unchanged).
- Procedural original backgrounds per location kind instead of per-story art; static SVG,
  movable things drawn by the composition.
- Walk speed is limited by the rig: `walk()` slows down until no planted foot exceeds the
  leg span (first plan at 170 px/s failed validation: foot 115.6 px > 115).
- Remotion render (headless Chrome + localhost) and macOS speech need access outside the
  command sandbox, as already recorded for the pilot.

# Decisions — story-to-video M1.1 quality pass (2026-10-21)

- Fix classes, not the two stories: every change is a planner/renderer/validator rule that
  applies to any story; the same code rendered both videos (source hash in WORKLOG).
- Children are the same rig scaled 0.72 about the ground line. Tracks stay in world space;
  renderer and validator map world→rig per frame (affine, so interpolation is exact).
- Staging rules: a person standing where someone must go steps aside; a gesture never goes
  through a person (the gesturer steps back first); speakers and listeners face each other.
  The validator rejects two people standing still inside each other (> 0.3 s) unless a
  hand-over contact is declared, and any held item covering a face (> 0.25 s).
- Hand-over = approach to arm's length, both hands meet on the item, 0.5 s shared hold,
  switch while both touch, receiver draws it in; camera pushes to ≥ 1.9×.
- Boarding = walk to the open door, step up, step in behind the body (seen through door and
  windows), doors close, the vehicle leaves with the passenger. The bus was enlarged so an
  adult fits inside (it is not to real scale; a car still cannot take a standing passenger).
- Sitting = stop in front, plant feet, hips back and down with a hand on the seat edge,
  pelvis on the surface. A carried bag/box/tray is set on a wide seat beside the sitter
  (staging; logged in planner_notes and the timeline as `put_down`). Not done on chairs.
- Close-ups are sized from the item (largest dimension, visual centre). Written items with
  quoted words in the same sentence get a full-frame insert showing exactly those words in
  a handwriting font. No words are added.
- Items resting on wall furniture are drawn behind people; held items between body and hands.
