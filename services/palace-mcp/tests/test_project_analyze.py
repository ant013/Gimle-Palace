from __future__ import annotations

import asyncio
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from unittest.mock import AsyncMock

import pytest
from neo4j.exceptions import ServiceUnavailable

from palace_mcp.extractors import registry
from palace_mcp.extractors.foundation.profiles import SWIFT_KIT_EXTRACTOR_ORDER
from palace_mcp.project_analyze import (
    ActiveAnalysisRunExistsError,
    AnalysisCheckpoint,
    AnalysisCheckpointStatus,
    AnalysisRunMode,
    AnalysisRun,
    AnalysisRunStartResult,
    AnalysisRunStatus,
    ExtractorAttemptResult,
    ExtractorExecutionMode,
    ProjectAnalysisService,
    _resolve_run_mode_plan,
)
from palace_mcp.memory.models import Tier


def _utc(
    year: int = 2026,
    month: int = 5,
    day: int = 14,
    hour: int = 12,
    minute: int = 0,
    second: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class InMemoryAnalysisRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, AnalysisRun] = {}
        self._lock = asyncio.Lock()

    async def start_run(self, run: AnalysisRun) -> AnalysisRunStartResult:
        async with self._lock:
            active = next(
                (
                    existing
                    for existing in self._runs.values()
                    if existing.lock_key == run.lock_key
                    and existing.status
                    in {
                        AnalysisRunStatus.PENDING,
                        AnalysisRunStatus.RUNNING,
                        AnalysisRunStatus.RESUMABLE,
                    }
                ),
                None,
            )
            if active is not None:
                if active.idempotency_key == run.idempotency_key:
                    return AnalysisRunStartResult(
                        run=active.model_copy(deep=True), active_run_reused=True
                    )
                raise ActiveAnalysisRunExistsError(active.run_id)
            self._runs[run.run_id] = run.model_copy(deep=True)
            return AnalysisRunStartResult(
                run=run.model_copy(deep=True), active_run_reused=False
            )

    async def get_run(
        self,
        run_id: str,
        *,
        now: datetime | None = None,
    ) -> AnalysisRun:
        run = self._require(run_id)
        current = now or _utc()
        lease_expired = (
            run.lease_expires_at is not None
            and datetime.fromisoformat(run.lease_expires_at) <= current
        )
        null_lease_before_first_checkpoint = run.lease_expires_at is None and all(
            checkpoint.status == AnalysisCheckpointStatus.NOT_ATTEMPTED
            and checkpoint.started_at is None
            and checkpoint.finished_at is None
            for checkpoint in run.checkpoints
        )
        if run.status == AnalysisRunStatus.RUNNING and (
            lease_expired or null_lease_before_first_checkpoint
        ):
            run = run.model_copy(
                update={
                    "status": AnalysisRunStatus.RESUMABLE,
                    "updated_at": _iso(current),
                    "lease_owner": None,
                    "lease_expires_at": None,
                }
            )
            self._runs[run_id] = run
        return run.model_copy(deep=True)

    async def acquire_lease(
        self,
        run_id: str,
        *,
        lease_owner: str,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> AnalysisRun:
        current = now or _utc()
        run = await self.get_run(run_id, now=current)
        if run.status in {
            AnalysisRunStatus.SUCCEEDED,
            AnalysisRunStatus.SUCCEEDED_WITH_SKIPS,
            AnalysisRunStatus.SUCCEEDED_WITH_FAILURES,
            AnalysisRunStatus.FAILED,
            AnalysisRunStatus.CANCELED,
        }:
            return run
        lease_expires_at = _iso(current + timedelta(seconds=lease_seconds))
        updated = run.model_copy(
            update={
                "status": AnalysisRunStatus.RUNNING,
                "updated_at": _iso(current),
                "lease_owner": lease_owner,
                "lease_expires_at": lease_expires_at,
            }
        )
        self._runs[run_id] = updated
        return updated.model_copy(deep=True)

    async def mark_run_resumable(
        self,
        run_id: str,
        *,
        now: datetime | None = None,
    ) -> AnalysisRun:
        current = now or _utc()
        run = self._require(run_id)
        if run.status in {
            AnalysisRunStatus.SUCCEEDED,
            AnalysisRunStatus.SUCCEEDED_WITH_SKIPS,
            AnalysisRunStatus.SUCCEEDED_WITH_FAILURES,
            AnalysisRunStatus.FAILED,
            AnalysisRunStatus.CANCELED,
        }:
            return run.model_copy(deep=True)
        updated = run.model_copy(
            update={
                "status": AnalysisRunStatus.RESUMABLE,
                "updated_at": _iso(current),
                "lease_owner": None,
                "lease_expires_at": None,
            }
        )
        self._runs[run_id] = updated
        return updated.model_copy(deep=True)

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
        run = self._require(run_id)
        checkpoints = [
            checkpoint if item.extractor == checkpoint.extractor else item
            for item in run.checkpoints
        ]
        updated = run.model_copy(
            update={
                "status": status,
                "updated_at": updated_at,
                "lease_owner": lease_owner,
                "lease_expires_at": lease_expires_at,
                "last_completed_extractor": last_completed_extractor,
                "checkpoints": checkpoints,
            }
        )
        self._runs[run_id] = updated
        return updated.model_copy(deep=True)

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
        current = now or _utc()
        run = self._require(run_id)
        updated = run.model_copy(
            update={
                "status": status,
                "updated_at": _iso(current),
                "finished_at": _iso(current),
                "lease_owner": None,
                "lease_expires_at": None,
                "error_code": error_code,
                "message": message,
                "overview": overview,
                "audit": audit,
                "report_markdown": report_markdown,
                "next_actions": next_actions,
            }
        )
        self._runs[run_id] = updated
        return updated.model_copy(deep=True)

    def _require(self, run_id: str) -> AnalysisRun:
        if run_id not in self._runs:
            raise AssertionError(f"missing run {run_id}")
        return self._runs[run_id]


async def _register_noop(*args: object, **kwargs: object) -> None:
    return None


def _build_service(
    *,
    store: InMemoryAnalysisRunStore,
    clock: Callable[[], datetime] | None = None,
    audit_runner: Any | None = None,
    neo4j_retry_attempts: int = 3,
    neo4j_retry_initial_delay_seconds: float = 0,
) -> ProjectAnalysisService:
    return ProjectAnalysisService(
        driver=object(),  # runtime-only dependency is stubbed in unit tests
        store=store,
        extractor_registry=registry.EXTRACTORS,
        register_project_func=_register_noop,
        register_bundle_func=_register_noop,
        add_to_bundle_func=_register_noop,
        audit_runner=audit_runner or _default_audit_runner,
        ensure_schema_func=_register_noop,
        lease_seconds=10,
        lease_owner="pytest",
        clock=clock or _utc,
        neo4j_retry_attempts=neo4j_retry_attempts,
        neo4j_retry_initial_delay_seconds=neo4j_retry_initial_delay_seconds,
    )


async def _default_audit_runner(*args: object, **kwargs: object) -> dict[str, Any]:
    return {"ok": True, "report_markdown": "# audit\n"}


@pytest.mark.asyncio
async def test_service_start_run_ensures_schema_before_project_registration_and_store_start() -> (
    None
):
    events: list[str] = []

    async def fake_ensure_schema(driver: object) -> None:
        events.append("schema")

    class RecordingStore(InMemoryAnalysisRunStore):
        async def start_run(self, run: AnalysisRun) -> AnalysisRunStartResult:
            events.append(f"store:{run.parent_mount}:{run.relative_path}")
            return await super().start_run(run)

    async def register_project(
        driver: object,
        *,
        slug: str,
        name: str,
        tags: list[str],
        parent_mount: str,
        relative_path: str,
        language_profile: str,
        expected_profile: bool,
    ) -> None:
        events.append(
            f"register:{parent_mount}:{relative_path}:{language_profile}:{expected_profile}"
        )

    service = ProjectAnalysisService(
        driver=object(),  # runtime-only dependency is stubbed in unit tests
        store=RecordingStore(),
        extractor_registry=registry.EXTRACTORS,
        register_project_func=register_project,
        register_bundle_func=_register_noop,
        add_to_bundle_func=_register_noop,
        audit_runner=_default_audit_runner,
        ensure_schema_func=fake_ensure_schema,
        lease_seconds=10,
        lease_owner="pytest",
        clock=_utc,
    )

    result = await service.start_run(
        slug="tron-kit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        idempotency_key="idem-1",
    )

    assert result.active_run_reused is False
    assert result.run.status == AnalysisRunStatus.RUNNING
    assert result.run.lease_owner == "pytest"
    assert result.run.lease_expires_at is not None
    assert events == [
        "schema",
        "register:hs:TronKit.Swift:swift_kit:False",
        "store:hs:TronKit.Swift",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("slug", "expected_profile"),
    [("uw-ios-app", True), ("uw-ios-baseline", True), ("tron-kit", False)],
)
async def test_start_run_marks_projects_with_expected_profiles(
    slug: str, expected_profile: bool
) -> None:
    captured: list[bool] = []

    async def register_project(
        driver: object,
        *,
        slug: str,
        name: str,
        tags: list[str],
        parent_mount: str,
        relative_path: str,
        language_profile: str,
        expected_profile: bool,
    ) -> None:
        captured.append(expected_profile)

    service = ProjectAnalysisService(
        driver=object(),
        store=InMemoryAnalysisRunStore(),
        extractor_registry=registry.EXTRACTORS,
        register_project_func=register_project,
        register_bundle_func=_register_noop,
        add_to_bundle_func=_register_noop,
        audit_runner=_default_audit_runner,
        ensure_schema_func=_register_noop,
        lease_seconds=10,
        lease_owner="pytest",
        clock=_utc,
    )

    await service.start_run(
        slug=slug,
        parent_mount="hs",
        relative_path="Project.Swift",
        language_profile="swift_kit",
        extractors=["symbol_index_swift"],
        idempotency_key=f"expected-profile-{slug}",
    )

    assert captured == [expected_profile]


def test_resolve_default_extractors_matches_swift_kit_contract() -> None:
    store = InMemoryAnalysisRunStore()
    service = _build_service(store=store)

    ordered = service.resolve_default_extractors(language_profile="swift_kit")

    assert ordered == SWIFT_KIT_EXTRACTOR_ORDER
    assert all(name in registry.EXTRACTORS for name in ordered)


@pytest.mark.asyncio
async def test_resolve_run_mode_plan_uses_incremental_when_detect_changes_is_small(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "palace_mcp.project_analyze._read_project_head_sha",
        AsyncMock(return_value="head-123"),
    )
    monkeypatch.setattr(
        "palace_mcp.project_analyze._read_project_indexed_commit",
        AsyncMock(return_value="2026-06-20T12:00:00Z"),
    )
    monkeypatch.setattr(
        "palace_mcp.project_analyze.native_detect_changes",
        AsyncMock(
            return_value={
                "ok": True,
                "files": ["Sources/A.swift", "Sources/B.swift"],
                "truncated": False,
            }
        ),
    )
    monkeypatch.setattr(
        "palace_mcp.project_analyze._count_project_files",
        AsyncMock(return_value=10),
    )

    plan = await _resolve_run_mode_plan(
        object(),
        slug="tron-kit",
        requested_mode=AnalysisRunMode.INCREMENTAL,
    )

    assert plan == (
        AnalysisRunMode.INCREMENTAL,
        "requested_incremental",
        "head-123",
        2,
        0.2,
    )


@pytest.mark.asyncio
async def test_resolve_run_mode_plan_falls_back_to_full_when_detect_changes_truncated(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "palace_mcp.project_analyze._read_project_head_sha",
        AsyncMock(return_value="head-123"),
    )
    monkeypatch.setattr(
        "palace_mcp.project_analyze._read_project_indexed_commit",
        AsyncMock(return_value="2026-06-20T12:00:00Z"),
    )
    monkeypatch.setattr(
        "palace_mcp.project_analyze.native_detect_changes",
        AsyncMock(
            return_value={
                "ok": True,
                "files": [f"Sources/{index}.swift" for index in range(600)],
                "truncated": True,
            }
        ),
    )

    plan = await _resolve_run_mode_plan(
        object(),
        slug="tron-kit",
        requested_mode=AnalysisRunMode.INCREMENTAL,
    )

    assert plan == (
        AnalysisRunMode.FULL,
        "detect_changes_truncated",
        "head-123",
        None,
        None,
    )


@pytest.mark.asyncio
async def test_resolve_run_mode_plan_falls_back_to_full_for_large_committed_delta(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "tron-kit"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], cwd=repo)
    _git(["config", "user.email", "t@t"], cwd=repo)
    _git(["config", "user.name", "T"], cwd=repo)
    for index in range(10):
        (repo / f"File{index}.swift").write_text(f"v1-{index}\n")
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "initial", "-q"], cwd=repo)
    base_sha = _git(["rev-parse", "HEAD"], cwd=repo)
    for index in range(9):
        (repo / f"File{index}.swift").write_text(f"v2-{index}\n")
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "update", "-q"], cwd=repo)
    head_sha = _git(["rev-parse", "HEAD"], cwd=repo)

    monkeypatch.setattr(
        "palace_mcp.project_analyze._read_project_head_sha",
        AsyncMock(return_value=head_sha),
    )
    monkeypatch.setattr(
        "palace_mcp.project_analyze._read_project_indexed_commit",
        AsyncMock(return_value=base_sha),
    )
    monkeypatch.setattr(
        "palace_mcp.code.native_detect_changes._resolve_repo_path",
        AsyncMock(return_value=repo),
    )
    monkeypatch.setattr(
        "palace_mcp.project_analyze._count_project_files",
        AsyncMock(return_value=10),
    )

    plan = await _resolve_run_mode_plan(
        object(),
        slug="tron-kit",
        requested_mode=AnalysisRunMode.INCREMENTAL,
    )

    assert plan == (
        AnalysisRunMode.FULL,
        "change_threshold_exceeded",
        head_sha,
        9,
        0.9,
    )


