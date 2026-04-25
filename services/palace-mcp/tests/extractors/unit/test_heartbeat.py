"""Unit tests for HeartbeatExtractor — mock graphiti driver."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.heartbeat import HeartbeatExtractor


@pytest.mark.asyncio
async def test_heartbeat_run_writes_one_episode_and_returns_stats() -> None:
    graphiti = MagicMock()
    ctx = ExtractorRunContext(
        project_slug="gimle",
        group_id="project/gimle",
        repo_path=Path("/repos/gimle"),
        run_id="test-run-123",
        duration_ms=0,
        logger=logging.getLogger("test"),
    )

    with patch(
        "palace_mcp.extractors.heartbeat.save_entity_node", new_callable=AsyncMock
    ) as mock_save:
        extractor = HeartbeatExtractor()
        stats = await extractor.run(graphiti=graphiti, ctx=ctx)

    assert stats.nodes_written == 1
    assert stats.edges_written == 0
    mock_save.assert_called_once()
    node = mock_save.call_args.args[1]
    assert "Episode" in node.labels
    assert node.group_id == "project/gimle"
    assert node.attributes["kind"] == "heartbeat"


@pytest.mark.asyncio
async def test_heartbeat_episode_provenance_and_confidence() -> None:
    graphiti = MagicMock()
    ctx = ExtractorRunContext(
        project_slug="gimle",
        group_id="project/gimle",
        repo_path=Path("/repos/gimle"),
        run_id="run-xyz",
        duration_ms=42,
        logger=logging.getLogger("test"),
    )

    with patch(
        "palace_mcp.extractors.heartbeat.save_entity_node", new_callable=AsyncMock
    ) as mock_save:
        await HeartbeatExtractor().run(graphiti=graphiti, ctx=ctx)

    node = mock_save.call_args.args[1]
    assert node.attributes["provenance"] == "asserted"
    assert node.attributes["confidence"] == 1.0
    assert node.attributes["extractor"].startswith("heartbeat@")
