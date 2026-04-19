"""Tests for palace_git_diff and parse_numstat. Spec §4.4."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from palace_mcp.git.tools import parse_numstat, palace_git_diff


# ---------------------------------------------------------------------------
# parse_numstat unit tests
# ---------------------------------------------------------------------------


def test_parse_numstat_basic() -> None:
    raw = "3\t1\tsrc/foo.py\n0\t2\tsrc/bar.py\n"
    stats = parse_numstat(raw)
    assert len(stats) == 2
    assert stats[0].path == "src/foo.py"
    assert stats[0].added == 3
    assert stats[0].deleted == 1
    assert stats[1].deleted == 2


def test_parse_numstat_binary() -> None:
    """Binary files show - for added/deleted."""
    raw = "-\t-\tbinary.bin\n"
    stats = parse_numstat(raw)
    assert len(stats) == 1
    assert stats[0].added is None
    assert stats[0].deleted is None


def test_parse_numstat_empty() -> None:
    assert parse_numstat("") == []


# ---------------------------------------------------------------------------
# Integration helpers
# ---------------------------------------------------------------------------


def _get_commits(repo: Path) -> list[str]:
    out = subprocess.check_output(
        ["git", "log", "--pretty=%H", "-n", "2"], cwd=repo, text=True
    )
    return [ln for ln in out.splitlines() if ln]


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


async def test_diff_full_between_commits(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    shas = _get_commits(tmp_repo)
    old, new = shas[1], shas[0]
    result = await palace_git_diff("testproj", ref_a=old, ref_b=new)
    assert result["ok"] is True
    assert result["mode"] == "full"
    assert result["diff"]
    assert "a.py" in result["diff"]
    assert result["truncated"] is False


async def test_diff_stat_mode(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    shas = _get_commits(tmp_repo)
    old, new = shas[1], shas[0]
    result = await palace_git_diff("testproj", ref_a=old, ref_b=new, mode="stat")
    assert result["ok"] is True
    assert result["mode"] == "stat"
    assert result["files_stat"] is not None
    assert len(result["files_stat"]) > 0
    assert result["diff"] is None


async def test_diff_invalid_mode_returns_error(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    result = await palace_git_diff(
        "testproj", ref_a="HEAD", ref_b="HEAD", mode="badmode"
    )
    assert result["ok"] is False
    assert result["error_code"] == "invalid_mode"


async def test_diff_invalid_slug_returns_error() -> None:
    result = await palace_git_diff("INVALID!", ref_a="HEAD", ref_b="HEAD")
    assert result["ok"] is False
    assert result["error_code"] == "invalid_slug"


async def test_diff_invalid_ref_returns_error(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    result = await palace_git_diff("testproj", ref_a="--bad", ref_b="HEAD")
    assert result["ok"] is False
    assert result["error_code"] == "invalid_ref"


async def test_diff_path_filter(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    shas = _get_commits(tmp_repo)
    old, new = shas[1], shas[0]
    result = await palace_git_diff("testproj", ref_a=old, ref_b=new, path="a.py")
    assert result["ok"] is True
    assert result["mode"] == "full"
