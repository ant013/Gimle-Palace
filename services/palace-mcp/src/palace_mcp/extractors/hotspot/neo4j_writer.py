from __future__ import annotations

from datetime import datetime
from typing import Any

PHASE_1_CYPHER = """
MERGE (f:File {project_id: $project_id, path: $path})
SET f.ccn_total = $ccn_total,
    f.complexity_status = 'fresh',
    f.last_complexity_run_at = datetime($run_started_at)
WITH f
UNWIND $functions AS fn_in
MERGE (fn:Function {
  project_id: $project_id,
  path: $path,
  name: fn_in.name,
  start_line: fn_in.start_line
})
SET fn.end_line = fn_in.end_line,
    fn.ccn = fn_in.ccn,
    fn.parameter_count = fn_in.parameter_count,
    fn.nloc = fn_in.nloc,
    fn.language = fn_in.language,
    fn.last_run_at = datetime($run_started_at)
MERGE (f)-[:CONTAINS]->(fn)
""".strip()

PHASE_3_CYPHER = """
MERGE (f:File {project_id: $project_id, path: $path})
SET f.churn_count = $churn,
    f.complexity_window_days = $window_days,
    f.hotspot_score = $score,
    f.complexity_status = 'fresh',
    f.last_complexity_run_at = datetime($run_started_at)
""".strip()

PHASE_4_EVICT_CYPHER = """
MATCH (f:File {project_id: $project_id})-[:CONTAINS]->(fn:Function)
WHERE NOT f.path IN $preserved_paths
  AND fn.last_run_at < datetime($run_started_at)
DETACH DELETE fn
""".strip()

PHASE_5_DEAD_CYPHER = """
MATCH (f:File {project_id: $project_id})
WHERE NOT f.path IN $preserved_paths
  AND coalesce(f.ccn_total, 0) > 0
SET f.ccn_total = 0,
    f.churn_count = 0,
    f.hotspot_score = 0.0,
    f.complexity_status = 'stale',
    f.last_complexity_run_at = datetime($run_started_at)
""".strip()


def _functions_payload(parsed_file: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": fn.name,
            "start_line": fn.start_line,
            "end_line": fn.end_line,
            "ccn": fn.ccn,
            "parameter_count": fn.parameter_count,
            "nloc": fn.nloc,
            "language": parsed_file.language,
        }
        for fn in parsed_file.functions
    ]


async def write_file_and_functions(
    driver: Any,
    *,
    project_id: str,
    parsed_file: Any,
    run_started_at: datetime,
) -> None:
    async with driver.session() as session:
        await session.run(
            PHASE_1_CYPHER,
            {
                "project_id": project_id,
                "path": parsed_file.path,
                "ccn_total": parsed_file.ccn_total,
                "run_started_at": run_started_at.isoformat(),
                "functions": _functions_payload(parsed_file),
            },
        )


async def write_hotspot_score(
    driver: Any,
    *,
    project_id: str,
    path: str,
    churn: int,
    score: float,
    window_days: int,
    run_started_at: datetime,
) -> None:
    async with driver.session() as session:
        await session.run(
            PHASE_3_CYPHER,
            {
                "project_id": project_id,
                "path": path,
                "churn": churn,
                "score": score,
                "window_days": window_days,
                "run_started_at": run_started_at.isoformat(),
            },
        )


async def evict_stale_functions(
    driver: Any,
    *,
    project_id: str,
    preserved_paths: list[str],
    run_started_at: datetime,
) -> None:
    async with driver.session() as session:
        await session.run(
            PHASE_4_EVICT_CYPHER,
            {
                "project_id": project_id,
                "preserved_paths": preserved_paths,
                "run_started_at": run_started_at.isoformat(),
            },
        )


async def mark_dead_files_zero(
    driver: Any,
    *,
    project_id: str,
    preserved_paths: list[str],
    run_started_at: datetime,
) -> None:
    async with driver.session() as session:
        await session.run(
            PHASE_5_DEAD_CYPHER,
            {
                "project_id": project_id,
                "preserved_paths": preserved_paths,
                "run_started_at": run_started_at.isoformat(),
            },
        )
