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
    out = upload_issue("2610", "For Construction", "Stage 2", [str(f)], env="dev", dry_run=True, uploader_email="a@x.nz")
    assert out["argv"] == [
        "--as", "a@x.nz", "--project", "2610", "--type", "For Construction", "--name", "Stage 2",
        "--file", str(f.resolve()), "--env", "dev", "--dry-run",
    ]


@needs_node
def test_issue_draft_maps_recipients_and_notes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSEMBLY_APP_DIR", str(_stub_cli(tmp_path, "upload-issues.ts", ECHO)))
    out = issue_draft("c1", "review", recipients=["Jane Smith", "Acme"], cover_notes="hi", uploader_email="a@x.nz")
    assert out["argv"] == [
        "--issue", "c1", "--as", "a@x.nz", "--type", "review",
        "--to", "Jane Smith", "--to", "Acme", "--notes", "hi", "--env", "prod",
    ]


@needs_node
def test_upload_renders_raises_the_cli_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = "console.error('x');\nconsole.log('RESULT ' + JSON.stringify({ ok: false, error: 'no project numbered 9' }));\nprocess.exit(1);\n"
    monkeypatch.setenv("ASSEMBLY_APP_DIR", str(_stub_cli(tmp_path, "upload-renders.ts", body)))
    with pytest.raises(RuntimeError, match="no project numbered 9"):
        upload_renders("9", [str(tmp_path)], uploader_email="a@x.nz")


@needs_node
def test_partial_failure_is_returned_not_raised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Some files failed but others uploaded: the caller needs the per-file detail, not an exception."""
    result = {"ok": False, "uploaded": ["a.png"], "failed": [{"file": "b.png", "error": "denied"}]}
    body = f"console.log('RESULT ' + JSON.stringify({json.dumps(result)}));\nprocess.exit(1);\n"
    monkeypatch.setenv("ASSEMBLY_APP_DIR", str(_stub_cli(tmp_path, "upload-renders.ts", body)))
    assert upload_renders("1", [str(tmp_path)], uploader_email="a@x.nz") == result


def test_missing_cli_names_assembly_app_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSEMBLY_APP_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="ASSEMBLY_APP_DIR"):
        upload_renders("1", [str(tmp_path)], uploader_email="a@x.nz")


def test_bad_env_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSEMBLY_APP_DIR", str(_stub_cli(tmp_path, "upload-renders.ts", ECHO)))
    with pytest.raises(ValueError, match="prod"):
        upload_renders("1", [str(tmp_path)], env="staging", uploader_email="a@x.nz")


# ── saved login ──────────────────────────────────────────────────────────────────────────────────

import assembly_mcp.server as server  # noqa: E402
from assembly_mcp.server import save_login, saved_login  # noqa: E402

# Prints the password the CLI was given, so the test can see which one reached it.
SHOW_PW = "console.log('RESULT ' + JSON.stringify({ ok: true, argv: process.argv.slice(2), pw: process.env.ASSEMBLY_PASSWORD ?? null }));\n"


@pytest.fixture(autouse=True)
def _isolated_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Never touch the real ~/.assembly/credentials.json."""
    path = tmp_path / "creds" / "credentials.json"
    monkeypatch.setenv("ASSEMBLY_CREDENTIALS_FILE", str(path))
    monkeypatch.delenv("ASSEMBLY_PASSWORD", raising=False)
    return path


def test_save_login_checks_then_saves_and_becomes_default(_isolated_credentials: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(server, "_check_sign_in", lambda e, p, env: calls.append((e, p, env)))
    out = save_login(" jo@x.nz ", "pw1")
    assert calls == [("jo@x.nz", "pw1", "prod")]
    assert out == {"ok": True, "email": "jo@x.nz", "default": "jo@x.nz", "saved_to": str(_isolated_credentials)}
    assert json.loads(_isolated_credentials.read_text()) == {"jo@x.nz": "pw1", "_default": "jo@x.nz"}
    assert saved_login() == {"default": "jo@x.nz", "people": ["jo@x.nz"]}


def test_save_login_does_not_save_a_wrong_password(_isolated_credentials: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def bad(e: str, p: str, env: str) -> None:
        raise RuntimeError("sign-in failed for jo@x.nz: Invalid login credentials")

    monkeypatch.setattr(server, "_check_sign_in", bad)
    with pytest.raises(RuntimeError, match="Invalid login"):
        save_login("jo@x.nz", "wrong")
    assert not _isolated_credentials.exists()
    assert saved_login() == {"default": None, "people": []}


def test_second_person_keeps_or_takes_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_check_sign_in", lambda e, p, env: None)
    save_login("jo@x.nz", "pw1")
    save_login("sam@x.nz", "pw2", make_default=False)
    assert saved_login() == {"default": "jo@x.nz", "people": ["jo@x.nz", "sam@x.nz"]}
    save_login("JO@x.nz", "pw3")  # re-save replaces, case-insensitively
    assert saved_login()["people"] == ["sam@x.nz", "JO@x.nz"]


@needs_node
def test_upload_uses_saved_default_and_its_password(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_check_sign_in", lambda e, p, env: None)
    save_login("jo@x.nz", "pw1")
    save_login("sam@x.nz", "pw2", make_default=False)
    monkeypatch.setenv("ASSEMBLY_APP_DIR", str(_stub_cli(tmp_path, "upload-renders.ts", SHOW_PW)))
    out = upload_renders("2610", [str(tmp_path)])
    assert out["argv"][:2] == ["--as", "jo@x.nz"] and out["pw"] == "pw1"
    out = upload_renders("2610", [str(tmp_path)], uploader_email="sam@x.nz")
    assert out["argv"][:2] == ["--as", "sam@x.nz"] and out["pw"] == "pw2"


def test_upload_without_a_saved_login_says_to_save_one(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="save_login"):
        upload_renders("2610", [str(tmp_path)])


def test_saved_login_never_returns_passwords(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_check_sign_in", lambda e, p, env: None)
    save_login("jo@x.nz", "secret-pw")
    assert "secret-pw" not in json.dumps(saved_login())
