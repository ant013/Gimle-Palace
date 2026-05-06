"""Tests for Pattern #21: Startup duplicate tool name detection.

Duplicate MCP tool names must crash at boot with a clear RuntimeError,
not silently shadow each other.
"""

import pytest

from palace_mcp.mcp_server import assert_unique_tool_names


class TestAssertUniqueToolNames:
    def test_no_duplicates_passes(self) -> None:
        """Unique tool names → no exception raised."""
        assert_unique_tool_names(
            ["palace.health.status", "palace.memory.lookup", "palace.memory.health"]
        )

    def test_duplicate_raises_runtime_error(self) -> None:
        """Duplicate tool name → RuntimeError with the offending name in the message."""
        with pytest.raises(RuntimeError, match="palace.memory.lookup"):
            assert_unique_tool_names(
                ["palace.health.status", "palace.memory.lookup", "palace.memory.lookup"]
            )

    def test_empty_list_passes(self) -> None:
        """No tools registered → no exception."""
        assert_unique_tool_names([])

    def test_single_tool_passes(self) -> None:
        """Single tool → no exception."""
        assert_unique_tool_names(["palace.health.status"])

    def test_build_mcp_asgi_app_uses_current_tools_without_crash(self) -> None:
        """build_mcp_asgi_app() with existing tool registrations does not crash.

        This validates that our currently registered tools have unique names.
        """
        from palace_mcp.mcp_server import build_mcp_asgi_app

        # Should not raise — all current tool names are unique.
        build_mcp_asgi_app()


class TestCodeToolRegistration:
    def test_code_tools_registered_in_mcp(self) -> None:
        """palace.code.* tools pass Pattern #21 dedup and appear in the MCP app.

        Tests through build_mcp_asgi_app() — same path as TestAssertUniqueToolNames.
        Verifies that code tools are tracked by _registered_tool_names (Pattern #21)
        and don't collide with existing palace.memory.* / palace.git.* tools.
        """
        from palace_mcp.mcp_server import build_mcp_asgi_app, _mcp

        build_mcp_asgi_app()  # asserts unique names — would crash on collision
        code_tools = [
            t
            for t in _mcp._tool_manager.list_tools()
            if t.name.startswith("palace.code.")
        ]
        assert {tool.name for tool in code_tools} == {
            "palace.code.detect_changes",
            "palace.code.find_hotspots",
            "palace.code.find_owners",
            "palace.code.find_references",
            "palace.code.find_version_skew",
            "palace.code.get_architecture",
            "palace.code.get_code_snippet",
            "palace.code.list_functions",
            "palace.code.manage_adr",
            "palace.code.query_graph",
            "palace.code.search_code",
            "palace.code.search_graph",
            "palace.code.test_impact",
            "palace.code.trace_call_path",
        }
