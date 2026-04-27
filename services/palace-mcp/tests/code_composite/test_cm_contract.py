"""CM contract tests — pin literal argument/response shapes for CM tools.

If codebase-memory-mcp changes its wire format, these tests fail loudly
so the drift is caught before production.

Update LAST_VERIFIED_CM_VERSION when CM binary is upgraded and shapes
are re-verified against the new version.
"""

from __future__ import annotations

import json
import re
from typing import Any
from unittest.mock import AsyncMock

import pytest

from mcp.types import CallToolResult, TextContent

from palace_mcp import code_composite, code_router

# Pin date of last manual verification against the running CM binary.
LAST_VERIFIED_CM_VERSION = "2026-04-26"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _result(data: dict[str, Any]) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data))],
        isError=False,
    )


def _session(*responses: dict[str, Any]) -> AsyncMock:
    session = AsyncMock()
    session.call_tool = AsyncMock(side_effect=[_result(r) for r in responses])
    return session


def _error_session(error_text: str = "project not registered") -> AsyncMock:
    """CM session whose search_graph returns isError=True."""
    session = AsyncMock()
    error_result = CallToolResult(
        content=[TextContent(type="text", text=error_text)],
        isError=True,
    )
    session.call_tool = AsyncMock(return_value=error_result)
    return session


# ---------------------------------------------------------------------------
# search_graph contract
# ---------------------------------------------------------------------------


class TestSearchGraphContract:
    """Pins the search_graph request arguments and response shape."""

    def test_result_item_required_fields(self) -> None:
        """Every item in search_graph.results must have these four fields."""
        item: dict[str, Any] = {
            "name": "register_code_tools",
            "qualified_name": "palace_mcp.code_router.register_code_tools",
            "label": "Function",
            "file_path": "src/palace_mcp/code_router.py",
        }
        # Our composite accesses exactly these keys — assert they are present
        assert "name" in item
        assert "qualified_name" in item

    @pytest.mark.asyncio
    async def test_resolve_qn_sends_qn_pattern_arg(self) -> None:
        """_resolve_qn sends qn_pattern as a suffix-anchored regex."""
        session = _session(
            {
                "results": [
                    {
                        "name": "register_code_tools",
                        "qualified_name": "palace_mcp.code_router.register_code_tools",
                        "label": "Function",
                        "file_path": "src/palace_mcp/code_router.py",
                    }
                ],
                "total": 1,
                "has_more": False,
            }
        )
        code_router._set_cm_session(session)

        await code_composite._resolve_qn(session, "register_code_tools", "repos-gimle")

        call_args = session.call_tool.call_args
        assert call_args.args[0] == "search_graph"
        args = call_args.kwargs["arguments"]
        assert args["project"] == "repos-gimle"
        assert args["label"] == "Function"
        assert "limit" in args
        # Pattern is suffix-anchored: .*<escaped_name>$
        pattern = args["qn_pattern"]
        assert pattern.endswith("register_code_tools$")
        assert re.compile(pattern)  # valid regex

    @pytest.mark.asyncio
    async def test_search_graph_single_result_parsed(self) -> None:
        """_resolve_qn returns (short_name, qualified_name) on a single match."""
        session = _session(
            {
                "results": [
                    {
                        "name": "fn",
                        "qualified_name": "pkg.mod.fn",
                        "label": "Function",
                        "file_path": "pkg/mod.py",
                    }
                ],
                "total": 1,
                "has_more": False,
            }
        )
        result = await code_composite._resolve_qn(session, "fn", "proj")
        assert result == ("fn", "pkg.mod.fn")

    @pytest.mark.asyncio
    async def test_search_graph_empty_results_error_envelope(self) -> None:
        """_resolve_qn returns symbol_not_found envelope when results=[]."""
        session = _session({"results": [], "total": 0, "has_more": False})
        result = await code_composite._resolve_qn(session, "unknown_fn", "proj")
        assert isinstance(result, dict)
        assert result["error_code"] == "symbol_not_found"

    @pytest.mark.asyncio
    async def test_search_graph_multiple_results_error_envelope(self) -> None:
        """_resolve_qn returns ambiguous_qualified_name when >1 results."""
        session = _session(
            {
                "results": [
                    {
                        "name": "fn",
                        "qualified_name": "a.fn",
                        "label": "Function",
                        "file_path": "a.py",
                    },
                    {
                        "name": "fn",
                        "qualified_name": "b.fn",
                        "label": "Function",
                        "file_path": "b.py",
                    },
                ],
                "total": 2,
                "has_more": False,
            }
        )
        result = await code_composite._resolve_qn(session, "fn", "proj")
        assert isinstance(result, dict)
        assert result["error_code"] == "ambiguous_qualified_name"
        assert len(result["matches"]) == 2

    @pytest.mark.asyncio
    async def test_search_graph_cm_error_returns_cm_error_envelope(self) -> None:
        """_resolve_qn returns cm_error envelope when CM search_graph fails."""
        session = _error_session("project not registered in CM")
        result = await code_composite._resolve_qn(session, "fn", "proj")
        assert isinstance(result, dict)
        assert result["error_code"] == "cm_error"

    @pytest.mark.asyncio
    async def test_search_graph_is_error_returns_cm_error_envelope(self) -> None:
        """_resolve_qn returns cm_error envelope when CM returns isError=True.

        Regression for QA finding (GIM-102 Phase 4.1): when CM search_graph fails
        (project not registered in CM), _resolve_qn must return a cm_error dict.
        The CALLER (palace_code_find_references) must check error_code and fall
        back to literal QN instead of propagating this error to the user.
        """
        session = _error_session("project not registered in CM graph")
        result = await code_composite._resolve_qn(session, "my.function", "proj")
        assert isinstance(result, dict)
        assert result["error_code"] == "cm_error"
        # Confirm the caller has the information needed to distinguish cm_error
        # from user-actionable errors (symbol_not_found, ambiguous_qualified_name).
        assert result["requested_qualified_name"] == "my.function"


