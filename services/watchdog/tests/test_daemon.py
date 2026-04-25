"""Tests for watchdog.daemon — tick orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gimle_watchdog import daemon
from gimle_watchdog.actions import RespawnResult
from gimle_watchdog.config import (
    CompanyConfig,
    Config,
    CooldownsConfig,
    DaemonConfig,
    EscalationConfig,
    LoggingConfig,
    PaperclipConfig,
    Thresholds,
)
from gimle_watchdog.paperclip import Issue
from gimle_watchdog.state import State


def _cfg(tmp_path: Path) -> Config:
    return Config(
        version=1,
        paperclip=PaperclipConfig(base_url="http://x", api_key="k"),
        companies=[
            CompanyConfig(
                id="9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64",
                name="gimle",
                thresholds=Thresholds(
                    died_min=3,
                    hang_etime_min=60,
                    hang_cpu_max_s=None,
                    idle_cpu_ratio_max=0.005,
                    hang_stream_idle_max_s=300,
                ),
            )
        ],
        daemon=DaemonConfig(poll_interval_seconds=120),
        cooldowns=CooldownsConfig(
            per_issue_seconds=300, per_agent_cap=3, per_agent_window_seconds=900
        ),
        logging=LoggingConfig(
            path=tmp_path / "x.log", level="INFO", rotate_max_bytes=1048576, rotate_backup_count=1
        ),
        escalation=EscalationConfig(post_comment_on_issue=True, comment_marker="<!-- m -->"),
    )


def _stuck_issue() -> Issue:
    return Issue(
        id="issue-1",
        assignee_agent_id="agent-1",
        execution_run_id=None,
        status="in_progress",
        updated_at=datetime(2026, 4, 21, 9, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_tick_wakes_stuck_issue(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.list_in_progress_issues = AsyncMock(return_value=[_stuck_issue()])
    with patch(
        "gimle_watchdog.daemon.actions.trigger_respawn",
        new=AsyncMock(return_value=RespawnResult(via="patch", success=True, run_id="run-new")),
    ):
        with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
            with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
                await daemon._tick(cfg, state, client)
    assert state.is_issue_in_cooldown("issue-1", cfg.cooldowns.per_issue_seconds)


@pytest.mark.asyncio
async def test_tick_escalates_capped_agent(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    from freezegun import freeze_time

    for ts in ["2026-04-21T09:55:00Z", "2026-04-21T09:57:00Z", "2026-04-21T09:58:00Z"]:
        with freeze_time(ts):
            state.record_wake(f"dummy-{ts}", "agent-1")
    client = MagicMock()
    client.list_in_progress_issues = AsyncMock(return_value=[_stuck_issue()])
    client.post_issue_comment = AsyncMock()
    with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
        with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
            with freeze_time("2026-04-21T10:05:00Z"):
                await daemon._tick(cfg, state, client)
    assert state.is_escalated("issue-1")
    client.post_issue_comment.assert_awaited_once()


@pytest.mark.asyncio
async def test_tick_kills_hanged_procs(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    from gimle_watchdog.detection import HangedProc

    client = MagicMock()
    client.list_in_progress_issues = AsyncMock(return_value=[])
    hanged = HangedProc(
        pid=12345, etime_s=5000, cpu_s=10, cpu_ratio=0.002, command="paperclip-skills append-system-prompt-file"
    )
    kill_mock = AsyncMock(return_value=MagicMock(status="clean", pid=12345))
    with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[hanged]):
        with patch("gimle_watchdog.daemon.actions.kill_hanged_proc", kill_mock):
            with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
                await daemon._tick(cfg, state, client)
    kill_mock.assert_called_once_with(hanged)


@pytest.mark.asyncio
async def test_run_loop_exits_on_tick_timeout(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    client = MagicMock()

    import asyncio

    async def hang(*a: object, **kw: object) -> None:
        await asyncio.sleep(120)

    with patch("gimle_watchdog.daemon._tick", new=hang):
        with patch("gimle_watchdog.daemon.TICK_TIMEOUT_SECONDS", 1):
            with patch("sys.exit") as mock_exit:
                await daemon._run_one_iteration_for_test(cfg, state, client)
                mock_exit.assert_called_with(1)


def test_build_escalation_body_non_permanent(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    state.record_escalation("issue-5", "no_run")
    body = daemon._build_escalation_body("issue-5", "agent-5", state, cfg.escalation.comment_marker)
    assert "agent-5" in body
    assert "auto-unescalate" in body
    assert "PERMANENT" not in body


def test_build_escalation_body_permanent(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    for _ in range(4):
        state.record_escalation("issue-6", "no_run")
    body = daemon._build_escalation_body("issue-6", "agent-6", state, cfg.escalation.comment_marker)
    assert "PERMANENT" in body
    assert "unescalate" in body
