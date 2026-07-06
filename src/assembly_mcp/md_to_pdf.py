"""Markdown → PDF conversion.

Pipeline: Markdown → HTML (python-markdown) → PDF (WeasyPrint), matching the
Assembly stack where WeasyPrint is the primary HTML/MD → PDF renderer
(pure-Python on top of cairo/pango, no TeX toolchain required).

WeasyPrint is imported lazily so this module — and the ``convert_pdftomd``
tool — still work on machines that lack WeasyPrint's native GTK/Pango
libraries (notably a stock Windows install).
"""

from __future__ import annotations

import re
from pathlib import Path

import markdown as md_lib

_MD_EXTENSIONS = [
    "extra",          # tables, fenced code, footnotes, attr_list, etc.
    "sane_lists",
    "smarty",
    "toc",
    "admonition",
]

# A clean, printable A4 stylesheet. Overridable via the `css` argument.
DEFAULT_CSS = """
@page {
    size: A4;
    margin: 22mm 20mm 20mm 20mm;
    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-size: 9pt;
        color: #888;
    }
}
html { font-size: 11pt; }
body {
    font-family: "Segoe UI", "Helvetica Neue", Arial, "Noto Sans", sans-serif;
    line-height: 1.5;
    color: #1a1a1a;
    -weasy-hyphens: auto;
}
h1, h2, h3, h4, h5, h6 {
    font-weight: 600;
    line-height: 1.25;
    margin: 1.2em 0 0.5em;
    page-break-after: avoid;
}
h1 { font-size: 1.9em; border-bottom: 2px solid #e2e2e2; padding-bottom: 0.2em; }
h2 { font-size: 1.5em; border-bottom: 1px solid #ececec; padding-bottom: 0.15em; }
h3 { font-size: 1.25em; }
h4 { font-size: 1.1em; }
p { margin: 0 0 0.7em; }
a { color: #0b5fff; text-decoration: none; }
ul, ol { margin: 0 0 0.7em 1.4em; }
li { margin: 0.15em 0; }
blockquote {
    margin: 0.8em 0;
    padding: 0.2em 1em;
    color: #555;
    border-left: 3px solid #d0d0d0;
    background: #fafafa;
}
code {
    font-family: "Cascadia Code", "Consolas", "Liberation Mono", monospace;
    font-size: 0.9em;
    background: #f3f3f3;
    padding: 0.1em 0.35em;
    border-radius: 3px;
}
pre {
    background: #f6f8fa;
    border: 1px solid #e6e6e6;
    border-radius: 6px;
    padding: 0.8em 1em;
    overflow-x: auto;
    page-break-inside: avoid;
}
pre code { background: none; padding: 0; }
table {
    border-collapse: collapse;
    width: 100%;
    margin: 0.8em 0;
    font-size: 0.95em;
    page-break-inside: avoid;
}
th, td {
    border: 1px solid #d8d8d8;
    padding: 6px 10px;
    text-align: left;
    vertical-align: top;
}
th { background: #f2f4f7; font-weight: 600; }
tr:nth-child(even) td { background: #fbfbfc; }
img { max-width: 100%; }
hr { border: none; border-top: 1px solid #e2e2e2; margin: 1.4em 0; }
"""

_FRONTMATTER_RE = re.compile(r"^﻿?---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _strip_frontmatter(text: str) -> tuple[str, dict[str, str]]:
    """Remove a leading ``---`` YAML front-matter block; return (body, meta)."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return text, {}
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip().lower()] = value.strip().strip('"').strip("'")
    return text[match.end():], meta


def _build_html(markdown_text: str, title: str | None, css: str) -> str:
    body, meta = _strip_frontmatter(markdown_text)
    doc_title = title or meta.get("title") or meta.get("source_pdf") or "Document"
    html_body = md_lib.markdown(body, extensions=_MD_EXTENSIONS, output_format="html5")
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{_escape(doc_title)}</title>\n"
        f"<style>{css}</style>\n</head>\n<body>\n{html_body}\n</body>\n</html>\n"
    )


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def pdf_magic_ok(data: bytes) -> bool:
    """True if `data` starts with the PDF magic bytes."""
    return data[:5] == b"%PDF-"


def markdown_to_pdf(
    *,
    markdown_text: str,
    output_path: str | Path,
    title: str | None = None,
    css: str | None = None,
    base_url: str | None = None,
) -> dict:
    """Render Markdown to a PDF file.

    Args:
        markdown_text: The Markdown source.
        output_path: Where to write the resulting ``.pdf``.
        title: Optional document title (falls back to front-matter ``title``).
        css: Optional CSS to replace the built-in print stylesheet.
        base_url: Base path/URL for resolving relative images and links.

    Returns:
        ``{"output_path": str, "bytes": int, "pages": int}``.

    Raises:
        RuntimeError: If WeasyPrint (or its native libraries) is unavailable,
            or the rendered output fails the PDF magic-byte check.
    """
    html_doc = _build_html(markdown_text, title, css or DEFAULT_CSS)

    try:
        from weasyprint import HTML  # lazy: keeps convert_pdftomd usable without GTK
    except (ImportError, OSError) as exc:  # OSError => native libs missing
        raise RuntimeError(
            "Markdown-to-PDF needs WeasyPrint and its native libraries "
            "(Pango/cairo/GDK-PixBuf). Install them:\n"
            "  - Linux (Debian/Ubuntu): apt install libpango-1.0-0 "
            "libpangoft2-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev\n"
            "  - macOS: brew install pango gdk-pixbuf libffi\n"
            "  - Windows: install the GTK3 runtime "
            "(https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer)\n"
            f"Underlying error: {exc}"
        ) from exc

    document = HTML(string=html_doc, base_url=base_url).render()
    pdf_bytes = document.write_pdf()
    if not pdf_magic_ok(pdf_bytes):
        raise RuntimeError("Rendered output failed the PDF magic-byte check.")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf_bytes)
    return {
        "output_path": str(out),
        "bytes": len(pdf_bytes),
        "pages": len(document.pages),
    }