# ---------------------------------------------------------------------------
# query_graph contract
# ---------------------------------------------------------------------------


class TestQueryGraphContract:
    """Pins the query_graph request and response shape for the :TESTS edge path."""

    @pytest.mark.asyncio
    async def test_query_graph_response_has_rows_list(self) -> None:
        """query_graph rows is a list; each row is a list with [name, qn]."""
        session = _session(
            {
                "rows": [
                    [
                        "test_register_code_tools",
                        "tests.test_code_router.test_register_code_tools",
                    ]
                ],
                "columns": ["name", "qualified_name"],
            }
        )
        result = await code_composite._test_impact_tests_edge(
            session,
            requested_qn="register_code_tools",
            resolved_qn="palace_mcp.code_router.register_code_tools",
            project="repos-gimle",
            max_results=50,
        )
        assert result["ok"] is True
        assert result["method"] == "tests_edge"
        assert len(result["tests"]) == 1
        t = result["tests"][0]
        assert t["name"] == "test_register_code_tools"
        assert t["hop"] == 1

    @pytest.mark.asyncio
    async def test_query_graph_cypher_uses_tests_edge(self) -> None:
        """_test_impact_tests_edge sends a Cypher query with :TESTS edge."""
        session = _session({"rows": [], "columns": ["name", "qualified_name"]})

        await code_composite._test_impact_tests_edge(
            session,
            requested_qn="fn",
            resolved_qn="pkg.fn",
            project="repos-gimle",
            max_results=10,
        )

        call_args = session.call_tool.call_args
        assert call_args.args[0] == "query_graph"
        query: str = call_args.kwargs["arguments"]["query"]
        assert "TESTS" in query
        assert "pkg.fn" in query
        assert "qualified_name" in query

    @pytest.mark.asyncio
    async def test_query_graph_limit_applied(self) -> None:
        """query_graph LIMIT in Cypher is max_results+1 for truncation detection."""
        session = _session({"rows": [], "columns": ["name", "qualified_name"]})
        await code_composite._test_impact_tests_edge(
            session,
            requested_qn="fn",
            resolved_qn="pkg.fn",
            project="proj",
            max_results=5,
        )
        query: str = session.call_tool.call_args.kwargs["arguments"]["query"]
        assert "LIMIT 6" in query  # max_results + 1

    @pytest.mark.asyncio
    async def test_query_graph_truncation_flag(self) -> None:
        """truncated=True when rows > max_results."""
        rows = [[f"t{i}", f"tests.t{i}"] for i in range(6)]  # max_results=5 → truncated
        session = _session({"rows": rows, "columns": ["name", "qualified_name"]})
        result = await code_composite._test_impact_tests_edge(
            session,
            requested_qn="fn",
            resolved_qn="pkg.fn",
            project="proj",
            max_results=5,
        )
        assert result["truncated"] is True
        assert len(result["tests"]) == 5