@pytest.mark.asyncio
async def test_start_run_incremental_mode_skips_global_extractors_and_stamps_stale_since(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "palace_mcp.project_analyze._resolve_run_mode_plan",
        AsyncMock(
            return_value=(
                AnalysisRunMode.INCREMENTAL,
                "requested_incremental",
                "head-abc",
                3,
                0.3,
            )
        ),
    )
    store = InMemoryAnalysisRunStore()
    service = _build_service(store=store)

    started = await service.start_run(
        slug="tron-kit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        extractors=["code_ownership", "hotspot", "cross_module_contract"],
        mode=AnalysisRunMode.INCREMENTAL,
        idempotency_key="incremental-plan",
    )

    assert started.run.requested_mode == AnalysisRunMode.INCREMENTAL
    assert started.run.effective_mode == AnalysisRunMode.INCREMENTAL
    assert started.run.stale_since_commit == "head-abc"
    assert [checkpoint.mode for checkpoint in started.run.checkpoints] == [
        ExtractorExecutionMode.INCREMENTAL,
        ExtractorExecutionMode.SKIPPED,
        ExtractorExecutionMode.SKIPPED,
    ]
    assert [checkpoint.status for checkpoint in started.run.checkpoints] == [
        AnalysisCheckpointStatus.NOT_ATTEMPTED,
        AnalysisCheckpointStatus.SKIPPED,
        AnalysisCheckpointStatus.SKIPPED,
    ]
    assert "stale_since=head-abc" in (started.run.checkpoints[1].message or "")


