"""Wire-contract integration tests for palace.memory.decide (GIM-91 rule).

Tests go through real MCP HTTP+SSE transport via streamablehttp_client.
Requires running palace-mcp container with Neo4j + embedder.

Run:
    COMPOSE_NEO4J_URI=bolt://localhost:7687 COMPOSE_NEO4J_PASSWORD=<pw> \\
    uv run pytest tests/integration/test_palace_memory_decide_wire.py -m integration
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


# ── helpers ───────────────────────────────────────────────────────────────────


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


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def neo4j_uri() -> str:
    if reuse := os.environ.get("COMPOSE_NEO4J_URI"):
        return reuse
    pytest.skip("COMPOSE_NEO4J_URI not set — skipping decide wire-contract tests.")


@pytest.fixture(scope="module")
def neo4j_auth() -> tuple[str, str]:
    return (
        os.environ.get("COMPOSE_NEO4J_USER", "neo4j"),
        os.environ.get("COMPOSE_NEO4J_PASSWORD", "password"),
    )


@pytest.fixture(scope="module")
def mcp_url(neo4j_uri: str, neo4j_auth: tuple[str, str]) -> Iterator[str]:
    import palace_mcp.mcp_server as _ms
    from palace_mcp.config import Settings

    settings = Settings(
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_auth[0],
        neo4j_password=neo4j_auth[1],
    )
    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    _ms.set_driver(drv)
    _ms.set_settings(settings)

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


# ── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_decide_appears_in_tools_list(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    names = [t.name for t in result.tools]
    assert "palace.memory.decide" in names, (
        f"palace.memory.decide missing from tools/list. Got: {names}"
    )


@pytest.mark.integration
async def test_decide_valid_call_returns_ok(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.memory.decide",
                {
                    "title": "Wire-contract test decision",
                    "body": "This decision was recorded by the wire-contract integration test.",
                    "slice_ref": "GIM-95",
                    "decision_maker_claimed": "pythonengineer",
                    "decision_kind": "design",
                    "confidence": 0.9,
                },
            )

    assert not result.isError, f"Expected ok result, got isError. Content: {result.content}"
    assert result.content
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is True
    assert "uuid" in payload
    assert payload["slice_ref"] == "GIM-95"


@pytest.mark.integration
async def test_decide_invalid_decision_maker_returns_envelope(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.memory.decide",
                {
                    "title": "Bad decision",
                    "body": "This should fail validation.",
                    "slice_ref": "GIM-95",
                    "decision_maker_claimed": "hacker",
                },
            )

    assert result.content
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is False
    assert payload["error_code"] == "validation_error"
    assert not result.isError, (
        "Validation errors must return envelope (ok=False), NOT FastMCP isError"
    )
