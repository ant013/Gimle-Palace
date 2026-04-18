"""Unit tests for palace_mcp.ingest.builders — pure-function EntityNode/EntityEdge builders."""

from __future__ import annotations

import pytest

from palace_mcp.ingest.builders import (
    build_agent_node,
    build_assigned_to_edge,
    build_authored_by_edge,
    build_comment_node,
    build_issue_node,
    build_on_edge,
)

RUN_STARTED = "2024-06-01T12:00:00+00:00"


# ── Issue node ────────────────────────────────────────────────────────────────


def _issue(**overrides: object) -> dict:
    base: dict = {
        "id": "issue-uuid-1",
        "identifier": "GIM-42",
        "title": "Fix the thing",
        "description": "Some description",
        "status": "in_progress",
        "createdAt": "2024-01-01T00:00:00+00:00",
        "updatedAt": "2024-01-02T00:00:00+00:00",
        "assigneeAgentId": "agent-uuid-1",
    }
    base.update(overrides)
    return base


def test_build_issue_node_uuid() -> None:
    node = build_issue_node(_issue(), run_started=RUN_STARTED)
    assert node.uuid == "issue-uuid-1"


def test_build_issue_node_label() -> None:
    node = build_issue_node(_issue(), run_started=RUN_STARTED)
    assert "Issue" in node.labels


def test_build_issue_node_name_includes_key_and_title() -> None:
    node = build_issue_node(_issue(), run_started=RUN_STARTED)
    assert "GIM-42" in node.name
    assert "Fix the thing" in node.name


def test_build_issue_node_text_hash_reproducible() -> None:
    node1 = build_issue_node(_issue(), run_started=RUN_STARTED)
    node2 = build_issue_node(_issue(), run_started=RUN_STARTED)
    assert node1.attributes["text_hash"] == node2.attributes["text_hash"]


def test_build_issue_node_text_hash_changes_on_description() -> None:
    node1 = build_issue_node(_issue(description="desc A"), run_started=RUN_STARTED)
    node2 = build_issue_node(_issue(description="desc B"), run_started=RUN_STARTED)
    assert node1.attributes["text_hash"] != node2.attributes["text_hash"]


def test_build_issue_node_palace_last_seen_at() -> None:
    node = build_issue_node(_issue(), run_started=RUN_STARTED)
    assert node.attributes["palace_last_seen_at"] == RUN_STARTED


def test_build_issue_node_source_is_paperclip() -> None:
    node = build_issue_node(_issue(), run_started=RUN_STARTED)
    assert node.attributes["source"] == "paperclip"


def test_build_issue_node_status() -> None:
    node = build_issue_node(_issue(status="done"), run_started=RUN_STARTED)
    assert node.attributes["status"] == "done"


def test_build_issue_node_missing_id_raises() -> None:
    with pytest.raises(KeyError):
        build_issue_node({"title": "no id"}, run_started=RUN_STARTED)


def test_build_issue_node_missing_created_at_raises() -> None:
    data = {
        "id": "x",
        "title": "t",
        "description": "d",
        "status": "todo",
        "updatedAt": "2024-01-01T00:00:00+00:00",
    }
    with pytest.raises(ValueError, match="missing"):
        build_issue_node(data, run_started=RUN_STARTED)


def test_build_issue_node_empty_description() -> None:
    """Empty description is allowed; text_hash is sha256 of empty string."""
    node = build_issue_node(_issue(description=None), run_started=RUN_STARTED)
    assert node.attributes["text_hash"] is not None
    assert node.attributes["description"] == ""


def test_build_issue_node_assignee_agent_id() -> None:
    node = build_issue_node(_issue(assigneeAgentId=None), run_started=RUN_STARTED)
    assert node.attributes["assignee_agent_id"] is None

    node2 = build_issue_node(_issue(assigneeAgentId="agent-42"), run_started=RUN_STARTED)
    assert node2.attributes["assignee_agent_id"] == "agent-42"


# ── Comment node ──────────────────────────────────────────────────────────────


def _comment(**overrides: object) -> dict:
    base: dict = {
        "id": "comment-uuid-1",
        "body": "LGTM!",
        "issueId": "issue-uuid-1",
        "authorAgentId": "agent-uuid-1",
        "createdAt": "2024-01-03T00:00:00+00:00",
        "updatedAt": "2024-01-03T00:00:00+00:00",
    }
    base.update(overrides)
    return base


