"""Read/write :OwnershipCheckpoint nodes (one per project)."""

from __future__ import annotations

from datetime import datetime, timezone

from neo4j import AsyncDriver

from palace_mcp.extractors.code_ownership.models import OwnershipCheckpoint

_LOAD_CYPHER = """
MATCH (c:OwnershipCheckpoint {project_id: $project_id})
RETURN c.project_id     AS project_id,
       c.last_head_sha  AS last_head_sha,
       c.last_completed_at AS last_completed_at,
       c.run_id         AS run_id,
       c.updated_at     AS updated_at
"""

_UPDATE_CYPHER = """
MERGE (c:OwnershipCheckpoint {project_id: $project_id})
SET c.last_head_sha     = $head_sha,
    c.last_completed_at = $now,
    c.run_id            = $run_id,
    c.updated_at        = $now
"""

_DELETE_CYPHER = """
MATCH (c:OwnershipCheckpoint {project_id: $project_id})
DELETE c
"""

_BASELINE_EXISTS_CYPHER = """
MATCH (s:OwnershipFileState {project_id: $project_id})
RETURN count(s) > 0 AS has_baseline
"""


async def load_checkpoint(
    driver: AsyncDriver, *, project_id: str
) -> OwnershipCheckpoint | None:
    async with driver.session() as session:
        result = await session.run(_LOAD_CYPHER, project_id=project_id)
        record = await result.single()
    if record is None:
        return None
    last_completed = record["last_completed_at"]
    if isinstance(last_completed, str):
        last_completed = datetime.fromisoformat(last_completed)
    elif hasattr(last_completed, "to_native"):
        last_completed = last_completed.to_native()
    updated = record["updated_at"]
    if isinstance(updated, str):
        updated = datetime.fromisoformat(updated)
    elif hasattr(updated, "to_native"):
        updated = updated.to_native()
    return OwnershipCheckpoint(
        project_id=record["project_id"],
        last_head_sha=record["last_head_sha"],
        last_completed_at=last_completed,
        run_id=record["run_id"],
        updated_at=updated,
    )


async def update_checkpoint(
    driver: AsyncDriver,
    *,
    project_id: str,
    head_sha: str,
    run_id: str,
) -> None:
    now = datetime.now(tz=timezone.utc).isoformat()
    async with driver.session() as session:
        await session.run(
            _UPDATE_CYPHER,
            project_id=project_id,
            head_sha=head_sha,
            run_id=run_id,
            now=now,
        )


async def delete_checkpoint(driver: AsyncDriver, *, project_id: str) -> None:
    async with driver.session() as session:
        await session.run(_DELETE_CYPHER, project_id=project_id)


async def has_file_state_baseline(driver: AsyncDriver, *, project_id: str) -> bool:
    async with driver.session() as session:
        result = await session.run(
            _BASELINE_EXISTS_CYPHER,
            project_id=project_id,
        )
        record = await result.single()
    return bool(record and record["has_baseline"])
