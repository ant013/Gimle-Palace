"""Behavior tests for the Glitcherry persistent runtime workspace preparer."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = (
    REPO
    / "paperclips"
    / "projects"
    / "glitcherry-android"
    / "scripts"
    / "prepare-runtime-workspaces.sh"
)


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_bare_remote(tmp_path: Path, name: str, marker: str) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    work = tmp_path / f"{name}-source"
    bare = tmp_path / f"{name}.git"
    work.mkdir()
    _git("init", "--initial-branch=develop", cwd=work)
    _git("config", "user.name", "Test User", cwd=work)
    _git("config", "user.email", "test@example.com", cwd=work)
    (work / "AGENTS.md").write_text(f"# {marker} repository rules\n")
    (work / "README.md").write_text(f"# {marker}\n")
    _git("add", "AGENTS.md", "README.md", cwd=work)
    _git("commit", "-m", "fixture", cwd=work)
    _git("clone", "--bare", str(work), str(bare), cwd=tmp_path)
    return bare, work


def _write_private(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o600)


def _fixture(tmp_path: Path) -> dict[str, Path]:
    android_remote, android_source = _make_bare_remote(
        tmp_path, "Glitcherry-Android", "android"
    )
    control_remote, _ = _make_bare_remote(tmp_path, "Glitcherry", "control")
    team_root = tmp_path / "runs"
    for name in ("GlitcherryCTO", "GlitcherryAndroidEngineer"):
        workspace = team_root / name / "workspace"
        workspace.mkdir(parents=True)
        (workspace / "AGENTS.md").write_text(f"generated role for {name}\n")

    manifest = tmp_path / "paperclip-agent-assembly.yaml"
    manifest.write_text(
        """\
schemaVersion: 2
project:
  integration_branch: develop
agents:
  - agent_name: GlitcherryCTO
    workflow_role: inner_orchestrator
  - agent_name: GlitcherryAndroidEngineer
    workflow_role: implementer
"""
    )
    paths = tmp_path / "paths.yaml"
    _write_private(
        paths,
        f"""\
schemaVersion: 2
team_workspace_root: {team_root}
android_repository_url: {android_remote}
control_repository_url: {control_remote}
""",
    )
    bindings = tmp_path / "bindings.yaml"
    _write_private(
        bindings,
        """\
schemaVersion: 2
company_id: 00000000-0000-4000-8000-000000000001
agents:
  GlitcherryCTO: 00000000-0000-4000-8000-000000000002
  GlitcherryAndroidEngineer: 00000000-0000-4000-8000-000000000003
""",
    )
    return {
        "android_remote": android_remote,
        "android_source": android_source,
        "control_remote": control_remote,
        "team_root": team_root,
        "manifest": manifest,
        "paths": paths,
        "bindings": bindings,
    }


def _run(fixture: dict[str, Path], *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--manifest",
            str(fixture["manifest"]),
            "--paths",
            str(fixture["paths"]),
            "--bindings",
            str(fixture["bindings"]),
            "--allow-local-test-remotes",
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(fixture["team_root"].parent / "home")},
    )


def test_preparer_is_idempotent_and_keeps_tracked_agents_unchanged(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    expected_agents_hash = _sha256(fixture["android_source"] / "AGENTS.md")

    first = _run(fixture)
    assert first.returncode == 0, first.stderr

    android_repos = [
        fixture["team_root"] / name / "workspace" / "repo"
        for name in ("GlitcherryCTO", "GlitcherryAndroidEngineer")
    ]
    control_repo = fixture["team_root"] / "GlitcherryCTO" / "workspace" / "control"
    git_dir_inodes = [(repo / ".git").stat().st_ino for repo in android_repos]

    for repo in android_repos:
        assert _sha256(repo / "AGENTS.md") == expected_agents_hash
        assert _git("status", "--porcelain", cwd=repo).stdout == ""
        assert _git("branch", "--show-current", cwd=repo).stdout.strip() == "develop"
    assert (control_repo / ".git").is_dir()

    second = _run(fixture)
    assert second.returncode == 0, second.stderr
    assert [(repo / ".git").stat().st_ino for repo in android_repos] == git_dir_inodes
    for repo in android_repos:
        assert _sha256(repo / "AGENTS.md") == expected_agents_hash
        assert _git("status", "--porcelain", cwd=repo).stdout == ""


def test_preparer_refuses_wrong_origin_without_disclosing_it(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    first = _run(fixture)
    assert first.returncode == 0, first.stderr

    wrong_remote, _ = _make_bare_remote(tmp_path, "Wrong-Android", "wrong")
    _write_private(
        fixture["paths"],
        f"""\
