"""Phase C3 Task 4: migrate-bindings.sh — legacy UUID extraction."""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "paperclips" / "scripts" / "migrate-bindings.sh"


def test_script_exists_executable():
    assert SCRIPT.is_file()
    assert (SCRIPT.stat().st_mode & 0o111) != 0


def test_help_works():
    out = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "Usage" in out.stdout


def test_no_args_dies():
    out = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True)
    assert out.returncode != 0


def test_missing_project_dies():
    out = subprocess.run(
        ["bash", str(SCRIPT), "nonexistent-xyz", "--dry-run"],
        capture_output=True, text=True,
    )
    assert out.returncode != 0
    assert "manifest not found" in out.stderr or "manifest not found" in out.stdout


def test_sources_lib_helpers():
    text = SCRIPT.read_text()
    assert "_common.sh" in text
    assert "_paperclip_api.sh" in text


def test_gimle_dry_run_extracts_codex_uuids(tmp_path, monkeypatch):
    """gimle's paperclips/codex-agent-ids.env has 11+ codex UUIDs; --dry-run must surface them."""
    monkeypatch.setenv("HOME", str(tmp_path))
    out = subprocess.run(
        ["bash", str(SCRIPT), "gimle", "--dry-run"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert out.returncode == 0, f"stderr: {out.stderr}"
    # Renamed entries: CX_PYTHON_ENGINEER_AGENT_ID -> CXPythonEngineer
    assert "CXPythonEngineer:" in out.stdout
    assert "CodexArchitectReviewer:" in out.stdout
    assert "schemaVersion: 2" in out.stdout


def test_dry_run_does_not_touch_filesystem(tmp_path, monkeypatch):
    """--dry-run must NOT create ~/.paperclip/projects/<key>/bindings.yaml."""
    monkeypatch.setenv("HOME", str(tmp_path))
    subprocess.run(
        ["bash", str(SCRIPT), "gimle", "--dry-run"],
        cwd=REPO, capture_output=True, text=True,
    )
    target = tmp_path / ".paperclip" / "projects" / "gimle" / "bindings.yaml"
    assert not target.exists()


def test_dry_run_output_is_sorted(tmp_path, monkeypatch):
    """Idempotency: output must have agents sorted alphabetically."""
    monkeypatch.setenv("HOME", str(tmp_path))
    out = subprocess.run(
        ["bash", str(SCRIPT), "gimle", "--dry-run"],
        cwd=REPO, capture_output=True, text=True,
    )
    agent_lines = [
        line.strip().split(":")[0]
        for line in out.stdout.splitlines()
        if line.startswith("  ") and ":" in line
    ]
    assert agent_lines == sorted(agent_lines), f"agents not sorted: {agent_lines}"
