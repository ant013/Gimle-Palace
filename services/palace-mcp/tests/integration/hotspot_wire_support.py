from __future__ import annotations

import asyncio
import os
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import suppress

import pytest
from neo4j import AsyncGraphDatabase


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


@pytest.fixture(scope="session")
def neo4j_uri() -> Iterator[str]:
    if reuse := os.environ.get("COMPOSE_NEO4J_URI"):
        yield reuse
        return

    try:
        from testcontainers.neo4j import Neo4jContainer  # type: ignore[import]
    except Exception as exc:
        pytest.skip(f"testcontainers.neo4j unavailable — skipping wire tests: {exc}")

    try:
        with Neo4jContainer("neo4j:5.26.0") as container:
            yield container.get_connection_url()
    except Exception as exc:
        pytest.skip(f"Could not start Neo4j testcontainer — skipping wire tests: {exc}")


@pytest.fixture(scope="session")
def neo4j_auth() -> tuple[str, str]:
    return (
        os.environ.get("COMPOSE_NEO4J_USER", "neo4j"),
        os.environ.get("COMPOSE_NEO4J_PASSWORD", "password"),
    )


@pytest.fixture(scope="session")
def mcp_url(neo4j_uri: str, neo4j_auth: tuple[str, str]) -> Iterator[str]:
    import palace_mcp.mcp_server as _ms

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    _ms.set_driver(drv)
    app = _ms.build_mcp_asgi_app()
    port = _free_port()
    srv = _TestServer(app, port)
    srv.start()
    yield f"http://127.0.0.1:{port}/"
    _ms._driver = None  # type: ignore[attr-defined]
    srv.stop()
    _cleanup = asyncio.new_event_loop()
    try:
        with suppress(RuntimeError):
            _cleanup.run_until_complete(drv.close())
    finally:
        _cleanup.close()
