"""Integration test — HeartbeatExtractor writes :Episode node to Neo4j."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.heartbeat import HeartbeatExtractor


@pytest.mark.asyncio
async def test_heartbeat_writes_node(
    driver: AsyncDriver, graphiti_mock: MagicMock
) -> None:
    ctx = ExtractorRunContext(
        project_slug="gimle",
        group_id="project/gimle",
        repo_path=Path("/repos/gimle"),
        run_id="integ-run-heartbeat-001",
        duration_ms=0,
        logger=logging.getLogger("test"),
    )
    extractor = HeartbeatExtractor()
    stats = await extractor.run(graphiti=graphiti_mock, ctx=ctx)

    assert stats.nodes_written == 1
    assert stats.edges_written == 0

    async with driver.session() as s:
        result = await s.run("MATCH (n:Episode) RETURN count(n) AS c")
        row = await result.single()
    assert row is not None and row["c"] == 1
