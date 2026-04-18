"""EntityNode and EntityEdge builders for paperclip data.

Maps paperclip API DTOs to graphiti-core EntityNode / EntityEdge instances.
Group_id hardcoded to "project/gimle" in N+1a; parameterized in N+1b.
Pure functions — no I/O.

graphiti-core auto-prepends :Entity to all labels (verified in verification §5.F),
so labels=["Issue"] becomes stored as ["Entity", "Issue"].
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode

GROUP_ID = "project/gimle"  # parameterized in N+1b
SOURCE = "paperclip"


def _ts(record: dict[str, Any], key: str, fallback_key: str = "createdAt") -> str:
    val = record.get(key) or record.get(fallback_key)
    if not isinstance(val, str):
        raise ValueError(
            f"paperclip record missing {key}/{fallback_key}: {record.get('id')}"
        )
    return val


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def build_issue_node(
    issue: dict[str, Any], *, run_started: str, group_id: str = GROUP_ID
) -> EntityNode:
    description = issue.get("description") or ""
    return EntityNode(
        uuid=issue["id"],
        name=f"{issue.get('identifier') or issue.get('key') or ''}: {issue.get('title') or ''}",
        labels=["Issue"],  # graphiti auto-prepends :Entity (verification §5.F)
        group_id=group_id,
        summary=description[:500],
        attributes={
            "id": issue["id"],
            "key": issue.get("identifier") or issue.get("key") or "",
            "title": issue.get("title") or "",
            "description": description,
            "status": issue.get("status") or "",
            "source": SOURCE,
            "source_created_at": _ts(issue, "createdAt"),
            "source_updated_at": _ts(issue, "updatedAt"),
            "palace_last_seen_at": run_started,
            "text_hash": sha256(description.encode()).hexdigest(),
            "assignee_agent_id": issue.get("assigneeAgentId"),
        },
    )


def build_comment_node(
    comment: dict[str, Any], *, run_started: str, group_id: str = GROUP_ID
) -> EntityNode:
    body = comment.get("body") or ""
    return EntityNode(
        uuid=comment["id"],
        name=f"comment-{comment['id'][:8]}",
        labels=["Comment"],
        group_id=group_id,
        summary=body[:500],
        attributes={
            "id": comment["id"],
            "body": body,
            "issue_id": comment.get("issueId") or "",
            "author_agent_id": comment.get("authorAgentId"),
            "source": SOURCE,
            "source_created_at": _ts(comment, "createdAt"),
            "source_updated_at": _ts(comment, "updatedAt"),
            "palace_last_seen_at": run_started,
            "text_hash": sha256(body.encode()).hexdigest(),
        },
    )


def build_agent_node(
    agent: dict[str, Any], *, run_started: str, group_id: str = GROUP_ID
) -> EntityNode:
    name = agent.get("name") or ""
    return EntityNode(
        uuid=agent["id"],
        name=name,
        labels=["Agent"],
        group_id=group_id,
        summary=f"{name} ({agent.get('role') or ''})",
        attributes={
            "id": agent["id"],
            "name": name,
            "url_key": agent.get("urlKey") or "",
            "role": agent.get("role") or "",
            "source": SOURCE,
            "source_created_at": _ts(agent, "createdAt"),
            "source_updated_at": _ts(agent, "updatedAt"),
            "palace_last_seen_at": run_started,
            "text_hash": sha256(name.encode()).hexdigest(),
        },
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_on_edge(
    *,
    comment_uuid: str,
    issue_uuid: str,
    comment_created_at: str,
    run_started: str,
    group_id: str = GROUP_ID,
) -> EntityEdge:
    return EntityEdge(
        source_node_uuid=comment_uuid,
        target_node_uuid=issue_uuid,
        name="ON",
        fact=f"Comment {comment_uuid} is on issue {issue_uuid}",
        group_id=group_id,
        created_at=_parse_iso(run_started),
        valid_at=_parse_iso(comment_created_at),
        invalid_at=None,
    )


def build_authored_by_edge(
    *,
    comment_uuid: str,
    agent_uuid: str,
    comment_created_at: str,
    run_started: str,
    group_id: str = GROUP_ID,
) -> EntityEdge:
    return EntityEdge(
        source_node_uuid=comment_uuid,
        target_node_uuid=agent_uuid,
        name="AUTHORED_BY",
        fact=f"Comment {comment_uuid} authored by agent {agent_uuid}",
        group_id=group_id,
        created_at=_parse_iso(run_started),
        valid_at=_parse_iso(comment_created_at),
        invalid_at=None,
    )


def build_assigned_to_edge(
    *,
    issue_uuid: str,
    agent_uuid: str,
    run_started: str,
    group_id: str = GROUP_ID,
) -> EntityEdge:
    return EntityEdge(
        source_node_uuid=issue_uuid,
        target_node_uuid=agent_uuid,
        name="ASSIGNED_TO",
        fact=f"Issue {issue_uuid} assigned to agent {agent_uuid} as of {run_started}",
        group_id=group_id,
        created_at=_parse_iso(run_started),
        valid_at=_parse_iso(run_started),
        invalid_at=None,
    )
