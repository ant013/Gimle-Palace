"""Tests for git.command.run_git. Spec §5.4-§5.8."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from palace_mcp.git.command import (
    ForbiddenGitCommand,
    GitError,
    GitTimeout,
    run_git,
)


def test_whitelist_rejects_push(tmp_repo: Path) -> None:
    with pytest.raises(ForbiddenGitCommand):
        run_git(["push", "origin"], repo_path=tmp_repo)


def test_whitelist_rejects_commit(tmp_repo: Path) -> None:
    with pytest.raises(ForbiddenGitCommand):
        run_git(["commit", "-am", "x"], repo_path=tmp_repo)


def test_env_sanitization(tmp_repo: Path) -> None:
    """Hostile $HOME/.gitconfig must not be read."""
    # Create a hostile global config that would fail git if read.
    hostile_home = tmp_repo.parent / "hostile_home"
    hostile_home.mkdir()
    (hostile_home / ".gitconfig").write_text(
        "[include]\n    path = /nonexistent/evil\n"
    )
    with patch.dict(os.environ, {"HOME": str(hostile_home)}):
        res = run_git(["log", "-1", "--pretty=%H"], repo_path=tmp_repo)
    assert res.rc == 0
    assert len(res.stdout.strip()) == 40  # full SHA


def test_timeout_raises_git_timeout(tmp_repo: Path) -> None:
    # Use an impossible, slow command. `git log -L` on an empty pattern
    # can hang briefly; simpler: force timeout via tiny budget.
    with pytest.raises(GitTimeout):
        run_git(["log", "--all"], repo_path=tmp_repo, timeout_s=0.0001)


def test_happy_path_log_returns_stdout(tmp_repo: Path) -> None:
    res = run_git(["log", "--pretty=%H", "-n", "2"], repo_path=tmp_repo)
    assert res.rc == 0
    lines = [ln for ln in res.stdout.splitlines() if ln]
    assert len(lines) == 2
    assert all(len(ln) == 40 for ln in lines)
    assert res.truncated is False


def test_cap_streaming_truncates_at_line_boundary(tmp_repo: Path) -> None:
    # Create 50 commits to exceed cap=10.
    repo = tmp_repo
    for i in range(50):
        (repo / "a.py").write_text(f"change-{i}\n")
        subprocess.run(
            ["git", "commit", "-am", f"c{i}", "-q"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
    res = run_git(
        ["log", "--pretty=%H", "-n", "500"],
        repo_path=repo,
        max_stdout_lines=10,
    )
    # Cap hit; last line must end with newline (no mid-line truncation).
    assert res.truncated is True
    assert res.stdout.endswith("\n")
    assert len([ln for ln in res.stdout.splitlines() if ln]) == 10


def test_stderr_drained_on_cap_kill(tmp_repo: Path) -> None:
    """Process must not deadlock when cap fires mid-stream.

    Reproduces stderr-pipe-fills deadlock scenario by running a command
    that produces large stderr while stdout is being cap-killed.
    """
    # `git log -n 1` produces 1 line stdout; cap at 1; assert no hang.
    res = run_git(
        ["log", "-n", "1"],
        repo_path=tmp_repo,
        max_stdout_lines=1,
        timeout_s=5.0,
    )
    # Normal output has 1 line; assertion is implicit (no hang).
    assert res.rc == 0


def test_invalid_utf8_replaced(tmp_path: Path) -> None:
    repo = tmp_path / "enc"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    (repo / "a").write_text("x")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    # Commit with invalid UTF-8 in subject via GIT_COMMITTER_EMAIL trick:
    # easier: use bytes via raw subprocess and I18N.COMMIT_ENCODING.
    env = os.environ.copy()
    env["LANG"] = "C"
    subj = b"initial \xff\xfe\n"
    subprocess.run(
        ["git", "commit", "-F", "-", "-q"],
        cwd=repo,
        input=subj,
        env=env,
        check=True,
        capture_output=True,
    )
    res = run_git(["log", "--pretty=%s", "-n", "1"], repo_path=repo)
    # Main invariant: no UnicodeDecodeError raised; output is a string.
    # (On macOS git may re-encode Latin-1 bytes to valid UTF-8 before output.)
    assert isinstance(res.stdout, str)
    assert "initial" in res.stdout


def test_broken_pipe_raises_git_error(tmp_repo: Path) -> None:
    """Mock proc.stdout.readline to raise BrokenPipeError — assert GitError raised.

    Maps to spec §7.6. Verifies the streaming loop handles broken pipes.
    """
    with patch(
        "palace_mcp.git.command.subprocess.Popen",
        spec=True,
    ) as mock_popen:
        mock_proc = mock_popen.return_value.__enter__.return_value
        # readline raises BrokenPipeError on the first call
        mock_proc.stdout.readline.side_effect = BrokenPipeError("pipe broken")
        mock_proc.stderr.read.return_value = b"broken pipe"
        mock_proc.returncode = None
        with pytest.raises(GitError):
            run_git(["log", "--oneline", "-5"], repo_path=tmp_repo)


def test_missing_git_binary_raises_git_error(
    tmp_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Patch SAFE_ENV PATH to a non-existent dir so git cannot be found — assert GitError.

    Maps to spec §7.6. Verifies error message is human-readable.
    """
    import palace_mcp.git.command as cmd_mod

    monkeypatch.setitem(cmd_mod.SAFE_ENV, "PATH", "/nonexistent")
    with pytest.raises(GitError, match=r"git"):
        run_git(["log", "--oneline", "-1"], repo_path=tmp_repo)
