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
from mcp.server.fastmcp.tools.base import Tool
from mcp.server.fastmcp.utilities.func_metadata import (
    ArgModelBase,
    FuncMetadata,
    func_metadata as _func_metadata,
)
from mcp.types import CallToolResult, TextContent
from pydantic import ConfigDict

logger = logging.getLogger(__name__)

_cm_session: ClientSession | None = None
_cm_exit_stack: AsyncExitStack | None = None


def _set_cm_session(session: ClientSession | None) -> None:
    """DI injection point — used by tests."""
    global _cm_session  # noqa: PLW0603
    _cm_session = session


def get_cm_session() -> ClientSession | None:
    """Public accessor — returns current CM session, None if not started.

    Use from composite tools to read the session at invocation time
    (avoids None-at-import-time of direct imports).
    """
    return _cm_session


def parse_cm_result(result: Any) -> dict[str, Any]:
    """Parse MCP CallToolResult → dict; replaces inline logic in _forward.

    Public so composite tools (code_composite.py) can reuse the same
    result-extraction semantics without duplicating the pattern.

    Note: non-dict JSON is wrapped as {"_raw": value} (intentional rename
    from _forward's {"result": value} — near-unreachable in practice).
    Non-JSON text is wrapped as {"_raw": text}.
    """
    if result.structuredContent is not None:
        return dict(result.structuredContent)
    for block in result.content:
        if isinstance(block, TextContent):
            try:
                parsed = json.loads(block.text)
                return parsed if isinstance(parsed, dict) else {"_raw": parsed}
            except json.JSONDecodeError:
                return {"_raw": block.text}
    return {}


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


class _OpenArgs(ArgModelBase):
    """Open argument model: accepts any flat fields and returns all as kwargs.

    FastMCP's func_metadata generates a closed schema from typed function
    signatures. This model bypasses that by accepting all extras and returning
    them from model_dump_one_level(), which is what call_fn_with_arg_validation
    unpacks into **kwargs for the underlying function.
    """

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    def model_dump_one_level(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


_OPEN_SCHEMA: dict[str, Any] = {"type": "object", "additionalProperties": True}


def _make_open_fn_metadata(fn: Any) -> FuncMetadata:
    """Build FuncMetadata with open arg schema, preserving the function's output schema."""
    real_meta = _func_metadata(fn)
    return FuncMetadata(
        arg_model=_OpenArgs,
        output_schema=real_meta.output_schema,
        output_model=real_meta.output_model,
        wrap_output=real_meta.wrap_output,
    )


def _patch_tool_open_schema(
    mcp_instance: Any, name: str, fn_meta: FuncMetadata
) -> None:
    """Replace a registered FastMCP tool with an open-schema variant."""
    original = mcp_instance._tool_manager._tools[name]
    mcp_instance._tool_manager._tools[name] = Tool(
        fn=original.fn,
        name=original.name,
        title=original.title,
        description=original.description,
        parameters=_OPEN_SCHEMA,
        fn_metadata=fn_meta,
        is_async=original.is_async,
        context_kwarg=original.context_kwarg,
        annotations=original.annotations,
        icons=original.icons,
        meta=original.meta,
    )


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
    mcp_instance: Any = None,
) -> None:
    """Register all palace.code.* tools using the provided decorator.

    Accepts `_tool` from mcp_server.py — Pattern #21 dedup-aware decorator
    that appends each name to `_registered_tool_names` before delegating
    to `@_mcp.tool()`.

    Pass `mcp_instance` (the FastMCP server) to enable open-schema patching
    so that MCP clients can call tools with flat arguments (GIM-89 fix).
    """
    for cm_name, desc in _ENABLED_CM_TOOLS.items():
        _register_passthrough(tool_decorator, cm_name, desc, mcp_instance)
    for disabled_name, message in _DISABLED_CM_TOOLS.items():
        _register_disabled_tool(tool_decorator, disabled_name, message, mcp_instance)


def _register_passthrough(
    tool_decorator: Callable[[str, str], Callable[..., Any]],
    cm_tool_name: str,
    description: str,
    mcp_instance: Any = None,
) -> None:
    palace_name = f"palace.code.{cm_tool_name}"

    @tool_decorator(palace_name, description)
    async def _forward(**kwargs: Any) -> dict[str, Any]:
        assert _cm_session is not None, (
            "CM subprocess not started; set CODEBASE_MEMORY_MCP_BINARY"
        )
        result: CallToolResult = await _cm_session.call_tool(
            cm_tool_name, arguments=kwargs
        )
        if result.isError:
            return {"error": [str(block) for block in result.content]}
        return parse_cm_result(result)

    if mcp_instance is not None:
        _patch_tool_open_schema(
            mcp_instance, palace_name, _make_open_fn_metadata(_forward)
        )


def _register_disabled_tool(
    tool_decorator: Callable[[str, str], Callable[..., Any]],
    cm_tool_name: str,
    message: str,
    mcp_instance: Any = None,
) -> None:
    palace_name = f"palace.code.{cm_tool_name}"

    @tool_decorator(palace_name, f"[DISABLED] {cm_tool_name}")
    async def _blocked(**kwargs: Any) -> dict[str, Any]:
        return {
            "error": message,
            "hint": "Use palace.memory.lookup Decision {...} instead.",
        }

    if mcp_instance is not None:
        _patch_tool_open_schema(
            mcp_instance, palace_name, _make_open_fn_metadata(_blocked)
        )