@pytest.mark.asyncio
async def test_start_run_incremental_mode_isolated_per_project(monkeypatch) -> None:
    async def _fake_plan(
        _driver: object, *, slug: str, requested_mode: AnalysisRunMode
    ) -> tuple[AnalysisRunMode, str | None, str | None, int | None, float | None]:
        assert requested_mode == AnalysisRunMode.INCREMENTAL
        if slug == "tron-kit":
            return (
                AnalysisRunMode.INCREMENTAL,
                "requested_incremental",
                "head-tron",
                1,
                0.1,
            )
        return (
            AnalysisRunMode.FULL,
            "change_threshold_exceeded",
            "head-gimle",
            9,
            0.9,
        )

    monkeypatch.setattr("palace_mcp.project_analyze._resolve_run_mode_plan", _fake_plan)
    service = _build_service(store=InMemoryAnalysisRunStore())

    tron = await service.start_run(
        slug="tron-kit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        extractors=["code_ownership", "hotspot"],
        mode=AnalysisRunMode.INCREMENTAL,
        idempotency_key="tron-plan",
    )
    gimle = await service.start_run(
        slug="gimle",
        parent_mount="hs",
        relative_path="Gimle",
        language_profile="python_service",
        extractors=["code_ownership", "hotspot"],
        mode=AnalysisRunMode.INCREMENTAL,
        idempotency_key="gimle-plan",
    )

    assert tron.run.effective_mode == AnalysisRunMode.INCREMENTAL
    assert tron.run.stale_since_commit == "head-tron"
    assert tron.run.checkpoints[1].status == AnalysisCheckpointStatus.SKIPPED
    assert gimle.run.effective_mode == AnalysisRunMode.FULL
    assert gimle.run.stale_since_commit == "head-gimle"
    assert all(
        checkpoint.status == AnalysisCheckpointStatus.NOT_ATTEMPTED
        for checkpoint in gimle.run.checkpoints
    )


@pytest.mark.asyncio
async def test_default_executor_passes_symbol_index_run_id_to_prune(
    monkeypatch,
) -> None:
    store = InMemoryAnalysisRunStore()
    service = _build_service(store=store)
    started = await service.start_run(
        slug="tron-kit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        extractors=["symbol_index_swift", "prune_swift_symbols"],
        idempotency_key="prune-companion-run",
    )
    symbol_checkpoint = started.run.checkpoints[0].model_copy(
        update={
            "status": AnalysisCheckpointStatus.OK,
            "ingest_run_id": "symbol-run-123",
        }
    )
    run = started.run.model_copy(
        update={"checkpoints": [symbol_checkpoint, started.run.checkpoints[1]]}
    )
    recorded: dict[str, object] = {}

    async def _fake_run_extractor(**kwargs: object) -> dict[str, object]:
        recorded.update(kwargs)
        return {
            "ok": True,
            "run_id": "prune-run-456",
            "outcome": "ok",
        }

    monkeypatch.setattr("palace_mcp.project_analyze.run_extractor", _fake_run_extractor)

    executor = service._default_executor(graphiti=object())
    attempt = await executor("prune_swift_symbols", run)

    assert attempt.status == AnalysisCheckpointStatus.OK
    assert attempt.ingest_run_id == "prune-run-456"
    assert recorded["companion_run_id"] == "symbol-run-123"


@pytest.mark.asyncio
async def test_default_executor_passes_skipped_symbol_index_run_id_to_prune(
    monkeypatch,
) -> None:
    store = InMemoryAnalysisRunStore()
    service = _build_service(store=store)
    started = await service.start_run(
        slug="tron-kit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        extractors=["symbol_index_swift", "prune_swift_symbols"],
        idempotency_key="prune-gated",
    )
    symbol_checkpoint = started.run.checkpoints[0].model_copy(
        update={
            "status": AnalysisCheckpointStatus.SKIPPED,
            "ingest_run_id": "symbol-run-123",
        }
    )
    run = started.run.model_copy(
        update={"checkpoints": [symbol_checkpoint, started.run.checkpoints[1]]}
    )
    recorded: dict[str, object] = {}

    async def _fake_run_extractor(**kwargs: object) -> dict[str, object]:
        recorded.update(kwargs)
        return {
            "ok": True,
            "run_id": "prune-run-456",
            "outcome": "ok",
        }

    monkeypatch.setattr("palace_mcp.project_analyze.run_extractor", _fake_run_extractor)

    executor = service._default_executor(graphiti=object())
    attempt = await executor("prune_swift_symbols", run)

    assert attempt.status == AnalysisCheckpointStatus.OK
    assert attempt.ingest_run_id == "prune-run-456"
    assert recorded["companion_run_id"] == "symbol-run-123"


