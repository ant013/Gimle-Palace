"""Integration test fixtures — real Neo4j via testcontainers or compose reuse.

Per spec §7.2: COMPOSE_NEO4J_URI env-var selects reuse of an existing
compose Neo4j; absent, spin up a throwaway container.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from neo4j import AsyncGraphDatabase, AsyncDriver


@pytest.fixture(scope="session")
def neo4j_uri() -> Iterator[str]:
    if reuse := os.environ.get("COMPOSE_NEO4J_URI"):
        yield reuse
        return

    # Fallback: boot a throwaway Neo4j container.
    from testcontainers.neo4j import Neo4jContainer  # type: ignore[import]

    with Neo4jContainer("neo4j:5.26.0") as container:
        yield container.get_connection_url()


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
