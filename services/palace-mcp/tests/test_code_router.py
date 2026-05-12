"""Unit tests for code_router.py — palace.code.* tool registration."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest
from mcp import ClientSession
from mcp.server.fastmcp import FastMCP
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

        register_code_tools(stub_tool, mcp)
        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        for name in EXPECTED_ENABLED_TOOLS:
            assert name in tool_names, f"Missing tool: {name}"

    def test_manage_adr_not_in_cm_router(self) -> None:
        """palace.code.manage_adr is NOT registered via code_router (GIM-274: native tool)."""
        stub_tool, mcp, _ = self._make_stub_tool()
        from palace_mcp.code_router import register_code_tools

        register_code_tools(stub_tool, mcp)
        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "palace.code.manage_adr" not in tool_names, (
            "manage_adr must be registered via adr/router.py, not code_router"
        )

    def test_total_tool_count_is_seven(self) -> None:
        """Exactly 7 palace.code.* tools registered via code_router (all CM pass-throughs)."""
        stub_tool, mcp, _ = self._make_stub_tool()
        from palace_mcp.code_router import register_code_tools

        register_code_tools(stub_tool, mcp)
        code_tools = [
            t
            for t in mcp._tool_manager.list_tools()
            if t.name.startswith("palace.code.")
        ]
        assert len(code_tools) == 7

    def test_each_tool_dispatches_to_distinct_cm_name(self) -> None:
        """Verify each registered tool forwards to its own CM tool name (closure binding correctness).

        CR CRITICAL #2: The decorator receives a factory-bound cm_tool_name,
        ensuring no late-binding closure bug in the registration loop.
        """
        stub_tool, mcp, _ = self._make_stub_tool()
        from palace_mcp.code_router import register_code_tools

        register_code_tools(stub_tool, mcp)
        tools = [
            t
            for t in mcp._tool_manager.list_tools()
            if t.name.startswith("palace.code.")
        ]
        names = {t.name for t in tools}
        assert len(names) == 7, (
            f"Expected 7 distinct tool names, got {len(names)}: {names}"
        )

    def test_decorator_receives_seven_names(self) -> None:
        """Stub decorator tracks all 7 CM tool names — proves Pattern #21 integration point works."""
        stub_tool, mcp, tracked = self._make_stub_tool()
        from palace_mcp.code_router import register_code_tools

        register_code_tools(stub_tool, mcp)
        code_names = [n for n in tracked if n.startswith("palace.code.")]
        assert len(code_names) == 7, f"Expected 7, got {len(code_names)}: {code_names}"

    def test_open_schema_on_enabled_tools(self) -> None:
        """After patching, all enabled tools expose additionalProperties: true schema."""
        stub_tool, mcp, _ = self._make_stub_tool()
        from palace_mcp.code_router import register_code_tools

        register_code_tools(stub_tool, mcp)
        for name in EXPECTED_ENABLED_TOOLS:
            tool = mcp._tool_manager.get_tool(name)
            assert tool.parameters.get("additionalProperties") is True, (
                f"{name} schema missing additionalProperties: true"
            )



class TestPassthroughSerialization:
    @pytest.mark.asyncio
    async def test_call_tool_arguments_forwarded(self) -> None:
        """Pass-through calls cm_session.call_tool with flat args (no double-nesting)."""
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
        register_code_tools(stub_tool, mcp)

        # Flat args — the normal MCP client calling convention (GIM-89 fix).
        await mcp.call_tool("palace.code.search_graph", {"name_pattern": "main"})

        mock_session.call_tool.assert_called_once_with(
            "search_graph", arguments={"name_pattern": "main"}
        )

        _set_cm_session(None)

    @pytest.mark.asyncio
    async def test_fastmcp_signature_binding_flat_args(self) -> None:
        """FastMCP schema binding propagates flat args to CM — no double-nesting.

        Exercises the full FastMCP call path (mcp.call_tool, not tool.run)
        to prove the open-schema patching produces the correct arg binding (GIM-89).
        """
        from mcp.types import CallToolResult

        from palace_mcp.code_router import _set_cm_session, register_code_tools

        captured: dict = {}

        async def _fake_call_tool(name: str, arguments: dict) -> CallToolResult:  # type: ignore[type-arg]
            captured["name"] = name
            captured["arguments"] = arguments
            return CallToolResult(
                content=[TextContent(type="text", text='{"total":1}')],
                isError=False,
            )

        mock_session = AsyncMock(spec=ClientSession)
        mock_session.call_tool = AsyncMock(side_effect=_fake_call_tool)
        _set_cm_session(mock_session)

        mcp = FastMCP("test")
        stub_tool = lambda name, desc: mcp.tool(name=name, description=desc)  # noqa: E731
        register_code_tools(stub_tool, mcp)

        # mcp.call_tool goes through FastMCP's full argument-binding pipeline.
        await mcp.call_tool(
            "palace.code.search_graph",
            {"name_pattern": "register_code_tools", "project": "repos-gimle"},
        )

        assert captured["name"] == "search_graph"
        assert captured["arguments"] == {
            "name_pattern": "register_code_tools",
            "project": "repos-gimle",
        }

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
        register_code_tools(stub_tool, mcp)

        await mcp.call_tool("palace.code.get_architecture", {})
        mock_session.call_tool.assert_called_once_with("get_architecture", arguments={})

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
        register_code_tools(stub_tool, mcp)

        with pytest.raises(Exception, match="CM subprocess died"):
            await mcp.call_tool("palace.code.get_architecture", {})

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
        register_code_tools(stub_tool, mcp)

        result = await mcp.call_tool("palace.code.search_code", {})
        # Unpack: call_tool may return tuple (content, structured) or content list
        if isinstance(result, tuple):
            structured = result[1]
            assert "error" in structured
        else:
            import json as _json

            text = result[0].text
            parsed = _json.loads(text)
            assert "error" in parsed

        _set_cm_session(None)
