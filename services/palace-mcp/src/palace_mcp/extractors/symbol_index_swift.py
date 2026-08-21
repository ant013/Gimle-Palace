"""SymbolIndexSwift — Swift extractor on 101a foundation (GIM-128).

Reads canonical SCIP protobuf emitted by the local Swift emitter and ingests
Swift DEF/USE occurrences through the standard 3-phase bootstrap:
  Phase 1: defs + decls only (always runs)
  Phase 2: user-code uses above importance threshold (if budget < 50% used)
  Phase 3: vendor uses (if budget < 30% used)
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Iterable, Sized
from dataclasses import dataclass, replace
import logging
from datetime import datetime, timezone
from pathlib import Path
import re
from time import perf_counter
from typing import ClassVar

from graphiti_core import Graphiti
from neo4j import AsyncDriver

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorExecutionMode,
    ExtractorIncrementalCapability,
    ExtractorOutcome,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.foundation.checkpoint import (
    create_ingest_run,
    finalize_ingest_run,
    write_checkpoint,
)
from palace_mcp.extractors.foundation.baseline import (
    BASELINE_STATUS_VALID,
    build_valid_extractor_baseline,
    load_extractor_baseline,
    upsert_extractor_baseline,
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
from palace_mcp.extractors.foundation.delta_resolution import (
    capture_delta_resolution_baseline,
    write_delta_resolution_baseline_artifact,
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
    bump_unchanged_symbol_liveness,
    delete_stale_relationships,
    soft_delete_symbols,
    soft_delete_symbols_for_paths,
    write_symbol_nodes,
)
from palace_mcp.git.command import GitError, GitTimeout, run_git
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

_CLEAR_ABSENT_FILE_HASHES_CYPHER = """
MATCH (f:File {project_id: $project_id})
WHERE f.body_hash IS NOT NULL
  AND f.last_symbol_index_run_id IS NOT NULL
  AND NOT f.path IN $current_paths
SET f.last_symbol_index_removed_in_run_id = $run_id,
    f.last_symbol_index_removed_at = datetime($observed_at),
    f.last_symbol_index_removed_in_commit = $commit_sha
REMOVE f.body_hash
"""

_CLEAR_REMOVED_FILE_HASHES_CYPHER = """
MATCH (f:File {project_id: $project_id})
WHERE f.body_hash IS NOT NULL
  AND f.last_symbol_index_run_id IS NOT NULL
  AND f.path IN $removed_paths
SET f.last_symbol_index_removed_in_run_id = $run_id,
    f.last_symbol_index_removed_at = datetime($observed_at),
    f.last_symbol_index_removed_in_commit = $commit_sha
