"""Integration tests for audit discovery via :IngestRun (S1.4).

Seeds Neo4j with :IngestRun rows using S0.1 unified schema
(extractor_name, project fields), then asserts discovery returns
the latest successful run per extractor.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import pytest_asyncio
from neo4j import AsyncDriver, AsyncGraphDatabase

import os


@pytest.fixture(scope="session")
def neo4j_uri() -> Iterator[str]:
    if reuse := os.environ.get("COMPOSE_NEO4J_URI"):
        yield reuse
        return
    from testcontainers.neo4j import Neo4jContainer  # type: ignore[import]
    with Neo4jContainer("neo4j:5.26.0") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def neo4j_auth() -> tuple[str, str]:
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
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")


async def _seed_ingest_run(
    driver: AsyncDriver,
    *,
    run_id: str,
    extractor_name: str,
    project: str,
    success: bool,
    started_at: str,
) -> None:
    cypher = """
    CREATE (r:IngestRun {
        run_id: $run_id,
        extractor_name: $extractor_name,
        project: $project,
        success: $success,
        started_at: datetime($started_at)
    })
    """
    async with driver.session() as session:
        await session.run(
            cypher,
            run_id=run_id,
            extractor_name=extractor_name,
            project=project,
            success=success,
            started_at=started_at,
        )


@pytest.mark.integration
class TestAuditDiscovery:
    async def test_finds_latest_successful_run_per_extractor(self, driver: AsyncDriver) -> None:
        from palace_mcp.audit.discovery import find_latest_runs

        await _seed_ingest_run(driver, run_id="r1", extractor_name="hotspot", project="test-proj", success=True, started_at="2026-05-07T10:00:00Z")
        await _seed_ingest_run(driver, run_id="r2", extractor_name="hotspot", project="test-proj", success=True, started_at="2026-05-07T12:00:00Z")
        await _seed_ingest_run(driver, run_id="r3", extractor_name="dead_symbol_binary_surface", project="test-proj", success=True, started_at="2026-05-07T11:00:00Z")

        result = await find_latest_runs(driver, project="test-proj")

        assert "hotspot" in result
        assert result["hotspot"].run_id == "r2"  # latest
        assert "dead_symbol_binary_surface" in result
        assert result["dead_symbol_binary_surface"].run_id == "r3"

    async def test_ignores_failed_runs(self, driver: AsyncDriver) -> None:
        from palace_mcp.audit.discovery import find_latest_runs

        await _seed_ingest_run(driver, run_id="r-ok", extractor_name="hotspot", project="p", success=True, started_at="2026-05-07T09:00:00Z")
        await _seed_ingest_run(driver, run_id="r-fail", extractor_name="hotspot", project="p", success=False, started_at="2026-05-07T11:00:00Z")

        result = await find_latest_runs(driver, project="p")
        assert result["hotspot"].run_id == "r-ok"

    async def test_empty_project_returns_empty_dict(self, driver: AsyncDriver) -> None:
        from palace_mcp.audit.discovery import find_latest_runs

        result = await find_latest_runs(driver, project="no-such-project")
        assert result == {}

    async def test_different_projects_are_isolated(self, driver: AsyncDriver) -> None:
        from palace_mcp.audit.discovery import find_latest_runs

        await _seed_ingest_run(driver, run_id="r-a", extractor_name="hotspot", project="proj-a", success=True, started_at="2026-05-07T10:00:00Z")
        await _seed_ingest_run(driver, run_id="r-b", extractor_name="hotspot", project="proj-b", success=True, started_at="2026-05-07T10:00:00Z")

        result_a = await find_latest_runs(driver, project="proj-a")
        result_b = await find_latest_runs(driver, project="proj-b")

        assert result_a["hotspot"].run_id == "r-a"
        assert result_b["hotspot"].run_id == "r-b"
