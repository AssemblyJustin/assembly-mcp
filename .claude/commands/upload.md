---
description: Upload issues or renders to an assembly-app project as the person doing it. `/upload issues` — files → a draft issue (Transmittal) on the project's Documents tab, then issue it on confirm. `/upload renders` — images → the project's Renders tab. Asks who they are, which project, (issues) the issue type + name, and the files. Uses the Assembly MCP tools upload_issue / issue_draft / upload_renders.
argument-hint: issues | renders
---

# upload — issues or renders

`$ARGUMENTS` picks the mode: `issues` or `renders` (ask if missing).

## Ask for (one short message, only what's missing)

| | issues | renders |
|---|---|---|
| **Who they are** — their app email | ✓ | ✓ |
| **Project** — number (e.g. `2610`) or UUID | ✓ | ✓ |
| **Issue type** — For Information / Review / Approval / Construction / Tender / Coordination / Record | ✓ | — |
| **Issue name** — as it should read on the Documents tab | ✓ | — |
| **Files** — file and/or folder paths (dropped files are fine) | ✓ | ✓ (images) |
| *Render name* — optional, only for a single image | — | optional |

Default target is **prod** (app.assembly.nz). Use `env="dev"` only if they say dev/test.
**Never ask for or pass a password.** The tools sign in as that person using `ASSEMBLY_PASSWORD`
or `~/.assembly/credentials.json` (`{"<email>": "<password>"}`). If sign-in fails with "no password",
tell them to add that file themselves. Don't offer to write it.

## /upload issues

1. `upload_issue(uploader_email, project, issue_type, issue_name, files, dry_run=True)` and show the
   plan: project name, the matched issue type, the issue name, and the file list. Ask "Upload?".
2. On yes: `upload_issue(...)` without `dry_run`. Report `N uploaded · N failed` and say it's a
   **draft** on the project's Documents tab. Keep the `collectionId`.
3. Ask whether to **issue it now**. Issuing uses up an issue number and can't be undone. Show
   `recipientChoices` (organisation → people) and ask who it goes to (people or whole
   organisations; none is allowed) and for any cover notes. Confirm the issue type.
4. On an explicit yes: `issue_draft(uploader_email, collection_id, issue_type, recipients, cover_notes)`.
   Report the issue number (e.g. `2610.T-004`). On no: leave the draft. They can issue it later
   from the Documents tab or by running this again.

## /upload renders

1. `upload_renders(uploader_email, project, files, title?, dry_run=True)` and show what will upload,
   what's already there (skipped) and what isn't an image (skipped). Ask "Upload?".
2. On yes: run it without `dry_run`. Report the tally. The images are on the project's **Renders** tab.

## Errors (say them plainly; don't retry blindly)
- `unknown issue type "…" — choose one of: …` → ask them to pick one from that list.
- `not on this project's team: …` → show `recipientChoices` again.
- `no project numbered …` / `not visible` → they aren't on that project, or the number is wrong.
- `row-level security` / `denied` → their role on the project can't upload (viewers and clients can't).
- If the `assembly` MCP server isn't connected, use the CLIs from an assembly-app checkout instead:
  `pnpm -C apps/frontend upload-issues …` / `upload-renders …` (same flags; see the script headers).