REMOVE f.body_hash
"""

_READ_FILE_HASHES_CYPHER = """
MATCH (f:File {project_id: $project_id})
WHERE f.body_hash IS NOT NULL
RETURN f.path AS path, f.body_hash AS body_hash
"""

_READ_FILE_COMMITS_CYPHER = """
MATCH (f:File {project_id: $project_id})
WHERE f.last_seen_in_commit IS NOT NULL
RETURN collect(DISTINCT f.last_seen_in_commit) AS commits
"""

_GRAPH_BATCH_SIZE = 500
_INCREMENTAL_FULL_REPROCESS_THRESHOLD = 0.8
_GIT_CHANGESET_CAP = 500
_SWIFT_SYMBOL_BASELINE_KIND = "swift_symbol_scope"
_SWIFT_SYMBOL_BASELINE_STATE_VERSION = 1
_SWIFT_SOURCE_SUFFIXES = (".swift", ".swiftinterface")
_SWIFT_ACCESS_LOOKBACK_LINES = 2
_SWIFT_ACCESS_MODIFIER_RE = re.compile(
    r"\b(open|public|package|internal|fileprivate|private)\b"
)
_SWIFT_DECLARATION_RE = re.compile(
    r"\b(class|struct|enum|protocol|extension|func|var|let|typealias|actor|init|subscript)\b"
)


@dataclass(frozen=True)
class _GitChangeSet:
    changed: set[str]
    added: set[str]
    removed: set[str]
    truncated: bool


class SymbolIndexSwift(BaseExtractor):
    name: ClassVar[str] = "symbol_index_swift"
    incremental_capability: ClassVar[ExtractorIncrementalCapability] = (
        ExtractorIncrementalCapability.DELTA
    )
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
            scip_paths = _scip_source_paths(scip_index)

            def _iter_occurrences() -> Iterable[SymbolOccurrence]:
                return iter_scip_occurrences(
                    scip_index,
                    commit_sha=commit_sha,
                    ingest_run_id=ctx.run_id,
                )

            current_body_hashes = _build_file_body_hashes(ctx.repo_path, scip_paths)
            previous_body_hashes = await _read_existing_file_body_hashes(
                driver, project_id=ctx.group_id
            )
            current_body_hash_manifest_digest = _body_hash_manifest_digest(
                current_body_hashes
            )
            scip_document_count = _count_scip_documents(scip_index)
            scip_occurrence_count = _count_scip_occurrences(scip_index)
            logger.info(
                "symbol_index_swift.snapshot.loaded",
                extra={
                    "extractor": self.name,
                    "project": ctx.project_slug,
                    "run_id": ctx.run_id,
                    "snapshot_scope": "full_scip_parse_and_hash",
                    "scip_document_count": scip_document_count,
                    "scip_occurrence_count": scip_occurrence_count,
                    "body_hash_file_count": len(current_body_hashes),
                },
            )
            changed_files: set[str] = set()
            removed_files: set[str] = set()
            incremental_tantivy = False
            selected_graph_paths: set[str] | None = None
            removed_graph_paths: set[str] = set()
            graph_fallback_reason: str | None = None
            previous_commit_sha: str | None = None
            previous_commit_source: str | None = None
            if (
                not ctx.force
                and previous_body_hashes
                and previous_body_hashes == current_body_hashes
            ):
                fast_skip_reason = await _current_swift_baseline_fast_skip_reason(
                    driver,
                    project_id=ctx.group_id,
                    commit_sha=commit_sha,
                    body_hash_manifest_digest=current_body_hash_manifest_digest,
                )
                if fast_skip_reason is None:
                    logger.info(
                        "symbol_index_swift.freshness.skip",
                        extra={
                            "extractor": self.name,
                            "project": ctx.project_slug,
                            "run_id": ctx.run_id,
                            "freshness_decision": "skip",
                            "freshness_reason": "body_hash_match",
                            "baseline_state": "present",
                            "graph_refresh": "skipped",
                            "occurrence_iteration_count": 0,
                            "file_count": len(current_body_hashes),
                        },
                    )
                    await finalize_ingest_run(driver, run_id=ctx.run_id, success=True)
                    return ExtractorStats(
                        outcome=ExtractorOutcome.SKIPPED,
                        message=(
                            "Skipped re-ingest: file body_hash values and durable "
                            "Swift baseline matched current HEAD."
                        ),
                        next_action="Modify source content or run with force=True before rerunning symbol_index_swift.",
                        mode=ExtractorExecutionMode.SKIPPED,
                    )

                await _refresh_graph_state(
                    driver,
                    repo_path=ctx.repo_path,
                    scip_index=scip_index,
                    iter_occurrences=_iter_occurrences,
                    project_id=ctx.group_id,
                    run_id=ctx.run_id,
                    commit_sha=commit_sha,
                    file_body_hashes=current_body_hashes,
                    selected_paths=None,
                    removed_paths=set(),
                )
                await _write_swift_symbol_baseline(
                    driver,
                    project_id=ctx.group_id,
                    project_slug=ctx.project_slug,
                    run_id=ctx.run_id,
                    commit_sha=commit_sha,
                    scip_path=scip_path,
                    repo_path=ctx.repo_path,
                    scip_digest=_file_digest(scip_path),
                    scip_document_count=scip_document_count,
                    scip_occurrence_count=scip_occurrence_count,
                    current_body_hashes=current_body_hashes,
                )
                logger.info(
                    "symbol_index_swift.freshness.skip",
                    extra={
                        "extractor": self.name,
                        "project": ctx.project_slug,
                        "run_id": ctx.run_id,
                        "freshness_decision": "skip",
                        "freshness_reason": "body_hash_match",
                        "baseline_state": fast_skip_reason,
                        "graph_refresh": "full",
                        "file_count": len(current_body_hashes),
                    },
                )
                await finalize_ingest_run(driver, run_id=ctx.run_id, success=True)
                return ExtractorStats(
                    outcome=ExtractorOutcome.SKIPPED,
                    message="Skipped re-ingest: file body_hash values matched existing :File nodes.",
                    next_action="Modify source content before rerunning symbol_index_swift.",
                    mode=ExtractorExecutionMode.SKIPPED,
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
                            for path in sorted(current_body_hashes)
                            if previous_body_hashes.get(path)
                            != current_body_hashes[path]
                        ][:10],
                    },
                )
                changed_files, removed_files, changed_ratio = _diff_file_body_hashes(
                    previous_body_hashes=previous_body_hashes,
                    current_body_hashes=current_body_hashes,
                )
                incremental_tantivy = (
                    not ctx.force
                    and _incremental_ingest_enabled(settings)
                    and changed_ratio < _INCREMENTAL_FULL_REPROCESS_THRESHOLD
                )
                if incremental_tantivy:
                    (
                        previous_commit_sha,
                        graph_fallback_reason,
                    ) = await _read_swift_symbol_baseline_commit(
                        driver,
                        project_id=ctx.group_id,
                        extractor_name=self.name,
                    )
                    if previous_commit_sha is not None:
                        previous_commit_source = "extractor_baseline"
                    elif graph_fallback_reason == "baseline_missing":
                        previous_commit_sha = await _read_existing_commit_sha(
                            driver, project_id=ctx.group_id
                        )
                        if previous_commit_sha is not None:
                            previous_commit_source = "legacy_file_commits"
                            graph_fallback_reason = None
                    if previous_commit_sha is not None:
                        (
                            selected_graph_paths,
                            removed_graph_paths,
                            graph_fallback_reason,
                        ) = await _derive_incremental_graph_scope(
                            repo_path=ctx.repo_path,
                            previous_commit_sha=previous_commit_sha,
                            scip_paths=scip_paths,
                            changed_files=changed_files,
                            removed_files=removed_files,
                        )
                    incremental_tantivy = selected_graph_paths is not None
                logger.info(
                    "symbol_index_swift.tantivy.plan",
                    extra={
                        "extractor": self.name,
                        "project": ctx.project_slug,
                        "run_id": ctx.run_id,
                        "tantivy_mode": (
                            "incremental" if incremental_tantivy else "full_reprocess"
                        ),
                        "changed_file_count": len(changed_files),
                        "removed_file_count": len(removed_files),
                        "changed_file_ratio": changed_ratio,
                        "graph_mode": (
                            "incremental"
                            if selected_graph_paths is not None
                            else "full"
                        ),
                        "graph_fallback_reason": graph_fallback_reason,
                        "previous_commit_source": previous_commit_source,
                    },
                )
                if (
                    incremental_tantivy
                    and previous_commit_sha is not None
                    and selected_graph_paths is not None
                ):
                    baseline = await capture_delta_resolution_baseline(
                        driver,
                        group_id=ctx.group_id,
                        project=ctx.project_slug,
                        previous_commit_sha=previous_commit_sha,
                        changed_paths=selected_graph_paths,
                        removed_paths=removed_graph_paths,
                    )
                    write_delta_resolution_baseline_artifact(
                        repo_path=ctx.repo_path,
                        run_id=ctx.run_id,
                        baseline=baseline,
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
                selected_paths = selected_graph_paths if incremental_tantivy else None
                if incremental_tantivy:
                    await bridge.delete_by_file_paths_async(
                        sorted((selected_paths or set()) | removed_graph_paths)
                    )
                check_phase_budget(
                    nodes_written_so_far=total_written,
                    max_occurrences_total=settings.palace_max_occurrences_total,
                    phase="phase1_defs",
                )
                p1 = await _ingest_batch(
                    bridge,
                    _iter_selected_occurrences(
                        occurrences=_iter_occurrences(),
                        selected_paths=selected_paths,
                        kinds=(SymbolKind.DEF, SymbolKind.DECL),
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
                            occurrences=_iter_selected_occurrences(
                                occurrences=_iter_occurrences(),
                                selected_paths=selected_paths,
                            ),
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
                        _iter_vendor_occurrences(
                            occurrences=_iter_selected_occurrences(
                                occurrences=_iter_occurrences(),
                                selected_paths=selected_paths,
                            ),
                            counter=counter,
                            settings=settings,
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
                repo_path=ctx.repo_path,
                scip_index=scip_index,
                iter_occurrences=_iter_occurrences,
                project_id=ctx.group_id,
                run_id=ctx.run_id,
                commit_sha=commit_sha,
                file_body_hashes=current_body_hashes,
                selected_paths=selected_graph_paths if incremental_tantivy else None,
                removed_paths=removed_graph_paths,
            )
            await _write_swift_symbol_baseline(
                driver,
                project_id=ctx.group_id,
                project_slug=ctx.project_slug,
                run_id=ctx.run_id,
                commit_sha=commit_sha,
                scip_path=scip_path,
                repo_path=ctx.repo_path,
                scip_digest=_file_digest(scip_path),
                scip_document_count=scip_document_count,
                scip_occurrence_count=scip_occurrence_count,
                current_body_hashes=current_body_hashes,
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
            return ExtractorStats(
                nodes_written=sym_nodes,
                edges_written=0,
                mode=(
                    ExtractorExecutionMode.INCREMENTAL
                    if incremental_tantivy
                    else ExtractorExecutionMode.FULL
                ),
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


async def _read_swift_symbol_baseline_commit(
    driver: AsyncDriver,
    *,
    project_id: str,
    extractor_name: str,
) -> tuple[str | None, str | None]:
    baseline = await load_extractor_baseline(
        driver,
        project_id=project_id,
        extractor=extractor_name,
        baseline_kind=_SWIFT_SYMBOL_BASELINE_KIND,
    )
    if baseline is None:
        return None, "baseline_missing"
    if baseline.status != BASELINE_STATUS_VALID:
        return None, baseline.invalid_reason or "baseline_invalid"
    if baseline.state_version != _SWIFT_SYMBOL_BASELINE_STATE_VERSION:
        return None, "baseline_schema_mismatch"
    if not baseline.commit_sha:
        return None, "baseline_commit_missing"
    return baseline.commit_sha, None


async def _current_swift_baseline_fast_skip_reason(
    driver: AsyncDriver,
    *,
    project_id: str,
    commit_sha: str,
    body_hash_manifest_digest: str,
) -> str | None:
    baseline = await load_extractor_baseline(
        driver,
        project_id=project_id,
        extractor=SymbolIndexSwift.name,
        baseline_kind=_SWIFT_SYMBOL_BASELINE_KIND,
    )
    if baseline is None:
        return "missing"
    if baseline.status != BASELINE_STATUS_VALID:
        return "invalid"
    if baseline.state_version != _SWIFT_SYMBOL_BASELINE_STATE_VERSION:
        return "invalid"
    if baseline.commit_sha != commit_sha:
        return "stale_commit"
    if baseline.body_hash_manifest_digest != body_hash_manifest_digest:
        return "stale_body_hash_manifest"
    return None


async def _write_swift_symbol_baseline(
    driver: AsyncDriver,
    *,
    project_id: str,
    project_slug: str,
    run_id: str,
    commit_sha: str,
    scip_path: Path,
    repo_path: Path,
    scip_digest: str | None,
    scip_document_count: int,
    scip_occurrence_count: int,
    current_body_hashes: dict[str, str],
) -> None:
    await upsert_extractor_baseline(
        driver,
        baseline=build_valid_extractor_baseline(
            project_id=project_id,
            project_slug=project_slug,
            extractor=SymbolIndexSwift.name,
            baseline_kind=_SWIFT_SYMBOL_BASELINE_KIND,
            state_version=_SWIFT_SYMBOL_BASELINE_STATE_VERSION,
            commit_sha=commit_sha,
            run_id=run_id,
            indexed_commit=commit_sha,
            scip_digest=scip_digest,
            scip_path=_display_path(repo_path=repo_path, path=scip_path),
            scip_document_count=scip_document_count,
            scip_occurrence_count=scip_occurrence_count,
            body_hash_manifest_digest=_body_hash_manifest_digest(current_body_hashes),
            file_count=len(current_body_hashes),
        ),
    )


def _body_hash_manifest_digest(file_body_hashes: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for file_path, body_hash in sorted(file_body_hashes.items()):
        digest.update(file_path.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        digest.update(body_hash.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _file_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _display_path(*, repo_path: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_path.resolve()).as_posix()
    except ValueError:
        return str(path)


def _count_scip_documents(scip_index: object) -> int:
    documents = getattr(scip_index, "documents", ())
    return len(documents)


def _count_scip_occurrences(scip_index: object) -> int:
    documents = getattr(scip_index, "documents", ())
    return sum(len(getattr(doc, "occurrences", ()) or ()) for doc in documents)


def _incremental_ingest_enabled(settings: object) -> bool:
    value = getattr(settings, "palace_incremental_ingest", False)
    return value if isinstance(value, bool) else False


def _diff_file_body_hashes(
    *,
    previous_body_hashes: dict[str, str],
    current_body_hashes: dict[str, str],
) -> tuple[set[str], set[str], float]:
    current_paths = set(current_body_hashes)
    previous_paths = set(previous_body_hashes)
    changed_files = {
        path
        for path in current_paths
        if previous_body_hashes.get(path) != current_body_hashes[path]
    }
    removed_files = previous_paths - current_paths
    total_paths = len(previous_paths | current_paths)
    changed_ratio = (
        len(changed_files | removed_files) / total_paths if total_paths else 0.0
    )
    return changed_files, removed_files, changed_ratio


def _is_swift_source_path(file_path: str) -> bool:
    return file_path.endswith(_SWIFT_SOURCE_SUFFIXES)


def _scip_source_paths(scip_index: object) -> set[str]:
    documents = getattr(scip_index, "documents", ())
    return {
        str(doc.relative_path)
        for doc in documents
        if getattr(doc, "relative_path", None)
        and _is_swift_source_path(str(doc.relative_path))
    }


def _build_file_body_hashes(
    repo_path: Path, paths_or_occurrences: Iterable[str] | Iterable[SymbolOccurrence]
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    missing = 0
    file_paths: set[str] = set()
    for item in paths_or_occurrences:
        if isinstance(item, SymbolOccurrence):
            file_paths.add(item.file_path)
        elif hasattr(item, "file_path"):
            file_paths.add(str(getattr(item, "file_path")))
        else:
            file_paths.add(str(item))
    for file_path in sorted(file_paths):
        try:
            hashes[file_path] = hashlib.sha256(
                (repo_path / file_path).read_bytes()
            ).hexdigest()
        except (FileNotFoundError, OSError):
            # The SCIP may reference files that no longer exist on disk (e.g. cleaned
            # DerivedData build-intermediates of a stale SCIP). body_hash is freshness
            # metadata only; skip the unreadable file so symbol ingestion still runs.
            missing += 1
    if missing:
        logger.warning(
            "symbol_index_body_hash_missing_files",
            extra={"missing_files": missing, "hashed_files": len(hashes)},
        )
    return hashes


async def _read_git_change_set(repo_path: Path, base_commit: str) -> _GitChangeSet:
    result = await asyncio.to_thread(
        run_git,
        [
            "diff",
            "--name-status",
            "--no-renames",
            base_commit,
            "HEAD",
            "--",
        ],
        repo_path=repo_path,
        max_stdout_lines=_GIT_CHANGESET_CAP,
    )
    if result.rc != 0:
        raise GitError(result.rc, result.stderr[:200] or "git diff failed")

    changed: set[str] = set()
    added: set[str] = set()
    removed: set[str] = set()
    for line in result.stdout.splitlines():
        if not line:
            continue
        status, _, raw_path = line.partition("\t")
        if not status or not raw_path:
            continue
        path = Path(raw_path).as_posix()
        code = status[0]
        if code == "D":
            removed.add(path)
            continue
        if code == "A":
            added.add(path)
            continue
        if code in {"M", "T", "U", "C"}:
            changed.add(path)

    return _GitChangeSet(
        changed=changed,
        added=added,
        removed=removed,
        truncated=result.truncated,
    )


async def _derive_incremental_graph_scope(
    *,
    repo_path: Path,
    previous_commit_sha: str | None,
    scip_paths: set[str],
    changed_files: set[str],
    removed_files: set[str],
) -> tuple[set[str] | None, set[str], str | None]:
    if not previous_commit_sha:
        return None, set(), "previous_commit_missing"
    try:
        git_changes = await _read_git_change_set(repo_path, previous_commit_sha)
    except (GitError, GitTimeout):
        return None, set(), "git_diff_error"

    if git_changes.truncated:
        return None, set(), "git_diff_truncated"

    git_changed = {
        path
        for path in git_changes.changed | git_changes.added
        if _is_swift_source_path(path)
    }
    git_removed = {path for path in git_changes.removed if _is_swift_source_path(path)}
    selected_paths = git_changed & scip_paths
    if git_changed - scip_paths:
        return None, set(), "scip_path_mismatch"

    scoped_body_changes = {
        path for path in changed_files if _is_swift_source_path(path)
    }
    scoped_body_removals = {
        path for path in removed_files if _is_swift_source_path(path)
    }
    if scoped_body_changes != selected_paths:
        return None, set(), "body_hash_changed_mismatch"
    if scoped_body_removals != git_removed:
        return None, set(), "body_hash_removed_mismatch"
    return selected_paths, git_removed, None


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


async def _read_existing_commit_sha(
    driver: AsyncDriver, *, project_id: str
) -> str | None:
    async with driver.session() as session:
        result = await session.run(_READ_FILE_COMMITS_CYPHER, project_id=project_id)
        row = await result.single()
    if not row:
        return None
    commits = [str(commit) for commit in row.get("commits") or [] if commit]
    if len(commits) != 1:
        return None
    return commits[0]


async def _write_file_body_hashes(
    driver: AsyncDriver,
    *,
    project_id: str,
    run_id: str,
    file_body_hashes: dict[str, str],
    observed_at: datetime,
    commit_sha: str,
    prune_absent_paths: bool,
    removed_paths: set[str],
) -> int:
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
        if prune_absent_paths:
            result = await session.run(
                _CLEAR_ABSENT_FILE_HASHES_CYPHER,
                project_id=project_id,
                run_id=run_id,
                observed_at=observed_at_str,
                commit_sha=commit_sha,
                current_paths=sorted(file_body_hashes),
            )
            await result.consume()
        elif removed_paths:
            result = await session.run(
                _CLEAR_REMOVED_FILE_HASHES_CYPHER,
                project_id=project_id,
                run_id=run_id,
                observed_at=observed_at_str,
                commit_sha=commit_sha,
                removed_paths=sorted(removed_paths),
            )
            await result.consume()
    return len(rows)


async def _refresh_graph_state(
    driver: AsyncDriver,
    *,
    repo_path: Path,
    scip_index: object,
    iter_occurrences: Callable[[], Iterable[SymbolOccurrence]],
    project_id: str,
    run_id: str,
    commit_sha: str,
    file_body_hashes: dict[str, str],
    selected_paths: set[str] | None,
    removed_paths: set[str],
) -> tuple[int, int, int]:
    # Keep graph-layer freshness aligned even when Tantivy ingest is skipped.
    refresh_started_at = perf_counter()
    selected_file_paths = None if selected_paths is None else set(selected_paths)
    affected_paths = set(removed_paths)
    if selected_file_paths is not None:
        affected_paths |= selected_file_paths
    graph_mode = "full" if selected_file_paths is None else "incremental"
    logger.info(
        "symbol_index_swift.graph_refresh.start",
        extra={
            "project_id": project_id,
            "run_id": run_id,
            "graph_mode": graph_mode,
            "selected_file_count": (
                None if selected_file_paths is None else len(selected_file_paths)
            ),
            "removed_file_count": len(removed_paths),
        },
    )

    def _iter_graph_occurrences() -> Iterable[SymbolOccurrence]:
        if selected_file_paths is None:
            return iter_occurrences()
        return _iter_selected_occurrences(
            occurrences=iter_occurrences(),
            selected_paths=selected_file_paths,
        )

    def_file_paths: dict[str, str] = {}
    def_line_starts: dict[str, int] = {}
    def_symbol_ids: dict[str, int] = {}
    phase_started_at = perf_counter()
    for occ in _iter_graph_occurrences():
        if occ.kind in (SymbolKind.DEF, SymbolKind.DECL):
            def_file_paths.setdefault(occ.symbol_qualified_name, occ.file_path)
            def_symbol_ids.setdefault(occ.symbol_qualified_name, occ.symbol_id)
            # SCIP ranges are 0-based; snippet windows / get_code_snippet are
            # 1-based. Record the declaration line so the snippet windows on the
            # symbol instead of falling back to the file head (dogfood W8c).
            def_line_starts.setdefault(occ.symbol_qualified_name, occ.line + 1)
    logger.info(
        "symbol_index_swift.graph_refresh.definitions",
        extra={
            "project_id": project_id,
            "run_id": run_id,
            "definition_count": len(def_file_paths),
            "duration_ms": int((perf_counter() - phase_started_at) * 1000),
        },
    )

    graph_seen_at = datetime.now(tz=timezone.utc)
    phase_started_at = perf_counter()
    symbol_infos = tuple(iter_scip_symbol_infos(scip_index))
    if selected_file_paths is not None:
        symbol_infos = tuple(
            sym_info
            for sym_info in symbol_infos
            if def_file_paths.get(sym_info.qualified_name) in selected_file_paths
        )
    symbol_infos = _with_access_modifiers(
        symbol_infos,
        repo_path=repo_path,
        def_file_paths=def_file_paths,
        def_line_starts=def_line_starts,
    )
    logger.info(
        "symbol_index_swift.graph_refresh.symbol_infos",
        extra={
            "project_id": project_id,
            "run_id": run_id,
            "symbol_info_count": len(symbol_infos),
            "duration_ms": int((perf_counter() - phase_started_at) * 1000),
        },
    )
    phase_started_at = perf_counter()
    shadow_rows = _build_shadow_rows(
        occurrences=_iter_graph_occurrences(),
        symbol_infos=symbol_infos,
        group_id=project_id,
        seen_at=graph_seen_at,
    )
    logger.info(
        "symbol_index_swift.graph_refresh.shadow_rows_built",
        extra={
            "project_id": project_id,
            "run_id": run_id,
            "shadow_row_count": len(shadow_rows),
            "duration_ms": int((perf_counter() - phase_started_at) * 1000),
        },
    )
    phase_started_at = perf_counter()
    shadow_count = await _write_shadow_rows(driver, shadow_rows)
    logger.info(
        "symbol_index_swift.graph_refresh.shadow_rows_written",
        extra={
            "project_id": project_id,
            "run_id": run_id,
            "shadow_row_count": shadow_count,
            "duration_ms": int((perf_counter() - phase_started_at) * 1000),
        },
    )

    phase_started_at = perf_counter()
    sym_nodes = 0
    seen_qnames: set[str] = set()
    sym_batch: list[ScipSymbolInfo] = []
    sym_batch_size = 5000
    for sym_info in symbol_infos:
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
                def_symbol_ids=def_symbol_ids,
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
            def_symbol_ids=def_symbol_ids,
        )
    logger.info(
        "symbol_index_swift.graph_refresh.symbol_nodes_written",
        extra={
            "project_id": project_id,
            "run_id": run_id,
            "symbol_node_count": sym_nodes,
            "duration_ms": int((perf_counter() - phase_started_at) * 1000),
        },
    )

    phase_started_at = perf_counter()
    deleted_count = 0
    if selected_file_paths is None and seen_qnames:
        deleted_count = await soft_delete_symbols(
            driver, project_id, seen_qnames, datetime.now(tz=timezone.utc)
        )
    elif affected_paths:
        deleted_count = await soft_delete_symbols_for_paths(
            driver,
            project_id,
            affected_paths,
            seen_qnames,
            datetime.now(tz=timezone.utc),
        )
        await bump_unchanged_symbol_liveness(
            driver,
            group_id=project_id,
            written_changed_qnames=seen_qnames,
            run_id=run_id,
        )
        await delete_stale_relationships(
            driver,
            group_id=project_id,
            changed_file_paths=affected_paths,
            run_id=run_id,
        )
    logger.info(
        "symbol_index_swift.graph_refresh.soft_delete",
        extra={
            "project_id": project_id,
            "run_id": run_id,
            "deleted_count": deleted_count,
            "duration_ms": int((perf_counter() - phase_started_at) * 1000),
        },
    )

    phase_started_at = perf_counter()
    await _write_file_body_hashes(
        driver,
        project_id=project_id,
        run_id=run_id,
        file_body_hashes=file_body_hashes,
        observed_at=graph_seen_at,
        commit_sha=commit_sha,
        prune_absent_paths=selected_file_paths is None,
        removed_paths=removed_paths,
    )
    logger.info(
        "symbol_index_swift.graph_refresh.file_hashes_written",
        extra={
            "project_id": project_id,
            "run_id": run_id,
            "file_count": len(file_body_hashes),
            "duration_ms": int((perf_counter() - phase_started_at) * 1000),
        },
    )
    logger.info(
        "symbol_index_swift.graph_refresh.done",
        extra={
            "project_id": project_id,
            "run_id": run_id,
            "symbol_node_count": sym_nodes,
            "shadow_row_count": shadow_count,
            "deleted_count": deleted_count,
            "duration_ms": int((perf_counter() - refresh_started_at) * 1000),
        },
    )
    return sym_nodes, shadow_count, deleted_count


def _with_access_modifiers(
    symbol_infos: tuple[ScipSymbolInfo, ...],
    *,
    repo_path: Path,
    def_file_paths: dict[str, str],
    def_line_starts: dict[str, int],
) -> tuple[ScipSymbolInfo, ...]:
    file_lines_cache: dict[str, tuple[str, ...] | None] = {}
    return tuple(
        replace(
            sym_info,
            access_modifier=_infer_swift_access_modifier(
                repo_path=repo_path,
                file_path=def_file_paths.get(sym_info.qualified_name),
                line_start=def_line_starts.get(sym_info.qualified_name),
                file_lines_cache=file_lines_cache,
            ),
        )
        for sym_info in symbol_infos
    )


def _infer_swift_access_modifier(
    *,
    repo_path: Path,
    file_path: str | None,
    line_start: int | None,
    file_lines_cache: dict[str, tuple[str, ...] | None],
) -> str:
    if file_path is None or line_start is None or line_start < 1:
        return ""

    lines = _load_repo_relative_lines(
        repo_path=repo_path,
        file_path=file_path,
        file_lines_cache=file_lines_cache,
    )
    if lines is None or line_start > len(lines):
        return ""

    declaration_line = lines[line_start - 1].split("//", 1)[0].strip()
    if not declaration_line:
        return ""

    declaration_match = _SWIFT_DECLARATION_RE.search(declaration_line)
    if declaration_match is None:
        return ""

    declaration_prefix_parts = [declaration_line[: declaration_match.start()]]
    window_start = max(0, line_start - 1 - _SWIFT_ACCESS_LOOKBACK_LINES)
    for raw_line in reversed(lines[window_start : line_start - 1]):
        prefix_line = raw_line.split("//", 1)[0].strip()
        if not prefix_line:
            break
        if _SWIFT_DECLARATION_RE.search(prefix_line):
            break
        if not prefix_line.startswith("@") and (
            _SWIFT_ACCESS_MODIFIER_RE.search(prefix_line) is None
        ):
            break
        declaration_prefix_parts.insert(0, prefix_line)

    declaration_prefix = " ".join(part for part in declaration_prefix_parts if part)
    match = _SWIFT_ACCESS_MODIFIER_RE.search(declaration_prefix)
    if match is not None:
        return str(match.group(1))
    return "internal"


def _load_repo_relative_lines(
    *,
    repo_path: Path,
    file_path: str,
    file_lines_cache: dict[str, tuple[str, ...] | None],
) -> tuple[str, ...] | None:
    cached = file_lines_cache.get(file_path)
    if cached is not None or file_path in file_lines_cache:
        return cached

    try:
        lines = (repo_path / file_path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        file_lines_cache[file_path] = None
        return None

    file_lines_cache[file_path] = tuple(lines)
    return file_lines_cache[file_path]


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
            result = await session.run(
                _MERGE_SYMBOL_OCCURRENCE_SHADOWS,
                rows=rows[i : i + _GRAPH_BATCH_SIZE],
            )
            await result.consume()
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


def _iter_selected_occurrences(
    *,
    occurrences: Iterable[SymbolOccurrence],
    selected_paths: set[str] | None,
    kinds: tuple[SymbolKind, ...] | None = None,
) -> Iterable[SymbolOccurrence]:
    for occ in occurrences:
        if selected_paths is not None and occ.file_path not in selected_paths:
            continue
        if kinds is not None and occ.kind not in kinds:
            continue
        yield occ


def _iter_vendor_occurrences(
    *,
    occurrences: Iterable[SymbolOccurrence],
    counter: BoundedInDegreeCounter,
    settings: object,
) -> Iterable[SymbolOccurrence]:
    for occ in occurrences:
        if occ.kind != SymbolKind.USE or not _is_vendor(occ.file_path):
            continue
        yield _with_importance(occ, counter, settings)


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
