"""Integration test — ensure_extractors_schema creates declared constraints + indexes."""

from __future__ import annotations

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors import registry
from graphiti_core import Graphiti

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.schema import ensure_extractors_schema


class _SchemaTest(BaseExtractor):
    name = "__schema_test"
    description = "declares schema for testing"
    constraints = [
        "CREATE CONSTRAINT __schema_test_id IF NOT EXISTS "
        "FOR (n:__SchemaTestNode) REQUIRE n.id IS UNIQUE",
    ]
    indexes = [
        "CREATE INDEX __schema_test_ts IF NOT EXISTS "
        "FOR (n:__SchemaTestNode) ON (n.ts)",
    ]

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        return ExtractorStats()


@pytest.fixture(autouse=True)
def _isolate_registry() -> None:
    snap = dict(registry.EXTRACTORS)
    yield
    registry.EXTRACTORS.clear()
    registry.EXTRACTORS.update(snap)


@pytest.mark.asyncio
async def test_ensure_extractors_schema_creates_declared(driver: AsyncDriver) -> None:
    registry.register(_SchemaTest())
    await ensure_extractors_schema(driver)

    async with driver.session() as s:
        result = await s.run("SHOW CONSTRAINTS YIELD name")
        names = [row["name"] async for row in result]
    assert "__schema_test_id" in names

    async with driver.session() as s:
        result = await s.run("SHOW INDEXES YIELD name")
        names = [row["name"] async for row in result]
    assert "__schema_test_ts" in names


@pytest.mark.asyncio
async def test_ensure_extractors_schema_idempotent(driver: AsyncDriver) -> None:
    """Re-run succeeds without errors (IF NOT EXISTS)."""
    registry.register(_SchemaTest())
    await ensure_extractors_schema(driver)
    await ensure_extractors_schema(driver)  # second run should not raise


@pytest.mark.asyncio
async def test_ensure_extractors_schema_empty_registry(driver: AsyncDriver) -> None:
    """Empty registry → no-op, no errors."""
    await ensure_extractors_schema(driver)  # empty, should succeed
