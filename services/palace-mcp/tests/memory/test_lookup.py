"""Unit tests for palace_mcp.memory.lookup._build_query (query-shape snapshot)
and LookupResponse.warnings field (GIM-37).
"""

from palace_mcp.memory.lookup import _build_query
from palace_mcp.memory.schema import LookupResponse, LookupResponseItem


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


# --- LookupResponse.warnings tests (GIM-37) ---


def test_lookup_response_warnings_empty_by_default() -> None:
    """warnings defaults to [] when no unknown filters exist."""
    resp = LookupResponse(items=[], total_matched=0, query_ms=1)
    assert resp.warnings == []


def test_lookup_response_warnings_populated() -> None:
    """warnings carries unknown-filter messages when provided."""
    msgs = [
        "unknown filter 'bogus' for entity_type 'Issue' — ignored",
        "unknown filter 'xyz' for entity_type 'Issue' — ignored",
    ]
    resp = LookupResponse(items=[], total_matched=0, query_ms=1, warnings=msgs)
    assert resp.warnings == msgs


def test_lookup_response_warnings_single_item_with_data() -> None:
    """warnings coexists with regular response items."""
    item = LookupResponseItem(id="abc", type="Agent", properties={"name": "bot"})
    resp = LookupResponse(
        items=[item],
        total_matched=1,
        query_ms=5,
        warnings=["unknown filter 'foo' for entity_type 'Agent' — ignored"],
    )
    assert len(resp.items) == 1
    assert len(resp.warnings) == 1
    assert "foo" in resp.warnings[0]
