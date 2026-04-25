"""Canonical MCP wire-contract integration tests — GIM-91.

Demonstrates the streamablehttp_client pattern for testing MCP tools through
the actual HTTP+SSE transport layer.  Copy-paste and adapt this file when
adding integration tests for new tools.

Run:
    COMPOSE_NEO4J_URI=bolt://localhost:7687 COMPOSE_NEO4J_PASSWORD=test \\
    uv run pytest tests/integration/test_mcp_wire_pattern.py -m integration

Why these tests matter (GIM-89 lesson):
    Mocking at the FastMCP signature-binding level (e.g. calling _forward()
    programmatically) does NOT catch broken inputSchema.  Only a real HTTP+SSE
    round-trip via streamablehttp_client can prove the wire contract is correct.
"""

from __future__ import annotations

import asyncio
import os
import socket
import threading
import time
from collections.abc import Iterator

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from neo4j import AsyncGraphDatabase


# ── helpers ───────────────────────────────────────────────────────────────────


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _TestServer:
    """Runs an ASGI app in a background daemon thread via uvicorn."""

    def __init__(self, app: object, port: int) -> None:
        import uvicorn

        self.port = port
        config = uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="error", access_log=False
        )
        self._server = uvicorn.Server(config)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.monotonic() + 5.0
        while not self._server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("Test MCP server did not start within 5 s")
            time.sleep(0.05)

    def stop(self) -> None:
        self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5)


# ── Neo4j fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def neo4j_uri() -> str:
    if reuse := os.environ.get("COMPOSE_NEO4J_URI"):
        return reuse
    pytest.skip(
        "COMPOSE_NEO4J_URI not set — skipping MCP wire-contract tests. "
        "Set COMPOSE_NEO4J_URI=bolt://localhost:7687 to run these tests."
    )


@pytest.fixture(scope="module")
def neo4j_auth() -> tuple[str, str]:
    return (
        os.environ.get("COMPOSE_NEO4J_USER", "neo4j"),
        os.environ.get("COMPOSE_NEO4J_PASSWORD", "password"),
    )


# ── MCP server fixture ─────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def mcp_url(neo4j_uri: str, neo4j_auth: tuple[str, str]) -> Iterator[str]:
    """Start palace-mcp ASGI server with a live driver; yield its base URL.

    The driver is created synchronously (no event loop binding at creation time
    for the neo4j async driver) and connections are established lazily inside
    uvicorn's event loop when tool handlers execute.
    """
    import palace_mcp.mcp_server as _ms

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    _ms.set_driver(drv)

    app = _ms.build_mcp_asgi_app()
    port = _free_port()
    srv = _TestServer(app, port)
    srv.start()

    yield f"http://127.0.0.1:{port}/"

    srv.stop()
    # Close driver on a fresh loop to avoid interfering with test event loop.
    _cleanup = asyncio.new_event_loop()
    try:
        _cleanup.run_until_complete(drv.close())
    finally:
        _cleanup.close()
    _ms._driver = None  # type: ignore[attr-defined]


# ── Task 3: reference tests for palace.memory.health ──────────────────────────


@pytest.mark.integration
async def test_tools_list_includes_memory_health(mcp_url: str) -> None:
    """tools/list returns palace.memory.health with a non-empty inputSchema."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    names = [t.name for t in result.tools]
    assert "palace.memory.health" in names, (
        f"palace.memory.health missing from tools/list. Got: {names}"
    )
    health_tool = next(t for t in result.tools if t.name == "palace.memory.health")
    assert health_tool.inputSchema is not None, "inputSchema must not be None"


@pytest.mark.integration
async def test_memory_health_call_flat_args_returns_result(mcp_url: str) -> None:
    """tools/call palace.memory.health with flat {} returns a non-empty CallToolResult.

    The result may be isError=True if Neo4j data is empty; the important thing
    is that the wire transport delivered a result (not an HTTP-level error).
    """
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("palace.memory.health", {})

    assert result.content, "tools/call must return non-empty content"


@pytest.mark.integration
async def test_call_unknown_tool_returns_mcp_error(mcp_url: str) -> None:
    """tools/call for a nonexistent tool returns isError=True at the MCP level."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("palace.nonexistent_tool_xyz", {})

    assert result.isError is True, (
        "Calling an unknown tool must return isError=True on the wire"
    )


# ── Task 4: GIM-89 regression — palace.code.search_graph flat schema ──────────


@pytest.mark.integration
async def test_search_graph_input_schema_is_flat(mcp_url: str) -> None:
    """palace.code.search_graph inputSchema must be open/flat (no _OpenArgs wrapper).

    Pre-GIM-89: schema was {'properties': {'arguments': {...}}, ...} causing
    flat-arg callers to receive a TypeError.
    Post-GIM-89: schema is {'type': 'object', 'additionalProperties': True}.
    """
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    search_tool = next(
        (t for t in result.tools if t.name == "palace.code.search_graph"), None
    )
    assert search_tool is not None, "palace.code.search_graph missing from tools/list"

    schema = search_tool.inputSchema
    assert schema is not None

    # Must NOT have a nested 'arguments' property (pre-GIM-89 bug).
    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    assert "arguments" not in props, (
        f"inputSchema must not have a nested 'arguments' property (GIM-89 regression). "
        f"Got schema: {schema}"
    )
    # Must be an open schema accepting arbitrary flat keys.
    assert schema.get("additionalProperties") is True, (
        f"inputSchema must have additionalProperties=true for passthrough tools. "
        f"Got schema: {schema}"
    )


@pytest.mark.integration
async def test_search_graph_call_flat_args_no_type_error(mcp_url: str) -> None:
    """tools/call palace.code.search_graph with flat args must not raise TypeError.

    Pre-GIM-89: nested _OpenArgs schema caused TypeError on flat-arg forwarding.
    Post-GIM-89: flat args are forwarded correctly; result may be an error
    (CM not running) but must never contain 'TypeError'.
    """
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.search_graph",
                {"query": "test", "project": "gimle"},
            )

    assert result.content, "tools/call must return non-empty content"
    if result.isError:
        error_text = " ".join(c.text for c in result.content if hasattr(c, "text"))
        assert "TypeError" not in error_text, (
            f"Got TypeError in tool result — GIM-89 regression detected. "
            f"Error: {error_text}"
        )
