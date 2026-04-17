"""Unit tests for palace_mcp.memory.lookup._build_query (query-shape snapshot)."""

from palace_mcp.memory.lookup import _build_query


def test_build_query_contains_entity_label_and_limit() -> None:
    q = _build_query("Issue", ["n.status = $status"], "source_updated_at", 20)
    assert "(n:Issue)" in q
    assert "LIMIT 20" in q
    assert "ORDER BY n.source_updated_at DESC" in q
    assert "$status" in q


def test_build_query_no_filters() -> None:
    q = _build_query("Agent", [], "source_updated_at", 5)
    assert "(n:Agent)" in q
    assert "LIMIT 5" in q
    assert "WHERE" not in q


def test_build_query_comment_entity() -> None:
    q = _build_query("Comment", ["n.source_created_at >= $ts"], "source_created_at", 10)
    assert "(n:Comment)" in q
    assert "LIMIT 10" in q
    assert "ORDER BY n.source_created_at DESC" in q
    assert "$ts" in q
