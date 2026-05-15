from __future__ import annotations

import asyncio
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

import palace_mcp.mcp_server as mcp_module
from palace_mcp.mcp_server import _mcp
from palace_mcp.project_analyze import (
    ActiveAnalysisRunExistsError,
    AnalysisCheckpoint,
    AnalysisRun,
    AnalysisRunStartResult,
    AnalysisRunStatus,
)

_NOW = "2026-05-15T10:00:00+00:00"


@pytest.fixture(autouse=True)
def reset_project_analyze_state() -> object:
    original_driver = mcp_module._driver
    original_graphiti = mcp_module._graphiti
    original_tasks = dict(mcp_module._project_analysis_tasks)
    mcp_module._project_analysis_tasks.clear()
    yield
    mcp_module._driver = original_driver
    mcp_module._graphiti = original_graphiti
    mcp_module._project_analysis_tasks.clear()
    mcp_module._project_analysis_tasks.update(original_tasks)


def _make_run(
    *,
    run_id: str = "run-123",
    status: AnalysisRunStatus = AnalysisRunStatus.PENDING,
    language_profile: str = "swift_kit",
) -> AnalysisRun:
    return AnalysisRun(
        run_id=run_id,
        slug="tron-kit",
        project_name="TronKit",
        parent_mount="hs",
        relative_path="TronKit.Swift",
        language_profile=language_profile,
        bundle=None,
        extractors=["code_ownership", "hotspot"],
        depth="full",
        continue_on_failure=True,
        idempotency_key="idem-1",
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
        started_at=_NOW,
        finished_at=None,
        lease_owner=None,
        lease_expires_at=None,
        last_completed_extractor=None,
        checkpoints=[
            AnalysisCheckpoint(extractor="code_ownership", position=0),
            AnalysisCheckpoint(extractor="hotspot", position=1),
        ],
        overview={},
        audit=None,
        report_markdown=None,
        next_actions=[],
    )


async def test_project_analyze_tools_are_registered() -> None:
    tools = {tool.name for tool in await _mcp.list_tools()}
    assert "palace.project.analyze" in tools
    assert "palace.project.analyze_status" in tools
    assert "palace.project.analyze_resume" in tools


async def test_project_analyze_requires_arguments() -> None:
    with pytest.raises(ToolError):
        await _mcp.call_tool("palace.project.analyze", {})


async def test_project_analyze_returns_run_id_and_schedules_background_execution() -> (
    None
):
    run = _make_run(status=AnalysisRunStatus.RUNNING)
    service = MagicMock()
    service.start_run = AsyncMock(
        return_value=AnalysisRunStartResult(run=run, active_run_reused=False)
    )

    with (
        patch("palace_mcp.mcp_server._driver", new=MagicMock()),
        patch("palace_mcp.mcp_server._graphiti", new=object()),
        patch(
            "palace_mcp.mcp_server._build_project_analysis_service",
            return_value=service,
        ),
        patch(
            "palace_mcp.mcp_server._schedule_project_analysis_execution",
            return_value=True,
        ) as schedule_mock,
    ):
        _content, structured = await _mcp.call_tool(
            "palace.project.analyze",
            {
                "slug": "tron-kit",
                "parent_mount": "hs",
                "relative_path": "TronKit.Swift",
                "language_profile": "swift_kit",
                "idempotency_key": "idem-1",
            },
        )

    assert structured["ok"] is True
    assert structured["run_id"] == "run-123"
    assert structured["status"] == "RUNNING"
    assert structured["active_run_reused"] is False
    assert structured["background_execution_scheduled"] is True
    assert structured["run"]["language_profile"] == "swift_kit"
    schedule_mock.assert_called_once_with(
        run_id="run-123",
        service=service,
        reacquire_lease=False,
    )


