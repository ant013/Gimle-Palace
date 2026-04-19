"""Tests for palace_git_show. Spec §4.2."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from palace_mcp.git.tools import palace_git_show


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _head_sha(repo: Path) -> str:
    return subprocess.check_output(
        ["git", "log", "-1", "--pretty=%H"], cwd=repo, text=True
    ).strip()


# ---------------------------------------------------------------------------
# File mode tests
# ---------------------------------------------------------------------------


async def test_show_file_returns_content(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    result = await palace_git_show("testproj", ref="HEAD", path="a.py")
    assert result["ok"] is True
    assert result["mode"] == "file"
    assert "line1" in result["content"]
    assert result["truncated"] is False


async def test_show_file_invalid_path_returns_error(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    result = await palace_git_show("testproj", ref="HEAD", path="../escape")
    assert result["ok"] is False
    assert result["error_code"] == "invalid_path"


async def test_show_file_nonexistent_returns_error(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    result = await palace_git_show("testproj", ref="HEAD", path="nope.txt")
    assert result["ok"] is False
    # nope.txt is not in the tree at all — not a blob
    assert result["error_code"] in ("invalid_path", "git_error")


async def test_show_binary_file_returns_binary_response(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Binary file (contains NUL byte) returns BinaryFileResponse."""
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    # Create a binary file in the repo
    binary_file = tmp_repo / "blob.bin"
    binary_file.write_bytes(b"\x00\x01\x02\x03binary")
    subprocess.run(["git", "add", "blob.bin"], cwd=tmp_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add binary", "-q"],
        cwd=tmp_repo, check=True, capture_output=True,
    )
    result = await palace_git_show("testproj", ref="HEAD", path="blob.bin")
    assert result["ok"] is False
    assert result["error_code"] == "binary_file"
    assert result["size_bytes"] > 0


# ---------------------------------------------------------------------------
# Commit mode tests
# ---------------------------------------------------------------------------


async def test_show_commit_returns_metadata(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    sha = _head_sha(tmp_repo)
    result = await palace_git_show("testproj", ref=sha)
    assert result["ok"] is True
    assert result["mode"] == "commit"
    assert result["sha"]
    assert result["subject"]
    assert result["truncated"] is False


async def test_show_commit_invalid_ref_returns_error(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    result = await palace_git_show("testproj", ref="deadbeefdeadbeef")
    assert result["ok"] is False
    assert result["error_code"] in ("invalid_ref", "git_error")


# ---------------------------------------------------------------------------
# Common error path tests
# ---------------------------------------------------------------------------


async def test_show_invalid_slug_returns_error() -> None:
    result = await palace_git_show("INVALID!", ref="HEAD")
    assert result["ok"] is False
    assert result["error_code"] == "invalid_slug"


async def test_show_invalid_ref_format_returns_error(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    result = await palace_git_show("testproj", ref="--bad-flag")
    assert result["ok"] is False
    assert result["error_code"] == "invalid_ref"
