# Story-to-Action roadmap

- [x] Recover checkout context and preserve pre-existing work.
- [x] Document source map and scoped feature/visual contracts.
- [x] Original cartoon Minh, detailed fixed apartment and one persistent cup.
- [x] Explicit four-action timeline, physical grip, wash, inversion/release, walk.
- [x] Local Vietnamese narration and clause subtitles through native composition.
- [x] Native MP4, all-frame mathematical checks, decode and actual-frame review.
- [x] User approved pilot visual style (2026-10-21). Gait, narration pacing and
      pronunciation not yet stated as approved.
- [x] Opening episode (~80 s, 11 shots) of the supplied story opening, reusing the
      pilot wash, with camera moves, expressions, SFX and narration→action links.
- [ ] User review of the opening: pacing (80 s vs ~60 s target), inverted-cup
      readability, expressions, SFX balance, pronunciation.
- [ ] Next: parameterize reach/open/walk clips against named world anchors
      (walk is parameterized; pickup/fridge reach are still authored keys).
- [x] Story-to-video M1 (2026-10-21): `scripts/story_to_video.py <story>` — automatic
      analysis (rules + optional local Ollama), shot/action planning, narration, SFX,
      Remotion render, QA. Tested on two new stories (vi, en) + an inline test story.
- [x] M1.1 quality pass (2026-10-21): staging/spacing, child scale, hand-over, boarding,
      sitting, prop-face occlusion, size-aware close-ups, written-item inserts, depth lane,
      surface slots; validator rules + 13 regression tests; both stories re-rendered.
- [ ] **User review of M1.1 results (blocking).** Do not start the next milestone before it.
- [x] Windows M1.1 compatibility: offline native/Piper routing, measured WAVs,
      analysis-only dry-run, PowerShell setup and Windows EN/VI rendering:
      **technical PASS; technical baseline accepted by the user on 2026-10-22**.
- [ ] Vietnamese pronunciation: **pending human review**.
- [ ] macOS runtime regression: **pending real-machine render**; mocked regressions pass.
- Windows VI image/technical review was accepted for compatibility only. Broader
  M1.1 creative approval is not inferred; M2 was unstarted at that checkpoint
  (current M2 status below). See
  `docs/WINDOWS_M11_HANDOFF_2026-10-22.md`.
- [x] M1.2 TTS evaluation (2026-10-22): user preferred Korva `hoang_nam`.
- [x] M1.2 Korva integration (2026-10-22): local offline provider `korva_tts` in the
      generic CLI (`--tts-provider korva`, auto for Vietnamese when installed); real
      MP4s `projects/m12-korva-chiec-o` and `projects/m12-korva-second-story`:
      **technical PASS**. See `docs/features/m1.2-korva-tts-integration.md`.
- [x] M1.2 finalized as technical baseline and pushed to `origin/coding` (2026-10-22).
      Korva `hoang_nam` is the preferred Vietnamese provider; SAPI/macOS Say/Piper
      remain selectable.
- [ ] **Human review of Korva pronunciation/content fidelity (blocking publication)**,
      incl. ASR-flagged *suspected, unconfirmed* omissions in short sentences and the
      b09 tail burst. Not publication quality-approved.
- [ ] Korva commercial-use clarification: publisher declares Apache-2.0; PhoAudiobook
      dataset provenance / preset consent uncertain — not a technical blocker.
- [ ] M2 Short + Long from one researched story (in progress, step by step):
  - [x] M2.1 Canonical Master Story Package (2026-10-22): schema + validator +
        Short/Long consistency checks; pilot STORY 053 (Lead Masks, 1966) validates.
        See `docs/features/m2.1-master-story-package.md`.
  - [x] M2.2 Canonical Short narration proof (2026-10-22): `scripts/master_story_short.py`;
        STORY 053 Short narrated with Korva, measured, SRT, gates. First selection measured
        72.68 s (duration gate FAIL), resolved in M2.2.1.
  - [x] M2.2.1 Short duration fixed by canonical selection (2026-10-22): SEG_01, 02, 19, 45,
        measured 49.496 s; all 7 gates PASS. Selection, no pause extension, Korva speed 1.05 and
        unspoken victim names **editorially approved by the user**.
  - [x] M2.1 + M2.2 committed and pushed as technical baseline to `origin/coding` (2026-10-22).
  - [ ] **Pending human review:** audio listening, factual wording, publication; continuity
        rules CR_006, CR_007, CR_008, CR_010. None is marked PASS.
  - [x] M2.3 Canonical Visual Scene Planning (2026-10-22): standalone schema,
        deterministic brief compiler and validator; STORY 053 Short has 11 shots
        covering 49.496375 s, 11 unresolved asset requests, no media generated.
        See `docs/features/m2.3-canonical-visual-scene-planning.md`.
  - [x] M2.3 editorial storyboard approved by the user for progression to M2.4,
        with four final attribution/presentation corrections applied. This does
        not approve historical facts, media rights or publication.
  - [x] M2.3.1 editorial refinement: six revised shots, five approved scene objects
        unchanged at that checkpoint; final SC_001 attribution correction is
        separately authorized. Same 11 IDs / 49.496375 s. Local graphics versus
        conditional historical media separated; final 16 text blocks checked.
        See `docs/features/m2.3.1-editorial-storyboard-refinement.md`.
  - [ ] Rendered mobile reading/pacing review; CR_006/007/008/010, factual,
        listening, licensing and publication approvals remain pending. All asset
        requests unresolved; local rendering recipes not implemented.
  - [ ] M2.4 Asset Resolution: editorial prerequisite approved, not started in
        this finalization task. Input contract: M2.3.1 feature report. No automatic
        fallback generation or rendering.
  - [ ] Later: Long assembly, visuals/rights layer, convergence with the Evidence Canon WIP.
- [ ] Candidates after review (not started): richer rig poses (lie down, crouch-walk,
      two-handed carry), more location kinds/variants, crowd/extra characters, per-character
      voices, better LLM prompting or a larger local model, word-level alignment, music,
      Shorts/vertical cut, UI.
