"""Wire-contract integration tests for palace.code.manage_adr (GIM-274).

Tests go through real MCP HTTP transport via streamablehttp_client.
Requires running palace-mcp with Neo4j (COMPOSE_NEO4J_URI set).

Run:
    COMPOSE_NEO4J_URI=bolt://localhost:7687 COMPOSE_NEO4J_PASSWORD=<pw> \\
    uv run pytest tests/integration/test_manage_adr_wire.py -m integration
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
import uuid
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
    def __init__(self, app: object, port: int) -> None:
        import uvicorn

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
    pytest.skip("COMPOSE_NEO4J_URI not set — skipping manage_adr wire tests.")


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

    # Ensure base_dir exists (set via conftest.pytest_configure → PALACE_ADR_BASE_DIR).
    from pathlib import Path

    adr_base = Path(os.environ.get("PALACE_ADR_BASE_DIR", "docs/postulates"))
    adr_base.mkdir(parents=True, exist_ok=True)

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


@pytest.fixture(scope="module")
def decision_id(neo4j_uri: str, neo4j_auth: tuple[str, str]) -> str:
    """Pre-create a :Decision node in Neo4j; return its id for bridge tests."""
    did = str(uuid.uuid4())
    loop = asyncio.new_event_loop()

    async def _create() -> None:
        drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
        try:
            async with drv.session() as s:
                await s.run(
                    "MERGE (d:Decision {uuid: $id}) SET d.title = 'Wire test decision'",
                    id=did,
                )
        finally:
            await drv.close()

    try:
        loop.run_until_complete(_create())
    finally:
        loop.close()

    return did


# ── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_manage_adr_appears_in_tools_list(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    names = [t.name for t in result.tools]
    assert "palace.code.manage_adr" in names, (
        f"palace.code.manage_adr missing from tools/list. Got: {names}"
    )


@pytest.mark.integration
async def test_write_valid_returns_ok(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.manage_adr",
                {
                    "mode": "write",
                    "slug": "wire-test-adr",
                    "section": "PURPOSE",
                    "body": "Wire test purpose body.",
                },
            )

    assert not result.isError, f"Expected ok, got isError: {result.content}"
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is True


@pytest.mark.integration
async def test_write_invalid_section_returns_envelope(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.manage_adr",
                {
                    "mode": "write",
                    "slug": "wire-test-adr",
                    "section": "INVALID_SECTION",
                    "body": "bad",
                },
            )

    assert result.content
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is False, "Invalid section must return ok=False envelope"
    assert not result.isError, "Validation errors must be envelope, NOT FastMCP isError"


@pytest.mark.integration
async def test_read_valid_slug_returns_ok(mcp_url: str) -> None:
    # Depends on write above having created wire-test-adr.
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.manage_adr",
                {"mode": "read", "slug": "wire-test-adr"},
            )

    assert not result.isError
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is True
    assert "sections" in payload
    assert payload["slug"] == "wire-test-adr"


@pytest.mark.integration
async def test_read_nonexistent_slug_returns_envelope(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.manage_adr",
                {"mode": "read", "slug": "nonexistent-wire-adr-xyz"},
            )

    assert result.content
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is False
    assert payload["error_code"] == "adr_not_found"
    assert not result.isError


@pytest.mark.integration
async def test_query_returns_ok_even_when_empty(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.manage_adr",
                {"mode": "query", "keyword": "zzznomatch_wire_xyz"},
            )

    assert not result.isError
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is True
    assert isinstance(payload["results"], list)


@pytest.mark.integration
async def test_query_finds_written_content(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.manage_adr",
                {"mode": "query", "keyword": "Wire test purpose"},
            )

    assert not result.isError
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is True


@pytest.mark.integration
async def test_supersede_valid_args_returns_ok(mcp_url: str) -> None:
    # First write a fresh old ADR.
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool(
                "palace.code.manage_adr",
                {
                    "mode": "write",
                    "slug": "wire-supersede-old",
                    "section": "PURPOSE",
                    "body": "Old design.",
                },
            )
            result = await session.call_tool(
                "palace.code.manage_adr",
                {
                    "mode": "supersede",
                    "old_slug": "wire-supersede-old",
                    "new_slug": "wire-supersede-new",
                    "reason": "Wire test supersede.",
                },
            )

    assert not result.isError
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is True


@pytest.mark.integration
async def test_supersede_nonexistent_old_returns_envelope(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.manage_adr",
                {
                    "mode": "supersede",
                    "old_slug": "wire-no-such-adr-xyz",
                    "new_slug": "wire-new-xyz",
                    "reason": "Should fail.",
                },
            )

    assert result.content
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is False
    assert payload["error_code"] == "adr_not_found"
    assert not result.isError


@pytest.mark.integration
async def test_write_with_valid_decision_id_returns_ok(
    mcp_url: str, decision_id: str
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.manage_adr",
                {
                    "mode": "write",
                    "slug": "wire-decision-bridge",
                    "section": "PURPOSE",
                    "body": "Decision bridge test.",
                    "decision_id": decision_id,
                },
            )

    assert not result.isError
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is True


@pytest.mark.integration
async def test_write_with_nonexistent_decision_id_returns_envelope(
    mcp_url: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.manage_adr",
                {
                    "mode": "write",
                    "slug": "wire-test-adr",
                    "section": "STACK",
                    "body": "Stack content.",
                    "decision_id": str(uuid.uuid4()),
                },
            )

    assert result.content
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is False
    assert payload["error_code"] == "decision_not_found"
    assert not result.isError
