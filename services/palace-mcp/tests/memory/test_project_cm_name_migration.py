from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.migrations.m2026_06_backfill_project_cm_project_name import (
    _LIST_PROJECTS,
    _SET_PROJECT_CM_NAME,
    run_migration,
)


class _AsyncRows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = iter(rows)

    def __aiter__(self) -> "_AsyncRows":
        return self

    async def __anext__(self) -> dict[str, Any]:
        try:
            return next(self._rows)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def _driver_for_projects(
    rows: list[dict[str, Any]], writes: list[dict[str, str]]
) -> MagicMock:
    async def _run(query: str, **params: Any) -> Any:
        if query == _LIST_PROJECTS:
            return _AsyncRows(rows)
        if query == _SET_PROJECT_CM_NAME:
            writes.append(
                {"slug": params["slug"], "cm_project_name": params["cm_project_name"]}
            )
            result = MagicMock()
            result.single = AsyncMock(return_value={"slug": params["slug"]})
            return result
        raise AssertionError(f"unexpected query: {query}")

    session = MagicMock()
    session.run = AsyncMock(side_effect=_run)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


@pytest.mark.asyncio
async def test_run_migration_backfills_derivable_cm_project_names() -> None:
    writes: list[dict[str, str]] = []
    driver = _driver_for_projects(
        [
            {
                "slug": "gimle",
                "parent_mount": None,
                "relative_path": None,
                "cm_project_name": None,
            },
            {
                "slug": "evm-kit",
                "parent_mount": "hs",
                "relative_path": "EvmKit.Swift",
                "cm_project_name": None,
            },
            {
                "slug": "legacy-partial",
                "parent_mount": "hs",
                "relative_path": None,
                "cm_project_name": None,
            },
        ],
        writes,
    )

    migrated = await run_migration(driver)

    assert migrated == 2
    assert writes == [
        {"slug": "gimle", "cm_project_name": "repos-gimle"},
        {"slug": "evm-kit", "cm_project_name": "repos-hs-EvmKit.Swift"},
    ]


@pytest.mark.asyncio
async def test_run_migration_preserves_existing_cm_project_names() -> None:
    writes: list[dict[str, str]] = []
    driver = _driver_for_projects(
        [
            {
                "slug": "test-preserve",
                "parent_mount": "hs",
                "relative_path": "TronKit.Swift",
                "cm_project_name": "repos-existing-preserve",
            },
            {
                "slug": "gimle",
                "parent_mount": None,
                "relative_path": None,
                "cm_project_name": None,
            },
        ],
        writes,
    )

    migrated = await run_migration(driver)

    assert migrated == 1
    assert writes == [{"slug": "gimle", "cm_project_name": "repos-gimle"}]


@pytest.mark.asyncio
async def test_run_migration_raises_on_collision_preflight() -> None:
    writes: list[dict[str, str]] = []
    driver = _driver_for_projects(
        [
            {
                "slug": "alpha",
                "parent_mount": "hs",
                "relative_path": "Shared.swift",
                "cm_project_name": None,
            },
            {
                "slug": "beta",
                "parent_mount": "hs",
                "relative_path": "Shared.swift",
                "cm_project_name": None,
            },
        ],
        writes,
    )

    with pytest.raises(ValueError, match="collision pre-flight failed"):
        await run_migration(driver)

    assert writes == []


@pytest.mark.asyncio
async def test_run_migration_raises_when_cm_project_name_matches_another_slug() -> None:
    writes: list[dict[str, str]] = []
    driver = _driver_for_projects(
        [
            {
                "slug": "gimle",
                "parent_mount": None,
                "relative_path": None,
                "cm_project_name": None,
            },
            {
                "slug": "repos-gimle",
                "parent_mount": None,
                "relative_path": None,
                "cm_project_name": "repos-repos-gimle",
            },
        ],
        writes,
    )

    with pytest.raises(ValueError, match="collision pre-flight failed"):
        await run_migration(driver)

    assert writes == []
