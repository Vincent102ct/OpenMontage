# P1 — OpenMontage Studio Input MVP

Status: implemented and tested locally on 2026-10-22; awaiting human review. Not committed.

Studio is the local, user-facing creation entry point. It saves a validated
**production request** into a normal project workspace and stops there. It does
not start research, TTS, scene planning, rendering, uploads or any paid API call.
Backlot remains the read-only monitoring board; Studio links to it.

Windows usage: [STUDIO_WINDOWS.md](../STUDIO_WINDOWS.md).

## Command

```powershell
.\.venv\Scripts\python.exe -m studio open    # serve on 127.0.0.1:4760 and open the browser
.\.venv\Scripts\python.exe -m studio serve   # serve only; --port N to change the port
```

The server binds `127.0.0.1` only and rejects other `Host` headers. The browser
opens only after `/studio/api/health` confirms the same Studio app and workspace.

## Architecture

| Path | Role |
| --- | --- |
| `studio/__main__.py` | CLI (`open`/`serve`), uvicorn on 127.0.0.1 |
| `studio/server.py` | Wraps the unchanged Backlot app and adds `/studio` routes on one origin, so `/p/<id>` board links work directly |
| `studio/models.py` | `NewProduction` (input) and `ProductionRequest` (saved) pydantic contracts |
| `studio/store.py` | Atomic, no-overwrite persistence into `projects/<id>/`; list/detail with integrity checks |
| `studio/catalog.py` | Reads hash-bound entries from `studio/approved_packages.json`; never approves anything itself |
| `studio/ui/` | Static HTML/CSS/JS (no build step, no external requests, strict CSP) |
| `schemas/studio/production_request.schema.json` | JSON Schema generated from `ProductionRequest`; a test keeps them identical |

Backlot source (`backlot/`) and `lib/checkpoint.py` are not modified. Studio does
not import `tools`, `lib.checkpoint` or `lib.canonical_assets` (enforced by test).

### API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/studio` | UI |
| GET | `/studio/api/health` | App identity and workspace key |
| GET | `/studio/api/packages` | Approved canonical packages that still match their recorded hash |
| GET | `/studio/api/productions` | Studio requests plus existing workspaces (read-only) |
| GET | `/studio/api/productions/{id}` | Saved request, saved files, Backlot URL |
| POST | `/studio/api/productions` | Validate and save; 201, 409 (exists), 413, 415, 422, 403 (cross-origin) |

## Production request contract (`schema_version` 1.0)

Saved at `projects/<id>/artifacts/production_request.json`:

| Field | Value |
| --- | --- |
| `project_id` | `^[a-z0-9][a-z0-9-]{0,63}$`; Windows reserved names rejected; auto `studio-YYYYMMDD-HHMMSS-<8 hex>` when empty |
| `title` | Single line, max 120; an explicit title is kept verbatim. Otherwise the first nonblank input line, minus a Markdown ATX heading marker (`# Title` → `Title`; `#hashtag` unchanged), or the package title. Content and hash are never altered |
| `input_mode` | `topic` / `story` / `canonical` |
| `content` | Original UTF-8 text, byte-for-byte (CRLF, leading/trailing whitespace kept); `null` for canonical |
| `content_sha256` | SHA-256 of the UTF-8 content, or of the canonical package bytes |
| `input_file` | `input/topic.txt`, `input/story.md` or `input/canonical-reference.json` |
| `source_filename` | Uploaded Markdown name (metadata only, never used as a path) |
| `formats` | Subset of `short` (9:16) and `long` (16:9), ordered, non-empty, unique |
| `style` | Constant `stickman_horror_2d` |
| `review_mode` / `review_status` | `human_required` / `pending_human_review` |
| `publishing_enabled` | Constant `false` |
| `status` | Constant `production_not_started` |
| `input_readiness` | `unresearched_topic`, `unreviewed_story` or `canonical_reference`; a topic is never treated as a researched Master Story |
| `created_at` | UTC timestamp |
| `canonical_package` | Catalog ID, package ID/version, repo-relative path, SHA-256, approver, approval time; no claims copied |

