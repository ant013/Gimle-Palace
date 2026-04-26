"""Unit tests for code_composite.py — palace.code.test_impact."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp.types import CallToolResult, TextContent


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

        session = _fake_session({"total": 0, "results": [], "has_more": False})
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

        session = _fake_session({
            "total": 1,
            "results": [{"name": "my_fn", "qualified_name": "mod.sub.my_fn", "file_path": "f.py"}],
            "has_more": False,
        })
        result = await _resolve_qn(session, "my_fn", "repos-gimle")
        assert result == ("my_fn", "mod.sub.my_fn")


class TestDefaultPath:
    @pytest.mark.asyncio
    async def test_happy_path_tests_edge(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(side_effect=[
            _make_result({  # search_graph
                "total": 1, "has_more": False,
                "results": [{"name": "decide", "qualified_name": "mod.decide", "file_path": "f.py"}],
            }),
            _make_result({  # query_graph
                "columns": ["name", "qualified_name"],
                "rows": [["test_a", "mod.test_a"], ["test_b", "mod.test_b"]],
                "total": 2,
            }),
        ])
        monkeypatch.setattr("palace_mcp.code_router.get_cm_session", lambda: fake_session)

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool("palace.code.test_impact", {
            "qualified_name": "decide",
        })
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is True
        assert payload["method"] == "tests_edge"
        assert len(payload["tests"]) == 2
        assert all(t["hop"] == 1 for t in payload["tests"])
        assert "disambiguation_caveat" not in payload
        assert payload["requested_qualified_name"] == "decide"
        assert payload["qualified_name"] == "mod.decide"

    @pytest.mark.asyncio
    async def test_truncation_tests_edge(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        max_results = 3
        rows = [[f"test_{i}", f"mod.test_{i}"] for i in range(max_results + 1)]
        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(side_effect=[
            _make_result({
                "total": 1, "has_more": False,
                "results": [{"name": "fn", "qualified_name": "mod.fn", "file_path": "f.py"}],
            }),
            _make_result({"columns": ["name", "qualified_name"], "rows": rows, "total": len(rows)}),
        ])
        monkeypatch.setattr("palace_mcp.code_router.get_cm_session", lambda: fake_session)

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool("palace.code.test_impact", {
            "qualified_name": "fn",
            "max_results": max_results,
        })
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["truncated"] is True
        assert len(payload["tests"]) == max_results
        assert payload["total_found"] == max_results + 1

    @pytest.mark.asyncio
    async def test_empty_result_tests_edge(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(side_effect=[
            _make_result({
                "total": 1, "has_more": False,
                "results": [{"name": "fn", "qualified_name": "mod.fn", "file_path": "f.py"}],
            }),
            _make_result({"columns": ["name", "qualified_name"], "rows": [], "total": 0}),
        ])
        monkeypatch.setattr("palace_mcp.code_router.get_cm_session", lambda: fake_session)

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool("palace.code.test_impact", {"qualified_name": "fn"})
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is True
        assert payload["tests"] == []
        assert payload["total_found"] == 0

    @pytest.mark.asyncio
    async def test_symbol_not_found_echoes_requested_qn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(return_value=_make_result(
            {"total": 0, "results": [], "has_more": False}
        ))
        monkeypatch.setattr("palace_mcp.code_router.get_cm_session", lambda: fake_session)

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool("palace.code.test_impact", {"qualified_name": "my_suffix"})
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is False
        assert payload["error_code"] == "symbol_not_found"
        assert payload["requested_qualified_name"] == "my_suffix"

    @pytest.mark.asyncio
    async def test_validation_error_echoes_requested_qn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        monkeypatch.setattr("palace_mcp.code_router.get_cm_session", lambda: AsyncMock())

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool("palace.code.test_impact", {"qualified_name": "bad name"})
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
        fake_session.call_tool = AsyncMock(side_effect=[
            _make_result({
                "total": 1, "has_more": False,
                "results": [{"name": "register_code_tools", "qualified_name": long_qn, "file_path": "f.py"}],
            }),
            _make_result({"columns": ["name", "qualified_name"], "rows": [], "total": 0}),
        ])
        monkeypatch.setattr("palace_mcp.code_router.get_cm_session", lambda: fake_session)

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool("palace.code.test_impact", {"qualified_name": "register_code_tools"})
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["requested_qualified_name"] == "register_code_tools"
        assert payload["qualified_name"] == long_qn


# ---------------------------------------------------------------------------
# Step 3 — opt-in path: _test_impact_trace
# ---------------------------------------------------------------------------


def _make_search_one(short_name: str, qn: str) -> dict[str, Any]:
    return {
        "total": 1, "has_more": False,
        "results": [{"name": short_name, "qualified_name": qn, "file_path": "f.py"}],
    }


class TestOptInPath:
    @pytest.mark.asyncio
    async def test_happy_path_trace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(side_effect=[
            _make_result(_make_search_one("fn", "mod.fn")),
            _make_result({
                "function": "fn",
                "direction": "inbound",
                "callers": [
                    {"name": "test_x", "qualified_name": "t.test_x", "hop": 1, "is_test": True},
                    {"name": "_cli", "qualified_name": "m._cli", "hop": 2},
                    {"name": "test_y", "qualified_name": "t.test_y", "hop": 2, "is_test": True},
                ],
            }),
        ])
        monkeypatch.setattr("palace_mcp.code_router.get_cm_session", lambda: fake_session)

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool("palace.code.test_impact", {
            "qualified_name": "fn",
            "include_indirect": True,
            "max_hops": 3,
        })
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is True
        assert payload["method"] == "trace_call_path"
        assert payload["disambiguation_caveat"] == "trace uses short-name; collisions possible"
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
        fake_session.call_tool = AsyncMock(side_effect=[
            _make_result(_make_search_one("fn", "mod.fn")),
            _make_result({"function": "fn", "direction": "inbound", "callers": []}),
        ])
        monkeypatch.setattr("palace_mcp.code_router.get_cm_session", lambda: fake_session)

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool("palace.code.test_impact", {
            "qualified_name": "fn",
            "include_indirect": True,
        })
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["ok"] is True
        assert payload["tests"] == []
        assert payload["disambiguation_caveat"] == "trace uses short-name; collisions possible"

    @pytest.mark.asyncio
    async def test_trace_truncation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        max_results = 3
        test_callers = [
            {"name": f"test_{i}", "qualified_name": f"t.test_{i}", "hop": 1, "is_test": True}
            for i in range(7)
        ]
        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(side_effect=[
            _make_result(_make_search_one("fn", "mod.fn")),
            _make_result({"function": "fn", "direction": "inbound", "callers": test_callers}),
        ])
        monkeypatch.setattr("palace_mcp.code_router.get_cm_session", lambda: fake_session)

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        result = await mcp.call_tool("palace.code.test_impact", {
            "qualified_name": "fn",
            "include_indirect": True,
            "max_results": max_results,
        })
        payload = json.loads(result[0][0].text)  # type: ignore[index]
        assert payload["truncated"] is True
        assert len(payload["tests"]) == max_results
        assert payload["total_found"] == 7  # exact, before truncation

    @pytest.mark.asyncio
    async def test_infrastructure_failure_when_session_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When CM session is None, handle_tool_error raises (FastMCP isError=True)."""
        from palace_mcp.code_composite import register_code_composite_tools
        from mcp.server.fastmcp import FastMCP

        monkeypatch.setattr("palace_mcp.code_router.get_cm_session", lambda: None)

        mcp = FastMCP("test")
        register_code_composite_tools(
            lambda name, desc: mcp.tool(name=name, description=desc),
            default_project="repos-gimle",
        )
        with pytest.raises(Exception):
            await mcp.call_tool("palace.code.test_impact", {"qualified_name": "fn"})


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

    def test_cm_default_project_default_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import importlib

        monkeypatch.delenv("PALACE_CM_DEFAULT_PROJECT", raising=False)
        monkeypatch.setenv("NEO4J_PASSWORD", "test")
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        import palace_mcp.config as cfg_module
        importlib.reload(cfg_module)
        settings = cfg_module.Settings()  # type: ignore[call-arg]
        assert settings.palace_cm_default_project == "repos-gimle"
