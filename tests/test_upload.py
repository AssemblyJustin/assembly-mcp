"""Offline tests for the upload tools: they shell out to the assembly-app upload CLIs and return the
CLI's `RESULT {json}` line. A stub CLI stands in for the real one (no network, no sign-in)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from assembly_mcp.server import issue_draft, upload_issue, upload_renders

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")


def _stub_cli(tmp_path: Path, name: str, body: str) -> Path:
    script = tmp_path / "apps" / "frontend" / "scripts" / name
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(body, encoding="utf-8")
    return tmp_path


# Echoes its argv back as the result, after a human progress line.
ECHO = "console.log('progress');\nconsole.log('RESULT ' + JSON.stringify({ ok: true, argv: process.argv.slice(2) }));\n"


@needs_node
def test_upload_issue_passes_inputs_as_flags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSEMBLY_APP_DIR", str(_stub_cli(tmp_path, "upload-issues.ts", ECHO)))
    f = tmp_path / "a.pdf"
    f.write_text("x")
    out = upload_issue("a@x.nz", "2610", "For Construction", "Stage 2", [str(f)], env="dev", dry_run=True)
    assert out["argv"] == [
        "--as", "a@x.nz", "--project", "2610", "--type", "For Construction", "--name", "Stage 2",
        "--file", str(f.resolve()), "--env", "dev", "--dry-run",
    ]


@needs_node
def test_issue_draft_maps_recipients_and_notes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSEMBLY_APP_DIR", str(_stub_cli(tmp_path, "upload-issues.ts", ECHO)))
    out = issue_draft("a@x.nz", "c1", "review", recipients=["Jane Smith", "Acme"], cover_notes="hi")
    assert out["argv"] == [
        "--issue", "c1", "--as", "a@x.nz", "--type", "review",
        "--to", "Jane Smith", "--to", "Acme", "--notes", "hi", "--env", "prod",
    ]


@needs_node
def test_upload_renders_raises_the_cli_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = "console.error('x');\nconsole.log('RESULT ' + JSON.stringify({ ok: false, error: 'no project numbered 9' }));\nprocess.exit(1);\n"
    monkeypatch.setenv("ASSEMBLY_APP_DIR", str(_stub_cli(tmp_path, "upload-renders.ts", body)))
    with pytest.raises(RuntimeError, match="no project numbered 9"):
        upload_renders("a@x.nz", "9", [str(tmp_path)])


@needs_node
def test_partial_failure_is_returned_not_raised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Some files failed but others uploaded: the caller needs the per-file detail, not an exception."""
    result = {"ok": False, "uploaded": ["a.png"], "failed": [{"file": "b.png", "error": "denied"}]}
    body = f"console.log('RESULT ' + JSON.stringify({json.dumps(result)}));\nprocess.exit(1);\n"
    monkeypatch.setenv("ASSEMBLY_APP_DIR", str(_stub_cli(tmp_path, "upload-renders.ts", body)))
    assert upload_renders("a@x.nz", "1", [str(tmp_path)]) == result


def test_missing_cli_names_assembly_app_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSEMBLY_APP_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="ASSEMBLY_APP_DIR"):
        upload_renders("a@x.nz", "1", [str(tmp_path)])


def test_bad_env_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSEMBLY_APP_DIR", str(_stub_cli(tmp_path, "upload-renders.ts", ECHO)))
    with pytest.raises(ValueError, match="prod"):
        upload_renders("a@x.nz", "1", [str(tmp_path)], env="staging")
