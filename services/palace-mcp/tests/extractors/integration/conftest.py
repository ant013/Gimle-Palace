"""Integration test fixtures — real Neo4j via testcontainers or compose reuse.

Per spec §7.2: COMPOSE_NEO4J_URI env-var selects reuse of an existing
compose Neo4j; absent, spin up a throwaway container.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from neo4j import AsyncDriver, AsyncGraphDatabase

from tests.integration.neo4j_runtime_support import ensure_reachable_neo4j_uri


@pytest.fixture(scope="session")
def neo4j_uri() -> Iterator[str]:
    if reuse := os.environ.get("COMPOSE_NEO4J_URI"):
        yield ensure_reachable_neo4j_uri(reuse)
        return

    try:
        from testcontainers.neo4j import Neo4jContainer  # type: ignore[import]
    except Exception as exc:
        pytest.skip(
            f"testcontainers.neo4j unavailable — skipping extractor integration tests: {exc}"
        )

    try:
        with Neo4jContainer("neo4j:5.26.0") as container:
            yield container.get_connection_url()
    except Exception as exc:
        pytest.skip(
            f"Could not start Neo4j testcontainer — skipping extractor integration tests: {exc}"
        )


@pytest.fixture(scope="session")
def neo4j_auth() -> tuple[str, str]:
    """Default auth for testcontainers; override if using compose reuse."""
    user = os.environ.get("COMPOSE_NEO4J_USER", "neo4j")
    pw = os.environ.get("COMPOSE_NEO4J_PASSWORD", "password")
    return user, pw


@pytest.fixture
async def driver(neo4j_uri: str, neo4j_auth: tuple[str, str]) -> Iterator[AsyncDriver]:
    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        yield drv
    finally:
        await drv.close()


@pytest.fixture(autouse=True)
async def clean_db(driver: AsyncDriver) -> None:
    """Clean all nodes between tests for hermetic runs."""
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")


@pytest.fixture
def graphiti_mock(neo4j_uri: str, neo4j_auth: tuple[str, str]) -> MagicMock:
    """Mock Graphiti with a real Neo4jDriver and a dummy embedder.

    Passes a Neo4jDriver backed by the test-container URI so save_entity_node
    can write to real Neo4j without making OpenAI API calls.
    """
    from graphiti_core.driver.neo4j_driver import Neo4jDriver

    user, password = neo4j_auth
    g = MagicMock()
    g.driver = Neo4jDriver(neo4j_uri, user=user, password=password)
    g.embedder = MagicMock()
    g.embedder.create = AsyncMock(return_value=[0.0] * 1024)
    g.embedder.create_batch = AsyncMock(
        side_effect=lambda texts: [[0.0] * 1024 for _ in texts]
    )
    g.build_indices_and_constraints = AsyncMock(return_value=None)
    return g
