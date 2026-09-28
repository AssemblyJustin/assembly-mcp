# Assembly MCP

A small [Model Context Protocol](https://modelcontextprotocol.io) server that
gives any MCP client (Claude Code, Claude Desktop, …) two document-conversion
tools:

| Tool | Direction | Engine |
|------|-----------|--------|
| **`convert_pdftomd`** | PDF → Markdown | assembly-app `pdf2md` CLI (pdf.js) |
| **`convert_mdtopdf`** | Markdown → PDF | [WeasyPrint](https://weasyprint.org) |

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
claude mcp add assembly -- uv --directory /ABSOLUTE/PATH/TO/assembly-mcp run assembly-mcp
```

Then the tools `convert_pdftomd` and `convert_mdtopdf` are available in your
session. This repo also ships matching slash commands — run Claude Code from
inside the repo (or copy `.claude/commands/*` into your project) to use:

```
/convert-pdftomd  report.pdf  report.md
/convert-mdtopdf  notes.md     notes.pdf
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
      "args": ["--directory", "C:\\ABSOLUTE\\PATH\\TO\\assembly-mcp", "run", "assembly-mcp"]
    }
  }
}
```

Restart Claude Desktop. The two tools appear under the 🔌 tools menu.

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

---

## Develop

```bash
uv run pytest            # smoke tests (PDF→MD skips without node/assembly-app; MD→PDF skips without GTK)
```

Project layout:

```
src/assembly_mcp/
  server.py       FastMCP server — registers both tools (stdio); convert_pdftomd
                  shells out to the assembly-app pdf2md CLI (_app_dir())
  md_to_pdf.py    python-markdown → WeasyPrint rendering
.claude/commands/ /convert-pdftomd and /convert-mdtopdf slash commands
tests/            smoke tests
```

## License

MIT — see [LICENSE](LICENSE).
