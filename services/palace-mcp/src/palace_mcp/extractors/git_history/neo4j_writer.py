"""Neo4j writer with explicit ON CREATE / ON MATCH for time-window preservation.

See spec GIM-186 §3.4 invariant 5.
"""

from __future__ import annotations

from neo4j import AsyncDriver

_MERGE_AUTHOR_CYPHER = """
MERGE (a:Author {provider: $provider, identity_key: $identity_key})
ON CREATE SET
  a.email = $email, a.name = $name, a.is_bot = $is_bot,
  a.first_seen_at = $ts, a.last_seen_at = $ts,
  a.project_id = $project_id
ON MATCH SET
  a.last_seen_at = CASE
    WHEN $ts > coalesce(a.last_seen_at, datetime('1970-01-01T00:00:00Z'))
    THEN $ts ELSE a.last_seen_at
  END,
  a.first_seen_at = CASE
    WHEN $ts < coalesce(a.first_seen_at, datetime('9999-12-31T23:59:59Z'))
    THEN $ts ELSE a.first_seen_at
  END,
  a.email = coalesce(a.email, $email),
  a.is_bot = $is_bot
"""

_MERGE_COMMIT_CYPHER = """
MERGE (c:Commit {sha: $sha})
ON CREATE SET
  c.project_id = $project_id,
  c.author_provider = $author_provider,
  c.author_identity_key = $author_identity_key,
  c.committer_provider = $committer_provider,
  c.committer_identity_key = $committer_identity_key,
  c.message_subject = $message_subject,
  c.message_full_truncated = $message_full_truncated,
  c.committed_at = $committed_at,
  c.parents = $parents
WITH c
MATCH (a:Author {provider: $author_provider, identity_key: $author_identity_key})
MERGE (c)-[:AUTHORED_BY]->(a)
WITH c
MATCH (cm:Author {provider: $committer_provider, identity_key: $committer_identity_key})
MERGE (c)-[:COMMITTED_BY]->(cm)
"""

_MERGE_TOUCHED_CYPHER = """
UNWIND $files AS path
MERGE (f:File {project_id: $project_id, path: path})
WITH f
MATCH (c:Commit {sha: $sha})
MERGE (c)-[:TOUCHED]->(f)
"""

_MERGE_PR_CYPHER = """
MERGE (p:PR {project_id: $project_id, number: $number})
ON CREATE SET
  p.title = $title, p.body_truncated = $body_truncated,
  p.state = $state, p.author_provider = $author_provider,
  p.author_identity_key = $author_identity_key,
  p.created_at = $created_at, p.merged_at = $merged_at,
  p.head_sha = $head_sha, p.base_branch = $base_branch
WITH p
MATCH (a:Author {provider: $author_provider, identity_key: $author_identity_key})
MERGE (p)-[:AUTHORED_BY]->(a)
"""

_MERGE_PR_COMMENT_CYPHER = """
MERGE (c:PRComment {id: $id})
ON CREATE SET
  c.project_id = $project_id, c.pr_number = $pr_number,
  c.body_truncated = $body_truncated,
  c.author_provider = $author_provider,
  c.author_identity_key = $author_identity_key,
  c.created_at = $created_at
WITH c
MATCH (p:PR {project_id: $project_id, number: $pr_number})
MERGE (c)-[:COMMENTS_ON]->(p)
WITH c
MATCH (a:Author {provider: $author_provider, identity_key: $author_identity_key})
MERGE (c)-[:AUTHORED_BY]->(a)
"""


async def write_commit_with_author(
    driver: AsyncDriver,
    project_id: str,
    commit_dict: dict,  # type: ignore[type-arg]
    *,
    is_bot: bool,
) -> None:
    """Write Author + Commit + Touched edges idempotently."""
    await driver.execute_query(
        _MERGE_AUTHOR_CYPHER,
        provider="git",
        identity_key=commit_dict["author_email"].lower(),
        email=commit_dict["author_email"].lower(),
        name=commit_dict["author_name"],
        is_bot=is_bot,
        ts=commit_dict["committed_at"],
        project_id=project_id,
    )
    if commit_dict["committer_email"] != commit_dict["author_email"]:
        await driver.execute_query(
            _MERGE_AUTHOR_CYPHER,
            provider="git",
            identity_key=commit_dict["committer_email"].lower(),
            email=commit_dict["committer_email"].lower(),
            name=commit_dict["committer_name"],
            is_bot=is_bot,
            ts=commit_dict["committed_at"],
            project_id=project_id,
        )

    await driver.execute_query(
        _MERGE_COMMIT_CYPHER,
        sha=commit_dict["sha"],
        project_id=project_id,
        author_provider="git",
        author_identity_key=commit_dict["author_email"].lower(),
        committer_provider="git",
        committer_identity_key=commit_dict["committer_email"].lower(),
        message_subject=commit_dict["message_subject"],
        message_full_truncated=commit_dict["message_full_truncated"],
        committed_at=commit_dict["committed_at"],
        parents=list(commit_dict["parents"]),
    )

    if commit_dict["touched_files"]:
        await driver.execute_query(
            _MERGE_TOUCHED_CYPHER,
            files=commit_dict["touched_files"],
            project_id=project_id,
            sha=commit_dict["sha"],
        )


async def write_pr(
    driver: AsyncDriver,
    project_id: str,
    pr_dict: dict,  # type: ignore[type-arg]
    author_identity_key: str,
    author_provider: str,
    *,
    is_bot: bool,
) -> None:
    """Write Author + PR node + AUTHORED_BY edge idempotently."""
    from datetime import datetime

    ts: datetime = (
        pr_dict.get("created_at") or pr_dict.get("merged_at") or datetime.now()
    )
    await driver.execute_query(
        _MERGE_AUTHOR_CYPHER,
        provider=author_provider,
        identity_key=author_identity_key,
        email=pr_dict.get("author_email", ""),
        name=pr_dict.get("author_name", ""),
        is_bot=is_bot,
        ts=ts,
        project_id=project_id,
    )
    await driver.execute_query(
        _MERGE_PR_CYPHER,
        project_id=project_id,
        number=pr_dict["number"],
        title=pr_dict.get("title", ""),
        body_truncated=pr_dict.get("body_truncated", ""),
        state=pr_dict.get("state", "open"),
        author_provider=author_provider,
        author_identity_key=author_identity_key,
        created_at=pr_dict.get("created_at"),
        merged_at=pr_dict.get("merged_at"),
        head_sha=pr_dict.get("head_sha"),
        base_branch=pr_dict.get("base_branch", ""),
    )


async def write_pr_comment(
    driver: AsyncDriver,
    project_id: str,
    comment_dict: dict,  # type: ignore[type-arg]
    author_identity_key: str,
    author_provider: str,
    *,
    is_bot: bool,
) -> None:
    """Write Author + PRComment node + edges idempotently."""
    from datetime import datetime

    ts: datetime = comment_dict.get("created_at") or datetime.now()
    await driver.execute_query(
        _MERGE_AUTHOR_CYPHER,
        provider=author_provider,
        identity_key=author_identity_key,
        email=comment_dict.get("author_email", ""),
        name=comment_dict.get("author_name", ""),
        is_bot=is_bot,
        ts=ts,
        project_id=project_id,
    )
    await driver.execute_query(
        _MERGE_PR_COMMENT_CYPHER,
        id=comment_dict["id"],
        project_id=project_id,
        pr_number=comment_dict["pr_number"],
        body_truncated=comment_dict.get("body_truncated", ""),
        author_provider=author_provider,
        author_identity_key=author_identity_key,
        created_at=ts,
    )
