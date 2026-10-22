# Story-to-video M1.1 on Windows

Windows Compatibility technical baseline accepted by the user on 2026-10-22.
Use the current `origin/coding` containing this guide and the Windows code.
Historical baseline `877a12b` alone still hardcodes macOS TTS.
No M2, footage-led WIP, paid API, story rewrite or renderer replacement is included.

## Clean-clone setup (PowerShell)

Prerequisites: Python >= 3.10, Node.js with npm, FFmpeg + ffprobe, and an offline
voice for the story language. Install/extract tools in user-writable locations;
no administrator rights, registry edits or execution-policy changes are needed by
this pipeline. A missing Windows language pack is not proof that a compatible
System.Speech voice can be installed without administrator help.

```powershell
git clone --branch coding https://github.com/Vincent102ct/OpenMontage.git
Set-Location OpenMontage
git rev-parse HEAD  # Compare with the published Windows Compatibility commit.
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --cache-dir .venv/pip-cache -r requirements-dev.txt
Push-Location remotion-composer
try { npm.cmd ci --no-audit --no-fund --cache ../.venv/npm-cache } finally { Pop-Location }

# If necessary, replace this with the bin directory of a user-local FFmpeg extraction:
# $env:Path = 'C:\Tools\ffmpeg\bin;' + $env:Path
$ffmpegBin = Split-Path (Get-Command ffmpeg -ErrorAction Stop).Source
$env:Path = "$ffmpegBin;$env:Path"
ffmpeg -version
ffprobe -version
.\.venv\Scripts\python.exe -c "import shutil; print(shutil.which('ffmpeg'), shutil.which('ffprobe'))"
```

The last command must print two executable paths. On the verified Windows
session, PowerShell command discovery found WinGet FFmpeg before Python's
inherited PATH did; explicitly putting that discovered directory first fixed it.
The npm cache is inside the workspace to avoid restricted user-profile caches.
Invoke `.venv\Scripts\python.exe` directly; venv activation is unnecessary.

Remotion uses its downloaded headless browser by default (the first render may
download it). To use an already installed Chrome instead:

```powershell
$env:REMOTION_BROWSER_EXECUTABLE = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
Test-Path $env:REMOTION_BROWSER_EXECUTABLE
```

Use the real path on the target machine, or remove the override to use Remotion's
default browser. The verified run used installed Chrome, not a browser download.
Keep default concurrency 2; paths containing spaces are supported.

## Check voices through the actual synthesis engines

```powershell
.\.venv\Scripts\python.exe -c "from tools.audio.windows_sapi_tts import WindowsSapiTTS; import json; print(json.dumps(WindowsSapiTTS().list_voices(), ensure_ascii=True, indent=2))"
```

The adapter queries both `powershell` (Windows PowerShell 5.1) and `pwsh`
(PowerShell 7, if installed), using `-NoProfile -NonInteractive`. Each voice row
contains `name`, `language_code` and `speech_host`. Only enabled voices exposed by
System.Speech count. Enumeration and synthesis use the same host; Windows Settings
and registry entries alone do not prove availability. No registry copying is used.

Observed on 2026-10-22:

| Host | Enabled voices | Language |
| --- | --- | --- |
| Windows PowerShell 5.1 | Microsoft David Desktop, Microsoft Zira Desktop | en-US |
| PowerShell 7.6.2 | Both Desktop voices, Microsoft David, Microsoft Mark, Microsoft Zira | en-US |
| PowerShell 7.6.2 | Microsoft An | vi-VN |

Other Windows machines may have only the two English Desktop voices. Never assume
Microsoft An is present, or that a voice visible under PowerShell 7 is visible
under Windows PowerShell 5.1. Actual synthesis must succeed as well as enumeration.

## Provider selection and timing

`--tts-provider auto` (default) tries the native provider for the OS, then Piper
only when a local model was explicitly configured. No cloud provider participates.

| OS/provider | Voice selection | Default speed / `--rate` units |
| --- | --- | --- |
| Windows / windows_sapi | Installed matching language; prefer Zira Desktop for EN | -1; integer -10..10, 0 is preserved |
| macOS / macos_say | Prefer Linh vi_VN and Samantha en_US; otherwise a matching installed voice | VI 145, EN 165 words/minute; integer 80..300 |
| Piper | Existing `.onnx` + adjacent `.onnx.json` declaring matching `language.code` | 1.0 length_scale; 0.25..4, larger is slower |

Explicit `--voice` must match the story language. A missing Vietnamese provider
is a blocker; the CLI never reads Vietnamese using an English voice. Supplying a
macOS speed such as 145 to SAPI fails rather than being clamped or reinterpreted.

All new SAPI/Piper WAVs become mono, 24 kHz, PCM16; macOS retains its existing
normalization. Timeline duration is measured from actual WAV samples, never word
count, process execution time or an assumed speaking speed. Narration cache keys
include provider/version, host, voice/model, locale, settings and exact text;
Piper model/config hashes distinguish changed weights. Cached WAV content hashes
are checked, and durations are remeasured on every run. Cache metadata does not
override actual samples.

