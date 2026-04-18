"""palace.memory.lookup — graphiti-core substrate (N+1a).

Replaces Cypher queries with graphiti namespace API calls.
Filter evaluation moved to Python layer; related-entity expansion
via get_by_node_uuid edge traversal.

Zero raw Cypher — spec §9 acceptance.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode

from palace_mcp.ingest.builders import GROUP_ID
from palace_mcp.memory.schema import (
    EntityType,
    LookupRequest,
    LookupResponse,
    LookupResponseItem,
)

logger = logging.getLogger(__name__)

# Keys that require edge-traversal for filtering (cannot be resolved from
# node attributes alone). These produce a warning and are handled after
# related-entity expansion.
_EDGE_FILTER_KEYS: dict[EntityType, set[str]] = {
    "Issue": {"assignee_name"},
    "Comment": {"issue_key", "author_name"},
    "Agent": set(),
}

# Direct attribute filter keys per entity type (Python attribute comparison).
_DIRECT_FILTER_KEYS: dict[EntityType, set[str]] = {
    "Issue": {"key", "status", "source_updated_at_gte", "source_updated_at_lte"},
    "Comment": {"source_created_at_gte"},
    "Agent": {"name", "url_key"},
}


async def _get_node_safe(graphiti: Graphiti, uuid: str) -> EntityNode | None:
    try:
        return await graphiti.nodes.entity.get_by_uuid(uuid)
    except (LookupError, ValueError, RuntimeError, KeyError):
        return None
    except Exception:  # noqa: BLE001 — graphiti may raise arbitrary types
        logger.warning("_get_node_safe: unexpected error fetching node %s", uuid, exc_info=True)
        return None


def _node_properties(node: EntityNode) -> dict[str, Any]:
    """Return a flat properties dict from node attributes (mirrors N+0 Cypher row)."""
    props = dict(node.attributes)
    # Ensure id is always present from uuid if not in attributes
    props.setdefault("id", node.uuid)
    return props


async def _fetch_related_issue(
    graphiti: Graphiti, node: EntityNode
) -> dict[str, Any]:
    edges = await graphiti.edges.entity.get_by_node_uuid(node.uuid)
    assignee: dict[str, Any] | None = None
    comments: list[dict[str, Any]] = []

    for edge in edges:
        if edge.invalid_at is not None:
            continue

        if edge.name == "ASSIGNED_TO" and edge.source_node_uuid == node.uuid:
            if assignee is None:  # first valid ASSIGNED_TO wins
                agent_node = await _get_node_safe(graphiti, edge.target_node_uuid)
                if agent_node:
                    assignee = {
                        "id": agent_node.attributes.get("id", agent_node.uuid),
                        "name": agent_node.name,
                        "url_key": agent_node.attributes.get("url_key", ""),
                    }

        elif edge.name == "ON" and edge.target_node_uuid == node.uuid:
            comment_node = await _get_node_safe(graphiti, edge.source_node_uuid)
            if comment_node is None:
                continue
            # Get author for this comment
            c_edges = await graphiti.edges.entity.get_by_node_uuid(comment_node.uuid)
            author_name: str | None = None
            for ce in c_edges:
                if (
                    ce.name == "AUTHORED_BY"
                    and ce.source_node_uuid == comment_node.uuid
                    and ce.invalid_at is None
                ):
                    author_node = await _get_node_safe(graphiti, ce.target_node_uuid)
                    if author_node:
                        author_name = author_node.name
                    break
            comments.append(
                {
                    "id": comment_node.attributes.get("id", comment_node.uuid),
                    "body": comment_node.attributes.get("body", ""),
                    "source_created_at": comment_node.attributes.get(
                        "source_created_at", ""
                    ),
                    "author_name": author_name,
                }
            )

    comments.sort(key=lambda c: c.get("source_created_at", ""), reverse=True)
    return {"assignee": assignee, "comments": comments[:50]}


async def _fetch_related_comment(
    graphiti: Graphiti, node: EntityNode
) -> dict[str, Any]:
    edges = await graphiti.edges.entity.get_by_node_uuid(node.uuid)
    issue: dict[str, Any] | None = None
    author: dict[str, Any] | None = None

    for edge in edges:
        if edge.invalid_at is not None:
            continue
        if edge.name == "ON" and edge.source_node_uuid == node.uuid:
            if issue is None:
                issue_node = await _get_node_safe(graphiti, edge.target_node_uuid)
                if issue_node:
                    issue = {
                        "id": issue_node.attributes.get("id", issue_node.uuid),
                        "key": issue_node.attributes.get("key", ""),
                        "title": issue_node.attributes.get("title", ""),
                        "status": issue_node.attributes.get("status", ""),
                    }
        elif edge.name == "AUTHORED_BY" and edge.source_node_uuid == node.uuid:
            if author is None:
                author_node = await _get_node_safe(graphiti, edge.target_node_uuid)
                if author_node:
                    author = {
                        "id": author_node.attributes.get("id", author_node.uuid),
                        "name": author_node.name,
                    }

    return {"issue": issue, "author": author}


def _apply_direct_filter(
    nodes: list[EntityNode], key: str, val: Any
) -> list[EntityNode]:
    """Filter nodes by attribute with gte/lte suffix support."""
    if key.endswith("_gte"):
        attr = key[: -len("_gte")]
        return [n for n in nodes if (n.attributes.get(attr) or "") >= val]
    if key.endswith("_lte"):
        attr = key[: -len("_lte")]
        return [n for n in nodes if (n.attributes.get(attr) or "") <= val]
    return [n for n in nodes if n.attributes.get(key) == val]


def _edge_filter_matches(
    related: dict[str, Any], entity_type: EntityType, edge_filters: dict[str, Any]
) -> bool:
    """Return True if related data satisfies all edge-traversal filters."""
    for key, val in edge_filters.items():
        if entity_type == "Issue" and key == "assignee_name":
            assignee = related.get("assignee")
            if not assignee or assignee.get("name") != val:
                return False
        elif entity_type == "Comment" and key == "issue_key":
            issue = related.get("issue")
            if not issue or issue.get("key") != val:
                return False
        elif entity_type == "Comment" and key == "author_name":
            author = related.get("author")
            if not author or author.get("name") != val:
                return False
    return True


async def perform_lookup(graphiti: Graphiti, req: LookupRequest) -> LookupResponse:
    t0 = time.monotonic()

    direct_allowed = _DIRECT_FILTER_KEYS[req.entity_type]
    edge_allowed = _EDGE_FILTER_KEYS[req.entity_type]
    direct_filters: dict[str, Any] = {}
    edge_filters: dict[str, Any] = {}
    unknown: list[str] = []

    for k, v in req.filters.items():
        if k in direct_allowed:
            direct_filters[k] = v
        elif k in edge_allowed:
            edge_filters[k] = v
        else:
            unknown.append(k)
            logger.warning(
                "query.lookup.unknown_filter",
                extra={"entity_type": req.entity_type, "filter_key": k},
            )

    # ── Fetch all nodes in group, filter by entity type label ─────────────────
    all_nodes = await graphiti.nodes.entity.get_by_group_ids([GROUP_ID])
    nodes = [n for n in all_nodes if req.entity_type in n.labels]

    # ── Apply direct attribute filters ─────────────────────────────────────────
    for key, val in direct_filters.items():
        nodes = _apply_direct_filter(nodes, key, val)

    # ── Sort ───────────────────────────────────────────────────────────────────
    nodes.sort(
        key=lambda n: n.attributes.get(req.order_by, "") or "",
        reverse=True,
    )

    # If no edge filters, we can count before expansion and apply limit early
    if not edge_filters:
        total = len(nodes)
        page_nodes = nodes[: req.limit]
    else:
        # Edge filters require related-data expansion before we can count/limit
        page_nodes = nodes
        total = 0  # computed below after filtering

    # ── Fetch related entities + apply edge filters ───────────────────────────
    items: list[LookupResponseItem] = []
    for node in page_nodes:
        if req.entity_type == "Issue":
            related = await _fetch_related_issue(graphiti, node)
        elif req.entity_type == "Comment":
            related = await _fetch_related_comment(graphiti, node)
        else:
            related = {}

        if edge_filters and not _edge_filter_matches(related, req.entity_type, edge_filters):
            continue

        items.append(
            LookupResponseItem(
                id=node.attributes.get("id", node.uuid),
                type=req.entity_type,
                properties=_node_properties(node),
                related=related,
            )
        )

    if edge_filters:
        total = len(items)
        items = items[: req.limit]

    query_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "query.lookup",
        extra={
            "entity_type": req.entity_type,
            "filters": list(req.filters.keys()),
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
