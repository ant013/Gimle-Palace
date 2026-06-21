from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable

from neo4j import AsyncDriver

from palace_mcp.git.command import GitError, GitTimeout, run_git

_GIT_CHANGESET_CAP = 500

_READ_FILE_COMMITS_CYPHER = """
MATCH (f:File {project_id: $project_id})
WHERE coalesce(f.last_seen_in_commit, f.commit_sha) IS NOT NULL
RETURN collect(DISTINCT coalesce(f.last_seen_in_commit, f.commit_sha)) AS commits
"""


class IncrementalMode(StrEnum):
    FULL = "full"
    INCREMENTAL = "incremental"
    SKIP = "skip"


class AuditScopeKind(StrEnum):
    FILE = "file"
    MODULE = "module"
    MIXED = "mixed"
    PROJECT = "project"


AUDIT_EXTRACTOR_SCOPE_KINDS: dict[str, AuditScopeKind] = {
    "code_ownership": AuditScopeKind.FILE,
    "crypto_domain_model": AuditScopeKind.FILE,
    "error_handling_policy": AuditScopeKind.FILE,
    "coding_convention": AuditScopeKind.MODULE,
    "testability_di": AuditScopeKind.MODULE,
    "localization_accessibility": AuditScopeKind.MIXED,
    "dead_symbol_binary_surface": AuditScopeKind.PROJECT,
}

FILE_SCOPED_AUDIT_EXTRACTORS: frozenset[str] = frozenset(
    name
    for name, scope_kind in AUDIT_EXTRACTOR_SCOPE_KINDS.items()
    if scope_kind == AuditScopeKind.FILE
)


@dataclass(frozen=True)
class _GitChangeSet:
    changed: set[str]
    added: set[str]
    removed: set[str]
    truncated: bool


@dataclass(frozen=True)
class IncrementalPathScope:
    mode: IncrementalMode
    changed_paths: set[str]
    removed_paths: set[str]
    reason: str | None = None


def incremental_ingest_enabled(settings: object) -> bool:
    value = getattr(settings, "palace_incremental_ingest", False)
    return value if isinstance(value, bool) else False


async def derive_incremental_path_scope(
    driver: AsyncDriver,
    *,
    repo_path: Path,
    project_id: str,
    settings: object,
    force: bool = False,
    path_filter: Callable[[str], bool] | None = None,
) -> IncrementalPathScope:
    if force or not incremental_ingest_enabled(settings):
        return IncrementalPathScope(
            mode=IncrementalMode.FULL,
            changed_paths=set(),
            removed_paths=set(),
            reason="incremental_disabled",
        )

    previous_commit_sha = await read_existing_commit_sha(driver, project_id=project_id)
    if not previous_commit_sha:
        return IncrementalPathScope(
            mode=IncrementalMode.FULL,
            changed_paths=set(),
            removed_paths=set(),
            reason="previous_commit_missing",
        )

    try:
        git_changes = await _read_git_change_set(repo_path, previous_commit_sha)
    except (GitError, GitTimeout):
        return IncrementalPathScope(
            mode=IncrementalMode.FULL,
            changed_paths=set(),
            removed_paths=set(),
            reason="git_diff_error",
        )

    if git_changes.truncated:
        return IncrementalPathScope(
            mode=IncrementalMode.FULL,
            changed_paths=set(),
            removed_paths=set(),
            reason="git_diff_truncated",
        )

    changed_paths = _filter_paths(git_changes.changed | git_changes.added, path_filter)
    removed_paths = _filter_paths(git_changes.removed, path_filter)
    if not changed_paths and not removed_paths:
        return IncrementalPathScope(
            mode=IncrementalMode.SKIP,
            changed_paths=set(),
            removed_paths=set(),
            reason="no_relevant_changes",
        )

    return IncrementalPathScope(
        mode=IncrementalMode.INCREMENTAL,
        changed_paths=changed_paths,
        removed_paths=removed_paths,
    )


async def read_existing_commit_sha(
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


def _filter_paths(
    paths: set[str], path_filter: Callable[[str], bool] | None
) -> set[str]:
    if path_filter is None:
        return set(paths)
    return {path for path in paths if path_filter(path)}


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
