"""palace.code.* MCP tool router — pass-through to codebase-memory-mcp subprocess.

Registers 7 enabled tools (forwarded to CM via MCP SDK stdio transport) and
1 disabled tool (manage_adr — returns directive error).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, TextContent

logger = logging.getLogger(__name__)

_cm_session: ClientSession | None = None
_cm_exit_stack: AsyncExitStack | None = None


def _set_cm_session(session: ClientSession | None) -> None:
    """DI injection point — used by tests."""
    global _cm_session  # noqa: PLW0603
    _cm_session = session


async def start_cm_subprocess(binary: str) -> None:
    """Start CM binary as stdio subprocess and initialize MCP session."""
    global _cm_session, _cm_exit_stack  # noqa: PLW0603
    stack = AsyncExitStack()
    params = StdioServerParameters(command=binary, args=[])
    read, write = await stack.enter_async_context(stdio_client(params))
    session = ClientSession(read, write)
    _cm_session = await stack.enter_async_context(session)
    await session.initialize()
    _cm_exit_stack = stack
    logger.info("codebase-memory-mcp subprocess started: %s", binary)


async def stop_cm_subprocess() -> None:
    """Shut down the CM subprocess and close MCP session."""
    global _cm_session, _cm_exit_stack  # noqa: PLW0603
    if _cm_exit_stack is not None:
        await _cm_exit_stack.aclose()
    _cm_session = None
    _cm_exit_stack = None
    logger.info("codebase-memory-mcp subprocess stopped")


_ENABLED_CM_TOOLS: dict[str, str] = {
    "search_graph": "Search code graph nodes by name pattern, label, or file pattern.",
    "trace_call_path": "Trace function call chains (inbound/outbound/both).",
    "query_graph": "Run a Cypher-like query against the code graph.",
    "detect_changes": "Detect uncommitted changes mapped to symbols.",
    "get_architecture": "Get project architecture: languages, packages, entry points, routes.",
    "get_code_snippet": "Get source code for a qualified symbol name.",
    "search_code": "Grep-like code search across indexed repositories.",
}

_DISABLED_CM_TOOLS: dict[str, str] = {
    "manage_adr": (
        "Decision is authoritative in palace.memory; CM ADR store is not used. "
        "Use palace.memory.lookup Decision {...} to read."
    ),
}


def register_code_tools(
    tool_decorator: Callable[[str, str], Callable[..., Any]],
) -> None:
    """Register all palace.code.* tools using the provided decorator.

    Accepts `_tool` from mcp_server.py — Pattern #21 dedup-aware decorator
    that appends each name to `_registered_tool_names` before delegating
    to `@_mcp.tool()`.
    """
    for cm_name, desc in _ENABLED_CM_TOOLS.items():
        _register_passthrough(tool_decorator, cm_name, desc)
    for disabled_name, message in _DISABLED_CM_TOOLS.items():
        _register_disabled_tool(tool_decorator, disabled_name, message)


def _register_passthrough(
    tool_decorator: Callable[[str, str], Callable[..., Any]],
    cm_tool_name: str,
    description: str,
) -> None:
    palace_name = f"palace.code.{cm_tool_name}"

    @tool_decorator(palace_name, description)
    async def _forward(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        assert _cm_session is not None, (
            "CM subprocess not started; set CODEBASE_MEMORY_MCP_BINARY"
        )
        args = arguments or {}
        result: CallToolResult = await _cm_session.call_tool(
            cm_tool_name, arguments=args
        )
        if result.isError:
            return {"error": [str(block) for block in result.content]}
        if result.structuredContent is not None:
            return dict(result.structuredContent)
        for block in result.content:
            if isinstance(block, TextContent):
                try:
                    parsed = json.loads(block.text)
                    if isinstance(parsed, dict):
                        return parsed
                    return {"result": parsed}
                except json.JSONDecodeError:
                    return {"text": block.text}
        return {}


def _register_disabled_tool(
    tool_decorator: Callable[[str, str], Callable[..., Any]],
    cm_tool_name: str,
    message: str,
) -> None:
    palace_name = f"palace.code.{cm_tool_name}"

    @tool_decorator(palace_name, f"[DISABLED] {cm_tool_name}")
    async def _blocked() -> dict[str, Any]:
        return {
            "error": message,
            "hint": "Use palace.memory.lookup Decision {...} instead.",
        }
