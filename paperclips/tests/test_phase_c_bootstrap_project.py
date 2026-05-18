"""Phase C2: bootstrap-project.sh structural validation.

Per spec §9.2 — 13 steps, idempotent, journal-snapshotted, topological hire,
2-stage canary. Live execution requires real paperclip API. Tests verify
script structure + arg-parsing only.
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "paperclips" / "scripts" / "bootstrap-project.sh"


def test_script_exists_executable():
    assert SCRIPT.is_file()
    assert (SCRIPT.stat().st_mode & 0o111) != 0


def test_help_works():
    out = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "bootstrap" in out.stdout.lower()


def test_validates_manifest_first():
    text = SCRIPT.read_text()
    assert "validate-manifest.sh" in text or "validate_manifest" in text


def test_uses_topological_order():
    text = SCRIPT.read_text()
    assert "reportsTo" in text or "topological" in text.lower()


def test_supports_canary_flag():
    text = SCRIPT.read_text()
    assert "--canary" in text


def test_calls_bootstrap_watchdog_at_end():
    text = SCRIPT.read_text()
    assert "bootstrap-watchdog.sh" in text


def test_journal_snapshot_before_mutations():
    text = SCRIPT.read_text()
    assert "journal_open" in text


def test_supports_reuse_bindings():
    text = SCRIPT.read_text()
    assert "--reuse-bindings" in text


def test_sources_all_4_libs():
    text = SCRIPT.read_text()
    for lib in ["_common.sh", "_paperclip_api.sh", "_journal.sh", "_prompts.sh"]:
        assert lib in text, f"missing lib source: {lib}"


def test_fails_without_project_key():
    out = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True)
    assert out.returncode != 0
    assert "project-key required" in out.stderr or "project-key" in out.stderr.lower()
