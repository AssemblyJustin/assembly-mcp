"""Smoke tests: round-trip Markdown → PDF → Markdown.

The MD→PDF leg is skipped automatically if WeasyPrint's native libraries are
not installed (e.g. a stock Windows box without the GTK3 runtime).
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
import pytest

from assembly_mcp.md_to_pdf import markdown_to_pdf, pdf_magic_ok
from assembly_mcp.pdf_to_md import pdf_to_markdown

SAMPLE_MD = """\
# Assembly MCP Test

A short paragraph with **bold** and *italic* text.

## Features

- PDF to Markdown
- Markdown to PDF

| Tool | Direction |
|------|-----------|
| PyMuPDF | PDF to MD |
| WeasyPrint | MD to PDF |
"""


def _weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):
        return False
    return True


def _make_pdf(path: Path) -> None:
    """Build a small PDF without WeasyPrint, so PDF→MD can be tested anywhere."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 90), "Assembly MCP Test", fontsize=22)
    page.insert_text((72, 140), "A short paragraph of body text.", fontsize=11)
    page.insert_text((72, 170), "Features", fontsize=16)
    page.insert_text((72, 200), "PDF to Markdown and back again.", fontsize=11)
    doc.save(path)
    doc.close()


def test_pdf_to_markdown(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    _make_pdf(pdf)
    md = pdf_to_markdown(pdf)
    assert "Assembly MCP Test" in md
    assert md.startswith("---")  # front-matter
    assert "source_pdf" in md
    # The 22pt line should be promoted to a heading.
    assert "# Assembly MCP Test" in md


@pytest.mark.skipif(
    not _weasyprint_available(),
    reason="WeasyPrint native libraries not installed",
)
def test_markdown_to_pdf_and_back(tmp_path: Path) -> None:
    pdf = tmp_path / "out.pdf"
    result = markdown_to_pdf(markdown_text=SAMPLE_MD, output_path=pdf)
    assert result["pages"] >= 1
    data = pdf.read_bytes()
    assert pdf_magic_ok(data)

    md = pdf_to_markdown(pdf)
    assert "Assembly MCP Test" in md
    assert "Features" in md
