"""DeadCodeExtractor — G0d algorithm orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from graphiti_core import Graphiti

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorExecutionMode,
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
from palace_mcp.extractors.dead_code.incremental import (
    compute_incremental_reachable,
    should_fallback_to_full,
)
from palace_mcp.extractors.dead_code.neo4j_writer import (
    _members_json,
    load_dead_finding_props,
    write_dead_findings,
    write_symbol_reachability,
)
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
from palace_mcp.extractors.foundation.incremental_scope import (
    IncrementalMode,
    derive_incremental_path_scope,
)
from palace_mcp.extractors.foundation.schema import ensure_custom_schema
from palace_mcp.extractors.foundation.delta_resolution import (
    ResolvedDelta,
    read_delta_resolution_baseline_artifact,
    resolve_delta_resolution,
)

if TYPE_CHECKING:
    from neo4j import AsyncDriver
    from palace_mcp.config import Settings

_SWIFT_SOURCE_SUFFIXES = (".swift", ".swiftinterface")


class DeadCodeExtractor(BaseExtractor):
    """Graph-reachability dead-code analysis (G0d algorithm).

    Distinct from dead_symbol_binary_surface (Periphery/binary-surface approach).
    This extractor uses the SCIP call/reference graph to identify unreachable
    code clusters, extension chains, and individual dead symbols.
    """

    name: ClassVar[str] = "dead_code"
    timeout_s: ClassVar[float] = 3600.0
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
        "FOR (n:DeadFinding) ON (n.project, n.severity)",
        "CREATE INDEX symbol_reachable_run IF NOT EXISTS "
        "FOR (s:Symbol) ON (s.group_id, s.reachable_run_id)",
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
        scope = await derive_incremental_path_scope(
            driver,
            repo_path=ctx.repo_path,
            project_id=ctx.group_id,
            settings=settings,
            force=ctx.force,
            path_filter=lambda path: path.endswith(_SWIFT_SOURCE_SUFFIXES),
        )
        if scope.mode == IncrementalMode.SKIP:
            return ExtractorStats(
                outcome=ExtractorOutcome.SKIPPED,
                message="Skipped dead_code: no changed Swift symbol files.",
                next_action="Modify Swift source or run with force=True before rerunning dead_code.",
                mode=ExtractorExecutionMode.SKIPPED,
            )

        mode = (
            ExtractorExecutionMode.INCREMENTAL
            if scope.mode == IncrementalMode.INCREMENTAL
            else ExtractorExecutionMode.FULL
        )
        fallback_reason: str | None = None
        resolved_delta: ResolvedDelta | None = None
        if (
            mode == ExtractorExecutionMode.INCREMENTAL
            and ctx.companion_run_id is not None
        ):
            baseline = read_delta_resolution_baseline_artifact(
                repo_path=ctx.repo_path,
                run_id=ctx.companion_run_id,
            )
            if baseline is None:
                fallback_reason = "delta_baseline_missing"
                mode = ExtractorExecutionMode.FULL
            else:
                resolved_delta = await resolve_delta_resolution(
                    driver,
                    baseline=baseline,
                    current_commit_sha=_read_head_sha(ctx.repo_path),
                )
                if not _delta_has_changes(resolved_delta):
                    return ExtractorStats(
                        outcome=ExtractorOutcome.SKIPPED,
                        message="Skipped dead_code: resolved delta was empty.",
                        next_action="Modify symbol graph inputs or run with force=True before rerunning dead_code.",
                        mode=ExtractorExecutionMode.SKIPPED,
                    )
        elif mode == ExtractorExecutionMode.INCREMENTAL:
            fallback_reason = "companion_run_missing"
            mode = ExtractorExecutionMode.FULL

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
        # Pre-flight: dead_code BFS needs Symbol→Symbol call edges
        # (CALLS, REFERENCES, EXTENDS, CONFORMS_TO, EXTENSION_OF, EXISTENTIAL_USE).
        # These are populated by codebase_memory_bridge. If a project has many
        # Symbol nodes but zero edges, the algorithm degenerates: every symbol
        # is unreachable from every seed, so all N symbols are classified dead.
        # build_findings then iterates over N entries. On native-only ingest of
        # uw-ios-baseline this hit the 3600 s extractor timeout with N=250 595
        # and edges=0. Skip early with a clear message instead of stalling.
        if not graph.edges:
            await write_checkpoint(
                driver,
                run_id=ctx.run_id,
                project=ctx.project_slug,
                phase="phase1_defs",
                expected_doc_count=len(graph.symbols),
            )
            ctx.logger.warning(
                "dead_code: %d Symbol nodes but 0 call/reference edges for "
                "group_id=%s — run codebase_memory_bridge first to materialize "
                "CALLS/REFERENCES/EXTENDS/CONFORMS_TO/EXTENSION_OF/EXISTENTIAL_USE "
                "edges; dead_code BFS is meaningless without them",
                len(graph.symbols),
                ctx.group_id,
            )
            return ExtractorStats(
                outcome=ExtractorOutcome.MISSING_INPUT,
                message=(
                    f"{len(graph.symbols)} Symbol nodes but 0 call/reference "
                    f"edges for group_id={ctx.group_id} — run "
                    "codebase_memory_bridge first to materialize the SCIP "
                    "call graph; dead_code BFS is meaningless without edges"
                ),
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
        existing_findings = await load_dead_finding_props(
            driver=driver,
            group_id=ctx.group_id,
        )
        seeds = compute_all_seeds(graph)
        reachable: frozenset[str]
        if mode == ExtractorExecutionMode.INCREMENTAL and resolved_delta is not None:
            previous_live = {
                qname
                for qname, symbol in graph.symbols.items()
                if symbol.reachable_run_id is not None
            }
            if not previous_live:
                fallback_reason = "reachable_state_missing"
                mode = ExtractorExecutionMode.FULL
                reachable = compute_reachable_set(graph, seeds)
            else:
                reachable, affected = compute_incremental_reachable(
                    graph=graph,
                    delta=resolved_delta,
                    previous_live=previous_live,
                    seeds=seeds,
                )
                threshold = float(
                    getattr(
                        settings,
                        "palace_incremental_deadcode_full_threshold",
                        0.2,
                    )
                )
                if should_fallback_to_full(
                    affected_count=len(affected),
                    total_symbols=len(graph.symbols),
                    threshold_ratio=threshold,
                ):
                    fallback_reason = "affected_threshold_exceeded"
                    mode = ExtractorExecutionMode.FULL
                    reachable = compute_reachable_set(graph, seeds)
                else:
                    await write_symbol_reachability(
                        driver=driver,
                        group_id=ctx.group_id,
                        reachable_qnames=reachable & affected,
                        unreachable_qnames=affected - reachable,
                        run_id=ctx.run_id,
                    )
        else:
            reachable = compute_reachable_set(graph, seeds)

        if mode == ExtractorExecutionMode.FULL:
            await write_symbol_reachability(
                driver=driver,
                group_id=ctx.group_id,
                reachable_qnames=reachable,
                unreachable_qnames=set(graph.symbols) - reachable,
                run_id=ctx.run_id,
            )

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
        findings_to_write, stale_finding_ids = _diff_findings_against_existing(
            findings=findings,
            existing=existing_findings,
            group_id=ctx.group_id,
        )

        write_summary = await write_dead_findings(
            driver=driver,
            findings=findings_to_write,
            group_id=ctx.group_id,
            stale_finding_ids=stale_finding_ids,
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
            "dead_code: wrote %d changed findings (%d total findings, %d nodes, %d edges, mode=%s, fallback_reason=%s)",
            len(findings_to_write),
            len(findings),
            total_nodes,
            total_edges,
            mode.value,
            fallback_reason,
        )
        message = None
        if fallback_reason is not None:
            message = f"incremental fallback to full: {fallback_reason}"
        return ExtractorStats(
            nodes_written=total_nodes,
            edges_written=total_edges,
            message=message,
            mode=mode,
        )


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


def _delta_has_changes(delta: ResolvedDelta) -> bool:
    return any(
        (
            delta.symbol_deltas,
            delta.edge_deltas,
            delta.seed_deltas,
            delta.public_api_deltas,
        )
    )


def _stable_finding_props(finding: Any, group_id: str) -> dict[str, Any]:
    props: dict[str, Any] = {
        "group_id": group_id,
        "kind": finding.kind.value,
        "severity": finding.severity.value,
        "project": finding.project,
        "size": finding.size,
        "reachable_from_public_surface": finding.reachable_from_public_surface,
        "reachable_from_dynamic_dispatch": finding.reachable_from_dynamic_dispatch,
        "safe_to_delete_score": finding.safe_to_delete_score,
        "evidence_query": finding.evidence_query,
        "members_json": _members_json(finding),
    }
    if finding.git_last_external_ref is not None:
        props["git_last_external_ref"] = finding.git_last_external_ref
    if finding.module_coverage_ratio is not None:
        props["module_coverage_ratio"] = finding.module_coverage_ratio
    if finding.target_dead_type is not None:
        props["target_dead_type"] = finding.target_dead_type
    return props


def _normalize_existing_props(props: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in props.items() if key != "created_at"}


def _diff_findings_against_existing(
    *,
    findings: list[Any],
    existing: dict[str, dict[str, Any]],
    group_id: str,
) -> tuple[list[Any], list[str]]:
    current_props = {
        finding.finding_id: _stable_finding_props(finding, group_id)
        for finding in findings
    }
    changed = [
        finding
        for finding in findings
        if _normalize_existing_props(existing.get(finding.finding_id, {}))
        != current_props[finding.finding_id]
    ]
    stale = sorted(set(existing) - set(current_props))
    return changed, stale


def _read_head_sha(repo_path: Path) -> str:
    try:
        git_dir, refs_root = _resolve_git_dirs(repo_path)
    except (FileNotFoundError, OSError, ValueError):
        return "unknown"

    head_path = git_dir / "HEAD"
    try:
        head = head_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "unknown"
    if not head.startswith("ref: "):
        return head[:40]
    ref_name = head.removeprefix("ref: ").strip()
    ref_path = refs_root / ref_name
    try:
        return ref_path.read_text(encoding="utf-8").strip()[:40]
    except FileNotFoundError:
        return _read_packed_ref(refs_root, ref_name)


def _resolve_git_dirs(repo_path: Path) -> tuple[Path, Path]:
    git_path = repo_path / ".git"
    if git_path.is_dir():
        git_dir = git_path
    else:
        pointer = git_path.read_text(encoding="utf-8").strip()
        if not pointer.startswith("gitdir: "):
            raise ValueError("invalid gitdir pointer")
        git_dir = (repo_path / pointer.removeprefix("gitdir: ").strip()).resolve()

    commondir_path = git_dir / "commondir"
    if commondir_path.exists():
        common_dir = (
            git_dir / commondir_path.read_text(encoding="utf-8").strip()
        ).resolve()
        return git_dir, common_dir
    return git_dir, git_dir


def _read_packed_ref(refs_root: Path, ref_name: str) -> str:
    packed_refs_path = refs_root / "packed-refs"
    try:
        for line in packed_refs_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "^")):
                continue
            sha, _, packed_ref_name = stripped.partition(" ")
            if packed_ref_name == ref_name:
                return sha[:40]
    except FileNotFoundError:
        return "unknown"
    return "unknown"