schemaVersion: 2
team_workspace_root: {fixture['team_root']}
android_repository_url: {wrong_remote}
control_repository_url: {fixture['control_remote']}
""",
    )

    result = _run(fixture)
    assert result.returncode != 0
    assert "origin does not match" in result.stderr.lower()
    assert str(fixture["android_remote"]) not in result.stderr
    assert str(wrong_remote) not in result.stderr


def test_preparer_refuses_dirty_repository(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    first = _run(fixture)
    assert first.returncode == 0, first.stderr
    repo = fixture["team_root"] / "GlitcherryAndroidEngineer" / "workspace" / "repo"
    (repo / "README.md").write_text("dirty\n")

    result = _run(fixture)
    assert result.returncode != 0
    assert "dirty" in result.stderr.lower()
    assert (repo / "README.md").read_text() == "dirty\n"


def test_preparer_refuses_unmanaged_and_stale_repository(tmp_path: Path) -> None:
    unmanaged_fixture = _fixture(tmp_path / "unmanaged")
    unmanaged_repo = (
        unmanaged_fixture["team_root"]
        / "GlitcherryAndroidEngineer"
        / "workspace"
        / "repo"
    )
    unmanaged_repo.mkdir()
    (unmanaged_repo / "keep.txt").write_text("do not delete\n")

    unmanaged = _run(unmanaged_fixture)
    assert unmanaged.returncode != 0
    assert "unmanaged" in unmanaged.stderr.lower()
    assert (unmanaged_repo / "keep.txt").read_text() == "do not delete\n"

    stale_fixture = _fixture(tmp_path / "stale")
    first = _run(stale_fixture)
    assert first.returncode == 0, first.stderr
    source = stale_fixture["android_source"]
    (source / "README.md").write_text("new remote head\n")
    _git("add", "README.md", cwd=source)
    _git("commit", "-m", "advance develop", cwd=source)
    _git("push", str(stale_fixture["android_remote"]), "develop", cwd=source)

    stale = _run(stale_fixture)
    assert stale.returncode != 0
    assert "current develop" in stale.stderr.lower()


def test_local_remotes_require_explicit_test_flag_and_no_workspace_source_key(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    text = SCRIPT.read_text() if SCRIPT.exists() else ""
    forbidden_key = "workspace_git" + "_source_path_key"
    assert forbidden_key not in text
    assert forbidden_key not in fixture["manifest"].read_text()
    actual_manifest = (
        REPO
        / "paperclips"
        / "projects"
        / "glitcherry-android"
        / "paperclip-agent-assembly.yaml"
    )
    assert forbidden_key not in actual_manifest.read_text()

    result = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--manifest",
            str(fixture["manifest"]),
            "--paths",
            str(fixture["paths"]),
            "--bindings",
            str(fixture["bindings"]),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "allowlisted github" in result.stderr.lower()


def test_host_local_paths_and_bindings_must_be_private(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture["bindings"].chmod(0o644)

    result = _run(fixture)

    assert result.returncode != 0
    assert "bindings file must be owner-controlled and mode 600" in result.stderr
    assert "00000000-0000-4000-8000-000000000001" not in result.stderr
