"""Unit tests for palace_mcp.memory.health.get_health — graphiti-core substrate."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.memory.health import get_health, _check_embedder
from palace_mcp.memory.schema import HealthResponse
from graphiti_core.nodes import EntityNode


def _make_entity_node(
    uuid: str,
    labels: list[str],
    attributes: dict,
) -> EntityNode:
    node = MagicMock(spec=EntityNode)
    node.uuid = uuid
    node.labels = labels
    node.attributes = attributes
    return node


def _make_graphiti(
    *,
    neo4j_reachable: bool = True,
    group_nodes: list[EntityNode] | None = None,
) -> MagicMock:
    """Build a minimal Graphiti mock for health tests."""
    graphiti = MagicMock()

    if neo4j_reachable:
        graphiti.driver.verify_connectivity = AsyncMock(return_value=None)
    else:
        graphiti.driver.verify_connectivity = AsyncMock(
            side_effect=Exception("conn refused")
        )

    nodes = group_nodes or []
    graphiti.nodes.entity.get_by_group_ids = AsyncMock(return_value=nodes)
    return graphiti


@pytest.mark.asyncio
async def test_get_health_neo4j_unreachable() -> None:
    graphiti = _make_graphiti(neo4j_reachable=False)
    result = await get_health(graphiti)
    assert result.neo4j_reachable is False
    assert result.entity_counts == {}
    assert result.embedder_reachable is False


@pytest.mark.asyncio
async def test_get_health_returns_entity_counts() -> None:
    nodes = [
        _make_entity_node("i1", ["Entity", "Issue"], {"source": "paperclip"}),
        _make_entity_node("i2", ["Entity", "Issue"], {"source": "paperclip"}),
        _make_entity_node("c1", ["Entity", "Comment"], {"source": "paperclip"}),
        _make_entity_node("a1", ["Entity", "Agent"], {"source": "paperclip"}),
    ]
    graphiti = _make_graphiti(group_nodes=nodes)
    result: HealthResponse = await get_health(graphiti)
    assert result.neo4j_reachable is True
    assert result.entity_counts["Issue"] == 2
    assert result.entity_counts["Comment"] == 1
    assert result.entity_counts["Agent"] == 1


@pytest.mark.asyncio
async def test_get_health_no_ingest_run() -> None:
    nodes = [
        _make_entity_node("i1", ["Entity", "Issue"], {"source": "paperclip"}),
    ]
    graphiti = _make_graphiti(group_nodes=nodes)
    result = await get_health(graphiti)
    assert result.last_ingest_started_at is None
    assert result.last_ingest_finished_at is None
    assert result.last_ingest_duration_ms is None
    assert result.last_ingest_errors == []


@pytest.mark.asyncio
async def test_get_health_latest_ingest_run() -> None:
    run1 = _make_entity_node(
        "run-1",
        ["Entity", "IngestRun"],
        {
            "started_at": "2024-01-01T10:00:00+00:00",
            "finished_at": "2024-01-01T10:01:00+00:00",
            "duration_ms": 60000,
            "errors": [],
        },
    )
    run2 = _make_entity_node(
        "run-2",
        ["Entity", "IngestRun"],
        {
            "started_at": "2024-01-02T10:00:00+00:00",
            "finished_at": "2024-01-02T10:01:00+00:00",
            "duration_ms": 55000,
            "errors": ["SomeError: oops"],
        },
    )
    graphiti = _make_graphiti(group_nodes=[run1, run2])
    result = await get_health(graphiti)
    # Most recent run (run2) should be returned
    assert result.last_ingest_started_at == "2024-01-02T10:00:00+00:00"
    assert result.last_ingest_duration_ms == 55000
    assert result.last_ingest_errors == ["SomeError: oops"]


@pytest.mark.asyncio
async def test_get_health_empty_graph() -> None:
    graphiti = _make_graphiti(group_nodes=[])
    result = await get_health(graphiti)
    assert result.neo4j_reachable is True
    assert result.entity_counts == {"Issue": 0, "Comment": 0, "Agent": 0}
    assert result.last_ingest_started_at is None


@pytest.mark.asyncio
async def test_get_health_group_fetch_failure_returns_partial() -> None:
    """If get_by_group_ids fails, returns reachable=True with empty counts."""
    graphiti = MagicMock()
    graphiti.driver.verify_connectivity = AsyncMock(return_value=None)
    graphiti.nodes.entity.get_by_group_ids = AsyncMock(
        side_effect=RuntimeError("graphiti error")
    )
    result = await get_health(graphiti)
    assert result.neo4j_reachable is True
    assert result.entity_counts == {}


@pytest.mark.asyncio
async def test_get_health_embedder_reachable() -> None:
    graphiti = _make_graphiti(group_nodes=[])
    with patch(
        "palace_mcp.memory.health._check_embedder", AsyncMock(return_value=True)
    ):
        result = await get_health(graphiti, embedder_base_url="http://ollama:11434/v1")
    assert result.embedder_reachable is True


@pytest.mark.asyncio
async def test_get_health_embedder_unreachable() -> None:
    graphiti = _make_graphiti(group_nodes=[])
    with patch(
        "palace_mcp.memory.health._check_embedder", AsyncMock(return_value=False)
    ):
        result = await get_health(graphiti, embedder_base_url="http://ollama:11434/v1")
    assert result.embedder_reachable is False


@pytest.mark.asyncio
async def test_get_health_no_embedder_url_skips_probe() -> None:
    """When embedder_base_url is empty, probe is skipped and reachable=False."""
    graphiti = _make_graphiti(group_nodes=[])
    result = await get_health(graphiti, embedder_base_url="")
    assert result.embedder_reachable is False


@pytest.mark.asyncio
async def test_check_embedder_success() -> None:
    """_check_embedder returns True when /models returns 2xx."""
    import httpx

    mock_resp = MagicMock()
    mock_resp.is_success = True

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await _check_embedder("http://ollama:11434/v1")
    assert result is True


@pytest.mark.asyncio
async def test_check_embedder_failure() -> None:
    """_check_embedder returns False on connection error."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await _check_embedder("http://ollama:11434/v1")
    assert result is False
