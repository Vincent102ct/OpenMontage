# OpenMontage Studio on Windows

Studio saves a story or topic as a new production request. It does **not** start
research, narration or video rendering, and it never publishes.

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

## Notes

- Studio refuses to reuse an existing project ID; nothing is overwritten.
- Style is fixed to Stickman Horror 2D. Human review is required; publishing is disabled.
- Everything stays on this computer (`127.0.0.1` only).
