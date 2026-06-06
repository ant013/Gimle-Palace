"""SymbolIndexSwift — Swift extractor on 101a foundation (GIM-128).

Reads canonical SCIP protobuf emitted by the local Swift emitter and ingests
Swift DEF/USE occurrences through the standard 3-phase bootstrap:
  Phase 1: defs + decls only (always runs)
  Phase 2: user-code uses above importance threshold (if budget < 50% used)
  Phase 3: vendor uses (if budget < 30% used)
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

from graphiti_core import Graphiti
from neo4j import AsyncDriver

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorOutcome,
    ExtractorRunContext,
    ExtractorStats,
)
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
from palace_mcp.extractors.foundation.importance import (
    BoundedInDegreeCounter,
    importance_score,
    load_or_reset_in_degree_counter,
    tier_weight,
)
from palace_mcp.extractors.foundation.models import (
    Language,
    SymbolKind,
    SymbolOccurrence,
)
from palace_mcp.extractors.foundation.schema import ensure_custom_schema
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge
from palace_mcp.extractors.scip_parser import (
    FindScipPath,
    ScipPathRequiredError,
    iter_scip_occurrences,
    parse_scip_file,
)

logger = logging.getLogger(__name__)

_GRAPH_BATCH_SIZE = 1_000
_WRITE_FUNCTIONS_CYPHER = """
UNWIND $rows AS row
MERGE (f:File {project_id: $project_id, path: row.file_path})
SET f.group_id = $group_id,
    f.body_hash = row.body_hash,
    f.language = row.language,
    f.last_symbol_index_run_id = $run_id,
    f.last_symbol_index_run_at = datetime($observed_at)
WITH f, row
MERGE (fn:Function {
    project_id: $project_id,
    path: row.file_path,
    qualified_name: row.symbol_qualified_name,
    start_line: row.start_line
})
SET fn.group_id = $group_id,
    fn.name = row.name,
    fn.display_name = row.name,
    fn.symbol_qualified_name = row.symbol_qualified_name,
    fn.end_line = row.end_line,
    fn.language = row.language,
    fn.kind = row.kind,
    fn.importance = row.importance,
    fn.commit_sha = row.commit_sha,
    fn.last_run_id = $run_id,
    fn.last_run_at = datetime($observed_at),
    fn.extractor = 'symbol_index_swift'
MERGE (f)-[:CONTAINS]->(fn)
"""
_READ_FILE_HASHES_CYPHER = """
MATCH (f:File {project_id: $project_id})
RETURN f.path AS path, f.body_hash AS body_hash
"""
_WRITE_SHADOWS_CYPHER = """
UNWIND $rows AS row
MERGE (shadow:SymbolOccurrenceShadow {
    group_id: $group_id,
    symbol_id: row.symbol_id,
    symbol_qualified_name: row.symbol_qualified_name,
    kind: row.kind
})
SET shadow.language = row.language,
    shadow.importance = row.importance,
    shadow.tier_weight = row.tier_weight,
    shadow.last_seen_at = datetime($observed_at),
    shadow.schema_version = row.schema_version,
    shadow.commit_sha = row.commit_sha,
    shadow.project = $project,
    shadow.run_id = $run_id