@pytest.mark.asyncio
async def test_default_executor_skips_prune_when_symbol_index_skip_has_no_run_id() -> (
    None
):
    store = InMemoryAnalysisRunStore()
    service = _build_service(store=store)
    started = await service.start_run(
        slug="tron-kit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        extractors=["symbol_index_swift", "prune_swift_symbols"],
        idempotency_key="prune-gated",
    )
    symbol_checkpoint = started.run.checkpoints[0].model_copy(
        update={
            "status": AnalysisCheckpointStatus.SKIPPED,
            "ingest_run_id": None,
        }
    )
    run = started.run.model_copy(
        update={"checkpoints": [symbol_checkpoint, started.run.checkpoints[1]]}
    )

    executor = service._default_executor(graphiti=object())
    attempt = await executor("prune_swift_symbols", run)

    assert attempt.status == AnalysisCheckpointStatus.SKIPPED
    assert attempt.ingest_run_id is None
    assert attempt.message is not None
    assert "symbol_index_swift" in attempt.message


@pytest.mark.asyncio
async def test_default_executor_skips_prune_when_symbol_index_has_error_code() -> None:
    store = InMemoryAnalysisRunStore()
    service = _build_service(store=store)
    started = await service.start_run(
        slug="tron-kit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        extractors=["symbol_index_swift", "prune_swift_symbols"],
        idempotency_key="prune-gated-error",
    )
    symbol_checkpoint = started.run.checkpoints[0].model_copy(
        update={
            "status": AnalysisCheckpointStatus.OK,
            "ingest_run_id": "symbol-run-123",
            "error_code": "fatal_index_error",
        }
    )
    run = started.run.model_copy(
        update={"checkpoints": [symbol_checkpoint, started.run.checkpoints[1]]}
    )

    executor = service._default_executor(graphiti=object())
    attempt = await executor("prune_swift_symbols", run)

    assert attempt.status == AnalysisCheckpointStatus.SKIPPED
    assert attempt.ingest_run_id is None
    assert attempt.message is not None
    assert "did not complete successfully" in attempt.message


@pytest.mark.asyncio
async def test_concurrent_start_reuses_same_active_run_for_same_idempotency_key() -> (
    None
):
    store = InMemoryAnalysisRunStore()
    service = _build_service(store=store)

    async def _start() -> AnalysisRunStartResult:
        return await service.start_run(
            slug="tron-kit",
            parent_mount="hs",
            relative_path="TronKit.Swift",
            language_profile="swift_kit",
            idempotency_key="same-key",
        )

    first, second = await asyncio.gather(_start(), _start())

    assert first.run.run_id == second.run.run_id
    assert {first.active_run_reused, second.active_run_reused} == {False, True}


@pytest.mark.asyncio
async def test_start_rejects_different_active_run_for_same_slug_and_profile() -> None:
    store = InMemoryAnalysisRunStore()
    service = _build_service(store=store)

    await service.start_run(
        slug="tron-kit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        idempotency_key="first-key",
    )

    with pytest.raises(ActiveAnalysisRunExistsError):
        await service.start_run(
            slug="tron-kit",
            parent_mount="hs",
            relative_path="TronKit.Swift",
            language_profile="swift_kit",
            idempotency_key="second-key",
        )


@pytest.mark.asyncio
async def test_status_turns_expired_running_lease_into_resumable_after_restart() -> (
    None
):
    store = InMemoryAnalysisRunStore()
    current_time = [_utc()]

    def _clock() -> datetime:
        return current_time[0]

    service = _build_service(store=store, clock=_clock)
    started = await service.start_run(
        slug="tron-kit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        idempotency_key="lease-key",
    )

    current_time[0] = current_time[0] + timedelta(seconds=30)

    restarted_service = _build_service(store=store, clock=_clock)
    run = await restarted_service.get_status(started.run.run_id)

    assert run.status == AnalysisRunStatus.RESUMABLE
    assert run.lease_owner is None
    assert run.lease_expires_at is None


@pytest.mark.asyncio
async def test_status_turns_null_lease_unstarted_running_run_into_resumable() -> None:
    store = InMemoryAnalysisRunStore()
    service = _build_service(store=store)
    started = await service.start_run(
        slug="tron-kit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        idempotency_key="null-lease-key",
    )
    store._runs[started.run.run_id] = started.run.model_copy(
        update={"lease_owner": None, "lease_expires_at": None}
    )

    run = await service.get_status(started.run.run_id)

    assert run.status == AnalysisRunStatus.RESUMABLE
    assert run.lease_owner is None
    assert run.lease_expires_at is None


@pytest.mark.asyncio
async def test_resume_reacquires_null_lease_unstarted_running_run() -> None:
    store = InMemoryAnalysisRunStore()
    service = _build_service(store=store)
    started = await service.start_run(
        slug="tron-kit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        idempotency_key="resume-null-lease-key",
    )
    store._runs[started.run.run_id] = started.run.model_copy(
        update={"lease_owner": None, "lease_expires_at": None}
    )

    run = await service.resume_run(started.run.run_id)

    assert run.status == AnalysisRunStatus.RUNNING
    assert run.lease_owner == "pytest"
    assert run.lease_expires_at is not None


@pytest.mark.asyncio
async def test_force_new_cancels_stuck_active_run_and_starts_replacement() -> None:
    store = InMemoryAnalysisRunStore()
    service = _build_service(store=store)
    started = await service.start_run(
        slug="tron-kit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        idempotency_key="stuck-active-key",
    )
    store._runs[started.run.run_id] = started.run.model_copy(
        update={"lease_owner": None, "lease_expires_at": None}
    )

    replacement = await service.start_run(
        slug="tron-kit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        idempotency_key="replacement-key",
        force_new=True,
    )

    old = await store.get_run(started.run.run_id)
    assert old.status == AnalysisRunStatus.CANCELED
    assert old.error_code == "project_analyze_force_new_replaced_stuck_run"
    assert replacement.run.run_id != started.run.run_id
    assert replacement.run.status == AnalysisRunStatus.RUNNING
    assert replacement.active_run_reused is False


