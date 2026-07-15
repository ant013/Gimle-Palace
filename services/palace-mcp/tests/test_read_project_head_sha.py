"""Regression: _read_project_head_sha vs run_git's truncated-at-cap semantics.

run_git flags truncated=True whenever output EXACTLY fills max_stdout_lines
(cap reached = producer killed = intentional success path). A caller expecting
N lines must therefore pass a cap of N+1, else every valid response looks
truncated. With cap=1, _read_project_head_sha returned None for every repo and
silently degraded ALL incremental analyzes to full
(effective_mode_reason=repo_head_unavailable) — found 2026-07-15.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.git.command import run_git
from palace_mcp.project_analyze import _read_project_head_sha


def _git_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()

    def g(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@t")
    g("config", "user.name", "T")
    (repo / "a.txt").write_text("x\n")
    g("add", ".")
    g("commit", "-m", "c", "-q")
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repo, sha


def _driver(repo: Path) -> object:
    row = {"p": {"repo_path": str(repo)}}
    result = AsyncMock()
    result.single = AsyncMock(return_value=row)
    session = AsyncMock()
    session.run = AsyncMock(return_value=result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


def test_run_git_flags_truncated_when_output_exactly_fills_cap(
    tmp_path: Path,
) -> None:
    """Documents the cap semantics the fix relies on."""
    repo, _ = _git_repo(tmp_path)
    exact = run_git(["rev-parse", "HEAD"], repo_path=repo, max_stdout_lines=1)
    assert exact.truncated is True  # cap reached == truncated, by design
    roomy = run_git(["rev-parse", "HEAD"], repo_path=repo, max_stdout_lines=2)
    assert roomy.truncated is False
    assert roomy.rc == 0


@pytest.mark.asyncio
async def test_read_project_head_sha_returns_sha_for_single_line_output(
    tmp_path: Path,
) -> None:
    repo, sha = _git_repo(tmp_path)
    got = await _read_project_head_sha(_driver(repo), "some-project")
    assert got == sha
