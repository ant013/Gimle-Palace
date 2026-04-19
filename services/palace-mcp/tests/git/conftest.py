"""Shared fixtures for palace_mcp.git tests.

`tmp_repo` creates a real git repository with 2 commits in a tmp dir.
Tests run against real git — per feedback_qa_skipped_gim48.md, mocking
subprocess hides API-drift bugs.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Create a real git repo at `<tmp>/repos/testproj` with 2 commits."""
    repo = tmp_path / "repos" / "testproj"
    repo.mkdir(parents=True)
    _run(["git", "init", "-q", "-b", "main"], cwd=repo)
    _run(["git", "config", "user.email", "t@t"], cwd=repo)
    _run(["git", "config", "user.name", "T"], cwd=repo)
    (repo / "a.py").write_text("line1\nline2\n")
    _run(["git", "add", "."], cwd=repo)
    _run(["git", "commit", "-m", "initial", "-q"], cwd=repo)
    (repo / "a.py").write_text("line1\nline2-changed\nline3\n")
    _run(["git", "commit", "-am", "change", "-q"], cwd=repo)
    return repo


@pytest.fixture
def repos_root(tmp_path: Path, tmp_repo: Path) -> Path:
    """Simulate container's /repos/ with one project mounted."""
    # tmp_repo already lives at tmp_path / "repos" / "testproj"
    return tmp_path / "repos"
