"""HeartbeatExtractor — diagnostic probe that writes one :Episode node."""

from __future__ import annotations

from datetime import datetime, timezone

from graphiti_core import Graphiti

from palace_mcp.extractors.base import BaseExtractor, ExtractorRunContext, ExtractorStats
from palace_mcp.graphiti_runtime import save_entity_node
from palace_mcp.graphiti_schema.entities import make_episode


class HeartbeatExtractor(BaseExtractor):
    name = "heartbeat"
    version = "0.2"
    description = (
        "Diagnostic probe — writes one :Episode node to verify Neo4j + Graphiti connectivity."
    )
    constraints = []
    indexes = []

    async def run(self, *, graphiti: Graphiti, ctx: ExtractorRunContext) -> ExtractorStats:
        now = datetime.now(timezone.utc)
        episode = make_episode(
            group_id=ctx.group_id,
            name=f"heartbeat-{now.isoformat()}",
            kind="heartbeat",
            source="extractor.heartbeat",
            confidence=1.0,
            provenance="asserted",
            extractor=f"heartbeat@{self.version}",
            extractor_version=self.version,
            observed_at=now.isoformat(),
            extra={"duration_ms": ctx.duration_ms},
        )
        await save_entity_node(graphiti, episode)
        return ExtractorStats(nodes_written=1, edges_written=0)
