"""Assembly MCP server.

Exposes two tools over stdio:
  * convert_pdftomd — PDF → Markdown (wraps the assembly-app pdf2md CLI, pdf.js)
  * convert_mdtopdf — Markdown → PDF (WeasyPrint)

Run with:  assembly-mcp        (installed script)
      or:   python -m assembly_mcp.server
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .md_to_pdf import markdown_to_pdf

mcp = FastMCP("assembly")


def _app_dir() -> Path:
    """The assembly-app checkout whose pdf2md CLI is THE converter (env ASSEMBLY_APP_DIR, else the
    sibling `assembly-app` next to this repo)."""
    env = os.environ.get("ASSEMBLY_APP_DIR")
    return Path(env) if env else Path(__file__).resolve().parents[3] / "assembly-app"


@mcp.tool()
def convert_pdftomd(
    pdf_path: str,
    output_path: str | None = None,
    strip_watermarks: bool = True,
    front_matter: bool = True,
) -> str:
    """Convert a PDF file to Markdown.

    Runs the assembly-app pdf2md converter (pdf.js: headings, lists, ruled
    tables, images saved beside the .md in `<stem>_images/`). `strip_watermarks`
    / `front_matter` are always on. When `output_path` is omitted, the Markdown
    and any extracted images are written to a new temp folder; the returned
    summary line names it — pass `output_path` to control the location.

    Args:
        pdf_path: Path to the source `.pdf` file.
        output_path: Optional path to also write the Markdown to (`.md`). If
            omitted, a fresh temp directory is used (named in the returned
            summary line).
        strip_watermarks: Kept for compatibility; always on in the unified converter.
        front_matter: Kept for compatibility; always on in the unified converter.

    Returns:
        The converted Markdown as a string, prefixed with a summary comment.
    """
    script = _app_dir() / "apps" / "frontend" / "scripts" / "pdf2md.ts"
    if not script.exists():
        raise FileNotFoundError(f"pdf2md CLI not found at {script} — set ASSEMBLY_APP_DIR to the assembly-app checkout")
    node = shutil.which("node")
    if node is None:
        raise FileNotFoundError("node (>=22) not found on PATH — required for the pdf2md converter")
    out = Path(output_path) if output_path else Path(tempfile.mkdtemp(prefix="pdf2md-")) / (Path(pdf_path).stem + ".md")
    proc = subprocess.run(
        [node, "--experimental-strip-types", "--no-warnings", str(script), str(Path(pdf_path).resolve()), str(out.resolve())],
        cwd=script.parents[1], capture_output=True, text=True, timeout=600,
        encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"pdf2md exited {proc.returncode}")
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    markdown = out.read_text(encoding="utf-8")
    return (
        f"<!-- pdf2md: {summary['pages']} pages, {summary['tables']} tables, {summary['images']} images; "
        f"written to {summary['output']} -->\n" + markdown
    )


@mcp.tool()
def convert_mdtopdf(
    output_path: str,
    md_path: str | None = None,
    markdown_text: str | None = None,
    title: str | None = None,
    css: str | None = None,
) -> str:
    """Convert Markdown to a PDF file.

    Renders Markdown → HTML → PDF with WeasyPrint (the Assembly MD→PDF stack)
    using a clean print stylesheet. Provide EITHER `md_path` OR `markdown_text`.
    A PDF is binary, so `output_path` is required.

    Args:
        output_path: Path to write the resulting `.pdf` (required).
        md_path: Path to a source `.md` file.
        markdown_text: Raw Markdown string (alternative to `md_path`).
        title: Optional document title (falls back to front-matter `title`).
        css: Optional CSS to replace the built-in print stylesheet.

    Returns:
        A confirmation string with the output path, byte size, and page count.
    """
    if md_path and markdown_text:
        raise ValueError("Provide only one of md_path or markdown_text, not both.")
    base_url: str | None = None
    if md_path:
        src = Path(md_path)
        if not src.exists():
            raise FileNotFoundError(f"Markdown file not found: {src}")
        markdown_text = src.read_text(encoding="utf-8")
        base_url = str(src.parent)
    if not markdown_text:
        raise ValueError("Provide either md_path or markdown_text.")

    result = markdown_to_pdf(
        markdown_text=markdown_text,
        output_path=output_path,
        title=title,
        css=css,
        base_url=base_url,
    )
    return (
        f"Wrote {result['bytes']:,} bytes to {result['output_path']} "
        f"({result['pages']} page(s))."
    )


def main() -> None:
    """Console-script entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
