"""Wire-level integration tests for palace.code.test_impact — GIM-98.

Tests run over real HTTP+SSE via streamablehttp_client. The CM subprocess
is not required for schema/validation/error-path tests; CM-dependent happy
paths require COMPOSE_CM_BINARY to be set.

Run (schema + error paths only, no CM binary needed):
    COMPOSE_NEO4J_URI=bolt://localhost:7687 COMPOSE_NEO4J_PASSWORD=test \\
    uv run pytest tests/integration/test_palace_code_test_impact_wire.py -m integration

Run (happy paths — CM binary required):
    COMPOSE_NEO4J_URI=bolt://localhost:7687 COMPOSE_NEO4J_PASSWORD=test \\
    COMPOSE_CM_BINARY=/path/to/codebase-memory-mcp \\
    uv run pytest tests/integration/test_palace_code_test_impact_wire.py -m integration
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def neo4j_uri() -> str:
    if reuse := os.environ.get("COMPOSE_NEO4J_URI"):
        return reuse
    pytest.skip(
        "COMPOSE_NEO4J_URI not set — skipping test_impact integration tests. "
        "Set COMPOSE_NEO4J_URI=bolt://localhost:7687 to run."
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


# ---------------------------------------------------------------------------
# Schema / tool-list tests (no CM binary required)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_test_impact_appears_in_tools_list(mcp_url: str) -> None:
    """palace.code.test_impact must appear in tools/list."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    names = [t.name for t in result.tools]
    assert "palace.code.test_impact" in names, (
        f"palace.code.test_impact missing from tools/list. Got: {names}"
    )


@pytest.mark.integration
async def test_test_impact_input_schema_has_required_fields(mcp_url: str) -> None:
    """palace.code.test_impact inputSchema must expose expected parameters."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    tool = next((t for t in result.tools if t.name == "palace.code.test_impact"), None)
    assert tool is not None
    schema = tool.inputSchema
    assert schema is not None

    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    assert "qualified_name" in props, "qualified_name must be in inputSchema properties"
    assert "include_indirect" in props
    assert "max_hops" in props
    assert "max_results" in props

    required = schema.get("required", []) if isinstance(schema, dict) else []
    assert "qualified_name" in required, "qualified_name must be required"


# ---------------------------------------------------------------------------
# Validation error path (no CM binary required)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_test_impact_invalid_qn_returns_validation_error(mcp_url: str) -> None:
    """Calling with invalid qualified_name (spaces) returns validation_error."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.test_impact",
                {"qualified_name": "has spaces!"},
            )

    assert result.content, "tools/call must return non-empty content"
    # Should be a valid JSON envelope with error_code, not a TypeError
    text = " ".join(c.text for c in result.content if hasattr(c, "text"))
    data: dict = json.loads(text)
    assert data.get("ok") is False
    assert data.get("error_code") == "validation_error"


# ---------------------------------------------------------------------------
# CM-not-started error path (no CM binary required)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_test_impact_cm_not_started_returns_mcp_error(mcp_url: str) -> None:
    """When CM subprocess is not running, test_impact returns isError=True.

    Result must not contain 'TypeError' — the error must be surfaced
    as a clear CM-not-started message.
    """
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.test_impact",
                {"qualified_name": "register_code_tools"},
            )

    assert result.content, "tools/call must return non-empty content"
    error_text = " ".join(c.text for c in result.content if hasattr(c, "text"))
    assert "TypeError" not in error_text, f"TypeError must not appear in error: {error_text}"


# ---------------------------------------------------------------------------
# Happy-path tests (require COMPOSE_CM_BINARY)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cm_binary() -> str:
    binary = os.environ.get("COMPOSE_CM_BINARY", "")
    if not binary:
        pytest.skip(
            "COMPOSE_CM_BINARY not set — skipping CM-dependent happy path tests. "
            "Set COMPOSE_CM_BINARY=/path/to/codebase-memory-mcp to run."
        )
    return binary


@pytest.fixture(scope="module")
def mcp_url_with_cm(
    neo4j_uri: str, neo4j_auth: tuple[str, str], cm_binary: str
) -> Iterator[str]:
    """MCP server fixture with CM subprocess started."""
    import palace_mcp.mcp_server as _ms
    from palace_mcp import code_router

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    _ms.set_driver(drv)

    # Start CM subprocess via code_router
    loop = asyncio.new_event_loop()
    loop.run_until_complete(code_router.start_cm_subprocess(cm_binary))

    app = _ms.build_mcp_asgi_app()
    port = _free_port()
    srv = _TestServer(app, port)
    srv.start()

    yield f"http://127.0.0.1:{port}/"

    srv.stop()
    loop.run_until_complete(code_router.stop_cm_subprocess())
    loop.run_until_complete(drv.close())
    loop.close()
    _ms._driver = None  # type: ignore[attr-defined]


@pytest.mark.integration
async def test_default_path_happy(mcp_url_with_cm: str) -> None:
    """Default path: ok=True, method=tests_edge, all tests have hop=1."""
    async with streamablehttp_client(mcp_url_with_cm) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.test_impact",
                {
                    "qualified_name": "register_code_tools",
                    "project": os.environ.get("COMPOSE_CM_PROJECT", "repos-gimle"),
                },
            )

    assert result.content
    text = " ".join(c.text for c in result.content if hasattr(c, "text"))
    data: dict = json.loads(text)
    assert data.get("ok") is True, f"Expected ok=True, got: {data}"
    assert data.get("method") == "tests_edge"
    tests = data.get("tests", [])
    assert all(t["hop"] == 1 for t in tests), "All tests_edge tests must have hop=1"


@pytest.mark.integration
async def test_opt_in_path_happy(mcp_url_with_cm: str) -> None:
    """Opt-in path: ok=True, method=trace_call_path, disambiguation_caveat present."""
    async with streamablehttp_client(mcp_url_with_cm) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.test_impact",
                {
                    "qualified_name": "register_code_tools",
                    "project": os.environ.get("COMPOSE_CM_PROJECT", "repos-gimle"),
                    "include_indirect": True,
                    "max_hops": 2,
                },
            )

    assert result.content
    text = " ".join(c.text for c in result.content if hasattr(c, "text"))
    data: dict = json.loads(text)
    assert data.get("ok") is True, f"Expected ok=True, got: {data}"
    assert data.get("method") == "trace_call_path"
    assert "disambiguation_caveat" in data


@pytest.mark.integration
async def test_not_found_returns_symbol_not_found(mcp_url_with_cm: str) -> None:
    """Unknown symbol returns error_code=symbol_not_found."""
    async with streamablehttp_client(mcp_url_with_cm) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.test_impact",
                {
                    "qualified_name": "this_function_does_not_exist_xyzzy",
                    "project": os.environ.get("COMPOSE_CM_PROJECT", "repos-gimle"),
                },
            )

    assert result.content
    text = " ".join(c.text for c in result.content if hasattr(c, "text"))
    data: dict = json.loads(text)
    assert data.get("ok") is False
    assert data.get("error_code") == "symbol_not_found"
