"""Phase D Task 4: migrate-bindings.sh --check-conflicts mode."""
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_migrate_check_conflicts_flag_supported():
    text = (REPO / "paperclips" / "scripts" / "migrate-bindings.sh").read_text()
    assert "--check-conflicts" in text, "migrate-bindings.sh must support --check-conflicts"


def test_migrate_check_conflicts_detects_disagreement(tmp_path, monkeypatch):
    """If bindings.yaml UUID differs from legacy env, --check-conflicts must report it."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # The legacy env file in the real repo has CXCTO=da97dbd9... — write bindings
    # with a DIFFERENT UUID for CXCTO so dual-read flags the conflict.
    proj = tmp_path / ".paperclip" / "projects" / "gimle"
    proj.mkdir(parents=True)
    (proj / "bindings.yaml").write_text(
        'schemaVersion: 2\n'
        'company_id: "abc"\n'
        'agents:\n'
        '  CXCTO: "different-uuid-than-legacy"\n'
    )
    out = subprocess.run(
        ["bash", str(REPO / "paperclips" / "scripts" / "migrate-bindings.sh"),
         "gimle", "--check-conflicts"],
        cwd=REPO, capture_output=True, text=True,
        env={**os.environ, "HOME": str(tmp_path)},
    )
    combined = (out.stdout + out.stderr).lower()
    assert "conflict" in combined or out.returncode != 0, \
        f"--check-conflicts did not surface disagreement: rc={out.returncode}\n{combined}"


def test_migrate_check_conflicts_clean_when_matching(tmp_path, monkeypatch):
    """If bindings UUIDs match legacy, --check-conflicts must succeed quietly."""
    monkeypatch.setenv("HOME", str(tmp_path))
    proj = tmp_path / ".paperclip" / "projects" / "gimle"
    proj.mkdir(parents=True)
    # Use the same UUID that's in the real codex-agent-ids.env for CXCTO
    (proj / "bindings.yaml").write_text(
        'schemaVersion: 2\n'
        'company_id: "abc"\n'
        'agents:\n'
        '  CXCTO: "da97dbd9-6627-48d0-b421-66af0750eacf"\n'
    )
    out = subprocess.run(
        ["bash", str(REPO / "paperclips" / "scripts" / "migrate-bindings.sh"),
         "gimle", "--check-conflicts"],
        cwd=REPO, capture_output=True, text=True,
        env={**os.environ, "HOME": str(tmp_path)},
    )
    combined = (out.stdout + out.stderr).lower()
    assert out.returncode == 0, \
        f"--check-conflicts failed on matching bindings: rc={out.returncode}\n{combined}"
    assert "conflict" not in combined or "no conflicts" in combined
