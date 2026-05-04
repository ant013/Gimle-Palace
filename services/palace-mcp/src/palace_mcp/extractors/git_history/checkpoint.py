"""GitHistoryCheckpoint own state persistence — see spec §3.6."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from neo4j import AsyncDriver

from palace_mcp.extractors.git_history.models import GitHistoryCheckpoint

_MERGE_CHECKPOINT_CYPHER = """
MERGE (c:GitHistoryCheckpoint {project_id: $project_id})
SET c.last_commit_sha = $last_commit_sha,
    c.last_pr_updated_at = $last_pr_updated_at,
    c.last_phase_completed = $last_phase_completed,
    c.updated_at = datetime()
"""

_LOAD_CHECKPOINT_CYPHER = """
MATCH (c:GitHistoryCheckpoint {project_id: $project_id})
RETURN c.project_id AS project_id,
       c.last_commit_sha AS last_commit_sha,
       c.last_pr_updated_at AS last_pr_updated_at,
       c.last_phase_completed AS last_phase_completed,
       c.updated_at AS updated_at
"""


async def write_git_history_checkpoint(
    driver: AsyncDriver,
    project_id: str,
    *,
    last_commit_sha: str | None,
    last_pr_updated_at: datetime | None,
    last_phase_completed: Literal["none", "phase1", "phase2"],
) -> None:
    await driver.execute_query(
        _MERGE_CHECKPOINT_CYPHER,
        project_id=project_id,
        last_commit_sha=last_commit_sha,
        last_pr_updated_at=last_pr_updated_at,
        last_phase_completed=last_phase_completed,
    )


async def load_git_history_checkpoint(
    driver: AsyncDriver,
    project_id: str,
) -> GitHistoryCheckpoint:
    """Return persisted checkpoint, or a fresh 'none' state if absent."""
    result = await driver.execute_query(_LOAD_CHECKPOINT_CYPHER, project_id=project_id)
    if not result.records:
        return GitHistoryCheckpoint(
            project_id=project_id,
            last_commit_sha=None,
            last_pr_updated_at=None,
            last_phase_completed="none",
            updated_at=datetime.now(timezone.utc),
        )
    row = result.records[0]
    return GitHistoryCheckpoint(
        project_id=row["project_id"],
        last_commit_sha=row["last_commit_sha"],
        last_pr_updated_at=row["last_pr_updated_at"],
        last_phase_completed=row["last_phase_completed"],
        updated_at=row["updated_at"],
    )