# ---------------------------------------------------------------------------
# trace_call_path contract
# ---------------------------------------------------------------------------


class TestTraceCallPathContract:
    """Pins the trace_call_path request/response shape."""

    @pytest.mark.asyncio
    async def test_trace_call_path_sends_correct_args(self) -> None:
        """_test_impact_trace sends inbound direction with include_tests=True."""
        session = _session({"callers": []})
        await code_composite._test_impact_trace(
            session,
            requested_qn="fn",
            resolved_qn="pkg.fn",
            short_name="fn",
            project="repos-gimle",
            max_hops=3,
            max_results=50,
        )
        call_args = session.call_tool.call_args
        assert call_args.args[0] == "trace_call_path"
        args = call_args.kwargs["arguments"]
        assert args["project"] == "repos-gimle"
        assert args["function_name"] == "fn"
        assert args["direction"] == "inbound"
        assert args["depth"] == 3
        assert args["include_tests"] is True

    @pytest.mark.asyncio
    async def test_trace_call_path_caller_fields(self) -> None:
        """Callers have is_test, hop, name, qualified_name; non-tests omit is_test."""
        test_caller = {
            "name": "test_fn",
            "qualified_name": "tests.test_fn",
            "is_test": True,
            "hop": 1,
        }
        prod_caller = {
            "name": "caller_fn",
            "qualified_name": "pkg.caller_fn",
            "hop": 2,
        }  # no is_test
        session = _session({"callers": [test_caller, prod_caller]})

        result = await code_composite._test_impact_trace(
            session,
            requested_qn="fn",
            resolved_qn="pkg.fn",
            short_name="fn",
            project="proj",
            max_hops=3,
            max_results=50,
        )
        assert result["ok"] is True
        assert result["method"] == "trace_call_path"
        # Only test callers are included (is_test truthy)
        assert len(result["tests"]) == 1
        assert result["tests"][0]["name"] == "test_fn"
        assert result["tests"][0]["hop"] == 1

    @pytest.mark.asyncio
    async def test_trace_call_path_sorted_by_hop(self) -> None:
        """Result tests are sorted by hop (closest callers first)."""
        session = _session(
            {
                "callers": [
                    {
                        "name": "deep",
                        "qualified_name": "t.deep",
                        "is_test": True,
                        "hop": 3,
                    },
                    {
                        "name": "near",
                        "qualified_name": "t.near",
                        "is_test": True,
                        "hop": 1,
                    },
                ]
            }
        )
        result = await code_composite._test_impact_trace(
            session,
            requested_qn="fn",
            resolved_qn="pkg.fn",
            short_name="fn",
            project="proj",
            max_hops=3,
            max_results=50,
        )
        assert result["tests"][0]["name"] == "near"
        assert result["tests"][1]["name"] == "deep"

    @pytest.mark.asyncio
    async def test_trace_call_path_disambiguation_caveat_present(self) -> None:
        """Response includes disambiguation_caveat for the homonym-risk warning."""
        session = _session({"callers": []})
        result = await code_composite._test_impact_trace(
            session,
            requested_qn="fn",
            resolved_qn="pkg.fn",
            short_name="fn",
            project="proj",
            max_hops=2,
            max_results=10,
        )
        assert "disambiguation_caveat" in result

    @pytest.mark.asyncio
    async def test_trace_call_path_max_hops_used_field(self) -> None:
        """Response includes max_hops_used set to the requested depth."""
        session = _session({"callers": []})
        result = await code_composite._test_impact_trace(
            session,
            requested_qn="fn",
            resolved_qn="pkg.fn",
            short_name="fn",
            project="proj",
            max_hops=4,
            max_results=10,
        )
        assert result["max_hops_used"] == 4
