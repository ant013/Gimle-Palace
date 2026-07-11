"""Schema advertisement + index DDL for get_code_snippet scope."""

from __future__ import annotations

from palace_mcp.code_router import _open_schema_for_tool
from palace_mcp.memory.constraints import SNIPPET_SCOPE_INDEXES


def test_snippet_scope_index_ddl_present() -> None:
    ddl = " ".join(SNIPPET_SCOPE_INDEXES)
    assert "symbol_group_qn" in ddl
    assert "(s.group_id, s.qualified_name)" in ddl
    assert "IF NOT EXISTS" in ddl


def test_get_code_snippet_advertises_scope_enum() -> None:
    schema = _open_schema_for_tool("get_code_snippet")
    scope = schema["properties"]["scope"]
    assert scope["enum"] == ["symbol", "file", "type"]
    assert scope["default"] == "symbol"


def test_search_graph_has_no_scope() -> None:
    schema = _open_schema_for_tool("search_graph")
    assert "scope" not in schema["properties"]
