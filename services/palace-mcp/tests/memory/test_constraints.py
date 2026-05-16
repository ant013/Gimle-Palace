"""Tests for memory/constraints.py.

Integration tests marked @pytest.mark.integration require NEO4J_PASSWORD env var
and a reachable Neo4j instance — skipped otherwise.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.memory.constraints import ensure_schema


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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ensure_schema_preserves_registered_project_metadata(
    live_driver: Any,
) -> None:
    async with live_driver.session() as s:
        await s.run(
            """
            MERGE (p:Project {slug: 'test-preserve'})
            SET p.group_id = 'project/test-preserve',
                p.name = 'Real Name',
                p.parent_mount = 'hs-stage',
                p.relative_path = 'TronKit.Swift',
                p.language_profile = 'swift_kit'
            """
        )

    await ensure_schema(live_driver, default_group_id="project/test-preserve")

    async with live_driver.session() as s:
        row = await (
            await s.run(
                "MATCH (p:Project {slug: 'test-preserve'}) "
                "RETURN p.name AS name, p.parent_mount AS parent_mount, "
                "p.relative_path AS relative_path, "
                "p.language_profile AS language_profile"
            )
        ).single()

    assert row is not None
    assert row["name"] == "Real Name"
    assert row["parent_mount"] == "hs-stage"
    assert row["relative_path"] == "TronKit.Swift"
    assert row["language_profile"] == "swift_kit"


# ---------------------------------------------------------------------------
# Task 4 integration tests — integrity invariant
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ensure_schema_fails_on_unregistered_group_id(live_driver: Any) -> None:
    """If any Graphiti entity has a group_id with no :Project, ensure_schema raises."""
    from palace_mcp.memory.constraints import SchemaIntegrityError

    async with live_driver.session() as s:
        await s.run(
            "CREATE (:Episode {uuid: 'stray-t4', group_id: 'project/unregistered-t4'})"
        )

    try:
        with pytest.raises(SchemaIntegrityError, match="unregistered"):
            await ensure_schema(live_driver, default_group_id="project/test-bootstrap")
    finally:
        async with live_driver.session() as s:
            await s.run("MATCH (n:Episode {uuid: 'stray-t4'}) DETACH DELETE n")


@pytest.mark.asyncio
async def test_ensure_schema_bootstrap_upsert_supplies_optional_project_fields() -> (
    None
):
    from palace_mcp.memory.cypher import BOOTSTRAP_PROJECT

    driver = AsyncMock()
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    driver.session = MagicMock(return_value=session)

    empty_result = AsyncMock()
    empty_result.single.return_value = {"unregistered": []}

    async def run_side_effect(query: str, **kwargs: Any) -> Any:
        if query == BOOTSTRAP_PROJECT:
            return None
        if "RETURN collect(g) AS unregistered" in query:
            return empty_result
        return None

    session.run.side_effect = run_side_effect

    await ensure_schema(driver, default_group_id="project/test-bootstrap")

    upsert_call = next(
        call
        for call in session.run.await_args_list
        if call.args[0] == BOOTSTRAP_PROJECT
    )
    assert upsert_call.kwargs["parent_mount"] is None
    assert upsert_call.kwargs["relative_path"] is None
    assert upsert_call.kwargs["language_profile"] is None
