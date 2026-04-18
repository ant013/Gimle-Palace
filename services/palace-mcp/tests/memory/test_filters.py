from palace_mcp.memory.filters import resolve_filters


def test_issue_known_keys_pass_through() -> None:
    where_clauses, params, unknown = resolve_filters(
        "Issue",
        {
            "key": "GIM-23",
            "status": "done",
            "source_updated_at_gte": "2026-04-01T00:00:00Z",
        },
    )
    assert "n.key = $key" in where_clauses
    assert "n.status = $status" in where_clauses
    assert "n.source_updated_at >= $source_updated_at_gte" in where_clauses
    assert params == {
        "key": "GIM-23",
        "status": "done",
        "source_updated_at_gte": "2026-04-01T00:00:00Z",
    }
    assert unknown == []


def test_issue_unknown_key_returned_separately() -> None:
    where_clauses, params, unknown = resolve_filters(
        "Issue", {"key": "GIM-23", "bogus": "x"}
    )
    assert unknown == ["bogus"]
    assert "bogus" not in params


def test_issue_assignee_name_joins_via_agent() -> None:
    where_clauses, params, unknown = resolve_filters(
        "Issue", {"assignee_name": "CodeReviewer"}
    )
    # assignee_name uses a relationship traversal — marked as a special "join" clause.
    assert any("ASSIGNED_TO" in c for c in where_clauses)
    assert params["assignee_name"] == "CodeReviewer"


def test_agent_whitelist_enforced() -> None:
    _, params, unknown = resolve_filters("Agent", {"name": "X", "foo": "bar"})
    assert "name" in params
    assert unknown == ["foo"]
