"""Unit tests for code_composite.py — palace.code.test_impact."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp.types import CallToolResult, TextContent

from palace_mcp.code_composite import _cm_project_to_slug, _slug_to_cm_project


# ---------------------------------------------------------------------------
# Slug ↔ CM project name translation (GIM-122)
# ---------------------------------------------------------------------------


class TestSlugToCmProject:
    """Boundary translation: operator-facing slug → CM-internal project name.

    palace-mcp public API uses slugs ('gimle'); codebase-memory-mcp keys
    projects by mount-path-derived names ('/repos/gimle' → 'repos-gimle').
    Without this translation `palace.code.test_impact project='gimle'`
    returns cm_error because CM doesn't know 'gimle'.
    """

    def test_operator_slug_gets_repos_prefix(self) -> None:
        assert _slug_to_cm_project("gimle") == "repos-gimle"

    def test_already_cm_name_passthrough(self) -> None:
        # Idempotent on already-translated names so the config default
        # (palace_cm_default_project='repos-gimle') round-trips safely.
        assert _slug_to_cm_project("repos-gimle") == "repos-gimle"

    def test_non_repos_prefix_still_translates(self) -> None:
        # Non-`repos-` slugs get the prefix even though the convention
        # currently only has /repos/* mounts. Keep behaviour predictable
        # rather than try to detect "looks already-mapped" heuristically.
        assert _slug_to_cm_project("medic") == "repos-medic"


class TestCmProjectToSlug:
    """Inverse of _slug_to_cm_project — strips the 'repos-' prefix.

    Ensures Neo4j-side queries (IngestRun.project, etc.) see the operator
    slug regardless of whether the default came from CM-form config or the
    user passed an already-translated CM name by mistake (GIM-123).
    """

    def test_repos_prefix_stripped(self) -> None:
        assert _cm_project_to_slug("repos-gimle") == "gimle"

    def test_plain_slug_passthrough(self) -> None:
        # Idempotent — operator slug unchanged.
        assert _cm_project_to_slug("gimle") == "gimle"

    def test_round_trip(self) -> None:
        # _cm_project_to_slug ∘ _slug_to_cm_project = identity on slugs.
        assert _cm_project_to_slug(_slug_to_cm_project("gimle")) == "gimle"
        assert _cm_project_to_slug(_slug_to_cm_project("medic")) == "medic"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(data: dict[str, Any]) -> CallToolResult:
    """Create a fake CallToolResult with JSON text content."""
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data))],
        isError=False,
    )


def _make_structured_result(data: dict[str, Any]) -> CallToolResult:
    """Create a fake CallToolResult with structuredContent."""
    return CallToolResult(
        content=[],
        isError=False,
        structuredContent=data,
    )


# ---------------------------------------------------------------------------
# Step 1 — TestImpactRequest validation
# ---------------------------------------------------------------------------


class TestTestImpactRequestValidation:
    def test_valid_simple_name(self) -> None:
        from palace_mcp.code_composite import TestImpactRequest

        req = TestImpactRequest(qualified_name="my_function")
        assert req.qualified_name == "my_function"

    def test_valid_dotted_name(self) -> None:
        from palace_mcp.code_composite import TestImpactRequest

        req = TestImpactRequest(qualified_name="module.submodule.func")
        assert req.qualified_name == "module.submodule.func"

    def test_valid_slug_with_hyphens(self) -> None:
        from palace_mcp.code_composite import TestImpactRequest

        req = TestImpactRequest(
            qualified_name="repos-gimle.services.palace-mcp.src.palace_mcp.code_router.fn"
        )
        assert req.qualified_name.startswith("repos-gimle")

    def test_rejects_empty_string(self) -> None:
        from pydantic import ValidationError

        from palace_mcp.code_composite import TestImpactRequest

        with pytest.raises(ValidationError):
            TestImpactRequest(qualified_name="")

    def test_rejects_leading_digit(self) -> None:
        from pydantic import ValidationError

        from palace_mcp.code_composite import TestImpactRequest

        with pytest.raises(ValidationError):
            TestImpactRequest(qualified_name="0bad_name")

    def test_rejects_spaces(self) -> None:
        from pydantic import ValidationError

        from palace_mcp.code_composite import TestImpactRequest

        with pytest.raises(ValidationError):
            TestImpactRequest(qualified_name="bad name with spaces")

    def test_rejects_max_hops_too_large(self) -> None:
        from pydantic import ValidationError

        from palace_mcp.code_composite import TestImpactRequest

        with pytest.raises(ValidationError):
            TestImpactRequest(qualified_name="fn", max_hops=10)

    def test_rejects_max_results_zero(self) -> None:
        from pydantic import ValidationError

        from palace_mcp.code_composite import TestImpactRequest

        with pytest.raises(ValidationError):
            TestImpactRequest(qualified_name="fn", max_results=0)

    def test_defaults(self) -> None:
        from palace_mcp.code_composite import TestImpactRequest

        req = TestImpactRequest(qualified_name="fn")
        assert req.max_hops == 3
        assert req.max_results == 50
        assert req.include_indirect is False
        assert req.project is None


# ---------------------------------------------------------------------------
# Step 1 — parse_cm_result helper
# ---------------------------------------------------------------------------


class TestParseCmResult:
    def test_structured_content_returned_as_dict(self) -> None:
        from palace_mcp.code_router import parse_cm_result

        result = _make_structured_result({"total": 1, "results": []})
        data = parse_cm_result(result)
        assert data == {"total": 1, "results": []}

    def test_json_text_dict_returned_directly(self) -> None:
        from palace_mcp.code_router import parse_cm_result

        result = _make_result({"rows": [["a", "b"]], "columns": ["x", "y"]})
        data = parse_cm_result(result)
        assert data["rows"] == [["a", "b"]]

    def test_json_text_non_dict_wrapped(self) -> None:
        from palace_mcp.code_router import parse_cm_result

        result = CallToolResult(
            content=[TextContent(type="text", text="[1, 2, 3]")],
            isError=False,
        )
        data = parse_cm_result(result)
        # Non-dict JSON — wrapped under a key
        assert isinstance(data, dict)
        assert len(data) == 1

    def test_non_json_text_wrapped(self) -> None:
        from palace_mcp.code_router import parse_cm_result

        result = CallToolResult(
            content=[TextContent(type="text", text="not json at all")],
            isError=False,
        )
        data = parse_cm_result(result)
        assert isinstance(data, dict)
        assert len(data) == 1

    def test_empty_content_returns_empty_dict(self) -> None:
        from palace_mcp.code_router import parse_cm_result

        result = CallToolResult(content=[], isError=False)
        assert parse_cm_result(result) == {}


# ---------------------------------------------------------------------------
# Step 1 — get_cm_session accessor
# ---------------------------------------------------------------------------


class TestGetCmSession:
    def test_returns_none_when_not_started(self) -> None:
        from palace_mcp import code_router
        from palace_mcp.code_router import get_cm_session

        original = code_router._cm_session
        code_router._cm_session = None
        try:
            assert get_cm_session() is None
        finally:
            code_router._cm_session = original

    def test_returns_session_when_set(self) -> None:
        from palace_mcp import code_router
        from palace_mcp.code_router import get_cm_session

        original = code_router._cm_session
        fake_session = AsyncMock()
        code_router._cm_session = fake_session  # type: ignore[assignment]
        try:
            assert get_cm_session() is fake_session
        finally:
            code_router._cm_session = original


# ---------------------------------------------------------------------------
# Step 2 — default path: _resolve_qn + _test_impact_tests_edge
# ---------------------------------------------------------------------------


def _fake_session(*call_tool_responses: dict[str, Any]) -> AsyncMock:
    """Build an AsyncMock ClientSession with sequential call_tool responses."""
    session = AsyncMock()
    session.call_tool = AsyncMock(
        side_effect=[_make_result(r) for r in call_tool_responses]
    )
    return session


class TestResolvQn:
    @pytest.mark.asyncio
    async def test_symbol_not_found(self) -> None:
        from palace_mcp.code_composite import _resolve_qn

        session = _fake_session(
            {"total": 0, "results": [], "has_more": False},
            {"rows": []},
        )
        result = await _resolve_qn(session, "nonexistent_fn", "repos-gimle")
        assert isinstance(result, dict)
        assert result["ok"] is False
        assert result["error_code"] == "symbol_not_found"
        assert result["requested_qualified_name"] == "nonexistent_fn"

    @pytest.mark.asyncio
    async def test_ambiguous_exact_count(self) -> None:
        from palace_mcp.code_composite import _resolve_qn

        results = [
            {"name": f"fn{i}", "qualified_name": f"mod.fn{i}", "file_path": "f.py"}
            for i in range(3)
        ]
        session = _fake_session({"total": 3, "results": results, "has_more": False})
        result = await _resolve_qn(session, "fn", "repos-gimle")
        assert isinstance(result, dict)
        assert result["error_code"] == "ambiguous_qualified_name"
        assert "3" in result["message"]
        assert len(result["matches"]) == 3

    @pytest.mark.asyncio
    async def test_ambiguous_lower_bound(self) -> None:
        from palace_mcp.code_composite import _resolve_qn

        results = [
            {"name": f"fn{i}", "qualified_name": f"mod.fn{i}", "file_path": "f.py"}
            for i in range(10)
        ]
        session = _fake_session({"total": 10, "results": results, "has_more": True})
        result = await _resolve_qn(session, "fn", "repos-gimle")
        assert isinstance(result, dict)
        assert "at least 10" in result["message"]

    @pytest.mark.asyncio
    async def test_happy_path_returns_tuple(self) -> None:
        from palace_mcp.code_composite import _resolve_qn

        session = _fake_session(
            {
                "total": 1,
                "results": [
                    {
                        "name": "my_fn",
                        "qualified_name": "mod.sub.my_fn",
                        "file_path": "f.py",
                    }
                ],
                "has_more": False,
            }
        )
        result = await _resolve_qn(session, "my_fn", "repos-gimle")
        assert result == ("my_fn", "mod.sub.my_fn")


class TestDefaultPath:
    @pytest.mark.asyncio
    async def test_happy_path_tests_edge(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(
            side_effect=[
                _make_result(
                    {  # search_graph
                        "total": 1,
                        "has_more": False,
                        "results": [
                            {
                                "name": "decide",
                                "qualified_name": "mod.decide",
                                "file_path": "f.py",
                            }
                        ],
                    }
                ),
                _make_result(
                    {  # query_graph
                        "columns": ["name", "qualified_name"],
                        "rows": [["test_a", "mod.test_a"], ["test_b", "mod.test_b"]],
                        "total": 2,
                    }
                ),
            ]
        )
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool(
            "palace.code.test_impact",
            {
                "qualified_name": "decide",
            },
        )
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is True
        assert payload["method"] == "tests_edge"
        assert len(payload["tests"]) == 2
        assert all(t["hop"] == 1 for t in payload["tests"])
        assert "disambiguation_caveat" not in payload
        assert payload["requested_qualified_name"] == "decide"
        assert payload["qualified_name"] == "mod.decide"

    @pytest.mark.asyncio
    async def test_short_name_fallback_normalizes_cm_project_for_neo4j(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from mcp.server.fastmcp import FastMCP

        from palace_mcp.code_composite import register_code_composite_tools

        fake_session = _fake_session({"total": 0, "results": [], "has_more": False})
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        query_mock = AsyncMock(
            return_value=[
                {
                    "name": "BalanceData",
                    "short_name": "BalanceData",
                    "qualified_name": "WalletKit.BalanceData",
                    "file_path": "WalletKit.swift",
                    "symbol": "",
                }
            ]
        )
        monkeypatch.setattr(
            "palace_mcp.code_composite._query_symbol_candidates", query_mock
        )
        monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: object())
        tests_edge = AsyncMock(
            return_value={
                "ok": True,
                "method": "tests_edge",
                "requested_qualified_name": "BalanceData",
                "qualified_name": "WalletKit.BalanceData",
                "tests": [],
                "total_found": 0,
                "truncated": False,
            }
        )
        monkeypatch.setattr(
            "palace_mcp.code_composite._test_impact_tests_edge", tests_edge
        )

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool(
            "palace.code.test_impact",
            {
                "qualified_name": "BalanceData",
                "project": "uw-ios-app",
            },
        )

        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is True
        assert payload["qualified_name"] == "WalletKit.BalanceData"
        assert query_mock.await_args_list[0].kwargs["group_id"] == "project/uw-ios-app"
        tests_edge.assert_awaited_once_with(
            fake_session,
            requested_qn="BalanceData",
            resolved_qn="WalletKit.BalanceData",
            project="repos-uw-ios-app",
            max_results=50,
        )

    @pytest.mark.asyncio
    async def test_truncation_tests_edge(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        max_results = 3
        rows = [[f"test_{i}", f"mod.test_{i}"] for i in range(max_results + 1)]
        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(
            side_effect=[
                _make_result(
                    {
                        "total": 1,
                        "has_more": False,
                        "results": [
                            {
                                "name": "fn",
                                "qualified_name": "mod.fn",
                                "file_path": "f.py",
                            }
                        ],
                    }
                ),
                _make_result(
                    {
                        "columns": ["name", "qualified_name"],
                        "rows": rows,
                        "total": len(rows),
                    }
                ),
            ]
        )
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool(
            "palace.code.test_impact",
            {
                "qualified_name": "fn",
                "max_results": max_results,
            },
        )
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["truncated"] is True
        assert len(payload["tests"]) == max_results
        assert payload["total_found"] == max_results + 1

    @pytest.mark.asyncio
    async def test_duplicate_tests_edge_rows_are_collapsed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(
            side_effect=[
                _make_result(
                    {
                        "total": 1,
                        "has_more": False,
                        "results": [
                            {
                                "name": "fn",
                                "qualified_name": "mod.fn",
                                "file_path": "f.py",
                            }
                        ],
                    }
                ),
                _make_result(
                    {
                        "columns": ["name", "qualified_name"],
                        "rows": [
                            ["test_a", "mod.test_a"],
                            ["test_a", "mod.test_a"],
                            ["test_b", "mod.test_b"],
                        ],
                        "total": 3,
                    }
                ),
            ]
        )
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool(
            "palace.code.test_impact",
            {
                "qualified_name": "fn",
            },
        )
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert [test["qualified_name"] for test in payload["tests"]] == [
            "mod.test_a",
            "mod.test_b",
        ]
        assert payload["total_found"] == 2

    @pytest.mark.asyncio
    async def test_empty_result_tests_edge(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(
            side_effect=[
                _make_result(
                    {
                        "total": 1,
                        "has_more": False,
                        "results": [
                            {
                                "name": "fn",
                                "qualified_name": "mod.fn",
                                "file_path": "f.py",
                            }
                        ],
                    }
                ),
                _make_result(
                    {"columns": ["name", "qualified_name"], "rows": [], "total": 0}
                ),
            ]
        )
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool(
            "palace.code.test_impact", {"qualified_name": "fn"}
        )
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is True
        assert payload["tests"] == []
        assert payload["total_found"] == 0

    @pytest.mark.asyncio
    async def test_symbol_not_found_echoes_requested_qn(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(
            side_effect=[
                _make_result({"total": 0, "results": [], "has_more": False}),
                _make_result({"rows": []}),
            ]
        )
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool(
            "palace.code.test_impact", {"qualified_name": "my_suffix"}
        )
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is False
        assert payload["error_code"] == "symbol_not_found"
        assert payload["requested_qualified_name"] == "my_suffix"

    @pytest.mark.asyncio
    async def test_validation_error_echoes_requested_qn(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: AsyncMock()
        )

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool(
            "palace.code.test_impact", {"qualified_name": "bad name"}
        )
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is False
        assert payload["error_code"] == "validation_error"
        assert payload["requested_qualified_name"] == "bad name"

    @pytest.mark.asyncio
    async def test_resolved_qn_echo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Short suffix input → output qualified_name is the resolved long QN."""
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        long_qn = "repos-gimle.services.palace-mcp.src.palace_mcp.code_router.register_code_tools"
        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(
            side_effect=[
                _make_result(
                    {
                        "total": 1,
                        "has_more": False,
                        "results": [
                            {
                                "name": "register_code_tools",
                                "qualified_name": long_qn,
                                "file_path": "f.py",
                            }
                        ],
                    }
                ),
                _make_result(
                    {"columns": ["name", "qualified_name"], "rows": [], "total": 0}
                ),
            ]
        )
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool(
            "palace.code.test_impact", {"qualified_name": "register_code_tools"}
        )
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["requested_qualified_name"] == "register_code_tools"
        assert payload["qualified_name"] == long_qn


