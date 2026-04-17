"""palace.memory.health implementation.

Queries Neo4j for:
- Entity counts (Issue / Comment / Agent)
- Latest IngestRun metadata (started_at, finished_at, duration_ms, errors)
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncDriver, AsyncManagedTransaction

from palace_mcp.memory.cypher import ENTITY_COUNTS, LATEST_INGEST_RUN
from palace_mcp.memory.schema import HealthResponse

logger = logging.getLogger(__name__)


async def get_health(driver: AsyncDriver) -> HealthResponse:
    """Return health data: reachability, entity counts, last ingest run info."""
    try:
        await driver.verify_connectivity()
    except Exception as exc:
        logger.warning("palace.memory.health neo4j unreachable: %s", exc)
        return HealthResponse(neo4j_reachable=False, entity_counts={})

    async def _read(tx: AsyncManagedTransaction) -> tuple[dict[str, int], dict[str, Any] | None]:
        counts_result = await tx.run(ENTITY_COUNTS)
        counts: dict[str, int] = {}
        async for row in counts_result:
            counts[row["type"]] = int(row["count"])

        ingest_result = await tx.run(LATEST_INGEST_RUN, source="paperclip")
        ingest_row = await ingest_result.single()
        ingest_data: dict[str, Any] | None = dict(ingest_row["r"]) if ingest_row else None
        return counts, ingest_data

    async with driver.session() as session:
        entity_counts, ingest = await session.execute_read(_read)

    return HealthResponse(
        neo4j_reachable=True,
        entity_counts=entity_counts,
        last_ingest_started_at=ingest.get("started_at") if ingest else None,
        last_ingest_finished_at=ingest.get("finished_at") if ingest else None,
        last_ingest_duration_ms=ingest.get("duration_ms") if ingest else None,
        last_ingest_errors=list(ingest.get("errors") or []) if ingest else [],
    )
