# Windows M1.1 compatibility handoff — 2026-10-22

Windows Compatibility is accepted as a **technical baseline** by the user on
2026-10-22, after review of the Windows VI image and technical result. Two real
MP4s rendered; Windows EN/VI rendering: **technical PASS**. Vietnamese pronunciation:
**pending human review**. macOS runtime regression: **pending real-machine render**.
This acceptance authorizes the scoped commit and normal push to `origin/coding`;
it does not imply pronunciation/creative approval or permission to begin M2.

## 1. Repository and environment

- Active branch was already `coding`, HEAD `877a12baa327dc5657df8d3e622bf02b6b7c1f24`.
  This is the source baseline; finalization publishes only the Windows file
  allowlist on top of it, without a reset, force push or unrelated WIP.
- Windows build 26200; Python 3.14.5 (`.venv/Scripts/python.exe`), Node 24.16.0,
  npm 10.4.0, FFmpeg/ffprobe 9.0.1, Remotion 4.0.484, Chrome 155.0.8059.85.
- Python requirements installed into the existing workspace venv; `npm.cmd ci`
  completed (199 packages) using workspace-local cache after the default cache
  returned EPERM. No administrator/security/configuration changes.
- Windows PowerShell 5.1 and PowerShell 7.6.2 both available. Piper not installed.
- Finalization recheck: Python 3.14.5, Node 24.16.0, npm 11.13.0 (the original
  render session reported npm 10.4.0). FFmpeg remains 9.0.1, installed under the
  user's WinGet directory and added to this session's PATH; no global PATH or
  security setting was changed. Dependencies were reused for final checks.
- Registry after correcting the session FFmpeg PATH: TTS **1/12 providers**
  configured (`windows_sapi`), FFmpeg/Remotion/HyperFrames reported available.
  Retained the user-required existing Remotion path; HyperFrames not used/tested.
- Preserved existing dirty files: `docs/ARCHITECTURE.md`, `lib/checkpoint.py`,
  `schemas/artifacts/__init__.py`, five artifact schemas, `tools/video/video_compose.py`,
  and untracked evidence/source-visual docs, library and tests. They are not this
  milestone's implementation. No footage-led WIP was incorporated into StoryVideo.

## 2. Compatibility root causes

1. Generic CLI hardcoded `macos_say_tts`, Linh/Samantha and macOS WPM.
2. SAPI returned synthesis wall time, not WAV duration; WAV format was not unified
   with macOS narration; no requested-language check in its adapter.
3. PowerShell 5.1 exposes only English Desktop voices here. PowerShell 7 exposes
   the installed Vietnamese Microsoft An voice; voice lists differ by runtime.
4. Piper assumed a model identifier without verifying a local model/config or
   language, and did not return measured audio duration.
5. `--no-render` meant package-only after TTS, although the historical handoff
   suggested it could plan on Windows without a matching speech provider.
6. Cache identity omitted provider/model/host; cached duration metadata was trusted.
7. Session PATH/caches differed between PowerShell discovery and child processes.
   The existing BaseTool already resolves Windows `.cmd` wrappers, quotes argument
   lists and decodes UTF-8; existing Remotion staging/props paths worked unchanged.

## 3. Changed files and behavior

| File | Change |
| --- | --- |
| `scripts/story_to_video.py` | Offline provider options, analysis-only dry-run, accurate no-render help, measured/cache-validated narration, UTF-8 console, provider evidence; subtitle/QA failures return failure; retain legacy voice report metadata alongside structured TTS metadata |
| `tools/audio/local_narration.py` | OS/language/installed-voice selection, native provider speed scales, explicit Piper model/config identity |
| `tools/audio/local_wav.py` | Mono 24 kHz PCM16 normalization and complete sample-based WAV duration |
| `tools/audio/windows_sapi_tts.py` | Actual enabled voice inventories in both hosts, same-host synthesis, locale/rate checks, safe UTF-8 text file, normalized duration |
| `tools/audio/macos_say_tts.py` | Expose reusable voice enumeration; preserve say invocation, locale checks, defaults and normalization |
| `tools/audio/piper_tts.py` | Existing local model/config and language checks, UTF-8 stdin, temporary raw WAV, normalized duration; no automatic download |
| `tests/tools/test_local_narration.py` | Routing/language/host/rate/cache/PCM/Piper/dry-run/no-render regressions |
| `tests/contracts/test_phase3_contracts.py` | Exact provider catalog now includes the existing macos_say/windows_sapi tools |

No Story Planner, Remotion template, rig, source story, shared BaseTool, paid TTS
selector or video-compose code changed for this task. Existing story schemas and
CLI positional input remain supported. Project IDs now reject path traversal.

## 4. Providers verified

