"""Tests for memory/constraints.py.

Static (unit) tests run always. Integration tests marked @pytest.mark.integration
require NEO4J_PASSWORD env var and a reachable Neo4j instance — skipped otherwise.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from palace_mcp.memory.constraints import ensure_schema
from palace_mcp.memory.cypher import BACKFILL_GROUP_ID


def test_backfill_has_where_is_null_guard() -> None:
    assert "WHERE n.group_id IS NULL" in BACKFILL_GROUP_ID


def test_backfill_covers_all_four_labels() -> None:
    for label in ("Issue", "Comment", "Agent", "IngestRun"):
        assert f"(n:{label})" in BACKFILL_GROUP_ID


def test_backfill_parameterises_default() -> None:
    assert "$default" in BACKFILL_GROUP_ID


# ---------------------------------------------------------------------------
# Integration fixtures (skip if no live Neo4j)
# ---------------------------------------------------------------------------


@pytest.fixture
def neo4j_password() -> str:
    pw = os.environ.get("NEO4J_PASSWORD", "")
    if not pw:
        pytest.skip("NEO4J_PASSWORD not set — skipping integration tests")
    return pw


@pytest.fixture
def neo4j_uri() -> str:
    return os.environ.get("NEO4J_URI", "bolt://localhost:7687")


@pytest.fixture
async def live_driver(neo4j_uri: str, neo4j_password: str) -> Any:  # type: ignore[misc]
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
# Task 3 integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ensure_schema_bootstraps_default_project(live_driver: Any) -> None:
    """First call to ensure_schema creates a :Project node for the default slug."""
    await ensure_schema(live_driver, default_group_id="project/test-bootstrap")

    async with live_driver.session() as s:
        result = await s.run(
            "MATCH (p:Project {slug: 'test-bootstrap'}) RETURN p.slug AS slug, "
            "p.group_id AS g, p.source_created_at AS ts"
        )
        row = await result.single()

    assert row is not None
    assert row["slug"] == "test-bootstrap"
    assert row["g"] == "project/test-bootstrap"
    assert row["ts"] is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ensure_schema_bootstrap_idempotent(live_driver: Any) -> None:
    """Second call does not rewrite source_created_at."""
    await ensure_schema(live_driver, default_group_id="project/test-idem")
    async with live_driver.session() as s:
        row1 = await (
            await s.run(
                "MATCH (p:Project {slug: 'test-idem'}) RETURN p.source_created_at AS t"
            )
        ).single()
    await ensure_schema(live_driver, default_group_id="project/test-idem")
    async with live_driver.session() as s:
        row2 = await (
            await s.run(
                "MATCH (p:Project {slug: 'test-idem'}) RETURN p.source_created_at AS t"
            )
        ).single()
    assert row1["t"] == row2["t"], "source_created_at must be preserved"


# ---------------------------------------------------------------------------
# Task 4 integration tests — integrity invariant
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ensure_schema_fails_on_unregistered_group_id(live_driver: Any) -> None:
    """If any Issue/Comment/Agent/IngestRun has a group_id with no :Project,
    ensure_schema raises a clear error."""
    from palace_mcp.memory.constraints import SchemaIntegrityError

    async with live_driver.session() as s:
        await s.run(
            "CREATE (:Issue {id: 'stray-t4', group_id: 'project/unregistered-t4', "
            "source: 'paperclip', palace_last_seen_at: '1970'})"
        )

    try:
        with pytest.raises(SchemaIntegrityError, match="unregistered"):
            await ensure_schema(live_driver, default_group_id="project/test-bootstrap")
    finally:
        async with live_driver.session() as s:
            await s.run("MATCH (n {id: 'stray-t4'}) DETACH DELETE n")
