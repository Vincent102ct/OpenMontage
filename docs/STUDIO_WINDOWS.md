# OpenMontage Studio on Windows

Studio saves a story or topic as a new production request and, on request,
prepares a story draft for review. It does **not** start research, narration or
video rendering, and it never publishes.

## Open Studio

In PowerShell, from the `OpenMontage` folder (after the setup in
[WINDOWS_STORY_TO_VIDEO.md](WINDOWS_STORY_TO_VIDEO.md)):

```powershell
.\.venv\Scripts\python.exe -m studio open
```

Your browser opens `http://127.0.0.1:4760/studio`. Keep the terminal open while
you use Studio; press `Ctrl+C` there to stop it. If the browser does not open,
copy the printed URL. If port 4760 is busy, add `--port 4761`.

## Save a Vietnamese story as Short + Long

1. **New Production** → choose **Full story**.
2. Paste the story into the text box, or use **Import Markdown** for a UTF-8 `.md` file.
3. Optional: enter a title, and under **Optional project ID** an ID such as
   `chuyen-xe-cuoi` (lowercase letters, digits, hyphens). Leave it empty for an automatic ID.
4. Under **Output formats**, click **Select both** (Short 9:16 + Long 16:9).
5. Click **Save / Create Project**.

The green panel shows the project ID, the saved files under `projects/<id>/` and
**Production not started**. Click **Open Backlot** to see the monitoring board;
all stages show as pending.

Other modes:

- **Topic**: a subject to research later. It is saved as unresearched input, not as a story.
- **Canonical package**: only packages approved in `studio/approved_packages.json` appear.
  The list is empty until a reviewer adds one.

## My Productions

Lists Studio requests and existing project workspaces. **View input** shows the
saved text; **Open Backlot** opens that project's board.

## Prepare a story draft

For a **Full story** production, **My Productions → Prepare Story Draft** checks
the saved story against its recorded hash. It then writes draft files for review under
`projects/<id>/artifacts/story_intake/v1/`:
- story segments;
- character, place and object candidates;
- recurring times and numbers;
- proposed text clean-ups;
- questions for you.

It does not run research, narration or rendering, and it never changes your
original story or the saved request.

The draft panel shows **Review status: Pending human review**. Proposed edits
(for example a stray `\` or a personal note at the end) are shown as before/after
and are **not applied** to your story. The automatic analysis covers rules only; plot,
twists and who-is-who are listed as questions for you.

Clicking the button again shows the same draft; it is never rewritten. If a draft
file was edited by hand, Studio refuses to overwrite it. Move the `story_intake\v1`
folder aside to prepare it again. The button is disabled for Topic and Canonical
productions (not supported yet).

Same action from PowerShell:

```powershell
.\.venv\Scripts\python.exe -m studio intake <project-id>
```

Details: [P2.1 feature document](features/p2.1-story-intake-bridge.md).

## Review the story

After **Prepare Story Draft**, open **My Productions → Story Review**.

1. If no Story Bible exists yet, click **Import Story Bible draft (.json)** and pick
   the draft, for example
   `projects\_private_story_drafts\my-story\story_bible.draft.json`.
   Studio checks every quote against your original story. If anything does not
   match, it lists the problems and saves nothing.
2. Review each section:
   - **Proposed edits:** Accept, Reject or Defer.
   - **Interpretation questions:** type your answer and click **Record answer**, **Preserve Ambiguity**
     to deliberately leave a mystery unexplained, or **Defer** to leave review unfinished. An empty
     answer is never saved; the question stays open.
   - **Story Bible:** characters, places, objects, facts and claims, events, dialogue,
     sounds, motifs and continuity, each with the exact story lines it comes from.
   - **Short and Long drafts:** every line is marked **Verbatim source text** or
     **Authored proposal**; durations are estimates until narration is measured.
3. To change a decision, click a different button; Studio keeps the earlier
   decision as history. If the page is out of date, Studio asks you to reload
   instead of overwriting a newer decision.

The **Missing or incomplete** box lists what is still unknown or undecided.
Recording decisions never starts narration, rendering or publishing.

Same actions from PowerShell:

```powershell
.\.venv\Scripts\python.exe -m studio fiction <project-id> --draft projects\_private_story_drafts\my-story\story_bible.draft.json
.\.venv\Scripts\python.exe -m studio review <project-id>
```

Keep private stories and Story Bibles under the gitignored `projects/` directory.
The CLI only reads `.json` files under `_private_story_drafts` in the configured
projects directory; traversal and symlink/junction paths are refused. The browser
imports the selected file contents and sends no server-side file path. Do not
commit a private draft, narrative or screenshot. The imported draft is hash-checked
and source-linked; it remains unapproved after review decisions are recorded.

Details: [P2.2 feature document](features/p2.2-fiction-story-package.md).

## Approve a reviewed story

After importing the Story Bible, stay in **Story Review**:

1. Decide every proposed edit, Story Bible item and both formats. Accept applies
   an edit to a separate reviewed copy; Reject preserves the original text.
   Rejected semantic items are excluded from the reviewed canon. Defer blocks approval.
2. Answer each interpretation question or explicitly choose **Preserve Ambiguity**.
   This records an intentional mystery without inventing an answer or a speaker.
   An answer is recorded as your interpretation; it never silently rewrites a fact.
3. Click **Materialize Reviewed Story**. Review the applied decisions, working
   text and source mapping, accepted canon, intentional ambiguities, Short/Long
   contents and blockers. Broken references and missing Long text must be fixed
   through explicit decisions or a revised authored draft; Studio does not guess repairs.
4. Check the displayed version, package SHA-256 and manifest SHA-256. If there
   are no blockers, check the acknowledgement and click **Approve Reviewed Story**.

This writes a hash-bound approval for pre-production story content only. It does
not start narration, animation or rendering, and it does not permit publishing.

Files live under `projects/<id>/artifacts/reviewed_fiction/v2/`:
`reviewed_package.json`, `reviewed_working_text.md`, `manifest.json`, and (only
after explicit approval) `approval.json`. Original inputs and all v1 artifacts stay
unchanged. The same decisions return the same version without rewriting files.
New decisions require a new version (`v3`, `v4`, …) and another approval; frozen
versions remain available in the version selector. A stale page cannot approve
different hashes or newer decisions. Never commit these private production files.

Details and synthetic example: [P2.3 feature document](features/p2.3-reviewed-fiction-package.md).

## Notes

- Studio refuses to reuse an existing project ID; nothing is overwritten.
- Style is fixed to Stickman Horror 2D. Human review is required; publishing is disabled.
- Everything stays on this computer (`127.0.0.1` only).
