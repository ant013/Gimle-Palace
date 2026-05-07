"""End-to-end MCP wire tests for the 3 new audit composite tools (GIM-228, S0.2).

Verifies tool registration in MCP server tool inventory and correct wire contract.

Run:
    COMPOSE_NEO4J_URI=bolt://localhost:7687 COMPOSE_NEO4J_PASSWORD=changeme \\
    uv run pytest tests/integration/test_audit_composite_e2e.py -m integration
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

pytest_plugins = ("tests.integration.hotspot_wire_support",)

_NEW_TOOLS = [
    "palace.code.find_dead_symbols",
    "palace.code.find_public_api",
    "palace.code.find_cross_module_contracts",
]


@pytest.fixture(scope="module")
def e2e_seeded_project(neo4j_uri: str, neo4j_auth: tuple[str, str]) -> Iterator[str]:
    """Seed one record per new extractor type for e2e coverage."""
    from neo4j import GraphDatabase

    slug = f"audit-e2e-{uuid.uuid4().hex[:8]}"
    gid = f"project/{slug}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
        # DeadSymbolCandidate
        sess.run(
            """
            CREATE (:DeadSymbolCandidate {
                id: 'e2e-ds1', project: $slug, group_id: $gid,
                module_name: 'AppModule', language: 'swift',
                display_name: 'OldHelper', kind: 'class',
                candidate_state: 'unused_candidate', confidence: 'medium',
                evidence_source: 'periphery', evidence_mode: 'static',
                commit_sha: 'c1', symbol_key: 'AppModule.OldHelper', schema_version: 1
            })
            """,
            slug=slug, gid=gid,
        )
        # PublicApiSurface + PublicApiSymbol
        sess.run(
            """
            CREATE (s:PublicApiSurface {
                id: 'e2e-surface1', project: $slug, group_id: $gid,
                module_name: 'CoreKit', language: 'swift', commit_sha: 'c1',
                artifact_path: 'CoreKit.swiftinterface',
                artifact_kind: 'swiftinterface', tool_name: 'p', tool_version: '1',
                schema_version: 1
            })
            CREATE (sym:PublicApiSymbol {
                id: 'e2e-sym1', project: $slug, group_id: $gid,
                module_name: 'CoreKit', language: 'swift', commit_sha: 'c1',
                fqn: 'CoreKit.DataStore', display_name: 'DataStore', kind: 'class',
                visibility: 'public', signature: 'public class DataStore',
                signature_hash: 'h1', source_artifact_path: 'CoreKit.swiftinterface',
                schema_version: 1
            })
            MERGE (s)-[:EXPORTS]->(sym)
            """,
            slug=slug, gid=gid,
        )
        # ModuleContractDelta
        sess.run(
            """
            CREATE (:ModuleContractDelta {
                id: 'e2e-delta1', project: $slug, group_id: $gid,
                consumer_module_name: 'App', producer_module_name: 'CoreKit',
                language: 'swift', from_commit_sha: 'c0', to_commit_sha: 'c1',
                removed_consumed_symbol_count: 1, added_consumed_symbol_count: 0,
                signature_changed_consumed_symbol_count: 0, affected_use_count: 3,
                classification_scope: 'minimal_symbol_delta', schema_version: 1
            })
            """,
            slug=slug, gid=gid,
        )
    yield slug
    with drv.session() as sess:
        sess.run(
            "MATCH (n) WHERE n.project = $s OR n.group_id = $g DETACH DELETE n",
            s=slug, g=gid,
        )
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_new_tools_in_tools_list(mcp_url: str) -> None:
    """All 3 new composite tools appear in the MCP server tool inventory."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
    names = {t.name for t in result.tools}
    for tool_name in _NEW_TOOLS:
        assert tool_name in names, f"{tool_name} missing from tools/list"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_dead_symbols_wire(mcp_url: str, e2e_seeded_project: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_dead_symbols", {"project": e2e_seeded_project}
            )
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is True
    assert len(payload["result"]) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_public_api_wire(mcp_url: str, e2e_seeded_project: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_public_api", {"project": e2e_seeded_project}
            )
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is True
    assert len(payload["result"]) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_cross_module_contracts_wire(
    mcp_url: str, e2e_seeded_project: str
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_cross_module_contracts",
                {"project": e2e_seeded_project},
            )
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is True
    assert len(payload["result"]) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_dead_symbols_unregistered_project(mcp_url: str) -> None:
    """Unregistered project returns canonical error_code."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_dead_symbols", {"project": "no-such-project"}
            )
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is False
    assert payload["error_code"] == "project_not_registered"
