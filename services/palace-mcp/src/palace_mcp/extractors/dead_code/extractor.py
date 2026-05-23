"""DeadCodeExtractor — G0d algorithm orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from graphiti_core import Graphiti

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorOutcome,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.dead_code.finding_builder import build_findings
from palace_mcp.extractors.dead_code.git_enrichment import enrich_findings_with_git
from palace_mcp.extractors.dead_code.graph_loader import (
    load_git_history,
    load_symbol_graph,
)
from palace_mcp.extractors.dead_code.neo4j_writer import write_dead_findings
from palace_mcp.extractors.dead_code.reachability import (
    compute_dead_candidates,
    compute_reachable_set,
)
from palace_mcp.extractors.dead_code.seeds import compute_all_seeds
from palace_mcp.extractors.foundation.checkpoint import (
    create_ingest_run,
    finalize_ingest_run,
    write_checkpoint,
)
from palace_mcp.extractors.foundation.circuit_breaker import (
    check_phase_budget,
    check_resume_budget,
)
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.schema import ensure_custom_schema

if TYPE_CHECKING:
    from neo4j import AsyncDriver
    from palace_mcp.config import Settings


class DeadCodeExtractor(BaseExtractor):
    """Graph-reachability dead-code analysis (G0d algorithm).

    Distinct from dead_symbol_binary_surface (Periphery/binary-surface approach).
    This extractor uses the SCIP call/reference graph to identify unreachable
    code clusters, extension chains, and individual dead symbols.
    """

    name: ClassVar[str] = "dead_code"
    description: ClassVar[str] = (
        "Graph-reachability dead-code analysis using SCIP symbol graph. "
        "Identifies unreachable symbols, SCC clusters, dead extension chains, "
        "and dead modules via BFS + Tarjan SCC. "
        "See also: dead_symbol_binary_surface (Periphery/binary-surface approach)."
    )

    constraints: ClassVar[list[str]] = [
        "CREATE CONSTRAINT dead_finding_id_unique IF NOT EXISTS "
        "FOR (n:DeadFinding) REQUIRE n.finding_id IS UNIQUE"
    ]
    indexes: ClassVar[list[str]] = [
        "CREATE INDEX dead_finding_project_severity IF NOT EXISTS "
        "FOR (n:DeadFinding) ON (n.project, n.severity)"
    ]

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        del graphiti
        from palace_mcp.mcp_server import get_driver, get_settings

        driver = get_driver()
        settings = get_settings()

        if driver is None:
            raise ExtractorError(
                error_code=ExtractorErrorCode.SCHEMA_BOOTSTRAP_FAILED,
                message="Neo4j driver not available",
                recoverable=False,
                action="retry",
            )
        if settings is None:
            raise ExtractorError(
                error_code=ExtractorErrorCode.SCHEMA_BOOTSTRAP_FAILED,
                message="Settings not available",
                recoverable=False,
                action="retry",
            )

        previous_error = await _get_previous_error_code(driver, ctx.project_slug)
        check_resume_budget(previous_error_code=previous_error)

        await ensure_custom_schema(driver)
        await create_ingest_run(
            driver,
            run_id=ctx.run_id,
            project=ctx.project_slug,
            extractor_name=self.name,
        )

        try:
            stats = await self._run_pipeline(driver=driver, settings=settings, ctx=ctx)
        except ExtractorError as e:
            await finalize_ingest_run(
                driver, run_id=ctx.run_id, success=False, error_code=e.error_code.value
            )
            raise
        except Exception:
            await finalize_ingest_run(
                driver,
                run_id=ctx.run_id,
                success=False,
                error_code=ExtractorErrorCode.NEO4J_SHADOW_WRITE_FAILED.value,
            )
            raise

        await finalize_ingest_run(driver, run_id=ctx.run_id, success=True)
        return stats

    async def _run_pipeline(
        self,
        *,
        driver: "AsyncDriver",
        settings: "Settings",
        ctx: ExtractorRunContext,
    ) -> ExtractorStats:
        total_nodes = 0
        total_edges = 0

        # Phase 1: load graph
        check_phase_budget(
            nodes_written_so_far=total_nodes,
            max_occurrences_total=settings.palace_max_occurrences_total,
            phase="phase1_defs",
        )
        graph = await load_symbol_graph(driver, group_id=ctx.group_id)
        if not graph.symbols:
            await write_checkpoint(
                driver,
                run_id=ctx.run_id,
                project=ctx.project_slug,
                phase="phase1_defs",
                expected_doc_count=0,
            )
            ctx.logger.info(
                "dead_code: no Symbol nodes found for group_id=%s — skipping",
                ctx.group_id,
            )
            return ExtractorStats(
                outcome=ExtractorOutcome.MISSING_INPUT,
                message=f"no Symbol nodes for group_id={ctx.group_id}",
            )
        await write_checkpoint(
            driver,
            run_id=ctx.run_id,
            project=ctx.project_slug,
            phase="phase1_defs",
            expected_doc_count=len(graph.symbols),
        )

        # Phase 2: BFS + extension chain + SCC
        check_phase_budget(
            nodes_written_so_far=total_nodes,
            max_occurrences_total=settings.palace_max_occurrences_total,
            phase="phase2_user_uses",
        )
        seeds = compute_all_seeds(graph)
        reachable = compute_reachable_set(graph, seeds)
        dead_candidates = compute_dead_candidates(graph, reachable)

        findings = build_findings(graph, dead_candidates, project=ctx.project_slug)

        # Phase 3: git enrichment + write
        check_phase_budget(
            nodes_written_so_far=total_nodes,
            max_occurrences_total=settings.palace_max_occurrences_total,
            phase="phase3_vendor_uses",
        )
        all_member_names = [m.qualified_name for f in findings for m in f.members]
        git_history = await load_git_history(driver, ctx.project_slug, all_member_names)
        findings = enrich_findings_with_git(findings, git_history, graph.symbols)

        write_summary = await write_dead_findings(
            driver=driver,
            findings=findings,
            group_id=ctx.group_id,
        )
        total_nodes += write_summary.nodes_created
        total_edges += write_summary.relationships_created

        await write_checkpoint(
            driver,
            run_id=ctx.run_id,
            project=ctx.project_slug,
            phase="phase3_vendor_uses",
            expected_doc_count=len(findings),
        )

        ctx.logger.info(
            "dead_code: wrote %d findings (%d nodes, %d edges)",
            len(findings),
            total_nodes,
            total_edges,
        )
        return ExtractorStats(nodes_written=total_nodes, edges_written=total_edges)


async def _get_previous_error_code(driver: "AsyncDriver", project: str) -> str | None:
    query = """
    MATCH (r:IngestRun {project: $project, extractor_name: 'dead_code'})
    WHERE r.success = false
    RETURN r.error_code AS error_code
    ORDER BY r.started_at DESC
    LIMIT 1
    """
    async with driver.session() as session:
        result = await session.run(query, project=project)
        record = await result.single()
        return None if record is None else record["error_code"]
