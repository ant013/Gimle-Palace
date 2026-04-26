"""palace.memory.decide — write-side implementation for :Decision nodes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode

from palace_mcp.graphiti_runtime import save_entity_node
from palace_mcp.memory.decide_models import DecideRequest

_EXTRACTOR = "palace.memory.decide@0.1"
_EXTRACTOR_VERSION = "0.1"


async def decide(req: DecideRequest, *, g: Graphiti, group_id: str) -> dict[str, Any]:
    """Persist a :Decision EntityNode and return success envelope.

    group_id resolution is the caller's responsibility (MCP wrapper, Task 3).
    Infra exceptions (embedder, Neo4j) propagate — caller routes them via handle_tool_error.
    """
    decided_at = datetime.now(UTC).isoformat()

    node = EntityNode(
        name=req.title,
        group_id=group_id,
        labels=["Decision"],
        attributes={
            "body": req.body,
            "slice_ref": req.slice_ref,
            "decision_maker_claimed": req.decision_maker_claimed,
            "decision_kind": req.decision_kind,
            "provenance": "asserted",
            "confidence": req.confidence,
            "decided_at": decided_at,
            "extractor": _EXTRACTOR,
            "extractor_version": _EXTRACTOR_VERSION,
            "attestation": "none",
            "tags": req.tags if req.tags is not None else [],
            "evidence_ref": req.evidence_ref if req.evidence_ref is not None else [],
        },
    )

    await save_entity_node(g, node)

    name_embedding_dim = len(node.name_embedding) if node.name_embedding else 0

    return {
        "ok": True,
        "uuid": str(node.uuid),
        "name": node.name,
        "slice_ref": req.slice_ref,
        "decision_maker_claimed": req.decision_maker_claimed,
        "decided_at": decided_at,
        "name_embedding_dim": name_embedding_dim,
    }
