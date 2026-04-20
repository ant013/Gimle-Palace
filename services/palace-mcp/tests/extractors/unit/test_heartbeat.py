"""Unit tests for HeartbeatExtractor — mock driver."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.extractors.base import ExtractionContext
from palace_mcp.extractors.heartbeat import HeartbeatExtractor


@pytest.mark.asyncio
async def test_heartbeat_extract_writes_and_returns_stats() -> None:
    result = AsyncMock()
    session = AsyncMock()
    session.run = AsyncMock(return_value=result)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)

    driver = MagicMock()
    driver.session = MagicMock(return_value=cm)

    ctx = ExtractionContext(
        driver=driver,
        project_slug="gimle",
        group_id="project/gimle",
        repo_path=Path("/repos/gimle"),
        run_id="test-run-123",
        logger=logging.getLogger("test"),
    )

    extractor = HeartbeatExtractor()
    stats = await extractor.extract(ctx)

    assert stats.nodes_written == 1
    assert stats.edges_written == 0

    session.run.assert_called_once()
    call_args = session.run.call_args
    cypher = call_args.args[0]
    kwargs = call_args.kwargs
    assert "MERGE (h:ExtractorHeartbeat" in cypher
    assert kwargs["run_id"] == "test-run-123"
    assert kwargs["extractor"] == "heartbeat"
    assert kwargs["group_id"] == "project/gimle"
    assert "ts" in kwargs  # ISO-8601 string
