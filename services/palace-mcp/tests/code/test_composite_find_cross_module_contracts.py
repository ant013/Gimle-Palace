"""Tests for palace.code.find_cross_module_contracts composite MCP tool (GIM-228, S0.2)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest_plugins = ("tests.integration.hotspot_wire_support",)


def _mock_driver_no_project() -> MagicMock:
    single_result = AsyncMock()
    single_result.single = AsyncMock(return_value=None)
    session = AsyncMock()
    session.run = AsyncMock(return_value=single_result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


@pytest.mark.asyncio
async def test_find_cross_module_contracts_project_not_registered() -> None:
    from palace_mcp.code.find_cross_module_contracts import find_cross_module_contracts

    driver = _mock_driver_no_project()
    result = await find_cross_module_contracts(driver=driver, project="no-such-project")
    assert result["ok"] is False
    assert result["error_code"] == "project_not_registered"


@pytest.fixture(scope="module")
def contracts_empty_project(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    from neo4j import GraphDatabase

    slug = f"cm-empty-{uuid.uuid4().hex[:8]}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
    yield slug
    with drv.session() as sess:
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.fixture(scope="module")
def contracts_seeded_project(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    from neo4j import GraphDatabase

    slug = f"cm-seeded-{uuid.uuid4().hex[:8]}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
        sess.run(
            """
            CREATE (d:ModuleContractDelta {
                id: 'delta1', project: $slug, group_id: $gid,
                consumer_module_name: 'AppModule',
                producer_module_name: 'CoreKit',
                language: 'swift',
                from_commit_sha: 'aaa111',
                to_commit_sha: 'bbb222',
                removed_consumed_symbol_count: 2,
                added_consumed_symbol_count: 1,
                signature_changed_consumed_symbol_count: 0,
                affected_use_count: 5,
                classification_scope: 'minimal_symbol_delta',
                schema_version: 1
            })
            """,
            slug=slug,
            gid=f"project/{slug}",
        )
    yield slug
    with drv.session() as sess:
        sess.run(
            "MATCH (n) WHERE n.project = $s OR n.group_id = $g DETACH DELETE n",
            s=slug,
            g=f"project/{slug}",
        )
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_cross_module_contracts_empty_graph(
    neo4j_uri: str,
    neo4j_auth: tuple[str, str],
    contracts_empty_project: str,
) -> None:
    from neo4j import AsyncGraphDatabase
    from palace_mcp.code.find_cross_module_contracts import find_cross_module_contracts

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        result = await find_cross_module_contracts(
            driver=drv, project=contracts_empty_project
        )
    finally:
        await drv.close()
    assert result["ok"] is True
    assert result["result"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_cross_module_contracts_seeded(
    neo4j_uri: str,
    neo4j_auth: tuple[str, str],
    contracts_seeded_project: str,
) -> None:
    from neo4j import AsyncGraphDatabase
    from palace_mcp.code.find_cross_module_contracts import find_cross_module_contracts

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        result = await find_cross_module_contracts(
            driver=drv, project=contracts_seeded_project
        )
    finally:
        await drv.close()
    assert result["ok"] is True
    rows = result["result"]
    assert len(rows) >= 1
    row = rows[0]
    for field in (
        "consumer_module",
        "producer_module",
        "language",
        "removed_count",
        "added_count",
    ):
        assert field in row, f"Missing field: {field}"
    assert row["consumer_module"] == "AppModule"
    assert row["producer_module"] == "CoreKit"
    assert row["removed_count"] == 2
