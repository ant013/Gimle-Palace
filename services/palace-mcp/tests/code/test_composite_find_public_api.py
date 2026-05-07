"""Tests for palace.code.find_public_api composite MCP tool (GIM-228, S0.2)."""

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
async def test_find_public_api_project_not_registered() -> None:
    from palace_mcp.code.find_public_api import find_public_api

    driver = _mock_driver_no_project()
    result = await find_public_api(driver=driver, project="no-such-project")
    assert result["ok"] is False
    assert result["error_code"] == "project_not_registered"


@pytest.fixture(scope="module")
def public_api_empty_project(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    from neo4j import GraphDatabase

    slug = f"pa-empty-{uuid.uuid4().hex[:8]}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
    yield slug
    with drv.session() as sess:
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.fixture(scope="module")
def public_api_seeded_project(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    from neo4j import GraphDatabase

    slug = f"pa-seeded-{uuid.uuid4().hex[:8]}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
        sess.run(
            """
            CREATE (surface:PublicApiSurface {
                id: 'surface1', project: $slug, group_id: $gid,
                module_name: 'CoreKit', language: 'swift',
                commit_sha: 'abc123',
                artifact_path: 'CoreKit.swiftinterface',
                artifact_kind: 'swiftinterface',
                tool_name: 'swiftinterface_parser',
                tool_version: '1.0',
                schema_version: 1
            })
            CREATE (sym:PublicApiSymbol {
                id: 'sym1', project: $slug, group_id: $gid,
                module_name: 'CoreKit', language: 'swift',
                commit_sha: 'abc123',
                fqn: 'CoreKit.WalletService',
                display_name: 'WalletService',
                kind: 'class',
                visibility: 'public',
                signature: 'public class WalletService',
                signature_hash: 'hash1',
                source_artifact_path: 'CoreKit.swiftinterface',
                schema_version: 1
            })
            MERGE (surface)-[:EXPORTS]->(sym)
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
async def test_find_public_api_empty_graph(
    neo4j_uri: str,
    neo4j_auth: tuple[str, str],
    public_api_empty_project: str,
) -> None:
    from neo4j import AsyncGraphDatabase
    from palace_mcp.code.find_public_api import find_public_api

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        result = await find_public_api(driver=drv, project=public_api_empty_project)
    finally:
        await drv.close()
    assert result["ok"] is True
    assert result["result"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_public_api_seeded(
    neo4j_uri: str,
    neo4j_auth: tuple[str, str],
    public_api_seeded_project: str,
) -> None:
    from neo4j import AsyncGraphDatabase
    from palace_mcp.code.find_public_api import find_public_api

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        result = await find_public_api(driver=drv, project=public_api_seeded_project)
    finally:
        await drv.close()
    assert result["ok"] is True
    rows = result["result"]
    assert len(rows) >= 1
    row = rows[0]
    for field in ("fqn", "module_name", "kind", "visibility"):
        assert field in row, f"Missing field: {field}"
    assert row["fqn"] == "CoreKit.WalletService"
    assert row["visibility"] == "public"
