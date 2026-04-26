"""MCP wire-contract integration tests for palace.memory.prime — GIM-96.

Verifies that the MCP wire transport delivers a valid response for
palace.memory.prime — catching any FastMCP signature-binding issues
that unit tests cannot detect.

Run:
    COMPOSE_NEO4J_URI=bolt://localhost:7687 COMPOSE_NEO4J_PASSWORD=test \\
    uv run pytest tests/integration/test_prime_wire_contract.py -m integration
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
from collections.abc import Iterator

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from neo4j import AsyncGraphDatabase


# ── helpers ────────────────────────────────────────────────────────────────────


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _TestServer:
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


# ── fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def neo4j_uri() -> str:
    if reuse := os.environ.get("COMPOSE_NEO4J_URI"):
        return reuse
    pytest.skip(
        "COMPOSE_NEO4J_URI not set — skipping prime wire-contract tests. "
        "Set COMPOSE_NEO4J_URI=bolt://localhost:7687 to run these tests."
    )


@pytest.fixture(scope="module")
def neo4j_auth() -> tuple[str, str]:
    return (
        os.environ.get("COMPOSE_NEO4J_USER", "neo4j"),
        os.environ.get("COMPOSE_NEO4J_PASSWORD", "password"),
    )


@pytest.fixture(scope="module")
def mcp_url(neo4j_uri: str, neo4j_auth: tuple[str, str]) -> Iterator[str]:
    import palace_mcp.mcp_server as _ms

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    _ms.set_driver(drv)

    app = _ms.build_mcp_asgi_app()
    port = _free_port()
    srv = _TestServer(app, port)
    srv.start()

    yield f"http://127.0.0.1:{port}/"

    srv.stop()
    _cleanup = asyncio.new_event_loop()
    try:
        _cleanup.run_until_complete(drv.close())
    finally:
        _cleanup.close()
    _ms._driver = None  # type: ignore[attr-defined]


# ── tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_prime_appears_in_tools_list(mcp_url: str) -> None:
    """tools/list must include palace.memory.prime."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    names = [t.name for t in result.tools]
    assert "palace.memory.prime" in names, (
        f"palace.memory.prime missing from tools/list. Got: {names}"
    )


@pytest.mark.integration
async def test_prime_input_schema_has_role_param(mcp_url: str) -> None:
    """inputSchema for palace.memory.prime must declare a 'role' parameter."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    prime_tool = next(
        (t for t in result.tools if t.name == "palace.memory.prime"), None
    )
    assert prime_tool is not None
    schema = prime_tool.inputSchema
    assert schema is not None

    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    assert "role" in props, (
        f"'role' not in inputSchema.properties. Got: {list(props.keys())}"
    )


@pytest.mark.integration
async def test_prime_invalid_role_returns_error_envelope(mcp_url: str) -> None:
    """tools/call with an invalid role must return ok=false error envelope."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.memory.prime",
                {"role": "nonexistent_role_xyz"},
            )

    assert result.content, "must return non-empty content"
    text = " ".join(c.text for c in result.content if hasattr(c, "text"))
    payload = json.loads(text)
    assert payload.get("ok") is False
    assert payload.get("error_code") == "invalid_role"


@pytest.mark.integration
async def test_prime_valid_role_returns_ok_envelope(mcp_url: str) -> None:
    """tools/call with a valid role must return ok=true with content field.

    The content may be minimal (no decisions in test DB) but the wire
    contract must be satisfied.
    """
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.memory.prime",
                {"role": "pythonengineer", "slice_id": "GIM-TEST"},
            )

    assert result.content, "must return non-empty content"
    # Must not be an MCP-level error
    text = " ".join(c.text for c in result.content if hasattr(c, "text"))
    payload = json.loads(text)
    assert payload.get("ok") is True, f"Expected ok=true, got: {payload}"
    assert "content" in payload
    assert "role" in payload
    assert payload["role"] == "pythonengineer"
    assert "tokens_estimated" in payload
    assert isinstance(payload["truncated"], bool)
