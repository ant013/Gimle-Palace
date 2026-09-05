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
    worktree = fixture["worktrees"] / "feature" / "GLA-123-single-worktree"
    worktree.parent.mkdir(exist_ok=True)
    base_sha = _git("rev-parse", "origin/develop", cwd=fixture["primary"]).stdout.strip()
    _git(
        "worktree",
        "add",
        "-b",
        "feature/GLA-123-single-worktree",
        str(worktree),
        base_sha,
        cwd=fixture["primary"],
    )
    result = _run(
        fixture,
        "adopt",
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
        "--project-workspace-id",
        "00000000-0000-4000-8000-000000000124",
        "--execution-workspace-id",
        "00000000-0000-4000-8000-000000000125",
        "--worktree-path",
        str(worktree),
        "--branch",
        "feature/GLA-123-single-worktree",
        "--base-sha",
        base_sha,
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


def _block(
    fixture: dict[str, Path], owner: str, run_id: str
) -> subprocess.CompletedProcess[str]:
    return _run(
        fixture,
        "block",
        "--issue-key",
        "GLA-123",
        "--owner",
        owner,
        "--run-id",
        run_id,
        "--reason",
        "LOCAL_BLOCKED: bounded fixture decision is required",
    )


def _resume_blocked(
    fixture: dict[str, Path],
    next_owner: str,
    next_phase: str,
    *,
    operator: str = "GlitcherryCTO",
    run_id: str = "run-cto-resume",
    evidence: str = "answered interaction fixture-decision-123",
) -> subprocess.CompletedProcess[str]:
    return _run(
        fixture,
        "resume-blocked",
        "--issue-key",
        "GLA-123",
        "--operator",
        operator,
        "--run-id",
        run_id,
        "--next-owner",
        next_owner,
        "--next-phase",
        next_phase,
        "--evidence",
        evidence,
    )


def _adopt_recovery_checkpoint(
    fixture: dict[str, Path],
    old_head: str,
    new_head: str,
    *,
    operator: str = "GlitcherryCTO",
    run_id: str = "run-cto-adopt",
    evidence: str = "Board approved retained checkpoint after exact terminated run",
) -> subprocess.CompletedProcess[str]:
    return _run(
        fixture,
        "adopt-recovery-checkpoint",
        "--issue-key",
        "GLA-123",
        "--operator",
        operator,
        "--run-id",
        run_id,
        "--expected-old-head",
        old_head,
        "--new-head",
        new_head,
        "--evidence",
        evidence,
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


def _recover_advanced_checkpoint(
    fixture: dict[str, Path],
) -> tuple[Path, str, str, str]:
    _create(fixture)
    worktree, engineer_run = _route_to_implementation(fixture)
    old_head = _state(fixture)["head_sha"]
    checkpoint = worktree / "retained-checkpoint.txt"
    checkpoint.write_text("bounded implementation checkpoint\n")
    _git("add", checkpoint.name, cwd=worktree)
    _git("commit", "-m", "GLA-123 retain implementation checkpoint", cwd=worktree)
    new_head = _git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
    state_path = fixture["states"] / "GLA-123.json"
    legacy_state = _state(fixture)
    legacy_state["lease"] = {
        "owner": "GlitcherryAndroidEngineer",
        "run_id": engineer_run,
        "expires_at": "2099-01-01T00:00:00Z",
    }
    state_path.write_text(json.dumps(legacy_state, indent=2, sort_keys=True) + "\n")
    state_path.chmod(0o600)
    recovered = _run(
        fixture,
        "recover",
        "--issue-key",
        "GLA-123",
        "--expected-owner",
        "GlitcherryAndroidEngineer",
        "--expected-run-id",
        engineer_run,
        "--terminated-run-id",
        engineer_run,
        "--operator",
        "GlitcherryCTO",
        "--evidence",
        "Paperclip run terminated and environment lease released",
    )
    assert recovered.returncode == 0, recovered.stderr
    return worktree, old_head, new_head, engineer_run


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


def test_adopt_handoff_and_claim_validate_expected_owner_without_lease(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    created = _create(fixture)

    worktree = Path(created["worktree_path"])
    state_path = fixture["states"] / "GLA-123.json"
    assert worktree.is_dir()
    assert created["project_workspace_id"] == "00000000-0000-4000-8000-000000000124"
    assert created["execution_workspace_id"] == "00000000-0000-4000-8000-000000000125"
    assert state_path.stat().st_mode & 0o777 == 0o600
    assert _git("branch", "--show-current", cwd=worktree).stdout.strip() == (
        "feature/GLA-123-single-worktree"
    )

    overlap = _claim(fixture, "GlitcherryAndroidEngineer", "run-android-overlap")
    assert overlap.returncode != 0
    assert "expected owner" in overlap.stderr.lower()

    handoff = _handoff(
        fixture,
        "GlitcherryCTO",
        "run-cto-0",
        "GlitcherryCodeReviewer",
        "spec_review",
    )
    assert handoff.returncode == 0, handoff.stderr
    legacy_state = _state(fixture)
    legacy_state["lease"] = {
        "owner": "GlitcherryCTO",
        "run_id": "obsolete-run",
        "expires_at": "2000-01-01T00:00:00Z",
    }
    state_path.write_text(json.dumps(legacy_state, indent=2, sort_keys=True) + "\n")
    state_path.chmod(0o600)
    claimed = _claim(fixture, "GlitcherryCodeReviewer", "run-review-1")
    assert claimed.returncode == 0, claimed.stderr
    state = _state(fixture)
    assert state["lease"] is None
    assert state["phase"] == "spec_review"


def test_adopt_tolerates_terminal_v1_history(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    legacy = fixture["states"] / "GLA-122.json"
    legacy.write_text(
        json.dumps(
            {
                "schema_version": "glitcherry-slice-worktree/v1",
                "issue_key": "GLA-122",
                "phase": "cleaned",
            }
        )
        + "\n"
    )
    legacy.chmod(0o600)

    adopted = _create(fixture)

    assert adopted["schema_version"] == "glitcherry-slice-worktree/v2"


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
    assert _state(fixture)["lease"] is None
    assert _state(fixture)["expected_owner"] == "GlitcherryCTO"


def test_recovery_requires_exact_run_and_preserves_dirty_work(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    created = _create(fixture)
    dirty = Path(created["worktree_path"]) / "unfinished.txt"
    dirty.write_text("must survive recovery\n")
    state_path = fixture["states"] / "GLA-123.json"
    legacy_state = _state(fixture)
    legacy_state["lease"] = {
        "owner": "GlitcherryCTO",
        "run_id": "run-cto-0",
        "expires_at": "2099-01-01T00:00:00Z",
    }
    state_path.write_text(json.dumps(legacy_state, indent=2, sort_keys=True) + "\n")
    state_path.chmod(0o600)

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


def test_recovery_adopts_clean_linear_implementation_checkpoint(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    worktree, old_head, new_head, engineer_run = _recover_advanced_checkpoint(fixture)
    assert _state(fixture)["head_sha"] == old_head
    assert _claim(fixture, "GlitcherryCTO", "run-cto-before-adopt").returncode != 0

    before_status = _git("status", "--porcelain=v2", cwd=worktree).stdout
    adopted = _adopt_recovery_checkpoint(fixture, old_head, new_head)
    assert adopted.returncode == 0, adopted.stderr

    state = _state(fixture)
    assert state["head_sha"] == new_head
    assert state["phase"] == "recovery"
    assert state["expected_owner"] == "GlitcherryCTO"
    assert state["lease"] is None
    assert state["recovery_resume_owner"] == "GlitcherryAndroidEngineer"
    assert state["recovery_resume_phase"] == "implementation"
    adoption = state["checkpoint_adoptions"][-1]
    assert adoption["old_head_sha"] == old_head
    assert adoption["new_head_sha"] == new_head
    assert adoption["operator"] == "GlitcherryCTO"
    assert adoption["operator_run_id"] == "run-cto-adopt"
    assert adoption["recovered_owner"] == "GlitcherryAndroidEngineer"
    assert adoption["recovered_run_id"] == engineer_run
    assert _git("status", "--porcelain=v2", cwd=worktree).stdout == before_status

    assert _claim(fixture, "GlitcherryCTO", "run-cto-after-adopt").returncode == 0
    handed_off = _handoff(
        fixture,
        "GlitcherryCTO",
        "run-cto-after-adopt",
        "GlitcherryCTO",
        "plan_revision",
    )
    assert handed_off.returncode == 0, handed_off.stderr


def test_recovery_checkpoint_adoption_rejects_invalid_arguments_without_state_change(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _, old_head, new_head, _ = _recover_advanced_checkpoint(fixture)
    state_path = fixture["states"] / "GLA-123.json"
    original_state = state_path.read_bytes()

    attempts = (
        _adopt_recovery_checkpoint(
            fixture, old_head, new_head, operator="GlitcherryCodeReviewer"
        ),
        _adopt_recovery_checkpoint(
            fixture, old_head, new_head, run_id="unsafe run id"
        ),
        _adopt_recovery_checkpoint(fixture, old_head, new_head, evidence="too short"),
        _adopt_recovery_checkpoint(fixture, old_head[:-1], new_head),
        _adopt_recovery_checkpoint(fixture, old_head, new_head.upper()),
        _adopt_recovery_checkpoint(fixture, "0" * 40, new_head),
        _adopt_recovery_checkpoint(fixture, old_head, "1" * 40),
        _adopt_recovery_checkpoint(fixture, old_head, old_head),
    )

    assert all(attempt.returncode != 0 for attempt in attempts)
    assert state_path.read_bytes() == original_state


def test_recovery_checkpoint_adoption_rejects_invalid_controller_state(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _, old_head, new_head, _ = _recover_advanced_checkpoint(fixture)
    state_path = fixture["states"] / "GLA-123.json"
    original_state = _state(fixture)

    mutations = (
        lambda state: state.update({"phase": "plan_revision"}),
        lambda state: state.update({"expected_owner": "GlitcherryCodeReviewer"}),
        lambda state: state.update(
            {
                "lease": {
                    "owner": "GlitcherryCTO",
                    "run_id": "run-live",
                    "expires_at": "2099-01-01T00:00:00Z",
                }
            }
        ),
        lambda state: state.update({"android_merge_sha": "1" * 40}),
        lambda state: state.update({"recovery": []}),
        lambda state: state["recovery"][-1].update(
            {"owner": "GlitcherryMediaPipelineEngineer"}
        ),
        lambda state: state.update(
            {"primary_implementer": "GlitcherryMediaPipelineEngineer"}
        ),
        lambda state: state.update(
            {"recovery_resume_owner": "GlitcherryMediaPipelineEngineer"}
        ),
        lambda state: state.update({"recovery_resume_phase": "spec"}),
        lambda state: state.update(
            {
                "checkpoint_adoptions": [
                    {
                        "recovery_recorded_at": state["recovery"][-1]["recorded_at"],
                        "recovered_run_id": state["recovery"][-1]["run_id"],
                    }
                ]
            }
        ),
    )

    for mutate in mutations:
        state = json.loads(json.dumps(original_state))
        mutate(state)
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        state_path.chmod(0o600)
        before = state_path.read_bytes()
        result = _adopt_recovery_checkpoint(fixture, old_head, new_head)
        assert result.returncode != 0
        assert state_path.read_bytes() == before


def test_recovery_checkpoint_adoption_rejects_dirty_or_wrong_branch(
    tmp_path: Path,
) -> None:
    dirty_fixture = _fixture(tmp_path / "dirty")
    dirty_worktree, old_head, new_head, _ = _recover_advanced_checkpoint(dirty_fixture)
    dirty_state_path = dirty_fixture["states"] / "GLA-123.json"
    dirty_state = dirty_state_path.read_bytes()
    dirty_file = dirty_worktree / "uncommitted.txt"
    dirty_file.write_text("must remain untouched\n")
    dirty_result = _adopt_recovery_checkpoint(dirty_fixture, old_head, new_head)
    assert dirty_result.returncode != 0
    assert "dirty" in dirty_result.stderr.lower()
    assert dirty_state_path.read_bytes() == dirty_state
    assert dirty_file.read_text() == "must remain untouched\n"

    branch_fixture = _fixture(tmp_path / "branch")
    branch_worktree, old_head, new_head, _ = _recover_advanced_checkpoint(branch_fixture)
    branch_state_path = branch_fixture["states"] / "GLA-123.json"
    branch_state = branch_state_path.read_bytes()
    _git("checkout", "-b", "unexpected-branch", cwd=branch_worktree)
    branch_result = _adopt_recovery_checkpoint(branch_fixture, old_head, new_head)
    assert branch_result.returncode != 0
    assert "branch" in branch_result.stderr.lower()
    assert branch_state_path.read_bytes() == branch_state


def test_recovery_checkpoint_adoption_rejects_divergence_merge_and_replay(
    tmp_path: Path,
) -> None:
    divergent_fixture = _fixture(tmp_path / "divergent")
    divergent_worktree, old_head, _, _ = _recover_advanced_checkpoint(divergent_fixture)
    divergent_state_path = divergent_fixture["states"] / "GLA-123.json"
    divergent_state = divergent_state_path.read_bytes()
    empty_tree = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    divergent_head = _git(
        "commit-tree", empty_tree, "-m", "divergent checkpoint", cwd=divergent_worktree
    ).stdout.strip()
    _git("reset", "--hard", divergent_head, cwd=divergent_worktree)
    divergent_result = _adopt_recovery_checkpoint(
        divergent_fixture, old_head, divergent_head
    )
    assert divergent_result.returncode != 0
    assert "descendant" in divergent_result.stderr.lower()
    assert divergent_state_path.read_bytes() == divergent_state

    merge_fixture = _fixture(tmp_path / "merge")
    merge_worktree, old_head, _, _ = _recover_advanced_checkpoint(merge_fixture)
    merge_state_path = merge_fixture["states"] / "GLA-123.json"
    _git("checkout", "-b", "checkpoint-side", old_head, cwd=merge_worktree)
    (merge_worktree / "side.txt").write_text("side\n")
    _git("add", "side.txt", cwd=merge_worktree)
    _git("commit", "-m", "side checkpoint", cwd=merge_worktree)
    _git("checkout", "feature/GLA-123-single-worktree", cwd=merge_worktree)
    _git("merge", "--no-ff", "checkpoint-side", "-m", "merge checkpoint", cwd=merge_worktree)
    merge_head = _git("rev-parse", "HEAD", cwd=merge_worktree).stdout.strip()
    merge_state = merge_state_path.read_bytes()
    merge_result = _adopt_recovery_checkpoint(merge_fixture, old_head, merge_head)
    assert merge_result.returncode != 0
    assert "merge commit" in merge_result.stderr.lower()
    assert merge_state_path.read_bytes() == merge_state

    replay_fixture = _fixture(tmp_path / "replay")
    replay_worktree, old_head, first_head, _ = _recover_advanced_checkpoint(replay_fixture)
    first = _adopt_recovery_checkpoint(replay_fixture, old_head, first_head)
    assert first.returncode == 0, first.stderr
    (replay_worktree / "later.txt").write_text("unauthorized later advance\n")
    _git("add", "later.txt", cwd=replay_worktree)
    _git("commit", "-m", "later checkpoint", cwd=replay_worktree)
    later_head = _git("rev-parse", "HEAD", cwd=replay_worktree).stdout.strip()
    replay_state_path = replay_fixture["states"] / "GLA-123.json"
    replay_state = replay_state_path.read_bytes()
    replay = _adopt_recovery_checkpoint(replay_fixture, first_head, later_head)
    assert replay.returncode != 0
    assert "already adopted" in replay.stderr.lower()
    assert replay_state_path.read_bytes() == replay_state


def test_technical_triage_returns_to_same_implementer_without_review_rejection(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _create(fixture)
    _, engineer_run = _route_to_implementation(fixture)
    head = _state(fixture)["head_sha"]

    triage = _handoff(
        fixture,
        "GlitcherryAndroidEngineer",
        engineer_run,
        "GlitcherryCTO",
        "technical_triage",
    )
    assert triage.returncode == 0, triage.stderr
    assert _claim(fixture, "GlitcherryCTO", "run-cto-triage").returncode == 0
    routed = _handoff(
        fixture,
        "GlitcherryCTO",
        "run-cto-triage",
        "GlitcherryAndroidEngineer",
        "implementation",
    )
    assert routed.returncode == 0, routed.stderr
    state = _state(fixture)
    assert state["head_sha"] == head
    assert state["primary_implementer"] == "GlitcherryAndroidEngineer"
    assert state["review_rejections"] == 0
    assert _claim(
        fixture,
        "GlitcherryAndroidEngineer",
        "run-engineer-after-triage",
    ).returncode == 0


def test_clean_blocked_slice_resumes_and_routes_without_synthetic_plan_edit(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    created = _create(fixture)

    blocked = _block(fixture, "GlitcherryCTO", "run-cto-0")
    assert blocked.returncode == 0, blocked.stderr
    state = _state(fixture)
    assert state["phase"] == "blocked"
    assert state["blocked_from_phase"] == "spec"
    assert state["blocked_by_owner"] == "GlitcherryCTO"
    assert state["blocked_head_sha"] == created["head_sha"]

    resumed = _resume_blocked(fixture, "GlitcherryCTO", "plan_revision")
    assert resumed.returncode == 0, resumed.stderr
    state = _state(fixture)
    assert state["phase"] == "plan_revision"
    assert state["expected_owner"] == "GlitcherryCTO"
    assert state["lease"] is None
    assert state["block_reason"].startswith("LOCAL_BLOCKED:")
    assert state["blocked_resumes"][-1]["dirty"] is False
    assert state["blocked_resumes"][-1]["operator"] == "GlitcherryCTO"
    assert state["blocked_resumes"][-1]["operator_run_id"] == "run-cto-resume"

    claimed = _claim(fixture, "GlitcherryCTO", "run-cto-plan-revision")
    assert claimed.returncode == 0, claimed.stderr
    routed = _handoff(
        fixture,
        "GlitcherryCTO",
        "run-cto-plan-revision",
        "GlitcherryAndroidEngineer",
        "implementation",
    )
    assert routed.returncode == 0, routed.stderr
    state = _state(fixture)
    assert state["head_sha"] == created["head_sha"]
    assert state["review_rejections"] == 0
    assert _claim(
        fixture,
        "GlitcherryAndroidEngineer",
        "run-engineer-after-block",
    ).returncode == 0


def test_dirty_blocked_slice_requires_primary_implementer_recovery(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _create(fixture)
    worktree, engineer_run = _route_to_implementation(fixture)
    dirty = worktree / "unfinished.txt"
    dirty.write_text("must survive blocked resume\n")

    blocked = _block(fixture, "GlitcherryAndroidEngineer", engineer_run)
    assert blocked.returncode == 0, blocked.stderr
    state_path = fixture["states"] / "GLA-123.json"
    blocked_state = state_path.read_bytes()

    wrong_owner = _resume_blocked(fixture, "GlitcherryCTO", "plan_revision")
    assert wrong_owner.returncode != 0
    assert "primary implementer" in wrong_owner.stderr.lower()
    assert state_path.read_bytes() == blocked_state
    assert dirty.read_text() == "must survive blocked resume\n"

    resumed = _resume_blocked(
        fixture,
        "GlitcherryAndroidEngineer",
        "implementation_recovery",
    )
    assert resumed.returncode == 0, resumed.stderr
    state = _state(fixture)
    assert state["phase"] == "implementation_recovery"
    assert state["expected_owner"] == "GlitcherryAndroidEngineer"
    assert state["lease"] is None
    assert state["blocked_resumes"][-1]["dirty"] is True
    assert dirty.read_text() == "must survive blocked resume\n"

    wrong_claim = _claim(fixture, "GlitcherryCTO", "run-cto-wrong-owner")
    assert wrong_claim.returncode != 0
    claimed = _claim(
        fixture,
        "GlitcherryAndroidEngineer",
        "run-engineer-recovery",
    )
    assert claimed.returncode == 0, claimed.stderr
    assert dirty.read_text() == "must survive blocked resume\n"

    dirty_handoff = _handoff(
        fixture,
        "GlitcherryAndroidEngineer",
        "run-engineer-recovery",
        "GlitcherryCTO",
        "plan_revision",
    )
    assert dirty_handoff.returncode != 0
    assert "dirty" in dirty_handoff.stderr.lower()

    _git("add", "unfinished.txt", cwd=worktree)
    _git("commit", "-m", "GLA-123 preserve recovery work", cwd=worktree)
    handed_off = _handoff(
        fixture,
        "GlitcherryAndroidEngineer",
        "run-engineer-recovery",
        "GlitcherryCTO",
        "plan_revision",
    )
    assert handed_off.returncode == 0, handed_off.stderr
    assert _claim(
        fixture,
        "GlitcherryCTO",
        "run-cto-plan-revision",
    ).returncode == 0
    routed = _handoff(
        fixture,
        "GlitcherryCTO",
        "run-cto-plan-revision",
        "GlitcherryAndroidEngineer",
        "implementation",
    )
    assert routed.returncode == 0, routed.stderr
    assert _state(fixture)["review_rejections"] == 0
    assert _claim(
        fixture,
        "GlitcherryAndroidEngineer",
        "run-engineer-after-dirty-recovery",
    ).returncode == 0


def test_correction_after_approval_requires_fresh_exact_head_review(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _create(fixture)
    worktree, reviewer_run = _route_to_code_review(fixture)
    approved_head = _state(fixture)["head_sha"]

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
    assert _state(fixture)["reviewed_head"] == approved_head
    assert _claim(fixture, "GlitcherryCTO", "run-cto-after-approval").returncode == 0
    assert _handoff(
        fixture,
        "GlitcherryCTO",
        "run-cto-after-approval",
        "GlitcherryAndroidEngineer",
        "implementation",
    ).returncode == 0

    engineer_run = "run-engineer-post-approval-fix"
    assert _claim(fixture, "GlitcherryAndroidEngineer", engineer_run).returncode == 0
    (worktree / "post-approval-fix.txt").write_text("fresh review required\n")
    _git("add", "post-approval-fix.txt", cwd=worktree)
    _git("commit", "-m", "GLA-123 post-approval correction", cwd=worktree)
    correction_head = _git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
    assert correction_head != approved_head
    assert _handoff(
        fixture,
        "GlitcherryAndroidEngineer",
        engineer_run,
        "GlitcherryCodeReviewer",
        "code_review",
    ).returncode == 0
    state = _state(fixture)
    assert state["head_sha"] == correction_head
    assert state["reviewed_head"] == approved_head
    assert state["review_rejections"] == 0

    second_review_run = "run-review-post-approval-fix"
    assert _claim(
        fixture,
        "GlitcherryCodeReviewer",
        second_review_run,
    ).returncode == 0
    reapproved = _run(
        fixture,
        "approve",
        "--issue-key",
        "GLA-123",
        "--owner",
        "GlitcherryCodeReviewer",
        "--run-id",
        second_review_run,
        "--next-owner",
        "GlitcherryCTO",
    )
    assert reapproved.returncode == 0, reapproved.stderr
    assert _state(fixture)["reviewed_head"] == correction_head


def test_blocked_resume_rejections_leave_state_unchanged(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _create(fixture)
    assert _block(fixture, "GlitcherryCTO", "run-cto-0").returncode == 0
    state_path = fixture["states"] / "GLA-123.json"
    blocked_state = state_path.read_bytes()

    attempts = (
        _resume_blocked(
            fixture,
            "GlitcherryCTO",
            "plan_revision",
            operator="GlitcherryCodeReviewer",
        ),
        _resume_blocked(
            fixture,
            "GlitcherryCTO",
            "plan_revision",
            run_id="unsafe run id",
        ),
        _resume_blocked(
            fixture,
            "GlitcherryCTO",
            "plan_revision",
            evidence="too short",
        ),
        _resume_blocked(
            fixture,
            "GlitcherryCodeReviewer",
            "plan_revision",
        ),
    )

    assert all(attempt.returncode != 0 for attempt in attempts)
    assert state_path.read_bytes() == blocked_state


def test_blocked_resume_rejects_changed_head(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    created = _create(fixture)
    assert _block(fixture, "GlitcherryCTO", "run-cto-0").returncode == 0
    state_path = fixture["states"] / "GLA-123.json"
    blocked_state = state_path.read_bytes()
    worktree = Path(created["worktree_path"])

    (worktree / "unexpected.txt").write_text("unexpected commit\n")
    _git("add", "unexpected.txt", cwd=worktree)
    _git("commit", "-m", "unexpected head", cwd=worktree)
    changed_head = _resume_blocked(fixture, "GlitcherryCTO", "plan_revision")
    assert changed_head.returncode != 0
    assert "head" in changed_head.stderr.lower()
    assert state_path.read_bytes() == blocked_state


def test_blocked_resume_rejects_started_merge_state(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _create(fixture)
    assert _block(fixture, "GlitcherryCTO", "run-cto-0").returncode == 0
    state_path = fixture["states"] / "GLA-123.json"
    state = _state(fixture)
    state["android_merge_sha"] = "1234567"
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    state_path.chmod(0o600)
    merge_state = state_path.read_bytes()
    merging = _resume_blocked(fixture, "GlitcherryCTO", "plan_revision")
    assert merging.returncode != 0
    assert "merge or cleanup" in merging.stderr.lower()
    assert state_path.read_bytes() == merge_state


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


def test_cleanup_normalizes_for_paperclip_then_removes_exact_refs(
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

    approved_head = _state(fixture)["reviewed_head"]
    prepared = _run(
        fixture,
        "prepare-cleanup",
        "--issue-key",
        "GLA-123",
        "--owner",
        "GlitcherryCTO",
        "--run-id",
        "run-cto-merge",
    )
    assert prepared.returncode == 0, prepared.stderr
    state = _state(fixture)
    assert state["phase"] == "workspace_cleanup"
    assert state["approved_head_sha"] == approved_head
    assert _git("rev-parse", "HEAD", cwd=worktree).stdout.strip() == android_merge

    premature = _run(
        fixture,
        "cleanup",
        "--issue-key",
        "GLA-123",
        "--owner",
        "GlitcherryCTO",
        "--run-id",
        "run-parent-cleanup",
    )
    assert premature.returncode != 0
    assert "has not been archived" in premature.stderr

    # Simulate Paperclip's supported execution-workspace archive. The normal
    # non-force branch deletion now succeeds because prepare-cleanup moved the
    # runtime-created branch to the verified merge commit.
    _git("worktree", "remove", str(worktree), cwd=fixture["primary"])
    _git("branch", "-d", branch, cwd=fixture["primary"])

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
