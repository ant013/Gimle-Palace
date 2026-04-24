"""Integration tests — full _tick against a real (in-process) Paperclip mock."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from gimle_watchdog import daemon
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
from gimle_watchdog.paperclip import PaperclipClient
from gimle_watchdog.state import State


def _cfg(base_url: str, tmp_path: Path) -> Config:
    return Config(
        version=1,
        paperclip=PaperclipConfig(base_url=base_url, api_key="tok"),
        companies=[
            CompanyConfig(
                id="9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64",
                name="gimle",
                thresholds=Thresholds(died_min=3, hang_etime_min=60, hang_cpu_max_s=30),
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


@pytest.mark.asyncio
async def test_tick_wakes_stuck_issue_end_to_end(mock_paperclip, tmp_path):  # type: ignore[no-untyped-def]
    base_url, mpc_state = mock_paperclip
    stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    mpc_state.issues["issue-1"] = {
        "assigneeAgentId": "agent-1",
        "executionRunId": None,
        "status": "in_progress",
        "updatedAt": stale,
    }
    cfg = _cfg(base_url, tmp_path)
    state = State.load(tmp_path / "state.json")
    client = PaperclipClient(base_url=base_url, api_key="tok")
    try:
        with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
            with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
                await daemon._tick(cfg, state, client)
    finally:
        await client.aclose()
    assert mpc_state.issues["issue-1"]["executionRunId"] is not None
    assert state.is_issue_in_cooldown("issue-1", cfg.cooldowns.per_issue_seconds)


@pytest.mark.asyncio
async def test_tick_escalates_and_comments_end_to_end(mock_paperclip, tmp_path):  # type: ignore[no-untyped-def]
    base_url, mpc_state = mock_paperclip
    stale = "2026-04-21T10:01:00Z"  # 4 min before frozen tick time
    mpc_state.issues["issue-2"] = {
        "assigneeAgentId": "agent-1",
        "executionRunId": None,
        "status": "in_progress",
        "updatedAt": stale,
    }
    cfg = _cfg(base_url, tmp_path)
    state = State.load(tmp_path / "state.json")
    # Pre-load agent cap so next tick escalates
    from freezegun import freeze_time

    for ts in ["2026-04-21T09:55:00Z", "2026-04-21T09:57:00Z", "2026-04-21T09:58:00Z"]:
        with freeze_time(ts):
            state.record_wake(f"dummy-{ts}", "agent-1")

    client = PaperclipClient(base_url=base_url, api_key="tok")
    try:
        with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
            with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
                with freeze_time("2026-04-21T10:05:00Z"):
                    await daemon._tick(cfg, state, client)
    finally:
        await client.aclose()
    assert state.is_escalated("issue-2")
    assert any("issue-2" in iid for iid, _ in mpc_state.comments_posted)
