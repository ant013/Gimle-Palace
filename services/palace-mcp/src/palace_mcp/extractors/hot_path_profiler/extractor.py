"""hot_path_profiler extractor implementation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from palace_mcp.audit.contracts import AuditContract

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorConfigError,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.hot_path_profiler import neo4j_writer, symbol_resolver
from palace_mcp.extractors.hot_path_profiler.models import (
    HotPathSample,
    HotPathSummary,
)
from palace_mcp.extractors.hot_path_profiler.parsers import (
    is_simpleperf_trace,
    parse_instruments_trace,
    parse_perfetto_trace,
    parse_simpleperf_trace,
)


class HotPathProfilerExtractor(BaseExtractor):
    """Roadmap #17 runtime hot-path profiler extractor."""

    name: ClassVar[str] = "hot_path_profiler"
    description: ClassVar[str] = (
        "Parses committed Instruments JSON and Perfetto traces, resolves hot-path "
        "samples onto existing :Function nodes, and writes :HotPathSample/"
        ":HotPathSummary snapshots for audit queries."
    )
    constraints: ClassVar[list[str]] = []
    indexes: ClassVar[list[str]] = [
        "CREATE INDEX hot_path_sample_project IF NOT EXISTS "
        "FOR (s:HotPathSample) ON (s.project_id, s.qualified_name)",
        "CREATE INDEX hot_path_summary_project IF NOT EXISTS "
        "FOR (s:HotPathSummary) ON (s.project_id, s.trace_id)",
        "CREATE INDEX hot_path_unresolved_project IF NOT EXISTS "
        "FOR (s:HotPathSampleUnresolved) ON (s.project_id, s.symbol_name)",
    ]

    async def run(
        self,
        *,
        graphiti: Any,
        ctx: ExtractorRunContext,
    ) -> ExtractorStats:
        profiles_dir = ctx.repo_path / "profiles"
        if not profiles_dir.is_dir():
            raise ExtractorConfigError(
                f"profiles directory not found under repo root: {profiles_dir}"
            )

        trace_files = self._discover_trace_files(profiles_dir)
        if not trace_files:
            raise ExtractorConfigError(
                f"no trace files found under {profiles_dir} (expected *.json or *.pftrace)"
            )

        driver = graphiti.driver
        total_nodes = 0
        total_edges = 0

        for trace_path in trace_files:
            summary, samples = self._parse_trace(trace_path)
            resolved, unresolved = await symbol_resolver.resolve_samples(
                driver,
                project_id=ctx.group_id,
                samples=samples,
            )
            summary = self._resolved_summary(summary, resolved)
            nodes, edges = await neo4j_writer.write_snapshot(
                driver,
                project_id=ctx.group_id,
                run_id=ctx.run_id,
                summary=summary,
                resolved=resolved,
                unresolved=unresolved,
            )
            ctx.logger.info(
                "hot_path_profiler trace processed",
                extra={
                    "project": ctx.project_slug,
                    "trace_path": str(trace_path),
                    "trace_id": summary.trace_id,
                    "resolved": len(resolved),
                    "unresolved": len(unresolved),
                },
            )
            total_nodes += nodes
            total_edges += edges

        return ExtractorStats(nodes_written=total_nodes, edges_written=total_edges)

    def audit_contract(self) -> "AuditContract":
        from palace_mcp.audit.contracts import AuditContract, Severity

        return AuditContract(
            extractor_name="hot_path_profiler",
            template_name="hot_path_profiler.md",
            query="""
MATCH (sum:HotPathSummary {project_id: $project_id})
WITH sum
MATCH (sample:HotPathSample {
    project_id: $project_id,
    run_id: sum.run_id,
    trace_id: sum.trace_id
})
WITH sample,
     sum,
     CASE
         WHEN sample.total_samples_in_trace > 0
         THEN toFloat(sample.cpu_samples) / toFloat(sample.total_samples_in_trace)
         ELSE 0.0
     END AS cpu_share,
     CASE
         WHEN sample.total_wall_ms_in_trace > 0
         THEN toFloat(sample.wall_ms) / toFloat(sample.total_wall_ms_in_trace)
         ELSE 0.0
     END AS wall_share
WHERE cpu_share >= sum.threshold_cpu_share
RETURN sample.trace_id AS trace_id,
       sample.qualified_name AS qualified_name,
       sample.symbol_name AS symbol_name,
       sample.cpu_samples AS cpu_samples,
       sample.wall_ms AS wall_ms,
       sample.source_format AS source_format,
       cpu_share AS cpu_share,
       wall_share AS wall_share
ORDER BY cpu_share DESC, wall_share DESC
LIMIT 25
""".strip(),
            severity_column="cpu_share",
            severity_mapper=lambda value: (
                Severity.HIGH
                if value is not None and float(value) >= 0.20
                else Severity.MEDIUM
                if value is not None and float(value) >= 0.10
                else Severity.LOW
                if value is not None and float(value) > 0
                else Severity.INFORMATIONAL
            ),
        )

    def _discover_trace_files(self, profiles_dir: Path) -> list[Path]:
        files = [
            *sorted(profiles_dir.glob("*.json")),
            *sorted(profiles_dir.glob("*.pftrace")),
            *sorted(profiles_dir.glob("*.trace")),
            *sorted(profiles_dir.glob("*.proto")),
            *sorted(profiles_dir.glob("*.pb")),
        ]
        return [path for path in files if path.is_file()]

    def _parse_trace(
        self, trace_path: Path
    ) -> tuple[HotPathSummary, list[HotPathSample]]:
        if trace_path.suffix == ".json":
            return parse_instruments_trace(trace_path)
        if trace_path.suffix == ".pftrace":
            return parse_perfetto_trace(trace_path)
        if trace_path.suffix in {".trace", ".proto", ".pb"} and is_simpleperf_trace(
            trace_path
        ):
            return parse_simpleperf_trace(trace_path)
        raise ExtractorConfigError(f"unsupported trace file: {trace_path}")

    def _resolved_summary(
        self,
        summary: HotPathSummary,
        resolved: list[HotPathSample],
    ) -> HotPathSummary:
        hot_function_count = sum(
            1 for sample in resolved if sample.cpu_share >= summary.threshold_cpu_share
        )
        return summary.model_copy(update={"hot_function_count": hot_function_count})
