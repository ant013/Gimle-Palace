"""Tests for palace_git_blame and parse_blame_porcelain. Spec §4.3."""

from __future__ import annotations

from pathlib import Path

import pytest

from palace_mcp.git.tools import parse_blame_porcelain, palace_git_blame


# ---------------------------------------------------------------------------
# parse_blame_porcelain unit tests
# ---------------------------------------------------------------------------

_SHA = "abcdef1234567890abcdef1234567890abcdef12"  # exactly 40 chars

_PORCELAIN_SAMPLE = f"""\
{_SHA} 1 1 2
author Alice
author-time 1700000000
\tline1
{_SHA} 2 2
\tline2
"""


def test_parse_blame_porcelain_two_lines() -> None:
    result = parse_blame_porcelain(_PORCELAIN_SAMPLE)
    assert len(result) == 2
    assert result[0].line_no == 1
    assert result[0].author_name == "Alice"
    assert result[0].content == "line1"
    assert result[1].line_no == 2
    assert result[1].content == "line2"


def test_parse_blame_porcelain_empty() -> None:
    assert parse_blame_porcelain("") == []


def test_parse_blame_porcelain_sha_short() -> None:
    result = parse_blame_porcelain(_PORCELAIN_SAMPLE)
    assert result[0].short == _SHA[:7]


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


async def test_blame_returns_lines_for_file(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    result = await palace_git_blame("testproj", path="a.py")
    assert result["ok"] is True
    assert result["project"] == "testproj"
    assert len(result["lines"]) > 0
    assert result["truncated"] is False
    first = result["lines"][0]
    assert first["line_no"] >= 1
    assert first["sha"]


async def test_blame_line_range(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    result = await palace_git_blame("testproj", path="a.py", line_start=1, line_end=1)
    assert result["ok"] is True
    assert len(result["lines"]) == 1
    assert result["lines"][0]["line_no"] == 1


async def test_blame_invalid_slug_returns_error() -> None:
    result = await palace_git_blame("INVALID!", path="a.py")
    assert result["ok"] is False
    assert result["error_code"] == "invalid_slug"


async def test_blame_invalid_ref_returns_error(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    result = await palace_git_blame("testproj", path="a.py", ref="--bad")
    assert result["ok"] is False
    assert result["error_code"] == "invalid_ref"


async def test_blame_invalid_path_returns_error(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    result = await palace_git_blame("testproj", path="../escape")
    assert result["ok"] is False
    assert result["error_code"] == "invalid_path"
