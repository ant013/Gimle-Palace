"""Integration test: ensure_schema runs without error.

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


@pytest_asyncio.fixture(scope="module", loop_scope="module")
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
@pytest.mark.asyncio(loop_scope="module")
async def test_ensure_schema_runs_without_error(live_driver: Any) -> None:
    """ensure_schema completes idempotently on a live Neo4j."""
    from palace_mcp.memory.constraints import ensure_schema

    await ensure_schema(live_driver, default_group_id="project/integration-test")
    # A second run must also succeed (idempotency).
    await ensure_schema(live_driver, default_group_id="project/integration-test")

    async with live_driver.session() as session:
        row = await (
            await session.run(
                "MATCH (p:Project {slug: 'integration-test'}) "
                "RETURN p.group_id AS group_id, "
                "p.parent_mount AS parent_mount, "
                "p.relative_path AS relative_path"
            )
        ).single()

    assert row is not None
    assert row["group_id"] == "project/integration-test"
    assert row["parent_mount"] is None
    assert row["relative_path"] is None
