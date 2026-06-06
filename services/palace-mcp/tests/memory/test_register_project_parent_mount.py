"""Tests for register_project parent_mount + relative_path extension (GIM-182 Step 3).

Covers:
- §8.10: register_project with parent_mount stores fields correctly
- §8.11: legacy project (no parent_mount) still works unchanged
- §8.21: invalid parent_mount / relative_path patterns rejected at boundary
- namespace collision guard: project slug must not conflict with bundle name
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.memory.project_tools import register_project
from palace_mcp.memory.schema import ProjectInfo

_NOW = "2026-05-03T12:00:00+00:00"


def _project_row(
    slug: str, *, parent_mount: str | None = None, relative_path: str | None = None
) -> dict[str, Any]:
    cm_project_name = None
    if parent_mount is None and relative_path is None:
        cm_project_name = f"repos-{slug}"
    elif parent_mount == "hs" and relative_path == "EvmKit.Swift":
        cm_project_name = "repos-hs-EvmKit.Swift"
    return {
        "p": {
            "slug": slug,
            "cm_project_name": cm_project_name,
            "name": slug.replace("-", " ").title(),
            "tags": [],
            "language": None,
            "framework": None,
            "repo_url": None,
            "parent_mount": parent_mount,
            "relative_path": relative_path,
            "source_created_at": _NOW,
            "source_updated_at": _NOW,
        }
    }


def _driver_for_sequence(*results: dict[str, Any] | None) -> MagicMock:
    """Fake driver returning the provided single() payloads in order."""
    queue = list(results)

    async def _run(query: str, **params: Any) -> Any:
        result = MagicMock()
        payload = queue.pop(0)
        if payload is None:
            result.single = AsyncMock(return_value=None)
            return result
        row = MagicMock()
        row.__getitem__ = lambda _self, key: payload[key]
        result.single = AsyncMock(return_value=row)
        return result

    session = MagicMock()
    session.run = AsyncMock(side_effect=_run)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


def _driver_for(returned_row: dict[str, Any]) -> MagicMock:
    """Fake driver returning returned_row on fourth run() call (after UPSERT)."""
    return _driver_for_sequence(None, None, None, returned_row)


# ---------------------------------------------------------------------------
# §8.10 — register_project with parent_mount stores fields
# ---------------------------------------------------------------------------


async def test_register_project_with_parent_mount_stores_fields() -> None:
    """parent_mount and relative_path are passed through to UPSERT and reflected in ProjectInfo."""
    row = _project_row("evm-kit", parent_mount="hs", relative_path="EvmKit.Swift")
    driver = _driver_for(row)

    info: ProjectInfo = await register_project(
        driver,
        slug="evm-kit",
        name="EvmKit",
        tags=[],
        parent_mount="hs",
        relative_path="EvmKit.Swift",
    )

    assert info.slug == "evm-kit"
    assert info.cm_project_name == "repos-hs-EvmKit.Swift"
    assert info.parent_mount == "hs"
    assert info.relative_path == "EvmKit.Swift"


# ---------------------------------------------------------------------------
# §8.11 — legacy (no parent_mount) unchanged
# ---------------------------------------------------------------------------


async def test_register_project_legacy_no_parent_mount() -> None:
    """Calling without parent_mount works exactly as before (backward-compatible)."""
    row = _project_row("gimle")
    driver = _driver_for(row)

    info: ProjectInfo = await register_project(
        driver,
        slug="gimle",
        name="Gimle",
        tags=[],
    )

    assert info.slug == "gimle"
    assert info.cm_project_name == "repos-gimle"
    assert info.parent_mount is None
    assert info.relative_path is None


# ---------------------------------------------------------------------------
# §8.21 — invalid parent_mount name rejected at boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_mount",
    [
        "../etc",
        "/absolute",
        "UPPER",
        "has_underscore",
        "toolongmountname12345",
        "",
    ],
)
async def test_register_project_invalid_parent_mount_rejected(bad_mount: str) -> None:
    """Invalid parent_mount name raises ValueError before any I/O."""
    driver = MagicMock()  # should never be called
    driver.session = MagicMock(side_effect=AssertionError("no I/O expected"))

    with pytest.raises(ValueError, match="parent_mount"):
        await register_project(
            driver,
            slug="evm-kit",
            name="EvmKit",
            tags=[],
            parent_mount=bad_mount,
            relative_path="EvmKit.Swift",
        )


# ---------------------------------------------------------------------------
# §8.21 — invalid relative_path rejected at boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_rel",
    [
        "../etc/passwd",
        "../../root",
        "",
        "/absolute",
        "path with spaces",
        "path\x00null",
    ],
)
async def test_register_project_invalid_relative_path_rejected(bad_rel: str) -> None:
    """Invalid relative_path raises ValueError before any I/O."""
    driver = MagicMock()
    driver.session = MagicMock(side_effect=AssertionError("no I/O expected"))

    with pytest.raises(ValueError, match="relative_path"):
        await register_project(
            driver,
            slug="evm-kit",
            name="EvmKit",
            tags=[],
            parent_mount="hs",
            relative_path=bad_rel,
        )


# ---------------------------------------------------------------------------
# namespace collision: project slug must not conflict with bundle name
# ---------------------------------------------------------------------------


async def test_register_project_bundle_slug_collision_rejected() -> None:
    """If a :Bundle with the same name exists, raise ProjectSlugConflictsWithBundle."""
    from palace_mcp.memory.bundle import ProjectSlugConflictsWithBundle

    # First run() returns a bundle row (conflict), second never called
    calls: list[int] = [0]

    async def _run(query: str, **params: Any) -> Any:
        calls[0] += 1
        result = MagicMock()
        result.single = AsyncMock(return_value={"b_name": "uw-ios"})
        return result

    session = MagicMock()
    session.run = AsyncMock(side_effect=_run)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    driver = MagicMock()
    driver.session = MagicMock(return_value=session)

    with pytest.raises(ProjectSlugConflictsWithBundle, match="uw-ios"):
        await register_project(
            driver,
            slug="uw-ios",
            name="UW iOS",
            tags=[],
        )


async def test_register_project_rejects_existing_cm_project_name_collision() -> None:
    driver = _driver_for_sequence(
        None,
        {"slug": "beta", "cm_project_name": "repos-hs-Shared.swift"},
    )

    with pytest.raises(ValueError, match="project namespace conflict"):
        await register_project(
            driver,
            slug="alpha",
            name="Alpha",
            tags=[],
            parent_mount="hs",
            relative_path="Shared.swift",
        )


async def test_register_project_rejects_slug_matching_existing_cm_project_name() -> (
    None
):
    driver = _driver_for_sequence(
        None,
        {"slug": "gimle", "cm_project_name": "repos-gimle"},
    )

    with pytest.raises(ValueError, match="project namespace conflict"):
        await register_project(
            driver,
            slug="repos-gimle",
            name="Repos Gimle",
            tags=[],
        )
