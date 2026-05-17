"""Integration tests for palace.code.* tools against a real CM subprocess.

Each test calls CM directly via the injected ClientSession and verifies a
non-error response shape. Tests are skipped when CM binary is not on PATH.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from tests.code_graph.conftest import CodeGraphSession
from tests.code_graph.conftest import cm_session


async def _call_tool(
    cm_session: CodeGraphSession,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> Any:
    """Call a CM tool via MCP SDK and return the unwrapped result."""
    tool_args = {"project": cm_session.project}
    if arguments is not None:
        tool_args.update(arguments)

    result = await cm_session.session.call_tool(tool_name, arguments=tool_args)
    assert not result.isError, f"CM returned error: {result.content}"
    if result.structuredContent is not None:
        return result.structuredContent

    for block in result.content:
        if hasattr(block, "text"):
            try:
                return json.loads(block.text)
            except json.JSONDecodeError:
                return {"text": block.text}
    return {}


@pytest.mark.asyncio
class TestCodeGraphIntegration:
    async def test_end_to_end_get_architecture(self) -> None:
        async with cm_session() as session:
            result = await _call_tool(session, "get_architecture")
        assert isinstance(result, dict)
        assert "project" in result

    async def test_end_to_end_search_graph(self) -> None:
        async with cm_session() as session:
            result = await _call_tool(session, "search_graph", {"name_pattern": "main"})
        assert isinstance(result, dict)

    async def test_end_to_end_trace_path(self) -> None:
        async with cm_session() as session:
            result = await _call_tool(
                session,
                "trace_path",
                {"function_name": "main", "direction": "outbound", "depth": 2},
            )
        assert isinstance(result, dict)

    async def test_end_to_end_get_code_snippet(self) -> None:
        async with cm_session() as session:
            result = await _call_tool(
                session, "get_code_snippet", {"qualified_name": "main"}
            )
        assert isinstance(result, dict)

    async def test_end_to_end_query_graph(self) -> None:
        async with cm_session() as session:
            result = await _call_tool(
                session, "query_graph", {"query": "MATCH (n) RETURN count(n)"}
            )
        assert result is not None

    async def test_end_to_end_detect_changes(self) -> None:
        async with cm_session() as session:
            result = await _call_tool(session, "detect_changes")
        assert isinstance(result, dict)

    async def test_end_to_end_search_code(self) -> None:
        async with cm_session() as session:
            result = await _call_tool(session, "search_code", {"pattern": "def main"})
        assert isinstance(result, dict)

    async def test_end_to_end_manage_adr(self) -> None:
        async with cm_session() as session:
            result = await _call_tool(session, "manage_adr", {"mode": "get"})
        assert isinstance(result, dict)
        assert "status" in result

    async def test_manage_adr_not_registered_by_code_router(self) -> None:
        """manage_adr must be registered by adr.router, not code_router."""
        from mcp.server.fastmcp import FastMCP

        from palace_mcp.code_router import register_code_tools

        mcp = FastMCP("test")
        stub_tool = lambda name, desc: mcp.tool(name=name, description=desc)  # noqa: E731
        register_code_tools(stub_tool, mcp)
        with pytest.raises(ToolError, match="Unknown tool: palace.code.manage_adr"):
            await mcp.call_tool("palace.code.manage_adr", {"project": "unused"})

    async def test_router_flat_args_reach_cm(self) -> None:
        """palace.code.search_graph with flat args (no double-nesting) returns results.

        Regression test for GIM-89: **kwargs signature must propagate flat args
        through FastMCP binding all the way to the CM subprocess.
        """
        from mcp.server.fastmcp import FastMCP

        from palace_mcp.code_router import _set_cm_session, register_code_tools

        async with cm_session() as session:
            _set_cm_session(session.session)
            try:
                mcp = FastMCP("test")
                stub_tool = lambda name, desc: mcp.tool(name=name, description=desc)  # noqa: E731
                register_code_tools(stub_tool, mcp)

                # Call through FastMCP's full pipeline with flat args (GIM-89 regression).
                result = await mcp.call_tool(
                    "palace.code.search_graph",
                    {"project": session.project, "name_pattern": "main"},
                )
            finally:
                _set_cm_session(None)

        assert result is not None
