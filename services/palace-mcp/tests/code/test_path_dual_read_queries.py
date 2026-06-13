from __future__ import annotations

import inspect

from palace_mcp.code.find_semantic import (
    _COUNT_EMBEDDED_SYMBOLS_QUERY,
    _COVERAGE_QUERY,
    _VECTOR_LEGACY_QUERY,
    _VECTOR_QUERY,
    _VECTOR_SEARCH_QUERY,
)
from palace_mcp.code.find_hotspots import _QUERY as HOTSPOTS_QUERY
from palace_mcp.code.find_owners import _QUERY_CYPHER as OWNERS_QUERY
from palace_mcp.code_composite import _QUERY_HOTSPOT_SCORE
from palace_mcp.code.list_functions import _QUERY as LIST_FUNCTIONS_QUERY
from palace_mcp.extractors.code_ownership.churn_aggregator import _CHURN_CYPHER
from palace_mcp.extractors.code_ownership.extractor import CodeOwnershipExtractor
from palace_mcp.extractors.foundation.module_owner import _resolve_from_graph
from palace_mcp.extractors.hotspot.churn_query import CHURN_CYPHER
from palace_mcp.extractors.hotspot.extractor import HotspotExtractor


def test_tool_queries_dual_read_file_path() -> None:
    assert "coalesce(f.file_path, f.path)" in OWNERS_QUERY
    assert "coalesce(st.file_path, st.path)" in OWNERS_QUERY
    assert "coalesce(f.file_path, f.path)" in LIST_FUNCTIONS_QUERY
    assert "coalesce(fn.file_path, fn.path)" in LIST_FUNCTIONS_QUERY
    assert "coalesce(f.file_path, f.path)" in HOTSPOTS_QUERY


def test_phase_4a_queries_honor_include_deprecated_filter() -> None:
    assert "($include_deprecated OR NOT f:Deprecated)" in OWNERS_QUERY
    assert "($include_deprecated OR NOT f:Deprecated)" in LIST_FUNCTIONS_QUERY
    assert "($include_deprecated OR NOT f:Deprecated)" in HOTSPOTS_QUERY
    assert "($include_deprecated OR NOT s:Deprecated)" in _COUNT_EMBEDDED_SYMBOLS_QUERY
    assert "($include_deprecated OR NOT s:Deprecated)" in _COVERAGE_QUERY
    assert "($include_deprecated OR NOT s:Deprecated)" in _VECTOR_QUERY


def test_semantic_vector_query_shapes_support_search_and_legacy_fallback() -> None:
    assert _VECTOR_QUERY == _VECTOR_SEARCH_QUERY
    assert _VECTOR_SEARCH_QUERY.startswith("CYPHER 25")
    assert "SEARCH s IN" in _VECTOR_SEARCH_QUERY
    assert "VECTOR INDEX symbol_embedding_idx" in _VECTOR_SEARCH_QUERY
    assert "SCORE AS score" in _VECTOR_SEARCH_QUERY
    assert "db.index.vector.queryNodes" not in _VECTOR_SEARCH_QUERY

    assert "db.index.vector.queryNodes('symbol_embedding_idx'" in _VECTOR_LEGACY_QUERY
    assert "SEARCH s IN" not in _VECTOR_LEGACY_QUERY

    assert "{symbol_embedding_idx}" not in _VECTOR_SEARCH_QUERY
    assert "{symbol_embedding_idx}" not in _VECTOR_LEGACY_QUERY
    assert "$index" not in _VECTOR_SEARCH_QUERY
    assert "$index" not in _VECTOR_LEGACY_QUERY


def test_semantic_vector_queries_read_optional_line_props_dynamically() -> None:
    for query in (_VECTOR_SEARCH_QUERY, _VECTOR_LEGACY_QUERY):
        assert "properties(s)[$line_start_key] AS line_start" in query
        assert "properties(s)[$line_end_key] AS line_end" in query
        assert "s.line_start AS line_start" not in query
        assert "s.line_end AS line_end" not in query


def test_extractor_queries_dual_read_file_path() -> None:
    assert "coalesce(f.file_path, f.path)" in CHURN_CYPHER
    assert "coalesce(f.file_path, f.path)" in _CHURN_CYPHER
    assert (
        "coalesce(f.file_path, f.path) AS path"
        in HotspotExtractor().audit_contract().query
    )
    assert (
        "coalesce(f.file_path, f.path) AS path"
        in CodeOwnershipExtractor().audit_contract().query
    )


def test_auxiliary_queries_dual_read_file_path() -> None:
    assert "coalesce(f.file_path, f.path) = $path" in _QUERY_HOTSPOT_SCORE
    assert "coalesce(file.file_path, file.path) = $file_path" in inspect.getsource(
        _resolve_from_graph
    )
