"""Unit tests for code_router.py — palace.code.* tool registration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError


EXPECTED_ENABLED_TOOLS = [
    "palace.code.search_graph",
    "palace.code.trace_call_path",
    "palace.code.query_graph",
    "palace.code.detect_changes",
    "palace.code.get_architecture",
    "palace.code.get_code_snippet",
    "palace.code.search_code",
]


class TestToolRegistration:
    """Unit tests use a stub decorator to test code_router in isolation.

    Integration with mcp_server._tool (Pattern #21) is tested in
    test_mcp_server.py::TestCodeToolRegistration.
    """

    @staticmethod
    def _make_stub_tool() -> tuple[Callable, FastMCP, list[str]]:
        """Create a stub _tool decorator that registers on a test FastMCP instance."""
        mcp = FastMCP("test")
        tracked_names: list[str] = []

        def stub_tool(name: str, description: str) -> Callable:
            tracked_names.append(name)
            return mcp.tool(name=name, description=description)

        return stub_tool, mcp, tracked_names

    def test_registers_seven_enabled_tools(self) -> None:
        """register_code_tools adds exactly 7 palace.code.* pass-through tools."""
        stub_tool, mcp, _ = self._make_stub_tool()
        from palace_mcp.code_router import register_code_tools

        register_code_tools(stub_tool)
        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        for name in EXPECTED_ENABLED_TOOLS:
            assert name in tool_names, f"Missing tool: {name}"

    def test_registers_manage_adr_as_disabled(self) -> None:
        """palace.code.manage_adr is registered and returns directive error."""
        stub_tool, mcp, _ = self._make_stub_tool()
        from palace_mcp.code_router import register_code_tools

        register_code_tools(stub_tool)
        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "palace.code.manage_adr" in tool_names

    def test_total_tool_count_is_eight(self) -> None:
        """Exactly 8 palace.code.* tools registered (7 enabled + 1 disabled)."""
        stub_tool, mcp, _ = self._make_stub_tool()
        from palace_mcp.code_router import register_code_tools

        register_code_tools(stub_tool)
        code_tools = [
            t for t in mcp._tool_manager.list_tools() if t.name.startswith("palace.code.")
        ]
        assert len(code_tools) == 8

    def test_each_tool_dispatches_to_distinct_cm_name(self) -> None:
        """Verify each registered tool forwards to its own CM tool name (closure binding correctness).

        CR CRITICAL #2: The decorator receives a factory-bound cm_tool_name,
        ensuring no late-binding closure bug in the registration loop.
        """
        stub_tool, mcp, _ = self._make_stub_tool()
        from palace_mcp.code_router import register_code_tools

        register_code_tools(stub_tool)
        tools = [
            t
            for t in mcp._tool_manager.list_tools()
            if t.name.startswith("palace.code.") and t.name != "palace.code.manage_adr"
        ]
        names = {t.name for t in tools}
        assert len(names) == 7, f"Expected 7 distinct tool names, got {len(names)}: {names}"

    def test_decorator_receives_all_names(self) -> None:
        """Stub decorator tracks all 8 tool names — proves Pattern #21 integration point works."""
        stub_tool, _, tracked = self._make_stub_tool()
        from palace_mcp.code_router import register_code_tools

        register_code_tools(stub_tool)
        code_names = [n for n in tracked if n.startswith("palace.code.")]
        assert len(code_names) == 8, f"Expected 8, got {len(code_names)}: {code_names}"


class TestDisabledTool:
    @pytest.mark.asyncio
    async def test_manage_adr_returns_directive_error(self) -> None:
        """Calling palace.code.manage_adr returns error + hint, no forwarding."""
        from palace_mcp.code_router import register_code_tools

        mcp = FastMCP("test")
        stub_tool = lambda name, desc: mcp.tool(name=name, description=desc)  # noqa: E731
        register_code_tools(stub_tool)

        tool = next(t for t in mcp._tool_manager.list_tools() if t.name == "palace.code.manage_adr")
        result = await tool.run(arguments={})
        assert "error" in result
        assert "palace.memory" in result["error"]
        assert "hint" in result


class TestPassthroughSerialization:
    @pytest.mark.asyncio
    async def test_jsonrpc_envelope_shape(self) -> None:
        """Pass-through builds correct JSON-RPC envelope and unwraps result.

        FastMCP converts **kwargs to a required field so pass-through tools
        use a single `arguments: dict | None = None` parameter. The LLM passes
        tool args as: palace.code.search_graph(arguments={"name_pattern": "x"}).
        """
        from palace_mcp.code_router import register_code_tools, set_cm_client

        captured_request: dict[str, Any] = {}

        async def mock_post(url: str, *, json: dict[str, Any], **kw: Any) -> MagicMock:
            captured_request.update(json)
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"jsonrpc": "2.0", "result": {"nodes": []}, "id": 1}
            return resp

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post = mock_post
        set_cm_client(client)

        mcp = FastMCP("test")
        stub_tool = lambda name, desc: mcp.tool(name=name, description=desc)  # noqa: E731
        register_code_tools(stub_tool)
        tool = next(
            t for t in mcp._tool_manager.list_tools() if t.name == "palace.code.search_graph"
        )
        # `arguments` is the single dict parameter; LLM passes CM args inside it.
        result = await tool.run(arguments={"arguments": {"name_pattern": "main"}})

        assert captured_request["jsonrpc"] == "2.0"
        assert captured_request["method"] == "tools/call"
        assert captured_request["params"]["name"] == "search_graph"
        assert captured_request["params"]["arguments"] == {"name_pattern": "main"}
        assert result == {"nodes": []}

        set_cm_client(None)  # cleanup


class TestPassthroughTimeout:
    @pytest.mark.asyncio
    async def test_timeout_surfaces_as_error(self) -> None:
        """httpx timeout → httpx.ReadTimeout raised (FastMCP converts to isError)."""
        from palace_mcp.code_router import register_code_tools, set_cm_client

        async def mock_post_timeout(url: str, **kw: Any) -> None:
            raise httpx.ReadTimeout("Connection timed out")

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post = mock_post_timeout
        set_cm_client(client)

        mcp = FastMCP("test")
        stub_tool = lambda name, desc: mcp.tool(name=name, description=desc)  # noqa: E731
        register_code_tools(stub_tool)
        tool = next(
            t for t in mcp._tool_manager.list_tools() if t.name == "palace.code.get_architecture"
        )

        # FastMCP wraps the underlying exception in ToolError.
        with pytest.raises(ToolError, match="Connection timed out"):
            await tool.run(arguments={})

        set_cm_client(None)  # cleanup
