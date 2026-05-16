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


def test_unmigrated_v1_manifest_rejected():
    """v1 manifests with inline UUIDs/paths must be rejected.

    Phase E migrated trading to v2 (clean). uaudit/gimle are still v1 with
    inline agent_id + abs paths — they must FAIL validate-manifest so the gate
    continues to enforce the schema until Phase F/G migrations.
    """
    for project in ("uaudit", "gimle"):
        out = subprocess.run(
            ["bash", str(SCRIPT), project],
            cwd=REPO, capture_output=True, text=True,
        )
        assert out.returncode != 0, \
            f"{project}: v1 manifest unexpectedly passed validate-manifest"
        assert "REJECT" in (out.stdout + out.stderr), \
            f"{project}: REJECT marker missing in output"


def test_v2_trading_manifest_accepted():
    """Phase E migrated trading must PASS validate-manifest (UUID-free, path-free, no forbidden keys)."""
    out = subprocess.run(
        ["bash", str(SCRIPT), "trading"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert out.returncode == 0, \
        f"trading v2 manifest rejected: {(out.stdout + out.stderr)[:500]}"
    assert "OK" in (out.stdout + out.stderr)