@pytest.mark.asyncio
async def test_mark_run_resumable_clears_live_lease_before_expiry() -> None:
    store = InMemoryAnalysisRunStore()
    service = _build_service(store=store)
    started = await service.start_run(
        slug="tron-kit",
        parent_mount="hs-stage",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        idempotency_key="orphaned-run",
    )

    run = await service.mark_run_resumable(started.run.run_id)

    assert run.status == AnalysisRunStatus.RESUMABLE
    assert run.lease_owner is None
    assert run.lease_expires_at is None


@pytest.mark.asyncio
async def test_fail_run_finalizes_terminal_failure_with_error_code() -> None:
    store = InMemoryAnalysisRunStore()
    service = _build_service(store=store)
    started = await service.start_run(
        slug="tron-kit",
        parent_mount="hs-stage",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        extractors=["symbol_index_swift"],
        idempotency_key="fail-run",
    )

    failed = await service.fail_run(
        started.run.run_id,
        error_code="project_analyze_runtime_error",
        message="RuntimeError: neo4j connection dropped",
    )

    assert failed.status == AnalysisRunStatus.FAILED
    assert failed.error_code == "project_analyze_runtime_error"
    assert failed.message == "RuntimeError: neo4j connection dropped"
    assert failed.audit is not None
    assert failed.audit["error_code"] == "project_analyze_runtime_error"


@pytest.mark.asyncio
async def test_execute_run_continues_after_failure_and_marks_stale_external_run() -> (
    None
):
    store = InMemoryAnalysisRunStore()
    audit_called = False

    async def _audit_runner(*args: object, **kwargs: object) -> dict[str, Any]:
        nonlocal audit_called
        audit_called = True
        return {"ok": True, "report_markdown": "# unexpected\n"}

    service = _build_service(store=store, audit_runner=_audit_runner)
    started = await service.start_run(
        slug="gimle",
        parent_mount="hs",
        relative_path="Gimle",
        language_profile="python_service",
        extractors=["code_ownership", "hotspot", "dependency_surface"],
        idempotency_key="failure-path",
    )

    outcomes = {
        "code_ownership": ExtractorAttemptResult(
            status=AnalysisCheckpointStatus.OK,
            ingest_run_id="run-1",
        ),
        "hotspot": ExtractorAttemptResult(
            status=AnalysisCheckpointStatus.RUN_FAILED,
            error_code="boom",
            message="hotspot failed",
        ),
        "dependency_surface": ExtractorAttemptResult(
            status=AnalysisCheckpointStatus.OK,
            ingest_run_id="run-3",
        ),
    }

    async def _executor(
        extractor_name: str,
        run: AnalysisRun,
    ) -> ExtractorAttemptResult:
        return outcomes[extractor_name]

    finished = await service.execute_run(
        started.run.run_id,
        executor=_executor,
        reacquire_lease=False,
    )

    assert finished.status == AnalysisRunStatus.SUCCEEDED_WITH_FAILURES
    assert [checkpoint.status for checkpoint in finished.checkpoints] == [
        AnalysisCheckpointStatus.OK,
        AnalysisCheckpointStatus.RUN_FAILED,
        AnalysisCheckpointStatus.OK,
    ]
    assert finished.audit is not None
    assert finished.audit["error_code"] == "STALE_EXTERNAL_RUN"
    assert "STALE_EXTERNAL_RUN" in (finished.report_markdown or "")
    assert audit_called is False


@pytest.mark.asyncio
async def test_execute_run_resume_keeps_git_history_failure_without_replay_error() -> (
    None
):
    store = InMemoryAnalysisRunStore()
    current_time = [_utc()]

    def _clock() -> datetime:
        return current_time[0]

    service = _build_service(store=store, clock=_clock)
    started = await service.start_run(
        slug="gimle",
        parent_mount="hs",
        relative_path="Gimle",
        language_profile="python_service",
        extractors=["git_history", "code_ownership", "hotspot"],
        idempotency_key="git-history-prereq",
    )

    git_history_checkpoint = started.run.checkpoints[0].model_copy(
        update={
            "status": AnalysisCheckpointStatus.OK,
            "started_at": _iso(current_time[0]),
            "finished_at": _iso(current_time[0] + timedelta(seconds=1)),
            "ingest_run_id": "ingest-git-history",
        }
    )
    await store.save_checkpoint(
        started.run.run_id,
        git_history_checkpoint,
        updated_at=git_history_checkpoint.finished_at or _iso(current_time[0]),
        last_completed_extractor=git_history_checkpoint.extractor,
        status=AnalysisRunStatus.RUNNING,
        lease_owner="pytest",
        lease_expires_at=_iso(current_time[0] + timedelta(seconds=10)),
    )

    code_ownership_checkpoint = started.run.checkpoints[1].model_copy(
        update={
            "status": AnalysisCheckpointStatus.RUN_FAILED,
            "started_at": _iso(current_time[0] + timedelta(seconds=2)),
            "finished_at": _iso(current_time[0] + timedelta(seconds=3)),
            "error_code": "git_history_not_indexed",
            "message": "no :Commit nodes found; run git_history first",
        }
    )
    await store.save_checkpoint(
        started.run.run_id,
        code_ownership_checkpoint,
        updated_at=code_ownership_checkpoint.finished_at or _iso(current_time[0]),
        last_completed_extractor=code_ownership_checkpoint.extractor,
        status=AnalysisRunStatus.RUNNING,
        lease_owner="pytest",
        lease_expires_at=_iso(current_time[0] + timedelta(seconds=12)),
    )

    seen: list[str] = []

    async def _executor(
        extractor_name: str,
        run: AnalysisRun,
    ) -> ExtractorAttemptResult:
        seen.append(extractor_name)
        return ExtractorAttemptResult(
            status=AnalysisCheckpointStatus.OK,
            ingest_run_id=f"ingest-{extractor_name}",
        )

    finished = await service.execute_run(
        started.run.run_id,
        executor=_executor,
        reacquire_lease=False,
    )

    failed_checkpoint = next(
        checkpoint
        for checkpoint in finished.checkpoints
        if checkpoint.extractor == "code_ownership"
    )

    assert seen == ["hotspot"]
    assert finished.status == AnalysisRunStatus.SUCCEEDED_WITH_FAILURES
    assert finished.error_code is None
    assert failed_checkpoint.status == AnalysisCheckpointStatus.RUN_FAILED
    assert failed_checkpoint.error_code == "git_history_not_indexed"
    assert finished.report_markdown is not None
    assert "project_analyze_checkpoint_replayed" not in finished.report_markdown


