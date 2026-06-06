from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.code.namespace import (
    SlugRegisteredButUnmapped,
    assert_known_project,
    invalidate,
    resolve,
)
from palace_mcp.memory.projects import UnknownProjectError


def _driver_for_rows(*rows: dict[str, object] | None) -> MagicMock:
    queue = list(rows)

    async def _run(query: str, **params: object) -> object:
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


@pytest.mark.asyncio
async def test_resolve_accepts_slug() -> None:
    invalidate()
    driver = _driver_for_rows(
        {"p": {"slug": "gimle", "cm_project_name": "repos-gimle"}}
    )

    resolution = await resolve(driver, "gimle")

    assert resolution.slug == "gimle"
    assert resolution.cm_project_name == "repos-gimle"


@pytest.mark.asyncio
async def test_resolve_accepts_cm_project_name() -> None:
    invalidate()
    driver = _driver_for_rows(
        {"p": {"slug": "evm-kit", "cm_project_name": "repos-hs-EvmKit.Swift"}}
    )

    resolution = await resolve(driver, "repos-hs-EvmKit.Swift")

    assert resolution.slug == "evm-kit"
    assert resolution.cm_project_name == "repos-hs-EvmKit.Swift"


@pytest.mark.asyncio
async def test_resolve_raises_slug_registered_but_unmapped() -> None:
    invalidate()
    driver = _driver_for_rows({"p": {"slug": "legacy", "cm_project_name": None}})

    with pytest.raises(SlugRegisteredButUnmapped, match="legacy"):
        await resolve(driver, "legacy")


@pytest.mark.asyncio
async def test_assert_known_project_raises_unknown_project() -> None:
    invalidate()
    driver = _driver_for_rows(None)

    with pytest.raises(UnknownProjectError, match="bogus"):
        await assert_known_project(driver, "bogus")


@pytest.mark.asyncio
async def test_invalidate_clears_namespace_cache() -> None:
    invalidate()
    driver = _driver_for_rows(
        {"p": {"slug": "gimle", "cm_project_name": "repos-gimle"}},
        {"p": {"slug": "gimle", "cm_project_name": "repos-gimle-v2"}},
    )

    first = await resolve(driver, "gimle")
    second = await resolve(driver, "gimle")
    invalidate()
    third = await resolve(driver, "gimle")

    assert first.cm_project_name == "repos-gimle"
    assert second.cm_project_name == "repos-gimle"
    assert third.cm_project_name == "repos-gimle-v2"


@pytest.mark.asyncio
async def test_resolve_logs_redacted_cm_name(caplog: pytest.LogCaptureFixture) -> None:
    invalidate()
    driver = _driver_for_rows(
        {"p": {"slug": "gimle", "cm_project_name": "repos-gimle"}}
    )

    with caplog.at_level(logging.DEBUG, logger="palace_mcp.code.namespace"):
        await resolve(driver, "gimle")

    assert (
        "namespace.resolve requested=gimle slug=gimle cm_project_name=<redacted>"
        in caplog.text
    )
    assert "repos-gimle" not in caplog.text
