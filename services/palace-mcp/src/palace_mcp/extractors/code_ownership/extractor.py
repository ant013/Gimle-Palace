"""Code ownership extractor orchestrator (Roadmap #32).

5-phase pipeline per spec rev2 §4:
0. bootstrap (schema, checkpoint, mailmap, bots, head)
1. dirty-set computation (pygit2.Diff)
2. blame walk (DIRTY only)
3. churn aggregation (DIRTY only, reversed Cypher)
4. scoring + atomic-replace write (per batch)
5. checkpoint + IngestRun finalize
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

if TYPE_CHECKING:
    from palace_mcp.audit.contracts import AuditContract

import pygit2

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.code_ownership.blame_walker import walk_blame
from palace_mcp.extractors.code_ownership.checkpoint import (
    load_checkpoint,
    update_checkpoint,
)
from palace_mcp.extractors.code_ownership.churn_aggregator import aggregate_churn
from palace_mcp.extractors.code_ownership.mailmap import MailmapResolver
from palace_mcp.extractors.code_ownership.models import OwnershipRunSummary
from palace_mcp.extractors.code_ownership.neo4j_writer import write_batch
from palace_mcp.extractors.code_ownership.schema_extension import (
    ensure_ownership_schema,
)
from palace_mcp.extractors.code_ownership.scorer import score_file
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode

logger = logging.getLogger(__name__)


class CodeOwnershipExtractor(BaseExtractor):
    """Roadmap #32 extractor — file-level ownership graph."""

    name: ClassVar[str] = "code_ownership"
    description: ClassVar[str] = (
        "File-level ownership: blame_share + recency-weighted churn"
    )
    constraints: ClassVar[list[str]] = []
    indexes: ClassVar[list[str]] = []

    def audit_contract(self) -> "AuditContract":
        from palace_mcp.audit.contracts import AuditContract, Severity

        return AuditContract(
            extractor_name="code_ownership",
            template_name="code_ownership.md",
            query="""
MATCH (f:File {project_id: $project_id})
OPTIONAL MATCH (f)-[r:OWNED_BY {source: 'extractor.code_ownership'}]->(a:Author)
WITH f, r, a ORDER BY r.weight DESC
WITH f, collect({r: r, a: a})[0] AS top_pair, count(r) AS total_authors
RETURN f.path AS path,
       top_pair.a.email AS top_owner_email,
       top_pair.r.weight AS top_owner_weight,
       total_authors
ORDER BY top_owner_weight ASC
LIMIT 100
""".strip(),
            severity_column="top_owner_weight",
            # Low top_owner_weight → very diffuse ownership → higher severity
            severity_mapper=lambda v: (
                Severity.HIGH
                if v is None or float(v) < 0.1
                else Severity.MEDIUM
                if float(v) < 0.2
                else Severity.INFORMATIONAL
            ),
        )

    async def run(
        self, *, graphiti: object, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        from palace_mcp.mcp_server import get_settings

        settings = get_settings()
        assert settings is not None, "Palace settings not initialised"

        driver = graphiti.driver  # type: ignore[attr-defined]
        project_id = ctx.group_id
        repo_path = ctx.repo_path

        summary = await self._run(
            driver=driver,
            project_id=project_id,
            repo_path=repo_path,
            run_id=ctx.run_id,
            settings=settings,
        )
        await self._write_run_extras(driver, ctx.run_id, summary)
        return ExtractorStats(
            nodes_written=summary.dirty_files_count + summary.deleted_files_count + 1,
            edges_written=summary.edges_written,
        )

    async def _run(
        self,
        *,
        driver: object,
        project_id: str,
        repo_path: Path,
        run_id: str,
        settings: object,
    ) -> OwnershipRunSummary:
        alpha: float = settings.ownership_blame_weight  # type: ignore[attr-defined]
        await ensure_ownership_schema(driver)  # type: ignore[arg-type]
        checkpoint = await load_checkpoint(driver, project_id=project_id)  # type: ignore[arg-type]

        try:
            repo = pygit2.Repository(str(repo_path))
        except Exception as exc:
            raise ExtractorError(
                error_code=ExtractorErrorCode.OWNERSHIP_DIFF_FAILED,
                message=f"cannot open repo at {repo_path}: {type(exc).__name__}",
                recoverable=False,
                action="retry",
            ) from exc

        try:
            head_oid = repo.head.target
            current_head = str(head_oid)
        except Exception as exc:
            raise ExtractorError(
                error_code=ExtractorErrorCode.REPO_HEAD_INVALID,
                message=f"cannot resolve HEAD: {type(exc).__name__}",
                recoverable=False,
                action="retry",
            ) from exc

        mailmap = MailmapResolver.from_repo(
            repo,
            max_bytes=settings.mailmap_max_bytes,  # type: ignore[attr-defined]
        )

        bot_keys = await self._fetch_bot_identity_keys(driver, project_id)
        known_author_ids = await self._fetch_known_author_ids(driver, project_id)

        has_commits = await self._has_any_commits(driver, project_id)
        if not has_commits:
            raise ExtractorError(
                error_code=ExtractorErrorCode.GIT_HISTORY_NOT_INDEXED,
                message=f"no :Commit nodes for project {project_id!r}",
                recoverable=False,
                action="manual_cleanup",
            )

        # Phase 1 — DIRTY/DELETED computation
        dirty: set[str]
        deleted: set[str] = set()
        prev_head_sha = checkpoint.last_head_sha if checkpoint else None
        if prev_head_sha is None:
            dirty = await asyncio.to_thread(self._all_files_in_head, repo)
        elif prev_head_sha == current_head:
            await update_checkpoint(
                driver,  # type: ignore[arg-type]
                project_id=project_id,
                head_sha=current_head,
                run_id=run_id,
            )
            return OwnershipRunSummary(
                project_id=project_id,
                run_id=run_id,
                head_sha=current_head,
                prev_head_sha=prev_head_sha,
                dirty_files_count=0,
                deleted_files_count=0,
                edges_written=0,
                edges_deleted=0,
                mailmap_resolver_path=mailmap.path.value,
                exit_reason="no_change",
                duration_ms=0,
                alpha_used=alpha,
            )
        else:
            try:
                prev_commit = repo.get(prev_head_sha)
                curr_commit = repo.get(current_head)
                diff = prev_commit.tree.diff_to_tree(curr_commit.tree)  # type: ignore[union-attr]
            except Exception as exc:
                raise ExtractorError(
                    error_code=ExtractorErrorCode.OWNERSHIP_DIFF_FAILED,
                    message=f"diff {prev_head_sha[:8]}..{current_head[:8]} raised {type(exc).__name__}",
                    recoverable=False,
                    action="retry",
                ) from exc
            dirty = set()
            for delta in diff.deltas:
                status = delta.status_char()
                if status in ("A", "M", "R") and delta.new_file.path:
                    dirty.add(delta.new_file.path)
                if status == "R" and delta.old_file.path:
                    deleted.add(delta.old_file.path)
                if status == "D" and delta.old_file.path:
                    deleted.add(delta.old_file.path)

        max_files: int = settings.ownership_max_files_per_run  # type: ignore[attr-defined]
        if len(dirty) > max_files:
            raise ExtractorError(
                error_code=ExtractorErrorCode.OWNERSHIP_MAX_FILES_EXCEEDED,
                message=f"DIRTY={len(dirty)} > cap {max_files}",
                recoverable=False,
                action="raise_budget",
            )

        if not dirty and not deleted:
            await update_checkpoint(
                driver,  # type: ignore[arg-type]
                project_id=project_id,
                head_sha=current_head,
                run_id=run_id,
            )
            return OwnershipRunSummary(
                project_id=project_id,
                run_id=run_id,
                head_sha=current_head,
                prev_head_sha=prev_head_sha,
                dirty_files_count=0,
                deleted_files_count=0,
                edges_written=0,
                edges_deleted=0,
                mailmap_resolver_path=mailmap.path.value,
                exit_reason="no_dirty",
                duration_ms=0,
                alpha_used=alpha,
            )

        # Phase 2 — blame walk (CPU-bound pygit2 calls; offloaded to thread)
        blame_per_file, binary_paths = await asyncio.to_thread(
            walk_blame, repo, paths=dirty, mailmap=mailmap, bot_keys=bot_keys
        )

        # Phase 3 — churn aggregation
        churn_per_file = await aggregate_churn(
            driver,  # type: ignore[arg-type]
            project_id=project_id,
            paths=dirty,
            mailmap=mailmap,
            bot_keys=bot_keys,
            decay_days=float(settings.palace_recency_decay_days),  # type: ignore[attr-defined]
            known_author_ids=known_author_ids,
        )

        # Phase 4 — scoring + atomic-replace per batch
        batch_size: int = settings.ownership_write_batch_size  # type: ignore[attr-defined]

        edges_all: list[Any] = []
        states_all: list[dict[str, str | None]] = []
        for path in dirty:
            if path in binary_paths:
                states_all.append(
                    {
                        "path": path,
                        "status": "skipped",
                        "no_owners_reason": "binary_or_skipped",
                    }
                )
                continue
            blame = blame_per_file.get(path, {})
            churn = churn_per_file.get(path, {})
            edges = score_file(
                project_id=project_id,
                path=path,
                blame=blame,
                churn=churn,
                alpha=alpha,
                known_author_ids=known_author_ids,
            )
            if not edges:
                if not blame and not churn:
                    reason = "binary_or_skipped"
                elif blame and not churn:
                    reason = "no_commit_history"
                else:
                    reason = "all_bot_authors"
                states_all.append(
                    {"path": path, "status": "skipped", "no_owners_reason": reason}
                )
                continue
            edges_all.extend(edges)
            states_all.append(
                {"path": path, "status": "processed", "no_owners_reason": None}
            )

        edges_written = 0
        # sorted: deterministic batch order regardless of PYTHONHASHSEED
        paths_in_dirty = sorted(dirty)
        for i in range(0, max(len(paths_in_dirty), 1), batch_size):
            batch_paths = set(paths_in_dirty[i : i + batch_size])
            batch_edges = [e for e in edges_all if e.path in batch_paths]
            batch_states = [s for s in states_all if s["path"] in batch_paths]
            if not batch_paths:
                continue
            await write_batch(
                driver,  # type: ignore[arg-type]
                project_id=project_id,
                edges=batch_edges,
                file_states=batch_states,
                deleted_paths=[],
                run_id=run_id,
                alpha=alpha,
            )
            edges_written += len(batch_edges)

        deleted_list = sorted(deleted)
        for i in range(0, max(len(deleted_list), 1), batch_size):
            batch = deleted_list[i : i + batch_size]
            if not batch:
                continue
            await write_batch(
                driver,  # type: ignore[arg-type]
                project_id=project_id,
                edges=[],
                file_states=[],
                deleted_paths=batch,
                run_id=run_id,
                alpha=alpha,
            )

        await update_checkpoint(
            driver,  # type: ignore[arg-type]
            project_id=project_id,
            head_sha=current_head,
            run_id=run_id,
        )

        return OwnershipRunSummary(
            project_id=project_id,
            run_id=run_id,
            head_sha=current_head,
            prev_head_sha=prev_head_sha,
            dirty_files_count=len(dirty),
            deleted_files_count=len(deleted),
            edges_written=edges_written,
            edges_deleted=0,
            mailmap_resolver_path=mailmap.path.value,
            exit_reason="success",
            duration_ms=0,
            alpha_used=alpha,
        )

    @staticmethod
    def _all_files_in_head(repo: pygit2.Repository) -> set[str]:
        head_tree = repo.head.peel().tree
        out: set[str] = set()

        def visit(tree: pygit2.Tree, prefix: str = "") -> None:
            for entry in tree:
                full = (
                    f"{prefix}{entry.name}" if not prefix else f"{prefix}/{entry.name}"
                )
                if entry.type_str == "tree":
                    visit(cast(pygit2.Tree, repo[entry.id]), full)
                else:
                    out.add(full)

        visit(head_tree)
        return out

    @staticmethod
    async def _fetch_bot_identity_keys(driver: object, project_id: str) -> set[str]:
        async with driver.session() as session:  # type: ignore[attr-defined]
            result = await session.run(
                """
                MATCH (c:Commit {project_id: $proj})-[:AUTHORED_BY]->(a:Author)
                WHERE a.is_bot = true
                RETURN DISTINCT a.identity_key AS k
                LIMIT 10000
                """,
                proj=project_id,
            )
            return {row["k"] for row in await result.data()}

    @staticmethod
    async def _fetch_known_author_ids(driver: object, project_id: str) -> set[str]:
        async with driver.session() as session:  # type: ignore[attr-defined]
            result = await session.run(
                """
                MATCH (c:Commit {project_id: $proj})-[:AUTHORED_BY]->(a:Author)
                RETURN DISTINCT a.identity_key AS k
                """,
                proj=project_id,
            )
            return {row["k"] for row in await result.data()}

    @staticmethod
    async def _has_any_commits(driver: object, project_id: str) -> bool:
        async with driver.session() as session:  # type: ignore[attr-defined]
            result = await session.run(
                "MATCH (c:Commit {project_id: $proj}) RETURN count(c) AS n",
                proj=project_id,
            )
            row = await result.single()
        return row is not None and row["n"] > 0

    async def _write_run_extras(
        self, driver: object, run_id: str, summary: OwnershipRunSummary
    ) -> None:
        async with driver.session() as session:  # type: ignore[attr-defined]
            await session.run(
                """
                MATCH (r:IngestRun {id: $run_id})
                SET r.head_sha = $head_sha,
                    r.prev_head_sha = $prev_head_sha,
                    r.dirty_files_count = $dirty,
                    r.deleted_files_count = $deleted,
                    r.edges_written = $edges_written,
                    r.mailmap_resolver_path = $mailmap_path,
                    r.exit_reason = $exit_reason,
                    r.alpha_used = $alpha
                """,
                run_id=run_id,
                head_sha=summary.head_sha,
                prev_head_sha=summary.prev_head_sha,
                dirty=summary.dirty_files_count,
                deleted=summary.deleted_files_count,
                edges_written=summary.edges_written,
                mailmap_path=summary.mailmap_resolver_path,
                exit_reason=summary.exit_reason,
                alpha=summary.alpha_used,
            )
