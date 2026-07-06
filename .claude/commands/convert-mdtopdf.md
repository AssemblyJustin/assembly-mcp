---
description: Convert a Markdown file to PDF using the Assembly MCP (WeasyPrint)
argument-hint: <input.md> [output.pdf]
---

Convert a Markdown file to PDF by calling the Assembly MCP tool
`convert_mdtopdf` (from the `assembly` MCP server).

Arguments: `$ARGUMENTS`
- First token = path to the source `.md`.
- Optional second token = path to write the `.pdf` output to. If omitted, write
  the PDF next to the source Markdown with the same stem (e.g. `notes.md` →
  `notes.pdf`).

Steps:
1. Parse the arguments into `md_path` and (optional) `output_path`.
2. Call `convert_mdtopdf` with `md_path` and `output_path` (this is required —
   a PDF is binary and cannot be returned inline).
3. Report the output path, byte size, and page count returned by the tool.

If the tool reports that WeasyPrint's native libraries are missing, relay the
install instructions from its error message (GTK3 runtime on Windows; Pango/
cairo packages on Linux/macOS).

If the `assembly` MCP server is not connected, tell the user to add it — see the
repo README `Add to Claude Code` section — then stop.
