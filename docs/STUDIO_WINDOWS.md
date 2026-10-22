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

## Notes

- Studio refuses to reuse an existing project ID; nothing is overwritten.
- Style is fixed to Stickman Horror 2D. Human review is required; publishing is disabled.
- Everything stays on this computer (`127.0.0.1` only).
