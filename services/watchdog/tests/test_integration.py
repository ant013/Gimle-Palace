"""Integration tests — full _tick against a real (in-process) Paperclip mock."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from gimle_watchdog import daemon, detection as det
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


# --- GIM-80 idle-hang detection integration tests ----------------------------


def test_real_idle_proc_classified_as_hang(tmp_path: Path) -> None:
    """A process with very low CPU/etime ratio is classified as hang."""
    import unittest.mock as _mock

    # Build ps-like output for a fake idle process
    # etime=2h, cpu=1s → ratio ≈ 0.000139 → well below 0.005 threshold
    ps_text = (
        "  PID     ELAPSED        TIME COMMAND\n"
        "99991    2:00:00     0:00:01 /usr/bin/claude --append-system-prompt-file /tmp/paperclip-skills-xxx --add-dir /tmp\n"
    )
    with _mock.patch.object(det, "last_stream_event_age_seconds", return_value=None):
        hangs = det.parse_ps_output(
            ps_text, etime_min_s=3600, idle_cpu_ratio_max=0.005, hang_stream_idle_max_s=300
        )
    assert len(hangs) == 1
    assert hangs[0].pid == 99991
    assert hangs[0].cpu_ratio < 0.005


def test_real_active_proc_not_classified(tmp_path: Path) -> None:
    """A process with high CPU ratio is NOT classified as hang."""
    import unittest.mock as _mock

    # etime=2h, cpu=10min → ratio = 600/7200 ≈ 0.083 → above 0.005
    ps_text = (
        "  PID     ELAPSED        TIME COMMAND\n"
        "99992    2:00:00     0:10:00 /usr/bin/claude --append-system-prompt-file /tmp/paperclip-skills-xxx --add-dir /tmp\n"
    )
    with _mock.patch.object(det, "last_stream_event_age_seconds", return_value=None):
        hangs = det.parse_ps_output(
            ps_text, etime_min_s=3600, idle_cpu_ratio_max=0.005, hang_stream_idle_max_s=300
        )
    assert hangs == []


def test_stream_stall_detected(tmp_path: Path) -> None:
    """last_stream_event_age_seconds returns correct age for a stale log file (via mock path)."""
    import os
    import time
    import unittest.mock as _mock

    log_file = tmp_path / "stream.jsonl"
    log_file.write_text('{"event": "token"}\n')
    past_mtime = time.time() - 400  # 400s ago
    os.utime(log_file, (past_mtime, past_mtime))

    # Patch last_stream_event_age_seconds to use our temp file via subprocess mock
    # We directly validate the stat-based age by calling it with a controlled log path
    with _mock.patch("subprocess.run") as mock_run:
        # Simulate lsof returning our temp file as a .jsonl file
        mock_run.return_value = _mock.MagicMock(
            stdout=f"n{log_file}\n",
            returncode=0,
        )
        import sys as _sys

        if _sys.platform != "darwin":
            pytest.skip("lsof path only tested on macOS")
        age = det.last_stream_event_age_seconds(99999)
    assert age is not None
    assert 390 <= age <= 420  # ~400s old