# ---------------------------------------------------------------------------
# Step 3 — opt-in path: _test_impact_trace
# ---------------------------------------------------------------------------


def _make_search_one(short_name: str, qn: str) -> dict[str, Any]:
    return {
        "total": 1,
        "has_more": False,
        "results": [{"name": short_name, "qualified_name": qn, "file_path": "f.py"}],
    }


class TestOptInPath:
    @pytest.mark.asyncio
    async def test_happy_path_trace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(
            side_effect=[
                _make_result(_make_search_one("fn", "mod.fn")),
                _make_result(
                    {
                        "function": "fn",
                        "direction": "inbound",
                        "callers": [
                            {
                                "name": "test_x",
                                "qualified_name": "t.test_x",
                                "hop": 1,
                                "is_test": True,
                            },
                            {"name": "_cli", "qualified_name": "m._cli", "hop": 2},
                            {
                                "name": "test_y",
                                "qualified_name": "t.test_y",
                                "hop": 2,
                                "is_test": True,
                            },
                        ],
                    }
                ),
            ]
        )
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool(
            "palace.code.test_impact",
            {
                "qualified_name": "fn",
                "include_indirect": True,
                "max_hops": 3,
            },
        )
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is True
        assert payload["method"] == "trace_call_path"
        assert (
            payload["disambiguation_caveat"]
            == "trace uses short-name; collisions possible"
        )
        assert payload["max_hops_used"] == 3
        # only is_test callers, sorted by hop
        assert len(payload["tests"]) == 2
        assert payload["tests"][0]["hop"] == 1
        assert payload["tests"][1]["hop"] == 2
        assert payload["total_found"] == 2

    @pytest.mark.asyncio
    async def test_trace_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(
            side_effect=[
                _make_result(_make_search_one("fn", "mod.fn")),
                _make_result({"function": "fn", "direction": "inbound", "callers": []}),
            ]
        )
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool(
            "palace.code.test_impact",
            {
                "qualified_name": "fn",
                "include_indirect": True,
            },
        )
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is True
        assert payload["tests"] == []
        assert (
            payload["disambiguation_caveat"]
            == "trace uses short-name; collisions possible"
        )

    @pytest.mark.asyncio
    async def test_trace_truncation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        max_results = 3
        test_callers = [
            {
                "name": f"test_{i}",
                "qualified_name": f"t.test_{i}",
                "hop": 1,
                "is_test": True,
            }
            for i in range(7)
        ]
        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(
            side_effect=[
                _make_result(_make_search_one("fn", "mod.fn")),
                _make_result(
                    {"function": "fn", "direction": "inbound", "callers": test_callers}
                ),
            ]
        )
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool(
            "palace.code.test_impact",
            {
                "qualified_name": "fn",
                "include_indirect": True,
                "max_results": max_results,
            },
        )
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["truncated"] is True
        assert len(payload["tests"]) == max_results
        assert payload["total_found"] == 7  # exact, before truncation

    @pytest.mark.asyncio
    async def test_duplicate_trace_callers_are_collapsed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(
            side_effect=[
                _make_result(_make_search_one("fn", "mod.fn")),
                _make_result(
                    {
                        "function": "fn",
                        "direction": "inbound",
                        "callers": [
                            {
                                "name": "test_dup_far",
                                "qualified_name": "t.test_dup",
                                "hop": 3,
                                "is_test": True,
                            },
                            {
                                "name": "test_dup_near",
                                "qualified_name": "t.test_dup",
                                "hop": 1,
                                "is_test": True,
                            },
                            {
                                "name": "test_other",
                                "qualified_name": "t.test_other",
                                "hop": 2,
                                "is_test": True,
                            },
                        ],
                    }
                ),
            ]
        )
        monkeypatch.setattr(
            "palace_mcp.code_router.get_cm_session", lambda: fake_session
        )

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool(
            "palace.code.test_impact",
            {
                "qualified_name": "fn",
                "include_indirect": True,
            },
        )
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert [(test["qualified_name"], test["hop"]) for test in payload["tests"]] == [
            ("t.test_dup", 1),
            ("t.test_other", 2),
        ]
        assert payload["total_found"] == 2

    @pytest.mark.asyncio
    async def test_infrastructure_failure_when_session_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When CM session is None for exact-only lookups, handle_tool_error raises."""
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        monkeypatch.setattr("palace_mcp.code_router.get_cm_session", lambda: None)

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        with pytest.raises(Exception):
            await mcp.call_tool("palace.code.test_impact", {"qualified_name": "pkg.fn"})

    @pytest.mark.asyncio
    async def test_short_name_resolution_still_fails_cleanly_without_cm_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Short-name fallback must still surface the CM-not-started tool error."""
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        async def fake_query_symbol_candidates(
            driver: Any, query: str, **params: Any
        ) -> list[dict[str, Any]]:
            return [
                {
                    "name": "BalanceData",
                    "short_name": "BalanceData",
                    "symbol": "",
                    "qualified_name": "WalletKit.BalanceData",
                    "file_path": "WalletKit.swift",
                }
            ]

        monkeypatch.setattr("palace_mcp.code_router.get_cm_session", lambda: None)
        monkeypatch.setattr(
            "palace_mcp.code_composite._query_symbol_candidates",
            fake_query_symbol_candidates,
        )
        monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: object())

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        with pytest.raises(Exception) as excinfo:
            await mcp.call_tool(
                "palace.code.test_impact",
                {"qualified_name": "BalanceData", "project": "uw-ios-app"},
            )
        assert excinfo.type is not AssertionError