def test_build_comment_node_uuid() -> None:
    node = build_comment_node(_comment(), run_started=RUN_STARTED)
    assert node.uuid == "comment-uuid-1"


def test_build_comment_node_label() -> None:
    node = build_comment_node(_comment(), run_started=RUN_STARTED)
    assert "Comment" in node.labels


def test_build_comment_node_text_hash_on_body() -> None:
    node1 = build_comment_node(_comment(body="hello"), run_started=RUN_STARTED)
    node2 = build_comment_node(_comment(body="world"), run_started=RUN_STARTED)
    assert node1.attributes["text_hash"] != node2.attributes["text_hash"]


def test_build_comment_node_empty_body() -> None:
    node = build_comment_node(_comment(body=None), run_started=RUN_STARTED)
    assert node.attributes["body"] == ""


def test_build_comment_node_issue_id() -> None:
    node = build_comment_node(_comment(issueId="parent-issue"), run_started=RUN_STARTED)
    assert node.attributes["issue_id"] == "parent-issue"


# ── Agent node ────────────────────────────────────────────────────────────────


def _agent(**overrides: object) -> dict:
    base: dict = {
        "id": "agent-uuid-1",
        "name": "CTO",
        "urlKey": "cto",
        "role": "engineering",
        "createdAt": "2024-01-01T00:00:00+00:00",
        "updatedAt": "2024-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return base


def test_build_agent_node_uuid() -> None:
    node = build_agent_node(_agent(), run_started=RUN_STARTED)
    assert node.uuid == "agent-uuid-1"


def test_build_agent_node_name() -> None:
    node = build_agent_node(_agent(name="MCPEngineer"), run_started=RUN_STARTED)
    assert node.name == "MCPEngineer"


def test_build_agent_node_label() -> None:
    node = build_agent_node(_agent(), run_started=RUN_STARTED)
    assert "Agent" in node.labels


def test_build_agent_node_url_key() -> None:
    node = build_agent_node(_agent(urlKey="mcp-engineer"), run_started=RUN_STARTED)
    assert node.attributes["url_key"] == "mcp-engineer"


# ── Edges ─────────────────────────────────────────────────────────────────────


def test_build_on_edge_names_and_nodes() -> None:
    edge = build_on_edge(
        comment_uuid="c1",
        issue_uuid="i1",
        comment_created_at="2024-01-01T00:00:00+00:00",
        run_started=RUN_STARTED,
    )
    assert edge.name == "ON"
    assert edge.source_node_uuid == "c1"
    assert edge.target_node_uuid == "i1"
    assert edge.invalid_at is None


def test_build_authored_by_edge() -> None:
    edge = build_authored_by_edge(
        comment_uuid="c1",
        agent_uuid="a1",
        comment_created_at="2024-01-01T00:00:00+00:00",
        run_started=RUN_STARTED,
    )
    assert edge.name == "AUTHORED_BY"
    assert edge.source_node_uuid == "c1"
    assert edge.target_node_uuid == "a1"
    assert edge.invalid_at is None


def test_build_assigned_to_edge() -> None:
    edge = build_assigned_to_edge(
        issue_uuid="i1",
        agent_uuid="a1",
        run_started=RUN_STARTED,
    )
    assert edge.name == "ASSIGNED_TO"
    assert edge.source_node_uuid == "i1"
    assert edge.target_node_uuid == "a1"
    assert edge.invalid_at is None


def test_build_assigned_to_edge_valid_at_equals_run_started() -> None:
    from datetime import datetime

    edge = build_assigned_to_edge(
        issue_uuid="i1",
        agent_uuid="a1",
        run_started=RUN_STARTED,
    )
    assert edge.valid_at == datetime.fromisoformat(RUN_STARTED)


def test_build_on_edge_valid_at_equals_comment_created() -> None:
    from datetime import datetime

    comment_created = "2024-03-15T08:30:00+00:00"
    edge = build_on_edge(
        comment_uuid="c1",
        issue_uuid="i1",
        comment_created_at=comment_created,
        run_started=RUN_STARTED,
    )
    assert edge.valid_at == datetime.fromisoformat(comment_created)
