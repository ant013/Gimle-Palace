"""Neo4j writer for hot_path_profiler snapshots."""

from __future__ import annotations

from typing import Any, cast

from palace_mcp.extractors.hot_path_profiler.models import HotPathSample, HotPathSummary

_DELETE_EXISTING = """
MATCH (n)
WHERE n.project_id = $project_id
  AND n.trace_id = $trace_id
  AND (n:HotPathSample OR n:HotPathSummary OR n:HotPathSampleUnresolved)
DETACH DELETE n
""".strip()

_RESET_FUNCTION_ENRICHMENT = """
MATCH (fn:Function {project_id: $project_id})-[:HOT_PATH_SAMPLE]->(
    sample:HotPathSample {project_id: $project_id, trace_id: $trace_id}
)
SET fn.cpu_share = null,
    fn.wall_share = null,
    fn.is_hot_path = false
""".strip()

_WRITE_SUMMARY = """
CREATE (sum:HotPathSummary)
SET sum.project_id = $project_id,
    sum.run_id = $run_id,
    sum.trace_id = $trace_id,
    sum.source_format = $source_format,
    sum.total_cpu_samples = $total_cpu_samples,
    sum.total_wall_ms = $total_wall_ms,
    sum.hot_function_count = $hot_function_count,
    sum.threshold_cpu_share = $threshold_cpu_share
""".strip()

_WRITE_RESOLVED_SAMPLE = """
CREATE (sample:HotPathSample)
SET sample.project_id = $project_id,
    sample.run_id = $run_id,
    sample.trace_id = $trace_id,
    sample.source_format = $source_format,
    sample.symbol_name = $symbol_name,
    sample.qualified_name = $qualified_name,
    sample.cpu_samples = $cpu_samples,
    sample.wall_ms = $wall_ms,
    sample.total_samples_in_trace = $total_samples_in_trace,
    sample.total_wall_ms_in_trace = $total_wall_ms_in_trace,
    sample.thread_name = $thread_name
WITH sample
MATCH (fn:Function {project_id: $project_id})
WHERE coalesce(fn.qualified_name, fn.symbol_qualified_name, fn.name) = $qualified_name
SET fn.cpu_share = CASE
        WHEN $total_samples_in_trace > 0
        THEN toFloat($cpu_samples) / toFloat($total_samples_in_trace)
        ELSE 0.0
    END,
    fn.wall_share = CASE
        WHEN $total_wall_ms_in_trace > 0
        THEN toFloat($wall_ms) / toFloat($total_wall_ms_in_trace)
        ELSE 0.0
    END,
    fn.is_hot_path = CASE
        WHEN $total_samples_in_trace > 0
        THEN (toFloat($cpu_samples) / toFloat($total_samples_in_trace)) >= $threshold_cpu_share
        ELSE false
    END
MERGE (fn)-[:HOT_PATH_SAMPLE]->(sample)
""".strip()

_WRITE_UNRESOLVED_SAMPLE = """
CREATE (sample:HotPathSampleUnresolved)
SET sample.project_id = $project_id,
    sample.run_id = $run_id,
    sample.trace_id = $trace_id,
    sample.source_format = $source_format,
    sample.symbol_name = $symbol_name,
    sample.cpu_samples = $cpu_samples,
    sample.wall_ms = $wall_ms,
    sample.total_samples_in_trace = $total_samples_in_trace,
    sample.total_wall_ms_in_trace = $total_wall_ms_in_trace,
    sample.thread_name = $thread_name
""".strip()


async def write_snapshot(
    driver: Any,
    *,
    project_id: str,
    run_id: str,
    summary: HotPathSummary,
    resolved: list[HotPathSample],
    unresolved: list[HotPathSample],
) -> tuple[int, int]:
    """Write one trace snapshot and return node/edge counts."""

    async with driver.session() as session:
        return cast(
            tuple[int, int],
            await session.execute_write(
                _write_snapshot_tx,
                project_id,
                run_id,
                summary,
                resolved,
                unresolved,
            ),
        )


async def _write_snapshot_tx(
    tx: Any,
    project_id: str,
    run_id: str,
    summary: HotPathSummary,
    resolved: list[HotPathSample],
    unresolved: list[HotPathSample],
) -> tuple[int, int]:
    cursor = await tx.run(
        _RESET_FUNCTION_ENRICHMENT,
        project_id=project_id,
        trace_id=summary.trace_id,
    )
    await cursor.consume()

    cursor = await tx.run(
        _DELETE_EXISTING,
        project_id=project_id,
        trace_id=summary.trace_id,
    )
    await cursor.consume()

    cursor = await tx.run(
        _WRITE_SUMMARY,
        project_id=project_id,
        run_id=run_id,
        trace_id=summary.trace_id,
        source_format=summary.source_format,
        total_cpu_samples=summary.total_cpu_samples,
        total_wall_ms=summary.total_wall_ms,
        hot_function_count=summary.hot_function_count,
        threshold_cpu_share=summary.threshold_cpu_share,
    )
    await cursor.consume()

    for sample in resolved:
        cursor = await tx.run(
            _WRITE_RESOLVED_SAMPLE,
            project_id=project_id,
            run_id=run_id,
            trace_id=sample.trace_id,
            source_format=sample.source_format,
            symbol_name=sample.symbol_name,
            qualified_name=sample.qualified_name,
            cpu_samples=sample.cpu_samples,
            wall_ms=sample.wall_ms,
            total_samples_in_trace=sample.total_samples_in_trace,
            total_wall_ms_in_trace=sample.total_wall_ms_in_trace,
            thread_name=sample.thread_name,
            threshold_cpu_share=summary.threshold_cpu_share,
        )
        await cursor.consume()

    for sample in unresolved:
        cursor = await tx.run(
            _WRITE_UNRESOLVED_SAMPLE,
            project_id=project_id,
            run_id=run_id,
            trace_id=sample.trace_id,
            source_format=sample.source_format,
            symbol_name=sample.symbol_name,
            cpu_samples=sample.cpu_samples,
            wall_ms=sample.wall_ms,
            total_samples_in_trace=sample.total_samples_in_trace,
            total_wall_ms_in_trace=sample.total_wall_ms_in_trace,
            thread_name=sample.thread_name,
        )
        await cursor.consume()

    return 1 + len(resolved) + len(unresolved), len(resolved)
