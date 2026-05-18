"""ADR decision bridge — creates (:Decision)-[:CITED_BY]->(:AdrDocument) edge (GIM-274).

AD-D5: manual bridge — caller passes decision_id param on write().
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncDriver

logger = logging.getLogger(__name__)

_CHECK_DECISION = "MATCH (d:Decision {uuid: $decision_id}) RETURN d.uuid"
_CREATE_EDGE = """
MATCH (d:Decision {uuid: $decision_id})
MATCH (a:AdrDocument {slug: $slug})
MERGE (d)-[:CITED_BY]->(a)
"""


async def create_cited_by_edge(
    decision_id: str,
    slug: str,
    driver: AsyncDriver,
) -> dict[str, Any]:
    """Create (:Decision)-[:CITED_BY]->(:AdrDocument) edge. Validates Decision exists first."""
    async with driver.session() as session:
        result = await session.run(_CHECK_DECISION, decision_id=decision_id)
        record = await result.single()
        if record is None:
            return {
                "ok": False,
                "error_code": "decision_not_found",
                "message": f"Decision {decision_id!r} not found; create it via palace.memory.decide",
            }
        await session.run(_CREATE_EDGE, decision_id=decision_id, slug=slug)

    logger.info("adr.bridge.cited_by decision_id=%s slug=%s", decision_id, slug)
    return {"ok": True}
