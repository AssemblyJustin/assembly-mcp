"""PDF → Markdown conversion using PyMuPDF (fitz).

A general-purpose converter modelled on the Assembly BuildingCode /
ReferenceConverter pipeline:

  * font-size analysis to build a heading map (largest sizes → H1..Hn)
  * running header / footer ("page furniture") detection and removal
  * table extraction → GitHub-flavoured pipe tables
  * watermark stripping (Standards NZ / IHS style regex + light-grey overlay text)
  * YAML front-matter linking back to the source PDF

This is a code-only extraction (Tiers 1–2 of the Assembly pipeline). It does
not perform the vision-based Tier 3–4 verification, which needs a Claude API
call — so treat the output as a high-quality first pass, not a certified copy.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF

# PyMuPDF span flag bits
_FLAG_BOLD = 1 << 4  # 16
_FLAG_ITALIC = 1 << 1  # 2

# Watermark / licence boilerplate common on NZ/AU standards PDFs.
_WATERMARK_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^\s*licensed to\b",
        r"^\s*licence\b",
        r"single[- ]user licence",
        r"not for (resale|distribution)",
        r"uncontrolled (copy|when printed)",
        r"purchased by\b",
        r"standards new zealand",
        r"standards australia",
        r"^\s*IHS\b",
        r"copyright.*standards",
        r"this is a free preview",
        r"downloaded\s+\d{1,2}\s+\w+\s+\d{4}",
        r"^\s*©\s*\d{4}\b",
    )
]

# Bullet glyphs PDFs use for unordered lists (WeasyPrint/Word/InDesign etc.).
_BULLET_CHARS = "•●◦▪▫‣∙·"
# A block that is *only* a bullet marker (stray glyph, no content) → drop it.
_BULLET_ONLY_RE = re.compile(rf"^[\s{re.escape(_BULLET_CHARS)}]+$")
# A block whose text starts with a bullet marker → turn into a Markdown list item.
_LEADING_BULLET_RE = re.compile(rf"^[{re.escape(_BULLET_CHARS)}]\s+")


def _norm_key(text: str) -> str:
    """Normalise a line for furniture matching (digits → #, lowercased)."""
    return re.sub(r"\d+", "#", text.strip().lower())


def _is_watermark(text: str) -> bool:
    return any(p.search(text) for p in _WATERMARK_PATTERNS)


def _is_light_grey(color: int) -> bool:
    """True for near-white / light-grey span colours (watermark overlays)."""
    r = (color >> 16) & 0xFF
    g = (color >> 8) & 0xFF
    b = color & 0xFF
    # Light and roughly neutral (e.g. 0xF0F0F0).
    return r >= 0xD0 and g >= 0xD0 and b >= 0xD0 and max(r, g, b) - min(r, g, b) <= 0x14


def _build_heading_map(doc: fitz.Document, max_levels: int = 4) -> tuple[dict[float, int], float]:
    """Map the largest font sizes to heading levels 1..max_levels.

    Body text is taken to be the size that covers the most characters.
    """
    sizes: Counter[float] = Counter()
    for page in doc:
        data = page.get_text("dict")
        for block in data.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span["text"].strip()
                    if text:
                        sizes[round(span["size"], 1)] += len(text)
    if not sizes:
        return {}, 0.0
    body_size = sizes.most_common(1)[0][0]
    heading_sizes = sorted((s for s in sizes if s >= body_size + 0.9), reverse=True)
    heading_map = {size: level for level, size in enumerate(heading_sizes[:max_levels], start=1)}
    return heading_map, body_size


def _collect_furniture(doc: fitz.Document, threshold: float = 0.4) -> set[str]:
    """Find lines that repeat in the top/bottom margins across many pages."""
    top: Counter[str] = Counter()
    bottom: Counter[str] = Counter()
    n = len(doc)
    for page in doc:
        height = page.rect.height
        for block in page.get_text("blocks"):
            text = block[4].strip()
            if not text:
                continue
            y0, y1 = block[1], block[3]
            key = _norm_key(text)
            if not key:
                continue
            if y0 < height * 0.08:
                top[key] += 1
            elif y1 > height * 0.92:
                bottom[key] += 1
    limit = max(2, int(n * threshold))
    furniture = {k for k, c in top.items() if c >= limit}
    furniture |= {k for k, c in bottom.items() if c >= limit}
    return furniture


def _overlap_ratio(inner: fitz.Rect, outer: fitz.Rect) -> float:
    """Fraction of `inner`'s area that lies within `outer`."""
    isect = inner & outer
    if not isect or inner.get_area() == 0:
        return 0.0
    return isect.get_area() / inner.get_area()


def _table_to_markdown(table) -> str:
    """Render a PyMuPDF table as a GitHub-flavoured pipe table."""
    try:
        rows = table.extract()
    except Exception:
        return ""
    cleaned = [
        [(cell or "").replace("\n", " ").replace("|", r"\|").strip() for cell in row]
        for row in rows
    ]
    cleaned = [row for row in cleaned if any(row)]
    if len(cleaned) < 1:
        return ""
    ncol = max(len(r) for r in cleaned)

    def pad(row: list[str]) -> list[str]:
        return row + [""] * (ncol - len(row))

    header = pad(cleaned[0])
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * ncol) + " |",
    ]
    for row in cleaned[1:]:
        lines.append("| " + " | ".join(pad(row)) + " |")
    return "\n".join(lines)


