"""Smoke tests: convert_pdftomd (wraps the assembly-app pdf2md CLI) and
convert_mdtopdf (WeasyPrint).

The PDF→MD test is skipped automatically if the assembly-app checkout /
its pdf2md CLI / node are not available. The MD→PDF leg is skipped
automatically if WeasyPrint's native libraries are not installed (e.g. a
stock Windows box without the GTK3 runtime).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from assembly_mcp.md_to_pdf import markdown_to_pdf, pdf_magic_ok
from assembly_mcp.server import _app_dir, convert_pdftomd

SAMPLE_MD = """\
# Assembly MCP Test

A short paragraph with **bold** and *italic* text.

## Features

- PDF to Markdown
- Markdown to PDF

| Tool | Direction |
|------|-----------|
| pdf.js | PDF to MD |
| WeasyPrint | MD to PDF |
"""

APP = _app_dir()
needs_app = pytest.mark.skipif(
    not (APP / "apps/frontend/scripts/pdf2md.ts").exists() or shutil.which("node") is None,
    reason="assembly-app checkout / node not available",
)


def _weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):
        return False
    return True


@needs_app
def test_pdftomd_wraps_app_cli(tmp_path: Path) -> None:
    # Build a one-page PDF with the app's own fixture builder via node would couple the tests;
    # use the md->pdf leg if available, else a minimal hand-written PDF.
    pdf = tmp_path / "hello.pdf"
    pdf.write_bytes(_MINIMAL_PDF)
    md = convert_pdftomd(str(pdf), str(tmp_path / "hello.md"))
    assert 'converter: "assembly-pdf2md/2"' in md
    assert "Hello Assembly" in md
    assert (tmp_path / "hello.md").exists()


_MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R"
    b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 72 780 Td (Hello Assembly) Tj ET\nendstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


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
