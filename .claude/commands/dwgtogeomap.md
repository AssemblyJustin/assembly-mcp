---
description: Put a Revit DWG's linework on an assembly-app project's Site → Revit Maps tab, as the person doing it. First time only, asks for their app email + password and saves them; after that it never asks again. Then asks which project and the DWG, shows a dry run (coordinate system, units, layers, line count, distance to site), and uploads on "yes". Uses the Assembly MCP tools saved_login / save_login / dwg_to_geomap.
argument-hint: [project] [path/to/drawing.dwg]
---

# dwgtogeomap — Revit DWG → Site → Revit Maps

`$ARGUMENTS` may already hold the project and/or the DWG path — use what's there, ask for the rest.

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

- **Project** — number (e.g. `2610`), name (e.g. `Homestead Bay`), or UUID.
- **DWG** — path to the `.dwg` (a dropped file is fine). It should be exported from Revit with
  **"Coordinate system basis: Shared"** so it lands in real-world coordinates.
- *Drawing name* — optional; defaults to the file name without `.dwg`. Uploading the same name
  again **replaces** that drawing (say so if they're re-uploading).

Target: **dev** (dev.assembly.nz) for now — always pass `env="dev"` (and `save_login(..., env="dev")`
for a dev account). Revit Maps (the `project_map_layers` table and the conversion API) is only on dev
until it's promoted; a prod upload fails until then. Once it's on prod, prod becomes the default and
dev is used only if they say dev/test.

## 2. Dry run

`dwg_to_geomap(project, file, name?, dry_run=True)` and show, briefly:

- **Project** — `project.number` + `project.name`
- **Coordinate system** — `drawing.crsName` (EPSG:`drawing.epsg`), auto-detected
- **Units** — `drawing.units`
- **Layers** — each `name (lines)`
- **Lines** — `drawing.lineCount`
- **Distance to site** — `drawing.distanceToSiteKm` km (or "no site location set")
- `replaced: true` → "This replaces the existing drawing named …"
- any `warnings`, word for word

If `distanceToSiteKm` > 2, **warn before asking**: the drawing's centre is that far from the
project site, so it's probably misplaced — most often the Revit export didn't use Shared
coordinates, or the project's site location is wrong. Suggest re-exporting; only continue if they
still want to.

Then ask **"Upload?"**.

## 3. Upload

On yes: `dwg_to_geomap(project, file, name?)` without `dry_run`. Report: drawing name, line count,
layers, and whether it was added or replaced an existing drawing. Then point them to the project's
**Site → Revit Maps** tab — every drawing is drawn there, and each layer can be switched on/off.

## Errors (say them plainly; don't retry blindly)
- `no saved login` → do the first-time step (section 0).
- `sign-in failed … Invalid login credentials` → their password changed: ask for the new one once
  and `save_login` again.
- `… matches N projects …` → show the listed projects and ask which one (or for the number).
- `no project numbered or named …` / `not visible` → they aren't on that project, or the name/number is wrong.
- `could not be read` (unreadable) → the DWG is damaged or not a real DWG: re-export it from Revit
  (File → Export → CAD Formats → DWG).
- `no lines in model space` (no-lines) → export a plan view that actually shows the linework.
- Couldn't work out where the drawing sits (no-crs) → re-export from Revit with **"Coordinate
  system basis: Shared"**, and make sure the project's site location is set (Site tab).
- `larger than 50 MB` → purge the model / export only the site plan view.
- `not a .dwg file` / `not found` → ask for the right path.
- `didn't accept your login` / `isn't allowed to use the conversion service` → sign in again with
  `save_login`; the conversion service is for Assembly organisation members.
- `Couldn't reach the conversion service` → it's down or offline; try later.
- `row-level security` / `admin or editor` → their role on the project can't add drawings (viewers
  and clients can't).
- If the `assembly` MCP server isn't connected, say so (it's registered in `~/.claude.json`; a new
  session reconnects it). The CLI also runs directly from an assembly-app checkout:
  `pnpm -C apps/frontend upload-dwg-geomap --project <number|name> --file <path.dwg> [--dry-run]`.