Workspace layout follows the AGENT_GUIDE convention (`artifacts/`, `assets/*`,
`renders/`) plus `input/`. `project.json` is written last with
`pipeline_type: character-animation`, `status: production_not_started`,
`production_started: false`, so Backlot shows the project with every stage pending.
No checkpoints, events, research briefs or media are created.

### Safety rules

- `mkdir` of the project directory is the atomic reservation; any existing
  directory (including empty or legacy workspaces) returns 409 and nothing is
  written. Files are opened with mode `x`.
- Project IDs are validated before any path is built; symlinks and resolved
  paths outside `projects/` are rejected.
- Canonical packages must be listed in `studio/approved_packages.json`, live
  under `examples/master-story/`, match the recorded SHA-256 and pass
  `lib.master_story.validate_package`. The shipped catalog is empty: no package,
  including STORY 053, is self-approved by this milestone.
- Saves require `application/json`, same-origin, body ≤ 2 MB, content ≤ 200,000
  characters / 1 MB UTF-8, no control characters other than tab/CR/LF.
- Detail and listing re-verify the saved input bytes against the request; a
  tampered input is reported as invalid and never rewritten.

## UI

New Production (input mode, title, text or Markdown upload, optional project ID,
Short/Long/both, fixed Stickman Horror 2D style, human review required,
publishing disabled, "Production not started"), My Productions (empty, loading,
error/retry states, input viewer) and Open Backlot links. All UI text is English;
user content can be Vietnamese.

Screenshots (fictional test fixtures only, real Chrome, full-page captures):
[new production](../images/studio/p1-new-production.png),
[saved project](../images/studio/p1-saved-project.png),
[my productions](../images/studio/p1-my-productions.png),
[mobile](../images/studio/p1-mobile.png),
[browser check list](../images/studio/browser-results.json).

## Verification (2026-10-22, Windows 11, Python 3.14.5 in `.venv`)

```powershell
.\.venv\Scripts\python.exe -m pytest tests/studio -q -p no:cacheprovider --basetemp=.venv/pytest-p1-studio
# 66 passed (Studio); with tests/backlot: 103 passed, 1 skipped
```

- `tests/studio/test_input.py` (65): Vietnamese UTF-8 bytes and hash, JSON Schema
  parity, all three modes, all format choices, 20 invalid payloads that write
  nothing, 15 unsafe project IDs, no overwrite of Studio/empty/legacy projects,
  concurrent saves, literal XSS text, cross-origin/non-JSON/oversize rejection,
  no subprocess/network/tool-registry use during saves, Backlot compatibility,
  Markdown heading title derivation (16 cases),
  catalog path escape and tamper detection.
- `tests/studio/test_browser.py` (1): real Chrome via the existing Remotion CDP
  driver, 17 UI checks, zero external requests and page errors. Skips if Chrome,
  Node or `remotion-composer/node_modules` is missing.
- Manual smoke: `python -m studio serve` against the real `projects/` returned
  health, Studio page and Backlot `/` with 200 and listed existing workspaces
  read-only (GET only).
- Pre-existing WIP files and `examples/master-story/` were hashed before and
  after this work and are unchanged.

## Known limits and follow-ups

- No pipeline consumes `production_request.json` yet. The next step (topic →
  research → Master Story) must read it and keep the human review gates.
- The canonical catalog is empty. Approving a package (for example STORY 053)
  requires a human to add a hash-bound entry.
- Updates to `ROADMAP.md`, `DECISIONS.md`, `WORKLOG.md`, `SOURCE_MAP.md` and
  `docs/ARCHITECTURE.md` are deferred: those files hold unrelated uncommitted
  WIP. Proposed entries:
  - ROADMAP: `[x] P1 Studio Input MVP — local input-only entry point; see docs/features/p1-studio-input-mvp.md`.
  - DECISIONS: Studio wraps Backlot on one origin without editing Backlot;
    saves never start production; canonical packages require explicit hash-bound approval.
  - SOURCE_MAP: `studio/`, `schemas/studio/`, `tests/studio/`.
- In this environment pytest's default temp directory is access-denied; pass
  `--basetemp` under `.venv/`.
- Test inputs contain Vietnamese text on purpose (UTF-8 coverage).