async def test_project_analyze_reused_running_run_does_not_schedule_duplicate() -> None:
    run = _make_run(status=AnalysisRunStatus.RUNNING)
    service = MagicMock()
    service.start_run = AsyncMock(
        return_value=AnalysisRunStartResult(run=run, active_run_reused=True)
    )

    with (
        patch("palace_mcp.mcp_server._driver", new=MagicMock()),
        patch("palace_mcp.mcp_server._graphiti", new=object()),
        patch(
            "palace_mcp.mcp_server._build_project_analysis_service",
            return_value=service,
        ),
        patch(
            "palace_mcp.mcp_server._schedule_project_analysis_execution",
            return_value=True,
        ) as schedule_mock,
    ):
        _content, structured = await _mcp.call_tool(
            "palace.project.analyze",
            {
                "slug": "tron-kit",
                "parent_mount": "hs",
                "relative_path": "TronKit.Swift",
                "language_profile": "swift_kit",
                "idempotency_key": "idem-1",
            },
        )

    assert structured["ok"] is True
    assert structured["active_run_reused"] is True
    assert structured["background_execution_scheduled"] is False
    schedule_mock.assert_not_called()


async def test_project_analyze_reused_resumable_run_reacquires_lease() -> None:
    run = _make_run(status=AnalysisRunStatus.RESUMABLE)
    service = MagicMock()
    service.start_run = AsyncMock(
        return_value=AnalysisRunStartResult(run=run, active_run_reused=True)
    )

    with (
        patch("palace_mcp.mcp_server._driver", new=MagicMock()),
        patch("palace_mcp.mcp_server._graphiti", new=object()),
        patch(
            "palace_mcp.mcp_server._build_project_analysis_service",
            return_value=service,
        ),
        patch(
            "palace_mcp.mcp_server._schedule_project_analysis_execution",
            return_value=True,
        ) as schedule_mock,
    ):
        _content, structured = await _mcp.call_tool(
            "palace.project.analyze",
            {
                "slug": "tron-kit",
                "parent_mount": "hs",
                "relative_path": "TronKit.Swift",
                "language_profile": "swift_kit",
                "idempotency_key": "idem-1",
            },
        )

    assert structured["ok"] is True
    assert structured["status"] == "RESUMABLE"
    assert structured["active_run_reused"] is True
    assert structured["background_execution_scheduled"] is True
    schedule_mock.assert_called_once_with(
        run_id="run-123",
        service=service,
        reacquire_lease=True,
    )


async def test_project_analyze_conflict_returns_structured_error() -> None:
    service = MagicMock()
    service.start_run = AsyncMock(
        side_effect=ActiveAnalysisRunExistsError("run-existing")
    )

    with (
        patch("palace_mcp.mcp_server._driver", new=MagicMock()),
        patch("palace_mcp.mcp_server._graphiti", new=object()),
        patch(
            "palace_mcp.mcp_server._build_project_analysis_service",
            return_value=service,
        ),
    ):
        _content, structured = await _mcp.call_tool(
            "palace.project.analyze",
            {
                "slug": "tron-kit",
                "parent_mount": "hs",
                "relative_path": "TronKit.Swift",
                "language_profile": "swift_kit",
                "idempotency_key": "different-key",
            },
        )

    assert structured["ok"] is False
    assert structured["error_code"] == "ACTIVE_ANALYSIS_RUN_EXISTS"
    assert structured["run_id"] == "run-existing"


async def test_project_analyze_status_returns_durable_state() -> None:
    run = _make_run(status=AnalysisRunStatus.RESUMABLE)
    service = MagicMock()
    service.get_status = AsyncMock(return_value=run)

    with (
        patch("palace_mcp.mcp_server._driver", new=MagicMock()),
        patch(
            "palace_mcp.mcp_server._build_project_analysis_service",
            return_value=service,
        ),
    ):
        _content, structured = await _mcp.call_tool(
            "palace.project.analyze_status",
            {"run_id": "run-123"},
        )

    assert structured["ok"] is True
    assert structured["run_id"] == "run-123"
    assert structured["status"] == "RESUMABLE"
    assert structured["background_execution_scheduled"] is False