Inspect `artifacts/tts_selection.json`, `assets/audio/narration_manifest.json`
and `artifacts/render_report.json` for the provider actually used.

## Run a new story without editing code

```powershell
.\.venv\Scripts\python.exe scripts/story_to_video.py path/to/new-story.md --analyzer rules

# Existing M1.1 fixtures; these IDs keep Windows outputs separate from old Mac runs:
.\.venv\Scripts\python.exe scripts/story_to_video.py examples/story-to-video/stories/the-last-loaf.en.md --analyzer rules --project-id windows-m11-last-loaf
.\.venv\Scripts\python.exe scripts/story_to_video.py examples/story-to-video/stories/chiec-o-mau-vang.vi.md --analyzer rules --project-id windows-m11-chiec-o

# Optional explicit native voice; otherwise auto-selection handles language:
.\.venv\Scripts\python.exe scripts/story_to_video.py path/to/story.vi.md --analyzer rules --tts-provider windows_sapi --voice 'Microsoft An' --rate -1
```

`--analyzer rules` requires no LLM. Existing `auto` behavior may contact optional
local Ollama; this is separate from TTS. Output is
`projects/<file-slug>-auto/renders/final.mp4`, or the supplied project ID, plus
analysis, measured narration, action timeline, subtitles, QA, keyframes and contact
sheet. Story content stays unchanged. Different voices produce different durations.

### Two distinct non-rendering modes

```powershell
# Analysis only: works even without a TTS voice or FFmpeg.
.\.venv\Scripts\python.exe scripts/story_to_video.py path/to/story.md --analyzer rules --dry-run

# Narration + SFX + measured timeline + validated Remotion package, but no browser/MP4.
.\.venv\Scripts\python.exe scripts/story_to_video.py path/to/story.md --analyzer rules --no-render
```

`--dry-run` stops before provider selection/TTS/planning. It writes analysis and
`dry_run_report.json` under a separate `<project-id>-dry-run` workspace; it emits no
duration, action timeline, SFX, subtitles or Remotion package. Empty workspace
directories may be created. Existing production outputs are not evidence of a dry run.

`--no-render` intentionally needs a real matching voice. It synthesizes real audio
because the action timeline needs measured durations. The two flags are mutually
exclusive. Neither mode estimates narration durations to fabricate a valid timeline.

### Optional Piper (not required for the verified EN/VI runs)

Install a compatible Piper executable into your venv/user space and put its
directory on PATH. Obtain a properly licensed local voice model and its matching
config. This change does not download models, change language-pack settings or
call a service to replace a missing local voice.

```powershell
# Once a compatible piper executable and these two files exist locally:
Get-Command piper
Test-Path 'C:\Voices\voice.onnx'
Test-Path 'C:\Voices\voice.onnx.json'
.\.venv\Scripts\python.exe scripts/story_to_video.py path/to/story.vi.md --analyzer rules --tts-provider piper --piper-model 'C:\Voices\voice.onnx' --rate 1.0
# Optional per-session default (auto still prefers matching native speech):
$env:OPENMONTAGE_PIPER_MODEL = 'C:\Voices\voice.onnx'
```

The model config must declare the actual language (for example `vi_VN`), and weights
must really be trained for it. Do not relabel English metadata as Vietnamese.
Piper was not installed on the acceptance machine: routing, missing model,
language rejection, UTF-8 stdin and WAV normalization have mocked tests; real Piper
inference and its pronunciation are unverified here. If no usable native voice or
compatible local model exists, use analysis-only dry-run until one is available.

## Tests and TypeScript check (PowerShell)

```powershell
.\.venv\Scripts\python.exe -m pytest tests/tools tests/lib tests/contracts -q -p no:cacheprovider --basetemp=.venv/windows-tests

# Stage templates under the composer tree so TypeScript resolves its node_modules.
$templateCheck = Join-Path (Get-Location) 'remotion-composer/projects/_windows_tsc'
New-Item -ItemType Directory -Path $templateCheck -Force | Out-Null
Copy-Item -Path tools/character/remotion/*.ts,tools/character/remotion/*.tsx -Destination $templateCheck
& remotion-composer/node_modules/.bin/tsc.cmd --noEmit --strict --esModuleInterop --jsx react-jsx --skipLibCheck --target ES2020 --moduleResolution node "$templateCheck/index.tsx"
git diff --check
```

`--basetemp` is a disposable test directory: choose a dedicated new directory if
it already contains anything you need. Test network protection stays enabled.
Tests preserve macOS voice/rate behavior with mocks. Windows EN/VI rendering:
**technical PASS**. Vietnamese pronunciation: **pending human review**.
macOS runtime regression: **pending real-machine render**. The Windows VI image
and technical review was accepted for compatibility; this does not authorize M2.

Results and remaining review gates: [Windows handoff](WINDOWS_M11_HANDOFF_2026-10-22.md).
