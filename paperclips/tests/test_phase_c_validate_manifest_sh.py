"""Phase C3 Task 3: validate-manifest.sh wrapper around validate_manifest.py."""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "paperclips" / "scripts" / "validate-manifest.sh"


def test_script_exists_executable():
    assert SCRIPT.is_file()
    assert (SCRIPT.stat().st_mode & 0o111) != 0


def test_help_works():
    out = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "Usage" in out.stdout


def test_no_args_shows_usage_and_exits_nonzero():
    out = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True)
    assert out.returncode != 0


def test_uses_python_validator():
    text = SCRIPT.read_text()
    assert "validate_manifest" in text
    assert "python3" in text


def test_missing_manifest_dies():
    out = subprocess.run(
        ["bash", str(SCRIPT), "nonexistent-project-xyz"],
        capture_output=True, text=True,
    )
    assert out.returncode != 0
    assert "manifest not found" in out.stderr or "manifest not found" in out.stdout


def test_trading_manifest_rejected():
    """trading manifest still has UUIDs/paths (Phase E will clean). Wrapper must propagate failure."""
    out = subprocess.run(
        ["bash", str(SCRIPT), "trading"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert out.returncode != 0
    assert "REJECT" in (out.stdout + out.stderr)