@pytest.mark.asyncio
async def test_execute_run_marks_success_path_succeeded_and_records_audit_payload() -> (
    None
):
    store = InMemoryAnalysisRunStore()
    audit_called = False

    async def _audit_runner(*args: object, **kwargs: object) -> dict[str, Any]:
        nonlocal audit_called
        audit_called = True
        return {"ok": True, "report_markdown": "# unexpected\n"}

    service = _build_service(store=store, audit_runner=_audit_runner)
    started = await service.start_run(
        slug="gimle",
        parent_mount="hs",
        relative_path="Gimle",
        language_profile="python_service",
        extractors=["code_ownership", "hotspot"],
        depth="quick",
        idempotency_key="success-path",
    )

    async def _executor(
        extractor_name: str,
        run: AnalysisRun,
    ) -> ExtractorAttemptResult:
        return ExtractorAttemptResult(
            status=AnalysisCheckpointStatus.OK,
            ingest_run_id=f"ingest-{extractor_name}",
        )

    finished = await service.execute_run(
        started.run.run_id,
        executor=_executor,
        reacquire_lease=False,
    )

    assert finished.status == AnalysisRunStatus.SUCCEEDED
    assert finished.overview["OK"] == 2
    assert finished.audit is not None
    assert finished.audit["ok"] is True
    assert finished.report_markdown is not None
    assert finished.report_markdown.startswith("# unexpected\n")
    assert audit_called is True


@pytest.mark.asyncio
async def test_execute_run_records_extractor_modes_and_stale_since_in_report(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "palace_mcp.project_analyze._resolve_run_mode_plan",
        AsyncMock(
            return_value=(
                AnalysisRunMode.INCREMENTAL,
                "requested_incremental",
                "head-xyz",
                2,
                0.2,
            )
        ),
    )
    store = InMemoryAnalysisRunStore()

    async def _audit_runner(*args: object, **kwargs: object) -> dict[str, Any]:
        return {"ok": True, "report_markdown": "# audit\n"}

    service = _build_service(store=store, audit_runner=_audit_runner)
    started = await service.start_run(
        slug="tron-kit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        extractors=["code_ownership", "hotspot"],
        mode=AnalysisRunMode.INCREMENTAL,
        idempotency_key="incremental-report",
    )

    async def _executor(
        extractor_name: str,
        run: AnalysisRun,
    ) -> ExtractorAttemptResult:
        assert extractor_name == "code_ownership"
        return ExtractorAttemptResult(
            status=AnalysisCheckpointStatus.OK,
            mode=ExtractorExecutionMode.INCREMENTAL,
            ingest_run_id="ingest-code-ownership",
        )

    finished = await service.execute_run(
        started.run.run_id,
        executor=_executor,
        reacquire_lease=False,
    )

    assert finished.audit is not None
    assert finished.audit["effective_mode"] == "incremental"
    assert finished.audit["extractor_modes"] == {
        "code_ownership": "incremental",
        "hotspot": "skipped",
    }
    assert finished.audit["stale_since"] == "head-xyz"
    assert finished.report_markdown is not None
    assert "Requested mode: `incremental`" in finished.report_markdown
    assert "stale_since=`head-xyz`" in finished.report_markdown


@pytest.mark.asyncio
async def test_execute_run_marks_optional_missing_inputs_as_succeeded_with_skips() -> (
    None
):
    store = InMemoryAnalysisRunStore()
    audit_called = False

    async def _audit_runner(*args: object, **kwargs: object) -> dict[str, Any]:
        nonlocal audit_called
        audit_called = True
        return {"ok": True, "report_markdown": "# audit with skips\n"}

    service = _build_service(store=store, audit_runner=_audit_runner)
    started = await service.start_run(
        slug="tron-kit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        extractors=["public_api_surface", "cross_module_contract", "hot_path_profiler"],
        depth="full",
        idempotency_key="optional-missing-inputs",
    )

    outcomes = {
        "public_api_surface": ExtractorAttemptResult(
            status=AnalysisCheckpointStatus.MISSING_INPUT,
            ingest_run_id="run-public-api",
            message="No public API artifacts found under .palace/public-api/...",
            next_action="Commit public API snapshots under .palace/public-api/.",
        ),
        "cross_module_contract": ExtractorAttemptResult(
            status=AnalysisCheckpointStatus.SKIPPED,
            ingest_run_id="run-contracts",
            message="No PublicApiSurface/PublicApiSymbol rows found for the current commit.",
            next_action="Rerun public_api_surface before cross_module_contract.",
        ),
        "hot_path_profiler": ExtractorAttemptResult(
            status=AnalysisCheckpointStatus.MISSING_INPUT,
            ingest_run_id="run-hot-path",
            message="profiles directory not found under repo root.",
            next_action="Commit runtime traces under profiles/.",
        ),
    }

    async def _executor(
        extractor_name: str,
        run: AnalysisRun,
    ) -> ExtractorAttemptResult:
        return outcomes[extractor_name]

    finished = await service.execute_run(
        started.run.run_id,
        executor=_executor,
        reacquire_lease=False,
    )

    assert finished.status == AnalysisRunStatus.SUCCEEDED_WITH_SKIPS
    assert finished.overview["MISSING_INPUT"] == 2
    assert finished.overview["SKIPPED"] == 1
    assert finished.audit is not None
    assert finished.audit["ok"] is True
    assert finished.report_markdown is not None
    assert finished.report_markdown.startswith("# audit with skips\n")
    assert finished.next_actions == [
        "Commit public API snapshots under .palace/public-api/.",
        "Rerun public_api_surface before cross_module_contract.",
        "Commit runtime traces under profiles/.",
    ]
    assert audit_called is True


