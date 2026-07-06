---
description: Convert a PDF to Markdown using the Assembly MCP (PyMuPDF pipeline)
argument-hint: <input.pdf> [output.md]
---

Convert a PDF file to Markdown by calling the Assembly MCP tool
`convert_pdftomd` (from the `assembly` MCP server).

Arguments: `$ARGUMENTS`
- First token = path to the source `.pdf`.
- Optional second token = path to write the `.md` output to. If omitted, write
  the Markdown next to the source PDF with the same stem (e.g. `report.pdf` →
  `report.md`).

Steps:
1. Parse the arguments into `pdf_path` and (optional) `output_path`.
2. Call `convert_pdftomd` with `pdf_path`, `output_path`, `strip_watermarks=true`,
   `front_matter=true`.
3. Report where the Markdown was written and summarise anything notable
   (page count, tables found, watermark lines removed).

If the `assembly` MCP server is not connected, tell the user to add it — see the
repo README `Add to Claude Code` section — then stop.
