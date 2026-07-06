# Assembly MCP

A small [Model Context Protocol](https://modelcontextprotocol.io) server that
gives any MCP client (Claude Code, Claude Desktop, …) two document-conversion
tools:

| Tool | Direction | Engine |
|------|-----------|--------|
| **`convert_pdftomd`** | PDF → Markdown | [PyMuPDF](https://pymupdf.readthedocs.io) |
| **`convert_mdtopdf`** | Markdown → PDF | [WeasyPrint](https://weasyprint.org) |

Both are the conversion engines Assembly already standardises on:
PyMuPDF-first extraction (font-size heading detection, running header/footer
removal, table extraction, watermark stripping) and WeasyPrint for
Markdown/HTML → PDF (pure-Python, no TeX toolchain).

---

## Requirements

- **Python ≥ 3.11**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or `pip`
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

Convert a PDF file to Markdown.

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `pdf_path` | string | — | Path to the source `.pdf`. |
| `output_path` | string | `null` | Optional path to also write the `.md`. |
| `strip_watermarks` | bool | `true` | Remove Standards-NZ / IHS style watermark lines and light-grey overlay text. |
| `front_matter` | bool | `true` | Prepend YAML front-matter linking back to the source PDF. |

Returns the Markdown text. Extraction features: font-size heading map
(largest sizes → `#`..`####`), running header/footer removal, `find_tables()`
→ pipe tables, watermark/licence-line stripping.

> This is a code-only extraction (Tiers 1–2 of Assembly's pipeline). It does
> not run the vision-based Tier 3–4 verification, so treat the output as a
> high-quality first pass, not a certified copy.

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
uv run pytest            # smoke tests (MD→PDF test auto-skips without GTK)
```

Project layout:

```
src/assembly_mcp/
  server.py       FastMCP server — registers both tools (stdio)
  pdf_to_md.py    PyMuPDF extraction pipeline
  md_to_pdf.py    python-markdown → WeasyPrint rendering
.claude/commands/ /convert-pdftomd and /convert-mdtopdf slash commands
tests/            round-trip smoke test
```

## License

MIT — see [LICENSE](LICENSE).
