"""SymbolIndexSwift — Swift extractor on 101a foundation (GIM-128).

Reads canonical SCIP protobuf emitted by the local Swift emitter and ingests
Swift DEF/USE occurrences through the standard 3-phase bootstrap:
  Phase 1: defs + decls only (always runs)
  Phase 2: user-code uses above importance threshold (if budget < 50% used)
  Phase 3: vendor uses (if budget < 30% used)
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Sized
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

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
    SCHEMA_VERSION_CURRENT,
    SymbolKind,
    SymbolOccurrence,
)
from palace_mcp.extractors.foundation.schema import ensure_custom_schema
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge
from palace_mcp.extractors.foundation.symbol_node_writer import (
    soft_delete_symbols,
    write_symbol_nodes,
)
from palace_mcp.extractors.scip_parser import (
    FindScipPath,
    ScipPathRequiredError,
    ScipSymbolInfo,
    iter_scip_occurrences,
    iter_scip_symbol_infos,
    parse_scip_file,
)

logger = logging.getLogger(__name__)

_SCIP_KINDS_WITH_SHADOWS = frozenset(
    {
        "Variable",
        "Field",
        "Property",
        "Type",
        "Struct",
        "Class",
        "Enum",
        "Protocol",
        "TypeAlias",
    }
)

_MERGE_SYMBOL_OCCURRENCE_SHADOWS = """
UNWIND $rows AS row
MERGE (shadow:SymbolOccurrenceShadow {
    symbol_id: row.symbol_id,
    symbol_qualified_name: row.symbol_qualified_name,
    group_id: row.group_id
})
SET shadow.language = row.language,
    shadow.importance = row.importance,
    shadow.kind = row.kind,
    shadow.tier_weight = row.tier_weight,
    shadow.last_seen_at = row.last_seen_at,
    shadow.schema_version = row.schema_version,
    shadow.doc_key = row.doc_key,
    shadow.file_path = row.file_path,
    shadow.line = row.line,
    shadow.col_start = row.col_start,
    shadow.col_end = row.col_end,
    shadow.ingest_run_id = row.ingest_run_id
"""

_UPSERT_FILE_HASHES_CYPHER = """
UNWIND $rows AS row
MERGE (f:File {project_id: $project_id, path: row.path})
SET f.group_id = $project_id,
    f.language = 'swift',
    f.body_hash = row.body_hash,
    f.last_seen_in_run_id = $run_id,
    f.last_seen_at = datetime($observed_at),
    f.last_seen_in_commit = $commit_sha,
    f.last_symbol_index_run_id = $run_id,
    f.last_symbol_index_run_at = datetime($observed_at)
