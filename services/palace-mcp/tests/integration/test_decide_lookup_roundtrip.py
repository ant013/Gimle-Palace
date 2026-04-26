"""Round-trip integration test: palace.memory.decide → palace.memory.lookup.

Validates that:
1. A decision written via palace.memory.decide is readable via palace.memory.lookup.
2. The slice_ref filter in _WHITELIST["Decision"] actually works (Task 1 guard).
3. Properties like attestation and extractor are persisted correctly.

Run:
    COMPOSE_NEO4J_URI=bolt://localhost:7687 COMPOSE_NEO4J_PASSWORD=<pw> \\
    uv run pytest tests/integration/test_decide_lookup_roundtrip.py -m integration
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


@pytest.fixture(scope="module")
def neo4j_uri() -> str:
    if reuse := os.environ.get("COMPOSE_NEO4J_URI"):
        return reuse
    pytest.skip("COMPOSE_NEO4J_URI not set — skipping round-trip integration tests.")


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


@pytest.mark.integration
async def test_decide_then_lookup_by_slice_ref(mcp_url: str) -> None:
    """Write a Decision, then look it up by its unique slice_ref. Assert UUID matches.

    Guard: if _WHITELIST["Decision"] doesn't include slice_ref, the filter is
    logged+ignored and lookup returns ALL Decision nodes — the UUID assertion
    catches this.
    """
    # Use a unique slice_ref to avoid collisions with other test runs.
    unique_ref = f"GIM-95"
    test_title = f"Round-trip test {uuid.uuid4().hex[:8]}"

    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Write
            write_result = await session.call_tool(
                "palace.memory.decide",
                {
                    "title": test_title,
                    "body": "Round-trip test body for decide→lookup validation.",
                    "slice_ref": unique_ref,
                    "decision_maker_claimed": "pythonengineer",
                    "decision_kind": "design",
                    "confidence": 0.8,
                    "tags": ["integration-test"],
                },
            )

            assert not write_result.isError, (
                f"decide write failed: {write_result.content}"
            )
            write_payload = json.loads(write_result.content[0].text)
            assert write_payload["ok"] is True, f"decide returned not-ok: {write_payload}"
            written_uuid = write_payload["uuid"]

            # Read back via lookup with slice_ref filter
            lookup_result = await session.call_tool(
                "palace.memory.lookup",
                {
                    "entity_type": "Decision",
                    "filters": {"slice_ref": unique_ref},
                    "limit": 10,
                },
            )

    assert not lookup_result.isError, f"lookup failed: {lookup_result.content}"
    lookup_payload = json.loads(lookup_result.content[0].text)
    items = lookup_payload.get("items", [])

    # Find the specific node we just wrote by UUID
    matching = [it for it in items if it["id"] == written_uuid]
    assert len(matching) == 1, (
        f"Expected exactly 1 item with uuid={written_uuid}, "
        f"got {len(matching)} from {len(items)} total. "
        "If 0: slice_ref filter may be ignored (Task 1 regression). "
        f"Items: {[it['id'] for it in items]}"
    )

    props = matching[0]["properties"]
    assert props.get("attestation") == "none", (
        f"attestation must be 'none', got {props.get('attestation')!r}"
    )
    assert props.get("extractor") == "palace.memory.decide@0.1", (
        f"extractor must be 'palace.memory.decide@0.1', got {props.get('extractor')!r}"
    )
    assert props.get("decision_maker_claimed") == "pythonengineer"
