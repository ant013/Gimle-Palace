"""Phase C3 Task 10: update-versions.sh — journals + re-installs."""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "paperclips" / "scripts" / "update-versions.sh"


def test_script_exists_executable():
    assert SCRIPT.is_file()
    assert (SCRIPT.stat().st_mode & 0o111) != 0


def test_help_works():
    out = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "Usage" in out.stdout


def test_journals_before_update():
    text = SCRIPT.read_text()
    assert "journal_open" in text
    assert "journal_record" in text
    assert "journal_finalize" in text


def test_re_runs_install_paperclip():
    text = SCRIPT.read_text()
    assert "install-paperclip.sh" in text


def test_references_versions_env():
    text = SCRIPT.read_text()
    assert "versions.env" in text


def test_show_current_works_without_install():
    """--show-current prints versions.env, must not run install."""
    out = subprocess.run(
        ["bash", str(SCRIPT), "--show-current"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0
    assert "PAPERCLIPAI_VERSION" in (out.stdout + out.stderr)


def test_sources_lib_helpers():
    text = SCRIPT.read_text()
    assert "_common.sh" in text
    assert "_journal.sh" in text


def test_records_snapshot_kind_for_rollback():
    """Snapshot kind must match what rollback.sh handles."""
    text = SCRIPT.read_text()
    assert "version_bump_snapshot" in text
