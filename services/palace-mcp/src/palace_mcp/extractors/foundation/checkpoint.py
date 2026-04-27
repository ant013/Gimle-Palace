"""IngestRun + IngestCheckpoint read/write with reconciliation (GIM-101a, T8).

Architect Finding F5 + Silent-failure F4: IngestCheckpoint carries
expected_doc_count; on restart, reconcile count(Tantivy docs) == expected.
Mismatch → CHECKPOINT_DOC_COUNT_MISMATCH error; refuse to resume.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from neo4j import AsyncDriver

from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.models import IngestCheckpoint

Phase = Literal["phase1_defs", "phase2_user_uses", "phase3_vendor_uses"]

# ---------------------------------------------------------------------------
# IngestRun write/read
# ---------------------------------------------------------------------------

_WRITE_INGEST_RUN_CYPHER = """
MERGE (r:IngestRun {run_id: $run_id})
ON CREATE SET
    r.project = $project,
    r.extractor_name = $extractor_name,
    r.started_at = $started_at,
    r.success = null,
    r.error_code = null
RETURN r
"""

_FINALIZE_INGEST_RUN_CYPHER = """
MATCH (r:IngestRun {run_id: $run_id})
SET r.success = $success,
    r.error_code = $error_code,
    r.finished_at = $finished_at
RETURN r
"""


async def create_ingest_run(
    driver: AsyncDriver,
    *,
    run_id: str,
    project: str,
    extractor_name: str,
) -> None:
    """Create or merge an :IngestRun node for this run."""
    async with driver.session() as session:
        await session.run(
            _WRITE_INGEST_RUN_CYPHER,
            run_id=run_id,
            project=project,
            extractor_name=extractor_name,
            started_at=datetime.now(tz=timezone.utc).isoformat(),
        )


async def finalize_ingest_run(
    driver: AsyncDriver,
    *,
    run_id: str,
    success: bool,
    error_code: str | None = None,
) -> None:
    async with driver.session() as session:
        await session.run(
            _FINALIZE_INGEST_RUN_CYPHER,
            run_id=run_id,
            success=success,
            error_code=error_code,
            finished_at=datetime.now(tz=timezone.utc).isoformat(),
        )


# ---------------------------------------------------------------------------
# IngestCheckpoint write + read
# ---------------------------------------------------------------------------

_WRITE_CHECKPOINT_CYPHER = """
MERGE (c:IngestCheckpoint {run_id: $run_id, phase: $phase, project: $project})
ON CREATE SET
    c.expected_doc_count = $expected_doc_count,
    c.completed_at = $completed_at
ON MATCH SET
    c.expected_doc_count = $expected_doc_count,
    c.completed_at = $completed_at
RETURN c
"""

_READ_CHECKPOINT_CYPHER = """
MATCH (c:IngestCheckpoint {run_id: $run_id, project: $project})
RETURN c.phase AS phase,
       c.expected_doc_count AS expected_doc_count,
       c.completed_at AS completed_at
ORDER BY c.completed_at ASC
"""


async def write_checkpoint(
    driver: AsyncDriver,
    *,
    run_id: str,
    project: str,
    phase: Phase,
    expected_doc_count: int,
) -> IngestCheckpoint:
    """Write an IngestCheckpoint after successful phase commit in both stores."""
    now = datetime.now(tz=timezone.utc)
    async with driver.session() as session:
        await session.run(
            _WRITE_CHECKPOINT_CYPHER,
            run_id=run_id,
            project=project,
            phase=phase,
            expected_doc_count=expected_doc_count,
            completed_at=now.isoformat(),
        )
    return IngestCheckpoint(
        run_id=run_id,
        project=project,
        phase=phase,
        expected_doc_count=expected_doc_count,
        completed_at=now,
    )


async def read_checkpoints(
    driver: AsyncDriver, *, run_id: str, project: str
) -> list[IngestCheckpoint]:
    """Read all checkpoints for a run, ordered by completion time."""
    async with driver.session() as session:
        result = await session.run(
            _READ_CHECKPOINT_CYPHER,
            run_id=run_id,
            project=project,
        )
        records = await result.data()

    checkpoints = []
    for r in records:
        completed_at = r["completed_at"]
        if isinstance(completed_at, str):
            completed_at = datetime.fromisoformat(completed_at)
        checkpoints.append(
            IngestCheckpoint(
                run_id=run_id,
                project=project,
                phase=r["phase"],
                expected_doc_count=r["expected_doc_count"],
                completed_at=completed_at,
            )
        )
    return checkpoints


# ---------------------------------------------------------------------------
# Restart reconciliation
# ---------------------------------------------------------------------------


async def reconcile_checkpoint(
    *,
    checkpoint: IngestCheckpoint,
    actual_doc_count: int,
) -> None:
    """Verify Tantivy doc count matches checkpoint.expected_doc_count.

    Raises ExtractorError with CHECKPOINT_DOC_COUNT_MISMATCH if they disagree.
    Operator must set PALACE_FORCE_REINGEST=1 or rebuild Tantivy to proceed.
    """
    if actual_doc_count != checkpoint.expected_doc_count:
        raise ExtractorError(
            error_code=ExtractorErrorCode.CHECKPOINT_DOC_COUNT_MISMATCH,
            message=(
                f"Tantivy doc count ({actual_doc_count}) != "
                f"checkpoint expected_doc_count ({checkpoint.expected_doc_count}) "
                f"for run_id={checkpoint.run_id} phase={checkpoint.phase}. "
                "Set PALACE_FORCE_REINGEST=1 or rebuild Tantivy index to proceed."
            ),
            recoverable=False,
            action="rebuild_tantivy",
            phase=checkpoint.phase,
            partial_writes=actual_doc_count,
        )
