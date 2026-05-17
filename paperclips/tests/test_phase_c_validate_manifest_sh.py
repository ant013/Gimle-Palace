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


def test_all_v2_projects_accepted():
    """Phase E migrated trading, Phase F uaudit, Phase G gimle. All 3 projects
    are now v2-clean. Validator must accept all. No v1 projects remain in repo.
    Rejection path covered by validate_manifest.py unit tests directly.
    """
    for project in ("trading", "uaudit", "gimle"):
        out = subprocess.run(
            ["bash", str(SCRIPT), project],
            cwd=REPO, capture_output=True, text=True,
        )
        assert out.returncode == 0, \
            f"{project}: v2 manifest unexpectedly rejected: {(out.stdout + out.stderr)[:300]}"
        assert "OK" in (out.stdout + out.stderr)


def test_v2_uaudit_manifest_accepted():
    """Phase F migrated uaudit must PASS validate-manifest (v2-clean)."""
    out = subprocess.run(
        ["bash", str(SCRIPT), "uaudit"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert out.returncode == 0, \
        f"uaudit v2 manifest rejected: {(out.stdout + out.stderr)[:500]}"
    assert "OK" in (out.stdout + out.stderr)


def test_v2_trading_manifest_accepted():
    """Phase E migrated trading must PASS validate-manifest (UUID-free, path-free, no forbidden keys)."""
    out = subprocess.run(
        ["bash", str(SCRIPT), "trading"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert out.returncode == 0, \
        f"trading v2 manifest rejected: {(out.stdout + out.stderr)[:500]}"
    assert "OK" in (out.stdout + out.stderr)
