"""Fixtures for codebase-memory-mcp integration tests.

Spawns a CM process on an ephemeral port, indexes the sandbox-repo fixture,
and provides an httpx client pointed at it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

SANDBOX_REPO = Path(__file__).parent.parent / "fixtures" / "sandbox-repo"
CM_BINARY = shutil.which("codebase-memory-mcp")


def _find_free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def cm_port() -> Generator[int, None, None]:
    """Start CM on an ephemeral port, yield the port, kill on teardown."""
    if CM_BINARY is None:
        pytest.skip("codebase-memory-mcp binary not found on PATH")

    port = _find_free_port()
    proc = subprocess.Popen(
        [CM_BINARY, "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "CM_DATA_DIR": str(Path("/tmp") / f"cm-test-{port}")},
    )
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(30):
        try:
            r = httpx.post(
                f"{base_url}/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 0},
                timeout=2.0,
            )
            if r.status_code == 200:
                break
        except httpx.ConnectError:
            time.sleep(0.5)
    else:
        proc.kill()
        pytest.fail("CM did not become ready within 15s")

    httpx.post(
        f"{base_url}/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "index_repository",
                "arguments": {"repo_path": str(SANDBOX_REPO.resolve())},
            },
            "id": 2,
        },
        timeout=30.0,
    )

    yield port

    proc.kill()
    proc.wait()


@pytest_asyncio.fixture(scope="session")
async def cm_client(cm_port: int) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async httpx client pointed at the CM subprocess."""
    client = httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{cm_port}/mcp",
        timeout=30.0,
    )
    yield client
    await client.aclose()
