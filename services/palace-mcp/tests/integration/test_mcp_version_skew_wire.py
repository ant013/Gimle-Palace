"""MCP wire-contract tests for palace.code.find_version_skew (GIM-218).

Verifies that the tool is correctly wired through the streamable-HTTP transport:
  - palace.code.find_version_skew appears in tools/list with a non-empty inputSchema
  - error path: explicit error_code assertion (not tautological isError check)
  - success path: ok=True with well-formed response envelope

Each test sends a real HTTP+SSE round-trip via streamablehttp_client, which
catches broken inputSchema, schema-binding mismatches, and transport-layer
regressions that function-level tests cannot catch (GIM-89 lesson).

Run:
    COMPOSE_NEO4J_URI=bolt://localhost:7687 COMPOSE_NEO4J_PASSWORD=test \\
    uv run pytest tests/integration/test_mcp_version_skew_wire.py -m integration
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


# ── tool-list test ─────────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_find_version_skew_in_tools_list(mcp_url: str) -> None:
    """palace.code.find_version_skew must appear in tools/list with a non-empty inputSchema."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    names = [t.name for t in result.tools]
    assert "palace.code.find_version_skew" in names, (
        f"palace.code.find_version_skew missing from tools/list. Got: {names}"
    )
    tool = next(t for t in result.tools if t.name == "palace.code.find_version_skew")
    assert tool.inputSchema is not None, (
        "palace.code.find_version_skew has None inputSchema — wire binding broken"
    )


# ── error-path wire test ───────────────────────────────────────────────────────


@pytest.mark.integration
async def test_find_version_skew_mutually_exclusive_args_error_code(
    mcp_url: str,
) -> None:
    """Passing both project= and bundle= returns error_code=mutually_exclusive_args.

    Validates schema binding (both params reach the handler) and that the error
    envelope is returned as a JSON payload, not a transport crash.
    """
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_version_skew",
                {"project": "any-proj", "bundle": "any-bundle"},
            )

    assert result.content, "tools/call must return non-empty content"
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is False
    assert payload["error_code"] == "mutually_exclusive_args"


# ── success-path wire test ─────────────────────────────────────────────────────


@pytest.mark.integration
async def test_find_version_skew_success_returns_ok_true(
    mcp_url: str, neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> None:
    """project= with a seeded :Project + :DEPENDS_ON returns ok=True.

    Validates the full round-trip: schema binding → find_version_skew() →
    JSON envelope → streamable-HTTP response.
    """
    # Seed a minimal graph: one project with one dependency.
    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        async with drv.session() as session:
            await session.run(
                "MATCH (n) WHERE n:Project OR n:ExternalDependency DETACH DELETE n"
            )
            await session.run("""
                MERGE (p:Project {slug: 'wire-test-proj'})
                MERGE (d:ExternalDependency {purl: 'pkg:pypi/requests@2.31.0'})
                  SET d.ecosystem = 'pypi', d.resolved_version = '2.31.0'
                MERGE (p)-[:DEPENDS_ON {scope: 'main', declared_in: 'requirements.txt',
                                        declared_version_constraint: '>=2.31'}]->(d)
            """)
    finally:
        await drv.close()

    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.find_version_skew",
                {"project": "wire-test-proj", "top_n": 10},
            )

    assert result.content, "tools/call must return non-empty content"
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is True, f"Expected ok=True, got: {payload}"
    assert payload["mode"] == "project"
    assert payload["target_slug"] == "wire-test-proj"
    assert "skew_groups" in payload
    assert "warnings" in payload
