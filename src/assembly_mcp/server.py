"""Assembly MCP server.

Exposes these tools over stdio:
  * convert_pdftomd — PDF → Markdown (wraps the assembly-app pdf2md CLI, pdf.js)
  * convert_mdtopdf — Markdown → PDF (WeasyPrint)
  * upload_issue / issue_draft — files → a draft issue on a project's Documents tab, then issue it
    (wraps the assembly-app upload-issues CLI)
  * upload_renders — images → a project's Renders tab (wraps the assembly-app upload-renders CLI)
  * dwg_to_geomap — a Revit DWG → lines on a project's Site → Revit Maps tab (wraps the assembly-app
    upload-dwg-geomap CLI; the DWG is converted by civil-map-service)
  * product_catalogue / find_products / upload_product / upload_products — products (with variants,
    photos and spec-sheet PDFs) → the person's org product library, adding to a product that's already
    there instead of duplicating it, optionally selected on a project (wraps the assembly-app
    upload-product CLI)

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


def _run_upload_cli(script_name: str, args: list[str], child_env: dict[str, str] | None = None) -> dict:
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
        cwd=frontend, env=child_env, capture_output=True, text=True, timeout=1800,
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


# ── Saved login ──────────────────────────────────────────────────────────────────────────────────
# One file per machine, shared with the CLIs (upload/common.ts reads the same file):
#   {"_default": "<email>", "<email>": "<password>", ...}
# `_default` is who /upload acts as when no one else is named — so it asks once, never again.

_DEFAULT_KEY = "_default"


def _credentials_path() -> Path:
    env = os.environ.get("ASSEMBLY_CREDENTIALS_FILE")
    return Path(env) if env else Path.home() / ".assembly" / "credentials.json"


def _read_credentials() -> dict:
    try:
        data = json.loads(_credentials_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _saved_password(email: str) -> str | None:
    want = email.strip().lower()
    for k, v in _read_credentials().items():
        if k != _DEFAULT_KEY and k.strip().lower() == want and isinstance(v, str) and v:
            return v
    return None


def _resolve_uploader(uploader_email: str | None) -> str:
    """The named person, else the saved default; raises a 'run save_login' error when neither."""
    if uploader_email and uploader_email.strip():
        return uploader_email.strip()
    default = _read_credentials().get(_DEFAULT_KEY)
    if isinstance(default, str) and default:
        return default
    raise RuntimeError("no saved login — ask for the person's app email + password once and call save_login")


def _supabase_config(env: str) -> tuple[str, str]:
    """(url, anon key) the CLIs would use: prod from ASSEMBLY_SUPABASE_* (URL defaults to
    newapi-next), dev from the checkout's apps/frontend/.env.local."""
    if env == "prod":
        url = os.environ.get("ASSEMBLY_SUPABASE_URL", "https://newapi-next.assembly.nz")
        key = os.environ.get("ASSEMBLY_SUPABASE_ANON_KEY") or os.environ.get("ASSEMBLY_PROD_ANON_KEY")
        if not key:
            raise RuntimeError("ASSEMBLY_SUPABASE_ANON_KEY is not set for the assembly MCP server")
        return url, key
    vals: dict[str, str] = {}
    env_file = _app_dir() / "apps" / "frontend" / ".env.local"
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip("\"'")
    except OSError:
        pass
    url, key = vals.get("VITE_SUPABASE_URL"), vals.get("VITE_SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError(f"dev config not found in {env_file}")
    return url, key


def _check_sign_in(email: str, password: str, env: str) -> None:
    """Sign in once against the app's auth endpoint; raises with the server's message on failure."""
    import httpx

    url, key = _supabase_config(env)
    r = httpx.post(
        f"{url.rstrip('/')}/auth/v1/token?grant_type=password",
        headers={"apikey": key, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=30,
    )
    if r.status_code != 200:
        try:
            body = r.json()
            msg = body.get("error_description") or body.get("msg") or body.get("message") or r.text
        except ValueError:
            msg = r.text
        raise RuntimeError(f"sign-in failed for {email}: {msg}")


@mcp.tool()
def save_login(email: str, password: str, env: str = "prod", make_default: bool = True) -> dict:
    """Save a person's app login on this machine so /upload never asks again.

    Checks the email + password by signing in first; saves only if that works. By default also makes
    them the default uploader (who /upload acts as when no one else is named). Never echo the
    password back to the person.

    Args:
        email: Their app account email.
        password: Their app password.
        env: Which backend to check the login against: "prod" (default) or "dev".
        make_default: Make this person the default uploader (default true).

    Returns:
        {ok, email, default, saved_to}
    """
    _env_arg(env)
    email = email.strip()
    if "@" not in email or not password:
        raise ValueError("an email and a password are required")
    _check_sign_in(email, password, env)
    creds = {k: v for k, v in _read_credentials().items() if k.strip().lower() != email.lower() or k == _DEFAULT_KEY}
    creds[email] = password
    if make_default or not creds.get(_DEFAULT_KEY):
        creds[_DEFAULT_KEY] = email
    path = _credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(creds, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return {"ok": True, "email": email, "default": creds[_DEFAULT_KEY], "saved_to": str(path)}


@mcp.tool()
def saved_login() -> dict:
    """Who /upload will act as on this machine — call this FIRST. Never returns passwords.

    Returns:
        {default: "<email>" | null, people: ["<email>", ...]} — default null means nobody is saved
        yet: ask once for their app email + password and call `save_login`.
    """
    creds = _read_credentials()
    default = creds.get(_DEFAULT_KEY)
    people = [k for k, v in creds.items() if k != _DEFAULT_KEY and isinstance(v, str) and v]
    return {"default": default if isinstance(default, str) and default else None, "people": people}


def _uploader_env(email: str) -> dict[str, str]:
    """The child env for a CLI run as `email`: its saved password as ASSEMBLY_PASSWORD, so a stale
    ASSEMBLY_PASSWORD for someone else can never be used for this person."""
    child = dict(os.environ)
    pw = _saved_password(email)
    if pw:
        child["ASSEMBLY_PASSWORD"] = pw
    return child


@mcp.tool()
def upload_issue(
    project: str,
    issue_type: str,
    issue_name: str,
    files: list[str],
    env: str = "prod",
    dry_run: bool = False,
    uploader_email: str | None = None,
) -> dict:
    """Upload files to an assembly-app project as a DRAFT issue (a Transmittal on the Documents tab).

    Signs in as the person uploading, so it can only reach projects they are on. Never issues — call
    `issue_draft` with the returned `collectionId` once the person confirms. Run with `dry_run=True`
    first to check the project, issue type and file list without writing anything.

    Args:
        project: The project's number (e.g. "2610") or UUID.
        issue_type: The issue purpose, e.g. "For Construction", "For Information", "Review".
        issue_name: The issue's name as it should appear on the Documents tab.
        files: File and/or folder paths (folders are walked).
        env: "prod" (app.assembly.nz, default) or "dev" (dev.assembly.nz).
        dry_run: Show the plan only; no writes.
        uploader_email: Who is uploading — omit to use the saved default (see `saved_login`).

    Returns:
        {ok, uploader, project, issueType, name, collectionId, status: "draft", uploaded, failed,
        recipientChoices: [{organisation, people}]} — `recipientChoices` is who it can be issued to.
    """
    who = _resolve_uploader(uploader_email)
    args = ["--as", who, "--project", project, "--type", issue_type, "--name", issue_name]
    for f in files:
        args += ["--file", str(Path(f).expanduser().resolve())]
    args += _env_arg(env)
    if dry_run:
        args.append("--dry-run")
    return _run_upload_cli("upload-issues.ts", args, _uploader_env(who))


@mcp.tool()
def issue_draft(
    collection_id: str,
    issue_type: str,
    recipients: list[str] | None = None,
    cover_notes: str | None = None,
    env: str = "prod",
    uploader_email: str | None = None,
) -> dict:
    """Issue a draft created by `upload_issue` — allocates the next issue number. Irreversible:
    only call after the person has confirmed the issue type and recipients.

    Args:
        collection_id: `collectionId` returned by `upload_issue`.
        issue_type: The issue purpose (e.g. "For Construction").
        recipients: People ("Jane Smith") and/or organisations ("Smith Engineering" = all its
            members) from the draft's `recipientChoices`. May be empty.
        cover_notes: Optional transmittal cover notes.
        env: "prod" (default) or "dev" — must match the draft's.
        uploader_email: The person who created the draft — omit to use the saved default.

    Returns:
        {ok, collectionId, name, status: "issued", issueNumber, issueType, recipients}
    """
    who = _resolve_uploader(uploader_email)
    args = ["--issue", collection_id, "--as", who, "--type", issue_type]
    for r in recipients or []:
        args += ["--to", r]
    if cover_notes:
        args += ["--notes", cover_notes]
    args += _env_arg(env)
    return _run_upload_cli("upload-issues.ts", args, _uploader_env(who))


@mcp.tool()
def upload_renders(
    project: str,
    files: list[str],
    title: str | None = None,
    env: str = "prod",
    dry_run: bool = False,
    uploader_email: str | None = None,
) -> dict:
    """Upload render images to an assembly-app project's Renders tab, as the person uploading.

    Non-images are skipped and reported; an image already on the Renders tab (same file name) is
    skipped, so re-running is safe.

    Args:
        project: The project's number (e.g. "2610") or UUID.
        files: Image and/or folder paths (folders are walked).
        title: Name for the render — only when uploading exactly one image (default: file name).
        env: "prod" (app.assembly.nz, default) or "dev" (dev.assembly.nz).
        dry_run: Show the plan only; no writes.
        uploader_email: Who is uploading — omit to use the saved default (see `saved_login`).

    Returns:
        {ok, uploader, project, uploaded | toUpload, alreadyThere, skippedNotImages, failed}
    """
    who = _resolve_uploader(uploader_email)
    args = ["--as", who, "--project", project]
    for f in files:
        args += ["--file", str(Path(f).expanduser().resolve())]
    if title:
        args += ["--title", title]
    args += _env_arg(env)
    if dry_run:
        args.append("--dry-run")
    return _run_upload_cli("upload-renders.ts", args, _uploader_env(who))


@mcp.tool()
def dwg_to_geomap(
    project: str,
    file: str,
    name: str | None = None,
    env: str = "prod",
    dry_run: bool = False,
    uploader_email: str | None = None,
) -> dict:
    """Put a Revit DWG's linework on an assembly-app project's Site → Revit Maps tab, as the person
    uploading.

    The DWG is converted server-side (civil-map-service): its coordinate system (NZTM or the NZGD2000
    meridional circuit nearest the project's site) and units are detected automatically. Each
    drawing is stored by name; uploading the same name again REPLACES that drawing. Run with
    `dry_run=True` first: it converts the DWG and reports what would be stored, writing nothing.

    Args:
        project: The project's number (e.g. "2610"), UUID, or name (case-insensitive; an ambiguous
            name fails and lists the matching projects).
        file: Path to the .dwg (export from Revit with "Coordinate system basis: Shared").
        name: The drawing's name on the Revit Maps tab (default: the file name without .dwg).
        env: "prod" (app.assembly.nz, default) or "dev" (dev.assembly.nz).
        dry_run: Convert and show the result only; no writes.
        uploader_email: Who is uploading — omit to use the saved default (see `saved_login`).

    Returns:
        {ok, uploader, dryRun, project: {id, number, name}, drawing: {name, fileName, epsg, crsName,
        units, layers: [{name, lines}], lineCount, distanceToSiteKm}, replaced, warnings} —
        `replaced` (on a dry run: would replace) is true when a drawing with that name already
        existed; warn the person when `distanceToSiteKm` > 2 (the drawing is probably misplaced).
    """
    who = _resolve_uploader(uploader_email)
    args = ["--as", who, "--project", project, "--file", str(Path(file).expanduser().resolve())]
    if name:
        args += ["--name", name]
    args += _env_arg(env)
    if dry_run:
        args.append("--dry-run")
    return _run_upload_cli("upload-dwg-geomap.ts", args, _uploader_env(who))


def _abs_source(s: str) -> str:
    """A local file → its absolute path; an http(s) URL as given (the CLI downloads it)."""
    return s if s.lower().startswith(("http://", "https://")) else str(Path(s).expanduser().resolve())


def _resolve_product_files(spec: dict) -> dict:
    """Make every local file in one product spec absolute — photos, spec sheets and variant photos —
    since the CLI runs from the assembly-app checkout, not the caller's folder."""
    out = dict(spec)
    for key in ("images", "spec_sheets"):
        if out.get(key):
            out[key] = [_abs_source(s) for s in out[key]]
    if out.get("variants"):
        out["variants"] = [
            {**v, "images": [_abs_source(s) for s in v["images"]]} if v.get("images") else dict(v) for v in out["variants"]
        ]
    return out


def _run_with_spec(spec: dict | list | None, who: str, args: list[str]) -> dict:
    with tempfile.TemporaryDirectory(prefix="upload-product-") as tmp:
        spec_path = Path(tmp) / "products.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        return _run_upload_cli("upload-product.ts", ["--as", who, "--spec", str(spec_path), *args], _uploader_env(who))


@mcp.tool()
def product_catalogue(env: str = "prod", uploader_email: str | None = None) -> dict:
    """The product types (with their spec attributes) and leaf categories a product can be filed
    under — call before `upload_product` / `upload_products` to pick `category` / `type` / `attributes`.

    Args:
        env: "prod" (app.assembly.nz, default) or "dev".
        uploader_email: Who is asking — omit to use the saved default (see `saved_login`).

    Returns:
        {types: [{slug, name, attributes: [{key, label, type, unit, options}]}],
        categories: [{name, uniclass, path}]}
    """
    who = _resolve_uploader(uploader_email)
    return _run_upload_cli("upload-product.ts", ["--as", who, "--catalogue", *_env_arg(env)], _uploader_env(who))


@mcp.tool()
def find_products(
    query: str,
    organisation: str | None = None,
    env: str = "prod",
    uploader_email: str | None = None,
) -> dict:
    """Search the person's organisation product library — before adding, to see what's already there
    (and get a product's id for `existing_id`), or to answer "do we have X?".

    Args:
        query: Words to find in the product's name, brand, model code or website (all must match;
            "" lists the library, up to 50).
        organisation: Whose library, when the person is in several organisations.
        env: "prod" (app.assembly.nz, default) or "dev".
        uploader_email: Who is asking — omit to use the saved default (see `saved_login`).

    Returns:
        {organisation, matches: [{id, model, manufacturer, model_code, website, photos (count),
        variants: [{label, model_code}], specSheets: [file names]}], truncated}
    """
    who = _resolve_uploader(uploader_email)
    args = ["--as", who, "--find", query]
    if organisation:
        args += ["--org", organisation]
    return _run_upload_cli("upload-product.ts", [*args, *_env_arg(env)], _uploader_env(who))


@mcp.tool()
def upload_product(
    model: str,
    manufacturer: str | None = None,
    model_code: str | None = None,
    website: str | None = None,
    price: float | None = None,
    price_note: str | None = None,
    notes: str | None = None,
    suppliers: list[str] | None = None,
    category: str | None = None,
    product_type: str | None = None,
    attributes: dict | None = None,
    images: list[str] | None = None,
    variants: list[dict] | None = None,
    spec_sheets: list[str] | None = None,
    project: str | None = None,
    space: str | None = None,
    quantity: int | None = None,
    location: str | None = None,
    status: str | None = None,
    selection_notes: str | None = None,
    existing_product_id: str | None = None,
    update: str | None = None,
    organisation: str | None = None,
    env: str = "prod",
    dry_run: bool = False,
    uploader_email: str | None = None,
) -> dict:
    """Add ONE product to the person's organisation product library — with its size / colour variants,
    photos and spec-sheet PDFs — and optionally select it on a project. Signs in as the person (org
    admin/editor for the library; project admin/editor for a selection). For several products use
    `upload_products`.

    A product already in the library (same website, same brand + model code, or same brand + name) is
    never created again: what's missing is added to it instead (see `update`), and with `project` it
    is what gets selected. `similar` products are only reported — if the person says one IS this
    product, re-run with `existing_product_id`. Always `dry_run=True` first.

    Args:
        model: The product's name (e.g. "INTELLO PLUS").
        manufacturer: The brand.
        model_code: SKU / model code (of the product itself; per-size codes go on the variants).
        website: The product page URL.
        price: Price in NZD (number only).
        price_note: "rrp" or "on_request".
        notes: A short description.
        suppliers: Supplier names.
        category: A leaf category name or uniclass code (see `product_catalogue`).
        product_type: A product type slug or name (see `product_catalogue`).
        attributes: Spec values keyed by the type's attribute keys.
        images: Photo file paths and/or http(s) image URLs; the first is the cover.
        variants: Sizes / colours of this product: [{"size": "200 S"} or {"color": "Matte Black"} (one or
            both), "model_code", "price", "price_note", "source_url", "images": [...]}].
        spec_sheets: Spec-sheet / datasheet / manual PDFs — file paths and/or http(s) URLs.
        project: Also select it on this project — number (e.g. "2610"), name, or UUID.
        space: The project space (room) to put the selection in; created if new.
        quantity: Selection quantity (default 1).
        location: Where it goes (free text).
        status: Selection status: proposed (default), approved, rejected, option.
        selection_notes: Notes on the selection.
        existing_product_id: Use this library product instead of matching or creating one.
        update: For a product already in the library: "fill" (default — blank fields get a value;
            missing variants / photos / spec sheets are added), "overwrite" (also replaces the fields
            given), "none" (no field changes; missing variants / photos / spec sheets still added).
        organisation: Whose library, when the person is in several organisations.
        env: "prod" (app.assembly.nz, default) or "dev".
        dry_run: Check everything and report what would happen; no writes.
        uploader_email: Who is uploading — omit to use the saved default (see `saved_login`).

    Returns:
        {ok, dryRun, organisation, totals, products: [ONE report]} — see `upload_products`.
    """
    who = _resolve_uploader(uploader_email)
    spec = _resolve_product_files({
        "model": model,
        "manufacturer": manufacturer,
        "model_code": model_code,
        "website": website,
        "price": price,
        "price_note": price_note,
        "notes": notes,
        "suppliers": suppliers or [],
        "category": category,
        "type": product_type,
        "attributes": attributes,
        "images": images or [],
        "variants": variants or [],
        "spec_sheets": spec_sheets or [],
    })
    args: list[str] = []
    for flag, value in (
        ("--project", project),
        ("--space", space),
        ("--quantity", None if quantity is None else str(quantity)),
        ("--location", location),
        ("--status", status),
        ("--selection-notes", selection_notes),
        ("--existing", existing_product_id),
        ("--update", update),
        ("--org", organisation),
    ):
        if value:
            args += [flag, value]
    args += _env_arg(env)
    if dry_run:
        args.append("--dry-run")
    return _run_with_spec(spec, who, args)


@mcp.tool()
def upload_products(
    products: list[dict],
    organisation: str | None = None,
    env: str = "prod",
    dry_run: bool = False,
    uploader_email: str | None = None,
) -> dict:
    """Add MANY products in one go (a schedule, a supplier list, a folder of spec sheets) — one sign-in,
    one plan, one report. Each product follows the same rules as `upload_product`; a failure on one is
    reported on it and the rest still go ahead. Always `dry_run=True` first.

    Args:
        products: One dict per product: {"model" (required), "manufacturer", "model_code", "website",
            "price", "price_note", "notes", "suppliers": [...], "category", "type", "attributes": {...},
            "images": [...], "variants": [{"size" | "color", "model_code", "price", "price_note",
            "source_url", "images": [...]}], "spec_sheets": [...], "selection": {"project", "space",
            "quantity", "location", "status", "notes"}, "existing_id", "update": "fill"|"overwrite"|"none"}.
            Local file paths are made absolute here. Don't list the same product twice — merge its
            variants into one entry (a repeat only adds its selection).
        organisation: Whose library, when the person is in several organisations.
        env: "prod" (app.assembly.nz, default) or "dev".
        dry_run: Check everything and report what would happen; no writes.
        uploader_email: Who is uploading — omit to use the saved default (see `saved_login`).

    Returns:
        {ok, dryRun, organisation, totals: {products, create, addToExisting, alreadyThere, errors,
        selections}, products: [{index, action ("create" | "add to existing" | "already there" | "same
        as an earlier product" | "error"), error, product, productId, duplicateOf: {id, model, reason},
        sameAs, similar: [{id, model, manufacturer, website, reason}], update, changes: {field: value},
        photos: {add, alreadyThere}, specSheets: {add, alreadyThere}, variants: [{label, action (add |
        update), model_code, price, changes, photos}], selection: {project: {number, name}, action (add |
        update | already selected), changes, quantity, status, space: {name, created, alreadyIn}},
        failures: [{file, error}], warnings, done (after a real run)}]}
    """
    if not products:
        raise ValueError("upload_products needs at least one product")
    who = _resolve_uploader(uploader_email)
    args: list[str] = []
    if organisation:
        args += ["--org", organisation]
    args += _env_arg(env)
    if dry_run:
        args.append("--dry-run")
    return _run_with_spec({"products": [_resolve_product_files(p) for p in products]}, who, args)


def main() -> None:
    """Console-script entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
