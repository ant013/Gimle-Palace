"""Fixtures for codebase-memory-mcp integration tests.

Spawns a CM process via MCP SDK stdio transport, indexes the sandbox-repo
fixture, and provides a ClientSession for tool calls.
"""

from __future__ import annotations

import shutil
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack
from pathlib import Path

import pytest
import pytest_asyncio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SANDBOX_REPO = Path(__file__).parent.parent / "fixtures" / "sandbox-repo"
CM_BINARY = shutil.which("codebase-memory-mcp")


@pytest_asyncio.fixture(scope="session")
async def cm_session() -> AsyncGenerator[ClientSession, None]:
    """Start CM binary via stdio, index sandbox repo, yield ClientSession."""
    if CM_BINARY is None:
        pytest.skip("codebase-memory-mcp binary not found on PATH")

    params = StdioServerParameters(command=CM_BINARY, args=[])
    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(params))
        session = ClientSession(read, write)
        session = await stack.enter_async_context(session)
        await session.initialize()

        await session.call_tool(
            "index_repository",
            arguments={"repo_path": str(SANDBOX_REPO.resolve())},
        )

        yield session
