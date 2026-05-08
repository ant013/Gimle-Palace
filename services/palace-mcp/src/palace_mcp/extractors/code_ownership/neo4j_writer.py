"""Per-batch atomic-replace transaction writer.

Contract (per spec rev2 C2): for the paths in a batch, all old
:OWNED_BY edges (filtered by stable r.source) are deleted AND all new
edges (with sidecar :OwnershipFileState) are written within ONE
transaction. Readers see either the pre-batch or post-batch state for
any given path, never mixed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from neo4j import AsyncDriver

from palace_mcp.extractors.code_ownership.models import OwnershipEdge

OWNERSHIP_SOURCE = "extractor.code_ownership"

_DELETE_BY_PATH_CYPHER = """
UNWIND $paths AS p
MATCH (f:File {project_id: $proj, path: p})
      -[r:OWNED_BY {source: $source}]
      ->()
DELETE r
"""

_WRITE_EDGES_CYPHER = """
UNWIND $edges AS e
MATCH (f:File {project_id: $proj, path: e.path})
MERGE (a:Author {provider: 'git', identity_key: e.canonical_id})
  ON CREATE SET a.email = e.canonical_email,
                a.name = e.canonical_name,
                a.is_bot = false,
                a.first_seen_at = e.last_touched_at,
                a.last_seen_at = e.last_touched_at
MERGE (f)-[r:OWNED_BY {source: $source}]->(a)
SET r.weight = e.weight,
    r.blame_share = e.blame_share,
    r.recency_churn_share = e.recency_churn_share,
    r.last_touched_at = e.last_touched_at,
    r.lines_attributed = e.lines_attributed,
    r.commit_count = e.commit_count,
    r.run_id_provenance = $run_id,
    r.alpha_used = $alpha,
    r.canonical_via = e.canonical_via
"""

_WRITE_FILE_STATE_CYPHER = """
UNWIND $states AS s
MERGE (st:OwnershipFileState {project_id: $proj, path: s.path})
SET st.status = s.status,
    st.no_owners_reason = s.no_owners_reason,
    st.last_run_id = $run_id,
    st.updated_at = $now
"""


async def write_batch(
    driver: AsyncDriver,
    *,
    project_id: str,
    edges: list[OwnershipEdge],
    file_states: list[dict[str, Any]],
    deleted_paths: list[str],
    run_id: str,
    alpha: float,
) -> None:
    """Atomic-replace a batch of paths within a single tx."""
    edges_payload = [
        {
            "path": e.path,
            "canonical_id": e.canonical_id,
            "canonical_email": e.canonical_email,
            "canonical_name": e.canonical_name,
            "weight": e.weight,
            "blame_share": e.blame_share,
            "recency_churn_share": e.recency_churn_share,
            "last_touched_at": e.last_touched_at.isoformat(),
            "lines_attributed": e.lines_attributed,
            "commit_count": e.commit_count,
            "canonical_via": e.canonical_via,
        }
        for e in edges
    ]
    paths_to_wipe = list({e.path for e in edges} | set(deleted_paths))
    now = datetime.now(tz=timezone.utc).isoformat()

    async with driver.session() as session:
        async with await session.begin_transaction() as tx:
            if paths_to_wipe:
                await tx.run(
                    _DELETE_BY_PATH_CYPHER,
                    paths=paths_to_wipe,
                    proj=project_id,
                    source=OWNERSHIP_SOURCE,
                )
            if edges_payload:
                await tx.run(
                    _WRITE_EDGES_CYPHER,
                    edges=edges_payload,
                    proj=project_id,
                    source=OWNERSHIP_SOURCE,
                    run_id=run_id,
                    alpha=alpha,
                )
            if file_states:
                await tx.run(
                    _WRITE_FILE_STATE_CYPHER,
                    states=file_states,
                    proj=project_id,
                    run_id=run_id,
                    now=now,
                )
            # tx commits on context exit
