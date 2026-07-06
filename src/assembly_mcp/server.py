"""Assembly MCP server.

Exposes two tools over stdio:
  * convert_pdftomd — PDF → Markdown (PyMuPDF)
  * convert_mdtopdf — Markdown → PDF (WeasyPrint)

Run with:  assembly-mcp        (installed script)
      or:   python -m assembly_mcp.server
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .md_to_pdf import markdown_to_pdf
from .pdf_to_md import pdf_to_markdown

mcp = FastMCP("assembly")


@mcp.tool()
def convert_pdftomd(
    pdf_path: str,
    output_path: str | None = None,
    strip_watermarks: bool = True,
    front_matter: bool = True,
) -> str:
    """Convert a PDF file to Markdown.

    Uses PyMuPDF with font-size heading detection, running header/footer
    removal, table extraction, and optional watermark stripping — the Assembly
    PDF→MD pipeline. Returns the Markdown text; when `output_path` is given it
    also writes a `.md` file there.

    Args:
        pdf_path: Path to the source `.pdf` file.
        output_path: Optional path to also write the Markdown to (`.md`).
        strip_watermarks: Remove Standards-NZ / IHS style watermark lines and
            light-grey overlay text.
        front_matter: Prepend YAML front-matter linking back to the source PDF.

    Returns:
        The converted Markdown as a string.
    """
    markdown = pdf_to_markdown(
        pdf_path,
        strip_watermarks=strip_watermarks,
        write_frontmatter=front_matter,
    )
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
    return markdown


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
