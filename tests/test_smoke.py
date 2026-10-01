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
NODE = shutil.which("node")
needs_app = pytest.mark.skipif(
    not (APP / "apps/frontend/scripts/pdf2md.ts").exists() or NODE is None,
    reason="assembly-app checkout / node not available",
)
needs_node = pytest.mark.skipif(NODE is None, reason="node not available")


def _stub_app(tmp_path: Path, script_body: str) -> Path:
    """A fake assembly-app checkout with a stand-in `pdf2md.ts` at the CLI's contract path."""
    script = tmp_path / "apps" / "frontend" / "scripts" / "pdf2md.ts"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(script_body, encoding="utf-8")
    return tmp_path


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

_STUB_PDF = b"%PDF-1.4\n%%EOF\n"


@needs_node
def test_convert_pdftomd_raises_runtime_error_with_stderr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-zero exit from the CLI surfaces its stderr in the RuntimeError."""
    app_dir = _stub_app(tmp_path, "process.stderr.write('pdf2md: boom\\n');\nprocess.exit(1);\n")
    monkeypatch.setenv("ASSEMBLY_APP_DIR", str(app_dir))
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(_STUB_PDF)
    with pytest.raises(RuntimeError, match="boom"):
        convert_pdftomd(str(pdf), str(tmp_path / "out.md"))


def test_convert_pdftomd_missing_script_raises_filenotfound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No `pdf2md.ts` at the contract path -> a clear FileNotFoundError naming ASSEMBLY_APP_DIR."""
    monkeypatch.setenv("ASSEMBLY_APP_DIR", str(tmp_path))  # empty dir: no apps/frontend/scripts/pdf2md.ts
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(_STUB_PDF)
    with pytest.raises(FileNotFoundError, match="ASSEMBLY_APP_DIR"):
        convert_pdftomd(str(pdf), str(tmp_path / "out.md"))


@needs_node
def test_convert_pdftomd_handles_non_ascii_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-ASCII path segment in the CLI's JSON summary line round-trips cleanly (utf-8 decode)."""
    script_body = (
        "const fs = require('fs');\n"
        "fs.writeFileSync(process.argv[3], '# Hello\\n');\n"
        "console.log(JSON.stringify({output: 'C:/\\u014ct\\u0101kou/out.md', pages: 1, tables: 0, images: 0}));\n"
    )
    app_dir = _stub_app(tmp_path, script_body)
    monkeypatch.setenv("ASSEMBLY_APP_DIR", str(app_dir))
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(_STUB_PDF)
    md = convert_pdftomd(str(pdf), str(tmp_path / "out.md"))
    assert "Ōtākou" in md
    assert "# Hello" in md


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