@pytest.mark.asyncio
async def test_execute_run_renews_lease_while_checkpointing() -> None:
    class RecordingAnalysisRunStore(InMemoryAnalysisRunStore):
        def __init__(self) -> None:
            super().__init__()
            self.saved_leases: list[str] = []

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
            assert lease_owner == "pytest"
            assert lease_expires_at is not None
            self.saved_leases.append(lease_expires_at)
            return await super().save_checkpoint(
                run_id,
                checkpoint,
                updated_at=updated_at,
                last_completed_extractor=last_completed_extractor,
                status=status,
                lease_owner=lease_owner,
                lease_expires_at=lease_expires_at,
            )

    store = RecordingAnalysisRunStore()
    current_time = [_utc()]

    def _clock() -> datetime:
        return current_time[0]

    service = _build_service(store=store, clock=_clock)
    started = await service.start_run(
        slug="gimle",
        parent_mount="hs",
        relative_path="Gimle",
        language_profile="python_service",
        extractors=["code_ownership", "dependency_surface"],
        idempotency_key="lease-renewal",
    )

    async def _executor(
        extractor_name: str,
        run: AnalysisRun,
    ) -> ExtractorAttemptResult:
        current_time[0] = current_time[0] + timedelta(seconds=8)
        return ExtractorAttemptResult(
            status=AnalysisCheckpointStatus.OK,
            ingest_run_id=f"ingest-{extractor_name}",
        )

    finished = await service.execute_run(
        started.run.run_id,
        executor=_executor,
        reacquire_lease=False,
    )

    assert len(store.saved_leases) == 4
    assert store.saved_leases[0] < store.saved_leases[-1]
    assert finished.status == AnalysisRunStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_resume_continues_after_last_completed_extractor() -> None:
    store = InMemoryAnalysisRunStore()
    current_time = [_utc()]

    def _clock() -> datetime:
        return current_time[0]

    service = _build_service(store=store, clock=_clock)
    started = await service.start_run(
        slug="gimle",
        parent_mount="hs",
        relative_path="Gimle",
        language_profile="python_service",
        extractors=["code_ownership", "dependency_surface", "hotspot"],
        idempotency_key="resume-path",
    )

    first_checkpoint = started.run.checkpoints[0].model_copy(
        update={
            "status": AnalysisCheckpointStatus.OK,
            "started_at": _iso(current_time[0]),
            "finished_at": _iso(current_time[0] + timedelta(seconds=1)),
            "ingest_run_id": "ingest-code-ownership",
        }
    )
    await store.save_checkpoint(
        started.run.run_id,
        first_checkpoint,
        updated_at=first_checkpoint.finished_at or _iso(current_time[0]),
        last_completed_extractor=first_checkpoint.extractor,
        status=AnalysisRunStatus.RUNNING,
        lease_owner="pytest",
        lease_expires_at=_iso(current_time[0] + timedelta(seconds=10)),
    )

    seen: list[str] = []

    async def _executor(
        extractor_name: str,
        run: AnalysisRun,
    ) -> ExtractorAttemptResult:
        seen.append(extractor_name)
        return ExtractorAttemptResult(
            status=AnalysisCheckpointStatus.OK,
            ingest_run_id=f"ingest-{extractor_name}",
        )

    finished = await service.execute_run(
        started.run.run_id,
        executor=_executor,
        reacquire_lease=False,
    )

    assert seen == ["dependency_surface", "hotspot"]
    assert finished.status == AnalysisRunStatus.SUCCEEDED
    assert finished.audit is not None
    assert finished.audit["ok"] is True


@pytest.mark.asyncio
async def test_execute_run_fail_closes_interrupted_checkpoint_instead_of_replaying() -> (
    None
):
    store = InMemoryAnalysisRunStore()
    current_time = [_utc()]

    def _clock() -> datetime:
        return current_time[0]

    service = _build_service(store=store, clock=_clock)
    started = await service.start_run(
        slug="gimle",
        parent_mount="hs",
        relative_path="Gimle",
        language_profile="python_service",
        extractors=["dependency_surface", "error_handling_policy", "hotspot"],
        idempotency_key="interrupted-checkpoint",
    )

    completed_checkpoint = started.run.checkpoints[0].model_copy(
        update={
            "status": AnalysisCheckpointStatus.OK,
            "started_at": _iso(current_time[0]),
            "finished_at": _iso(current_time[0] + timedelta(seconds=1)),
            "ingest_run_id": "ingest-dependency-surface",
        }
    )
    await store.save_checkpoint(
        started.run.run_id,
        completed_checkpoint,
        updated_at=completed_checkpoint.finished_at or _iso(current_time[0]),
        last_completed_extractor=completed_checkpoint.extractor,
        status=AnalysisRunStatus.RUNNING,
        lease_owner="pytest",
        lease_expires_at=_iso(current_time[0] + timedelta(seconds=10)),
    )

    interrupted_checkpoint = started.run.checkpoints[1].model_copy(
        update={
            "started_at": _iso(current_time[0] + timedelta(seconds=2)),
            "finished_at": None,
        }
    )
    await store.save_checkpoint(
        started.run.run_id,
        interrupted_checkpoint,
        updated_at=interrupted_checkpoint.started_at or _iso(current_time[0]),
        last_completed_extractor=completed_checkpoint.extractor,
        status=AnalysisRunStatus.RUNNING,
        lease_owner="pytest",
        lease_expires_at=_iso(current_time[0] + timedelta(seconds=12)),
    )

    seen: list[str] = []

    async def _executor(
        extractor_name: str,
        run: AnalysisRun,
    ) -> ExtractorAttemptResult:
        seen.append(extractor_name)
        return ExtractorAttemptResult(
            status=AnalysisCheckpointStatus.OK,
            ingest_run_id=f"ingest-{extractor_name}",
        )

    finished = await service.execute_run(
        started.run.run_id,
        executor=_executor,
        reacquire_lease=False,
    )

    assert seen == []
    assert finished.status == AnalysisRunStatus.FAILED
    assert finished.error_code == "project_analyze_checkpoint_replayed"
    assert finished.message is not None
    assert "error_handling_policy" in finished.message
    assert finished.report_markdown is not None
    assert "project_analyze_checkpoint_replayed" in finished.report_markdown


@pytest.mark.asyncio
async def test_execute_run_resume_replays_interrupted_checkpoint_when_allowed() -> None:
    store = InMemoryAnalysisRunStore()
    current_time = [_utc()]

    def _clock() -> datetime:
        return current_time[0]

    service = _build_service(store=store, clock=_clock)
    started = await service.start_run(
        slug="gimle",
        parent_mount="hs",
        relative_path="Gimle",
        language_profile="python_service",
        extractors=["dependency_surface", "error_handling_policy", "hotspot"],
        idempotency_key="resume-interrupted-checkpoint",
    )

    completed_checkpoint = started.run.checkpoints[0].model_copy(
        update={
            "status": AnalysisCheckpointStatus.OK,
            "started_at": _iso(current_time[0]),
            "finished_at": _iso(current_time[0] + timedelta(seconds=1)),
            "ingest_run_id": "ingest-dependency-surface",
        }
    )
    await store.save_checkpoint(
        started.run.run_id,
        completed_checkpoint,
        updated_at=completed_checkpoint.finished_at or _iso(current_time[0]),
        last_completed_extractor=completed_checkpoint.extractor,
        status=AnalysisRunStatus.RUNNING,
        lease_owner="pytest",
        lease_expires_at=_iso(current_time[0] + timedelta(seconds=10)),
    )

    interrupted_checkpoint = started.run.checkpoints[1].model_copy(
        update={
            "started_at": _iso(current_time[0] + timedelta(seconds=2)),
            "finished_at": None,
        }
    )
    await store.save_checkpoint(
        started.run.run_id,
        interrupted_checkpoint,
        updated_at=interrupted_checkpoint.started_at or _iso(current_time[0]),
        last_completed_extractor=completed_checkpoint.extractor,
        status=AnalysisRunStatus.RESUMABLE,
        lease_owner=None,
        lease_expires_at=None,
    )

    await service.resume_run(started.run.run_id)

    seen: list[str] = []

    async def _executor(
        extractor_name: str,
        run: AnalysisRun,
    ) -> ExtractorAttemptResult:
        seen.append(extractor_name)
        return ExtractorAttemptResult(
            status=AnalysisCheckpointStatus.OK,
            ingest_run_id=f"ingest-{extractor_name}",
        )

    finished = await service.execute_run(
        started.run.run_id,
        executor=_executor,
        reacquire_lease=False,
        allow_interrupted_checkpoint_replay=True,
    )

    assert seen == ["error_handling_policy", "hotspot"]
    assert finished.status == AnalysisRunStatus.SUCCEEDED
    assert finished.error_code is None
    assert finished.report_markdown is not None
    assert "project_analyze_checkpoint_replayed" not in finished.report_markdown


