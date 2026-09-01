"""Behavior tests for the Glitcherry single-slice worktree controller."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
CONTROLLER = (
    REPO
    / "paperclips"
    / "projects"
    / "glitcherry-android"
    / "scripts"
    / "slice-worktree.py"
)


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def _remote(tmp_path: Path, name: str) -> tuple[Path, Path]:
    source = tmp_path / f"{name}-source"
    bare = tmp_path / f"{name}.git"
    source.mkdir(parents=True)
    _git("init", "--initial-branch=develop", cwd=source)
    _git("config", "user.name", "Test User", cwd=source)
    _git("config", "user.email", "test@example.com", cwd=source)
    (source / "AGENTS.md").write_text(f"# {name} rules\n")
    (source / "README.md").write_text(f"# {name}\n")
    _git("add", ".", cwd=source)
    _git("commit", "-m", "fixture", cwd=source)
    _git("clone", "--bare", str(source), str(bare), cwd=tmp_path)
    return bare, source


def _fixture(tmp_path: Path) -> dict[str, Path]:
    android_remote, _ = _remote(tmp_path, "Glitcherry-Android")
    control_remote, _ = _remote(tmp_path, "Glitcherry")
    primary = tmp_path / "canonical-android"
    control = tmp_path / "canonical-control"
    _git("clone", "--branch", "develop", str(android_remote), str(primary), cwd=tmp_path)
    _git("clone", "--branch", "develop", str(control_remote), str(control), cwd=tmp_path)
    for repo in (primary, control):
        _git("config", "user.name", "Test User", cwd=repo)
        _git("config", "user.email", "test@example.com", cwd=repo)

    worktrees = tmp_path / "slice-worktrees"
    states = tmp_path / "slice-state"
    worktrees.mkdir()
    states.mkdir()
    paths = tmp_path / "paths.yaml"
    paths.write_text(
        f"""\
