"""palace.memory.health — graphiti-core substrate (N+1a).

Replaces Cypher queries with graphiti namespace API.
Adds real HTTP embedder probe (WARNING #3 fix).

Zero raw Cypher — spec §9 acceptance.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from graphiti_core import Graphiti

from palace_mcp.ingest.builders import GROUP_ID
from palace_mcp.memory.schema import HealthResponse

logger = logging.getLogger(__name__)

_PAPERCLIP_LABELS = {"Issue", "Comment", "Agent"}


async def _check_embedder(base_url: str) -> bool:
    """HTTP probe: GET <base_url>/models — returns True if 2xx."""
    url = base_url.rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            return resp.is_success
    except Exception:  # noqa: BLE001
        return False


async def get_health(graphiti: Graphiti, embedder_base_url: str = "") -> HealthResponse:
    """Return health data: reachability, entity counts, last ingest run info."""
    # ── Neo4j reachability ────────────────────────────────────────────────────
    try:
        await graphiti.driver.verify_connectivity()
        neo4j_reachable = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("palace.memory.health neo4j unreachable: %s", exc)
        return HealthResponse(
            neo4j_reachable=False,
            embedder_reachable=False,
            entity_counts={},
        )

    # ── Embedder probe ────────────────────────────────────────────────────────
    embedder_ok = False
    if embedder_base_url:
        embedder_ok = await _check_embedder(embedder_base_url)

    # ── Entity counts via group nodes ─────────────────────────────────────────
    try:
        all_nodes = await graphiti.nodes.entity.get_by_group_ids([GROUP_ID])
    except Exception as exc:  # noqa: BLE001
        logger.warning("palace.memory.health group fetch failed: %s", exc)
        return HealthResponse(
            neo4j_reachable=True,
            embedder_reachable=embedder_ok,
            entity_counts={},
        )

    entity_counts: dict[str, int] = {lbl: 0 for lbl in _PAPERCLIP_LABELS}
    for node in all_nodes:
        for lbl in node.labels:
            if lbl in _PAPERCLIP_LABELS:
                entity_counts[lbl] = entity_counts.get(lbl, 0) + 1

    # ── Latest IngestRun ──────────────────────────────────────────────────────
    ingest_nodes = [n for n in all_nodes if "IngestRun" in n.labels]
    ingest_data: dict[str, Any] | None = None
    if ingest_nodes:
        # Sort by started_at DESC, take first
        ingest_nodes.sort(
            key=lambda n: n.attributes.get("started_at", "") or "",
            reverse=True,
        )
        latest = ingest_nodes[0]
        ingest_data = latest.attributes

    return HealthResponse(
        neo4j_reachable=True,
        embedder_reachable=embedder_ok,
        entity_counts=entity_counts,
        last_ingest_started_at=ingest_data.get("started_at") if ingest_data else None,
        last_ingest_finished_at=(
            ingest_data.get("finished_at") if ingest_data else None
        ),
        last_ingest_duration_ms=(
            ingest_data.get("duration_ms") if ingest_data else None
        ),
        last_ingest_errors=list(ingest_data.get("errors") or []) if ingest_data else [],
    )