# ---------------------------------------------------------------------------
# Step 4 — registration wiring + config
# ---------------------------------------------------------------------------


class TestRegistrationWiring:
    def test_test_impact_appears_exactly_once(self) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        tracked: list[str] = []

        def dedup_tool(name: str, description: str) -> Any:
            assert name not in tracked, f"Tool {name} registered twice"
            tracked.append(name)
            return FastMCP("inner").tool(name=name, description=description)

        register_code_composite_tools(dedup_tool, default_project="repos-gimle")
        assert "palace.code.test_impact" in tracked
        assert tracked.count("palace.code.test_impact") == 1

    def test_cm_default_project_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import importlib

        monkeypatch.setenv("PALACE_CM_DEFAULT_PROJECT", "repos-custom")
        monkeypatch.setenv("NEO4J_PASSWORD", "test")
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        import palace_mcp.config as cfg_module

        importlib.reload(cfg_module)
        settings = cfg_module.Settings()  # type: ignore[call-arg]
        assert settings.palace_cm_default_project == "repos-custom"

    def test_cm_default_project_default_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import importlib

        monkeypatch.delenv("PALACE_CM_DEFAULT_PROJECT", raising=False)
        monkeypatch.setenv("NEO4J_PASSWORD", "test")
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        import palace_mcp.config as cfg_module

        importlib.reload(cfg_module)
        settings = cfg_module.Settings()  # type: ignore[call-arg]
        assert settings.palace_cm_default_project == "repos-gimle"


