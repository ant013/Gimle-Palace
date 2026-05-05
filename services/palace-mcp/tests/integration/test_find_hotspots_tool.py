"""MCP wire-contract tests for palace.code.find_hotspots (GIM-195).

Run:
    COMPOSE_NEO4J_URI=bolt://localhost:7687 COMPOSE_NEO4J_PASSWORD=changeme \\
    uv run pytest tests/integration/test_find_hotspots_tool.py -m integration
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

pytest_plugins = ("tests.integration.hotspot_wire_support",)


@pytest.fixture(scope="module")
def registered_project_empty(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    """Create a bare :Project node with no :File nodes; delete after module."""
    from neo4j import GraphDatabase

    slug = "hotspot-wire-empty"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
    yield slug
    with drv.session() as sess:
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.fixture(scope="module")
def seeded_hotspot_project(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    """Seed :Project + :File nodes with hotspot data for query tests."""
    from neo4j import GraphDatabase

    slug = "hotspot-wire-seeded"
    group_id = f"project/{slug}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
        sess.run(
            "MERGE (f:File {project_id: $p, path: 'src/complex.py'}) "
            "SET f.hotspot_score = 2.5, f.ccn_total = 8, f.churn_count = 5, "
            "f.complexity_status = 'fresh', f.complexity_window_days = 90, "
            "f.last_complexity_run_at = datetime('2026-05-01T00:00:00Z')",
            p=group_id,
        )
        sess.run(
            "MERGE (f:File {project_id: $p, path: 'src/simple.py'}) "
            "SET f.hotspot_score = 0.8, f.ccn_total = 2, f.churn_count = 2, "
            "f.complexity_status = 'fresh', f.complexity_window_days = 90, "
            "f.last_complexity_run_at = datetime('2026-05-01T00:00:00Z')",
            p=group_id,
        )
        sess.run(
            "MATCH (f:File {project_id: $p, path: 'src/complex.py'}) "
            "MERGE (fn:Function {project_id: $p, path: 'src/complex.py', name: 'classify', start_line: 1}) "
            "SET fn.end_line = 13, fn.ccn = 6, fn.parameter_count = 1, fn.nloc = 13, fn.language = 'python' "
            "MERGE (f)-[:CONTAINS]->(fn)",
            p=group_id,
        )
    yield slug
    with drv.session() as sess:
        sess.run(
            "MATCH (n) WHERE n.project_id = $g DETACH DELETE n",
            g=group_id,
        )
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_hotspots_unregistered_project_returns_error(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_hotspots",
                {"project": "doesnotexist"},
            )
    resp = json.loads(result.content[0].text)
    assert resp["ok"] is False
    assert resp["error_code"] == "project_not_registered"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_hotspots_appears_in_tools_list(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    tool = next(
        (item for item in result.tools if item.name == "palace.code.find_hotspots"),
        None,
    )
    assert tool is not None, "palace.code.find_hotspots missing from tools/list"
    assert tool.inputSchema is not None, (
        "palace.code.find_hotspots inputSchema must not be None"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_hotspots_registered_no_files_returns_empty(
    mcp_url: str,
    registered_project_empty: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_hotspots",
                {"project": registered_project_empty},
            )
    resp = json.loads(result.content[0].text)
    assert resp.get("ok") is True
    assert resp["result"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_hotspots_with_data_returns_sorted_descending(
    mcp_url: str,
    seeded_hotspot_project: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_hotspots",
                {"project": seeded_hotspot_project, "top_n": 5},
            )
    resp = json.loads(result.content[0].text)
    assert resp.get("ok") is True
    rows = resp["result"]
    assert len(rows) > 0
    scores = [r["hotspot_score"] for r in rows]
    assert scores == sorted(scores, reverse=True)
    for r in rows:
        for k in (
            "path",
            "ccn_total",
            "churn_count",
            "hotspot_score",
            "computed_at",
            "window_days",
        ):
            assert k in r


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_hotspots_min_score_filter(
    mcp_url: str,
    seeded_hotspot_project: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_hotspots",
                {"project": seeded_hotspot_project, "min_score": 1.5},
            )
    resp = json.loads(result.content[0].text)
    assert resp.get("ok") is True
    for r in resp["result"]:
        assert r["hotspot_score"] >= 1.5
