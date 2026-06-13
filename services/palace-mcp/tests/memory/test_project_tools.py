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
from palace_mcp.memory.cypher import PROJECT_ENTITY_COUNTS
from palace_mcp.memory.schema import ProjectInfo

_NOW = "2026-04-18T10:00:00+00:00"


class _Neo4jDateTimeLike:
    def __init__(self, value: str) -> None:
        self._value = value

    def iso_format(self) -> str:
        return self._value


def _make_project_row(
    slug: str,
    name: str,
    tags: list[str],
    *,
    cm_project_name: str | None = None,
    language: str | None = None,
    framework: str | None = None,
    repo_url: str | None = None,
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


@pytest.mark.asyncio
async def test_list_projects_serializes_neo4j_temporal_values() -> None:
    row = _make_project_row("uw-ios-app", "unstoppable-wallet-ios", [])
    row["p"]["source_created_at"] = _Neo4jDateTimeLike(_NOW)
    row["p"]["source_updated_at"] = _Neo4jDateTimeLike(_NOW)
    driver = _make_mock_driver_for_list([row])

    infos = await list_projects(driver)

    assert infos[0].source_created_at == _NOW
    assert infos[0].source_updated_at == _NOW


def _make_mock_driver_for_overview(
    project_row: dict[str, Any],
    count_rows: list[dict[str, Any]],
    last_ingest: dict[str, Any] | None = None,
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
            # PROJECT_LAST_INGEST
            if last_ingest is None:
                result.single = AsyncMock(return_value=None)
            else:
                row = MagicMock()
                row.__getitem__ = lambda _self, key: {"r": last_ingest}[key]
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
        {"labels": ["Issue"], "c": 10},
        {"labels": ["Comment"], "c": 5},
    ]
    driver = _make_mock_driver_for_overview(project_row, count_rows)
    info = await get_project_overview(driver, slug="gimle")
    assert info.slug == "gimle"
    assert info.entity_counts == {"Issue": 10, "Comment": 5}


@pytest.mark.asyncio
async def test_get_project_overview_returns_code_extractor_entity_counts() -> None:
    project_row = _make_project_row("uw-ios-app", "unstoppable-wallet-ios", ["swift"])
    count_rows = [
        {"labels": ["Symbol"], "c": 10},
        {"labels": ["File"], "c": 5},
        {"labels": ["DeadFinding"], "c": 2},
        {"labels": ["ExternalDependency"], "c": 1},
    ]
    driver = _make_mock_driver_for_overview(project_row, count_rows)

    info = await get_project_overview(driver, slug="uw-ios-app")

    assert info.entity_counts == {
        "Symbol": 10,
        "File": 5,
        "DeadFinding": 2,
        "ExternalDependency": 1,
    }


def test_project_entity_counts_uses_group_id_without_static_label_filter() -> None:
    assert "WHERE n.group_id = $group_id" in PROJECT_ENTITY_COUNTS
    assert "n:ExternalLib" not in PROJECT_ENTITY_COUNTS
    assert "n:Model" not in PROJECT_ENTITY_COUNTS
    assert "n:Trace" not in PROJECT_ENTITY_COUNTS


@pytest.mark.asyncio
async def test_get_project_overview_serializes_last_ingest_temporal_values() -> None:
    project_row = _make_project_row("gimle", "Gimle", ["infra"])
    last_ingest = {
        "started_at": _Neo4jDateTimeLike("2026-06-13T09:00:00+00:00"),
        "finished_at": _Neo4jDateTimeLike("2026-06-13T09:01:00+00:00"),
    }
    driver = _make_mock_driver_for_overview(project_row, [], last_ingest=last_ingest)

    info = await get_project_overview(driver, slug="gimle")

    assert info.last_ingest_started_at == "2026-06-13T09:00:00+00:00"
    assert info.last_ingest_finished_at == "2026-06-13T09:01:00+00:00"
