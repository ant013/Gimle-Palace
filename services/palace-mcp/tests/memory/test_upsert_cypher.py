from palace_mcp.memory.cypher import UPSERT_AGENTS, UPSERT_COMMENTS, UPSERT_ISSUES


def test_upsert_issues_sets_group_id() -> None:
    assert "i.group_id" in UPSERT_ISSUES
    assert "$group_id" in UPSERT_ISSUES


def test_upsert_comments_sets_group_id() -> None:
    assert "c.group_id" in UPSERT_COMMENTS
    assert "$group_id" in UPSERT_COMMENTS


def test_upsert_agents_sets_group_id() -> None:
    assert "a.group_id" in UPSERT_AGENTS
    assert "$group_id" in UPSERT_AGENTS
