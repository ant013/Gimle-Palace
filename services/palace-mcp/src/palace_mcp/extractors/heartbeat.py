"""HeartbeatExtractor — diagnostic probe that writes one :ExtractorHeartbeat node."""

from __future__ import annotations

from datetime import datetime, timezone

from palace_mcp.extractors.base import BaseExtractor, ExtractionContext, ExtractorStats

_CYPHER_MERGE = """
MERGE (h:ExtractorHeartbeat {run_id: $run_id})
ON CREATE SET h.ts = $ts, h.extractor = $extractor, h.group_id = $group_id
"""


class HeartbeatExtractor(BaseExtractor):
    name = "heartbeat"
    description = "Diagnostic probe — writes one :ExtractorHeartbeat node to verify Neo4j connectivity."
    constraints = [
        "CREATE CONSTRAINT extractor_heartbeat_id IF NOT EXISTS "
        "FOR (h:ExtractorHeartbeat) REQUIRE h.run_id IS UNIQUE",
    ]
    indexes = [
        "CREATE INDEX extractor_heartbeat_group_id IF NOT EXISTS "
        "FOR (n:ExtractorHeartbeat) ON (n.group_id)",
        "CREATE INDEX extractor_heartbeat_ts IF NOT EXISTS "
        "FOR (n:ExtractorHeartbeat) ON (n.ts)",
    ]

    async def extract(self, ctx: ExtractionContext) -> ExtractorStats:
        ts = datetime.now(timezone.utc).isoformat()
        async with ctx.driver.session() as session:
            await session.run(
                _CYPHER_MERGE,
                run_id=ctx.run_id,
                ts=ts,
                extractor=self.name,
                group_id=ctx.group_id,
            )
        return ExtractorStats(nodes_written=1, edges_written=0)
