"""MCP wire-contract test for palace.code.find_references (per GIM-91).

All 3 states must be reachable via real streamablehttp_client.
Requires full palace-mcp running with MCP transport.
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
@pytest.mark.wire
class TestFindReferencesWireContract:
    @pytest.mark.asyncio
    async def test_state_b_never_indexed(self, mcp_client: object) -> None:
        """Query a project that has never been indexed → project_not_indexed."""
        result = await mcp_client.call_tool(  # type: ignore[union-attr]
            "palace.code.find_references",
            arguments={
                "qualified_name": "nonexistent.symbol",
                "project": "never-indexed-project",
            },
        )
        data = mcp_client.parse_result(result)  # type: ignore[union-attr]
        assert data["ok"] is True
        assert data["warning"] == "project_not_indexed"
        assert data["total_found"] == 0
        assert "action_required" in data

    @pytest.mark.asyncio
    async def test_state_a_genuinely_zero_refs(
        self, mcp_client: object, indexed_project: str
    ) -> None:
        """Query a symbol that exists but has no callers → empty, no warning."""
        result = await mcp_client.call_tool(  # type: ignore[union-attr]
            "palace.code.find_references",
            arguments={
                "qualified_name": "isolated_function_no_refs",
                "project": indexed_project,
            },
        )
        data = mcp_client.parse_result(result)  # type: ignore[union-attr]
        assert data["ok"] is True
        assert data["total_found"] == 0
        assert "warning" not in data

    @pytest.mark.asyncio
    async def test_state_c_evicted(
        self, mcp_client: object, evicted_project: str
    ) -> None:
        """Query a symbol with EvictionRecord → partial_index + coverage_pct."""
        result = await mcp_client.call_tool(  # type: ignore[union-attr]
            "palace.code.find_references",
            arguments={
                "qualified_name": "evicted_symbol",
                "project": evicted_project,
            },
        )
        data = mcp_client.parse_result(result)  # type: ignore[union-attr]
        assert data["ok"] is True
        assert data.get("warning") == "partial_index"
        assert "coverage_pct" in data

    @pytest.mark.asyncio
    async def test_dedup_pattern_21(self, mcp_client: object) -> None:
        """palace.code.find_references appears exactly once in tools/list (Pattern #21)."""
        tools = await mcp_client.list_tools()  # type: ignore[union-attr]
        find_refs_tools = [t for t in tools if t.name == "palace.code.find_references"]
        assert len(find_refs_tools) == 1
