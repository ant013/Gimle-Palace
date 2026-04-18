"""Ingest orchestrator — graphiti-core substrate (N+1a).

Replaces AsyncDriver/Cypher with graphiti.nodes/edges namespace API.
`run_ingest` is the single entry point; accepts PaperclipClient +
Graphiti instance (construction lives in the CLI / FastAPI lifespan).

Zero raw Cypher — spec §9 acceptance.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from graphiti_core import Graphiti

from palace_mcp.ingest.builders import (
    GROUP_ID,
    build_agent_node,
    build_assigned_to_edge,
    build_authored_by_edge,
    build_comment_node,
    build_issue_node,
    build_on_edge,
)
from palace_mcp.ingest.paperclip_client import PaperclipClient
from palace_mcp.ingest.upsert import (
    UpsertResult,
    gc_orphans,
    invalidate_stale_assignments,
    upsert_with_change_detection,
)
from palace_mcp.memory.ingest_run import write_ingest_run

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_ingest(
    *,
    client: PaperclipClient,
    graphiti: Graphiti,
    source: str = "paperclip",
    group_id: str = GROUP_ID,
) -> dict[str, Any]:
    """Run a full ingest pass against the paperclip API.

    Returns a summary dict compatible with the N+0 contract so that
    callers (CLI, palace.memory.health) need no changes.
    """
    run_id = str(uuid.uuid4())
    started_at = _utcnow_iso()
    started_monotonic = time.monotonic()
    errors: list[str] = []
    finished_at = started_at

    logger.info("ingest.start", extra={"source": source, "run_id": run_id})

    try:
        # ── Fetch ─────────────────────────────────────────────────────────────
        issues_raw = await client.list_issues()
        agents_raw = await client.list_agents()
        logger.info("ingest.fetch.issues", extra={"count": len(issues_raw)})
        logger.info("ingest.fetch.agents", extra={"count": len(agents_raw)})

        comments_raw: list[dict[str, Any]] = []
        for issue in issues_raw:
            ic = await client.list_comments_for_issue(issue["id"])
            comments_raw.extend(ic)
        logger.info("ingest.fetch.comments", extra={"count": len(comments_raw)})

        # ── Upsert agents ─────────────────────────────────────────────────────
        agent_counters: dict[str, int] = {r.value: 0 for r in UpsertResult}
        t0 = time.monotonic()
        for agent_raw in agents_raw:
            node = build_agent_node(agent_raw, run_started=started_at, group_id=group_id)
            result = await upsert_with_change_detection(graphiti, node)
            agent_counters[result.value] += 1
        logger.info(
            "ingest.upsert",
            extra={
                "type": "Agent",
                "count": len(agents_raw),
                "inserted": agent_counters[UpsertResult.INSERTED.value],
                "skipped": agent_counters[UpsertResult.SKIPPED_UNCHANGED.value],
                "re_embedded": agent_counters[UpsertResult.RE_EMBEDDED.value],
                "duration_ms": int((time.monotonic() - t0) * 1000),
            },
        )

        # ── Upsert issues + ASSIGNED_TO edges ─────────────────────────────────
        issue_counters: dict[str, int] = {r.value: 0 for r in UpsertResult}
        t0 = time.monotonic()
        for issue_raw in issues_raw:
            node = build_issue_node(issue_raw, run_started=started_at, group_id=group_id)
            result = await upsert_with_change_detection(graphiti, node)
            issue_counters[result.value] += 1

            assignee_id: str | None = issue_raw.get("assigneeAgentId")
            invalidated = await invalidate_stale_assignments(
                graphiti,
                issue_uuid=issue_raw["id"],
                new_agent_uuid=assignee_id,
                run_started=started_at,
            )
            if invalidated:
                logger.info(
                    "ingest.edges.invalidated",
                    extra={"issue_id": issue_raw["id"], "count": invalidated},
                )

            if assignee_id:
                edge = build_assigned_to_edge(
                    issue_uuid=issue_raw["id"],
                    agent_uuid=assignee_id,
                    run_started=started_at,
                    group_id=group_id,
                )
                await graphiti.edges.entity.save(edge)

        logger.info(
            "ingest.upsert",
            extra={
                "type": "Issue",
                "count": len(issues_raw),
                "inserted": issue_counters[UpsertResult.INSERTED.value],
                "skipped": issue_counters[UpsertResult.SKIPPED_UNCHANGED.value],
                "re_embedded": issue_counters[UpsertResult.RE_EMBEDDED.value],
                "duration_ms": int((time.monotonic() - t0) * 1000),
            },
        )

        # ── Upsert comments + ON / AUTHORED_BY edges ──────────────────────────
        comment_counters: dict[str, int] = {r.value: 0 for r in UpsertResult}
        t0 = time.monotonic()
        for comment_raw in comments_raw:
            node = build_comment_node(comment_raw, run_started=started_at, group_id=group_id)
            result = await upsert_with_change_detection(graphiti, node)
            comment_counters[result.value] += 1

            issue_id: str = comment_raw.get("issueId") or ""
            comment_created_at: str = comment_raw.get("createdAt") or started_at

            if issue_id:
                on_edge = build_on_edge(
                    comment_uuid=comment_raw["id"],
                    issue_uuid=issue_id,
                    comment_created_at=comment_created_at,
                    run_started=started_at,
                    group_id=group_id,
                )
                await graphiti.edges.entity.save(on_edge)

            author_id: str | None = comment_raw.get("authorAgentId")
            if author_id:
                authored_edge = build_authored_by_edge(
                    comment_uuid=comment_raw["id"],
                    agent_uuid=author_id,
                    comment_created_at=comment_created_at,
                    run_started=started_at,
                    group_id=group_id,
                )
                await graphiti.edges.entity.save(authored_edge)

        logger.info(
            "ingest.upsert",
            extra={
                "type": "Comment",
                "count": len(comments_raw),
                "inserted": comment_counters[UpsertResult.INSERTED.value],
                "skipped": comment_counters[UpsertResult.SKIPPED_UNCHANGED.value],
                "re_embedded": comment_counters[UpsertResult.RE_EMBEDDED.value],
                "duration_ms": int((time.monotonic() - t0) * 1000),
            },
        )

        # ── GC — only on clean success ────────────────────────────────────────
        gc_count = await gc_orphans(graphiti, group_id=group_id, cutoff=started_at)
        logger.info("ingest.gc", extra={"deleted": gc_count})

    except Exception as e:  # noqa: BLE001 — re-raised after audit trail
        errors.append(f"{type(e).__name__}: {e}")
        logger.exception("ingest.error", extra={"source": source, "run_id": run_id})
        raise
    finally:
        finished_at = _utcnow_iso()
        duration_ms = int((time.monotonic() - started_monotonic) * 1000)
        try:
            await write_ingest_run(
                graphiti,
                run_id=run_id,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                errors=errors,
                group_id=group_id,
                source=source,
            )
        except Exception:  # noqa: BLE001 — audit trail must not suppress original error
            logger.warning(
                "ingest.run_record.failed",
                extra={"run_id": run_id},
                exc_info=True,
            )
        logger.info(
            "ingest.finish",
            extra={
                "source": source,
                "run_id": run_id,
                "duration_ms": duration_ms,
                "errors": errors,
            },
        )

    return {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "errors": errors,
    }
