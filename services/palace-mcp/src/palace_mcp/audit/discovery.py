"""Audit extractor discovery — typed ExtractorStatus per extractor (GIM-283-1).

Public API: discover_extractor_statuses()
Legacy shim: find_latest_runs() (kept for callers not yet migrated)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from palace_mcp.audit.contracts import RunInfo
from palace_mcp.extractors.foundation.profiles import LanguageProfile

ExtractorStatusValue = Literal[
    "NOT_APPLICABLE", "NOT_ATTEMPTED", "RUN_FAILED", "FETCH_FAILED", "OK"
]


@dataclass(frozen=True)
class ExtractorStatus:
    """Typed status for one extractor relative to a project and profile."""

    extractor_name: str
    status: ExtractorStatusValue
    last_run_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


# Query: latest IngestRun per extractor for project, regardless of success flag.
# ORDER BY started_at DESC + LIMIT 1 per extractor implements last-attempt-wins.
_LATEST_RUN_QUERY = """
MATCH (r:IngestRun {project: $project})
WHERE r.extractor_name IS NOT NULL
WITH r.extractor_name AS extractor_name, r ORDER BY r.started_at DESC
WITH extractor_name, collect(r)[0] AS latest
RETURN extractor_name,
       coalesce(latest.run_id, latest.id) AS run_id,
       latest.started_at AS started_at,
       latest.success AS success,
       latest.error_code AS error_code,
       latest.message AS error_message
"""

# Legacy query: only successful runs (kept for find_latest_runs backward compat)
_DISCOVERY_QUERY = """
MATCH (r:IngestRun {project: $project, success: true})
WHERE r.extractor_name IS NOT NULL
WITH r.extractor_name AS extractor_name, r ORDER BY r.started_at DESC
WITH extractor_name, collect(r)[0] AS latest
RETURN extractor_name,
       coalesce(latest.run_id, latest.id) AS run_id,
       coalesce(latest.finished_at, latest.started_at) AS completed_at
"""


async def discover_extractor_statuses(
    driver: Any,
    *,
    project: str,
    profile: LanguageProfile,
    registry: dict[str, Any],
) -> dict[str, ExtractorStatus]:
    """Return typed ExtractorStatus for every audit extractor in registry.

    Classification logic (per spec §Status taxonomy):
    - NOT_APPLICABLE: extractor has audit_contract() but is not in profile.audit_extractors
    - NOT_ATTEMPTED:  in profile but no :IngestRun found
    - RUN_FAILED:     latest :IngestRun has success=False (last-attempt-wins)
    - OK:             latest :IngestRun has success=True (last-attempt-wins)
    - FETCH_FAILED:   set by run.py after discovery (fetcher raised an exception)
    """
    profile_set = profile.audit_extractors

    # Fetch latest runs — success OR failure
    latest_runs: dict[str, dict[str, Any]] = {}
    async with driver.session() as session:
        result = await session.run(_LATEST_RUN_QUERY, project=project)
        async for rec in result:
            name = rec["extractor_name"]
            latest_runs[name] = {
                "run_id": rec["run_id"],
                "success": rec["success"],
                "error_code": rec["error_code"],
                "error_message": rec["error_message"],
            }

    statuses: dict[str, ExtractorStatus] = {}
    for name, ext in registry.items():
        if ext.audit_contract() is None:
            continue  # not an audit extractor → skip entirely

        if name not in profile_set:
            statuses[name] = ExtractorStatus(
                extractor_name=name, status="NOT_APPLICABLE"
            )
            continue

        run = latest_runs.get(name)
        if run is None:
            statuses[name] = ExtractorStatus(
                extractor_name=name, status="NOT_ATTEMPTED"
            )
        elif run["success"]:
            statuses[name] = ExtractorStatus(
                extractor_name=name,
                status="OK",
                last_run_id=run["run_id"],
            )
        else:
            statuses[name] = ExtractorStatus(
                extractor_name=name,
                status="RUN_FAILED",
                last_run_id=run["run_id"],
                error_code=run.get("error_code"),
                error_message=run.get("error_message"),
            )

    return statuses


async def find_latest_runs(driver: Any, *, project: str) -> dict[str, RunInfo]:
    """Return the latest successful :IngestRun per extractor for the given project.

    Legacy function preserved for callers not yet migrated to discover_extractor_statuses.
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
