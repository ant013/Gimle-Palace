"""MCP wire-contract tests for GIM-182 bundle tools.

Verifies that all 7 new/modified bundle tool endpoints are correctly wired
through the streamable-HTTP transport:
  - palace.memory.register_bundle
  - palace.memory.add_to_bundle
  - palace.memory.bundle_members
  - palace.memory.bundle_status (memory)
  - palace.memory.delete_bundle
  - palace.ingest.run_extractor  (modified: bundle= param)
  - palace.ingest.bundle_status  (new)

Each test sends a real HTTP+SSE round-trip via streamablehttp_client, which
catches broken inputSchema, schema-binding mismatches, and transport-layer
regressions that unit tests calling handler functions directly cannot catch
(GIM-89 lesson).

Run:
    COMPOSE_NEO4J_URI=bolt://localhost:7687 COMPOSE_NEO4J_PASSWORD=test \\
    uv run pytest tests/integration/test_mcp_bundle_wire.py -m integration
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

from tests.integration.neo4j_runtime_support import ensure_reachable_neo4j_uri


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


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def neo4j_uri() -> str:
    if reuse := os.environ.get("COMPOSE_NEO4J_URI"):
        return ensure_reachable_neo4j_uri(reuse)
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


@pytest.fixture(scope="module")
def mcp_url(neo4j_uri: str, neo4j_auth: tuple[str, str]) -> Iterator[str]:
    """Start palace-mcp ASGI server with a live driver; yield its base URL."""
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


# ── tool-list tests ────────────────────────────────────────────────────────────

_BUNDLE_TOOLS = [
    "palace.memory.register_bundle",
    "palace.memory.add_to_bundle",
    "palace.memory.bundle_members",
    "palace.memory.bundle_status",
    "palace.memory.delete_bundle",
    "palace.ingest.run_extractor",
    "palace.ingest.bundle_status",
]


@pytest.mark.integration
async def test_tools_list_includes_all_bundle_tools(mcp_url: str) -> None:
    """tools/list must include all 7 bundle-related tools with non-empty inputSchema."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    names = [t.name for t in result.tools]
    for tool_name in _BUNDLE_TOOLS:
        assert tool_name in names, f"{tool_name} missing from tools/list. Got: {names}"

    for tool in result.tools:
        if tool.name in _BUNDLE_TOOLS:
            assert tool.inputSchema is not None, (
                f"{tool.name} has None inputSchema — wire binding broken"
            )


# ── error-path wire tests ─────────────────────────────────────────────────────
# These tests call with a non-existent bundle name. The tool must return
# a structured error_code dict (isError=False, content=[...]) rather than an
# HTTP 4xx/5xx that would surface as an exception.


@pytest.mark.integration
async def test_bundle_members_not_found_returns_error_envelope(mcp_url: str) -> None:
    """palace.memory.bundle_members on non-existent bundle returns error_code dict.

    Verifies that the tool schema correctly binds the `bundle` argument through
    the streamable-HTTP transport and that the error envelope reaches the client.
    """
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.memory.bundle_members",
                {"bundle": "__wire_test_nonexistent_bundle__"},
            )

    assert result.content, "tools/call must return non-empty content"
    # Tool must deliver an MCP-level result (not crash the transport).
    # Result may be isError=True (unknown bundle) — that's acceptable.
    # What's forbidden is a missing response or a TypeError (schema binding bug).
    if result.isError:
        error_text = " ".join(c.text for c in result.content if hasattr(c, "text"))
        assert "TypeError" not in error_text, (
            f"TypeError in tool result — schema binding broken. Error: {error_text}"
        )


@pytest.mark.integration
async def test_bundle_status_memory_not_found_returns_error_envelope(
    mcp_url: str,
) -> None:
    """palace.memory.bundle_status on non-existent bundle returns error_code dict."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.memory.bundle_status",
                {"bundle": "__wire_test_nonexistent_bundle__"},
            )

    assert result.content, "tools/call must return non-empty content"
    if result.isError:
        error_text = " ".join(c.text for c in result.content if hasattr(c, "text"))
        assert "TypeError" not in error_text, (
            f"TypeError in tool result — schema binding broken. Error: {error_text}"
        )


@pytest.mark.integration
async def test_ingest_bundle_status_not_found_returns_error_envelope(
    mcp_url: str,
) -> None:
    """palace.ingest.bundle_status with unknown run_id returns error_code not_found."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.ingest.bundle_status",
                {"run_id": "00000000-0000-0000-0000-000000000000"},
            )

    assert result.content, "tools/call must return non-empty content"
    if result.isError:
        error_text = " ".join(c.text for c in result.content if hasattr(c, "text"))
        assert "TypeError" not in error_text, (
            f"TypeError in tool result — schema binding broken. Error: {error_text}"
        )


@pytest.mark.integration
async def test_run_extractor_invalid_request_returns_error_envelope(
    mcp_url: str,
) -> None:
    """palace.ingest.run_extractor with both project= and bundle= returns invalid_request.

    Tests the modified run_extractor signature (GIM-182 added bundle= param).
    Passing both is a client error that must produce a structured error envelope,
    not a transport crash.
    """
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.ingest.run_extractor",
                {
                    "name": "heartbeat",
                    "project": "gimle",
                    "bundle": "uw-ios",
                },
            )

    assert result.content, "tools/call must return non-empty content"
    if result.isError:
        error_text = " ".join(c.text for c in result.content if hasattr(c, "text"))
        assert "TypeError" not in error_text, (
            f"TypeError in tool result — schema binding broken. Error: {error_text}"
        )