@pytest.mark.asyncio
async def test_execute_run_retries_transient_neo4j_failure_during_finalization() -> (
    None
):
    class FlakyFinalizeStore(InMemoryAnalysisRunStore):
        def __init__(self) -> None:
            super().__init__()
            self.finalize_attempts = 0

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
            self.finalize_attempts += 1
            if self.finalize_attempts == 1:
                raise ServiceUnavailable(
                    "Failed to read from defunct connection Address(host='neo4j', port=7687)"
                )
            return await super().finalize_run(
                run_id,
                status=status,
                overview=overview,
                audit=audit,
                report_markdown=report_markdown,
                next_actions=next_actions,
                error_code=error_code,
                message=message,
                now=now,
            )

    store = FlakyFinalizeStore()
    service = _build_service(
        store=store,
        neo4j_retry_attempts=2,
        neo4j_retry_initial_delay_seconds=0,
    )
    started = await service.start_run(
        slug="tron-kit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        extractors=["crypto_domain_model"],
        idempotency_key="flaky-finalize",
    )

    async def _executor(
        extractor_name: str,
        run: AnalysisRun,
    ) -> ExtractorAttemptResult:
        assert extractor_name == "crypto_domain_model"
        assert run.slug == "tron-kit"
        return ExtractorAttemptResult(
            status=AnalysisCheckpointStatus.OK,
            ingest_run_id="ingest-crypto-domain-model",
        )

    finished = await service.execute_run(
        started.run.run_id,
        executor=_executor,
        reacquire_lease=False,
    )

    assert store.finalize_attempts == 2
    assert finished.status == AnalysisRunStatus.SUCCEEDED
    assert finished.error_code is None
    assert finished.report_markdown is not None
    assert "project_analyze_runtime_error" not in finished.report_markdown


@pytest.mark.asyncio
async def test_start_run_retries_transient_neo4j_failures_during_bootstrap() -> None:
    attempts = {
        "ensure_schema": 0,
        "register_project": 0,
        "register_bundle": 0,
        "add_to_bundle": 0,
    }
    events: list[str] = []

    async def flaky_ensure_schema(driver: object) -> None:
        attempts["ensure_schema"] += 1
        events.append(f"ensure_schema:{attempts['ensure_schema']}")
        if attempts["ensure_schema"] == 1:
            raise ServiceUnavailable("neo4j warming up during schema bootstrap")

    async def flaky_register_project(
        driver: object,
        *,
        slug: str,
        name: str,
        tags: list[str],
        parent_mount: str,
        relative_path: str,
        language_profile: str,
        expected_profile: bool,
    ) -> None:
        attempts["register_project"] += 1
        events.append(f"register_project:{attempts['register_project']}")
        if attempts["register_project"] == 1:
            raise ServiceUnavailable("neo4j warming up during project registration")
        assert slug == "tron-kit"
        assert name == "tron-kit"
        assert tags == []
        assert parent_mount == "hs-stage"
        assert relative_path == "TronKit.Swift"
        assert language_profile == "swift_kit"
        assert expected_profile is False

    async def flaky_register_bundle(
        driver: object,
        *,
        name: str,
        description: str,
    ) -> None:
        attempts["register_bundle"] += 1
        events.append(f"register_bundle:{attempts['register_bundle']}")
        if attempts["register_bundle"] == 1:
            raise ServiceUnavailable("neo4j warming up during bundle registration")
        assert name == "uw-ios"
        assert description == "project analyze bundle uw-ios"

    async def flaky_add_to_bundle(
        driver: object,
        *,
        bundle: str,
        project: str,
        tier: Tier,
    ) -> None:
        attempts["add_to_bundle"] += 1
        events.append(f"add_to_bundle:{attempts['add_to_bundle']}")
        if attempts["add_to_bundle"] == 1:
            raise ServiceUnavailable("neo4j warming up during bundle linkage")
        assert bundle == "uw-ios"
        assert project == "tron-kit"
        assert tier == Tier.FIRST_PARTY

    service = ProjectAnalysisService(
        driver=object(),  # runtime-only dependency is stubbed in unit tests
        store=InMemoryAnalysisRunStore(),
        extractor_registry=registry.EXTRACTORS,
        register_project_func=flaky_register_project,
        register_bundle_func=flaky_register_bundle,
        add_to_bundle_func=flaky_add_to_bundle,
        audit_runner=_default_audit_runner,
        ensure_schema_func=flaky_ensure_schema,
        lease_seconds=10,
        lease_owner="pytest",
        clock=_utc,
        neo4j_retry_attempts=2,
        neo4j_retry_initial_delay_seconds=0,
    )

    started = await service.start_run(
        slug="tron-kit",
        parent_mount="hs-stage",
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
        bundle="uw-ios",
        extractors=["symbol_index_swift", "code_ownership"],
        idempotency_key="bootstrap-retry",
    )

    assert started.active_run_reused is False
    assert started.run.status == AnalysisRunStatus.RUNNING
    assert attempts == {
        "ensure_schema": 2,
        "register_project": 2,
        "register_bundle": 2,
        "add_to_bundle": 2,
    }
    assert events == [
        "ensure_schema:1",
        "ensure_schema:2",
        "register_project:1",
        "register_project:2",
        "register_bundle:1",
        "register_bundle:2",
        "add_to_bundle:1",
        "add_to_bundle:2",
    ]