# ---------------------------------------------------------------------------
# Step 5 — palace.code.call_hierarchy MCP tool registration (GIM-1175)
# ---------------------------------------------------------------------------


class _FakeSettings:
    palace_indexstore_paths: dict[str, str] = {"uw-ios-app": "/path/to/DataStore"}
    palace_sourcekit_index_store_path: str | None = None
    palace_call_hierarchy_timeout_s: float = 30.0


_FAKE_CALLER = {
    "source_file": "BalanceView.swift",
    "record_name": "BalanceView",
    "symbol_name": "updateBalance",
    "symbol_usr": "s:9WalletKit11BalanceViewC13updateBalanceyyF",
    "line": 42,
    "col": 5,
    "roles": ["call"],
}

_FAKE_CALL_HIERARCHY_OK = {
    "ok": True,
    "qualified_name": "BalanceData",
    "short_name": "BalanceData",
    "project": "uw-ios-app",
    "index_store_path": "/path/to/DataStore",
    "caller_count": 1,
    "callers": [_FAKE_CALLER],
    "latency_s": 0.123,
    "approach": "indexstore_direct",
}


class TestCallHierarchyRegistration:
    def test_call_hierarchy_registered(self) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        tracked: list[str] = []

        def spy_tool(name: str, description: str) -> Any:
            tracked.append(name)
            return FastMCP("inner").tool(name=name, description=description)

        register_code_composite_tools(spy_tool, default_project="repos-gimle")
        assert "palace.code.call_hierarchy" in tracked
        assert tracked.count("palace.code.call_hierarchy") == 1


