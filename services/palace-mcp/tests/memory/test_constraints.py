"""Tests for memory/constraints.py.

Integration tests marked @pytest.mark.integration require NEO4J_PASSWORD env var
and a reachable Neo4j instance — skipped otherwise.
"""

from __future__ import annotations

import asyncio
import os
from time import monotonic
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


async def _wait_for_group_id_trigger(live_driver: Any) -> None:
    deadline = monotonic() + 10.0
    while monotonic() < deadline:
        async with live_driver.session(database="system") as s:
            try:
                result = await s.run(
                    "CALL apoc.trigger.show('neo4j') "
                    "YIELD name, paused "
                    "RETURN name AS name, paused AS paused"
                )
                row = next(
                    (
                        dict(record)
                        async for record in result
                        if record["name"] == "require_group_id"
                    ),
                    None,
                )
            except Exception as exc:
                pytest.skip(f"APOC trigger support unavailable: {exc}")
        if row is not None and row["paused"] is False:
            return
        await asyncio.sleep(0.2)
    pytest.fail("require_group_id trigger did not become active within 10s")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ensure_schema_enforces_group_id_trigger(live_driver: Any) -> None:
    from neo4j.exceptions import Neo4jError

    await ensure_schema(live_driver, default_group_id="project/test-trigger-enforcement")
    await _wait_for_group_id_trigger(live_driver)

    async with live_driver.session() as s:
        await (await s.run("MATCH (n:Bundle {slug: 'trigger-allowed'}) DETACH DELETE n")).consume()
        await (
            await s.run("MATCH (n:Function {cm_id: 'trigger-rejected'}) DETACH DELETE n")
        ).consume()

    try:
        async with live_driver.session() as s:
            await (await s.run("CREATE (:Bundle {slug: 'trigger-allowed'})")).consume()
            with pytest.raises(Neo4jError, match="missing required group_id"):
                await (
                    await s.run("CREATE (:Function {cm_id: 'trigger-rejected'})")
                ).consume()
    finally:
        async with live_driver.session() as s:
            await (await s.run("MATCH (n:Bundle {slug: 'trigger-allowed'}) DETACH DELETE n")).consume()
            await (
                await s.run("MATCH (n:Function {cm_id: 'trigger-rejected'}) DETACH DELETE n")
            ).consume()


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
    missing_trigger_result = AsyncMock()
    missing_trigger_result.single.return_value = None

    async def run_side_effect(query: str, **kwargs: Any) -> Any:
        if query == BOOTSTRAP_PROJECT:
            return None
        if "CALL apoc.trigger.show" in query:
            return missing_trigger_result
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


@pytest.mark.asyncio
async def test_ensure_schema_installs_group_id_trigger_when_missing() -> None:
    from palace_mcp.memory.constraints import GROUP_ID_TRIGGER_QUERY

    driver = AsyncMock()
    default_session = AsyncMock()
    default_session.__aenter__.return_value = default_session
    default_session.__aexit__.return_value = None
    system_session = AsyncMock()
    system_session.__aenter__.return_value = system_session
    system_session.__aexit__.return_value = None
    driver.session = MagicMock(side_effect=[default_session, system_session, default_session])

    empty_result = AsyncMock()
    empty_result.single.return_value = {"unregistered": []}
    missing_trigger_result = AsyncMock()
    missing_trigger_result.single.return_value = None

    async def default_run_side_effect(query: str, **kwargs: Any) -> Any:
        if "RETURN collect(g) AS unregistered" in query:
            return empty_result
        return None

    default_session.run.side_effect = default_run_side_effect
    system_session.run.side_effect = [missing_trigger_result, None]

    await ensure_schema(driver, default_group_id="project/test-trigger")

    install_call = system_session.run.await_args_list[1]
    assert "CALL apoc.trigger.install" in install_call.args[0]
    assert install_call.kwargs["trigger_query"] == GROUP_ID_TRIGGER_QUERY
    assert install_call.kwargs["selector"] == {"phase": "before"}
    driver.session.assert_any_call(database="system")


@pytest.mark.asyncio
async def test_ensure_schema_leaves_matching_group_id_trigger_unchanged() -> None:
    from palace_mcp.memory.constraints import (
        GROUP_ID_TRIGGER_QUERY,
        GROUP_ID_TRIGGER_SELECTOR,
    )

    driver = AsyncMock()
    default_session = AsyncMock()
    default_session.__aenter__.return_value = default_session
    default_session.__aexit__.return_value = None
    system_session = AsyncMock()
    system_session.__aenter__.return_value = system_session
    system_session.__aexit__.return_value = None
    driver.session = MagicMock(side_effect=[default_session, system_session, default_session])

    empty_result = AsyncMock()
    empty_result.single.return_value = {"unregistered": []}
    existing_trigger_result = AsyncMock()
    existing_trigger_result.__aiter__.return_value = [{
        "name": "require_group_id",
        "query": GROUP_ID_TRIGGER_QUERY,
        "selector": GROUP_ID_TRIGGER_SELECTOR,
        "params": {},
        "paused": False,
    }]

    async def default_run_side_effect(query: str, **kwargs: Any) -> Any:
        if "RETURN collect(g) AS unregistered" in query:
            return empty_result
        return None

    default_session.run.side_effect = default_run_side_effect
    system_session.run.return_value = existing_trigger_result

    await ensure_schema(driver, default_group_id="project/test-trigger")

    assert system_session.run.await_count == 1
