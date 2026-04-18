from palace_mcp.memory.cypher import BACKFILL_GROUP_ID


def test_backfill_has_where_is_null_guard() -> None:
    assert "WHERE n.group_id IS NULL" in BACKFILL_GROUP_ID


def test_backfill_covers_all_four_labels() -> None:
    for label in ("Issue", "Comment", "Agent", "IngestRun"):
        assert f"(n:{label})" in BACKFILL_GROUP_ID


def test_backfill_parameterises_default() -> None:
    assert "$default" in BACKFILL_GROUP_ID
