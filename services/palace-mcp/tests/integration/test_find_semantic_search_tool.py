"""Wire tests for palace.code.semantic_search."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Iterator

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from palace_mcp.embeddings import (
    EmbeddingBackendDispatcher,
    set_embedding_dispatcher_factory,
)
from palace_mcp.extractors.foundation.schema import ensure_custom_schema

pytest_plugins = ("tests.integration.hotspot_wire_support",)


class _FakeBackend:
    def embed_text(self, text: str) -> list[float]:
        return [0.01] * 1536

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.01] * 1536 for _ in texts]


def _ensure_vector_schema_ready(
    neo4j_uri: str, neo4j_auth: tuple[str, str], *, timeout_seconds: float = 10.0
) -> None:
    from neo4j import AsyncGraphDatabase

    async def _bootstrap() -> None:
        driver = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
        try:
            await ensure_custom_schema(driver)
            deadline = time.monotonic() + timeout_seconds
            while True:
                async with driver.session() as session:
                    result = await session.run(
                        """
                        SHOW INDEXES YIELD name, type, state
                        WHERE name = 'symbol_embedding_idx'
                        RETURN type, state
                        """
                    )
                    row = await result.single()
                if (
                    row is not None
                    and row["type"] == "VECTOR"
                    and row["state"] == "ONLINE"
                ):
                    return
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "symbol_embedding_idx did not reach ONLINE state"
                    )
                await asyncio.sleep(0.1)
        finally:
            await driver.close()

    asyncio.run(_bootstrap())


@pytest.fixture(autouse=True)
def _reset_embedding_factory() -> None:
    set_embedding_dispatcher_factory(None)
    yield
    set_embedding_dispatcher_factory(None)


@pytest.fixture(scope="module")
def semantic_seeded_project(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    from neo4j import GraphDatabase

    _ensure_vector_schema_ready(neo4j_uri, neo4j_auth)

    slug = f"semantic-{uuid.uuid4().hex[:8]}"
    gid = f"project/{slug}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $slug})", slug=slug)
        sess.run(
            """
            CREATE (:Symbol {
                qualified_name: 'Wallet.verifySignature',
                group_id: $gid,
                kind: 'function',
                file_path: 'Sources/Wallet.swift',
                module_name: 'WalletCore',
                source_scope: 'project',
                embedding_input_hash: 'seed-hash',
                commit_sha: 'seed-commit',
                embedding: $embedding
            })
            """,
            gid=gid,
            embedding=[0.02] * 1536,
        )
    yield slug
    with drv.session() as sess:
        sess.run(
            "MATCH (n) WHERE n.group_id = $gid DETACH DELETE n",
            gid=gid,
        )
        sess.run("MATCH (p:Project {slug: $slug}) DETACH DELETE p", slug=slug)
    drv.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_semantic_search_in_tools_list(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
    assert "palace.code.semantic_search" in {tool.name for tool in result.tools}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_semantic_search_invalid_limit_returns_error_code(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.semantic_search",
                {
                    "query": "signature verification",
                    "limit": 0,
                },
            )

    payload = json.loads(result.content[0].text)
    assert payload["ok"] is False
    assert payload["error_code"] == "invalid_limit"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_semantic_search_invalid_context_limit_returns_error_code(
    mcp_url: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.semantic_search",
                {
                    "query": "signature verification",
                    "context_limit": 11,
                },
            )

    payload = json.loads(result.content[0].text)
    assert payload["ok"] is False
    assert payload["error_code"] == "invalid_context_limit"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_semantic_search_call_tool_seeded(
    mcp_url: str, semantic_seeded_project: str
) -> None:
    set_embedding_dispatcher_factory(
        lambda: EmbeddingBackendDispatcher(
            {"qodo": _FakeBackend()},
            default_backend="qodo",
        )
    )

    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.semantic_search",
                {
                    "query": "signature verification",
                    "project": semantic_seeded_project,
                    "include_context": False,
                    "limit": 1,
                },
            )

    payload = json.loads(result.content[0].text)
    assert payload["ok"] is True
    assert payload["returned_count"] == 1
    assert payload["backend"] == "qodo"
    assert payload["result"][0]["project"] == semantic_seeded_project
    assert payload["result"][0]["qualified_name"] == "Wallet.verifySignature"
