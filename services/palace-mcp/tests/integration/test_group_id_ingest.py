"""Integration test: ingest stamps group_id on every node and GC is group-scoped.

Run against a live Neo4j with:
    NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=... uv run pytest tests/integration/ -m integration

Excluded from default CI run (--ignore=tests/integration).
"""

from __future__ import annotations

import os
from typing import Any

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def neo4j_uri() -> str:
    return os.environ.get("NEO4J_URI", "bolt://localhost:7687")


@pytest.fixture(scope="module")
def neo4j_password() -> str:
    pw = os.environ.get("NEO4J_PASSWORD", "")
    if not pw:
        pytest.skip("NEO4J_PASSWORD not set — skipping integration tests")
    return pw


@pytest_asyncio.fixture(scope="module")
async def live_driver(neo4j_uri: str, neo4j_password: str):  # type: ignore[no-untyped-def]
    from neo4j import AsyncGraphDatabase

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=("neo4j", neo4j_password))
    try:
        await driver.verify_connectivity()
    except Exception:
        await driver.close()
        pytest.skip("Could not connect to Neo4j — skipping integration tests")
    yield driver
    await driver.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ensure_schema_runs_without_error(live_driver: Any) -> None:
    """ensure_schema completes idempotently on a live Neo4j."""
    from palace_mcp.memory.constraints import ensure_schema

    await ensure_schema(live_driver, default_group_id="project/integration-test")
    # A second run must also succeed (idempotency).
    await ensure_schema(live_driver, default_group_id="project/integration-test")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ingest_stamps_group_id_on_nodes(live_driver: Any) -> None:
    """After a minimal ingest, every node carries the expected group_id."""
    import httpx

    from palace_mcp.ingest.paperclip_client import PaperclipClient
    from palace_mcp.ingest.runner import run_ingest
    from palace_mcp.memory.constraints import ensure_schema

    group_id = "project/integration-test"
    await ensure_schema(live_driver, default_group_id=group_id)

    # Use a mock transport so we don't need a live Paperclip instance.
    def _handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/agents" in path:
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "integ-agent-1",
                        "name": "TestAgent",
                        "urlKey": "test-agent",
                        "role": "dev",
                        "createdAt": "2026-01-01T00:00:00Z",
                        "updatedAt": "2026-01-01T00:00:00Z",
                    }
                ],
            )
        if "/comments" in path:
            return httpx.Response(200, json=[])
        if "/issues" in path:
            return httpx.Response(
                200,
                json={
                    "issues": [
                        {
                            "id": "integ-issue-1",
                            "identifier": "INTEG-1",
                            "title": "Integration Test Issue",
                            "status": "done",
                            "createdAt": "2026-01-01T00:00:00Z",
                            "updatedAt": "2026-01-01T00:00:00Z",
                        }
                    ]
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(_handler)
    async with PaperclipClient(
        base_url="https://pc-test", token="t", company_id="co-1", transport=transport
    ) as client:
        result = await run_ingest(client=client, driver=live_driver, group_id=group_id)

    assert result["errors"] == [], f"Ingest had errors: {result['errors']}"

    # Verify group_id is set on every ingested node.
    async with live_driver.session() as session:
        record = await session.run(
            """
            MATCH (n)
            WHERE n.id IN ['integ-agent-1', 'integ-issue-1']
              AND n.group_id IS NULL
            RETURN count(n) AS c
            """
        )
        row = await record.single()
        assert row is not None
        null_count = row["c"]
    assert null_count == 0, f"{null_count} nodes missing group_id after ingest"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_gc_does_not_cross_project_boundary(live_driver: Any) -> None:
    """GC run for project A must not delete nodes that belong to project B."""
    from palace_mcp.memory.constraints import ensure_schema

    group_a = "project/gc-test-A"
    group_b = "project/gc-test-B"

    await ensure_schema(live_driver, default_group_id=group_a)

    # Create one Agent node for each group.
    async with live_driver.session() as session:
        await session.run(
            "MERGE (a:Agent {id: $id}) SET a.group_id = $gid, a.source = 'paperclip', a.palace_last_seen_at = $ts",
            id="gc-test-agent-A",
            gid=group_a,
            ts="2000-01-01T00:00:00+00:00",  # far in the past → would be GC'd if unscoped
        )
        await session.run(
            "MERGE (a:Agent {id: $id}) SET a.group_id = $gid, a.source = 'paperclip', a.palace_last_seen_at = $ts",
            id="gc-test-agent-B",
            gid=group_b,
            ts="2000-01-01T00:00:00+00:00",
        )

    from palace_mcp.memory.cypher import GC_BY_LABEL

    gc_query = GC_BY_LABEL.format(label="Agent")
    cutoff = "2099-01-01T00:00:00+00:00"  # everything is stale relative to this

    # Run GC scoped to group_a only.
    async with live_driver.session() as session:
        await session.run(gc_query, group_id=group_a, cutoff=cutoff)

    # group_b node must still exist.
    async with live_driver.session() as session:
        record = await session.run(
            "MATCH (a:Agent {id: 'gc-test-agent-B'}) RETURN a.group_id AS gid"
        )
        row = await record.single()
    assert row is not None, (
        "GC deleted a node from a different project (cross-project leak)"
    )
    assert row["gid"] == group_b

    # Cleanup.
    async with live_driver.session() as session:
        await session.run(
            "MATCH (a:Agent) WHERE a.id IN ['gc-test-agent-A', 'gc-test-agent-B'] DETACH DELETE a"
        )
