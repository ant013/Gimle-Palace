"""Seed-fixture smoke for canonical namespace passthrough."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
import socket
import threading
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult, TextContent

_FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "namespace_smoke.json"
_SLUG = "bitcoin-core"
_CM_PROJECT_NAME = "Users-fixture-BitcoinCore"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _TestServer:
    def __init__(self, app: object, port: int) -> None:
        import uvicorn

        self.port = port
        config = uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="error", access_log=False
        )
        self._server = uvicorn.Server(config)
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        def _run() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._server.serve())
            finally:
                asyncio.set_event_loop(None)
                pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()

        self._thread = threading.Thread(target=_run, daemon=True)
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


class _FixtureCmSession:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_tool(
        self, name: str, arguments: dict[str, object]
    ) -> CallToolResult:
        self.calls.append((name, dict(arguments)))
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(self.payload),
                )
            ],
            isError=False,
        )


@pytest.fixture(scope="module")
def namespace_fixture_payload() -> dict[str, object]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _namespace_driver() -> MagicMock:
    async def _run(_query: str, **params: object) -> object:
        result = MagicMock()
        value = params["value"]
        if value in {_SLUG, _CM_PROJECT_NAME}:
            row = {"p": {"slug": _SLUG, "cm_project_name": _CM_PROJECT_NAME}}
        else:
            row = None
        result.single = AsyncMock(return_value=row)
        return result

    session = MagicMock()
    session.run = AsyncMock(side_effect=_run)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


@pytest.fixture(scope="module")
def mcp_url() -> Iterator[str]:
    import palace_mcp.mcp_server as mcp_server

    from palace_mcp.code.namespace import invalidate

    invalidate()
    mcp_server.set_driver(_namespace_driver())
    server = _TestServer(mcp_server.build_mcp_asgi_app(), _free_port())
    server.start()
    try:
        yield f"http://127.0.0.1:{server.port}/"
    finally:
        mcp_server._driver = None  # type: ignore[attr-defined]
        invalidate()
        server.stop()


@pytest.fixture
def fixture_cm_session(
    namespace_fixture_payload: dict[str, object],
) -> Iterator[_FixtureCmSession]:
    from palace_mcp.code_router import _set_cm_session

    session = _FixtureCmSession(namespace_fixture_payload)
    _set_cm_session(session)
    try:
        yield session
    finally:
        _set_cm_session(None)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_code_slug_namespace_smoke(
    mcp_url: str,
    fixture_cm_session: _FixtureCmSession,
    namespace_fixture_payload: dict[str, object],
) -> None:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "palace.code.search_code",
                {"project": _SLUG, "pattern": "HD"},
            )

    payload = json.loads(result.content[0].text)
    assert result.isError is False
    assert payload == namespace_fixture_payload
    assert fixture_cm_session.calls == [
        (
            "search_code",
            {
                "project": _CM_PROJECT_NAME,
                "pattern": "HD",
            },
        )
    ]