schemaVersion: 2
primary_repo_root: {primary}
control_repo_root: {control}
task_worktree_root: {worktrees}
task_state_root: {states}
slice_lease_seconds: 60
android_repository_url: {android_remote}
control_repository_url: {control_remote}
"""
    )
    paths.chmod(0o600)
    return {
        "android_remote": android_remote,
        "control_remote": control_remote,
        "primary": primary,
        "control": control,
        "worktrees": worktrees,
        "states": states,
        "paths": paths,
    }


def _run(
    fixture: dict[str, Path], *args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(CONTROLLER),
            "--paths",
            str(fixture["paths"]),
            "--allow-local-test-remotes",
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(fixture["paths"].parent / "home")},
    )


def _create(fixture: dict[str, Path]) -> dict:
    result = _run(
        fixture,
        "create",
        "--issue-id",
        "00000000-0000-4000-8000-000000000123",
        "--issue-key",
        "GLA-123",
        "--slug",
        "single-worktree",
        "--owner",
        "GlitcherryCTO",
        "--run-id",
        "run-cto-0",
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _state(fixture: dict[str, Path]) -> dict:
    return json.loads((fixture["states"] / "GLA-123.json").read_text())


def _handoff(
    fixture: dict[str, Path], owner: str, run_id: str, next_owner: str, phase: str
) -> subprocess.CompletedProcess[str]:
    return _run(
        fixture,
        "handoff",
        "--issue-key",
        "GLA-123",
        "--owner",
        owner,
        "--run-id",
        run_id,
        "--next-owner",
        next_owner,
        "--next-phase",
        phase,
    )


def _claim(
    fixture: dict[str, Path], owner: str, run_id: str
) -> subprocess.CompletedProcess[str]:
    return _run(
        fixture,
        "claim",
        "--issue-key",
        "GLA-123",
        "--owner",
        owner,
        "--run-id",
        run_id,
    )


def _route_to_implementation(
    fixture: dict[str, Path],
) -> tuple[Path, str]:
    worktree = Path(_state(fixture)["worktree_path"])
    assert _handoff(
        fixture,
        "GlitcherryCTO",
        "run-cto-0",
        "GlitcherryCodeReviewer",
        "spec_review",
    ).returncode == 0
    assert _claim(fixture, "GlitcherryCodeReviewer", "run-spec-review").returncode == 0
    assert _handoff(
        fixture,
        "GlitcherryCodeReviewer",
        "run-spec-review",
        "GlitcherryCTO",
        "plan",
    ).returncode == 0
    assert _claim(fixture, "GlitcherryCTO", "run-plan").returncode == 0
    assert _handoff(
        fixture,
        "GlitcherryCTO",
        "run-plan",
        "GlitcherryCodeReviewer",
        "plan_review",
    ).returncode == 0
    assert _claim(fixture, "GlitcherryCodeReviewer", "run-plan-review").returncode == 0
    assert _handoff(
        fixture,
        "GlitcherryCodeReviewer",
        "run-plan-review",
        "GlitcherryCTO",
        "implementation_routing",
    ).returncode == 0
    assert _claim(fixture, "GlitcherryCTO", "run-routing").returncode == 0
    assert _handoff(
        fixture,
        "GlitcherryCTO",
        "run-routing",
        "GlitcherryAndroidEngineer",
        "implementation",
    ).returncode == 0
    engineer_run = "run-engineer-0"
    assert _claim(
        fixture, "GlitcherryAndroidEngineer", engineer_run
    ).returncode == 0
    return worktree, engineer_run


def _route_to_code_review(fixture: dict[str, Path]) -> tuple[Path, str]:
    worktree, engineer_run = _route_to_implementation(fixture)
    (worktree / "implementation.txt").write_text("reviewable\n")
    _git("add", ".", cwd=worktree)
    _git("commit", "-m", "GLA-123 implementation", cwd=worktree)
    assert _handoff(
        fixture,
        "GlitcherryAndroidEngineer",
        engineer_run,
        "GlitcherryCodeReviewer",
        "code_review",
    ).returncode == 0
    reviewer_run = "run-review-0"
    assert _claim(
        fixture, "GlitcherryCodeReviewer", reviewer_run
    ).returncode == 0
    return worktree, reviewer_run


def test_create_handoff_and_claim_enforce_single_owner(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    created = _create(fixture)

    worktree = Path(created["worktree_path"])
    state_path = fixture["states"] / "GLA-123.json"
    assert worktree.is_dir()
    assert state_path.stat().st_mode & 0o777 == 0o600
    assert _git("branch", "--show-current", cwd=worktree).stdout.strip() == (
        "feature/GLA-123-single-worktree"
    )

    overlap = _claim(fixture, "GlitcherryAndroidEngineer", "run-android-overlap")
    assert overlap.returncode != 0
    assert "active lease" in overlap.stderr.lower()

    handoff = _handoff(
        fixture,
        "GlitcherryCTO",
        "run-cto-0",
        "GlitcherryCodeReviewer",
        "spec_review",
    )
    assert handoff.returncode == 0, handoff.stderr
    claimed = _claim(fixture, "GlitcherryCodeReviewer", "run-review-1")
    assert claimed.returncode == 0, claimed.stderr
    state = _state(fixture)
    assert state["lease"]["owner"] == "GlitcherryCodeReviewer"
    assert state["phase"] == "spec_review"


def test_handoff_refuses_dirty_tree_and_preserves_changes(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    created = _create(fixture)
    worktree = Path(created["worktree_path"])
    dirty = worktree / "unfinished.txt"
    dirty.write_text("keep me\n")

    result = _handoff(
        fixture,
        "GlitcherryCTO",
        "run-cto-0",
        "GlitcherryCodeReviewer",
        "spec_review",
    )

    assert result.returncode != 0
    assert "dirty" in result.stderr.lower()
    assert dirty.read_text() == "keep me\n"
    assert _state(fixture)["lease"]["owner"] == "GlitcherryCTO"


def test_recovery_requires_exact_run_and_preserves_dirty_work(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    created = _create(fixture)
    dirty = Path(created["worktree_path"]) / "unfinished.txt"
    dirty.write_text("must survive recovery\n")

    wrong = _run(
        fixture,
        "recover",
        "--issue-key",
        "GLA-123",
        "--expected-owner",
        "GlitcherryCTO",
        "--expected-run-id",
        "run-cto-0",
        "--terminated-run-id",
        "some-other-run",
        "--operator",
        "GlitcherryCTO",
        "--evidence",
        "exact watchdog evidence",
    )
    assert wrong.returncode != 0
    assert _state(fixture)["lease"]["run_id"] == "run-cto-0"

    recovered = _run(
        fixture,
        "recover",
        "--issue-key",
        "GLA-123",
        "--expected-owner",
        "GlitcherryCTO",
        "--expected-run-id",
        "run-cto-0",
        "--terminated-run-id",
        "run-cto-0",
        "--operator",
        "GlitcherryCTO",
        "--evidence",
        "exact watchdog run and PID evidence",
    )
    assert recovered.returncode == 0, recovered.stderr
    assert dirty.read_text() == "must survive recovery\n"
    state = _state(fixture)
    assert state["phase"] == "recovery"
    assert state["expected_owner"] == "GlitcherryCTO"
    assert state["recovery_resume_phase"] == "spec"


def test_review_rejection_ceiling_stops_fourth_cycle(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _create(fixture)
    worktree, reviewer_run = _route_to_code_review(fixture)
    for cycle in range(1, 4):
        rejected = _run(
            fixture,
            "reject",
            "--issue-key",
            "GLA-123",
            "--owner",
            "GlitcherryCodeReviewer",
            "--run-id",
            reviewer_run,
            "--next-owner",
            "GlitcherryAndroidEngineer",
        )
        assert rejected.returncode == 0, rejected.stderr
        assert _state(fixture)["review_rejections"] == cycle

        engineer_run = f"run-engineer-{cycle}"
        assert _claim(
            fixture, "GlitcherryAndroidEngineer", engineer_run
        ).returncode == 0
        (worktree / f"fix-{cycle}.txt").write_text(f"fix {cycle}\n")
        _git("add", ".", cwd=worktree)
        _git("commit", "-m", f"GLA-123 fix {cycle}", cwd=worktree)
        assert _handoff(
            fixture,
            "GlitcherryAndroidEngineer",
            engineer_run,
            "GlitcherryCodeReviewer",
            "code_review",
        ).returncode == 0
        reviewer_run = f"run-review-{cycle}"
        assert _claim(
            fixture, "GlitcherryCodeReviewer", reviewer_run
        ).returncode == 0

    fourth = _run(
        fixture,
        "reject",
        "--issue-key",
        "GLA-123",
        "--owner",
        "GlitcherryCodeReviewer",
        "--run-id",
        reviewer_run,
        "--next-owner",
        "GlitcherryAndroidEngineer",
    )
    assert fourth.returncode != 0
    assert "three" in fourth.stderr.lower()
    assert _state(fixture)["review_rejections"] == 3

    approved = _run(
        fixture,
        "approve",
        "--issue-key",
        "GLA-123",
        "--owner",
        "GlitcherryCodeReviewer",
        "--run-id",
        reviewer_run,
        "--next-owner",
        "GlitcherryCTO",
    )
    assert approved.returncode == 0, approved.stderr


def _approve_for_merge(
    fixture: dict[str, Path], worktree: Path, engineer_run: str
) -> None:
    _git("push", "-u", "origin", "feature/GLA-123-single-worktree", cwd=worktree)
    assert _handoff(
        fixture,
        "GlitcherryAndroidEngineer",
        engineer_run,
        "GlitcherryCodeReviewer",
        "code_review",
    ).returncode == 0
    assert _claim(fixture, "GlitcherryCodeReviewer", "run-review").returncode == 0
    approved = _run(
        fixture,
        "approve",
        "--issue-key",
        "GLA-123",
        "--owner",
        "GlitcherryCodeReviewer",
        "--run-id",
        "run-review",
        "--next-owner",
        "GlitcherryCTO",
    )
    assert approved.returncode == 0, approved.stderr
    assert _claim(fixture, "GlitcherryCTO", "run-cto-merge").returncode == 0


def _merge_control_status(
    fixture: dict[str, Path], android_merge: str
) -> tuple[str, str]:
    control = fixture["control"]
    branch = "docs/status-GLA-123"
    _git("switch", "-c", branch, cwd=control)
    (control / "status.txt").write_text(f"GLA-123 + {android_merge}\n")
    _git("add", "status.txt", cwd=control)
    _git("commit", "-m", f"GLA-123 status for {android_merge}", cwd=control)
    reviewed_head = _git("rev-parse", "HEAD", cwd=control).stdout.strip()
    _git("push", "-u", "origin", branch, cwd=control)
    _git("switch", "develop", cwd=control)
    _git("merge", "--squash", branch, cwd=control)
    _git("commit", "-m", f"GLA-123 status for {android_merge}", cwd=control)
    _git("push", "origin", "develop", cwd=control)
    merge_sha = _git("rev-parse", "HEAD", cwd=control).stdout.strip()
    return reviewed_head, merge_sha


def test_cleanup_requires_both_merge_records_and_removes_exact_refs(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _create(fixture)
    worktree, engineer_run = _route_to_implementation(fixture)
    (worktree / "feature.txt").write_text("reviewed result\n")
    _git("add", ".", cwd=worktree)
    _git("commit", "-m", "GLA-123 implementation", cwd=worktree)
    _approve_for_merge(fixture, worktree, engineer_run)

    branch = "feature/GLA-123-single-worktree"
    _git("merge", "--squash", branch, cwd=fixture["primary"])
    _git("commit", "-m", "GLA-123 squash merge", cwd=fixture["primary"])
    _git("push", "origin", "develop", cwd=fixture["primary"])
    android_merge = _git("rev-parse", "HEAD", cwd=fixture["primary"]).stdout.strip()
    _, control_merge = _merge_control_status(fixture, android_merge)

    android = _run(
        fixture,
        "record-merge",
        "--issue-key",
        "GLA-123",
        "--owner",
        "GlitcherryCTO",
        "--run-id",
        "run-cto-merge",
        "--kind",
        "android",
        "--sha",
        android_merge,
        "--pr-number",
        "123",
    )
    assert android.returncode == 0, android.stderr
    control = _run(
        fixture,
        "record-merge",
        "--issue-key",
        "GLA-123",
        "--owner",
        "GlitcherryCTO",
        "--run-id",
        "run-cto-merge",
        "--kind",
        "control",
        "--sha",
        control_merge,
    )
    assert control.returncode == 0, control.stderr

    cleaned = _run(
        fixture,
        "cleanup",
        "--issue-key",
        "GLA-123",
        "--owner",
        "GlitcherryCTO",
        "--run-id",
        "run-cto-merge",
    )
    assert cleaned.returncode == 0, cleaned.stderr
    assert not worktree.exists()
    assert _git(
        "show-ref", "--verify", f"refs/heads/{branch}", cwd=fixture["primary"], check=False
    ).returncode != 0
    assert _git(
        "ls-remote", "--exit-code", "--heads", "origin", branch,
        cwd=fixture["primary"], check=False,
    ).returncode != 0
    assert _git(
        "show-ref",
        "--verify",
        "refs/heads/docs/status-GLA-123",
        cwd=fixture["control"],
        check=False,
    ).returncode != 0
    assert _git(
        "ls-remote",
        "--exit-code",
        "--heads",
        "origin",
        "docs/status-GLA-123",
        cwd=fixture["control"],
        check=False,
    ).returncode != 0
    assert _state(fixture)["phase"] == "cleaned"


def test_record_android_merge_refuses_unreachable_sha(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _create(fixture)
    worktree, engineer_run = _route_to_implementation(fixture)
    (worktree / "feature.txt").write_text("reviewed result\n")
    _git("add", ".", cwd=worktree)
    _git("commit", "-m", "GLA-123 implementation", cwd=worktree)
    _approve_for_merge(fixture, worktree, engineer_run)

    wrong_sha = _git("rev-parse", "HEAD", cwd=worktree).stdout.strip()

    result = _run(
        fixture,
        "record-merge",
        "--issue-key",
        "GLA-123",
        "--owner",
        "GlitcherryCTO",
        "--run-id",
        "run-cto-merge",
        "--kind",
        "android",
        "--sha",
        wrong_sha,
        "--pr-number",
        "123",
    )
    assert result.returncode != 0
    assert "not reachable" in result.stderr.lower()
    assert worktree.exists()
