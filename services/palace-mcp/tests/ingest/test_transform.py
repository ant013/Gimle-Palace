from palace_mcp.ingest.transform import (
    transform_agent,
    transform_comment,
    transform_issue,
)


def test_transform_issue_maps_expected_fields() -> None:
    pc_issue = {
        "id": "uuid-1",
        "identifier": "GIM-1",
        "title": "T",
        "description": "D",
        "status": "done",
        "createdAt": "2026-04-10T00:00:00Z",
        "updatedAt": "2026-04-17T00:00:00Z",
        "assigneeAgentId": "agent-1",
    }
    out = transform_issue(pc_issue, run_started="2026-04-17T06:00:00+00:00")
    assert out["id"] == "uuid-1"
    assert out["key"] == "GIM-1"
    assert out["source"] == "paperclip"
    assert out["source_created_at"] == "2026-04-10T00:00:00Z"
    assert out["source_updated_at"] == "2026-04-17T00:00:00Z"
    assert out["palace_last_seen_at"] == "2026-04-17T06:00:00+00:00"
    assert out["assignee_agent_id"] == "agent-1"


def test_transform_comment_handles_null_author() -> None:
    pc_comment = {
        "id": "c1",
        "body": "hi",
        "issueId": "uuid-1",
        "authorAgentId": None,
        "createdAt": "2026-04-17T05:00:00Z",
    }
    out = transform_comment(pc_comment, run_started="2026-04-17T06:00:00+00:00")
    assert out["author_agent_id"] is None
    assert out["issue_id"] == "uuid-1"
    assert out["source_updated_at"] == "2026-04-17T05:00:00Z"  # fallback to createdAt


def test_transform_agent_basic() -> None:
    pc_agent = {
        "id": "a1",
        "name": "CodeReviewer",
        "urlKey": "codereviewer",
        "role": "Review adversary.",
        "createdAt": "2026-04-13T00:00:00Z",
        "updatedAt": "2026-04-17T00:00:00Z",
    }
    out = transform_agent(pc_agent, run_started="2026-04-17T06:00:00+00:00")
    assert out["name"] == "CodeReviewer"
    assert out["url_key"] == "codereviewer"