| Provider / voice | Evidence / status |
| --- | --- |
| SAPI / Microsoft Zira Desktop, en-US, rate -1, Windows PowerShell | 16 real sentence WAVs and full EN MP4; technical PASS; no listening acceptance claimed |
| SAPI / Microsoft An, vi-VN, rate -1, PowerShell 7 | 21 real sentence WAVs and full VI MP4; technical PASS; pronunciation/intelligibility **pending** |
| macOS say / Linh 145 WPM, Samantha 165 WPM | Preserved defaults and mocked regressions PASS; live Mac unavailable here |
| Piper | Configured-model route and adapter covered by mocked tests; real runtime/model/pronunciation unverified; not required by these two renders |

No language substitution, paid API or new narration text. Original offline SAPI
voices were reused; no voice/language pack was installed or registry edited.

## 5. Windows commands

Run from `coding` containing the published Windows commit. Complete clean-clone setup,
PATH/browser configuration, voice discovery, Piper configuration and test commands:
[Windows guide](WINDOWS_STORY_TO_VIDEO.md).

```powershell
$ffmpegBin = Split-Path (Get-Command ffmpeg -ErrorAction Stop).Source
$env:Path = "$ffmpegBin;$env:Path"
$env:REMOTION_BROWSER_EXECUTABLE = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
.\.venv\Scripts\python.exe scripts/story_to_video.py examples/story-to-video/stories/the-last-loaf.en.md --analyzer rules --project-id windows-m11-last-loaf
.\.venv\Scripts\python.exe scripts/story_to_video.py examples/story-to-video/stories/chiec-o-mau-vang.vi.md --analyzer rules --project-id windows-m11-chiec-o
```

For another story, replace only the input path (project ID is optional). No
per-story source changes. `--no-render` still needs real TTS; `--dry-run` is
analysis-only and writes a separate workspace without a timeline or fake duration.

## 6. Outputs

Paths are relative to the repository root. Generated projects are gitignored.

| | English | Vietnamese |
| --- | --- | --- |
| Project | `projects/windows-m11-last-loaf/` | `projects/windows-m11-chiec-o/` |
| MP4 | `renders/final.mp4` | `renders/final.mp4` |
| Duration | 102.122667 s | 125.653333 s |
| Frames | 3062 | 3768 |
| Picture | H.264, 1280×720, 30 fps, yuvj420p | same |
| Audio | AAC 48 kHz; -21.3 LUFS | AAC 48 kHz; -18.2 LUFS |
| Measured source speech | 63.113125 s / 16 WAVs | 74.225333 s / 21 WAVs |
| Size | 19,746,007 bytes | 33,268,543 bytes |
| CLI wall time | 261.4 s | 299.1 s |
| QA | PASS, 0 warnings/issues | PASS, 0 warnings/issues |

SHA256:

```text
6afa4aa1ff86d348b7a9867e8fc76bca4eaf441dea6b3940a49a1532b3f1a93b  projects/windows-m11-last-loaf/renders/final.mp4
587a1d7b26c818f1ef243d40c654b66bcff9855e28b3fe118f454262728405c0  projects/windows-m11-chiec-o/renders/final.mp4
```

Each project contains `artifacts/{tts_selection,story_analysis,story_video,
action_timeline,compose_tool_result,qa_report,render_report,windows_verification}.json`,
`assets/audio/narration_manifest.json`, `assets/subtitles.srt`,
`renders/keyframes/` and `renders/contact_sheet.jpg`.

## 7. Tests, build and QA

- Publication candidate recheck (2026-10-22): **1872 PASS, 7 skipped, 3 xfailed,
  1 subtest passed**, 317.01 s; one SDK deprecation warning, no failures.
  This run uses a clean archive of `877a12b` plus exactly the 16 Windows files,
  excluding unrelated WIP (so its count differs from the earlier worktree run).
  Both real-audio EN/VI `--no-render` runs and strict TypeScript PASS on that
  candidate; source code/tests are byte-identical to the staged Windows files.
  Original MP4 hashes, decoded-audio/subtitle evidence and full decode rechecked
  successfully. Baseline and dirty-worktree versions of the three compose methods
  used here (`_render_via_atelier`, `_stage_atelier_project`, `_run_final_review`)
  have identical ASTs; no WIP renderer behavior is needed for this release.
  Local logs/JUnit: `.venv/windows-finalize-tests.log` / `windows-finalize-tests.xml`;
  generated projects and logs are intentionally excluded from Git. All 16 unrelated
  WIP paths retain their pre-finalization checksums. The staged allowlist contains
  only Python source/tests and Markdown, with no secret patterns or large binaries.
- Original M1.1/pilot/TTS/subtitle focused suites: 88 PASS against a clean archive
  of `877a12b` using the installed venv/dependencies. The first archive check lacked
  node_modules; after attaching the existing modules to that archive, all 88 passed.
- Extended focused suite: 104 PASS; final native/local TTS suite including
  additional no-render and Piper execution tests: 21 PASS.
- Initial broad unit run (`tests/tools tests/lib`): 749 PASS, 1 skipped, 3 expected
  failures, 1 subtest passed. Final combined suite results are recorded below.
