from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable

from neo4j import AsyncDriver

from palace_mcp.extractors.foundation.baseline import (
    BASELINE_STATUS_VALID,
    load_extractor_baseline,
)
from palace_mcp.git.command import GitError, GitTimeout, run_git

_GIT_CHANGESET_CAP = 500
_SWIFT_SYMBOL_BASELINE_KIND = "swift_symbol_scope"
_SWIFT_SYMBOL_BASELINE_STATE_VERSION = 1
_SWIFT_SOURCE_SUFFIXES = (".swift", ".swiftinterface")

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


@dataclass(frozen=True)
class SwiftDeltaScope:
    mode: IncrementalMode
    changed_paths: set[str]
    removed_paths: set[str]
    reason: str | None
    baseline_state: str
    baseline_commit_sha: str | None
    baseline_state_version: int | None
    baseline_invalid_reason: str | None
    baseline_successful_run_id: str | None
    validated_by: str | None
    changed_ratio: float | None = None


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


async def derive_swift_delta_scope(
    driver: AsyncDriver,
    *,
    repo_path: Path,
    project_id: str,
    settings: object,
    force: bool = False,
    scip_paths: set[str] | None = None,
    body_changed_paths: set[str] | None = None,
    body_removed_paths: set[str] | None = None,
    changed_ratio: float | None = None,
    full_reprocess_threshold: float = 0.8,
    extractor_name: str = "symbol_index_swift",
) -> SwiftDeltaScope:
    if force or not incremental_ingest_enabled(settings):
        return _swift_delta_scope(
            mode=IncrementalMode.FULL,
            reason="incremental_disabled",
        )

    baseline = await load_extractor_baseline(
        driver,
        project_id=project_id,
        extractor=extractor_name,
        baseline_kind=_SWIFT_SYMBOL_BASELINE_KIND,
    )
    if baseline is None:
        return _swift_delta_scope(
            mode=IncrementalMode.FULL,
            reason="baseline_missing",
            baseline_state="missing",
        )
    if baseline.status != BASELINE_STATUS_VALID:
        invalid_reason = baseline.invalid_reason or "baseline_invalid"
        return _swift_delta_scope(
            mode=IncrementalMode.FULL,
            reason=invalid_reason,
            baseline_state="invalid",
            baseline_commit_sha=baseline.commit_sha,
            baseline_state_version=baseline.state_version,
            baseline_invalid_reason=invalid_reason,
            baseline_successful_run_id=baseline.successful_run_id,
        )
    if baseline.state_version != _SWIFT_SYMBOL_BASELINE_STATE_VERSION:
        return _swift_delta_scope(
            mode=IncrementalMode.FULL,
            reason="baseline_schema_mismatch",
            baseline_state="invalid",
            baseline_commit_sha=baseline.commit_sha,
            baseline_state_version=baseline.state_version,
            baseline_invalid_reason="baseline_schema_mismatch",
            baseline_successful_run_id=baseline.successful_run_id,
        )
    if changed_ratio is not None and changed_ratio >= full_reprocess_threshold:
        return _swift_delta_scope(
            mode=IncrementalMode.FULL,
            reason="high_changed_ratio",
            baseline_state="present",
            baseline_commit_sha=baseline.commit_sha,
            baseline_state_version=baseline.state_version,
            baseline_successful_run_id=baseline.successful_run_id,
            changed_ratio=changed_ratio,
        )

    try:
        git_changes = await _read_git_change_set(repo_path, baseline.commit_sha)
    except (GitError, GitTimeout):
        return _swift_delta_scope(
            mode=IncrementalMode.FULL,
            reason="git_diff_error",
            baseline_state="present",
            baseline_commit_sha=baseline.commit_sha,
            baseline_state_version=baseline.state_version,
            baseline_successful_run_id=baseline.successful_run_id,
            changed_ratio=changed_ratio,
        )

    if git_changes.truncated:
        return _swift_delta_scope(
            mode=IncrementalMode.FULL,
            reason="git_diff_truncated",
            baseline_state="present",
            baseline_commit_sha=baseline.commit_sha,
            baseline_state_version=baseline.state_version,
            baseline_successful_run_id=baseline.successful_run_id,
            changed_ratio=changed_ratio,
        )

    git_changed = _filter_swift_paths(git_changes.changed | git_changes.added)
    git_removed = _filter_swift_paths(git_changes.removed)
    selected_paths = git_changed
    validated_by = "baseline_only"
    if scip_paths is not None:
        selected_paths = git_changed & scip_paths
        if git_changed - scip_paths:
            return _swift_delta_scope(
                mode=IncrementalMode.FULL,
                reason="scip_path_mismatch",
                baseline_state="present",
                baseline_commit_sha=baseline.commit_sha,
                baseline_state_version=baseline.state_version,
                baseline_successful_run_id=baseline.successful_run_id,
                changed_ratio=changed_ratio,
                validated_by="symbol_index_swift",
            )
        validated_by = "symbol_index_swift"

    if body_changed_paths is not None:
        scoped_body_changes = _filter_swift_paths(body_changed_paths)
        if scoped_body_changes != selected_paths:
            return _swift_delta_scope(
                mode=IncrementalMode.FULL,
                reason="body_hash_changed_mismatch",
                baseline_state="present",
                baseline_commit_sha=baseline.commit_sha,
                baseline_state_version=baseline.state_version,
                baseline_successful_run_id=baseline.successful_run_id,
                changed_ratio=changed_ratio,
                validated_by=validated_by,
            )
        validated_by = "symbol_index_swift"

    if body_removed_paths is not None:
        scoped_body_removals = _filter_swift_paths(body_removed_paths)
        if scoped_body_removals != git_removed:
            return _swift_delta_scope(
                mode=IncrementalMode.FULL,
                reason="body_hash_removed_mismatch",
                baseline_state="present",
                baseline_commit_sha=baseline.commit_sha,
                baseline_state_version=baseline.state_version,
                baseline_successful_run_id=baseline.successful_run_id,
                changed_ratio=changed_ratio,
                validated_by=validated_by,
            )
        validated_by = "symbol_index_swift"

    if not selected_paths and not git_removed:
        return _swift_delta_scope(
            mode=IncrementalMode.SKIP,
            reason="no_relevant_changes",
            baseline_state="present",
            baseline_commit_sha=baseline.commit_sha,
            baseline_state_version=baseline.state_version,
            baseline_successful_run_id=baseline.successful_run_id,
            changed_ratio=changed_ratio,
            validated_by=validated_by,
        )

    return _swift_delta_scope(
        mode=IncrementalMode.INCREMENTAL,
        reason=None,
        changed_paths=selected_paths,
        removed_paths=git_removed,
        baseline_state="present",
        baseline_commit_sha=baseline.commit_sha,
        baseline_state_version=baseline.state_version,
        baseline_successful_run_id=baseline.successful_run_id,
        changed_ratio=changed_ratio,
        validated_by=validated_by,
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


def _filter_swift_paths(paths: set[str]) -> set[str]:
    return {path for path in paths if path.endswith(_SWIFT_SOURCE_SUFFIXES)}


def _swift_delta_scope(
    *,
    mode: IncrementalMode,
    reason: str | None,
    changed_paths: set[str] | None = None,
    removed_paths: set[str] | None = None,
    baseline_state: str = "unknown",
    baseline_commit_sha: str | None = None,
    baseline_state_version: int | None = None,
    baseline_invalid_reason: str | None = None,
    baseline_successful_run_id: str | None = None,
    validated_by: str | None = None,
    changed_ratio: float | None = None,
) -> SwiftDeltaScope:
    return SwiftDeltaScope(
        mode=mode,
        changed_paths=set() if changed_paths is None else changed_paths,
        removed_paths=set() if removed_paths is None else removed_paths,
        reason=reason,
        baseline_state=baseline_state,
        baseline_commit_sha=baseline_commit_sha,
        baseline_state_version=baseline_state_version,
        baseline_invalid_reason=baseline_invalid_reason,
        baseline_successful_run_id=baseline_successful_run_id,
        validated_by=validated_by,
        changed_ratio=changed_ratio,
    )


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
