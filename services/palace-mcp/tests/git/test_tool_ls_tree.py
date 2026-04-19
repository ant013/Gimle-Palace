"""Tests for palace_git_ls_tree and parse_ls_tree. Spec §4.5."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from palace_mcp.git.tools import parse_ls_tree, palace_git_ls_tree


# ---------------------------------------------------------------------------
# parse_ls_tree unit tests
# ---------------------------------------------------------------------------


def test_parse_ls_tree_blob() -> None:
    raw = "100644 blob abc1234567890123456789012345678901234567890\tsrc/foo.py\n"
    entries = parse_ls_tree(raw)
    assert len(entries) == 1
    assert entries[0].path == "src/foo.py"
    assert entries[0].type == "blob"
    assert entries[0].mode == "100644"


def test_parse_ls_tree_tree() -> None:
    raw = "040000 tree abc1234567890123456789012345678901234567890\tsrc\n"
    entries = parse_ls_tree(raw)
    assert len(entries) == 1
    assert entries[0].type == "tree"


def test_parse_ls_tree_empty() -> None:
    assert parse_ls_tree("") == []


def test_parse_ls_tree_skips_unknown_type() -> None:
    raw = "100644 unknown abc1234567890123456789012345678901234567890\tfoo\n"
    assert parse_ls_tree(raw) == []


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


async def test_ls_tree_returns_entries(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    result = await palace_git_ls_tree("testproj")
    assert result["ok"] is True
    assert result["project"] == "testproj"
    assert len(result["entries"]) > 0
    assert result["truncated"] is False
    # a.py must appear
    paths = [e["path"] for e in result["entries"]]
    assert "a.py" in paths


async def test_ls_tree_recursive(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Add a subdirectory file so recursive matters
    sub = tmp_repo / "sub"
    sub.mkdir()
    (sub / "b.py").write_text("x")
    subprocess.run(["git", "add", "."], cwd=tmp_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add sub", "-q"],
        cwd=tmp_repo,
        check=True,
        capture_output=True,
    )
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    result = await palace_git_ls_tree("testproj", recursive=True)
    assert result["ok"] is True
    assert result["recursive"] is True
    paths = [e["path"] for e in result["entries"]]
    assert "sub/b.py" in paths


async def test_ls_tree_invalid_slug_returns_error() -> None:
    result = await palace_git_ls_tree("INVALID!")
    assert result["ok"] is False
    assert result["error_code"] == "invalid_slug"


async def test_ls_tree_invalid_ref_returns_error(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    result = await palace_git_ls_tree("testproj", ref="--bad-flag")
    assert result["ok"] is False
    assert result["error_code"] == "invalid_ref"


async def test_ls_tree_unknown_project_returns_error(
    repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    result = await palace_git_ls_tree("nonexistent")
    assert result["ok"] is False
    assert result["error_code"] == "project_not_registered"
