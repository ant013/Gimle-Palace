from palace_mcp.memory.cypher import (
    UPSERT_AGENTS,
    UPSERT_COMMENTS,
    UPSERT_ISSUES,
)


def test_upsert_issues_sets_group_id() -> None:
    assert "i.group_id" in UPSERT_ISSUES
    assert "$group_id" in UPSERT_ISSUES


def test_upsert_comments_sets_group_id() -> None:
    assert "c.group_id" in UPSERT_COMMENTS
    assert "$group_id" in UPSERT_COMMENTS


def test_upsert_agents_sets_group_id() -> None:
    assert "a.group_id" in UPSERT_AGENTS
    assert "$group_id" in UPSERT_AGENTS


def test_create_ingest_run_sets_group_id() -> None:
    from palace_mcp.memory.cypher import CREATE_INGEST_RUN

    assert "group_id: $group_id" in CREATE_INGEST_RUN


def test_latest_ingest_run_accepts_optional_group_filter() -> None:
    from palace_mcp.memory.cypher import LATEST_INGEST_RUN_FOR_GROUP

    assert "r.group_id = $group_id" in LATEST_INGEST_RUN_FOR_GROUP


def test_gc_by_label_filters_by_group_id() -> None:
    from palace_mcp.memory.cypher import GC_BY_LABEL

    assert "n.group_id = $group_id" in GC_BY_LABEL
    assert "n.source = 'paperclip'" in GC_BY_LABEL
    assert "n.palace_last_seen_at < $cutoff" in GC_BY_LABEL
