"""MCP wire-contract tests for palace.code.find_owners (GIM-216).

Tests the full HTTP+SSE round-trip through the MCP protocol layer using
streamablehttp_client. These verify the tool's inputSchema and wire contract,
not just the Python function.

Run:
    COMPOSE_NEO4J_URI=bolt://localhost:7687 COMPOSE_NEO4J_PASSWORD=changeme \\
    uv run pytest tests/integration/test_find_owners_mcp_wire.py -m integration
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

pytest_plugins = ("tests.integration.hotspot_wire_support",)


@pytest.fixture(scope="module")
def seeded_owners_project(neo4j_uri: str, neo4j_auth: tuple[str, str]) -> Iterator[str]:
    """Seed a :Project + checkpoint + :File + :OWNED_BY data for find_owners tests."""
    from neo4j import GraphDatabase

    slug = "owners-wire-seeded"
    group_id = f"project/{slug}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
        sess.run(
            """
            MERGE (c:OwnershipCheckpoint {project_id: $g})
              SET c.last_head_sha = 'deadbeef01',
                  c.last_completed_at = datetime(),
                  c.run_id = 'wire-r1',
                  c.updated_at = datetime()
            """,
            g=group_id,
        )
        sess.run(
            "MERGE (f:File {project_id: $g, path: 'src/main.py'})",
            g=group_id,
        )
        sess.run(
            """
            MERGE (a:Author {provider: 'git', identity_key: 'alice@example.com'})
              SET a.email = 'alice@example.com', a.name = 'Alice', a.is_bot = false
            """,
        )
        sess.run(
            """
            MATCH (f:File {project_id: $g, path: 'src/main.py'})
            MATCH (a:Author {provider: 'git', identity_key: 'alice@example.com'})
            MERGE (f)-[r:OWNED_BY {source: 'extractor.code_ownership'}]->(a)
              SET r.weight = 1.0,
                  r.blame_share = 1.0,
                  r.recency_churn_share = 1.0,
                  r.last_touched_at = datetime(),
                  r.lines_attributed = 10,
                  r.commit_count = 3,
                  r.run_id_provenance = 'wire-r1',
                  r.alpha_used = 0.5,
                  r.canonical_via = 'identity'
            """,
            g=group_id,
        )
        sess.run(
            """
            MERGE (st:OwnershipFileState {project_id: $g, path: 'src/main.py'})
              SET st.status = 'processed',
                  st.no_owners_reason = null,
                  st.last_run_id = 'wire-r1',
                  st.updated_at = datetime()
            """,
            g=group_id,
        )
    yield slug
    with drv.session() as sess:
        sess.run("MATCH (n) WHERE n.project_id = $g DETACH DELETE n", g=group_id)
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_owners_appears_in_tools_list(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    tool = next(
        (t for t in result.tools if t.name == "palace.code.find_owners"),
        None,
    )
    assert tool is not None, "palace.code.find_owners missing from tools/list"
    assert tool.inputSchema is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_owners_unregistered_project_returns_error(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_owners",
                {"file_path": "src/main.py", "project": "does-not-exist"},
            )
    resp = json.loads(result.content[0].text)
    assert resp["ok"] is False
    assert resp["error_code"] == "project_not_registered"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_owners_seeded_project_returns_owners(
    mcp_url: str,
    seeded_owners_project: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_owners",
                {
                    "file_path": "src/main.py",
                    "project": seeded_owners_project,
                    "top_n": 5,
                },
            )
    resp = json.loads(result.content[0].text)
    assert resp["ok"] is True
    assert len(resp["owners"]) == 1
    assert resp["owners"][0]["author_email"] == "alice@example.com"
    assert resp["owners"][0]["weight"] == pytest.approx(1.0)
    assert resp["no_owners_reason"] is None