async def test_project_analyze_status_keeps_running_when_local_worker_is_alive() -> (
    None
):
    run = _make_run(status=AnalysisRunStatus.RESUMABLE)
    service = MagicMock()
    service.get_status = AsyncMock(return_value=run)
    blocker = asyncio.Event()
    task = asyncio.create_task(blocker.wait())
    mcp_module._project_analysis_tasks["run-123"] = task

    try:
        with (
            patch("palace_mcp.mcp_server._driver", new=MagicMock()),
            patch(
                "palace_mcp.mcp_server._build_project_analysis_service",
                return_value=service,
            ),
        ):
            _content, structured = await _mcp.call_tool(
                "palace.project.analyze_status",
                {"run_id": "run-123"},
            )
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    assert structured["ok"] is True
    assert structured["status"] == "RUNNING"
    assert structured["background_execution_scheduled"] is True
    service.get_status.assert_awaited_once_with("run-123")


async def test_project_analyze_status_promotes_orphaned_running_run_to_resumable() -> (
    None
):
    run = _make_run(status=AnalysisRunStatus.RUNNING).model_copy(
        update={
            "lease_owner": "project-analyze@test-host",
            "lease_expires_at": "2026-05-15T10:15:00+00:00",
        }
    )
    resumable = run.model_copy(
        update={
            "status": AnalysisRunStatus.RESUMABLE,
            "lease_owner": None,
            "lease_expires_at": None,
        }
    )
    service = MagicMock()
    service.get_status = AsyncMock(return_value=run)
    service.mark_run_resumable = AsyncMock(return_value=resumable)
    service.lease_owner = "project-analyze@test-host"

    with (
        patch("palace_mcp.mcp_server._driver", new=MagicMock()),
        patch(
            "palace_mcp.mcp_server._build_project_analysis_service",
            return_value=service,
        ),
    ):
        _content, structured = await _mcp.call_tool(
            "palace.project.analyze_status",
            {"run_id": "run-123"},
        )

    assert structured["ok"] is True
    assert structured["status"] == "RESUMABLE"
    assert structured["background_execution_scheduled"] is False
    service.get_status.assert_awaited_once_with("run-123")
    service.mark_run_resumable.assert_awaited_once_with("run-123")


async def test_project_analyze_resume_reacquires_lease_then_schedules_worker() -> None:
    run = _make_run(status=AnalysisRunStatus.RUNNING)
    service = MagicMock()
    service.resume_run = AsyncMock(return_value=run)

    with (
        patch("palace_mcp.mcp_server._driver", new=MagicMock()),
        patch("palace_mcp.mcp_server._graphiti", new=object()),
        patch(
            "palace_mcp.mcp_server._build_project_analysis_service",
            return_value=service,
        ),
        patch(
            "palace_mcp.mcp_server._schedule_project_analysis_execution",
            return_value=True,
        ) as schedule_mock,
    ):
        _content, structured = await _mcp.call_tool(
            "palace.project.analyze_resume",
            {"run_id": "run-123"},
        )

    assert structured["ok"] is True
    assert structured["run_id"] == "run-123"
    assert structured["status"] == "RUNNING"
    assert structured["background_execution_scheduled"] is True
    schedule_mock.assert_called_once_with(
        run_id="run-123",
        service=service,
        reacquire_lease=False,
    )


async def test_project_analyze_resume_does_not_duplicate_live_worker_after_lease_expiry() -> (
    None
):
    run = _make_run(status=AnalysisRunStatus.RESUMABLE)
    service = MagicMock()
    service.get_status = AsyncMock(return_value=run)
    service.resume_run = AsyncMock()
    blocker = asyncio.Event()
    task = asyncio.create_task(blocker.wait())
    mcp_module._project_analysis_tasks["run-123"] = task

    try:
        with (
            patch("palace_mcp.mcp_server._driver", new=MagicMock()),
            patch("palace_mcp.mcp_server._graphiti", new=object()),
            patch(
                "palace_mcp.mcp_server._build_project_analysis_service",
                return_value=service,
            ),
            patch(
                "palace_mcp.mcp_server._schedule_project_analysis_execution",
                return_value=True,
            ) as schedule_mock,
        ):
            _content, structured = await _mcp.call_tool(
                "palace.project.analyze_resume",
                {"run_id": "run-123"},
            )
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    assert structured["ok"] is True
    assert structured["status"] == "RUNNING"
    assert structured["background_execution_scheduled"] is True
    service.get_status.assert_awaited_once_with("run-123")
    service.resume_run.assert_not_called()
    schedule_mock.assert_not_called()
