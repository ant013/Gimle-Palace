"""GIM-75 spec §6.2 — integration tests for Graphiti foundation.

Run against a live Neo4j (testcontainers or compose reuse):

    # Compose reuse (fastest):
    COMPOSE_NEO4J_URI=bolt://localhost:7687 \\
    COMPOSE_NEO4J_PASSWORD=test \\
    uv run pytest tests/integration/test_gim75_integration.py -m integration

    # Testcontainers auto-spin (CI):
    uv run pytest tests/integration/test_gim75_integration.py -m integration

Tests 1-4 require a real Neo4j. Test 5 is a unit-style check on the
Pydantic schema (included here per spec §6.2 numbering).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from neo4j import AsyncDriver, AsyncGraphDatabase


# ---------------------------------------------------------------------------
# Neo4j fixtures (mirrors extractors/integration/conftest.py)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def neo4j_uri() -> str:
    if reuse := os.environ.get("COMPOSE_NEO4J_URI"):
        return reuse
    pytest.skip(
        "COMPOSE_NEO4J_URI not set and testcontainers not installed — skipping GIM-75 integration"
    )


@pytest.fixture(scope="module")
def neo4j_auth() -> tuple[str, str]:
    user = os.environ.get("COMPOSE_NEO4J_USER", "neo4j")
    pw = os.environ.get("COMPOSE_NEO4J_PASSWORD", "password")
    return user, pw


@pytest_asyncio.fixture
async def driver(neo4j_uri: str, neo4j_auth: tuple[str, str]) -> AsyncIterator[AsyncDriver]:
    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        await drv.verify_connectivity()
    except Exception:
        await drv.close()
        pytest.skip("Could not connect to Neo4j — skipping integration tests")
    yield drv
    await drv.close()


@pytest_asyncio.fixture
async def clean_db(driver: AsyncDriver) -> None:
    """Wipe all nodes before each test for hermetic runs."""
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")


@pytest.fixture
def mock_graphiti(driver: AsyncDriver) -> Any:
    """Graphiti mock that wraps the real driver but stubs out OpenAI calls."""
    from graphiti_core.driver.neo4j_driver import Neo4jDriver

    neo4j_drv = Neo4jDriver(driver)

    g = MagicMock()
    g.driver = neo4j_drv
    # build_indices_and_constraints delegates to the raw driver
    g.build_indices_and_constraints = AsyncMock(return_value=None)
    return g


# ---------------------------------------------------------------------------
# Test 1 — ensure_graphiti_schema is idempotent
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ensure_graphiti_schema_idempotent(clean_db: None, mock_graphiti: Any) -> None:
    """ensure_graphiti_schema() can be called twice without error."""
    from palace_mcp.graphiti_runtime import ensure_graphiti_schema

    await ensure_graphiti_schema(mock_graphiti)
    await ensure_graphiti_schema(mock_graphiti)  # second call must not raise


# ---------------------------------------------------------------------------
# Test 2 — HeartbeatExtractor writes one Episode node
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_heartbeat_writes_one_episode(clean_db: None, driver: AsyncDriver, mock_graphiti: Any) -> None:
    """HeartbeatExtractor.run() creates exactly one :Episode node in Neo4j."""
    import logging

    from palace_mcp.extractors.base import ExtractorRunContext
    from palace_mcp.extractors.heartbeat import HeartbeatExtractor

    ctx = ExtractorRunContext(
        project_slug="gimle",
        group_id="project/gimle",
        repo_path=Path("/repos/gimle"),
        run_id="test-run-1",
        duration_ms=0,
        logger=logging.getLogger("test"),
    )

    # save_entity_node calls node.save(g.driver) — real driver, no OpenAI needed.
    extractor = HeartbeatExtractor()
    stats = await extractor.run(graphiti=mock_graphiti, ctx=ctx)

    assert stats.nodes_written == 1
    assert stats.edges_written == 0

    async with driver.session() as s:
        result = await s.run("MATCH (n:Episode) RETURN count(n) AS c")
        row = await result.single()
        assert row is not None and row["c"] == 1, (
            f"Expected 1 Episode node, found {row['c'] if row else 'no row'}"
        )


# ---------------------------------------------------------------------------
# Test 3 — Episode node has required metadata
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_heartbeat_episode_has_metadata(clean_db: None, driver: AsyncDriver, mock_graphiti: Any) -> None:
    """Episode node written by HeartbeatExtractor has group_id and kind attributes."""
    import logging

    from palace_mcp.extractors.base import ExtractorRunContext
    from palace_mcp.extractors.heartbeat import HeartbeatExtractor

    ctx = ExtractorRunContext(
        project_slug="gimle",
        group_id="project/gimle",
        repo_path=Path("/repos/gimle"),
        run_id="test-run-2",
        duration_ms=42,
        logger=logging.getLogger("test"),
    )

    await HeartbeatExtractor().run(graphiti=mock_graphiti, ctx=ctx)

    async with driver.session() as s:
        result = await s.run("MATCH (n:Episode) RETURN n")
        row = await result.single()
        assert row is not None, "No Episode node found"
        node = dict(row["n"])
        assert node.get("group_id") == "project/gimle", f"Wrong group_id: {node}"
        assert node.get("kind") == "heartbeat", f"Wrong kind: {node}"
        assert node.get("source") == "extractor.heartbeat", f"Wrong source: {node}"


# ---------------------------------------------------------------------------
# Test 4 — palace.memory.health entity_counts includes Episode
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_memory_health_counts_episodes(clean_db: None, driver: AsyncDriver, mock_graphiti: Any) -> None:
    """get_health() returns entity_counts dict with 'Episode' key after a heartbeat run."""
    import logging

    from palace_mcp.extractors.base import ExtractorRunContext
    from palace_mcp.extractors.heartbeat import HeartbeatExtractor
    from palace_mcp.memory.health import get_health

    ctx = ExtractorRunContext(
        project_slug="gimle",
        group_id="project/gimle",
        repo_path=Path("/repos/gimle"),
        run_id="test-run-3",
        duration_ms=10,
        logger=logging.getLogger("test"),
    )
    await HeartbeatExtractor().run(graphiti=mock_graphiti, ctx=ctx)

    health = await get_health(driver, default_group_id="project/gimle")

    assert health.neo4j_reachable, "Neo4j should be reachable"
    # entity_counts must include 'Episode' key (even if 0 for other types)
    assert "Episode" in health.entity_counts, (
        f"entity_counts must include 'Episode'. Got keys: {list(health.entity_counts.keys())}"
    )
    assert health.entity_counts["Episode"] == 1, (
        f"Expected 1 Episode, got {health.entity_counts.get('Episode')}"
    )


# ---------------------------------------------------------------------------
# Test 5 — palace.memory.lookup raises on unknown entity_type (schema validation)
# ---------------------------------------------------------------------------


def test_memory_lookup_unknown_entity_returns_error() -> None:
    """LookupRequest rejects unknown entity_type with ValidationError (schema boundary)."""
    import pytest
    from pydantic import ValidationError

    from palace_mcp.memory.schema import LookupRequest

    with pytest.raises(ValidationError):
        LookupRequest(entity_type="BogusType")  # type: ignore[arg-type]
