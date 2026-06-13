"""GitHistoryExtractor — see spec §5.1. Mirrors symbol_index_python pattern."""

from __future__ import annotations

import logging
import re
import subprocess
from typing import ClassVar

from datetime import datetime
from pathlib import Path

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorOutcome,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.circuit_breaker import (
    check_resume_budget,
    check_phase_budget,
)
from palace_mcp.extractors.foundation.schema import ensure_custom_schema
from palace_mcp.extractors.foundation.checkpoint import (
    create_ingest_run,
    finalize_ingest_run,
)
from palace_mcp.extractors.git_history.bot_detector import is_bot
from palace_mcp.extractors.git_history.checkpoint import (
    load_git_history_checkpoint,
    write_git_history_checkpoint,
)
from palace_mcp.extractors.git_history.neo4j_writer import write_commit_with_author
from palace_mcp.extractors.git_history.pygit2_walker import (
    Pygit2Walker,
    CommitNotFoundError,
)
from palace_mcp.extractors.git_history.tantivy_writer import (
    GitHistoryTantivyWriter,
    project_index_path,
)

log = logging.getLogger("watchdog.daemon")

_GITHUB_HTTPS_RE = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)
_GITHUB_SSH_RE = re.compile(
    r"^(?:git@github\.com:|ssh://git@github\.com/)(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)


async def _get_previous_error_code(driver: object, project: str) -> str | None:
    """Per-extractor circuit-breaker query (mirrors symbol_index_python.py:346)."""
    _QUERY = """
    MATCH (r:IngestRun {project: $project, extractor_name: 'git_history'})
    WHERE r.success = false
    RETURN r.error_code AS error_code
    ORDER BY r.started_at DESC
    LIMIT 1
    """
    from neo4j import AsyncDriver

    d: AsyncDriver = driver  # type: ignore[assignment]
    async with d.session() as session:
        result = await session.run(_QUERY, project=project)
        record = await result.single()
        return record["error_code"] if record else None


def _resolve_github_repo(repo_path: Path) -> tuple[str, str] | None:
    """Resolve GitHub owner/repo from origin remote.

    Project slugs are intentionally short identifiers like ``stable-wallet-ios``;
    they are not GitHub coordinates. Phase 2 must use the repository remote.
    """
    try:
        remote_url = subprocess.check_output(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    for pattern in (_GITHUB_HTTPS_RE, _GITHUB_SSH_RE):
        match = pattern.match(remote_url)
        if match:
            return match.group("owner"), match.group("repo")
    return None


class GitHistoryExtractor(BaseExtractor):
    name: ClassVar[str] = "git_history"
    description: ClassVar[str] = (
        "Walk git commit history + GitHub PR/comment data. Foundation for "
        "6 historical extractors (#11, #12, #26, #32, #43, #44)."
    )
    constraints: ClassVar[list[str]] = []
    indexes: ClassVar[list[str]] = []
    timeout_s: ClassVar[float] = 3600.0

    async def run(
        self,
        *,
        graphiti: object,
        ctx: ExtractorRunContext,
    ) -> ExtractorStats:
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
            ckpt = await load_git_history_checkpoint(driver, ctx.group_id)
            commits_written = 0
            prs_written = 0
            pr_comments_written = 0
            edges_written = 0
            full_resync = False

            # --- Phase 1: pygit2 commit walk ---
            check_phase_budget(
                nodes_written_so_far=commits_written,
                max_occurrences_total=getattr(
                    settings, "git_history_max_commits_per_run", 200_000
                ),
                phase="phase1_commits",
            )
            try:
                walker = Pygit2Walker(repo_path=ctx.repo_path)
                new_head_sha = walker.head_sha()
                try:
                    commits_list = list(walker.walk_since(ckpt.last_commit_sha))
                except CommitNotFoundError:
                    log.warning(
                        "git_history_resync_full",
                        extra={
                            "event": "git_history_resync_full",
                            "project_id": ctx.group_id,
                            "last_commit_sha_attempted": ckpt.last_commit_sha,
                        },
                    )
                    full_resync = True
                    commits_list = list(walker.walk_since(None))

                total_commits = len(commits_list)
                log.info(
                    "git_history_phase1_walk_start",
                    extra={
                        "event": "git_history_phase1_walk_start",
                        "project_id": ctx.group_id,
                        "total_commits": total_commits,
                        "full_resync": full_resync,
                    },
                )
                tantivy_index_path = project_index_path(
                    settings.git_history_tantivy_index_path,
                    ctx.group_id,
                )
                async with GitHistoryTantivyWriter(tantivy_index_path) as tw:
                    for commit in commits_list:
                        bot_flag = is_bot(commit["author_email"], commit["author_name"])
                        await write_commit_with_author(
                            driver, ctx.group_id, commit, is_bot=bot_flag
                        )
                        from palace_mcp.extractors.git_history.models import Commit

                        commit_obj = Commit(
                            project_id=ctx.group_id,
                            sha=commit["sha"],
                            author_provider="git",
                            author_identity_key=commit["author_email"].lower(),
                            committer_provider="git",
                            committer_identity_key=commit["committer_email"].lower(),
                            message_subject=commit["message_subject"],
                            message_full_truncated=commit["message_full_truncated"],
                            committed_at=commit["committed_at"],
                            parents=commit["parents"],
                        )
                        await tw.add_commit_async(
                            commit_obj, body_full=commit["message_full_truncated"]
                        )
                        commits_written += 1
                        edges_written += 2 + len(commit["touched_files"])
                        if commits_written % 500 == 0:
                            log.info(
                                "git_history_phase1_progress",
                                extra={
                                    "event": "git_history_phase1_progress",
                                    "project_id": ctx.group_id,
                                    "commits_written": commits_written,
                                    "total_commits": total_commits,
                                },
                            )

                await write_git_history_checkpoint(
                    driver,
                    ctx.group_id,
                    last_commit_sha=new_head_sha,
                    last_pr_updated_at=ckpt.last_pr_updated_at,
                    last_phase_completed="phase1",
                )
                log.info(
                    "git_history_phase1_complete",
                    extra={
                        "event": "git_history_phase1_complete",
                        "project_id": ctx.group_id,
                        "commits_written": commits_written,
                    },
                )
            except Exception as exc:
                log.exception(
                    "git_history_phase1_failed",
                    extra={
                        "event": "git_history_phase_failed",
                        "project_id": ctx.group_id,
                        "phase": "phase1",
                        "error_repr": repr(exc),
                    },
                )
                raise

            # --- Phase 2: GitHub GraphQL PR/comment ingest ---
            if not settings.github_token:
                log.warning(
                    "git_history_phase2_skipped_no_token",
                    extra={
                        "event": "git_history_phase2_skipped_no_token",
                        "project_id": ctx.group_id,
                    },
                )
                log.info(
                    "git_history_complete",
                    extra={
                        "event": "git_history_complete",
                        "project_id": ctx.group_id,
                        "commits_written": commits_written,
                        "prs_written": 0,
                        "pr_comments_written": 0,
                        "full_resync": full_resync,
                    },
                )
                await finalize_ingest_run(driver, run_id=ctx.run_id, success=True)
                return ExtractorStats(
                    nodes_written=commits_written,
                    edges_written=edges_written,
                    outcome=ExtractorOutcome.SKIPPED,
                    message=(
                        "GitHub token not configured; skipped pull request and "
                        "comment ingestion after the commit walk."
                    ),
                    next_action=(
                        "Set PALACE_GITHUB_TOKEN and rerun git_history if pull "
                        "request coverage is required."
                    ),
                )

            # Phase 2 with token: fetch PRs via GraphQL
            from palace_mcp.extractors.git_history.github_client import (
                GitHubClient,
                GitHubRepositoryUnavailable,
            )
            from palace_mcp.extractors.git_history.neo4j_writer import (
                write_pr,
                write_pr_comment,
            )

            github_repo = _resolve_github_repo(ctx.repo_path)
            if github_repo is None:
                log.warning(
                    "git_history_phase2_skipped_no_github_remote",
                    extra={
                        "event": "git_history_phase2_skipped_no_github_remote",
                        "project_id": ctx.group_id,
                    },
                )
                log.info(
                    "git_history_complete",
                    extra={
                        "event": "git_history_complete",
                        "project_id": ctx.group_id,
                        "commits_written": commits_written,
                        "prs_written": 0,
                        "pr_comments_written": 0,
                        "full_resync": full_resync,
                    },
                )
                await finalize_ingest_run(driver, run_id=ctx.run_id, success=True)
                return ExtractorStats(
                    nodes_written=commits_written,
                    edges_written=edges_written,
                    outcome=ExtractorOutcome.SKIPPED,
                    message=(
                        "GitHub origin remote not detected; skipped pull request "
                        "and comment ingestion after the commit walk."
                    ),
                    next_action=(
                        "Set origin to a github.com remote and rerun git_history "
                        "if pull request coverage is required."
                    ),
                )
            owner, repo_name = github_repo

            gh_client = GitHubClient(token=settings.github_token)
            max_pr_updated_at: datetime | None = None
            try:
                async for batch in gh_client.fetch_prs_since(
                    owner, repo_name, since=ckpt.last_pr_updated_at
                ):
                    for pr_node in batch:
                        identity_key = (pr_node.get("author", {}) or {}).get(
                            "login", "ghost"
                        )
                        bot_flag = is_bot(None, identity_key)
                        await write_pr(
                            driver,
                            ctx.group_id,
                            {
                                "number": pr_node["number"],
                                "title": pr_node.get("title", ""),
                                "body_truncated": (pr_node.get("body") or "")[:1024],
                                "state": pr_node.get("state", "open").lower(),
                                "head_sha": pr_node.get("headRefOid"),
                                "base_branch": (pr_node.get("baseRef") or {}).get(
                                    "name", ""
                                ),
                                "created_at": pr_node.get("createdAt"),
                                "merged_at": pr_node.get("mergedAt"),
                            },
                            author_identity_key=identity_key,
                            author_provider="github",
                            is_bot=bot_flag,
                        )
                        prs_written += 1
                        edges_written += 1

                        # Track the latest PR updatedAt for checkpoint advancement.
                        raw_updated = pr_node.get("updatedAt")
                        if raw_updated:
                            pr_dt = datetime.fromisoformat(
                                raw_updated.replace("Z", "+00:00")
                            )
                            if max_pr_updated_at is None or pr_dt > max_pr_updated_at:
                                max_pr_updated_at = pr_dt

                        for cmt in (pr_node.get("comments") or {}).get("nodes", []):
                            cmt_author = (cmt.get("author") or {}).get(
                                "login"
                            ) or "ghost"
                            await write_pr_comment(
                                driver,
                                ctx.group_id,
                                {
                                    "id": cmt["id"],
                                    "pr_number": pr_node["number"],
                                    "body_truncated": (cmt.get("body") or "")[:1024],
                                    "created_at": cmt.get("createdAt"),
                                },
                                author_identity_key=cmt_author,
                                author_provider="github",
                                is_bot=is_bot(None, cmt_author),
                            )
                            pr_comments_written += 1
                            edges_written += 2
            except GitHubRepositoryUnavailable:
                log.warning(
                    "git_history_phase2_skipped_github_repo_unavailable",
                    extra={
                        "event": "git_history_phase2_skipped_github_repo_unavailable",
                        "project_id": ctx.group_id,
                        "github_owner": owner,
                        "github_repo": repo_name,
                    },
                )
                log.info(
                    "git_history_complete",
                    extra={
                        "event": "git_history_complete",
                        "project_id": ctx.group_id,
                        "commits_written": commits_written,
                        "prs_written": 0,
                        "pr_comments_written": 0,
                        "full_resync": full_resync,
                    },
                )
                await finalize_ingest_run(driver, run_id=ctx.run_id, success=True)
                return ExtractorStats(
                    nodes_written=commits_written,
                    edges_written=edges_written,
                    outcome=ExtractorOutcome.SKIPPED,
                    message=(
                        f"GitHub GraphQL did not return repository {owner}/{repo_name}; "
                        "skipped pull request and comment ingestion after the commit walk."
                    ),
                    next_action=(
                        "Check GitHub token access to the repository, or rerun with a "
                        "token that can read repository pull requests."
                    ),
                )
            finally:
                await gh_client.aclose()

            await write_git_history_checkpoint(
                driver,
                ctx.group_id,
                last_commit_sha=new_head_sha,
                last_pr_updated_at=max_pr_updated_at or ckpt.last_pr_updated_at,
                last_phase_completed="phase2",
            )

            log.info(
                "git_history_complete",
                extra={
                    "event": "git_history_complete",
                    "project_id": ctx.group_id,
                    "commits_written": commits_written,
                    "prs_written": prs_written,
                    "pr_comments_written": pr_comments_written,
                    "full_resync": full_resync,
                },
            )
            await finalize_ingest_run(driver, run_id=ctx.run_id, success=True)
            return ExtractorStats(
                nodes_written=commits_written + prs_written + pr_comments_written,
                edges_written=edges_written,
            )

        except ExtractorError:
            await finalize_ingest_run(
                driver,
                run_id=ctx.run_id,
                success=False,
                error_code="extractor_error",
            )
            raise
        except Exception:
            await finalize_ingest_run(
                driver,
                run_id=ctx.run_id,
                success=False,
                error_code="unknown",
            )
            raise
