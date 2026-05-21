from __future__ import annotations

from palace_mcp.code.find_hotspots import _QUERY as HOTSPOTS_QUERY
from palace_mcp.code.find_owners import _QUERY_CYPHER as OWNERS_QUERY
from palace_mcp.code.list_functions import _QUERY as LIST_FUNCTIONS_QUERY
from palace_mcp.extractors.code_ownership.churn_aggregator import _CHURN_CYPHER
from palace_mcp.extractors.code_ownership.extractor import CodeOwnershipExtractor
from palace_mcp.extractors.hotspot.churn_query import CHURN_CYPHER
from palace_mcp.extractors.hotspot.extractor import HotspotExtractor


def test_tool_queries_dual_read_file_path() -> None:
    assert "coalesce(f.file_path, f.path)" in OWNERS_QUERY
    assert "coalesce(st.file_path, st.path)" in OWNERS_QUERY
    assert "coalesce(f.file_path, f.path)" in LIST_FUNCTIONS_QUERY
    assert "coalesce(fn.file_path, fn.path)" in LIST_FUNCTIONS_QUERY
    assert "coalesce(f.file_path, f.path)" in HOTSPOTS_QUERY


def test_extractor_queries_dual_read_file_path() -> None:
    assert "coalesce(f.file_path, f.path)" in CHURN_CYPHER
    assert "coalesce(f.file_path, f.path)" in _CHURN_CYPHER
    assert "coalesce(f.file_path, f.path) AS path" in HotspotExtractor().audit_contract().query
    assert "coalesce(f.file_path, f.path) AS path" in CodeOwnershipExtractor().audit_contract().query
