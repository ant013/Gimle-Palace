"""MCP wire-contract tests for palace.code.list_functions (GIM-195).

Run:
    COMPOSE_NEO4J_URI=bolt://localhost:7687 COMPOSE_NEO4J_PASSWORD=changeme \\
    uv run pytest tests/integration/test_list_functions_tool.py -m integration
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


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _TestServer:
    def __init__(self, app: object, port: int) -> None:
        import uvicorn
        self.port = port
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False)
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


@pytest.fixture(scope="module")
def neo4j_uri() -> str:
    if reuse := os.environ.get("COMPOSE_NEO4J_URI"):
        return reuse
    pytest.skip("COMPOSE_NEO4J_URI not set — skipping MCP wire-contract tests.")


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


@pytest.fixture(scope="module")
def seeded_functions_project(neo4j_uri: str, neo4j_auth: tuple[str, str]) -> Iterator[str]:
    """Seed :Project + :File + :Function nodes for list_functions tests; delete after module."""
    from neo4j import GraphDatabase
    slug = "lf-wire-seeded"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
        sess.run(
            "MERGE (f:File {project_id: $p, path: 'src/python_complex.py'}) "
            "SET f.hotspot_score = 2.5, f.ccn_total = 8, f.churn_count = 5, "
            "f.complexity_status = 'fresh', f.complexity_window_days = 90, "
            "f.last_complexity_run_at = datetime('2026-05-01T00:00:00Z')",
            p=slug,
        )
        # classify function: ccn=6
        sess.run(
            "MATCH (f:File {project_id: $p, path: 'src/python_complex.py'}) "
            "MERGE (fn:Function {project_id: $p, path: 'src/python_complex.py', name: 'classify', start_line: 1}) "
            "SET fn.end_line = 11, fn.ccn = 6, fn.parameter_count = 1, fn.nloc = 11, fn.language = 'python' "
            "MERGE (f)-[:CONTAINS]->(fn)",
            p=slug,
        )
        # helper function: ccn=2
        sess.run(
            "MATCH (f:File {project_id: $p, path: 'src/python_complex.py'}) "
            "MERGE (fn:Function {project_id: $p, path: 'src/python_complex.py', name: 'helper', start_line: 13}) "
            "SET fn.end_line = 17, fn.ccn = 2, fn.parameter_count = 0, fn.nloc = 5, fn.language = 'python' "
            "MERGE (f)-[:CONTAINS]->(fn)",
            p=slug,
        )
    yield slug
    with drv.session() as sess:
        sess.run(
            "MATCH (n) WHERE n.project_id = $s DETACH DELETE n",
            s=slug,
        )
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_unregistered_project_returns_error(mcp_url: str) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.list_functions",
                {"project": "doesnotexist", "path": "src/x.py"},
            )
    resp = json.loads(result.content[0].text)
    assert resp["ok"] is False
    assert resp["error_code"] == "project_not_registered"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_missing_file_returns_empty(
    mcp_url: str, seeded_functions_project: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.list_functions",
                {"project": seeded_functions_project, "path": "src/does_not_exist.py"},
            )
    resp = json.loads(result.content[0].text)
    assert resp.get("ok") is True
    assert resp["result"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_min_ccn_filter_excludes_low(
    mcp_url: str, seeded_functions_project: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.list_functions",
                {
                    "project": seeded_functions_project,
                    "path": "src/python_complex.py",
                    "min_ccn": 100,
                },
            )
    resp = json.loads(result.content[0].text)
    assert resp.get("ok") is True
    assert resp["result"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_functions_returns_sorted_by_ccn_desc(
    mcp_url: str, seeded_functions_project: str,
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.list_functions",
                {"project": seeded_functions_project, "path": "src/python_complex.py", "min_ccn": 0},
            )
    resp = json.loads(result.content[0].text)
    assert resp.get("ok") is True
    rows = resp["result"]
    assert len(rows) >= 1
    ccns = [r["ccn"] for r in rows]
    assert ccns == sorted(ccns, reverse=True)
    for r in rows:
        for k in ("name", "start_line", "end_line", "ccn", "parameter_count", "nloc", "language"):
            assert k in r
