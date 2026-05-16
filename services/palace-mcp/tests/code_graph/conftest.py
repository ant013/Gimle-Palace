"""Fixtures for codebase-memory-mcp integration tests.

Spawns a CM process via MCP SDK stdio transport, indexes the sandbox-repo
fixture, and provides a ClientSession for tool calls.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SANDBOX_REPO = Path(__file__).parent.parent / "fixtures" / "sandbox-repo"
CM_BINARY = shutil.which("codebase-memory-mcp")


@dataclass(slots=True)
class CodeGraphSession:
    """ClientSession plus the indexed project name returned by CM."""

    session: ClientSession
    project: str


def _parse_tool_result(result: Any) -> dict[str, Any]:
    """Parse MCP call content into a dictionary."""
    if result.structuredContent is not None:
        return dict(result.structuredContent)

    for block in result.content:
        text = getattr(block, "text", None)
        if text is not None:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return {"text": text}
            return parsed if isinstance(parsed, dict) else {"result": parsed}

    return {}


@asynccontextmanager
async def cm_session() -> AsyncIterator[CodeGraphSession]:
    """Start CM binary via stdio and yield session + indexed project."""
    if CM_BINARY is None:
        pytest.skip("codebase-memory-mcp binary not found on PATH")

    params = StdioServerParameters(command=CM_BINARY, args=[])
    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(params))
        session = ClientSession(read, write)
        session = await stack.enter_async_context(session)
        await session.initialize()

        index_result = await session.call_tool(
            "index_repository",
            arguments={"repo_path": str(SANDBOX_REPO.resolve())},
        )
        index_payload = _parse_tool_result(index_result)
        project = index_payload.get("project")
        if not isinstance(project, str) or not project:
            pytest.fail(f"index_repository did not return a project name: {index_payload}")

        yield CodeGraphSession(session=session, project=project)
