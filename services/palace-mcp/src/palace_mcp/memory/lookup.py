"""palace.memory.lookup implementation.

- Filters resolved to parameterized Cypher WHERE clauses (filters.py).
- Project resolved to group_ids list via resolve_group_ids (projects.py).
- Read queries via session.execute_read (managed read transaction).
- Related-entity expansion: empty in N+1a; arrives with GIM-77 bridge edges.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from neo4j import AsyncDriver, AsyncManagedTransaction

from palace_mcp.memory.filters import EntityType, resolve_filters
from palace_mcp.memory.projects import resolve_group_ids
from palace_mcp.memory.schema import (
    LookupRequest,
    LookupResponse,
    LookupResponseItem,
)
from palace_mcp.pagination import pagination_envelope

logger = logging.getLogger(__name__)

# Related-entity fragments per entity type.
# Empty in N+1a — cross-entity traversals arrive with GIM-77 (DEFINES/CALLS)
# and N+1c (TOUCHES/MODIFIES). Do not add ad-hoc Cypher here prematurely.
_RELATED_FRAGMENTS: dict[EntityType, str] = {}


def _serialize_props(props: dict[str, Any]) -> dict[str, Any]:
    """Convert neo4j temporal/spatial types to JSON-safe primitives."""
    out: dict[str, Any] = {}
    for k, v in props.items():
        if hasattr(v, "iso_format"):
            out[k] = v.iso_format()
        elif isinstance(v, (list, tuple)):
            out[k] = [x.iso_format() if hasattr(x, "iso_format") else x for x in v]
        else:
            out[k] = v
    return out


_ALLOWED_ORDER_COLUMNS = {"created_at", "updated_at", "name"}


def _safe_order_by(order_by: str) -> tuple[str, str]:
    """Parse a user ``order_by`` (e.g. ``"created_at desc"``) into (column, direction).

    Whitelists the column (defends against Cypher injection via interpolation) and
    parses an optional ASC/DESC direction. Falls back to ``("created_at", "DESC")``
    for anything unrecognised so the query is always valid and never raises.
    """
    tokens = (order_by or "").strip().split()
    column = tokens[0] if tokens else "created_at"
    direction = tokens[1].upper() if len(tokens) > 1 else "DESC"
    if column not in _ALLOWED_ORDER_COLUMNS:
        column = "created_at"
    if direction not in {"ASC", "DESC"}:
        direction = "DESC"
    return column, direction


def _build_query(
    entity_type: EntityType,
    where_clauses: list[str],
    order_by: str,
    limit: int,
    offset: int = 0,
) -> str:
    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    order_col, order_dir = _safe_order_by(order_by)
    # order_col/order_dir are whitelisted; limit/offset are validated ints.
    return f"""
        MATCH (n:{entity_type})
        {where}
        ORDER BY n.{order_col} {order_dir}
        SKIP {offset}
        LIMIT {limit}
        RETURN n AS node
    """


def _count_query(entity_type: EntityType, where_clauses: list[str]) -> str:
    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    return f"MATCH (n:{entity_type}) {where} RETURN count(n) AS c"


async def perform_lookup(
    driver: AsyncDriver,
    req: LookupRequest,
    default_group_id: str,
) -> LookupResponse:
    where_clauses, params, unknown = resolve_filters(req.entity_type, dict(req.filters))
    for k in unknown:
        logger.warning(
            "query.lookup.unknown_filter",
            extra={"entity_type": req.entity_type, "filter_key": k},
        )

    t0 = time.monotonic()

    async def _read(tx: AsyncManagedTransaction) -> tuple[list[dict[str, Any]], int]:
        group_ids = await resolve_group_ids(
            tx, req.project, default_group_id=default_group_id
        )
        all_clauses = ["n.group_id IN $group_ids"] + where_clauses
        all_params = {**params, "group_ids": group_ids}

        query = _build_query(
            req.entity_type, all_clauses, req.order_by, req.limit, req.offset
        )
        count_q = _count_query(req.entity_type, all_clauses)

        result = await tx.run(query, **all_params)
        rows: list[dict[str, Any]] = [r.data() async for r in result]
        count_result = await tx.run(count_q, **all_params)
        count_row = await count_result.single()
        count_val = int(count_row["c"]) if count_row else 0
        return rows, count_val

    async with driver.session() as session:
        rows, total = await session.execute_read(_read)

    items: list[LookupResponseItem] = []
    for row in rows:
        node = row["node"]
        props = _serialize_props(dict(node))
        node_id = props.get("uuid") or props.get("id", "")
        props.pop("group_id", None)
        items.append(
            LookupResponseItem(
                id=str(node_id),
                type=req.entity_type,
                properties=props,
                related={},
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
        f"unknown filter '{k}' for entity_type '{req.entity_type}' — ignored"
        for k in unknown
    ]
    page = pagination_envelope(total=total, returned=len(items), offset=req.offset)
    return LookupResponse(
        items=items,
        total_matched=total,
        query_ms=query_ms,
        warnings=warnings,
        total=page["total"],
        returned=page["returned"],
        offset=page["offset"],
        has_more=page["has_more"],
        next_offset=page.get("next_offset"),
        truncated=page["truncated"],
        truncated_reason=page.get("truncated_reason"),
    )
