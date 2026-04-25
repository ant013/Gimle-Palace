"""Integration tests for palace.code.* tools against a real CM subprocess.

Each test calls CM directly via the injected ClientSession and verifies a
non-error response shape. Tests are skipped when CM binary is not on PATH.
"""

from __future__ import annotations

from typing import Any

import pytest
from mcp import ClientSession


async def _call_tool(
    session: ClientSession,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> Any:
    """Call a CM tool via MCP SDK and return the unwrapped result."""
    result = await session.call_tool(tool_name, arguments=arguments or {})
    assert not result.isError, f"CM returned error: {result.content}"
    if result.structuredContent is not None:
        return result.structuredContent
    import json

    for block in result.content:
        if hasattr(block, "text"):
            try:
                return json.loads(block.text)
            except json.JSONDecodeError:
                return {"text": block.text}
    return {}


@pytest.mark.asyncio
class TestCodeGraphIntegration:
    async def test_end_to_end_get_architecture(self, cm_session: ClientSession) -> None:
        result = await _call_tool(cm_session, "get_architecture")
        assert isinstance(result, dict)
        assert "languages" in result

    async def test_end_to_end_search_graph(self, cm_session: ClientSession) -> None:
        result = await _call_tool(cm_session, "search_graph", {"name_pattern": "main"})
        assert isinstance(result, (dict, list))

    async def test_end_to_end_trace_call_path(self, cm_session: ClientSession) -> None:
        result = await _call_tool(
            cm_session,
            "trace_call_path",
            {"function_name": "main", "direction": "outbound", "depth": 2},
        )
        assert isinstance(result, (dict, list))

    async def test_end_to_end_get_code_snippet(self, cm_session: ClientSession) -> None:
        result = await _call_tool(
            cm_session, "get_code_snippet", {"qualified_name": "main"}
        )
        assert isinstance(result, (dict, str))

    async def test_end_to_end_query_graph(self, cm_session: ClientSession) -> None:
        result = await _call_tool(
            cm_session, "query_graph", {"query": "MATCH (n) RETURN count(n)"}
        )
        assert result is not None

    async def test_end_to_end_detect_changes(self, cm_session: ClientSession) -> None:
        result = await _call_tool(cm_session, "detect_changes")
        assert isinstance(result, (dict, list))

    async def test_end_to_end_search_code(self, cm_session: ClientSession) -> None:
        result = await _call_tool(cm_session, "search_code", {"pattern": "def main"})
        assert isinstance(result, (dict, list))

    async def test_end_to_end_manage_adr_blocked(
        self, cm_session: ClientSession
    ) -> None:
        """manage_adr goes through the router disabled path, not CM directly."""
        from mcp.server.fastmcp import FastMCP

        from palace_mcp.code_router import _set_cm_session, register_code_tools

        _set_cm_session(cm_session)
        mcp = FastMCP("test")
        stub_tool = lambda name, desc: mcp.tool(name=name, description=desc)  # noqa: E731
        register_code_tools(stub_tool)
        tool = next(
            t
            for t in mcp._tool_manager.list_tools()
            if t.name == "palace.code.manage_adr"
        )
        result = await tool.run(arguments={})
        assert "error" in result
        assert "palace.memory" in result["error"]
        _set_cm_session(None)
