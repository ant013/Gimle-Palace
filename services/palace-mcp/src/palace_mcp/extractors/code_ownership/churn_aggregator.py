"""Recency-weighted churn aggregation from existing :Commit graph.

Reversed-direction Cypher (start from :File PK), partial server-side
aggregation by raw a.identity_key (returns timestamps + count). Mailmap
canonicalization and decay computation happen client-side. Bot filter
is doubled: server-side via NOT a.is_bot AND post-mailmap via
bot_keys (catches mailmap-aliased bots).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import datetime, timezone

from neo4j import AsyncDriver

from palace_mcp.extractors.code_ownership.mailmap import MailmapResolver
from palace_mcp.extractors.code_ownership.models import ChurnShare

# Reversed direction: starts from :File PK lookup (UNIQUE on
# (project_id, path) per GIM-186). Server-side pre-aggregation by raw
# identity_key returns timestamps + count instead of N rows.
_CHURN_CYPHER = """
UNWIND $paths AS p
MATCH (f:File {project_id: $project_id, path: p})<-[:TOUCHED]-(c:Commit)
WHERE NOT c.is_merge
MATCH (c)-[:AUTHORED_BY]->(a:Author)
WHERE NOT a.is_bot
WITH p, a.identity_key AS raw_id, a.name AS raw_name,
     collect(c.committed_at) AS timestamps
RETURN p, raw_id, raw_name, timestamps, size(timestamps) AS commit_count
"""


async def aggregate_churn(
    driver: AsyncDriver,
    *,
    project_id: str,
    paths: Iterable[str],
    mailmap: MailmapResolver,
    bot_keys: set[str],
    decay_days: float,
    known_author_ids: set[str],
) -> dict[str, dict[str, ChurnShare]]:
    """Return {path: {canonical_id: ChurnShare}} for the given paths."""
    paths_list = list(paths)
    if not paths_list:
        return {}

    now = datetime.now(tz=timezone.utc)
    decay_seconds = decay_days * 86400.0

    async with driver.session() as session:
        result = await session.run(
            _CHURN_CYPHER,
            project_id=project_id,
            paths=paths_list,
        )
        records = await result.data()

    out: dict[str, dict[str, ChurnShare]] = {}
    for r in records:
        path = r["p"]
        raw_id = r["raw_id"]
        raw_name = r["raw_name"]
        timestamps = r["timestamps"]
        cn, ce = mailmap.canonicalize(raw_name, raw_id)
        canonical_id = ce
        if canonical_id in bot_keys:
            continue
        # Convert Neo4j datetime → Python datetime
        py_ts: list[datetime] = []
        for t in timestamps:
            if isinstance(t, datetime):
                py_ts.append(t if t.tzinfo else t.replace(tzinfo=timezone.utc))
            elif hasattr(t, "to_native"):
                native = t.to_native()
                py_ts.append(
                    native
                    if native.tzinfo
                    else native.replace(tzinfo=timezone.utc)
                )
            elif isinstance(t, str):
                py_ts.append(datetime.fromisoformat(t))
        if not py_ts:
            continue
        recency_score = sum(
            math.exp(-(now - ts).total_seconds() / decay_seconds)
            for ts in py_ts
        )
        last_touched_at = max(py_ts)
        commit_count = int(r["commit_count"])

        per_path = out.setdefault(path, {})
        existing = per_path.get(canonical_id)
        if existing is None:
            per_path[canonical_id] = ChurnShare(
                canonical_id=canonical_id,
                canonical_name=cn,
                canonical_email=ce,
                recency_score=recency_score,
                last_touched_at=last_touched_at,
                commit_count=commit_count,
            )
        else:
            # Two raw_ids canonicalize to same id (mailmap collapse)
            per_path[canonical_id] = ChurnShare(
                canonical_id=canonical_id,
                canonical_name=cn,
                canonical_email=ce,
                recency_score=existing.recency_score + recency_score,
                last_touched_at=max(existing.last_touched_at, last_touched_at),
                commit_count=existing.commit_count + commit_count,
            )
    return out
