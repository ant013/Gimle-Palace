from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "paperclips" / "scripts" / "migrate_path_to_file_path.sh"


def test_script_exists() -> None:
    assert SCRIPT.is_file()


def test_help_lists_expected_flags() -> None:
    out = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "--apply-step-1" in out.stdout
    assert "--apply-step-3" in out.stdout
    assert "--rollback-snapshot" in out.stdout


def test_dry_run_without_action_prints_plan() -> None:
    out = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0
    assert "coalesce(n.file_path, n.path)" in out.stdout
    assert "SET n.file_path = n.path" in out.stdout
    assert "REMOVE n.path" in out.stdout


def test_step1_dry_run_renders_apoc_iterate() -> None:
    out = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run", "--apply-step-1"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0
    assert "apoc.periodic.iterate" in out.stdout
    assert "SET n.file_path = n.path" in out.stdout


def test_step3_dry_run_renders_path_removal() -> None:
    out = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run", "--apply-step-3"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0
    assert "REMOVE n.path" in out.stdout


def test_rollback_dry_run_renders_neo4j_admin_command() -> None:
    out = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--dry-run",
            "--rollback-snapshot",
            "/tmp/pre-migration.dump",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0
    assert "neo4j-admin database load" in out.stdout
    assert "/tmp/pre-migration.dump" in out.stdout
