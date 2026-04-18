"""Upsert helpers using graphiti-core namespace API.

Implements:
- text_hash-based change detection (avoid re-embed cost)
- ASSIGNED_TO bi-temporal invalidation per spec §4.4
- gc_orphans via delete_by_uuids with single-UUID fallback per WARNING from CodeReview

Zero raw Cypher — spec §9 acceptance.
"""

from __future__ import annotations

import enum
import logging
from datetime import datetime

from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode

logger = logging.getLogger(__name__)

PAPERCLIP_LABELS = {"Issue", "Comment", "Agent"}


class UpsertResult(str, enum.Enum):
    INSERTED = "inserted"
    SKIPPED_UNCHANGED = "skipped_unchanged"
    RE_EMBEDDED = "re_embedded"


async def upsert_with_change_detection(
    graphiti: Graphiti, node: EntityNode
) -> UpsertResult:
    """Save a node, skipping re-embed if text_hash matches stored value.

    Returns UpsertResult to signal what happened (used for log counters and
    observability).
    """
    existing: EntityNode | None = None
    try:
        existing = await graphiti.nodes.entity.get_by_uuid(node.uuid)
    except (LookupError, ValueError, RuntimeError, KeyError):
        # Node does not exist — insert (triggers embed via save())
        pass
    except Exception:  # noqa: BLE001 — graphiti may raise arbitrary exception types
        logger.warning(
            "upsert_with_change_detection: unexpected error on get_by_uuid for %s",
            node.uuid,
            exc_info=True,
        )

    if existing is None:
        await graphiti.nodes.entity.save(node)
        return UpsertResult.INSERTED

    if existing.attributes.get("text_hash") == node.attributes.get("text_hash"):
        # Unchanged — refresh palace_last_seen_at on existing object only
        existing.attributes["palace_last_seen_at"] = node.attributes["palace_last_seen_at"]
        await graphiti.nodes.entity.save(existing)
        return UpsertResult.SKIPPED_UNCHANGED

    # Text changed — full re-embed via save() of new node
    await graphiti.nodes.entity.save(node)
    return UpsertResult.RE_EMBEDDED


async def invalidate_stale_assignments(
    graphiti: Graphiti,
    issue_uuid: str,
    new_agent_uuid: str | None,
    run_started: str,
) -> tuple[int, bool]:
    """Invalidate stale ASSIGNED_TO edges via graphiti.edges.entity.save.

    Returns (count_invalidated, has_active_same_assignee).
    has_active_same_assignee=True when a non-invalidated ASSIGNED_TO edge for
    new_agent_uuid already exists — caller must skip creating a duplicate edge
    to satisfy spec §4.3 idempotency.

    Zero raw Cypher — spec §9 acceptance.
    """
    invalidated = 0
    has_active_same_assignee = False
    run_started_dt = datetime.fromisoformat(run_started)
    edges = await graphiti.edges.entity.get_by_node_uuid(issue_uuid)
    for edge in edges:
        if edge.name != "ASSIGNED_TO":
            continue
        if edge.invalid_at is not None:
            continue  # already invalidated
        if edge.target_node_uuid == new_agent_uuid:
            has_active_same_assignee = True  # active edge for same agent — keep
            continue
        edge.invalid_at = run_started_dt
        await graphiti.edges.entity.save(edge)
        invalidated += 1
    return invalidated, has_active_same_assignee


async def gc_orphans(graphiti: Graphiti, *, group_id: str, cutoff: str) -> int:
    """Delete paperclip-sourced nodes whose palace_last_seen_at < cutoff.

    Uses graphiti.nodes.entity.get_by_group_ids + Python filter +
    delete_by_uuids (with single-UUID loop fallback if method absent per
    WARNING from CodeReviewer). Zero raw Cypher per spec §9 acceptance.

    Timestamps are compared as datetime objects (not strings) to handle
    differing ISO 8601 suffixes (Z vs +00:00, fractional seconds).
    """
    cutoff_dt = datetime.fromisoformat(cutoff)
    all_nodes = await graphiti.nodes.entity.get_by_group_ids([group_id])
    stale_uuids: list[str] = []
    for n in all_nodes:
        if n.attributes.get("source") != "paperclip":
            continue
        if not any(lbl in PAPERCLIP_LABELS for lbl in n.labels):
            continue
        last_seen_raw: str | None = n.attributes.get("palace_last_seen_at")
        if not last_seen_raw:
            continue
        try:
            last_seen_dt = datetime.fromisoformat(last_seen_raw)
        except ValueError:
            logger.warning(
                "gc_orphans: unparseable palace_last_seen_at %r on node %s — skipping",
                last_seen_raw,
                n.uuid,
            )
            continue
        if last_seen_dt < cutoff_dt:
            stale_uuids.append(n.uuid)
    if not stale_uuids:
        return 0

    if hasattr(graphiti.nodes.entity, "delete_by_uuids"):
        await graphiti.nodes.entity.delete_by_uuids(stale_uuids)
    elif hasattr(graphiti.nodes.entity, "delete_by_uuid"):
        # Fallback: loop single-UUID delete (gap #5 from mini-gap spike)
        logger.warning(
            "ingest.gc.fallback",
            extra={"reason": "delete_by_uuids absent, using loop fallback"},
        )
        for uid in stale_uuids:
            await graphiti.nodes.entity.delete_by_uuid(uid)
    else:
        logger.error(
            "ingest.gc.unavailable",
            extra={"reason": "neither delete_by_uuids nor delete_by_uuid found"},
        )
        return 0

    logger.info("ingest.gc.deleted", extra={"count": len(stale_uuids)})
    return len(stale_uuids)
