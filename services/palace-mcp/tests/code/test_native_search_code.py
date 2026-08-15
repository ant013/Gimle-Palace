"""Tests for the native search_code handler (grep over a project's on-disk repo)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from palace_mcp.code.native_detect_changes import FALLBACK_TO_CM
from palace_mcp.code.native_search_code import native_search_code
from palace_mcp.git.path_resolver import ProjectNotRegistered
from palace_mcp.memory.projects import InvalidSlug


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "Sources").mkdir()
    (tmp_path / "Sources" / "Wallet.swift").write_text(
        "class HDWallet {\n    let seed = 1\n}\n"
    )
    return tmp_path


def _patch_resolver(monkeypatch: pytest.MonkeyPatch, result: Any) -> None:
    """Stub _resolve_repo_path with a path to return or an exception to raise."""

    async def _fake(project: str) -> Any:
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("palace_mcp.code.native_search_code._resolve_repo_path", _fake)


@pytest.mark.asyncio
async def test_no_project_falls_back_to_cm() -> None:
    assert await native_search_code(pattern="HD") is FALLBACK_TO_CM


@pytest.mark.asyncio
async def test_unregistered_repo_falls_back_to_cm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A registered project without an on-disk repo must degrade to the CM
    passthrough — CM answers from its own index, so erroring here would regress
    every repo-less project."""
    _patch_resolver(monkeypatch, ProjectNotRegistered("bitcoin-core"))
    result = await native_search_code(project="bitcoin-core", pattern="HD")
    assert result is FALLBACK_TO_CM


@pytest.mark.asyncio
async def test_invalid_slug_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolver(monkeypatch, InvalidSlug("bad slug"))
    result = await native_search_code(project="../evil", pattern="HD")
    assert isinstance(result, dict)
    assert result["ok"] is False
    assert result["error_code"] == "invalid_slug"


@pytest.mark.asyncio
async def test_missing_pattern_errors() -> None:
    result = await native_search_code(project="gimle", pattern="  ")
    assert isinstance(result, dict)
    assert result["ok"] is False
    assert result["error_code"] == "validation_error"


@pytest.mark.asyncio
async def test_match_returns_repo_relative_path(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    _patch_resolver(monkeypatch, repo)
    result = await native_search_code(project="gimle", pattern="HDWallet")
    assert isinstance(result, dict)
    assert result["ok"] is True
    assert result["results"] == [
        {"file_path": "Sources/Wallet.swift", "line": 1, "text": "class HDWallet {"}
    ]
    assert result["total"] == 1
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_no_match_is_empty_not_error(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """grep exits 1 on no matches — that is a valid empty result, not a failure."""
    _patch_resolver(monkeypatch, repo)
    result = await native_search_code(project="gimle", pattern="NoSuchSymbol")
    assert isinstance(result, dict)
    assert result["ok"] is True
    assert result["results"] == []
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_case_insensitive_opt_in(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    _patch_resolver(monkeypatch, repo)
    assert (await native_search_code(project="gimle", pattern="hdwallet"))["total"] == 0
    insensitive = await native_search_code(
        project="gimle", pattern="hdwallet", case_sensitive=False
    )
    assert insensitive["total"] == 1


@pytest.mark.asyncio
async def test_max_results_caps_and_flags_truncation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "many.txt").write_text("HD\n" * 10)
    _patch_resolver(monkeypatch, tmp_path)
    result = await native_search_code(project="gimle", pattern="HD", max_results=3)
    assert result["total"] == 3
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_git_dir_is_excluded(monkeypatch: pytest.MonkeyPatch, repo: Path) -> None:
    (repo / ".git" / "COMMIT_EDITMSG").write_text("HDWallet refactor\n")
    _patch_resolver(monkeypatch, repo)
    result = await native_search_code(project="gimle", pattern="HDWallet")
    assert [r["file_path"] for r in result["results"]] == ["Sources/Wallet.swift"]


@pytest.mark.asyncio
async def test_pattern_starting_with_dash_is_not_read_as_a_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "f.txt").write_text("value --version here\n")
    _patch_resolver(monkeypatch, tmp_path)
    result = await native_search_code(project="gimle", pattern="--version")
    assert result["ok"] is True
    assert result["total"] == 1
