from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import pytest

from palace_mcp.extractors import registry
from palace_mcp.extractors.foundation.profiles import SWIFT_KIT_EXTRACTOR_ORDER
from palace_mcp.project_analyze import (
    ActiveAnalysisRunExistsError,
    AnalysisCheckpoint,
    AnalysisCheckpointStatus,
    AnalysisRun,
    AnalysisRunStartResult,
    AnalysisRunStatus,
    ExtractorAttemptResult,
    ProjectAnalysisService,
)


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
        if (
            run.status == AnalysisRunStatus.RUNNING
            and run.lease_expires_at is not None
            and datetime.fromisoformat(run.lease_expires_at) <= current
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
    )


async def _default_audit_runner(*args: object, **kwargs: object) -> dict[str, Any]:
    return {"ok": True, "report_markdown": "# audit\n"}


@pytest.mark.asyncio
async def test_service_start_run_ensures_schema_before_project_registration_and_store_start(
) -> None:
    events: list[str] = []

    async def fake_ensure_schema(driver: object, *, default_group_id: str) -> None:
        events.append(f"schema:{default_group_id}")

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
    ) -> None:
        events.append(f"register:{parent_mount}:{relative_path}:{language_profile}")

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
    assert events == [
        "schema:project/tron-kit",
        "register:hs:TronKit.Swift:swift_kit",
        "store:hs:TronKit.Swift",
    ]


def test_resolve_default_extractors_matches_swift_kit_contract() -> None:
    store = InMemoryAnalysisRunStore()
    service = _build_service(store=store)

    ordered = service.resolve_default_extractors(language_profile="swift_kit")

    assert ordered == SWIFT_KIT_EXTRACTOR_ORDER
    assert all(name in registry.EXTRACTORS for name in ordered)


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

    await service.resume_run(started.run.run_id)
    current_time[0] = current_time[0] + timedelta(seconds=30)

    restarted_service = _build_service(store=store, clock=_clock)
    run = await restarted_service.get_status(started.run.run_id)

    assert run.status == AnalysisRunStatus.RESUMABLE
    assert run.lease_owner is None
    assert run.lease_expires_at is None


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

    finished = await service.execute_run(started.run.run_id, executor=_executor)

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
async def test_execute_run_marks_success_path_stale_until_audit_supports_pinned_inputs() -> (
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

    finished = await service.execute_run(started.run.run_id, executor=_executor)

    assert finished.status == AnalysisRunStatus.SUCCEEDED_WITH_FAILURES
    assert finished.overview["OK"] == 2
    assert finished.audit is not None
    assert finished.audit["error_code"] == "STALE_EXTERNAL_RUN"
    assert "STALE_EXTERNAL_RUN" in (finished.report_markdown or "")
    assert audit_called is False


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

    finished = await service.execute_run(started.run.run_id, executor=_executor)

    assert len(store.saved_leases) == 2
    assert store.saved_leases[0] < store.saved_leases[1]
    assert finished.status == AnalysisRunStatus.SUCCEEDED_WITH_FAILURES


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

    finished = await service.execute_run(started.run.run_id, executor=_executor)

    assert seen == ["dependency_surface", "hotspot"]
    assert finished.status == AnalysisRunStatus.SUCCEEDED_WITH_FAILURES
    assert finished.audit is not None
    assert finished.audit["error_code"] == "STALE_EXTERNAL_RUN"
