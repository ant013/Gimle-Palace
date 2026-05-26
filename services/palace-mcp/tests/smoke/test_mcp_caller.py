"""Tests for MCP Streamable HTTP caller helpers (GIM-839 A2)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from palace_mcp.smoke.mcp_caller import (
    ExtractorResult,
    McpCallError,
    call_tool,
    list_tools,
    register_project,
    run_extractor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_result(payload: dict[str, Any]) -> CallToolResult:
    import json

    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload))])


def _mock_session(
    *,
    tools: list[str] | None = None,
    call_result: dict[str, Any] | None = None,
) -> AsyncMock:
    session = AsyncMock()
    if tools is not None:
        tool_objects = [Tool(name=t, inputSchema={"type": "object"}) for t in tools]
        session.list_tools.return_value = ListToolsResult(tools=tool_objects)
    if call_result is not None:
        session.call_tool.return_value = _text_result(call_result)
    return session


# ---------------------------------------------------------------------------
# list_tools
# ---------------------------------------------------------------------------


class TestListTools:
    async def test_returns_tool_names(self) -> None:
        session = _mock_session(
            tools=[
                "palace.memory.register_project",
                "palace.ingest.run_extractor",
                "palace.code.semantic_search",
            ]
        )
        result = await list_tools("http://localhost:8000/mcp", _session=session)
        assert result == [
            "palace.memory.register_project",
            "palace.ingest.run_extractor",
            "palace.code.semantic_search",
        ]

    async def test_empty_server(self) -> None:
        session = _mock_session(tools=[])
        result = await list_tools("http://localhost:8000/mcp", _session=session)
        assert result == []


# ---------------------------------------------------------------------------
# call_tool
# ---------------------------------------------------------------------------


class TestCallTool:
    async def test_returns_parsed_json(self) -> None:
        session = _mock_session(call_result={"ok": True, "data": "hello"})
        result = await call_tool(
            "http://localhost:8000/mcp",
            "palace.health.status",
            {},
            _session=session,
        )
        assert result == {"ok": True, "data": "hello"}
        session.call_tool.assert_awaited_once_with("palace.health.status", {})

    async def test_non_json_response_preserves_body(self) -> None:
        session = AsyncMock()
        session.call_tool.return_value = CallToolResult(
            content=[TextContent(type="text", text="not valid json!!!")]
        )
        with pytest.raises(McpCallError) as exc_info:
            await call_tool(
                "http://localhost:8000/mcp",
                "palace.health.status",
                {},
                _session=session,
            )
        err = exc_info.value
        assert err.tool_name == "palace.health.status"
        assert err.raw_body == "not valid json!!!"

    async def test_empty_content_raises(self) -> None:
        session = AsyncMock()
        session.call_tool.return_value = CallToolResult(content=[])
        with pytest.raises(McpCallError) as exc_info:
            await call_tool(
                "http://localhost:8000/mcp",
                "palace.health.status",
                {},
                _session=session,
            )
        assert exc_info.value.tool_name == "palace.health.status"

    async def test_non_text_content_raises(self) -> None:
        from mcp.types import ImageContent

        session = AsyncMock()
        session.call_tool.return_value = CallToolResult(
            content=[ImageContent(type="image", data="abc", mimeType="image/png")]
        )
        with pytest.raises(McpCallError) as exc_info:
            await call_tool(
                "http://localhost:8000/mcp",
                "palace.health.status",
                {},
                _session=session,
            )
        assert "unexpected content type" in str(exc_info.value)


# ---------------------------------------------------------------------------
# register_project — both name and slug
# ---------------------------------------------------------------------------


class TestRegisterProject:
    async def test_sends_both_name_and_slug(self) -> None:
        session = _mock_session(
            call_result={
                "slug": "bitcoin-kit",
                "name": "bitcoin-kit-ios",
                "group_id": "bitcoin-kit",
            }
        )
        result = await register_project(
            "http://localhost:8000/mcp",
            slug="bitcoin-kit",
            name="bitcoin-kit-ios",
            _session=session,
        )
        session.call_tool.assert_awaited_once()
        call_args = session.call_tool.call_args
        tool_name = call_args[0][0]
        arguments = call_args[0][1]

        assert tool_name == "palace.memory.register_project"
        assert "slug" in arguments
        assert "name" in arguments
        assert arguments["slug"] == "bitcoin-kit"
        assert arguments["name"] == "bitcoin-kit-ios"
        assert result["slug"] == "bitcoin-kit"

    async def test_sends_optional_fields_when_provided(self) -> None:
        session = _mock_session(
            call_result={"slug": "uw-ios-app", "name": "unstoppable-wallet-ios"}
        )
        await register_project(
            "http://localhost:8000/mcp",
            slug="uw-ios-app",
            name="unstoppable-wallet-ios",
            language="swift",
            parent_mount="hs",
            relative_path="unstoppable-wallet-ios",
            tags=["ios", "wallet"],
            _session=session,
        )
        arguments = session.call_tool.call_args[0][1]
        assert arguments["language"] == "swift"
        assert arguments["parent_mount"] == "hs"
        assert arguments["relative_path"] == "unstoppable-wallet-ios"
        assert arguments["tags"] == ["ios", "wallet"]

    async def test_omits_none_optional_fields(self) -> None:
        session = _mock_session(call_result={"slug": "s", "name": "n"})
        await register_project(
            "http://localhost:8000/mcp",
            slug="s",
            name="n",
            _session=session,
        )
        arguments = session.call_tool.call_args[0][1]
        assert set(arguments.keys()) == {"slug", "name"}

    async def test_error_preserves_mcp_body(self) -> None:
        session = AsyncMock()
        error_body = (
            '{"ok": false, "error_code": "invalid_slug", "message": "bad slug"}'
        )
        session.call_tool.return_value = CallToolResult(
            content=[TextContent(type="text", text=error_body)]
        )
        result = await register_project(
            "http://localhost:8000/mcp",
            slug="../bad",
            name="bad-project",
            _session=session,
        )
        assert result["ok"] is False
        assert result["error_code"] == "invalid_slug"
        assert "bad slug" in result["message"]


# ---------------------------------------------------------------------------
# run_extractor — structured status
# ---------------------------------------------------------------------------


class TestRunExtractor:
    async def test_returns_structured_result(self) -> None:
        session = _mock_session(
            call_result={
                "ok": True,
                "run_id": "abc-123",
                "duration_ms": 1500,
                "nodes_written": 42,
                "edges_written": 18,
            }
        )
        result = await run_extractor(
            "http://localhost:8000/mcp",
            extractor_name="symbol_index_swift",
            project="bitcoin-kit",
            _session=session,
        )
        assert isinstance(result, ExtractorResult)
        assert result.ok is True
        assert result.run_id == "abc-123"
        assert result.extractor_name == "symbol_index_swift"
        assert result.project == "bitcoin-kit"
        assert result.duration_ms == 1500
        assert result.nodes_written == 42
        assert result.edges_written == 18

    async def test_sends_correct_tool_and_arguments(self) -> None:
        session = _mock_session(call_result={"ok": True, "run_id": "r1"})
        await run_extractor(
            "http://localhost:8000/mcp",
            extractor_name="dead_code",
            project="uw-ios-app",
            _session=session,
        )
        call_args = session.call_tool.call_args
        assert call_args[0][0] == "palace.ingest.run_extractor"
        assert call_args[0][1] == {"name": "dead_code", "project": "uw-ios-app"}

    async def test_includes_scip_path_override_when_provided(self) -> None:
        session = _mock_session(call_result={"ok": True, "run_id": "r1"})
        await run_extractor(
            "http://localhost:8000/mcp",
            extractor_name="symbol_index_swift",
            project="uw-ios-app",
            scip_path="/tmp/uw-ios-app/scip/index.scip",
            _session=session,
        )
        call_args = session.call_tool.call_args
        assert call_args[0][1] == {
            "name": "symbol_index_swift",
            "project": "uw-ios-app",
            "scip_path": "/tmp/uw-ios-app/scip/index.scip",
        }

    async def test_error_result_structured(self) -> None:
        session = _mock_session(
            call_result={
                "ok": False,
                "error_code": "extractor_not_found",
                "message": "unknown extractor 'bogus'",
            }
        )
        result = await run_extractor(
            "http://localhost:8000/mcp",
            extractor_name="bogus",
            project="bitcoin-kit",
            _session=session,
        )
        assert result.ok is False
        assert result.error_code == "extractor_not_found"
        assert result.message == "unknown extractor 'bogus'"

    async def test_transport_error_preserves_body(self) -> None:
        session = AsyncMock()
        session.call_tool.return_value = CallToolResult(
            content=[TextContent(type="text", text="internal server error")]
        )
        with pytest.raises(McpCallError) as exc_info:
            await run_extractor(
                "http://localhost:8000/mcp",
                extractor_name="symbol_index_swift",
                project="bitcoin-kit",
                _session=session,
            )
        assert exc_info.value.raw_body == "internal server error"
