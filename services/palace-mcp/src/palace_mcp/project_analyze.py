"""Durable project-analysis orchestration core for MCP/CLI entrypoints.

This module owns the durable AnalysisRun state machine. MCP and CLI layers can
start a run quickly, poll Neo4j-backed status, and resume execution after
interruption without keeping orchestration state in memory.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, TypeVar
from uuid import uuid4

from neo4j import AsyncDriver, AsyncManagedTransaction
from neo4j.exceptions import ServiceUnavailable, SessionExpired
from pydantic import BaseModel, ConfigDict, Field

from palace_mcp.audit.run import run_audit
from palace_mcp.code.native_detect_changes import FALLBACK_TO_CM, native_detect_changes
from palace_mcp.extractors.base import ExtractorExecutionMode
from palace_mcp.extractors.foundation.profiles import get_ordered_extractors
from palace_mcp.extractors.runner import run_extractor
from palace_mcp.git.command import GitError, GitTimeout, run_git
from palace_mcp.memory.bundle import add_to_bundle, register_bundle
from palace_mcp.memory.cypher import (
    MARK_PROJECT_INDEXED_COMMIT_UNAVAILABLE,
    SET_PROJECT_INDEXED_COMMIT,
    ACQUIRE_ANALYSIS_LOCK,
    CREATE_CONSTRAINTS,
    CREATE_INDEXES,
    CREATE_ANALYSIS_RUN,
    FINALIZE_ANALYSIS_RUN,
    GET_PROJECT,
    GET_ACTIVE_ANALYSIS_RUN,
    GET_ANALYSIS_RUN_WITH_CHECKPOINTS,
    MARK_ANALYSIS_RUN_RESUMABLE,
    UPDATE_ANALYSIS_RUN_LEASE,
    UPDATE_ANALYSIS_RUN_PROGRESS,
    UPSERT_ANALYSIS_CHECKPOINT,
)
from palace_mcp.memory.models import Tier
from palace_mcp.memory.project_tools import register_project
from palace_mcp.git.path_resolver import (
    ProjectNotRegistered,
    resolve_registered_project,
)

if TYPE_CHECKING:
    from graphiti_core import Graphiti
    from palace_mcp.extractors.base import BaseExtractor


CFG = ConfigDict(extra="forbid")
logger = logging.getLogger(__name__)
_T = TypeVar("_T")
_EXPECTED_PROFILE_SLUGS = frozenset({"uw-ios-app", "uw-ios-baseline"})
_INCREMENTAL_FULL_REPROCESS_THRESHOLD = 0.8
_INCREMENTAL_GLOBAL_EXTRACTORS = frozenset(
    {"dead_code", "hotspot", "cross_module_contract"}
)


class AnalysisRunMode(StrEnum):
    FULL = "full"
    INCREMENTAL = "incremental"


class AnalysisRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RESUMABLE = "RESUMABLE"
    SUCCEEDED = "SUCCEEDED"
    SUCCEEDED_WITH_SKIPS = "SUCCEEDED_WITH_SKIPS"
    SUCCEEDED_WITH_FAILURES = "SUCCEEDED_WITH_FAILURES"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class AnalysisCheckpointStatus(StrEnum):
    OK = "OK"
    SKIPPED = "SKIPPED"
    MISSING_INPUT = "MISSING_INPUT"
    RUN_FAILED = "RUN_FAILED"
    FETCH_FAILED = "FETCH_FAILED"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"


ACTIVE_ANALYSIS_RUN_STATUSES: frozenset[AnalysisRunStatus] = frozenset(
    {
        AnalysisRunStatus.PENDING,
        AnalysisRunStatus.RUNNING,
        AnalysisRunStatus.RESUMABLE,
    }
)
TERMINAL_ANALYSIS_RUN_STATUSES: frozenset[AnalysisRunStatus] = frozenset(
    {
        AnalysisRunStatus.SUCCEEDED,
        AnalysisRunStatus.SUCCEEDED_WITH_SKIPS,
        AnalysisRunStatus.SUCCEEDED_WITH_FAILURES,
        AnalysisRunStatus.FAILED,
        AnalysisRunStatus.CANCELED,
    }
)
NON_FAILING_ANALYSIS_CHECKPOINT_STATUSES: frozenset[AnalysisCheckpointStatus] = (
    frozenset(
        {
            AnalysisCheckpointStatus.OK,
            AnalysisCheckpointStatus.SKIPPED,
            AnalysisCheckpointStatus.MISSING_INPUT,
        }
    )
)
FAILING_ANALYSIS_CHECKPOINT_STATUSES: frozenset[AnalysisCheckpointStatus] = frozenset(
    {
        AnalysisCheckpointStatus.RUN_FAILED,
        AnalysisCheckpointStatus.FETCH_FAILED,
    }
)


class AnalysisCheckpoint(BaseModel):
    model_config = CFG

    extractor: str
    position: int = Field(ge=0)
    status: AnalysisCheckpointStatus = AnalysisCheckpointStatus.NOT_ATTEMPTED
    mode: ExtractorExecutionMode | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error_code: str | None = None
    message: str | None = None
    ingest_run_id: str | None = None
    next_action: str | None = None


class AnalysisRun(BaseModel):
    model_config = CFG

    run_id: str
    slug: str
    project_name: str | None = None
    parent_mount: str
    relative_path: str
    language_profile: str
    bundle: str | None = None
    extractors: list[str]
    depth: str
    requested_mode: AnalysisRunMode = AnalysisRunMode.FULL
    effective_mode: AnalysisRunMode = AnalysisRunMode.FULL
    effective_mode_reason: str | None = None
    stale_since_commit: str | None = None
    changed_file_count: int | None = None
    changed_file_ratio: float | None = None
    continue_on_failure: bool = True
    idempotency_key: str
    status: AnalysisRunStatus
    created_at: str
    updated_at: str
    started_at: str
    finished_at: str | None = None
    lease_owner: str | None = None
    lease_expires_at: str | None = None
    last_completed_extractor: str | None = None
    error_code: str | None = None
    message: str | None = None
    checkpoints: list[AnalysisCheckpoint] = Field(default_factory=list)
    overview: dict[str, int] = Field(default_factory=dict)
    audit: dict[str, Any] | None = None
    report_markdown: str | None = None
    next_actions: list[str] = Field(default_factory=list)

    @property
    def lock_key(self) -> str:
        return f"{self.slug}|{self.language_profile}"


class AnalysisRunStartResult(BaseModel):
    model_config = CFG

    run: AnalysisRun
    active_run_reused: bool = False


class ExtractorAttemptResult(BaseModel):
    model_config = CFG

    status: AnalysisCheckpointStatus
    mode: ExtractorExecutionMode = ExtractorExecutionMode.FULL
    ingest_run_id: str | None = None
    error_code: str | None = None
    message: str | None = None
    next_action: str | None = None


class AnalysisRunNotFoundError(ValueError):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"analysis run not found: {run_id}")
        self.run_id = run_id


class ActiveAnalysisRunExistsError(ValueError):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"ACTIVE_ANALYSIS_RUN_EXISTS: {run_id}")
        self.run_id = run_id


class AnalysisRunNotResumableError(ValueError):
    def __init__(self, run_id: str, reason: str) -> None:
        super().__init__(f"analysis run {run_id} is not resumable: {reason}")
        self.run_id = run_id
        self.reason = reason


class AnalysisRunStore(Protocol):
    async def start_run(self, run: AnalysisRun) -> AnalysisRunStartResult: ...

    async def get_run(
        self, run_id: str, *, now: datetime | None = None
    ) -> AnalysisRun: ...

    async def acquire_lease(
        self,
        run_id: str,
        *,
        lease_owner: str,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> AnalysisRun: ...

    async def mark_run_resumable(
        self,
        run_id: str,
        *,
        now: datetime | None = None,
    ) -> AnalysisRun: ...

    async def save_checkpoint(
        self,
        run_id: str,
        checkpoint: AnalysisCheckpoint,
        *,
        updated_at: str,
        last_completed_extractor: str | None,
        status: AnalysisRunStatus,
        lease_owner: str | None,
        lease_expires_at: str | None,
    ) -> AnalysisRun: ...

    async def finalize_run(
        self,
        run_id: str,
        *,
        status: AnalysisRunStatus,
        overview: dict[str, int],
        audit: dict[str, Any] | None,
        report_markdown: str | None,
        next_actions: list[str],
        error_code: str | None = None,
        message: str | None = None,
        now: datetime | None = None,
    ) -> AnalysisRun: ...


ExtractorExecutor = Callable[[str, AnalysisRun], Awaitable[ExtractorAttemptResult]]
AuditRunner = Callable[..., Awaitable[dict[str, Any]]]
SchemaEnsurer = Callable[..., Awaitable[None]]
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _serialize_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True)


def _deserialize_json_object(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("expected JSON object payload")
    return parsed


def _deserialize_json_string_list(value: str | None) -> list[str]:
    if value is None:
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list) or not all(
        isinstance(item, str) for item in parsed
    ):
        raise ValueError("expected JSON string list payload")
    return list(parsed)


async def _resolve_registered_repo_path(driver: AsyncDriver, slug: str) -> Path:
    async with driver.session() as session:
        result = await session.run(GET_PROJECT, slug=slug)
        row = await result.single()
    if row is None:
        raise ProjectNotRegistered(slug)
    return resolve_registered_project(slug, project_node=row["p"])


async def _read_project_head_sha(driver: AsyncDriver, slug: str) -> str | None:
    try:
        repo_path = await _resolve_registered_repo_path(driver, slug)
    except (ProjectNotRegistered, ValueError):
        return None
    try:
        result = await asyncio.to_thread(
            run_git,
            ["rev-parse", "HEAD"],
            repo_path=repo_path,
            # Cap must exceed the expected 1 line: run_git flags truncated
            # whenever output EXACTLY fills the cap (cap reached = producer
            # killed), so cap=1 marked every valid single-line sha truncated
            # and silently degraded incremental analyzes to full
            # (effective_mode_reason=repo_head_unavailable).
            max_stdout_lines=2,
        )
    except (GitError, GitTimeout):
        return None
    if result.rc != 0 or result.truncated:
        return None
    return result.stdout.strip() or None


async def _count_project_files(driver: AsyncDriver, project_id: str) -> int:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (f:File {project_id: $project_id}) RETURN count(f) AS total",
            project_id=project_id,
        )
        row = await result.single()
    total = row["total"] if row is not None else 0
    return int(total or 0)


async def _read_project_indexed_commit(driver: AsyncDriver, slug: str) -> str | None:
    """Authoritative project-level indexed commit (:Project.indexed_commit).

    F2 (Sprint-1 reliability): the dominant per-symbol vote is NOT consulted —
    after any incremental ingest the vote is a previous run's sha, which made
    incremental-vs-full planning (and overview lag) wrong. Null (legacy,
    pre-backfill) honestly plans as full.
    """
    async with driver.session() as session:
        result = await session.run(
            "MATCH (p:Project {slug: $slug}) RETURN p.indexed_commit AS commit_sha",
            slug=slug,
        )
        row = await result.single()
    if row is None or row["commit_sha"] is None:
        return None
    return str(row["commit_sha"]) or None


_BASELINE_INDEXED_COMMIT = """
MATCH (b:ExtractorBaseline {project_id: $project_id, extractor: $extractor})
RETURN coalesce(b.indexed_commit, b.commit_sha) AS commit
ORDER BY b.updated_at DESC
LIMIT 1
""".strip()


async def _record_project_indexed_commit(
    driver: AsyncDriver, slug: str, extractor: str, *, now_iso: str
) -> None:
    """F2 writer: persist the authoritative indexed commit after symbol_index OK.

    Source = the extractor's own baseline (ingest-time tree HEAD — what the
    symbols were actually stamped with; language-agnostic). Monotonic via
    indexed_at guard. A decline is PERSISTED (indexed_commit_status =
    'unavailable'), never just logged: absence must be diagnosable from the
    payload (legacy-null vs broken-now).
    """
    try:
        async with driver.session() as session:
            result = await session.run(
                _BASELINE_INDEXED_COMMIT,
                project_id=f"project/{slug}",
                extractor=extractor,
            )
            row = await result.single()
            commit = str(row["commit"]) if row is not None and row["commit"] else None
            if commit:
                await session.run(
                    SET_PROJECT_INDEXED_COMMIT,
                    slug=slug,
                    indexed_commit=commit,
                    indexed_at=now_iso,
                )
            else:
                await session.run(
                    MARK_PROJECT_INDEXED_COMMIT_UNAVAILABLE,
                    slug=slug,
                    now=now_iso,
                )
                logger.warning(
                    "project_analyze.indexed_commit_unavailable",
                    extra={"project": slug, "extractor": extractor},
                )
    except Exception:  # noqa: BLE001 — best-effort metadata; never fail the run
        logger.warning(
            "project_analyze.indexed_commit_write_failed",
            extra={"project": slug, "extractor": extractor},
            exc_info=True,
        )


async def _resolve_run_mode_plan(
    driver: AsyncDriver,
    *,
    slug: str,
    requested_mode: AnalysisRunMode,
) -> tuple[
    AnalysisRunMode,
    str | None,
    str | None,
    int | None,
    float | None,
]:
    if requested_mode != AnalysisRunMode.INCREMENTAL:
        return AnalysisRunMode.FULL, "requested_full", None, None, None

    head_sha = await _read_project_head_sha(driver, slug)
    if head_sha is None:
        return AnalysisRunMode.FULL, "repo_head_unavailable", None, None, None

    indexed_commit = await _read_project_indexed_commit(driver, slug)
    if indexed_commit is None:
        return AnalysisRunMode.FULL, "indexed_commit_unavailable", head_sha, None, None

    detect_result = await native_detect_changes(project=slug, since=indexed_commit)
    if detect_result is FALLBACK_TO_CM:
        return AnalysisRunMode.FULL, "detect_changes_unavailable", head_sha, None, None
    if not isinstance(detect_result, dict) or detect_result.get("ok") is not True:
        reason = (
            str(detect_result.get("error_code"))
            if isinstance(detect_result, dict) and detect_result.get("error_code")
            else "detect_changes_unusable"
        )
        return AnalysisRunMode.FULL, reason, head_sha, None, None
    if detect_result.get("truncated") is True:
        return AnalysisRunMode.FULL, "detect_changes_truncated", head_sha, None, None

    raw_files = detect_result.get("files")
    if not isinstance(raw_files, list) or not all(
        isinstance(path, str) for path in raw_files
    ):
        return AnalysisRunMode.FULL, "detect_changes_unusable", head_sha, None, None

    project_file_count = await _count_project_files(driver, f"project/{slug}")
    if project_file_count <= 0:
        return (
            AnalysisRunMode.FULL,
            "project_file_count_unavailable",
            head_sha,
            None,
            None,
        )

    changed_file_count = len({path for path in raw_files if path})
    changed_file_ratio = changed_file_count / project_file_count
    if changed_file_ratio >= _INCREMENTAL_FULL_REPROCESS_THRESHOLD:
        return (
            AnalysisRunMode.FULL,
            "change_threshold_exceeded",
            head_sha,
            changed_file_count,
            changed_file_ratio,
        )

    return (
        AnalysisRunMode.INCREMENTAL,
        "requested_incremental",
        head_sha,
        changed_file_count,
        changed_file_ratio,
    )


async def ensure_project_analyze_schema(driver: AsyncDriver) -> None:
    """Apply only DDL required for project-analyze runtime state."""
    async with driver.session() as session:
        for stmt in CREATE_CONSTRAINTS:
            await session.run(stmt)
        for stmt in CREATE_INDEXES:
            await session.run(stmt)


def _checkpoint_counts(
    checkpoints: Sequence[AnalysisCheckpoint],
) -> dict[str, int]:
    counts = {status.value: 0 for status in AnalysisCheckpointStatus}
    for checkpoint in checkpoints:
        counts[checkpoint.status.value] += 1
    return counts


def _checkpoint_next_actions(
    checkpoints: Sequence[AnalysisCheckpoint],
) -> list[str]:
    seen: set[str] = set()
    next_actions: list[str] = []
    for checkpoint in checkpoints:
        if checkpoint.next_action is None or checkpoint.next_action in seen:
            continue
        seen.add(checkpoint.next_action)
        next_actions.append(checkpoint.next_action)
    return next_actions


def _checkpoint_was_interrupted(checkpoint: AnalysisCheckpoint) -> bool:
    return (
        checkpoint.status == AnalysisCheckpointStatus.NOT_ATTEMPTED
        and checkpoint.started_at is not None
        and checkpoint.finished_at is None
    )


def _checkpoint_has_progress(checkpoint: AnalysisCheckpoint) -> bool:
    return (
        checkpoint.status != AnalysisCheckpointStatus.NOT_ATTEMPTED
        or checkpoint.started_at is not None
        or checkpoint.finished_at is not None
    )


def _run_has_checkpoint_progress(run: AnalysisRun) -> bool:
    return any(_checkpoint_has_progress(checkpoint) for checkpoint in run.checkpoints)


def _lease_is_expired(run: AnalysisRun, now: datetime) -> bool:
    if run.lease_expires_at is None:
        return False
    expires_at = _parse_iso(run.lease_expires_at)
    return expires_at is not None and expires_at <= now


def _run_has_live_lease(run: AnalysisRun, now: datetime) -> bool:
    return (
        run.lease_owner is not None
        and run.lease_expires_at is not None
        and not _lease_is_expired(run, now)
    )


def _run_is_stuck_before_first_checkpoint(run: AnalysisRun, now: datetime) -> bool:
    return (
        run.status == AnalysisRunStatus.RUNNING
        and not _run_has_live_lease(run, now)
        and not _run_has_checkpoint_progress(run)
    )


def _run_can_be_force_replaced(run: AnalysisRun, now: datetime) -> bool:
    return (
        run.status == AnalysisRunStatus.RESUMABLE
        and not _run_has_checkpoint_progress(run)
    ) or _run_is_stuck_before_first_checkpoint(run, now)


def _response_mode_from_payload(
    payload: dict[str, Any],
    *,
    status: AnalysisCheckpointStatus,
) -> ExtractorExecutionMode:
    raw_mode = payload.get("mode")
    if isinstance(raw_mode, str):
        try:
            return ExtractorExecutionMode(raw_mode)
        except ValueError:
            pass
    if status in {
        AnalysisCheckpointStatus.SKIPPED,
        AnalysisCheckpointStatus.MISSING_INPUT,
    }:
        return ExtractorExecutionMode.SKIPPED
    return ExtractorExecutionMode.FULL


def _node_to_dict(node: Any) -> dict[str, Any]:
    if isinstance(node, dict):
        return node
    if hasattr(node, "items"):
        return {str(key): value for key, value in node.items()}
    raise TypeError(f"unsupported Neo4j node payload: {type(node).__name__}")


def _checkpoint_from_node(node: dict[str, Any]) -> AnalysisCheckpoint:
    return AnalysisCheckpoint(
        extractor=str(node["extractor"]),
        position=int(node["position"]),
        status=AnalysisCheckpointStatus(str(node["status"])),
        mode=(
            ExtractorExecutionMode(str(node["mode"]))
            if node.get("mode") is not None
            else None
        ),
        started_at=node.get("started_at"),
        finished_at=node.get("finished_at"),
        error_code=node.get("error_code"),
        message=node.get("message"),
        ingest_run_id=node.get("ingest_run_id"),
        next_action=node.get("next_action"),
    )


def _run_from_node(
    node: dict[str, Any],
    checkpoints: list[AnalysisCheckpoint],
) -> AnalysisRun:
    overview = _deserialize_json_object(node.get("overview_json")) or {}
    audit = _deserialize_json_object(node.get("audit_json"))
    next_actions = _deserialize_json_string_list(node.get("next_actions_json"))
    return AnalysisRun(
        run_id=str(node["run_id"]),
        slug=str(node["slug"]),
        project_name=node.get("project_name"),
        parent_mount=str(node["parent_mount"]),
        relative_path=str(node["relative_path"]),
        language_profile=str(node["language_profile"]),
        bundle=node.get("bundle"),
        extractors=list(node.get("extractors") or []),
        depth=str(node["depth"]),
        requested_mode=AnalysisRunMode(str(node.get("requested_mode") or "full")),
        effective_mode=AnalysisRunMode(str(node.get("effective_mode") or "full")),
        effective_mode_reason=node.get("effective_mode_reason"),
        stale_since_commit=node.get("stale_since_commit"),
        changed_file_count=(
            int(node["changed_file_count"])
            if node.get("changed_file_count") is not None
            else None
        ),
        changed_file_ratio=(
            float(node["changed_file_ratio"])
            if node.get("changed_file_ratio") is not None
            else None
        ),
        continue_on_failure=bool(node.get("continue_on_failure", True)),
        idempotency_key=str(node["idempotency_key"]),
        status=AnalysisRunStatus(str(node["status"])),
        created_at=str(node["created_at"]),
        updated_at=str(node["updated_at"]),
        started_at=str(node["started_at"]),
        finished_at=node.get("finished_at"),
        lease_owner=node.get("lease_owner"),
        lease_expires_at=node.get("lease_expires_at"),
        last_completed_extractor=node.get("last_completed_extractor"),
        error_code=node.get("error_code"),
        message=node.get("message"),
        checkpoints=checkpoints,
        overview={str(key): int(value) for key, value in overview.items()},
        audit=audit,
        report_markdown=node.get("report_markdown"),
        next_actions=next_actions,
    )


def _checkpoint_mode_label(checkpoint: AnalysisCheckpoint) -> str:
    return checkpoint.mode.value if checkpoint.mode is not None else "unknown"


def _stale_extractors(run: AnalysisRun) -> list[str]:
    return [
        checkpoint.extractor
        for checkpoint in run.checkpoints
        if checkpoint.mode == ExtractorExecutionMode.SKIPPED
        and checkpoint.extractor in _INCREMENTAL_GLOBAL_EXTRACTORS
    ]


class Neo4jAnalysisRunStore:
    """Durable AnalysisRun persistence backed by Neo4j."""

    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver

    async def start_run(self, run: AnalysisRun) -> AnalysisRunStartResult:
        async with self._driver.session() as session:
            return await session.execute_write(self._tx_start_run, run)

    @staticmethod
    async def _tx_start_run(
        tx: AsyncManagedTransaction,
        run: AnalysisRun,
    ) -> AnalysisRunStartResult:
        lock_result = await tx.run(
            ACQUIRE_ANALYSIS_LOCK,
            key=run.lock_key,
            created_at=run.created_at,
            touched_at=run.updated_at,
        )
        await lock_result.consume()
        existing_result = await tx.run(
            GET_ACTIVE_ANALYSIS_RUN,
            lock_key=run.lock_key,
            active_statuses=[status.value for status in ACTIVE_ANALYSIS_RUN_STATUSES],
        )
        existing_row = await existing_result.single()
        if existing_row is not None:
            existing_run_id = str(_node_to_dict(existing_row["r"])["run_id"])
            existing = await Neo4jAnalysisRunStore._read_run_tx(
                tx, existing_run_id, now=_parse_iso(run.updated_at) or _utc_now()
            )
            if existing.idempotency_key == run.idempotency_key:
                return AnalysisRunStartResult(run=existing, active_run_reused=True)
            raise ActiveAnalysisRunExistsError(existing.run_id)

        create_result = await tx.run(
            CREATE_ANALYSIS_RUN,
            run_id=run.run_id,
            lock_key=run.lock_key,
            slug=run.slug,
            project_name=run.project_name,
            parent_mount=run.parent_mount,
            relative_path=run.relative_path,
            language_profile=run.language_profile,
            bundle=run.bundle,
            extractors=run.extractors,
            depth=run.depth,
            requested_mode=run.requested_mode.value,
            effective_mode=run.effective_mode.value,
            effective_mode_reason=run.effective_mode_reason,
            stale_since_commit=run.stale_since_commit,
            changed_file_count=run.changed_file_count,
            changed_file_ratio=run.changed_file_ratio,
            continue_on_failure=run.continue_on_failure,
            idempotency_key=run.idempotency_key,
            status=run.status.value,
            created_at=run.created_at,
            updated_at=run.updated_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
            lease_owner=run.lease_owner,
            lease_expires_at=run.lease_expires_at,
            last_completed_extractor=run.last_completed_extractor,
            error_code=run.error_code,
            message=run.message,
            overview_json=_serialize_json(run.overview),
            audit_json=_serialize_json(run.audit),
            report_markdown=run.report_markdown,
            next_actions_json=_serialize_json(run.next_actions),
        )
        await create_result.consume()
        for checkpoint in run.checkpoints:
            checkpoint_result = await tx.run(
                UPSERT_ANALYSIS_CHECKPOINT,
                run_id=run.run_id,
                extractor=checkpoint.extractor,
                position=checkpoint.position,
                status=checkpoint.status.value,
                mode=checkpoint.mode.value if checkpoint.mode is not None else None,
                started_at=checkpoint.started_at,
                finished_at=checkpoint.finished_at,
                error_code=checkpoint.error_code,
                message=checkpoint.message,
                ingest_run_id=checkpoint.ingest_run_id,
                next_action=checkpoint.next_action,
            )
            await checkpoint_result.consume()
        return AnalysisRunStartResult(run=run, active_run_reused=False)

    async def get_run(
        self,
        run_id: str,
        *,
        now: datetime | None = None,
    ) -> AnalysisRun:
        async with self._driver.session() as session:
            return await session.execute_write(
                self._tx_get_run, run_id, now or _utc_now()
            )

    @staticmethod
    async def _tx_get_run(
        tx: AsyncManagedTransaction,
        run_id: str,
        now: datetime,
    ) -> AnalysisRun:
        return await Neo4jAnalysisRunStore._read_run_tx(tx, run_id, now=now)

    @staticmethod
    async def _read_run_tx(
        tx: AsyncManagedTransaction,
        run_id: str,
        *,
        now: datetime,
    ) -> AnalysisRun:
        result = await tx.run(GET_ANALYSIS_RUN_WITH_CHECKPOINTS, run_id=run_id)
        rows: list[dict[str, Any]] = []
        async for row in result:
            rows.append({"r": row["r"], "c": row["c"]})
        if not rows:
            raise AnalysisRunNotFoundError(run_id)

        run_node = _node_to_dict(rows[0]["r"])
        checkpoints = [
            _checkpoint_from_node(_node_to_dict(row["c"]))
            for row in rows
            if row["c"] is not None
        ]
        run = _run_from_node(run_node, checkpoints)
        if run.status == AnalysisRunStatus.RUNNING and (
            _lease_is_expired(run, now)
            or _run_is_stuck_before_first_checkpoint(run, now)
        ):
            resumable_result = await tx.run(
                MARK_ANALYSIS_RUN_RESUMABLE,
                run_id=run_id,
                status=AnalysisRunStatus.RESUMABLE.value,
                updated_at=_iso(now),
            )
            resumable_row = await resumable_result.single()
            if resumable_row is None:
                raise AnalysisRunNotFoundError(run_id)
            run = _run_from_node(_node_to_dict(resumable_row["r"]), checkpoints)
        return run

    async def acquire_lease(
        self,
        run_id: str,
        *,
        lease_owner: str,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> AnalysisRun:
        async with self._driver.session() as session:
            return await session.execute_write(
                self._tx_acquire_lease,
                run_id,
                lease_owner,
                lease_seconds,
                now or _utc_now(),
            )

    @staticmethod
    async def _tx_acquire_lease(
        tx: AsyncManagedTransaction,
        run_id: str,
        lease_owner: str,
        lease_seconds: int,
        now: datetime,
    ) -> AnalysisRun:
        run = await Neo4jAnalysisRunStore._read_run_tx(tx, run_id, now=now)
        if run.status in TERMINAL_ANALYSIS_RUN_STATUSES:
            return run
        if run.status == AnalysisRunStatus.RUNNING and not _lease_is_expired(run, now):
            raise AnalysisRunNotResumableError(run_id, "active lease still held")

        lease_expires_at = _iso(now + timedelta(seconds=lease_seconds))
        result = await tx.run(
            UPDATE_ANALYSIS_RUN_LEASE,
            run_id=run_id,
            status=AnalysisRunStatus.RUNNING.value,
            updated_at=_iso(now),
            lease_owner=lease_owner,
            lease_expires_at=lease_expires_at,
        )
        row = await result.single()
        if row is None:
            raise AnalysisRunNotFoundError(run_id)
        return run.model_copy(
            update={
                "status": AnalysisRunStatus.RUNNING,
                "updated_at": _iso(now),
                "lease_owner": lease_owner,
                "lease_expires_at": lease_expires_at,
            }
        )

    async def mark_run_resumable(
        self,
        run_id: str,
        *,
        now: datetime | None = None,
    ) -> AnalysisRun:
        async with self._driver.session() as session:
            return await session.execute_write(
                self._tx_mark_run_resumable,
                run_id,
                now or _utc_now(),
            )

    @staticmethod
    async def _tx_mark_run_resumable(
        tx: AsyncManagedTransaction,
        run_id: str,
        now: datetime,
    ) -> AnalysisRun:
        current = await Neo4jAnalysisRunStore._read_run_tx(tx, run_id, now=now)
        if current.status in TERMINAL_ANALYSIS_RUN_STATUSES:
            return current
        result = await tx.run(
            MARK_ANALYSIS_RUN_RESUMABLE,
            run_id=run_id,
            status=AnalysisRunStatus.RESUMABLE.value,
            updated_at=_iso(now),
        )
        row = await result.single()
        if row is None:
            raise AnalysisRunNotFoundError(run_id)
        return current.model_copy(
            update={
                "status": AnalysisRunStatus.RESUMABLE,
                "updated_at": _iso(now),
                "lease_owner": None,
                "lease_expires_at": None,
            }
        )

    async def save_checkpoint(
        self,
        run_id: str,
        checkpoint: AnalysisCheckpoint,
        *,
        updated_at: str,
        last_completed_extractor: str | None,
        status: AnalysisRunStatus,
        lease_owner: str | None,
        lease_expires_at: str | None,
    ) -> AnalysisRun:
        async with self._driver.session() as session:
            return await session.execute_write(
                self._tx_save_checkpoint,
                run_id,
                checkpoint,
                updated_at,
                last_completed_extractor,
                status,
                lease_owner,
                lease_expires_at,
            )

    @staticmethod
    async def _tx_save_checkpoint(
        tx: AsyncManagedTransaction,
        run_id: str,
        checkpoint: AnalysisCheckpoint,
        updated_at: str,
        last_completed_extractor: str | None,
        status: AnalysisRunStatus,
        lease_owner: str | None,
        lease_expires_at: str | None,
    ) -> AnalysisRun:
        await tx.run(
            UPSERT_ANALYSIS_CHECKPOINT,
            run_id=run_id,
            extractor=checkpoint.extractor,
            position=checkpoint.position,
            status=checkpoint.status.value,
            mode=checkpoint.mode.value if checkpoint.mode is not None else None,
            started_at=checkpoint.started_at,
            finished_at=checkpoint.finished_at,
            error_code=checkpoint.error_code,
            message=checkpoint.message,
            ingest_run_id=checkpoint.ingest_run_id,
            next_action=checkpoint.next_action,
        )
        await tx.run(
            UPDATE_ANALYSIS_RUN_PROGRESS,
            run_id=run_id,
            updated_at=updated_at,
            last_completed_extractor=last_completed_extractor,
            status=status.value,
            lease_owner=lease_owner,
            lease_expires_at=lease_expires_at,
        )
        return await Neo4jAnalysisRunStore._read_run_tx(
            tx,
            run_id,
            now=_parse_iso(updated_at) or _utc_now(),
        )

    async def finalize_run(
        self,
        run_id: str,
        *,
        status: AnalysisRunStatus,
        overview: dict[str, int],
        audit: dict[str, Any] | None,
        report_markdown: str | None,
        next_actions: list[str],
        error_code: str | None = None,
        message: str | None = None,
        now: datetime | None = None,
    ) -> AnalysisRun:
        async with self._driver.session() as session:
            return await session.execute_write(
                self._tx_finalize_run,
                run_id,
                status,
                overview,
                audit,
                report_markdown,
                next_actions,
                error_code,
                message,
                now or _utc_now(),
            )

    @staticmethod
    async def _tx_finalize_run(
        tx: AsyncManagedTransaction,
        run_id: str,
        status: AnalysisRunStatus,
        overview: dict[str, int],
        audit: dict[str, Any] | None,
        report_markdown: str | None,
        next_actions: list[str],
        error_code: str | None,
        message: str | None,
        now: datetime,
    ) -> AnalysisRun:
        result = await tx.run(
            FINALIZE_ANALYSIS_RUN,
            run_id=run_id,
            status=status.value,
            updated_at=_iso(now),
            finished_at=_iso(now),
            overview_json=_serialize_json(overview),
            audit_json=_serialize_json(audit),
            report_markdown=report_markdown,
            next_actions_json=_serialize_json(next_actions),
            error_code=error_code,
            message=message,
        )
        row = await result.single()
        if row is None:
            raise AnalysisRunNotFoundError(run_id)
        return await Neo4jAnalysisRunStore._read_run_tx(tx, run_id, now=now)


class ProjectAnalysisService:
    """Service-layer API for start/status/resume/execute orchestration."""

    def __init__(
        self,
        *,
        driver: AsyncDriver | None = None,
        store: AnalysisRunStore | None = None,
        extractor_registry: dict[str, BaseExtractor] | None = None,
        register_project_func: Callable[..., Awaitable[Any]] = register_project,
        register_bundle_func: Callable[..., Awaitable[Any]] = register_bundle,
        add_to_bundle_func: Callable[..., Awaitable[Any]] = add_to_bundle,
        audit_runner: AuditRunner = run_audit,
        ensure_schema_func: SchemaEnsurer = ensure_project_analyze_schema,
        lease_seconds: int = 900,
        lease_owner: str | None = None,
        clock: Clock = _utc_now,
        neo4j_retry_attempts: int = 3,
        neo4j_retry_initial_delay_seconds: float = 0.25,
    ) -> None:
        if store is None and driver is None:
            raise ValueError("driver is required when store is not provided")
        if neo4j_retry_attempts < 1:
            raise ValueError("neo4j_retry_attempts must be >= 1")
        if neo4j_retry_initial_delay_seconds < 0:
            raise ValueError("neo4j_retry_initial_delay_seconds must be >= 0")
        self._driver = driver
        if store is not None:
            self._store = store
        else:
            assert driver is not None
            self._store = Neo4jAnalysisRunStore(driver)
        self._extractor_registry = extractor_registry or {}
        self._register_project = register_project_func
        self._register_bundle = register_bundle_func
        self._add_to_bundle = add_to_bundle_func
        self._audit_runner = audit_runner
        self._ensure_schema = ensure_schema_func
        self._lease_seconds = lease_seconds
        self._lease_owner = lease_owner or f"project-analyze@{socket.gethostname()}"
        self._clock = clock
        self._neo4j_retry_attempts = neo4j_retry_attempts
        self._neo4j_retry_initial_delay_seconds = neo4j_retry_initial_delay_seconds

    def resolve_default_extractors(
        self,
        *,
        language_profile: str,
        extractors: Sequence[str] | None = None,
    ) -> tuple[str, ...]:
        if extractors is None:
            ordered = get_ordered_extractors(language_profile)
        else:
            if not extractors:
                raise ValueError("extractors must not be empty")
            seen: set[str] = set()
            deduped: list[str] = []
            for extractor_name in extractors:
                if extractor_name in seen:
                    raise ValueError(
                        f"duplicate extractor in request: {extractor_name!r}"
                    )
                seen.add(extractor_name)
                deduped.append(extractor_name)
            ordered = tuple(deduped)

        missing = [
            extractor_name
            for extractor_name in ordered
            if extractor_name not in self._extractor_registry
        ]
        if missing:
            raise ValueError(
                "extractor(s) missing from registry: " + ", ".join(sorted(missing))
            )
        return ordered

    async def start_run(
        self,
        *,
        slug: str,
        parent_mount: str,
        relative_path: str,
        language_profile: str,
        name: str | None = None,
        bundle: str | None = None,
        extractors: Sequence[str] | None = None,
        depth: str = "full",
        mode: AnalysisRunMode = AnalysisRunMode.FULL,
        continue_on_failure: bool = True,
        idempotency_key: str | None = None,
        force_new: bool = False,
    ) -> AnalysisRunStartResult:
        ordered_extractors = self.resolve_default_extractors(
            language_profile=language_profile,
            extractors=extractors,
        )
        project_name = name or slug
        driver = self._require_driver()
        await self._with_neo4j_retry(
            action="start_run.ensure_schema",
            operation=lambda: self._ensure_schema(driver),
        )
        await self._with_neo4j_retry(
            action="start_run.register_project",
            operation=lambda: self._register_project(
                driver,
                slug=slug,
                name=project_name,
                tags=[],
                parent_mount=parent_mount,
                relative_path=relative_path,
                language_profile=language_profile,
                expected_profile=slug in _EXPECTED_PROFILE_SLUGS,
            ),
        )
        if bundle is not None:
            await self._with_neo4j_retry(
                action="start_run.register_bundle",
                operation=lambda: self._register_bundle(
                    driver,
                    name=bundle,
                    description=f"project analyze bundle {bundle}",
                ),
            )
            await self._with_neo4j_retry(
                action="start_run.add_to_bundle",
                operation=lambda: self._add_to_bundle(
                    driver,
                    bundle=bundle,
                    project=slug,
                    tier=Tier.FIRST_PARTY,
                ),
            )

        (
            effective_mode,
            effective_mode_reason,
            stale_since_commit,
            changed_file_count,
            changed_file_ratio,
        ) = await _resolve_run_mode_plan(
            driver,
            slug=slug,
            requested_mode=mode,
        )
        checkpoints: list[AnalysisCheckpoint] = []
        for index, extractor_name in enumerate(ordered_extractors):
            checkpoint_mode = (
                ExtractorExecutionMode.FULL
                if effective_mode == AnalysisRunMode.FULL
                else (
                    ExtractorExecutionMode.SKIPPED
                    if extractor_name in _INCREMENTAL_GLOBAL_EXTRACTORS
                    else ExtractorExecutionMode.INCREMENTAL
                )
            )
            checkpoint = AnalysisCheckpoint(
                extractor=extractor_name,
                position=index,
                mode=checkpoint_mode,
            )
            if checkpoint_mode == ExtractorExecutionMode.SKIPPED:
                checkpoint = checkpoint.model_copy(
                    update={
                        "status": AnalysisCheckpointStatus.SKIPPED,
                        "message": (
                            f"Skipped {extractor_name} during incremental project_analyze; "
                            f"latest project-wide findings may be stale_since={stale_since_commit}."
                        ),
                        "next_action": (
                            f"Run a full project_analyze for {extractor_name} to refresh "
                            "project-wide audit results."
                        ),
                    }
                )
            checkpoints.append(checkpoint)

        now = self._clock()
        lease_expires_at = _iso(now + timedelta(seconds=self._lease_seconds))
        run = AnalysisRun(
            run_id=str(uuid4()),
            slug=slug,
            project_name=project_name,
            parent_mount=parent_mount,
            relative_path=relative_path,
            language_profile=language_profile,
            bundle=bundle,
            extractors=list(ordered_extractors),
            depth=depth,
            requested_mode=mode,
            effective_mode=effective_mode,
            effective_mode_reason=effective_mode_reason,
            stale_since_commit=stale_since_commit,
            changed_file_count=changed_file_count,
            changed_file_ratio=changed_file_ratio,
            continue_on_failure=continue_on_failure,
            idempotency_key=idempotency_key or str(uuid4()),
            status=AnalysisRunStatus.RUNNING,
            created_at=_iso(now),
            updated_at=_iso(now),
            started_at=_iso(now),
            lease_owner=self._lease_owner,
            lease_expires_at=lease_expires_at,
            error_code=None,
            message=None,
            checkpoints=checkpoints,
        )
        if force_new:
            run = run.model_copy(update={"idempotency_key": str(uuid4())})
        try:
            return await self._with_neo4j_retry(
                action="start_run",
                operation=lambda: self._store.start_run(run),
            )
        except ActiveAnalysisRunExistsError as exc:
            if not force_new:
                raise
            existing = await self.get_status(exc.run_id)
            replacement_time = self._clock()
            if not _run_can_be_force_replaced(existing, replacement_time):
                raise
            await self._cancel_run_for_force_new(existing)
            return await self._with_neo4j_retry(
                action="start_run.force_new_after_stuck_cancel",
                operation=lambda: self._store.start_run(run),
            )

    async def get_status(self, run_id: str) -> AnalysisRun:
        return await self._with_neo4j_retry(
            action="get_status",
            operation=lambda: self._store.get_run(run_id, now=self._clock()),
        )

    async def resume_run(self, run_id: str) -> AnalysisRun:
        return await self._with_neo4j_retry(
            action="resume_run",
            operation=lambda: self._store.acquire_lease(
                run_id,
                lease_owner=self._lease_owner,
                lease_seconds=self._lease_seconds,
                now=self._clock(),
            ),
        )

    async def mark_run_resumable(self, run_id: str) -> AnalysisRun:
        return await self._with_neo4j_retry(
            action="mark_run_resumable",
            operation=lambda: self._store.mark_run_resumable(run_id, now=self._clock()),
        )

    async def _cancel_run_for_force_new(self, run: AnalysisRun) -> AnalysisRun:
        audit_payload = {
            "ok": False,
            "error_code": "project_analyze_force_new_replaced_stuck_run",
            "message": "force_new replaced a stuck project analyze run before first checkpoint",
            "run_id": run.run_id,
        }
        canceled_run = run.model_copy(
            update={
                "status": AnalysisRunStatus.CANCELED,
                "error_code": "project_analyze_force_new_replaced_stuck_run",
                "message": audit_payload["message"],
            }
        )
        report_markdown = self._render_checkpoint_report(
            canceled_run,
            audit_payload,
            stale_external=False,
        )
        return await self._with_neo4j_retry(
            action="force_new.cancel_stuck_run",
            operation=lambda: self._store.finalize_run(
                run.run_id,
                status=AnalysisRunStatus.CANCELED,
                overview=_checkpoint_counts(run.checkpoints),
                audit=audit_payload,
                report_markdown=report_markdown,
                next_actions=[
                    "force_new started a replacement project analyze run after stuck-run recovery."
                ],
                error_code="project_analyze_force_new_replaced_stuck_run",
                message=str(audit_payload["message"]),
                now=self._clock(),
            ),
        )

    async def fail_run(
        self,
        run_id: str,
        *,
        error_code: str,
        message: str,
    ) -> AnalysisRun:
        run = await self._with_neo4j_retry(
            action="fail_run.get_run",
            operation=lambda: self._store.get_run(run_id, now=self._clock()),
        )
        overview = _checkpoint_counts(run.checkpoints)
        audit_payload = {
            "ok": False,
            "error_code": error_code,
            "message": message,
            "run_id": run_id,
        }
        failed_run = run.model_copy(
            update={
                "status": AnalysisRunStatus.FAILED,
                "error_code": error_code,
                "message": message,
            }
        )
        report_markdown = self._render_checkpoint_report(
            failed_run,
            audit_payload,
            stale_external=False,
        )
        return await self._with_neo4j_retry(
            action="fail_run.finalize_run",
            operation=lambda: self._store.finalize_run(
                run_id,
                status=AnalysisRunStatus.FAILED,
                overview=overview,
                audit=audit_payload,
                report_markdown=report_markdown,
                next_actions=[
                    "Inspect palace-mcp runtime failure, then start a fresh project analyze run."
                ],
                error_code=error_code,
                message=message,
                now=self._clock(),
            ),
        )

    @property
    def lease_owner(self) -> str:
        return self._lease_owner

    async def execute_run(
        self,
        run_id: str,
        *,
        graphiti: Graphiti | None = None,
        executor: ExtractorExecutor | None = None,
        reacquire_lease: bool = True,
        allow_interrupted_checkpoint_replay: bool = False,
    ) -> AnalysisRun:
        run = (
            await self.resume_run(run_id)
            if reacquire_lease
            else await self.get_status(run_id)
        )
        step_executor = executor or self._default_executor(graphiti)

        for checkpoint in run.checkpoints:
            if checkpoint.status != AnalysisCheckpointStatus.NOT_ATTEMPTED:
                continue
            if (
                _checkpoint_was_interrupted(checkpoint)
                and not allow_interrupted_checkpoint_replay
            ):
                return await self.fail_run(
                    run.run_id,
                    error_code="project_analyze_checkpoint_replayed",
                    message=(
                        f"checkpoint {checkpoint.extractor} was interrupted "
                        "before completion and would be replayed after restart; "
                        "failing closed instead of re-entering extractor work."
                    ),
                )

            checkpoint_started_at = self._clock()
            started_checkpoint = checkpoint.model_copy(
                update={
                    "started_at": _iso(checkpoint_started_at),
                    "finished_at": None,
                    "error_code": None,
                    "message": None,
                    "ingest_run_id": None,
                    "next_action": None,
                }
            )
            run = await self._with_neo4j_retry(
                action=f"save_checkpoint.started.{checkpoint.extractor}",
                operation=lambda: self._store.save_checkpoint(
                    run.run_id,
                    started_checkpoint,
                    updated_at=_iso(checkpoint_started_at),
                    last_completed_extractor=run.last_completed_extractor,
                    status=AnalysisRunStatus.RUNNING,
                    lease_owner=self._lease_owner,
                    lease_expires_at=_iso(
                        checkpoint_started_at + timedelta(seconds=self._lease_seconds)
                    ),
                ),
            )

            attempt = await step_executor(checkpoint.extractor, run)
            finished_at = _iso(self._clock())
            updated_checkpoint = started_checkpoint.model_copy(
                update={
                    "status": attempt.status,
                    "mode": attempt.mode,
                    "finished_at": finished_at,
                    "error_code": attempt.error_code,
                    "message": attempt.message,
                    "ingest_run_id": attempt.ingest_run_id,
                    "next_action": attempt.next_action,
                }
            )
            checkpoint_updated_at = self._clock()
            run = await self._with_neo4j_retry(
                action=f"save_checkpoint.finished.{checkpoint.extractor}",
                operation=lambda: self._store.save_checkpoint(
                    run.run_id,
                    updated_checkpoint,
                    updated_at=_iso(checkpoint_updated_at),
                    last_completed_extractor=updated_checkpoint.extractor,
                    status=AnalysisRunStatus.RUNNING,
                    lease_owner=self._lease_owner,
                    lease_expires_at=_iso(
                        checkpoint_updated_at + timedelta(seconds=self._lease_seconds)
                    ),
                ),
            )
            # F2: symbol_index success is the moment the project's authoritative
            # indexed commit becomes known — persist it (monotonic, best-effort).
            if (
                updated_checkpoint.extractor.startswith("symbol_index_")
                and attempt.status is AnalysisCheckpointStatus.OK
            ):
                await _record_project_indexed_commit(
                    self._require_driver(),
                    run.slug,
                    updated_checkpoint.extractor,
                    now_iso=_iso(checkpoint_updated_at),
                )
            if (
                attempt.status in FAILING_ANALYSIS_CHECKPOINT_STATUSES
                and not run.continue_on_failure
            ):
                break

        run = await self._with_neo4j_retry(
            action="execute_run.get_run",
            operation=lambda: self._store.get_run(run.run_id, now=self._clock()),
        )
        overview = _checkpoint_counts(run.checkpoints)
        all_non_failing = all(
            checkpoint.status in NON_FAILING_ANALYSIS_CHECKPOINT_STATUSES
            for checkpoint in run.checkpoints
        )
        checkpoint_next_actions = _checkpoint_next_actions(run.checkpoints)

        if all_non_failing:
            audit_payload = await self._run_audit(project=run.slug, depth=run.depth)
            audit_payload = self._augment_audit_payload(run, audit_payload)
            report_markdown = (
                audit_payload.get("report_markdown")
                if isinstance(audit_payload.get("report_markdown"), str)
                else self._render_checkpoint_report(
                    run,
                    audit_payload,
                    stale_external=False,
                )
            )
            if isinstance(report_markdown, str):
                report_markdown = self._decorate_report_markdown(report_markdown, run)
            if audit_payload.get("ok") is True:
                has_optional_gaps = any(
                    checkpoint.status
                    in {
                        AnalysisCheckpointStatus.SKIPPED,
                        AnalysisCheckpointStatus.MISSING_INPUT,
                    }
                    for checkpoint in run.checkpoints
                )
                final_status = (
                    AnalysisRunStatus.SUCCEEDED_WITH_SKIPS
                    if has_optional_gaps
                    else AnalysisRunStatus.SUCCEEDED
                )
                next_actions = checkpoint_next_actions
            else:
                final_status = AnalysisRunStatus.SUCCEEDED_WITH_FAILURES
                next_actions = checkpoint_next_actions or [
                    "Inspect audit payload and rerun project analyze if the audit output is incomplete."
                ]
        else:
            audit_payload = self._augment_audit_payload(
                run,
                self._build_stale_external_audit_payload(
                    run,
                    message=(
                        "Current AnalysisRun contains failed extractors; "
                        "latest-run audit fallback would break pinned provenance."
                    ),
                ),
            )
            final_status = AnalysisRunStatus.SUCCEEDED_WITH_FAILURES
            report_markdown = self._render_checkpoint_report(
                run,
                audit_payload,
                stale_external=True,
            )
            report_markdown = self._decorate_report_markdown(report_markdown, run)
            next_actions = checkpoint_next_actions or [
                "Resume the run after failed extractors are fixed to produce a fully pinned audit report."
            ]

        return await self._with_neo4j_retry(
            action="execute_run.finalize_run",
            operation=lambda: self._store.finalize_run(
                run.run_id,
                status=final_status,
                overview=overview,
                audit=audit_payload,
                report_markdown=report_markdown,
                next_actions=next_actions,
                error_code=None,
                message=None,
                now=self._clock(),
            ),
        )

    async def _with_neo4j_retry(
        self,
        *,
        action: str,
        operation: Callable[[], Awaitable[_T]],
    ) -> _T:
        delay_seconds = self._neo4j_retry_initial_delay_seconds
        for attempt in range(1, self._neo4j_retry_attempts + 1):
            try:
                return await operation()
            except (ServiceUnavailable, SessionExpired) as exc:
                if attempt >= self._neo4j_retry_attempts:
                    raise
                logger.warning(
                    "project_analyze.neo4j_retry",
                    extra={
                        "action": action,
                        "attempt": attempt,
                        "max_attempts": self._neo4j_retry_attempts,
                        "delay_seconds": delay_seconds,
                        "error": str(exc),
                    },
                )
                await asyncio.sleep(delay_seconds)
                delay_seconds *= 2
        raise AssertionError("unreachable: retry loop must return or raise")

    def _default_executor(self, graphiti: Graphiti | None) -> ExtractorExecutor:
        if graphiti is None:
            raise ValueError("graphiti is required when no custom executor is supplied")
        driver = self._require_driver()

        async def _execute(
            extractor_name: str,
            run: AnalysisRun,
        ) -> ExtractorAttemptResult:
            companion_run_id: str | None = None
            if extractor_name in {"prune_swift_symbols", "dead_code"}:
                symbol_index_checkpoint = next(
                    (
                        checkpoint
                        for checkpoint in run.checkpoints
                        if checkpoint.extractor == "symbol_index_swift"
                    ),
                    None,
                )
                checkpoint_valid = (
                    symbol_index_checkpoint is not None
                    and symbol_index_checkpoint.status
                    in {
                        AnalysisCheckpointStatus.OK,
                        AnalysisCheckpointStatus.SKIPPED,
                    }
                    and symbol_index_checkpoint.error_code is None
                    and symbol_index_checkpoint.ingest_run_id is not None
                )
                if extractor_name == "prune_swift_symbols" and not checkpoint_valid:
                    logger.warning(
                        "project_analyze.prune_skipped",
                        extra={
                            "run_id": run.run_id,
                            "project": run.slug,
                            "extractor": extractor_name,
                            "reason": "symbol_index_swift_not_ok",
                            "checkpoint_status": (
                                None
                                if symbol_index_checkpoint is None
                                else symbol_index_checkpoint.status.value
                            ),
                            "checkpoint_error_code": (
                                symbol_index_checkpoint.error_code
                                if symbol_index_checkpoint is not None
                                else None
                            ),
                        },
                    )
                    return ExtractorAttemptResult(
                        status=AnalysisCheckpointStatus.SKIPPED,
                        mode=ExtractorExecutionMode.SKIPPED,
                        message=(
                            "Skipped prune_swift_symbols because symbol_index_swift "
                            "did not complete successfully in this run."
                        ),
                        next_action=(
                            "Rerun symbol_index_swift successfully before prune_swift_symbols."
                        ),
                    )
                if checkpoint_valid:
                    assert symbol_index_checkpoint is not None
                    companion_run_id = symbol_index_checkpoint.ingest_run_id
            response = await run_extractor(
                driver=driver,
                graphiti=graphiti,
                name=extractor_name,
                project=run.slug,
                companion_run_id=companion_run_id,
            )
            if response.get("ok") is True:
                ingest_run_id = response.get("run_id")
                if not isinstance(ingest_run_id, str):
                    raise ValueError("extractor success response is missing run_id")
                outcome = str(response.get("outcome") or "ok")
                if outcome == "skipped":
                    status = AnalysisCheckpointStatus.SKIPPED
                elif outcome == "not_applicable":
                    status = AnalysisCheckpointStatus.SKIPPED
                elif outcome == "missing_input":
                    status = AnalysisCheckpointStatus.MISSING_INPUT
                else:
                    status = AnalysisCheckpointStatus.OK
                return ExtractorAttemptResult(
                    status=status,
                    mode=_response_mode_from_payload(response, status=status),
                    ingest_run_id=ingest_run_id,
                    message=(
                        response.get("message")
                        if isinstance(response.get("message"), str)
                        else None
                    ),
                    next_action=(
                        response.get("next_action")
                        if isinstance(response.get("next_action"), str)
                        else None
                    ),
                )
            maybe_run_id = response.get("run_id")
            return ExtractorAttemptResult(
                status=AnalysisCheckpointStatus.RUN_FAILED,
                mode=ExtractorExecutionMode.FULL,
                ingest_run_id=maybe_run_id if isinstance(maybe_run_id, str) else None,
                error_code=str(response.get("error_code") or "extractor_runtime_error"),
                message=str(response.get("message") or "extractor failed"),
                next_action=f"Repair {extractor_name} and call analyze_resume.",
            )

        return _execute

    async def _run_audit(self, *, project: str, depth: str) -> dict[str, Any]:
        return await self._audit_runner(
            self._require_driver(),
            self._extractor_registry,
            project=project,
            depth=depth,
        )

    def _augment_audit_payload(
        self,
        run: AnalysisRun,
        audit_payload: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(audit_payload)
        payload["requested_mode"] = run.requested_mode.value
        payload["effective_mode"] = run.effective_mode.value
        if run.effective_mode_reason is not None:
            payload["effective_mode_reason"] = run.effective_mode_reason
        if run.changed_file_count is not None:
            payload["changed_file_count"] = run.changed_file_count
        if run.changed_file_ratio is not None:
            payload["changed_file_ratio"] = run.changed_file_ratio
        payload["extractor_modes"] = {
            checkpoint.extractor: _checkpoint_mode_label(checkpoint)
            for checkpoint in run.checkpoints
        }
        stale_extractors = _stale_extractors(run)
        if stale_extractors and run.stale_since_commit is not None:
            payload["stale_since"] = run.stale_since_commit
            payload["stale_extractors"] = stale_extractors
        return payload

    def _decorate_report_markdown(self, report_markdown: str, run: AnalysisRun) -> str:
        lines = [
            report_markdown.rstrip(),
            "",
            "## Orchestration",
            f"- Requested mode: `{run.requested_mode.value}`",
            f"- Effective mode: `{run.effective_mode.value}`",
        ]
        if run.effective_mode_reason is not None:
            lines.append(f"- Mode reason: `{run.effective_mode_reason}`")
        if run.changed_file_count is not None:
            lines.append(f"- Changed files: `{run.changed_file_count}`")
        if run.changed_file_ratio is not None:
            lines.append(f"- Changed ratio: `{run.changed_file_ratio:.3f}`")
        stale_extractors = _stale_extractors(run)
        if stale_extractors and run.stale_since_commit is not None:
            extractors = ", ".join(f"`{name}`" for name in stale_extractors)
            lines.append(
                f"- Global audit results may be stale_since=`{run.stale_since_commit}` for {extractors}"
            )
        return "\n".join(lines) + "\n"

    def _build_stale_external_audit_payload(
        self,
        run: AnalysisRun,
        *,
        message: str,
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "error_code": "STALE_EXTERNAL_RUN",
            "message": message,
            "run_id": run.run_id,
            "checkpoint_run_ids": {
                checkpoint.extractor: checkpoint.ingest_run_id
                for checkpoint in run.checkpoints
                if checkpoint.ingest_run_id is not None
            },
        }

    def _require_driver(self) -> AsyncDriver:
        if self._driver is None:
            raise ValueError("driver is required for this operation")
        return self._driver

    def _render_checkpoint_report(
        self,
        run: AnalysisRun,
        audit_payload: dict[str, Any],
        *,
        stale_external: bool,
    ) -> str:
        lines = [
            f"# AnalysisRun {run.run_id}",
            "",
            f"- Project: `{run.slug}`",
            f"- Profile: `{run.language_profile}`",
            f"- Status: `{run.status.value}`",
            f"- Requested mode: `{run.requested_mode.value}`",
            f"- Effective mode: `{run.effective_mode.value}`",
            "",
            "## Checkpoints",
        ]
        if run.effective_mode_reason is not None:
            lines.insert(6, f"- Mode reason: `{run.effective_mode_reason}`")
        if run.stale_since_commit is not None and _stale_extractors(run):
            lines.insert(
                7 if run.effective_mode_reason is not None else 6,
                f"- stale_since=`{run.stale_since_commit}`",
            )
        for checkpoint in run.checkpoints:
            ingest_ref = checkpoint.ingest_run_id or "none"
            lines.append(
                f"- `{checkpoint.extractor}`: `{checkpoint.status.value}` "
                f"(mode={_checkpoint_mode_label(checkpoint)}, ingest_run_id={ingest_ref})"
            )
        if stale_external:
            lines.extend(
                [
                    "",
                    "## Audit",
                    "- `STALE_EXTERNAL_RUN`: latest-run fallback was not used because current checkpoint provenance is incomplete.",
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    "## Audit",
                    f"- Finalization error: `{audit_payload.get('error_code', 'unknown')}`",
                ]
            )
        return "\n".join(lines) + "\n"
