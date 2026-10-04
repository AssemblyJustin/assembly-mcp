# Assembly MCP

A small [Model Context Protocol](https://modelcontextprotocol.io) server that
gives any MCP client (Claude Code, Claude Desktop, …) document-conversion and assembly-app upload
tools:

| Tool | Direction | Engine |
|------|-----------|--------|
| **`convert_pdftomd`** | PDF → Markdown | assembly-app `pdf2md` CLI (pdf.js) |
| **`convert_mdtopdf`** | Markdown → PDF | [WeasyPrint](https://weasyprint.org) |
| **`upload_issue` / `issue_draft`** | files → draft issue → issued | assembly-app `upload-issues` CLI |
| **`upload_renders`** | images → Renders tab | assembly-app `upload-renders` CLI |

`convert_pdftomd` is a thin wrapper — it shells out to
`node --experimental-strip-types --no-warnings <assembly-app>/apps/frontend/scripts/pdf2md.ts`,
the assembly-app pdf2md converter (pdf.js: headings, lists, ruled tables,
images saved to `<stem>_images/`). Requires **Node ≥ 22** and an assembly-app
checkout — see `ASSEMBLY_APP_DIR` below. `convert_mdtopdf` renders
Markdown/HTML → PDF with WeasyPrint (pure-Python, no TeX toolchain).

---

## Requirements

- **Python ≥ 3.11**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or `pip`
- **Node ≥ 22** and an **assembly-app checkout** — required for `convert_pdftomd`,
  which shells out to that repo's `apps/frontend/scripts/pdf2md.ts`. By default
  it looks for a sibling `assembly-app` checkout next to this repo; point it
  elsewhere with the `ASSEMBLY_APP_DIR` environment variable.
- **WeasyPrint native libraries** — only needed for `convert_mdtopdf`
  (`convert_pdftomd` works without them):
  - **Linux (Debian/Ubuntu):** `apt install libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev`
  - **macOS:** `brew install pango gdk-pixbuf libffi`
  - **Windows:** install the
    [GTK3 runtime](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases).
    Without it, `convert_pdftomd` still works and `convert_mdtopdf` returns a
    clear "install GTK" error.

---

## Install

```bash
git clone https://github.com/AssemblyJustin/assembly-mcp.git
cd assembly-mcp
uv sync            # creates .venv and installs everything
```

Run the server directly to confirm it starts (it speaks MCP over stdio and will
wait for a client — `Ctrl-C` to exit):

```bash
uv run assembly-mcp
```

---

## Add to Claude Code

From anywhere, register the server (adjust the path to your clone):

```bash
claude mcp add assembly -- uv --directory /ABSOLUTE/PATH/TO/assembly-mcp run --no-sync assembly-mcp
```

(`--no-sync`: on Windows, a second Claude session's `uv run` otherwise tries to reinstall the
`assembly-mcp.exe` the first session is running, fails with "file in use", and the server never
connects. Run `uv sync` yourself after pulling.)

Then the tools are available in your session. This repo also ships matching slash commands — run
Claude Code from inside the repo (or copy `.claude/commands/*` into your project) to use:

```
/convert-pdftomd  report.pdf  report.md
/convert-mdtopdf  notes.md     notes.pdf
/upload issues
/upload renders
```

## Add to Claude Desktop

Edit `claude_desktop_config.json`
(**macOS:** `~/Library/Application Support/Claude/`,
**Windows:** `%APPDATA%\Claude\`) and add:

```json
{
  "mcpServers": {
    "assembly": {
      "command": "uv",
      "args": ["--directory", "C:\\ABSOLUTE\\PATH\\TO\\assembly-mcp", "run", "--no-sync", "assembly-mcp"]
    }
  }
}
```

Restart Claude Desktop. The tools appear under the 🔌 tools menu.

---

## Tools

### `convert_pdftomd`

Convert a PDF file to Markdown. PDF→Markdown runs the assembly-app pdf2md
converter (pdf.js) — headings, lists, ruled tables, images (saved to
`<stem>_images/`). Requires node ≥ 22 and the assembly-app checkout
(`ASSEMBLY_APP_DIR`).

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `pdf_path` | string | — | Path to the source `.pdf`. |
| `output_path` | string | `null` | Optional path to also write the `.md`. |
| `strip_watermarks` | bool | `true` | Kept for compatibility; always on in the unified converter. |
| `front_matter` | bool | `true` | Kept for compatibility; always on in the unified converter. |

Returns the Markdown text (prefixed with a `<!-- pdf2md: … -->` summary
comment giving page/table/image counts and the output path).

> This is a code-only extraction. It does not run vision-based verification,
> so treat the output as a high-quality first pass, not a certified copy.

### `convert_mdtopdf`

Convert Markdown to a PDF file. Provide **either** `md_path` **or**
`markdown_text`.

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `output_path` | string | — | Where to write the `.pdf` (required). |
| `md_path` | string | `null` | Path to a source `.md`. |
| `markdown_text` | string | `null` | Raw Markdown (alternative to `md_path`). |
| `title` | string | `null` | Document title (falls back to front-matter `title`). |
| `css` | string | `null` | CSS to replace the built-in print stylesheet. |

Renders Markdown → HTML → PDF with a clean A4 print stylesheet (tables, code
blocks, page numbers) and verifies the PDF magic bytes before writing.

### `upload_issue` / `issue_draft` / `upload_renders`

Upload to an assembly-app project **as the person doing it**. These are thin wrappers over the
assembly-app CLIs `apps/frontend/scripts/upload-issues.ts` and `upload-renders.ts` (node ≥ 22 +
an assembly-app checkout, `ASSEMBLY_APP_DIR`). Each signs in as `uploader_email`, so the database's own
permission rules apply: people can only upload to projects they're on, and viewers and clients can't upload.
The slash command `/upload issues` / `/upload renders` (`.claude/commands/upload.md`) drives them.

| Tool | Does |
|------|------|
| `upload_issue(project, issue_type, issue_name, files, env="prod", dry_run=False, uploader_email=None)` | Files → a **draft** issue (Transmittal) on the project's Documents tab. Returns `collectionId` + `recipientChoices`. Never issues. |
| `issue_draft(collection_id, issue_type, recipients=[], cover_notes=None, env="prod", uploader_email=None)` | Issues that draft (allocates the issue number, which can't be undone). `recipients` = people and/or organisation names. |
| `upload_renders(project, files, title=None, env="prod", dry_run=False, uploader_email=None)` | Images → the project's Renders tab. Skips non-images and images already there. |
| `save_login(email, password, env="prod", make_default=True)` | Checks the login by signing in, then saves it to `~/.assembly/credentials.json` and (by default) makes them the default uploader. `/upload` calls it the first time only. |
| `saved_login()` | Who `/upload` acts as on this machine (`default` + saved `people`). Never returns passwords. |

`uploader_email` is optional everywhere: omitted, the tools act as the saved default.

`project` is the project number (e.g. `2610`) or UUID. `issue_type` is the issue purpose: For
Information / Review / Approval / Construction / Tender / Coordination / Record (or an org's own).

**Setup (once per machine):**
- Login: nothing to do by hand. The first `/upload` asks for the person's app email + password
  once and `save_login` stores them in `~/.assembly/credentials.json`
  (`{"_default": "<email>", "<email>": "<password>"}`, several people allowed). After that it never
  asks again. `ASSEMBLY_PASSWORD` still works for scripted use.
- Prod: set `ASSEMBLY_SUPABASE_ANON_KEY` to the prod app's public anon key (URL defaults to
  `https://newapi-next.assembly.nz`; override with `ASSEMBLY_SUPABASE_URL`).
- Dev (`env="dev"`): read from the checkout's `apps/frontend/.env.local`.

---

## Develop

```bash
uv run pytest            # smoke tests (PDF→MD skips without node/assembly-app; MD→PDF skips without GTK)
```

Project layout:

```
src/assembly_mcp/
  server.py       FastMCP server — registers the tools (stdio); convert_pdftomd
                  shells out to the assembly-app pdf2md CLI (_app_dir())
  md_to_pdf.py    python-markdown → WeasyPrint rendering
.claude/commands/ /convert-pdftomd, /convert-mdtopdf and /upload slash commands
tests/            smoke tests
```

## License

MIT — see [LICENSE](LICENSE).
