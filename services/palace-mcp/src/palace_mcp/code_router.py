"""palace.code.* MCP tool router — pass-through to codebase-memory-mcp sidecar.

Registers 7 enabled tools (forwarded to CM via JSON-RPC over HTTP) and
1 disabled tool (manage_adr — returns directive error).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, cast

import httpx

logger = logging.getLogger(__name__)

_cm_client: httpx.AsyncClient | None = None


def set_cm_client(client: httpx.AsyncClient | None) -> None:
    """DI injection point — called from FastAPI lifespan."""
    global _cm_client  # noqa: PLW0603
    _cm_client = client


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


def register_code_tools(tool_decorator: Callable[[str, str], Callable[..., Any]]) -> None:
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
        assert _cm_client is not None, (
            "CM client not initialized; call set_cm_client() in lifespan"
        )
        args = arguments or {}
        response = await _cm_client.post(
            "",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": cm_tool_name, "arguments": args},
                "id": 1,
            },
        )
        response.raise_for_status()
        result = response.json()
        if "error" in result:
            return {"error": result["error"]}
        return cast(dict[str, Any], result.get("result", result))


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
