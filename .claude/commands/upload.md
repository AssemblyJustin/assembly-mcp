---
description: Upload issues or renders to an assembly-app project as the person doing it. `/upload issues` — files → a draft issue (Transmittal) on the project's Documents tab, then issue it on confirm. `/upload renders` — images → the project's Renders tab. First time only, asks for their app email + password and saves them; after that it never asks again. Then asks which project, (issues) the issue type + name, and the files. Uses the Assembly MCP tools saved_login / save_login / upload_issue / issue_draft / upload_renders.
argument-hint: issues | renders
---

# upload — issues or renders

`$ARGUMENTS` picks the mode: `issues` or `renders` (ask if missing).

## 0. Who they are (asked ONCE per machine, then never again)

Call `saved_login()` first.
- `default` is set → that's who they are. **Don't ask who they are or for a password.** Mention it
  in passing ("Uploading as jo@assembly.nz"). Only switch person if they say so: someone already in
  `people` → pass `uploader_email`; someone new → do the first-time step for them.
- `default` is null (first time) → ask in one message for their **app email and password**, then
  `save_login(email, password)`. It signs in to check them and saves only if that works. On
  "Invalid login credentials", say so and ask again. **Never repeat the password back** in any
  message, and never write it anywhere else (no notes, files, commits or memory).

After that, omit `uploader_email` in every call. The tools use the saved person.

## 1. Ask for (one short message, only what's missing)

| | issues | renders |
|---|---|---|
| **Project** — number (e.g. `2610`) or UUID | ✓ | ✓ |
| **Issue type** — For Information / Review / Approval / Construction / Tender / Coordination / Record | ✓ | — |
| **Issue name** — as it should read on the Documents tab | ✓ | — |
| **Files** — file and/or folder paths (dropped files are fine) | ✓ | ✓ (images) |
| *Render name* — optional, only for a single image | — | optional |

Default target is **prod** (app.assembly.nz). Use `env="dev"` only if they say dev/test (then
`save_login(..., env="dev")` for a dev account).

## /upload issues

1. `upload_issue(project, issue_type, issue_name, files, dry_run=True)` and show the plan: project
   name, the matched issue type, the issue name, and the file list. Ask "Upload?".
2. On yes: `upload_issue(...)` without `dry_run`. Report `N uploaded · N failed` and say it's a
   **draft** on the project's Documents tab. Keep the `collectionId`.
3. Ask whether to **issue it now**. Issuing uses up an issue number and can't be undone. Show
   `recipientChoices` (organisation → people) and ask who it goes to (people or whole
   organisations; none is allowed) and for any cover notes. Confirm the issue type.
4. On an explicit yes: `issue_draft(collection_id, issue_type, recipients, cover_notes)`.
   Report the issue number (e.g. `2610.T-004`). On no: leave the draft. They can issue it later
   from the Documents tab or by running this again.

## /upload renders

1. `upload_renders(project, files, title?, dry_run=True)` and show what will upload, what's already
   there (skipped) and what isn't an image (skipped). Ask "Upload?".
2. On yes: run it without `dry_run`. Report the tally. The images are on the project's **Renders** tab.

## Errors (say them plainly; don't retry blindly)
- `no saved login` → do the first-time step (section 0).
- `sign-in failed … Invalid login credentials` on an upload → their password changed: ask for the
  new one once and `save_login` again.
- `unknown issue type "…" — choose one of: …` → ask them to pick one from that list.
- `not on this project's team: …` → show `recipientChoices` again.
- `no project numbered …` / `not visible` → they aren't on that project, or the number is wrong.
- `row-level security` / `denied` → their role on the project can't upload (viewers and clients can't).
- If the `assembly` MCP server isn't connected, say so (it's registered in `~/.claude.json`; a new
  session reconnects it). The CLIs also run directly from an assembly-app checkout:
  `pnpm -C apps/frontend upload-issues …` / `upload-renders …` (see the script headers).
