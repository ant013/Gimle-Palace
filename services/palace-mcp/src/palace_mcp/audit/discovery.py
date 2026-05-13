"""Audit extractor discovery — finds latest successful :IngestRun per extractor.

Uses the S0.1 unified :IngestRun schema (extractor_name + project fields).
"""

from __future__ import annotations

from typing import Any

from palace_mcp.audit.contracts import RunInfo

_DISCOVERY_QUERY = """
MATCH (r:IngestRun {project: $project, success: true})
WHERE r.extractor_name IS NOT NULL
WITH r.extractor_name AS extractor_name, r ORDER BY r.started_at DESC
WITH extractor_name, collect(r)[0] AS latest
RETURN extractor_name,
       coalesce(latest.run_id, latest.id) AS run_id,
       latest.started_at AS completed_at
"""


async def find_latest_runs(driver: Any, *, project: str) -> dict[str, RunInfo]:
    """Return the latest successful :IngestRun per extractor for the given project.

    Returns a dict keyed by extractor_name. Returns empty dict if no runs found.
    """
    results: dict[str, RunInfo] = {}
    async with driver.session() as session:
        result = await session.run(_DISCOVERY_QUERY, project=project)
        async for rec in result:
            extractor_name = rec["extractor_name"]
            run_id = rec["run_id"]
            completed_at_raw = rec["completed_at"]
            completed_at: str | None = None
            if completed_at_raw is not None:
                if hasattr(completed_at_raw, "iso_format"):
                    completed_at = completed_at_raw.iso_format()
                else:
                    completed_at = str(completed_at_raw)
            results[extractor_name] = RunInfo(
                run_id=run_id,
                extractor_name=extractor_name,
                project=project,
                completed_at=completed_at,
            )
    return results
