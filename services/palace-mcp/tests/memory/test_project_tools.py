"""Unit tests for palace_mcp.memory.project_tools."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.memory.project_tools import (
    get_project_overview,
    list_projects,
    register_project,
)
from palace_mcp.memory.schema import ProjectInfo

_NOW = "2026-04-18T10:00:00+00:00"


def _make_project_row(
    slug: str,
    name: str,
    tags: list[str],
    *,
    cm_project_name: str | None = None,
    language: str | None = None,
    framework: str | None = None,
    repo_url: str | None = None,
    repo_path: str | None = None,
    expected_profile: bool = False,
) -> dict[str, Any]:
    return {
        "p": {
            "slug": slug,
            "cm_project_name": cm_project_name,
            "name": name,
            "tags": tags,
            "language": language,
            "framework": framework,
            "repo_url": repo_url,
            "repo_path": repo_path,
            "expected_profile": expected_profile,
            "source_created_at": _NOW,
            "source_updated_at": _NOW,
        }
    }


def _make_mock_driver_for_register(
    returned_row: dict[str, Any],
) -> MagicMock:
    call_count: list[int] = [0]

    async def _run(query: str, **params: Any) -> Any:
        call_count[0] += 1
        result = MagicMock()
        if call_count[0] in (1, 2, 3):
            # bundle check, namespace check, UPSERT_PROJECT — result unused
            result.single = AsyncMock(return_value=None)
            return result
        else:
            # GET_PROJECT — returns project row
            row = MagicMock()
            row.__getitem__ = lambda _self, key: returned_row[key]
            result.single = AsyncMock(return_value=row)
            return result

    session = MagicMock()
    session.run = _run
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    driver = MagicMock()
    driver.session.return_value = session
    return driver


# ---------------------------------------------------------------------------
# Task 8: register_project
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_project_returns_project_info() -> None:
    row = _make_project_row("medic", "Medic Healthcare", ["mobile", "kmp"])
    driver = _make_mock_driver_for_register(row)
    info = await register_project(
        driver, slug="medic", name="Medic Healthcare", tags=["mobile", "kmp"]
    )
    assert isinstance(info, ProjectInfo)
    assert info.slug == "medic"
    assert info.name == "Medic Healthcare"
    assert info.tags == ["mobile", "kmp"]
    assert info.source_created_at == _NOW


@pytest.mark.asyncio
async def test_register_project_optional_fields() -> None:
    row = _make_project_row(
        "alpha",
        "Alpha",
        [],
        cm_project_name="repos-alpha",
        language="Kotlin",
        framework="KMP",
        repo_url="https://gh/alpha",
        expected_profile=True,
    )
    driver = _make_mock_driver_for_register(row)
    info = await register_project(
        driver,
        slug="alpha",
        name="Alpha",
        tags=[],
        language="Kotlin",
        framework="KMP",
        repo_url="https://gh/alpha",
    )
    assert info.language == "Kotlin"
    assert info.framework == "KMP"
    assert info.repo_url == "https://gh/alpha"
    assert info.cm_project_name == "repos-alpha"
    assert info.expected_profile is True


@pytest.mark.asyncio
async def test_register_project_invalidates_namespace_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _make_project_row("gimle", "Gimle", [], cm_project_name="repos-gimle")
    driver = _make_mock_driver_for_register(row)
    invalidations: list[str] = []

    monkeypatch.setattr(
        "palace_mcp.code.namespace.invalidate",
        lambda: invalidations.append("cleared"),
    )

    await register_project(driver, slug="gimle", name="Gimle", tags=[])

    assert invalidations == ["cleared"]


# ---------------------------------------------------------------------------
# Task 9: list_projects + get_project_overview
# ---------------------------------------------------------------------------


def _make_mock_driver_for_list(
    project_rows: list[dict[str, Any]],
    count_rows: list[dict[str, Any]] | None = None,
) -> MagicMock:
    class _AsyncRows:
        def __init__(self, rows: list[dict[str, Any]]) -> None:
            self._iter = iter(rows)

        def __aiter__(self) -> "_AsyncRows":
            return self

        async def __anext__(self) -> dict[str, Any]:
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration

    call_count: list[int] = [0]

    async def _run(query: str, **params: Any) -> Any:
        call_count[0] += 1
        if call_count[0] == 1:
            return _AsyncRows(project_rows)
        return _AsyncRows(count_rows or [])

    session = MagicMock()
    session.run = _run
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    driver = MagicMock()
    driver.session.return_value = session
    return driver


@pytest.mark.asyncio
async def test_list_projects_returns_sorted_slugs() -> None:
    # Mock simulates DB ORDER BY p.slug — already sorted
    rows = [
        {"p": {**_make_project_row("gimle", "Gimle", [])["p"]}},
        {"p": {**_make_project_row("medic", "Medic", [])["p"]}},
    ]
    driver = _make_mock_driver_for_list(rows)
    infos = await list_projects(driver)
    slugs = [i.slug for i in infos]
    assert slugs == ["gimle", "medic"]


@pytest.mark.asyncio
async def test_list_projects_returns_separate_code_index_stats() -> None:
    rows = [
        {"p": {**_make_project_row("gimle", "Gimle", [])["p"]}},
        {"p": {**_make_project_row("medic", "Medic", [])["p"]}},
    ]
    count_rows = [
        {"slug": "gimle", "type": "Episode", "cnt": 2},
        {"slug": "gimle", "type": "Symbol", "cnt": 7},
        {"slug": "medic", "type": "Module", "cnt": 3},
    ]
    driver = _make_mock_driver_for_list(rows, count_rows)

    infos = await list_projects(driver)

    assert infos[0].slug == "gimle"
    assert infos[0].entity_counts == {"Episode": 2}
    assert infos[0].code_index_stats == {"Symbol": 7}
    assert infos[1].slug == "medic"
    assert infos[1].entity_counts == {}
    assert infos[1].code_index_stats == {"Module": 3}


@pytest.mark.asyncio
async def test_list_projects_tolerates_null_timestamps() -> None:
    # Regression: GIM-121. Some legacy :Project nodes have null
    # source_created_at/source_updated_at; ProjectInfo must accept None.
    legacy_row = _make_project_row("legacy", "Legacy Project", [])
    legacy_row["p"]["source_created_at"] = None
    legacy_row["p"]["source_updated_at"] = None
    rows = [{"p": {**legacy_row["p"]}}]
    driver = _make_mock_driver_for_list(rows)
    infos = await list_projects(driver)
    assert len(infos) == 1
    assert infos[0].slug == "legacy"
    assert infos[0].source_created_at is None
    assert infos[0].source_updated_at is None


def _make_mock_driver_for_overview(
    project_row: dict[str, Any],
    count_rows: list[dict[str, Any]],
    *,
    indexed_commit: str | None = None,
) -> MagicMock:
    call_count: list[int] = [0]

    class _AsyncRows:
        def __init__(self, rows: list[dict[str, Any]]) -> None:
            self._iter = iter(rows)

        def __aiter__(self) -> "_AsyncRows":
            return self

        async def __anext__(self) -> dict[str, Any]:
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration

    async def _run(query: str, **params: Any) -> Any:
        call_count[0] += 1
        result = MagicMock()
        if call_count[0] == 1:
            # GET_PROJECT
            row = MagicMock()
            row.__getitem__ = lambda _self, key: project_row[key]
            result.single = AsyncMock(return_value=row)
            return result
        elif call_count[0] == 2:
            # PROJECT_ENTITY_COUNTS
            return _AsyncRows(count_rows)
        elif call_count[0] == 3:
            # PROJECT_LAST_INGEST — no ingest run
            result.single = AsyncMock(return_value=None)
            return result
        else:
            if indexed_commit is None:
                result.single = AsyncMock(return_value=None)
                return result
            row = MagicMock()
            row.__getitem__ = lambda _self, key: {"commit_sha": indexed_commit}[key]
            result.single = AsyncMock(return_value=row)
            return result

    session = MagicMock()
    session.run = _run
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    driver = MagicMock()
    driver.session.return_value = session
    return driver


@pytest.mark.asyncio
async def test_get_project_overview_returns_entity_counts() -> None:
    project_row = _make_project_row("gimle", "Gimle", ["infra"])
    count_rows = [
        {"labels": ["Episode"], "c": 10},
        {"labels": ["Iteration"], "c": 5},
        {"labels": ["Symbol"], "c": 3},
    ]
    driver = _make_mock_driver_for_overview(project_row, count_rows)
    info = await get_project_overview(driver, slug="gimle")
    assert info.slug == "gimle"
    assert info.entity_counts == {"Episode": 10, "Iteration": 5}
    assert info.code_index_stats == {"Symbol": 3}


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def _run_text(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        args, cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.mark.asyncio
async def test_get_project_overview_reports_freshness_metadata(
    tmp_path: Path,
) -> None:
    repo_path = tmp_path / "gimle"
    repo_path.mkdir()
    _run(["git", "init", "-q", "-b", "main"], cwd=repo_path)
    _run(["git", "config", "user.email", "t@t"], cwd=repo_path)
    _run(["git", "config", "user.name", "T"], cwd=repo_path)
    (repo_path / "Wallet.swift").write_text("struct Wallet {}\n")
    _run(["git", "add", "."], cwd=repo_path)
    _run(["git", "commit", "-m", "initial", "-q"], cwd=repo_path)
    indexed_commit = _run_text(["git", "rev-parse", "HEAD"], cwd=repo_path)
    (repo_path / "Wallet.swift").write_text("struct Wallet { let id = 1 }\n")
    _run(["git", "add", "."], cwd=repo_path)
    _run(["git", "commit", "-m", "update", "-q"], cwd=repo_path)

    project_row = _make_project_row(
        "gimle",
        "Gimle",
        ["infra"],
        repo_path=str(repo_path),
    )
    driver = _make_mock_driver_for_overview(
        project_row,
        [],
        indexed_commit=indexed_commit,
    )

    info = await get_project_overview(driver, slug="gimle")

    assert info.indexed_commit == indexed_commit
    assert info.commits_behind_head == 1