"""


class SymbolIndexSwift(BaseExtractor):
    name: ClassVar[str] = "symbol_index_swift"
    timeout_s: ClassVar[float] = 1800.0
    description: ClassVar[str] = (
        "Ingest Swift symbols + occurrences from pre-generated SCIP file "
        "(palace-swift-scip-emit) into Tantivy (full-text) and Neo4j "
        "(IngestRun + checkpoint). Handles .swift/.swiftinterface in one "
        "pass. 3-phase bootstrap: defs/decls → user uses → vendor uses."
    )
    primary_lang: ClassVar[Language] = Language.SWIFT

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        from palace_mcp.mcp_server import get_driver, get_settings

        driver = get_driver()
        settings = get_settings()

        if driver is None:
            raise ExtractorError(
                error_code=ExtractorErrorCode.SCHEMA_BOOTSTRAP_FAILED,
                message="Neo4j driver not available — call set_driver() before run_extractor",
                recoverable=False,
                action="retry",
            )
        if settings is None:
            raise ExtractorError(
                error_code=ExtractorErrorCode.SCHEMA_BOOTSTRAP_FAILED,
                message="Settings not available — call set_settings() before run_extractor",
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
            scip_path = FindScipPath.resolve(ctx.project_slug, settings)
            scip_index = parse_scip_file(scip_path)
            commit_sha = _read_head_sha(ctx.repo_path)
            all_occs = list(
                iter_scip_occurrences(
                    scip_index,
                    commit_sha=commit_sha,
                    ingest_run_id=ctx.run_id,
                )
            )
            current_body_hashes = _build_file_body_hashes(ctx.repo_path, all_occs)
            previous_body_hashes = await _read_existing_file_body_hashes(
                driver, project=ctx.project_slug
            )
            if previous_body_hashes == current_body_hashes:
                logger.info(
                    "symbol_index_swift.freshness.skip",
                    extra={
                        "extractor": self.name,
                        "project": ctx.project_slug,
                        "run_id": ctx.run_id,
                        "freshness_decision": "skip",
                        "freshness_reason": "body_hash_match",
                        "file_count": len(current_body_hashes),
                        "body_hashes": [
                            {"path": path, "body_hash": body_hash}
                            for path, body_hash in sorted(current_body_hashes.items())[
                                :10
                            ]
                        ],
                    },
                )
                await finalize_ingest_run(driver, run_id=ctx.run_id, success=True)
                return ExtractorStats(
                    outcome=ExtractorOutcome.SKIPPED,
                    message="Skipped re-ingest: file body_hash values matched existing :File nodes.",
                    next_action="Modify source content before rerunning symbol_index_swift.",
                )
            if previous_body_hashes:
                changed_paths = sorted(
                    path
                    for path, body_hash in current_body_hashes.items()
                    if previous_body_hashes.get(path) != body_hash
                )
                removed_paths = sorted(set(previous_body_hashes) - set(current_body_hashes))
                logger.info(
                    "symbol_index_swift.freshness.reingest",
                    extra={
                        "extractor": self.name,
                        "project": ctx.project_slug,
                        "run_id": ctx.run_id,
                        "freshness_decision": "reingest",
                        "freshness_reason": "body_hash_mismatch",
                        "changed_files": [
                            {
                                "path": path,
                                "previous_body_hash": previous_body_hashes.get(path, ""),
                                "body_hash": current_body_hashes[path],
                            }
                            for path in changed_paths[:10]
                        ],
                        "removed_paths": removed_paths[:10],
                    },
                )

            tantivy_path = Path(settings.palace_tantivy_index_path)
            counter = _load_or_reset_counter(tantivy_path, ctx.run_id)
            for occ in all_occs:
                if occ.kind == SymbolKind.USE:
                    counter.increment(occ.symbol_qualified_name)

            total_written = 0
            async with TantivyBridge(
                tantivy_path,
                heap_size_mb=settings.palace_tantivy_heap_mb,
            ) as bridge:
                check_phase_budget(
                    nodes_written_so_far=total_written,
                    max_occurrences_total=settings.palace_max_occurrences_total,
                    phase="phase1_defs",
                )
                phase1 = [
                    o for o in all_occs if o.kind in (SymbolKind.DEF, SymbolKind.DECL)
                ]
                p1 = await _ingest_batch(bridge, phase1, "phase1_defs")
                await bridge.commit_async()
                await write_checkpoint(
                    driver,
                    run_id=ctx.run_id,
                    project=ctx.project_slug,
                    phase="phase1_defs",
                    expected_doc_count=p1,
                )
                total_written += p1
                logger.info("Phase 1 (defs+decls): %d written", p1)

                phase2: list[SymbolOccurrence] = []
                p2 = 0
                budget_frac = total_written / max(
                    settings.palace_max_occurrences_per_project, 1
                )
                if budget_frac < 0.5:
                    check_phase_budget(
                        nodes_written_so_far=total_written,
                        max_occurrences_total=settings.palace_max_occurrences_total,
                        phase="phase2_user_uses",
                    )
                    phase2 = [
                        _with_importance(o, counter, settings)
                        for o in all_occs
                        if o.kind == SymbolKind.USE and not _is_vendor(o.file_path)
                    ]
                    phase2 = [
                        o
                        for o in phase2
                        if o.importance >= settings.palace_importance_threshold_use
                    ]
                    p2 = await _ingest_batch(bridge, phase2, "phase2_user_uses")
                    await bridge.commit_async()
                    await write_checkpoint(
                        driver,
                        run_id=ctx.run_id,
                        project=ctx.project_slug,
                        phase="phase2_user_uses",
                        expected_doc_count=p1 + p2,
                    )
                    total_written += p2
                    logger.info("Phase 2 (user uses): %d written", p2)

                phase3: list[SymbolOccurrence] = []
                p3 = 0
                budget_frac = total_written / max(
                    settings.palace_max_occurrences_per_project, 1
                )
                if budget_frac < 0.3:
                    check_phase_budget(
                        nodes_written_so_far=total_written,
                        max_occurrences_total=settings.palace_max_occurrences_total,
                        phase="phase3_vendor_uses",
                    )
                    phase3 = [
                        _with_importance(o, counter, settings)
                        for o in all_occs
                        if o.kind == SymbolKind.USE and _is_vendor(o.file_path)
                    ]
                    p3 = await _ingest_batch(bridge, phase3, "phase3_vendor_uses")
                    if p3 > 0:
                        await bridge.commit_async()
                        await write_checkpoint(
                            driver,
                            run_id=ctx.run_id,
                            project=ctx.project_slug,
                            phase="phase3_vendor_uses",
                            expected_doc_count=p1 + p2 + p3,
                        )
                    total_written += p3
                    logger.info("Phase 3 (vendor uses): %d written", p3)

            graph_nodes_written, graph_edges_written = await _write_graph_projection(
                driver,
                project=ctx.project_slug,
                group_id=ctx.group_id,
                run_id=ctx.run_id,
                file_body_hashes=current_body_hashes,
                function_occurrences=phase1,
                shadow_occurrences=phase1 + phase2 + phase3,
            )
            counter_path = tantivy_path / "in_degree_counter.json"
            counter.to_disk(counter_path, run_id=ctx.run_id)

            await finalize_ingest_run(driver, run_id=ctx.run_id, success=True)
            return ExtractorStats(
                nodes_written=graph_nodes_written,
                edges_written=graph_edges_written,
            )

        except ScipPathRequiredError as e:
            await finalize_ingest_run(
                driver,
                run_id=ctx.run_id,
                success=False,
                error_code=ExtractorErrorCode.SCIP_PATH_REQUIRED.value,
            )
            raise ExtractorError(
                error_code=ExtractorErrorCode.SCIP_PATH_REQUIRED,
                message=str(e),
                recoverable=False,
                action="manual_cleanup",
            ) from e
        except ExtractorError:
            await finalize_ingest_run(
                driver, run_id=ctx.run_id, success=False, error_code="extractor_error"
            )
            raise
        except Exception:
            await finalize_ingest_run(
                driver, run_id=ctx.run_id, success=False, error_code="unknown"
            )
            raise


async def _ingest_batch(
    bridge: TantivyBridge,
    occurrences: list[SymbolOccurrence],
    phase: str,
    *,
    progress_interval: int = 10_000,
) -> int:
    written = 0
    total = len(occurrences)
    for occ in occurrences:
        await bridge.add_or_replace_async(occ, phase)
        written += 1
        if written % progress_interval == 0:
            await bridge.commit_async()
            logger.info("%s progress: %d/%d written", phase, written, total)
    return written


async def _write_graph_projection(
    driver: AsyncDriver,
    *,
    project: str,
    group_id: str,
    run_id: str,
    file_body_hashes: dict[str, str],
    function_occurrences: list[SymbolOccurrence],
    shadow_occurrences: list[SymbolOccurrence],
) -> tuple[int, int]:
    function_rows = _build_function_rows(function_occurrences, file_body_hashes)
    shadow_rows = _build_shadow_rows(shadow_occurrences)
    observed_at = datetime.now(timezone.utc).isoformat()

    await _write_batched_rows(
        driver,
        query=_WRITE_FUNCTIONS_CYPHER,
        rows=function_rows,
        project=project,
        group_id=group_id,
        run_id=run_id,
        observed_at=observed_at,
        log_label="phase1_graph_functions",
    )
    await _write_batched_rows(
        driver,
        query=_WRITE_SHADOWS_CYPHER,
        rows=shadow_rows,
        project=project,
        group_id=group_id,
        run_id=run_id,
        observed_at=observed_at,
        log_label="phase2_graph_shadows",
    )
    return len(function_rows) + len(shadow_rows), len(function_rows)


async def _write_batched_rows(
    driver: AsyncDriver,
    *,
    query: str,
    rows: list[dict[str, Any]],
    project: str,
    group_id: str,
    run_id: str,
    observed_at: str,
    log_label: str,
) -> None:
    total = len(rows)
    if total == 0:
        return
    async with driver.session() as session:
        for start in range(0, total, _GRAPH_BATCH_SIZE):
            batch = rows[start : start + _GRAPH_BATCH_SIZE]
            result = await session.run(
                query,
                rows=batch,
                project=project,
                project_id=group_id,
                group_id=group_id,
                run_id=run_id,
                observed_at=observed_at,
            )
            await result.consume()
            logger.info(
                "%s progress: %d/%d written",
                log_label,
                min(start + len(batch), total),
                total,
            )


def _build_function_rows(
    occurrences: list[SymbolOccurrence],
    file_body_hashes: dict[str, str],
) -> list[dict[str, Any]]:
    rows: dict[tuple[str, str, int], dict[str, Any]] = {}
    for occ in occurrences:
        key = (occ.file_path, occ.symbol_qualified_name, occ.line)
        current = rows.get(key)
        row = {
            "file_path": occ.file_path,
            "body_hash": file_body_hashes[occ.file_path],
            "symbol_qualified_name": occ.symbol_qualified_name,
            "name": occ.symbol_qualified_name,
            "start_line": occ.line,
            "end_line": occ.line,
            "language": occ.language.value,
            "kind": occ.kind.value,
            "importance": occ.importance,
            "commit_sha": occ.commit_sha,
        }
        if current is None or current["kind"] == SymbolKind.DECL.value:
            rows[key] = row
    return list(rows.values())


def _build_shadow_rows(
    occurrences: list[SymbolOccurrence],
) -> list[dict[str, Any]]:
    rows: dict[tuple[int, str, str], dict[str, Any]] = {}
    for occ in occurrences:
        key = (occ.symbol_id, occ.symbol_qualified_name, occ.kind.value)
        row = rows.get(key)
        if row is None or occ.importance > float(row["importance"]):
            rows[key] = {
                "symbol_id": occ.symbol_id,
                "symbol_qualified_name": occ.symbol_qualified_name,
                "kind": occ.kind.value,
                "language": occ.language.value,
                "importance": occ.importance,
                "tier_weight": tier_weight(occ.file_path),
                "commit_sha": occ.commit_sha,
                "schema_version": 1,
            }
    return list(rows.values())


def _load_or_reset_counter(tantivy_path: Path, run_id: str) -> BoundedInDegreeCounter:
    return load_or_reset_in_degree_counter(tantivy_path, run_id, logger=logger)


def _build_file_body_hashes(
    repo_path: Path, occurrences: list[SymbolOccurrence]
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for file_path in sorted({occ.file_path for occ in occurrences}):
        hashes[file_path] = hashlib.sha256((repo_path / file_path).read_bytes()).hexdigest()
    return hashes


async def _read_existing_file_body_hashes(
    driver: AsyncDriver, *, project: str
) -> dict[str, str]:
    async with driver.session() as session:
        result = await session.run(_READ_FILE_HASHES_CYPHER, project_id=project)
        rows = await result.data()
    return {
        str(row["path"]): str(row.get("body_hash") or "")
        for row in rows
        if row.get("path")
    }


def _with_importance(
    occ: SymbolOccurrence,
    counter: BoundedInDegreeCounter,
    settings: object,
) -> SymbolOccurrence:
    score = importance_score(
        cms_in_degree=counter.estimate(occ.symbol_qualified_name),
        file_path=occ.file_path,
        kind=occ.kind,
        last_seen_at=datetime.now(tz=timezone.utc),
        language=occ.language,
        primary_lang=Language.SWIFT,
        half_life_days=getattr(settings, "palace_recency_decay_days", 30.0),
    )
    return SymbolOccurrence(
        doc_key=occ.doc_key,
        symbol_id=occ.symbol_id,
        symbol_qualified_name=occ.symbol_qualified_name,
        kind=occ.kind,
        language=occ.language,
        file_path=occ.file_path,
        line=occ.line,
        col_start=occ.col_start,
        col_end=occ.col_end,
        importance=score,
        commit_sha=occ.commit_sha,
        ingest_run_id=occ.ingest_run_id,
    )


def _is_vendor(file_path: str) -> bool:
    vendor_markers = (
        "Pods/",
        "Carthage/",
        "SourcePackages/",
        ".build/",
        ".swiftpm/",
        "DerivedData/",
    )
    return any(marker in file_path for marker in vendor_markers)


def _read_head_sha(repo_path: Path) -> str:
    head_file = repo_path / ".git" / "HEAD"
    try:
        ref = head_file.read_text().strip()
        if ref.startswith("ref: "):
            ref_path = repo_path / ".git" / ref[5:]
            return ref_path.read_text().strip()[:40]
        return ref[:40]
    except (FileNotFoundError, OSError):
        return "unknown"


async def _get_previous_error_code(driver: AsyncDriver, project: str) -> str | None:
    query = """
    MATCH (r:IngestRun {project: $project, extractor_name: 'symbol_index_swift'})
    WHERE r.success = false
    RETURN r.error_code AS error_code
    ORDER BY r.started_at DESC
    LIMIT 1
    """
    async with driver.session() as session:
        result = await session.run(query, project=project)
        record = await result.single()
        return None if record is None else record["error_code"]