REMOVE f:Deprecated
REMOVE f.deprecated_at, f.deprecated_in_commit
WITH f
OPTIONAL MATCH (f)-[old:LAST_SEEN_IN]->()
DELETE old
WITH f
MATCH (run:IngestRun {run_id: $run_id})
MERGE (f)-[:LAST_SEEN_IN]->(run)
"""

_READ_FILE_HASHES_CYPHER = """
MATCH (f:File {project_id: $project_id})
WHERE f.body_hash IS NOT NULL
RETURN f.path AS path, f.body_hash AS body_hash
"""

_GRAPH_BATCH_SIZE = 500


class SymbolIndexSwift(BaseExtractor):
    name: ClassVar[str] = "symbol_index_swift"
    timeout_s: ClassVar[float] = 3600.0
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
            scip_path = ctx.scip_path or FindScipPath.resolve(
                ctx.project_slug, settings
            )
            scip_index = parse_scip_file(scip_path)
            commit_sha = _read_head_sha(ctx.repo_path)

            def _iter_occurrences() -> Iterable[SymbolOccurrence]:
                return iter_scip_occurrences(
                    scip_index,
                    commit_sha=commit_sha,
                    ingest_run_id=ctx.run_id,
                )

            current_body_hashes = _build_file_body_hashes(
                ctx.repo_path, _iter_occurrences()
            )
            previous_body_hashes = await _read_existing_file_body_hashes(
                driver, project_id=ctx.group_id
            )
            if previous_body_hashes and previous_body_hashes == current_body_hashes:
                await _refresh_graph_state(
                    driver,
                    scip_index=scip_index,
                    iter_occurrences=_iter_occurrences,
                    project_id=ctx.group_id,
                    run_id=ctx.run_id,
                    commit_sha=commit_sha,
                    file_body_hashes=current_body_hashes,
                )
                logger.info(
                    "symbol_index_swift.freshness.skip",
                    extra={
                        "extractor": self.name,
                        "project": ctx.project_slug,
                        "run_id": ctx.run_id,
                        "freshness_decision": "skip",
                        "freshness_reason": "body_hash_match",
                        "file_count": len(current_body_hashes),
                    },
                )
                await finalize_ingest_run(driver, run_id=ctx.run_id, success=True)
                return ExtractorStats(
                    outcome=ExtractorOutcome.SKIPPED,
                    message="Skipped re-ingest: file body_hash values matched existing :File nodes.",
                    next_action="Modify source content before rerunning symbol_index_swift.",
                )
            if previous_body_hashes:
                logger.info(
                    "symbol_index_swift.freshness.reingest",
                    extra={
                        "extractor": self.name,
                        "project": ctx.project_slug,
                        "run_id": ctx.run_id,
                        "freshness_decision": "reingest",
                        "freshness_reason": "body_hash_mismatch",
                        "changed_files": [
                            path
                            for path, body_hash in sorted(current_body_hashes.items())
                            if previous_body_hashes.get(path) != body_hash
                        ][:10],
                    },
                )

            tantivy_path = Path(settings.palace_tantivy_index_path)
            counter = _load_or_reset_counter(tantivy_path, ctx.run_id)
            for occ in _iter_occurrences():
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
                p1 = await _ingest_batch(
                    bridge,
                    (
                        occ
                        for occ in _iter_occurrences()
                        if occ.kind in (SymbolKind.DEF, SymbolKind.DECL)
                    ),
                    "phase1_defs",
                )
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
                    p2 = await _ingest_batch(
                        bridge,
                        _iter_phase2_occurrences(
                            occurrences=_iter_occurrences(),
                            counter=counter,
                            settings=settings,
                        ),
                        "phase2_user_uses",
                    )
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
                    p3 = await _ingest_batch(
                        bridge,
                        (
                            _with_importance(occ, counter, settings)
                            for occ in _iter_occurrences()
                            if occ.kind == SymbolKind.USE and _is_vendor(occ.file_path)
                        ),
                        "phase3_vendor_uses",
                    )
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

            counter_path = tantivy_path / "in_degree_counter.json"
            counter.to_disk(counter_path, run_id=ctx.run_id)

            sym_nodes, shadow_count, deleted_count = await _refresh_graph_state(
                driver,
                scip_index=scip_index,
                iter_occurrences=_iter_occurrences,
                project_id=ctx.group_id,
                run_id=ctx.run_id,
                commit_sha=commit_sha,
                file_body_hashes=current_body_hashes,
            )
            logger.info(
                "Symbol nodes written to Neo4j: %d; shadow rows: %d; Tantivy occurrences: %d",
                sym_nodes,
                shadow_count,
                total_written,
            )
            logger.info("Soft-deleted %d absent :Symbol nodes", deleted_count)

            await finalize_ingest_run(driver, run_id=ctx.run_id, success=True)
            # nodes_written reflects Neo4j :Symbol nodes (graph-layer count).
            # Tantivy occurrence count is logged above for observability.
            return ExtractorStats(nodes_written=sym_nodes, edges_written=0)

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
    occurrences: Iterable[SymbolOccurrence],
    phase: str,
    *,
    progress_interval: int = 10_000,
) -> int:
    written = 0
    total = len(occurrences) if isinstance(occurrences, Sized) else None
    for occ in occurrences:
        await bridge.add_or_replace_async(occ, phase)
        written += 1
        if written % progress_interval == 0:
            await bridge.commit_async()
            if total is None:
                logger.info("%s progress: %d written", phase, written)
            else:
                logger.info("%s progress: %d/%d written", phase, written, total)
    return written


def _load_or_reset_counter(tantivy_path: Path, run_id: str) -> BoundedInDegreeCounter:
    return load_or_reset_in_degree_counter(tantivy_path, run_id, logger=logger)


def _build_file_body_hashes(
    repo_path: Path, occurrences: Iterable[SymbolOccurrence]
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for file_path in sorted({occ.file_path for occ in occurrences}):
        hashes[file_path] = hashlib.sha256(
            (repo_path / file_path).read_bytes()
        ).hexdigest()
    return hashes


async def _read_existing_file_body_hashes(
    driver: AsyncDriver, *, project_id: str
) -> dict[str, str]:
    async with driver.session() as session:
        result = await session.run(_READ_FILE_HASHES_CYPHER, project_id=project_id)
        rows = await result.data()
    return {
        str(row["path"]): str(row.get("body_hash") or "")
        for row in rows
        if row.get("path")
    }


async def _write_file_body_hashes(
    driver: AsyncDriver,
    *,
    project_id: str,
    run_id: str,
    file_body_hashes: dict[str, str],
    observed_at: datetime,
    commit_sha: str,
) -> int:
    if not file_body_hashes:
        return 0
    rows = [
        {"path": path, "body_hash": body_hash}
        for path, body_hash in sorted(file_body_hashes.items())
    ]
    observed_at_str = observed_at.isoformat()
    async with driver.session() as session:
        for i in range(0, len(rows), _GRAPH_BATCH_SIZE):
            result = await session.run(
                _UPSERT_FILE_HASHES_CYPHER,
                rows=rows[i : i + _GRAPH_BATCH_SIZE],
                project_id=project_id,
                run_id=run_id,
                observed_at=observed_at_str,
                commit_sha=commit_sha,
            )
            await result.consume()
    return len(rows)


async def _refresh_graph_state(
    driver: AsyncDriver,
    *,
    scip_index: object,
    iter_occurrences: Callable[[], Iterable[SymbolOccurrence]],
    project_id: str,
    run_id: str,
    commit_sha: str,
    file_body_hashes: dict[str, str],
) -> tuple[int, int, int]:
    # Keep graph-layer freshness aligned even when Tantivy ingest is skipped.
    def_file_paths: dict[str, str] = {}
    def_line_starts: dict[str, int] = {}
    for occ in iter_occurrences():
        if occ.kind in (SymbolKind.DEF, SymbolKind.DECL):
            def_file_paths.setdefault(occ.symbol_qualified_name, occ.file_path)
            # SCIP ranges are 0-based; snippet windows / get_code_snippet are
            # 1-based. Record the declaration line so the snippet windows on the
            # symbol instead of falling back to the file head (dogfood W8c).
            def_line_starts.setdefault(occ.symbol_qualified_name, occ.line + 1)

    graph_seen_at = datetime.now(tz=timezone.utc)
    shadow_rows = _build_shadow_rows(
        occurrences=iter_occurrences(),
        symbol_infos=iter_scip_symbol_infos(scip_index),
        group_id=project_id,
        seen_at=graph_seen_at,
    )
    shadow_count = await _write_shadow_rows(driver, shadow_rows)

    sym_nodes = 0
    seen_qnames: set[str] = set()
    sym_batch: list[ScipSymbolInfo] = []
    sym_batch_size = 5000
    for sym_info in iter_scip_symbol_infos(scip_index):
        seen_qnames.add(sym_info.qualified_name)
        sym_batch.append(sym_info)
        if len(sym_batch) >= sym_batch_size:
            sym_nodes += await write_symbol_nodes(
                driver,
                sym_batch,
                def_file_paths,
                project_id,
                project_id=project_id,
                run_id=run_id,
                seen_at=graph_seen_at,
                commit_sha=commit_sha,
                def_line_starts=def_line_starts,
            )
            sym_batch = []
    if sym_batch:
        sym_nodes += await write_symbol_nodes(
            driver,
            sym_batch,
            def_file_paths,
            project_id,
            project_id=project_id,
            run_id=run_id,
            seen_at=graph_seen_at,
            commit_sha=commit_sha,
            def_line_starts=def_line_starts,
        )

    deleted_count = 0
    if seen_qnames:
        deleted_count = await soft_delete_symbols(
            driver, project_id, seen_qnames, datetime.now(tz=timezone.utc)
        )

    await _write_file_body_hashes(
        driver,
        project_id=project_id,
        run_id=run_id,
        file_body_hashes=file_body_hashes,
        observed_at=graph_seen_at,
        commit_sha=commit_sha,
    )
    return sym_nodes, shadow_count, deleted_count


def _build_shadow_rows(
    *,
    occurrences: Iterable[SymbolOccurrence],
    symbol_infos: Iterable[ScipSymbolInfo],
    group_id: str,
    seen_at: datetime,
) -> list[dict[str, object]]:
    target_qnames = {
        si.qualified_name
        for si in symbol_infos
        if si.scip_kind_name in _SCIP_KINDS_WITH_SHADOWS
    }
    if not target_qnames:
        return []

    rows_by_qname: dict[str, dict[str, object]] = {}
    for occ in occurrences:
        if occ.kind not in (SymbolKind.DEF, SymbolKind.DECL):
            continue
        if occ.symbol_qualified_name not in target_qnames:
            continue
        rows_by_qname.setdefault(
            occ.symbol_qualified_name,
            {
                "symbol_id": occ.symbol_id,
                "symbol_qualified_name": occ.symbol_qualified_name,
                "group_id": group_id,
                "language": occ.language.value,
                "importance": 1.0,
                "kind": occ.kind.value,
                "tier_weight": tier_weight(occ.file_path),
                "last_seen_at": seen_at.isoformat(),
                "schema_version": SCHEMA_VERSION_CURRENT,
                "doc_key": occ.doc_key,
                "file_path": occ.file_path,
                "line": occ.line,
                "col_start": occ.col_start,
                "col_end": occ.col_end,
                "ingest_run_id": occ.ingest_run_id,
            },
        )
    return list(rows_by_qname.values())


async def _write_shadow_rows(
    driver: AsyncDriver,
    rows: list[dict[str, object]],
) -> int:
    if not rows:
        return 0
    async with driver.session() as session:
        for i in range(0, len(rows), _GRAPH_BATCH_SIZE):
            await session.run(
                _MERGE_SYMBOL_OCCURRENCE_SHADOWS,
                rows=rows[i : i + _GRAPH_BATCH_SIZE],
            )
    return len(rows)


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


def _iter_phase2_occurrences(
    *,
    occurrences: Iterable[SymbolOccurrence],
    counter: BoundedInDegreeCounter,
    settings: object,
) -> Iterable[SymbolOccurrence]:
    threshold = getattr(settings, "palace_importance_threshold_use")
    for occ in occurrences:
        if occ.kind != SymbolKind.USE or _is_vendor(occ.file_path):
            continue
        occ = _with_importance(occ, counter, settings)
        if occ.importance >= threshold:
            yield occ


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
