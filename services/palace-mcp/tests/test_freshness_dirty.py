"""Unit tests for working-tree dirty detection in snippet_provider freshness."""

import subprocess
from pathlib import Path

from palace_mcp.code.snippet_provider import (
    FreshnessResult,
    _is_working_tree_dirty,
    inspect_freshness,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(repo: Path) -> str:
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "a.swift").write_text("let x = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    )
    return head.stdout.strip()


def test_freshness_result_dirty_defaults_none() -> None:
    fr = FreshnessResult(indexed_commit=None, commits_behind_head=None)
    assert fr.dirty_working_tree is None


def test_is_dirty_none_for_no_repo() -> None:
    assert _is_working_tree_dirty(None) is None


def test_is_dirty_none_for_non_git_dir(tmp_path: Path) -> None:
    assert _is_working_tree_dirty(tmp_path) is None


def test_clean_then_dirty_tracked_edit(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    assert _is_working_tree_dirty(tmp_path) is False
    # Edit a tracked file → dirty.
    (tmp_path / "a.swift").write_text("let x = 2\n")
    assert _is_working_tree_dirty(tmp_path) is True


def test_untracked_file_is_not_dirty(tmp_path: Path) -> None:
    # --untracked-files=no: a brand-new unstaged file is NOT reported dirty
    # (it cannot be SCIP-indexed anyway).
    _init_repo(tmp_path)
    (tmp_path / "new.swift").write_text("let y = 0\n")
    assert _is_working_tree_dirty(tmp_path) is False


def test_inspect_freshness_composes_dirty_and_commit(tmp_path: Path) -> None:
    head = _init_repo(tmp_path)
    fr = inspect_freshness(tmp_path, head)
    assert fr.indexed_commit == head
    assert fr.commits_behind_head == 0
    assert fr.stale is False
    assert fr.dirty_working_tree is False
    (tmp_path / "a.swift").write_text("let x = 3\n")
    fr2 = inspect_freshness(tmp_path, head)
    assert fr2.dirty_working_tree is True
    assert fr2.stale is False  # still at indexed HEAD; dirty ≠ stale


def test_staged_change_is_dirty(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "a.swift").write_text("changed\n")
    _git(tmp_path, "add", "-A")
    assert _is_working_tree_dirty(tmp_path) is True
