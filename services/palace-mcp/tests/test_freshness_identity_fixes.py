"""F2/F3/F5 (Sprint-1 reliability): indexed-commit writer, registry
identity checks, and serving-checkout git identity."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import palace_mcp.git.path_resolver as path_resolver
from palace_mcp.git.path_resolver import registration_identity_check
from palace_mcp.memory.project_tools import register_project
from palace_mcp.project_analyze import _record_project_indexed_commit
from palace_mcp.runtime_identity import _resolve as resolve_identity_uncached


def _mk_repo(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main"], cwd=path, check=True, capture_output=True
    )


# ---------------------------------------------------------------- F3: identity


def test_identity_check_ok_through_symlink(tmp_path: Path) -> None:
    real = tmp_path / "Repos-hs" / "kit"
    _mk_repo(real)
    link = tmp_path / "alias"
    link.symlink_to(real)
    check = registration_identity_check(
        "kit",
        project_node={
            "repo_path": str(link),
            "parent_mount": "hs",
            "relative_path": "kit",
        },
        repos_root=tmp_path / "Repos",
    )
    assert check == "ok"  # symlink-normalized: alias == mount layout


def test_identity_check_flags_two_different_repos(tmp_path: Path) -> None:
    _mk_repo(tmp_path / "Repos-hs" / "kit")
    other = tmp_path / "Repos-hs" / "kit2"
    _mk_repo(other)
    check = registration_identity_check(
        "kit",
        project_node={
            "repo_path": str(other),
            "parent_mount": "hs",
            "relative_path": "kit",
        },
        repos_root=tmp_path / "Repos",
    )
    assert check == "path_mismatch"  # the hd-wallet-kit defect signature


def test_identity_check_missing_and_unresolved(tmp_path: Path) -> None:
    assert (
        registration_identity_check(
            "kit",
            project_node={"repo_path": str(tmp_path / "gone")},
            repos_root=tmp_path / "Repos",
        )
        == "repo_path_missing"
    )
    assert (
        registration_identity_check(
            "kit", project_node={}, repos_root=tmp_path / "Repos"
        )
        == "unresolved"
    )


@pytest.mark.asyncio
async def test_register_project_rejects_path_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mk_repo(tmp_path / "Repos-hs" / "kit")
    other = tmp_path / "Repos-hs" / "kit2"
    _mk_repo(other)
    monkeypatch.setattr(path_resolver, "REPOS_ROOT", tmp_path / "Repos")
    with pytest.raises(ValueError, match="different directories"):
        await register_project(
            MagicMock(),  # rejected before any driver use
            slug="kit",
            name="Kit",
            tags=[],
            parent_mount="hs",
            relative_path="kit",
            repo_path=str(other),
        )


@pytest.mark.asyncio
async def test_register_project_rejects_non_git_repo_path(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(ValueError, match="not a git repo"):
        await register_project(
            MagicMock(), slug="kit", name="Kit", tags=[], repo_path=str(plain)
        )


# ------------------------------------------------------------------ F2: writer


def _writer_driver(baseline_commit: str | None) -> tuple[MagicMock, list]:
    calls: list = []

    async def _run(query: str, **params: object) -> MagicMock:
        calls.append((query, params))
        result = MagicMock()
        if "ExtractorBaseline" in query:
            if baseline_commit is None:
                result.single = AsyncMock(return_value=None)
            else:
                row = MagicMock()
                row.__getitem__ = lambda _s, k: baseline_commit
                result.single = AsyncMock(return_value=row)
        else:
            result.single = AsyncMock(return_value=None)
        return result

    session = MagicMock()
    session.run = AsyncMock(side_effect=_run)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver, calls


@pytest.mark.asyncio
async def test_indexed_commit_written_from_baseline() -> None:
    driver, calls = _writer_driver("abc123")
    await _record_project_indexed_commit(
        driver, "kit", "symbol_index_swift", now_iso="2026-07-17T00:00:00+00:00"
    )
    set_calls = [c for c in calls if "SET p.indexed_commit =" in c[0]]
    assert len(set_calls) == 1
    assert set_calls[0][1]["indexed_commit"] == "abc123"
    # monotonic guard present in the query
    assert "p.indexed_at IS NULL OR p.indexed_at <=" in set_calls[0][0]


@pytest.mark.asyncio
async def test_indexed_commit_decline_is_persisted_not_just_logged() -> None:
    driver, calls = _writer_driver(None)
    await _record_project_indexed_commit(
        driver, "kit", "symbol_index_swift", now_iso="2026-07-17T00:00:00+00:00"
    )
    mark_calls = [c for c in calls if "indexed_commit_status = 'unavailable'" in c[0]]
    assert len(mark_calls) == 1  # absence must be payload-diagnosable


# ---------------------------------------------------------------- F5: identity


def test_git_identity_resolves_real_worktree() -> None:
    identity = resolve_identity_uncached()
    # This test runs inside a real checkout (worktree with a .git FILE) —
    # resolution must succeed and never fall back to the env label as sha.
    assert identity.git_sha_source == "resolved"
    assert identity.git_sha is not None and len(identity.git_sha) == 40
    assert identity.source_checkout is not None
    assert identity.git_dirty in (True, False)
    assert identity.git_sha_error is None