- Earlier worktree combined run (`tests/tools tests/lib tests/contracts`): **1967 PASS,
  8 skipped, 3 xfailed, 1 subtest passed**, 326.84 s. One Google GenAI/Python
  deprecation warning, no failures. Logs/JUnit: `.venv/windows-m11-final-all.log`
  and `.venv/windows-m11-final-all.xml` (local, ignored).
- Contract suite: 1216 PASS, 7 skipped. Before fixing the stale provider expectation,
  it reproduced exactly the handoff failure (1215 PASS + that one failure).
- Strict TypeScript template typecheck PASS using a copy under the composer tree.
- `git diff --check` PASS. Source stories/Story Planner/Remotion templates have no diff.
  Python compile and Python 3.10 syntax checks PASS (runtime used here is 3.14.5).
- Actual rules-only dry-run on both fixtures PASS with no WAV/timeline/package.
  Actual no-render on both fixtures PASS (3071 EN / 3777 VI validator frames,
  including the validator's end margin). Wrong-language voice and SAPI rate 165
  each exit 1 before narration/planning, as required.
- Both MP4s: ffprobe facts verified, full FFmpeg decode clean; no silent narration
  window; 17/17 EN and 15/15 VI body-action windows show motion. Caption text and
  source narration match all original story beats. All 37 WAVs have actual measured
  mono 24 kHz PCM16 samples; SRT text matches exactly and timestamps differ from
  planned narration by at most 1 ms. Contact sheets inspected: captions (including
  Vietnamese diacritics) and final written-item insert are visible/readable.
- Additional one-off decoded-audio FFT cross-correlation against every original WAV:
  EN offsets +29.447..+56.903 ms (minimum correlation 0.90323), VI
  +27.896..+57.017 ms (minimum correlation 0.95142). Residuals are retained in
  `windows_verification.json`; they are below a two-frame/66.667 ms technical
  tolerance, **not zero**. Initial exploratory 40 ms tolerance was exceeded.
  A roughly 43 ms common delay is consistent with an encoding/mux delay, but the
  cause was not isolated and no renderer offset was changed. No word-level forced
  alignment, perfect sync, pronunciation or listening acceptance claimed.
  The existing generic compose review's `mix_intelligible`/`music_present` booleans
  are level heuristics, not listening or music detection evidence. There is no
  music track in these runs. Story QA PASS here is explicitly technical only.

## 8. Blockers and limitations

- **Vietnamese listening acceptance pending** by the user's choice. Correct voice
  locale and non-silent output alone cannot establish understandable pronunciation.
- Windows VI image/technical review was accepted for this compatibility baseline.
  Broader M1.1 creative approval is not inferred; M2 has not started.
- Live macOS speech/browser rendering cannot be verified on this Windows machine.
  The original story/pilot regressions and native adapter mocks pass; this is not
  a claim that a fresh Mac render was performed.
- A different Windows machine may lack Microsoft An or PowerShell 7. Fail clearly
  until a working local voice/model is available; do not relabel an English voice.
  Piper runtime/model download and inference were unnecessary and not tested live.
- Existing Mac-only handwriting font is not installed here; the renderer's
  existing cursive fallback rendered a legible Vietnamese insert. Fonts/voices
  cause different pixels/timing across OSs; bit-identical Mac output is not expected.
- Source speech measures sentence duration, not verb/word phonetic timestamps.
  Existing M1.1 action staging and other known rig limits remain as documented.
- Requirements are lower-bounded; exact future package resolution can differ.
  Baseline `877a12b` alone lacks the Windows change: clone current `coding` or use
  the published Windows commit. New-machine setup is documented, not independently
  run on a second physical machine.

## 9. Documentation updated

`docs/WINDOWS_STORY_TO_VIDEO.md` (setup/usage), this handoff,
`docs/HANDOFF_2026-10-21.md` (historical-baseline notice),
`docs/features/story-to-video-pipeline.md`, `SOURCE_MAP.md`, `ROADMAP.md`,
`WORKLOG.md`, `DECISIONS.md`. No WIP footage-led specifications were changed.

## 10. Continue from another machine

```powershell
git clone --branch coding https://github.com/Vincent102ct/OpenMontage.git
Set-Location OpenMontage
git rev-parse HEAD
```

Compare HEAD with the published commit linked in the delivery report; for an exact
baseline use `git checkout --detach <published-commit-sha>`. Follow
[Windows setup](WINDOWS_STORY_TO_VIDEO.md) for venv, npm ci, FFmpeg PATH, browser
and real voice enumeration, then run both fixture commands in section 5. Generated
MP4s are intentionally not pushed; regenerate them locally. No secret/API key is
required by this path. On an existing clone, preserve local changes before using
`git pull --ff-only origin coding`; do not reset or force-push to resolve divergence.

Remaining checks: listen to Vietnamese narration and record human feedback;
render on a real Mac with installed Linh/Samantha to close runtime regression.
M2 remains outside this handoff. Final clean-candidate test results are recorded
in section 7; checksums protect all unrelated WIP during publication.
