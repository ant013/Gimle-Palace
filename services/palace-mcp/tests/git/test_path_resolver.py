"""Tests for git.path_resolver. Spec §5.1, §5.2."""

from __future__ import annotations

from pathlib import Path

import pytest

from palace_mcp.git.path_resolver import (
    InvalidPath,
    ProjectNotRegistered,
    resolve_project,
    validate_rel_path,
)
from palace_mcp.memory.projects import InvalidSlug


# --- resolve_project (slug → repo Path) ---


def test_resolve_existing_project(repos_root: Path) -> None:
    repo = resolve_project("testproj", repos_root=repos_root)
    assert repo == (repos_root / "testproj").resolve()


def test_resolve_invalid_slug(repos_root: Path) -> None:
    with pytest.raises(InvalidSlug):
        resolve_project("../etc", repos_root=repos_root)


def test_resolve_missing_project(repos_root: Path) -> None:
    with pytest.raises(ProjectNotRegistered):
        resolve_project("absent", repos_root=repos_root)


def test_resolve_not_a_git_repo(tmp_path: Path, repos_root: Path) -> None:
    # Make a dir that isn't a git repo.
    plain = repos_root / "plain"
    plain.mkdir()
    with pytest.raises(ProjectNotRegistered):
        resolve_project("plain", repos_root=repos_root)


# --- validate_rel_path (path inside repo) ---


def test_valid_relative_path(tmp_repo: Path) -> None:
    p = validate_rel_path("a.py", repo_path=tmp_repo)
    assert p == (tmp_repo / "a.py").resolve()


def test_reject_absolute_path(tmp_repo: Path) -> None:
    with pytest.raises(InvalidPath):
        validate_rel_path("/etc/passwd", repo_path=tmp_repo)


def test_reject_pathspec_magic(tmp_repo: Path) -> None:
    for bad in [":(glob)*.py", ":!exclude", ":/root", ":top"]:
        with pytest.raises(InvalidPath):
            validate_rel_path(bad, repo_path=tmp_repo)


def test_reject_nul_byte(tmp_repo: Path) -> None:
    with pytest.raises(InvalidPath):
        validate_rel_path("a\x00.py", repo_path=tmp_repo)


def test_reject_traversal_escape(tmp_repo: Path) -> None:
    with pytest.raises(InvalidPath):
        validate_rel_path("../outside", repo_path=tmp_repo)


def test_reject_symlink_escape(tmp_repo: Path) -> None:
    outside = tmp_repo.parent / "secret.txt"
    outside.write_text("secret")
    link = tmp_repo / "evil"
    link.symlink_to(outside)
    with pytest.raises(InvalidPath):
        validate_rel_path("evil", repo_path=tmp_repo)
