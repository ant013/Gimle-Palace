"""IngestRun writer.

Writes a :IngestRun:Entity node per ingest pass for observability +
palace.memory.health latest_ingest_at queries.
"""

from __future__ import annotations

from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode


async def write_ingest_run(
    graphiti: Graphiti,
    *,
    run_id: str,
    started_at: str,
    finished_at: str,
    duration_ms: int,
    errors: list[str],
    group_id: str,
    source: str = "paperclip",
) -> None:
    node = EntityNode(
        uuid=run_id,
        name=f"ingest-{run_id[:8]}",
        labels=["IngestRun"],
        group_id=group_id,
        summary=f"{source} ingest {started_at}",
        attributes={
            "source": source,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "errors": errors,
            "run_id": run_id,
        },
    )
    await graphiti.nodes.entity.save(node)
