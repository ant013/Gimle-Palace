"""MCP wire-contract tests for palace.code.list_functions (GIM-195).

Run:
    COMPOSE_NEO4J_URI=bolt://localhost:7687 COMPOSE_NEO4J_PASSWORD=changeme \\
    uv run pytest tests/integration/test_list_functions_tool.py -m integration
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

pytest_plugins = ("tests.integration.hotspot_wire_support",)


@pytest.fixture(scope="module")
def seeded_functions_project(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    """Seed :Project + :File + :Function nodes for list_functions tests; delete after module."""
    from neo4j import GraphDatabase

    slug = "lf-wire-seeded"
    group_id = f"project/{slug}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
        sess.run(
            "MERGE (f:File {project_id: $p, path: 'src/python_complex.py'}) "
            "SET f.hotspot_score = 2.5, f.ccn_total = 8, f.churn_count = 5, "
            "f.complexity_status = 'fresh', f.complexity_window_days = 90, "
            "f.last_complexity_run_at = datetime('2026-05-01T00:00:00Z')",
            p=group_id,
        )
        # classify function: ccn=6
        sess.run(
            "MATCH (f:File {project_id: $p, path: 'src/python_complex.py'}) "
            "MERGE (fn:Function {project_id: $p, path: 'src/python_complex.py', name: 'classify', start_line: 1}) "
            "SET fn.end_line = 11, fn.ccn = 6, fn.parameter_count = 1, fn.nloc = 11, fn.language = 'python' "
            "MERGE (f)-[:CONTAINS]->(fn)",
            p=group_id,
        )
        # helper function: ccn=2
        sess.run(
            "MATCH (f:File {project_id: $p, path: 'src/python_complex.py'}) "
            "MERGE (fn:Function {project_id: $p, path: 'src/python_complex.py', name: 'helper', start_line: 13}) "
            "SET fn.end_line = 17, fn.ccn = 2, fn.parameter_count = 0, fn.nloc = 5, fn.language = 'python' "
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
async def test_list_functions_unregistered_project_returns_error(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.list_functions",
                {"project": "doesnotexist", "path": "src/x.py"},
            )
    resp = json.loads(result.content[0].text)
    assert resp["ok"] is False
    assert resp["error_code"] == "project_not_registered"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_appears_in_tools_list(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    tool = next(
        (item for item in result.tools if item.name == "palace.code.list_functions"),
        None,
    )
    assert tool is not None, "palace.code.list_functions missing from tools/list"
    assert tool.inputSchema is not None, (
        "palace.code.list_functions inputSchema must not be None"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_missing_file_returns_empty(
    mcp_url: str,
    seeded_functions_project: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.list_functions",
                {"project": seeded_functions_project, "path": "src/does_not_exist.py"},
            )
    resp = json.loads(result.content[0].text)
    assert resp.get("ok") is True
    assert resp["result"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_min_ccn_filter_excludes_low(
    mcp_url: str,
    seeded_functions_project: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.list_functions",
                {
                    "project": seeded_functions_project,
                    "path": "src/python_complex.py",
                    "min_ccn": 100,
                },
            )
    resp = json.loads(result.content[0].text)
    assert resp.get("ok") is True
    assert resp["result"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_returns_sorted_by_ccn_desc(
    mcp_url: str,
    seeded_functions_project: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.list_functions",
                {
                    "project": seeded_functions_project,
                    "path": "src/python_complex.py",
                    "min_ccn": 0,
                },
            )
    resp = json.loads(result.content[0].text)
    assert resp.get("ok") is True
    rows = resp["result"]
    assert len(rows) >= 1
    ccns = [r["ccn"] for r in rows]
    assert ccns == sorted(ccns, reverse=True)
    for r in rows:
        for k in (
            "name",
            "start_line",
            "end_line",
            "ccn",
            "parameter_count",
            "nloc",
            "language",
        ):
            assert k in r
