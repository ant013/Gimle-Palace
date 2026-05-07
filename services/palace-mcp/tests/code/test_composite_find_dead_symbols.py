"""Tests for palace.code.find_dead_symbols composite MCP tool (GIM-228, S0.2).

3 cases per spec:
  - project_not_registered → error response
  - empty graph (no DeadSymbolCandidate nodes) → ok=True, result=[]
  - seeded fixture → ok=True, result has expected items

Happy-path tests require Neo4j; marked @integration so they are skipped when
testcontainers are unavailable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest_plugins = ("tests.integration.hotspot_wire_support",)


# ---------------------------------------------------------------------------
# Error path (mocked driver)
# ---------------------------------------------------------------------------


def _mock_driver_no_project() -> MagicMock:
    """Returns a driver that always finds no :Project node."""
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
async def test_find_dead_symbols_project_not_registered() -> None:
    """find_dead_symbols returns error when project is not registered."""
    from palace_mcp.code.find_dead_symbols import find_dead_symbols

    driver = _mock_driver_no_project()
    result = await find_dead_symbols(driver=driver, project="no-such-project")
    assert result["ok"] is False
    assert result["error_code"] == "project_not_registered"


# ---------------------------------------------------------------------------
# Happy-path integration tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dead_symbols_empty_project(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    from neo4j import GraphDatabase

    slug = f"ds-empty-{uuid.uuid4().hex[:8]}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
    yield slug
    with drv.session() as sess:
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.fixture(scope="module")
def dead_symbols_seeded_project(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    from neo4j import GraphDatabase

    slug = f"ds-seeded-{uuid.uuid4().hex[:8]}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
        sess.run(
            """
            CREATE (c:DeadSymbolCandidate {
                id: 'c1', project: $slug, group_id: $gid,
                module_name: 'CoreModule', language: 'swift',
                display_name: 'UnusedView', kind: 'class',
                candidate_state: 'unused_candidate',
                confidence: 'high',
                evidence_source: 'periphery', evidence_mode: 'static',
                commit_sha: 'abc123', symbol_key: 'CoreModule.UnusedView',
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
            s=slug, g=f"project/{slug}",
        )
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_dead_symbols_empty_graph(
    neo4j_uri: str,
    neo4j_auth: tuple[str, str],
    dead_symbols_empty_project: str,
) -> None:
    """Empty graph returns ok=True with empty result list."""
    from neo4j import AsyncGraphDatabase
    from palace_mcp.code.find_dead_symbols import find_dead_symbols

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        result = await find_dead_symbols(driver=drv, project=dead_symbols_empty_project)
    finally:
        await drv.close()
    assert result["ok"] is True
    assert result["result"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_dead_symbols_seeded(
    neo4j_uri: str,
    neo4j_auth: tuple[str, str],
    dead_symbols_seeded_project: str,
) -> None:
    """Seeded fixture returns expected dead symbol items with required fields."""
    from neo4j import AsyncGraphDatabase
    from palace_mcp.code.find_dead_symbols import find_dead_symbols

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        result = await find_dead_symbols(driver=drv, project=dead_symbols_seeded_project)
    finally:
        await drv.close()
    assert result["ok"] is True
    rows = result["result"]
    assert len(rows) >= 1
    row = rows[0]
    for field in ("display_name", "kind", "module_name", "language", "candidate_state", "confidence"):
        assert field in row, f"Missing field: {field}"
    assert row["display_name"] == "UnusedView"
    assert row["candidate_state"] == "unused_candidate"
