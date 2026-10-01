"""Assembly MCP server.

Exposes these tools over stdio:
  * convert_pdftomd — PDF → Markdown (wraps the assembly-app pdf2md CLI, pdf.js)
  * convert_mdtopdf — Markdown → PDF (WeasyPrint)
  * upload_issue / issue_draft — files → a draft issue on a project's Documents tab, then issue it
    (wraps the assembly-app upload-issues CLI)
  * upload_renders — images → a project's Renders tab (wraps the assembly-app upload-renders CLI)

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


def _run_upload_cli(script_name: str, args: list[str]) -> dict:
    """Run an assembly-app upload CLI (`apps/frontend/scripts/<script_name>`) and return its
    `RESULT {json}` line. The CLI signs in AS the person (`--as <email>`); its password comes from
    ASSEMBLY_PASSWORD or ~/.assembly/credentials.json — never from a tool argument. Dev config is
    read from the checkout's `apps/frontend/.env.local`."""
    frontend = _app_dir() / "apps" / "frontend"
    script = frontend / "scripts" / script_name
    if not script.exists():
        raise FileNotFoundError(f"{script_name} not found at {script} — set ASSEMBLY_APP_DIR to an assembly-app checkout that has it")
    node = shutil.which("node")
    if node is None:
        raise FileNotFoundError("node (>=22) not found on PATH — required for the upload CLIs")
    proc = subprocess.run(
        [node, "--env-file-if-exists=.env.local", "--experimental-strip-types", "--no-warnings", str(script), *args],
        cwd=frontend, capture_output=True, text=True, timeout=1800,
        encoding="utf-8", errors="replace",
    )
    result_lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")]
    if not result_lines:
        raise RuntimeError(proc.stderr.strip() or f"{script_name} exited {proc.returncode} without a result")
    result = json.loads(result_lines[-1][len("RESULT "):])
    if result.get("ok") is False and "error" in result:
        raise RuntimeError(result["error"])
    return result


def _env_arg(env: str) -> list[str]:
    if env not in ("prod", "dev"):
        raise ValueError('env must be "prod" or "dev"')
    return ["--env", env]


@mcp.tool()
def upload_issue(
    uploader_email: str,
    project: str,
    issue_type: str,
    issue_name: str,
    files: list[str],
    env: str = "prod",
    dry_run: bool = False,
) -> dict:
    """Upload files to an assembly-app project as a DRAFT issue (a Transmittal on the Documents tab).

    Signs in as the person uploading, so it can only reach projects they are on. Never issues — call
    `issue_draft` with the returned `collectionId` once the person confirms. Run with `dry_run=True`
    first to check the project, issue type and file list without writing anything.

    Args:
        uploader_email: The app account of the person uploading (who they are).
        project: The project's number (e.g. "2610") or UUID.
        issue_type: The issue purpose, e.g. "For Construction", "For Information", "Review".
        issue_name: The issue's name as it should appear on the Documents tab.
        files: File and/or folder paths (folders are walked).
        env: "prod" (app.assembly.nz, default) or "dev" (dev.assembly.nz).
        dry_run: Show the plan only; no writes.

    Returns:
        {ok, project, issueType, name, collectionId, status: "draft", uploaded, failed,
        recipientChoices: [{organisation, people}]} — `recipientChoices` is who it can be issued to.
    """
    args = ["--as", uploader_email, "--project", project, "--type", issue_type, "--name", issue_name]
    for f in files:
        args += ["--file", str(Path(f).expanduser().resolve())]
    args += _env_arg(env)
    if dry_run:
        args.append("--dry-run")
    return _run_upload_cli("upload-issues.ts", args)


@mcp.tool()
def issue_draft(
    uploader_email: str,
    collection_id: str,
    issue_type: str,
    recipients: list[str] | None = None,
    cover_notes: str | None = None,
    env: str = "prod",
) -> dict:
    """Issue a draft created by `upload_issue` — allocates the next issue number. Irreversible:
    only call after the person has confirmed the issue type and recipients.

    Args:
        uploader_email: The same person who created the draft.
        collection_id: `collectionId` returned by `upload_issue`.
        issue_type: The issue purpose (e.g. "For Construction").
        recipients: People ("Jane Smith") and/or organisations ("Smith Engineering" = all its
            members) from the draft's `recipientChoices`. May be empty.
        cover_notes: Optional transmittal cover notes.
        env: "prod" (default) or "dev" — must match the draft's.

    Returns:
        {ok, collectionId, name, status: "issued", issueNumber, issueType, recipients}
    """
    args = ["--issue", collection_id, "--as", uploader_email, "--type", issue_type]
    for r in recipients or []:
        args += ["--to", r]
    if cover_notes:
        args += ["--notes", cover_notes]
    args += _env_arg(env)
    return _run_upload_cli("upload-issues.ts", args)


@mcp.tool()
def upload_renders(
    uploader_email: str,
    project: str,
    files: list[str],
    title: str | None = None,
    env: str = "prod",
    dry_run: bool = False,
) -> dict:
    """Upload render images to an assembly-app project's Renders tab, as the person uploading.

    Non-images are skipped and reported; an image already on the Renders tab (same file name) is
    skipped, so re-running is safe.

    Args:
        uploader_email: The app account of the person uploading (who they are).
        project: The project's number (e.g. "2610") or UUID.
        files: Image and/or folder paths (folders are walked).
        title: Name for the render — only when uploading exactly one image (default: file name).
        env: "prod" (app.assembly.nz, default) or "dev" (dev.assembly.nz).
        dry_run: Show the plan only; no writes.

    Returns:
        {ok, project, uploaded | toUpload, alreadyThere, skippedNotImages, failed}
    """
    args = ["--as", uploader_email, "--project", project]
    for f in files:
        args += ["--file", str(Path(f).expanduser().resolve())]
    if title:
        args += ["--title", title]
    args += _env_arg(env)
    if dry_run:
        args.append("--dry-run")
    return _run_upload_cli("upload-renders.ts", args)


def main() -> None:
    """Console-script entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
