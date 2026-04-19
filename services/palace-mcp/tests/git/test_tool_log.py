"""Tests for palace_git_log and parse_log. Spec §4.1."""

from __future__ import annotations

from pathlib import Path

import pytest

from palace_mcp.git.tools import LOG_CAP_N, parse_log, palace_git_log


# ---------------------------------------------------------------------------
# parse_log unit tests
# ---------------------------------------------------------------------------


def test_parse_log_two_entries() -> None:
    raw = (
        "abc1234567890123456789012345678901234567890\x00abc1234\x00Alice\x00a@a\x002024-01-01T00:00:00+00:00\x00first\n"
        "def1234567890123456789012345678901234567890\x00def1234\x00Bob\x00b@b\x002024-01-02T00:00:00+00:00\x00second\n"
    )
    entries = parse_log(raw)
    assert len(entries) == 2
    assert entries[0].author_name == "Alice"
    assert entries[0].subject == "first"
    assert entries[1].author_name == "Bob"
    assert entries[1].subject == "second"


def test_parse_log_empty() -> None:
    assert parse_log("") == []
    assert parse_log("   \n\n") == []


def test_parse_log_subject_with_pipe_chars() -> None:
    """Subject may contain colons, spaces; only first 6 NULL parts matter."""
    raw = "abc1234567890123456789012345678901234567890\x00abc1234\x00Alice\x00a@a\x002024-01-01T00:00:00+00:00\x00fix: the thing\n"
    entries = parse_log(raw)
    assert len(entries) == 1
    assert entries[0].subject == "fix: the thing"


def test_parse_log_skips_malformed_lines() -> None:
    """Lines with fewer than 6 NUL-separated fields are silently skipped."""
    raw = "only\x00three\x00fields\n"
    assert parse_log(raw) == []


# ---------------------------------------------------------------------------
# Integration tests — palace_git_log against a real tmp repo
# ---------------------------------------------------------------------------


async def test_log_returns_two_commits(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)

    result = await palace_git_log("testproj")

    assert result["ok"] is True
    assert result["project"] == "testproj"
    assert len(result["entries"]) == 2
    assert result["truncated"] is False


async def test_log_invalid_slug_returns_error_envelope() -> None:
    result = await palace_git_log("INVALID SLUG!")
    assert result["ok"] is False
    assert result["error_code"] == "invalid_slug"


async def test_log_unknown_project_returns_error_envelope(
    repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    result = await palace_git_log("nonexistent")
    assert result["ok"] is False
    assert result["error_code"] == "project_not_registered"


async def test_log_invalid_ref_returns_error_envelope(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    result = await palace_git_log("testproj", ref="--injected-flag")
    assert result["ok"] is False
    assert result["error_code"] == "invalid_ref"


async def test_log_n_capped_at_log_cap_n(
    tmp_repo: Path, repos_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """n values above LOG_CAP_N must be silently clamped."""
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    result = await palace_git_log("testproj", n=LOG_CAP_N + 9999)
    assert result["ok"] is True
    assert len(result["entries"]) <= LOG_CAP_N
