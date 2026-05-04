"""SymbolIndexClang — C/C++ extractor for pre-generated scip-clang indexes."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from graphiti_core import Graphiti
from neo4j import AsyncDriver

from palace_mcp.extractors.base import (
    BaseExtractor,
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
)
from palace_mcp.extractors.foundation.models import (
    Language,
    SymbolKind,
    SymbolOccurrence,
    build_symbol_occurrence_doc_key,
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

_VENDOR_MARKERS: tuple[str, ...] = (
    "Pods/",
    "Carthage/",
    "SourcePackages/",
    "third_party/",
    "Vendor/",
)
_SYSTEM_PREFIXES: tuple[str, ...] = (
    "/Applications/Xcode.app/",
    "/Library/Developer/",
    "/Library/Developer/CommandLineTools/",
)


class SymbolIndexClang(BaseExtractor):
    name: ClassVar[str] = "symbol_index_clang"
    description: ClassVar[str] = (
        "Ingest C/C++ symbols + occurrences from pre-generated scip-clang "
        "indexes into Tantivy and Neo4j. Filters system SDK paths, keeps "
        "repo app defs/uses, and routes in-repo vendor uses to phase 3."
    )
    primary_lang: ClassVar[Language] = Language.CPP

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
            all_occs = [
                normalized
                for occ in iter_scip_occurrences(
                    scip_index,
                    commit_sha=commit_sha,
                    ingest_run_id=ctx.run_id,
                )
                if (normalized := _normalize_occurrence(occ, ctx.repo_path)) is not None
            ]

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
                        if o.kind == SymbolKind.USE and not _is_vendor_path(o.file_path)
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
                        if o.kind == SymbolKind.USE and _is_vendor_path(o.file_path)
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

            counter_path = tantivy_path / "in_degree_counter.json"
            counter.to_disk(counter_path, run_id=ctx.run_id)

            await finalize_ingest_run(driver, run_id=ctx.run_id, success=True)
            return ExtractorStats(nodes_written=total_written, edges_written=0)

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
    bridge: TantivyBridge, occurrences: list[SymbolOccurrence], phase: str
) -> int:
    written = 0
    for occ in occurrences:
        await bridge.add_or_replace_async(occ, phase)
        written += 1
    return written


def _load_or_reset_counter(tantivy_path: Path, run_id: str) -> BoundedInDegreeCounter:
    counter = BoundedInDegreeCounter()
    counter_path = tantivy_path / "in_degree_counter.json"
    if not counter_path.exists():
        return counter
    if not counter.from_disk(counter_path, expected_run_id=run_id):
        if os.environ.get("PALACE_COUNTER_RESET") != "1":
            raise ExtractorError(
                error_code=ExtractorErrorCode.COUNTER_STATE_CORRUPT,
                message=(
                    f"Counter state corrupt or run_id mismatch at {counter_path}. "
                    "Set PALACE_COUNTER_RESET=1 to reset, or rebuild the index."
                ),
                recoverable=False,
                action="manual_cleanup",
            )
        return BoundedInDegreeCounter()
    return counter


def _normalize_occurrence(
    occ: SymbolOccurrence,
    repo_path: Path,
) -> SymbolOccurrence | None:
    normalized_path = _normalize_repo_relative_path(occ.file_path, repo_path)
    if normalized_path is None:
        return None
    if _is_vendor_path(normalized_path) and occ.kind in (
        SymbolKind.DEF,
        SymbolKind.DECL,
    ):
        return None
    if normalized_path == occ.file_path:
        return occ
    return SymbolOccurrence(
        doc_key=build_symbol_occurrence_doc_key(
            symbol_id=occ.symbol_id,
            file_path=normalized_path,
            line=occ.line,
            col_start=occ.col_start,
            commit_sha=occ.commit_sha,
        ),
        symbol_id=occ.symbol_id,
        symbol_qualified_name=occ.symbol_qualified_name,
        kind=occ.kind,
        language=occ.language,
        file_path=normalized_path,
        line=occ.line,
        col_start=occ.col_start,
        col_end=occ.col_end,
        importance=occ.importance,
        commit_sha=occ.commit_sha,
        ingest_run_id=occ.ingest_run_id,
        schema_version=occ.schema_version,
        synthesized_by=occ.synthesized_by,
    )


def _normalize_repo_relative_path(file_path: str, repo_path: Path) -> str | None:
    normalized = file_path.replace("\\", "/").removeprefix("./")
    if normalized.startswith(_SYSTEM_PREFIXES):
        return None

    candidate = Path(normalized)
    if not candidate.is_absolute():
        return normalized

    try:
        resolved_repo = repo_path.resolve(strict=False)
        resolved_file = candidate.resolve(strict=False)
        relative = resolved_file.relative_to(resolved_repo)
    except ValueError:
        return None
    return relative.as_posix()


def _is_vendor_path(file_path: str) -> bool:
    return any(marker in file_path for marker in _VENDOR_MARKERS)


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
        primary_lang=Language.CPP,
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
    MATCH (r:IngestRun {project: $project, extractor_name: 'symbol_index_clang'})
    WHERE r.success = false
    RETURN r.error_code AS error_code
    ORDER BY r.started_at DESC
    LIMIT 1
    """
    async with driver.session() as session:
        result = await session.run(query, project=project)
        record = await result.single()
        return None if record is None else record["error_code"]
