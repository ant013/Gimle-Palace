"""Unit tests for palace_mcp.memory.project_tools."""

from __future__ import annotations

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
    language: str | None = None,
    framework: str | None = None,
    repo_url: str | None = None,
) -> dict[str, Any]:
    return {
        "p": {
            "slug": slug,
            "name": name,
            "tags": tags,
            "language": language,
            "framework": framework,
            "repo_url": repo_url,
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
        if call_count[0] == 1:
            # UPSERT_PROJECT — result unused
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
        "alpha", "Alpha", [], language="Kotlin", framework="KMP", repo_url="https://gh/alpha"
    )
    driver = _make_mock_driver_for_register(row)
    info = await register_project(
        driver, slug="alpha", name="Alpha", tags=[],
        language="Kotlin", framework="KMP", repo_url="https://gh/alpha",
    )
    assert info.language == "Kotlin"
    assert info.framework == "KMP"
    assert info.repo_url == "https://gh/alpha"


# ---------------------------------------------------------------------------
# Task 9: list_projects + get_project_overview
# ---------------------------------------------------------------------------


def _make_mock_driver_for_list(
    project_rows: list[dict[str, Any]],
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

    async def _run(query: str, **params: Any) -> Any:
        return _AsyncRows(project_rows)

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


def _make_mock_driver_for_overview(
    project_row: dict[str, Any],
    count_rows: list[dict[str, Any]],
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
        else:
            # PROJECT_LAST_INGEST — no ingest run
            result.single = AsyncMock(return_value=None)
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
        {"labels": ["Issue"], "c": 10},
        {"labels": ["Comment"], "c": 5},
    ]
    driver = _make_mock_driver_for_overview(project_row, count_rows)
    info = await get_project_overview(driver, slug="gimle")
    assert info.slug == "gimle"
    assert info.entity_counts == {"Issue": 10, "Comment": 5}
