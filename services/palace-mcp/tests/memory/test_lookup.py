"""Unit tests for palace_mcp.memory.lookup._build_query (query-shape snapshot)
and LookupResponse.warnings field (GIM-37).
"""

from palace_mcp.memory.lookup import _build_query, _safe_order_by, _serialize_props
from palace_mcp.memory.schema import LookupRequest, LookupResponse, LookupResponseItem


# --- _serialize_props: embedding strip default-on (276K→~14K read payload) ---


def test_serialize_props_strips_embeddings_by_default() -> None:
    out = _serialize_props(
        {
            "name": "x",
            "body": "y",
            "name_embedding": [0.1] * 1536,
            "embedding": [0.2] * 768,
            "fact_embedding": [0.3] * 100,
        }
    )
    assert out == {"name": "x", "body": "y"}


def test_serialize_props_keeps_embedding_input_hash() -> None:
    # Regression guard: a real non-vector field must NOT be false-stripped.
    out = _serialize_props({"embedding_input_hash": "abc123", "name": "x"})
    assert out == {"embedding_input_hash": "abc123", "name": "x"}


def test_serialize_props_include_embeddings_true_keeps_them() -> None:
    out = _serialize_props(
        {"name": "x", "name_embedding": [0.1, 0.2]}, include_embeddings=True
    )
    assert out["name_embedding"] == [0.1, 0.2]


def test_lookup_request_include_embeddings_defaults_false() -> None:
    assert LookupRequest(entity_type="Decision").include_embeddings is False
    assert LookupRequest(
        entity_type="Decision", include_embeddings=True
    ).include_embeddings


def test_safe_order_by_neutralizes_injection() -> None:
    # Defensive: unknown/injection columns fall back to the safe default.
    assert _safe_order_by("created_at} RETURN n.name_embedding //") == (
        "created_at",
        "DESC",
    )
    assert _safe_order_by("name asc") == ("name", "ASC")


def test_build_query_contains_entity_label_and_limit() -> None:
    q = _build_query("Episode", ["n.kind = $kind"], "created_at", 20)
    assert "(n:Episode)" in q
    assert "LIMIT 20" in q
    assert "ORDER BY n.created_at DESC" in q
    assert "$kind" in q


def test_build_query_no_filters() -> None:
    q = _build_query("Symbol", [], "name", 5)
    assert "(n:Symbol)" in q
    assert "LIMIT 5" in q
    assert "WHERE" not in q


def test_build_query_file_entity() -> None:
    q = _build_query("File", ["n.path = $path"], "created_at", 10)
    assert "(n:File)" in q
    assert "LIMIT 10" in q
    assert "ORDER BY n.created_at DESC" in q
    assert "$path" in q


# --- LookupResponse.warnings tests (GIM-37) ---


def test_lookup_response_warnings_empty_by_default() -> None:
    """warnings defaults to [] when no unknown filters exist."""
    resp = LookupResponse(items=[], total_matched=0, query_ms=1)
    assert resp.warnings == []


def test_lookup_response_warnings_populated() -> None:
    """warnings carries unknown-filter messages when provided."""
    msgs = [
        "unknown filter 'bogus' for entity_type 'Episode' — ignored",
        "unknown filter 'xyz' for entity_type 'Episode' — ignored",
    ]
    resp = LookupResponse(items=[], total_matched=0, query_ms=1, warnings=msgs)
    assert resp.warnings == msgs


def test_lookup_response_warnings_single_item_with_data() -> None:
    """warnings coexists with regular response items."""
    item = LookupResponseItem(
        id="abc", type="Episode", properties={"kind": "heartbeat"}
    )
    resp = LookupResponse(
        items=[item],
        total_matched=1,
        query_ms=5,
        warnings=["unknown filter 'foo' for entity_type 'Episode' — ignored"],
    )
    assert len(resp.items) == 1
    assert len(resp.warnings) == 1
    assert "foo" in resp.warnings[0]


# --- project param + IN $group_ids WHERE ---


def test_build_query_uses_group_ids_in_clause() -> None:
    q = _build_query(
        "Episode",
        ["n.group_id IN $group_ids"],
        "created_at",
        20,
    )
    assert "n.group_id IN $group_ids" in q
