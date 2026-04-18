"""Ingest orchestrator. Fetches from paperclip, transforms, upserts via
managed write transactions (idempotent), GC on clean success.

`run_ingest` is the single entry point. Accepts a configured
PaperclipClient and an AsyncDriver — construction happens in the CLI.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from neo4j import AsyncDriver, AsyncManagedTransaction

from palace_mcp.ingest.paperclip_client import PaperclipClient
from palace_mcp.ingest.transform import (
    transform_agent,
    transform_comment,
    transform_issue,
)
from palace_mcp.memory import cypher

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _write_upsert_agents(
    tx: AsyncManagedTransaction, batch: list[dict[str, Any]]
) -> None:
    await tx.run(cypher.UPSERT_AGENTS, batch=batch)


async def _write_upsert_issues(
    tx: AsyncManagedTransaction, batch: list[dict[str, Any]]
) -> None:
    await tx.run(cypher.UPSERT_ISSUES, batch=batch)


async def _write_upsert_comments(
    tx: AsyncManagedTransaction, batch: list[dict[str, Any]]
) -> None:
    await tx.run(cypher.UPSERT_COMMENTS, batch=batch)


async def _write_gc(tx: AsyncManagedTransaction, *, label: str, cutoff: str) -> None:
    # Label is whitelisted (Issue|Comment|Agent) — not user input.
    query = cypher.GC_BY_LABEL.format(label=label)
    await tx.run(query, cutoff=cutoff)


async def _write_create_ingest_run(
    tx: AsyncManagedTransaction, *, run_id: str, started_at: str, source: str
) -> None:
    await tx.run(
        cypher.CREATE_INGEST_RUN, id=run_id, started_at=started_at, source=source
    )


async def _write_finalize_ingest_run(
    tx: AsyncManagedTransaction,
    *,
    run_id: str,
    finished_at: str,
    duration_ms: int,
    errors: list[str],
) -> None:
    await tx.run(
        cypher.FINALIZE_INGEST_RUN,
        id=run_id,
        finished_at=finished_at,
        duration_ms=duration_ms,
        errors=errors,
    )


async def run_ingest(
    *, client: PaperclipClient, driver: AsyncDriver, source: str = "paperclip"
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    started_at = _utcnow_iso()
    started_monotonic = time.monotonic()
    errors: list[str] = []
    finished_at = started_at

    logger.info("ingest.start", extra={"source": source, "run_id": run_id})

    async with driver.session() as session:
        await session.execute_write(
            _write_create_ingest_run,
            run_id=run_id,
            started_at=started_at,
            source=source,
        )

    try:
        issues_raw = await client.list_issues()
        agents_raw = await client.list_agents()
        logger.info(
            "ingest.fetch.issues", extra={"count": len(issues_raw), "source": source}
        )
        logger.info(
            "ingest.fetch.agents", extra={"count": len(agents_raw), "source": source}
        )

        comments_raw: list[dict[str, Any]] = []
        for issue in issues_raw:
            ic = await client.list_comments_for_issue(issue["id"])
            comments_raw.extend(ic)
        logger.info(
            "ingest.fetch.comments",
            extra={"count": len(comments_raw), "source": source},
        )

        issues_batch = [transform_issue(x, run_started=started_at) for x in issues_raw]
        agents_batch = [transform_agent(x, run_started=started_at) for x in agents_raw]
        comments_batch = [
            transform_comment(x, run_started=started_at) for x in comments_raw
        ]

        async with driver.session() as session:
            t0 = time.monotonic()
            await session.execute_write(_write_upsert_agents, agents_batch)
            logger.info(
                "ingest.upsert",
                extra={
                    "type": "Agent",
                    "count": len(agents_batch),
                    "duration_ms": int((time.monotonic() - t0) * 1000),
                },
            )

            t0 = time.monotonic()
            await session.execute_write(_write_upsert_issues, issues_batch)
            logger.info(
                "ingest.upsert",
                extra={
                    "type": "Issue",
                    "count": len(issues_batch),
                    "duration_ms": int((time.monotonic() - t0) * 1000),
                },
            )

            t0 = time.monotonic()
            await session.execute_write(_write_upsert_comments, comments_batch)
            logger.info(
                "ingest.upsert",
                extra={
                    "type": "Comment",
                    "count": len(comments_batch),
                    "duration_ms": int((time.monotonic() - t0) * 1000),
                },
            )

            # GC only on clean success — partial failure leaves stale data.
            for label in ("Issue", "Comment", "Agent"):
                await session.execute_write(_write_gc, label=label, cutoff=started_at)
                logger.info("ingest.gc", extra={"type": label})
    except Exception as e:  # noqa: BLE001 — re-raised after logging
        errors.append(f"{type(e).__name__}: {e}")
        logger.exception("ingest.error", extra={"source": source, "run_id": run_id})
        raise
    finally:
        finished_at = _utcnow_iso()
        duration_ms = int((time.monotonic() - started_monotonic) * 1000)
        async with driver.session() as session:
            await session.execute_write(
                _write_finalize_ingest_run,
                run_id=run_id,
                finished_at=finished_at,
                duration_ms=duration_ms,
                errors=errors,
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
