"""Integration test — HeartbeatExtractor writes :ExtractorHeartbeat node to Neo4j."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.base import ExtractionContext
from palace_mcp.extractors.heartbeat import HeartbeatExtractor


@pytest.mark.asyncio
async def test_heartbeat_writes_node(driver: AsyncDriver) -> None:
    ctx = ExtractionContext(
        driver=driver,
        project_slug="gimle",
        group_id="project/gimle",
        repo_path=Path("/repos/gimle"),
        run_id="integ-run-heartbeat-001",
        logger=logging.getLogger("test"),
    )
    extractor = HeartbeatExtractor()
    stats = await extractor.extract(ctx)

    assert stats.nodes_written == 1
    assert stats.edges_written == 0

    async with driver.session() as s:
        result = await s.run(
            "MATCH (h:ExtractorHeartbeat {run_id: $run_id}) RETURN h",
            run_id="integ-run-heartbeat-001",
        )
        row = await result.single()
    assert row is not None
    node = row["h"]
    assert node["extractor"] == "heartbeat"
    assert node["group_id"] == "project/gimle"
    assert node["ts"] is not None


@pytest.mark.asyncio
async def test_heartbeat_idempotent(driver: AsyncDriver) -> None:
    """Second extract with same run_id does not create a duplicate node."""
    ctx = ExtractionContext(
        driver=driver,
        project_slug="gimle",
        group_id="project/gimle",
        repo_path=Path("/repos/gimle"),
        run_id="integ-run-heartbeat-idem",
        logger=logging.getLogger("test"),
    )
    extractor = HeartbeatExtractor()
    await extractor.extract(ctx)
    await extractor.extract(ctx)  # second call — MERGE should not duplicate

    async with driver.session() as s:
        result = await s.run(
            "MATCH (h:ExtractorHeartbeat {run_id: $run_id}) RETURN count(h) AS cnt",
            run_id="integ-run-heartbeat-idem",
        )
        row = await result.single()
    assert row is not None
    assert row["cnt"] == 1
