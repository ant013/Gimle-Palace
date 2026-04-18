"""palace.memory.lookup implementation.

- Filters resolved to parameterized Cypher WHERE clauses (filters.py).
- Read queries via session.execute_read (managed read transaction).
- Related-entity expansion one hop per entity type.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from neo4j import AsyncDriver, AsyncManagedTransaction

from palace_mcp.memory.filters import resolve_filters
from palace_mcp.memory.schema import (
    EntityType,
    LookupRequest,
    LookupResponse,
    LookupResponseItem,
)

logger = logging.getLogger(__name__)

# One-hop related-entity fragments per entity type, returned in `related`.
# Issue fragment uses a CALL subquery to traverse AUTHORED_BY per comment
# so that author_name (nullable — human users are not Agent nodes) is included
# per spec §5.1.
_RELATED_FRAGMENTS: dict[EntityType, str] = {
    "Issue": """
        OPTIONAL MATCH (n)-[:ASSIGNED_TO]->(assignee:Agent)
        CALL (n) {
            OPTIONAL MATCH (c:Comment)-[:ON]->(n)
            OPTIONAL MATCH (c)-[:AUTHORED_BY]->(author:Agent)
            RETURN c, author
            ORDER BY c.source_created_at DESC
            LIMIT 50
        }
        WITH n, assignee,
             collect(CASE WHEN c IS NULL THEN null ELSE {
                 id: c.id, body: c.body,
                 source_created_at: c.source_created_at,
                 author_name: author.name
             } END) AS comments_raw
        WITH n, assignee,
             [x IN comments_raw WHERE x IS NOT NULL] AS comments
        RETURN n AS node,
            CASE WHEN assignee IS NULL THEN null
                 ELSE {id: assignee.id, name: assignee.name, url_key: assignee.url_key}
            END AS assignee,
            comments
    """,
    "Comment": """
        OPTIONAL MATCH (n)-[:ON]->(issue:Issue)
        OPTIONAL MATCH (n)-[:AUTHORED_BY]->(author:Agent)
        RETURN
            n AS node,
            CASE WHEN issue IS NULL THEN null
                 ELSE {id: issue.id, key: issue.key, title: issue.title, status: issue.status}
            END AS issue,
            CASE WHEN author IS NULL THEN null
                 ELSE {id: author.id, name: author.name}
            END AS author
    """,
    "Agent": "RETURN n AS node",
}


def _build_query(
    entity_type: EntityType, where_clauses: list[str], order_by: str, limit: int
) -> str:
    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    related = _RELATED_FRAGMENTS[entity_type]
    # NOTE: order_by and limit are restricted to safe values by LookupRequest schema.
    # order_by is a Literal union of known column names; limit is int 1-100.
    return f"""
        MATCH (n:{entity_type})
        {where}
        ORDER BY n.{order_by} DESC
        LIMIT {limit}
        CALL (n) {{
            {related}
        }}
        RETURN *
    """


def _count_query(entity_type: EntityType, where_clauses: list[str]) -> str:
    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    return f"MATCH (n:{entity_type}) {where} RETURN count(n) AS c"


async def perform_lookup(driver: AsyncDriver, req: LookupRequest) -> LookupResponse:
    where_clauses, params, unknown = resolve_filters(req.entity_type, dict(req.filters))
    # group_id always scopes the query — prepend so it's the first WHERE predicate.
    where_clauses.insert(0, "n.group_id = $group_id")
    params["group_id"] = req.group_id
    for k in unknown:
        logger.warning(
            "query.lookup.unknown_filter",
            extra={"entity_type": req.entity_type, "filter_key": k},
        )

    query = _build_query(req.entity_type, where_clauses, req.order_by, req.limit)
    count_query = _count_query(req.entity_type, where_clauses)

    t0 = time.monotonic()

    async def _read(tx: AsyncManagedTransaction) -> tuple[list[dict[str, Any]], int]:
        result = await tx.run(query, **params)
        rows: list[dict[str, Any]] = [r.data() async for r in result]
        count_result = await tx.run(count_query, **params)
        count_row = await count_result.single()
        count_val = int(count_row["c"]) if count_row else 0
        return rows, count_val

    async with driver.session() as session:
        rows, total = await session.execute_read(_read)

    items: list[LookupResponseItem] = []
    for row in rows:
        node = row["node"]
        related: dict[str, dict[str, Any] | list[dict[str, Any]] | None] = {}
        if req.entity_type == "Issue":
            related["assignee"] = row.get("assignee")
            related["comments"] = row.get("comments") or []
        elif req.entity_type == "Comment":
            related["issue"] = row.get("issue")
            related["author"] = row.get("author")
        props = dict(node)
        props.pop("group_id", None)
        items.append(
            LookupResponseItem(
                id=node["id"],
                type=req.entity_type,
                properties=props,
                related=related,
            )
        )

    query_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "query.lookup",
        extra={
            "entity_type": req.entity_type,
            "filters": list(params.keys()),
            "matched": len(items),
            "total_matched": total,
            "duration_ms": query_ms,
        },
    )
    warnings = [
        f"unknown filter '{k}' for entity_type '{req.entity_type}' \u2014 ignored"
        for k in unknown
    ]
    return LookupResponse(
        items=items, total_matched=total, query_ms=query_ms, warnings=warnings
    )