class TestCallHierarchyTool:
    @pytest.fixture(autouse=True)
    def _reset_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Disable the module-level hydration cache for every test in this class.

        GIM-1181 added a cache layer to palace.code.call_hierarchy. Without
        this fixture, an ok=True result from one test populates the global
        cache and later tests in the same run get a cache hit — bypassing the
        monkeypatched call_hierarchy_tool and breaking assertions on kwargs.
        """
        monkeypatch.setattr("palace_mcp.cache._cache", None)

    @pytest.mark.asyncio
    async def test_happy_path_returns_callers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        monkeypatch.setattr(
            "palace_mcp.code.call_hierarchy.call_hierarchy_tool",
            lambda **kwargs: _FAKE_CALL_HIERARCHY_OK,
        )
        monkeypatch.setattr(
            "palace_mcp.mcp_server.get_settings", lambda: _FakeSettings()
        )

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool(
            "palace.code.call_hierarchy",
            {"qualified_name": "BalanceData", "project": "uw-ios-app"},
        )
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is True
        assert payload["caller_count"] == 1
        assert len(payload["callers"]) == 1
        assert payload["callers"][0]["source_file"] == "BalanceView.swift"

    @pytest.mark.asyncio
    async def test_passes_settings_paths_to_tool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        received: dict[str, Any] = {}

        def capture(**kwargs: Any) -> dict[str, Any]:
            received.update(kwargs)
            return _FAKE_CALL_HIERARCHY_OK

        monkeypatch.setattr(
            "palace_mcp.code.call_hierarchy.call_hierarchy_tool", capture
        )
        monkeypatch.setattr(
            "palace_mcp.mcp_server.get_settings", lambda: _FakeSettings()
        )

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        await mcp.call_tool(
            "palace.code.call_hierarchy",
            {"qualified_name": "BalanceData", "project": "uw-ios-app"},
        )
        assert received["indexstore_paths"] == {"uw-ios-app": "/path/to/DataStore"}
        assert received["default_store_path"] is None
        assert received["timeout_s"] == 30.0
        assert received["project"] == "uw-ios-app"

    @pytest.mark.asyncio
    async def test_validation_error_returns_error_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        monkeypatch.setattr(
            "palace_mcp.mcp_server.get_settings", lambda: _FakeSettings()
        )

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        # 501-char string exceeds max_length=500
        result = await mcp.call_tool(
            "palace.code.call_hierarchy",
            {"qualified_name": "a" * 501},
        )
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is False
        assert payload["error_code"] == "validation_error"
        assert payload["requested_qualified_name"] == "a" * 501

    @pytest.mark.asyncio
    async def test_settings_none_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        monkeypatch.setattr("palace_mcp.mcp_server.get_settings", lambda: None)

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        with pytest.raises(Exception):
            await mcp.call_tool(
                "palace.code.call_hierarchy",
                {"qualified_name": "BalanceData"},
            )

    @pytest.mark.asyncio
    async def test_index_store_error_forwarded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        error_result = {
            "ok": False,
            "error_code": "index_store_not_configured",
            "qualified_name": "BalanceData",
            "project": None,
            "message": "No IndexStore path found.",
        }
        monkeypatch.setattr(
            "palace_mcp.code.call_hierarchy.call_hierarchy_tool",
            lambda **kwargs: error_result,
        )

        class EmptySettings(_FakeSettings):
            palace_indexstore_paths: dict[str, str] = {}
            palace_sourcekit_index_store_path: str | None = None

        monkeypatch.setattr(
            "palace_mcp.mcp_server.get_settings", lambda: EmptySettings()
        )

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool(
            "palace.code.call_hierarchy",
            {"qualified_name": "BalanceData"},
        )
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is False
        assert payload["error_code"] == "index_store_not_configured"