def _block_to_markdown(
    block: dict,
    heading_map: dict[float, int],
    strip_watermarks: bool,
) -> str | None:
    """Convert a single text block to a Markdown heading or paragraph."""
    line_texts: list[str] = []
    max_size = 0.0
    bold_chars = 0
    total_chars = 0
    for line in block.get("lines", []):
        span_texts: list[str] = []
        for span in line.get("spans", []):
            text = span["text"]
            if not text.strip():
                continue
            if strip_watermarks and _is_light_grey(span.get("color", 0)):
                continue
            span_texts.append(text)
            size = round(span["size"], 1)
            max_size = max(max_size, size)
            n = len(text)
            total_chars += n
            if span.get("flags", 0) & _FLAG_BOLD:
                bold_chars += n
        joined = "".join(span_texts).strip()
        if joined:
            line_texts.append(joined)

    if not line_texts:
        return None

    text = " ".join(line_texts).strip()
    text = re.sub(r"\s{2,}", " ", text)
    if not text:
        return None
    if strip_watermarks and _is_watermark(text):
        return None

    # List bullets: drop stray bullet-only blocks; convert leading bullets to
    # Markdown list items. (PDFs often place the bullet glyph in its own run.)
    if _BULLET_ONLY_RE.match(text):
        return None
    bullet = _LEADING_BULLET_RE.match(text)
    if bullet:
        return f"- {text[bullet.end():].strip()}"

    level = heading_map.get(max_size)
    if level is None and total_chars and bold_chars / total_chars > 0.9 and len(text) < 90:
        # Short, fully-bold block with no larger size → treat as a low-level heading.
        level = min(len(set(heading_map.values())) + 1, 4) if heading_map else 3
    if level:
        return f"{'#' * level} {text}"
    return text


def _convert_page(
    page: fitz.Page,
    heading_map: dict[float, int],
    furniture: set[str],
    strip_watermarks: bool,
) -> str:
    """Convert one page to Markdown, preserving top-to-bottom reading order."""
    items: list[tuple[float, str]] = []

    # Tables first, so we can skip the text blocks they overlap.
    table_rects: list[fitz.Rect] = []
    try:
        found = page.find_tables()
        tables = list(found.tables)
    except Exception:
        tables = []
    for table in tables:
        rect = fitz.Rect(table.bbox)
        md = _table_to_markdown(table)
        if md:
            table_rects.append(rect)
            items.append((rect.y0, md))

    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:  # 0 == text block
            continue
        bbox = fitz.Rect(block["bbox"])
        if any(_overlap_ratio(bbox, tr) > 0.5 for tr in table_rects):
            continue
        first_line = block.get("lines", [{}])[0]
        first_text = "".join(
            s.get("text", "") for s in first_line.get("spans", [])
        ).strip()
        # Whole block is repeating page furniture.
        block_text = " ".join(
            "".join(s.get("text", "") for s in ln.get("spans", []))
            for ln in block.get("lines", [])
        ).strip()
        if block_text and _norm_key(block_text) in furniture:
            continue
        _ = first_text  # (kept for readability / future refinement)

        md = _block_to_markdown(block, heading_map, strip_watermarks)
        if md:
            items.append((bbox.y0, md))

    items.sort(key=lambda item: item[0])
    return "\n\n".join(md for _, md in items)


def _front_matter(pdf_path: Path, page_count: int) -> str:
    return (
        "---\n"
        f'source_pdf: "{pdf_path.name}"\n'
        f"pages: {page_count}\n"
        'converter: "assembly-mcp convert_pdftomd (PyMuPDF)"\n'
        "---\n\n"
    )


def _postprocess(text: str) -> str:
    """Tidy: dedupe consecutive identical headings, collapse blank runs."""
    lines = text.split("\n")
    out: list[str] = []
    for line in lines:
        stripped = line.rstrip()
        if (
            stripped.startswith("#")
            and out
            and out[-1].strip() == stripped.strip()
        ):
            continue
        out.append(stripped)
    joined = "\n".join(out)
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip() + "\n"


def pdf_to_markdown(
    pdf_path: str | Path,
    *,
    strip_watermarks: bool = True,
    write_frontmatter: bool = True,
    max_heading_levels: int = 4,
) -> str:
    """Convert a PDF file to a Markdown string.

    Args:
        pdf_path: Path to the source ``.pdf`` file.
        strip_watermarks: Remove Standards-NZ / IHS style watermark lines and
            light-grey overlay text.
        write_frontmatter: Prepend YAML front-matter linking back to the PDF.
        max_heading_levels: Cap on distinct heading levels detected by font size.

    Returns:
        The converted Markdown as a string.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Not a .pdf file: {path}")

    doc = fitz.open(path)
    try:
        heading_map, _body = _build_heading_map(doc, max_levels=max_heading_levels)
        furniture = _collect_furniture(doc)
        pages_md: list[str] = []
        for page in doc:
            page_md = _convert_page(page, heading_map, furniture, strip_watermarks)
            if page_md.strip():
                pages_md.append(page_md)
        page_count = len(doc)
    finally:
        doc.close()

    body = _postprocess("\n\n".join(pages_md))
    if write_frontmatter:
        body = _front_matter(path, page_count) + body
    return body
