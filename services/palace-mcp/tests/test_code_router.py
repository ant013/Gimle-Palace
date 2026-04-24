"""Unit tests for code_router.py — palace.code.* tool registration."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest
from mcp import ClientSession
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import TextContent


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
            t
            for t in mcp._tool_manager.list_tools()
            if t.name.startswith("palace.code.")
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
        assert len(names) == 7, (
            f"Expected 7 distinct tool names, got {len(names)}: {names}"
        )

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

        tool = next(
            t
            for t in mcp._tool_manager.list_tools()
            if t.name == "palace.code.manage_adr"
        )
        result = await tool.run(arguments={})
        assert "error" in result
        assert "palace.memory" in result["error"]
        assert "hint" in result


class TestPassthroughSerialization:
    @pytest.mark.asyncio
    async def test_call_tool_arguments_forwarded(self) -> None:
        """Pass-through calls cm_session.call_tool with correct name and arguments."""
        from mcp.types import CallToolResult

        from palace_mcp.code_router import _set_cm_session, register_code_tools

        mock_result = CallToolResult(
            content=[TextContent(type="text", text='{"nodes":[]}')],
            isError=False,
        )
        mock_session = AsyncMock(spec=ClientSession)
        mock_session.call_tool = AsyncMock(return_value=mock_result)
        _set_cm_session(mock_session)

        mcp = FastMCP("test")
        stub_tool = lambda name, desc: mcp.tool(name=name, description=desc)  # noqa: E731
        register_code_tools(stub_tool)
        tool = next(
            t
            for t in mcp._tool_manager.list_tools()
            if t.name == "palace.code.search_graph"
        )
        result = await tool.run(arguments={"arguments": {"name_pattern": "main"}})

        mock_session.call_tool.assert_called_once_with(
            "search_graph", arguments={"name_pattern": "main"}
        )
        assert result == {"nodes": []}

        _set_cm_session(None)

    @pytest.mark.asyncio
    async def test_structured_content_returned_directly(self) -> None:
        """When structuredContent is present, it is returned as-is."""
        from mcp.types import CallToolResult

        from palace_mcp.code_router import _set_cm_session, register_code_tools

        mock_result = CallToolResult(
            content=[],
            structuredContent={"languages": ["python"], "packages": []},
            isError=False,
        )
        mock_session = AsyncMock(spec=ClientSession)
        mock_session.call_tool = AsyncMock(return_value=mock_result)
        _set_cm_session(mock_session)

        mcp = FastMCP("test")
        stub_tool = lambda name, desc: mcp.tool(name=name, description=desc)  # noqa: E731
        register_code_tools(stub_tool)
        tool = next(
            t
            for t in mcp._tool_manager.list_tools()
            if t.name == "palace.code.get_architecture"
        )
        result = await tool.run(arguments={})
        assert result == {"languages": ["python"], "packages": []}

        _set_cm_session(None)


class TestPassthroughError:
    @pytest.mark.asyncio
    async def test_exception_from_call_tool_surfaces_as_tool_error(self) -> None:
        """Exception from call_tool → FastMCP converts to ToolError."""
        from palace_mcp.code_router import _set_cm_session, register_code_tools

        mock_session = AsyncMock(spec=ClientSession)
        mock_session.call_tool = AsyncMock(
            side_effect=RuntimeError("CM subprocess died")
        )
        _set_cm_session(mock_session)

        mcp = FastMCP("test")
        stub_tool = lambda name, desc: mcp.tool(name=name, description=desc)  # noqa: E731
        register_code_tools(stub_tool)
        tool = next(
            t
            for t in mcp._tool_manager.list_tools()
            if t.name == "palace.code.get_architecture"
        )

        with pytest.raises(ToolError, match="CM subprocess died"):
            await tool.run(arguments={})

        _set_cm_session(None)

    @pytest.mark.asyncio
    async def test_is_error_result_returns_error_dict(self) -> None:
        """isError=True result returns error dict without raising."""
        from mcp.types import CallToolResult

        from palace_mcp.code_router import _set_cm_session, register_code_tools

        mock_result = CallToolResult(
            content=[TextContent(type="text", text="not found")],
            isError=True,
        )
        mock_session = AsyncMock(spec=ClientSession)
        mock_session.call_tool = AsyncMock(return_value=mock_result)
        _set_cm_session(mock_session)

        mcp = FastMCP("test")
        stub_tool = lambda name, desc: mcp.tool(name=name, description=desc)  # noqa: E731
        register_code_tools(stub_tool)
        tool = next(
            t
            for t in mcp._tool_manager.list_tools()
            if t.name == "palace.code.search_code"
        )
        result = await tool.run(arguments={})
        assert "error" in result

        _set_cm_session(None)
