"""Integration tests for palace.code.* tools against a real CM subprocess.

Each test calls CM directly via the injected client and verifies a non-error
response shape. Tests are skipped when CM binary is not on PATH.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest


async def _call_tool(
    cm_client: httpx.AsyncClient,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call a CM tool via JSON-RPC and return the result."""
    response = await cm_client.post(
        "",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments or {}},
            "id": 1,
        },
    )
    response.raise_for_status()
    data = response.json()
    assert "error" not in data, f"CM returned error: {data.get('error')}"
    return data.get("result", data)


@pytest.mark.asyncio
class TestCodeGraphIntegration:
    async def test_end_to_end_get_architecture(self, cm_client: httpx.AsyncClient) -> None:
        result = await _call_tool(cm_client, "get_architecture")
        assert isinstance(result, dict)
        assert "languages" in result

    async def test_end_to_end_search_graph(self, cm_client: httpx.AsyncClient) -> None:
        result = await _call_tool(cm_client, "search_graph", {"name_pattern": "main"})
        assert isinstance(result, (dict, list))

    async def test_end_to_end_trace_call_path(self, cm_client: httpx.AsyncClient) -> None:
        result = await _call_tool(
            cm_client,
            "trace_call_path",
            {"function_name": "main", "direction": "outbound", "depth": 2},
        )
        assert isinstance(result, (dict, list))

    async def test_end_to_end_get_code_snippet(self, cm_client: httpx.AsyncClient) -> None:
        result = await _call_tool(cm_client, "get_code_snippet", {"qualified_name": "main"})
        assert isinstance(result, (dict, str))

    async def test_end_to_end_query_graph(self, cm_client: httpx.AsyncClient) -> None:
        result = await _call_tool(cm_client, "query_graph", {"query": "MATCH (n) RETURN count(n)"})
        assert result is not None

    async def test_end_to_end_detect_changes(self, cm_client: httpx.AsyncClient) -> None:
        result = await _call_tool(cm_client, "detect_changes")
        assert isinstance(result, (dict, list))

    async def test_end_to_end_search_code(self, cm_client: httpx.AsyncClient) -> None:
        result = await _call_tool(cm_client, "search_code", {"pattern": "def main"})
        assert isinstance(result, (dict, list))

    async def test_end_to_end_manage_adr_blocked(self, cm_client: httpx.AsyncClient) -> None:
        """manage_adr goes through the router disabled path, not CM directly."""
        from mcp.server.fastmcp import FastMCP

        from palace_mcp.code_router import register_code_tools
        from palace_mcp.code_router import set_cm_client as _set

        _set(cm_client)
        mcp = FastMCP("test")
        stub_tool = lambda name, desc: mcp.tool(name=name, description=desc)  # noqa: E731
        register_code_tools(stub_tool)
        tool = next(
            t for t in mcp._tool_manager.list_tools() if t.name == "palace.code.manage_adr"
        )
        result = await tool.run(arguments={})
        assert "error" in result
        assert "palace.memory" in result["error"]
        _set(None)
