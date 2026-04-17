"""Map paperclip API DTOs to Neo4j node property dicts.

Pure functions — no I/O. Each returns a dict ready for Cypher UNWIND.
Timestamp fallback: if paperclip omits `updatedAt`, use `createdAt`
so `source_updated_at` is always populated (required by schema).
"""

from typing import Any

SOURCE = "paperclip"


def _ts(record: dict[str, Any], key: str, fallback_key: str = "createdAt") -> str:
    val = record.get(key) or record.get(fallback_key)
    if not isinstance(val, str):
        raise ValueError(f"paperclip record missing {key}/{fallback_key}: {record.get('id')}")
    return val


def transform_issue(issue: dict[str, Any], *, run_started: str) -> dict[str, Any]:
    return {
        "id": issue["id"],
        "key": issue.get("identifier") or issue.get("key") or "",
        "title": issue.get("title") or "",
        "description": issue.get("description") or "",
        "status": issue.get("status") or "",
        "source": SOURCE,
        "source_created_at": _ts(issue, "createdAt"),
        "source_updated_at": _ts(issue, "updatedAt"),
        "palace_last_seen_at": run_started,
        "assignee_agent_id": issue.get("assigneeAgentId"),
    }


def transform_comment(comment: dict[str, Any], *, run_started: str) -> dict[str, Any]:
    return {
        "id": comment["id"],
        "body": comment.get("body") or "",
        "issue_id": comment.get("issueId") or "",
        "author_agent_id": comment.get("authorAgentId"),
        "source": SOURCE,
        "source_created_at": _ts(comment, "createdAt"),
        "source_updated_at": _ts(comment, "updatedAt"),
        "palace_last_seen_at": run_started,
    }


def transform_agent(agent: dict[str, Any], *, run_started: str) -> dict[str, Any]:
    return {
        "id": agent["id"],
        "name": agent.get("name") or "",
        "url_key": agent.get("urlKey") or "",
        "role": agent.get("role") or "",
        "source": SOURCE,
        "source_created_at": _ts(agent, "createdAt"),
        "source_updated_at": _ts(agent, "updatedAt"),
        "palace_last_seen_at": run_started,
    }
