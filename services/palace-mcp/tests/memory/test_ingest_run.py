"""Unit tests for palace_mcp.memory.ingest_run.write_ingest_run."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from palace_mcp.memory.ingest_run import write_ingest_run


def _make_graphiti() -> MagicMock:
    graphiti = MagicMock()
    graphiti.nodes.entity.save = AsyncMock(return_value=None)
    return graphiti


@pytest.mark.asyncio
async def test_write_ingest_run_saves_node() -> None:
    graphiti = _make_graphiti()
    await write_ingest_run(
        graphiti,
        run_id="run-uuid-1",
        started_at="2024-01-01T00:00:00+00:00",
        finished_at="2024-01-01T00:01:00+00:00",
        duration_ms=60000,
        errors=[],
        group_id="project/gimle",
    )
    graphiti.nodes.entity.save.assert_called_once()


@pytest.mark.asyncio
async def test_write_ingest_run_node_uuid_is_run_id() -> None:
    graphiti = _make_graphiti()
    await write_ingest_run(
        graphiti,
        run_id="my-run-id",
        started_at="2024-01-01T00:00:00+00:00",
        finished_at="2024-01-01T00:01:00+00:00",
        duration_ms=5000,
        errors=[],
        group_id="project/gimle",
    )
    saved_node = graphiti.nodes.entity.save.call_args[0][0]
    assert saved_node.uuid == "my-run-id"


@pytest.mark.asyncio
async def test_write_ingest_run_label_is_ingest_run() -> None:
    graphiti = _make_graphiti()
    await write_ingest_run(
        graphiti,
        run_id="r1",
        started_at="2024-01-01T00:00:00+00:00",
        finished_at="2024-01-01T00:01:00+00:00",
        duration_ms=1000,
        errors=[],
        group_id="project/gimle",
    )
    saved_node = graphiti.nodes.entity.save.call_args[0][0]
    assert "IngestRun" in saved_node.labels


@pytest.mark.asyncio
async def test_write_ingest_run_attributes_include_errors() -> None:
    graphiti = _make_graphiti()
    errors = ["NetworkError: timeout", "ValueError: bad data"]
    await write_ingest_run(
        graphiti,
        run_id="r1",
        started_at="2024-01-01T00:00:00+00:00",
        finished_at="2024-01-01T00:01:00+00:00",
        duration_ms=9000,
        errors=errors,
        group_id="project/gimle",
    )
    saved_node = graphiti.nodes.entity.save.call_args[0][0]
    assert saved_node.attributes["errors"] == errors


@pytest.mark.asyncio
async def test_write_ingest_run_source_default() -> None:
    graphiti = _make_graphiti()
    await write_ingest_run(
        graphiti,
        run_id="r1",
        started_at="2024-01-01T00:00:00+00:00",
        finished_at="2024-01-01T00:01:00+00:00",
        duration_ms=1000,
        errors=[],
        group_id="project/gimle",
    )
    saved_node = graphiti.nodes.entity.save.call_args[0][0]
    assert saved_node.attributes["source"] == "paperclip"


@pytest.mark.asyncio
async def test_write_ingest_run_source_override() -> None:
    graphiti = _make_graphiti()
    await write_ingest_run(
        graphiti,
        run_id="r1",
        started_at="2024-01-01T00:00:00+00:00",
        finished_at="2024-01-01T00:01:00+00:00",
        duration_ms=1000,
        errors=[],
        group_id="project/gimle",
        source="custom-source",
    )
    saved_node = graphiti.nodes.entity.save.call_args[0][0]
    assert saved_node.attributes["source"] == "custom-source"


@pytest.mark.asyncio
async def test_write_ingest_run_duration_ms_stored() -> None:
    graphiti = _make_graphiti()
    await write_ingest_run(
        graphiti,
        run_id="r1",
        started_at="2024-01-01T00:00:00+00:00",
        finished_at="2024-01-01T00:01:00+00:00",
        duration_ms=42000,
        errors=[],
        group_id="project/gimle",
    )
    saved_node = graphiti.nodes.entity.save.call_args[0][0]
    assert saved_node.attributes["duration_ms"] == 42000
