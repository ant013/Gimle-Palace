from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast

import pygit2

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorError,
    ExtractorExecutionMode,
    ExtractorOutcome,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.foundation.incremental_scope import (
    IncrementalMode,
    derive_incremental_path_scope,
)

if TYPE_CHECKING:
    from palace_mcp.audit.contracts import AuditContract
from palace_mcp.extractors.hotspot import (
    churn_query,
    file_walker,
    lizard_runner,
    neo4j_writer,
)
from palace_mcp.extractors.hotspot.models import ParsedFile

_PREREQ_QUERY = (
    "MATCH (r:IngestRun {project: $project, extractor_name: 'git_history'}) "
    "WHERE r.success = true RETURN count(r) AS n"
)

_FILE_COUNT_QUERY = "MATCH (f:File {project_id: $project_id}) RETURN count(f) AS n"


class _HotspotError(ExtractorError):
    """Hotspot-specific error with a runtime error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.error_code: str = code  # type: ignore[misc]


async def _count_git_history_runs(driver: Any, *, project: str) -> int:
    async with driver.session() as session:
        result = await session.run(_PREREQ_QUERY, project=project)
        row = await result.single()
    return int(row["n"]) if row is not None else 0


async def _count_db_files(driver: Any, *, project_id: str) -> int:
    async with driver.session() as session:
        result = await session.run(_FILE_COUNT_QUERY, project_id=project_id)
        row = await result.single()
    return int(row["n"]) if row is not None else 0


def _head_commit_as_of(
    repo_path: Any, *, fallback_as_of: datetime | None = None
) -> datetime:
    try:
        repo = pygit2.Repository(str(repo_path))
    except pygit2.GitError:
        if fallback_as_of is not None:
            return fallback_as_of
        raise
    commit = cast(Any, repo[repo.head.target])
    return datetime.fromtimestamp(commit.commit_time, tz=timezone.utc)


class HotspotExtractor(BaseExtractor):
    name: ClassVar[str] = "hotspot"
    description: ClassVar[str] = (
        "Roadmap #44 — Code Complexity × Churn Hotspot. "
        "Computes Tornhill log-log score per file and writes :Function nodes."
    )
    constraints: ClassVar[list[str]] = [
        "CREATE CONSTRAINT function_unique IF NOT EXISTS "
        "FOR (fn:Function) REQUIRE (fn.project_id, fn.path, fn.name, fn.start_line) IS UNIQUE",
    ]
    indexes: ClassVar[list[str]] = [
        "CREATE INDEX file_hotspot_score IF NOT EXISTS FOR (f:File) ON (f.hotspot_score)",
        "CREATE INDEX function_path IF NOT EXISTS FOR (fn:Function) ON (fn.project_id, fn.path)",
    ]

    async def run(self, *, graphiti: object, ctx: ExtractorRunContext) -> ExtractorStats:  # fmt: skip
        from palace_mcp.mcp_server import get_settings

        settings = get_settings()
        assert settings is not None, "Palace settings not initialised"
        driver = graphiti.driver  # type: ignore[attr-defined]
        run_started_at = datetime.now(tz=timezone.utc)
        as_of = _head_commit_as_of(ctx.repo_path, fallback_as_of=run_started_at)

        # Prerequisite: git_history must have run first (else all churn = 0 → all scores = 0)
        git_history_runs = await _count_git_history_runs(
            driver, project=ctx.project_slug
        )
        if git_history_runs == 0:
            raise _HotspotError(
                "prerequisite_missing",
                f"git_history must run before hotspot for project {ctx.project_slug!r}; "
                "run palace.ingest.run_extractor(name='git_history', project=...) first",
            )

        scope = await derive_incremental_path_scope(
            driver,
            repo_path=ctx.repo_path,
            project_id=ctx.group_id,
            settings=settings,
            force=ctx.force,
            path_filter=file_walker.is_supported_path,
        )
        refresh_only_incremental = scope.mode == IncrementalMode.SKIP
        is_incremental = (
            scope.mode == IncrementalMode.INCREMENTAL or refresh_only_incremental
        )
        if refresh_only_incremental:
            existing_file_complexities = (
                await neo4j_writer.fetch_active_file_complexities(
                    driver,
                    project_id=ctx.group_id,
                    excluded_paths=[],
                )
            )
            if not existing_file_complexities:
                return ExtractorStats(
                    outcome=ExtractorOutcome.SKIPPED,
                    message="Skipped hotspot: no changed hotspot-supported files.",
                    next_action=(
                        "Modify tracked source files or rerun with force=True before rerunning hotspot."
                    ),
                    mode=ExtractorExecutionMode.SKIPPED,
                )
            files: list[Any] = []
            deleted_paths: list[str] = []
        else:
            files = (
                [ctx.repo_path / path for path in sorted(scope.changed_paths)]
                if is_incremental
                else list(file_walker._walk(ctx.repo_path))
            )
            deleted_paths = sorted(scope.removed_paths) if is_incremental else []

        batch_size: int = settings.palace_hotspot_lizard_batch_size
        timeout_s: int = settings.palace_hotspot_lizard_timeout_s
        behavior: Literal["drop_batch", "fail_run"] = (
            settings.palace_hotspot_lizard_timeout_behavior
        )

        parsed_files: list[ParsedFile] = []
        skipped_paths: list[str] = []
        for i in range(0, len(files), batch_size):
            batch = files[i : i + batch_size]
            result = await lizard_runner.run_batch(
                batch,
                repo_root=ctx.repo_path,
                timeout_s=timeout_s,
                behavior=behavior,
            )
            parsed_files.extend(result.parsed)
            skipped_paths.extend(result.skipped_files)

        # Loud-fail invariants: detect 0-scan before silently writing zero scores
        scanned_files = len(files)
        parsed_functions = sum(len(pf.functions) for pf in parsed_files)
        if scanned_files == 0:
            if is_incremental:
                parsed_functions = 0
            else:
                db_files = await _count_db_files(driver, project_id=ctx.group_id)
                if db_files > 0:
                    raise _HotspotError(
                        "data_mismatch_zero_scan_with_files_present",
                        f"file_walker found 0 source files for project {ctx.project_slug!r} "
                        f"but {db_files} :File nodes exist in Neo4j — likely mount or stop-list mismatch",
                    )
                raise _HotspotError(
                    "empty_project",
                    f"file_walker found 0 source files and Neo4j has 0 :File nodes for project "
                    f"{ctx.project_slug!r} — repo may be empty or incorrectly mounted",
                )
        elif parsed_functions == 0:
            raise _HotspotError(
                "lizard_parser_zero_functions",
                f"lizard scanned {scanned_files} file(s) for project {ctx.project_slug!r} "
                "but extracted 0 functions — lizard may be broken or files have no parseable code",
            )

        nodes_w = 0
        edges_w = 0
        for pf in parsed_files:
            await neo4j_writer.write_file_and_functions(
                driver,
                project_id=ctx.group_id,
                parsed_file=pf,
                run_started_at=run_started_at,
            )
            nodes_w += 1 + len(pf.functions)
            edges_w += len(pf.functions)

        paths = [pf.path for pf in parsed_files]
        preserved_paths = sorted({*paths, *skipped_paths})
        if is_incremental:
            file_complexities = await neo4j_writer.fetch_active_file_complexities(
                driver,
                project_id=ctx.group_id,
                excluded_paths=deleted_paths,
            )
        else:
            file_complexities = {pf.path: pf.ccn_total for pf in parsed_files}
        churn_map = await churn_query.fetch_churn(
            driver,
            project_id=ctx.group_id,
            paths=sorted(file_complexities),
            window_days=settings.palace_hotspot_churn_window_days,
            as_of=as_of,
        )
        for path, ccn_total in file_complexities.items():
            churn = churn_map.get(path, 0)
            score = math.log(ccn_total + 1) * math.log(churn + 1)
            await neo4j_writer.write_hotspot_score(
                driver,
                project_id=ctx.group_id,
                path=path,
                churn=churn,
                score=score,
                window_days=settings.palace_hotspot_churn_window_days,
                run_started_at=run_started_at,
            )

        if is_incremental:
            await neo4j_writer.evict_stale_functions_for_paths(
                driver,
                project_id=ctx.group_id,
                paths=paths + deleted_paths,
                run_started_at=run_started_at,
            )
            await neo4j_writer.mark_deleted_files_zero(
                driver,
                project_id=ctx.group_id,
                paths=deleted_paths,
                run_started_at=run_started_at,
            )
        else:
            await neo4j_writer.evict_stale_functions(
                driver,
                project_id=ctx.group_id,
                preserved_paths=preserved_paths,
                run_started_at=run_started_at,
            )
            await neo4j_writer.mark_dead_files_zero(
                driver,
                project_id=ctx.group_id,
                preserved_paths=preserved_paths,
                run_started_at=run_started_at,
            )

        return ExtractorStats(
            nodes_written=nodes_w,
            edges_written=edges_w,
            mode=(
                ExtractorExecutionMode.INCREMENTAL
                if is_incremental
                else ExtractorExecutionMode.FULL
            ),
        )

    def audit_contract(self) -> "AuditContract":
        from palace_mcp.audit.contracts import AuditContract, Severity

        return AuditContract(
            extractor_name="hotspot",
            template_name="hotspot.md",
            query="""
MATCH (f:File {project_id: $project_id})
WHERE coalesce(f.hotspot_score, 0.0) > 0
  AND coalesce(f.complexity_status, 'stale') = 'fresh'
RETURN coalesce(f.file_path, f.path) AS path,
       f.ccn_total AS ccn_total,
       f.churn_count AS churn_count,
       f.hotspot_score AS hotspot_score,
       f.complexity_window_days AS window_days
ORDER BY f.hotspot_score DESC
LIMIT 100
""".strip(),
            severity_column="hotspot_score",
            severity_mapper=lambda v: (
                Severity.CRITICAL
                if v is not None and float(v) >= 5.0
                else Severity.HIGH
                if v is not None and float(v) >= 3.0
                else Severity.MEDIUM
                if v is not None and float(v) >= 1.5
                else Severity.LOW
                if v is not None and float(v) > 0
                else Severity.INFORMATIONAL
            ),
        )
