"""Tests for watchdog.actions — trigger_respawn + kill_hanged_proc."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gimle_watchdog import actions as act
from gimle_watchdog.detection import HangedProc
from gimle_watchdog.paperclip import Issue, PaperclipClient


def _issue(run_id: str | None = None) -> Issue:
    return Issue(
        id="issue-1",
        assignee_agent_id="agent-1",
        execution_run_id=run_id,
        status="in_progress",
        updated_at=datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc),
    )


# --- trigger_respawn ------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_respawn_via_patch_succeeds():
    """PATCH → new executionRunId appears → via='patch'."""
    client = MagicMock(spec=PaperclipClient)
    client.patch_issue = AsyncMock()
    client.post_release = AsyncMock()
    client.get_issue = AsyncMock(return_value=_issue(run_id="run-new"))

    with patch.object(act, "_sleep", new=AsyncMock()):
        result = await act.trigger_respawn(client, _issue(), "agent-1")

    assert result.via == "patch"
    assert result.success is True
    assert result.run_id == "run-new"
    client.patch_issue.assert_awaited_once_with("issue-1", {"assigneeAgentId": "agent-1"})
    client.post_release.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_respawn_patch_fails_release_patch_succeeds():
    client = MagicMock(spec=PaperclipClient)
    client.patch_issue = AsyncMock()
    client.post_release = AsyncMock()
    # First 6 polls show no run; next 6 polls (after release+patch) show run
    responses = [_issue(run_id=None)] * 6 + [_issue(run_id="run-new")] * 6
    client.get_issue = AsyncMock(side_effect=responses)

    with patch.object(act, "_sleep", new=AsyncMock()):
        result = await act.trigger_respawn(client, _issue(), "agent-1")

    assert result.via == "release_patch"
    assert result.success is True
    client.post_release.assert_awaited_once_with("issue-1")
    assert client.patch_issue.await_count == 2


@pytest.mark.asyncio
async def test_trigger_respawn_total_failure():
    client = MagicMock(spec=PaperclipClient)
    client.patch_issue = AsyncMock()
    client.post_release = AsyncMock()
    client.get_issue = AsyncMock(return_value=_issue(run_id=None))

    with patch.object(act, "_sleep", new=AsyncMock()):
        result = await act.trigger_respawn(client, _issue(), "agent-1")

    assert result.via == "none"
    assert result.success is False


# --- kill_hanged_proc -----------------------------------------------------------


async def test_kill_hanged_proc_clean_exit():
    """Process exits within grace period after SIGTERM → 'clean'."""
    hang = HangedProc(pid=12345, etime_s=3600, cpu_s=0, command="fake")

    def mock_kill(pid: int, sig: int) -> None:
        if sig == 0:
            raise ProcessLookupError("dead")
        # SIGTERM — noop in mock

    with patch.object(
        act, "_read_proc_cmdline", return_value="paperclip-skills append-system-prompt-file fake"
    ):
        with patch("gimle_watchdog.actions.os.kill", side_effect=mock_kill):
            with patch("gimle_watchdog.actions.asyncio.sleep"):
                result = await act.kill_hanged_proc(hang)
    assert result.status == "clean"


async def test_kill_hanged_proc_forced():
    """Process doesn't exit within grace period → SIGKILL → 'forced'."""
    hang = HangedProc(pid=12345, etime_s=3600, cpu_s=0, command="fake")

    with patch.object(
        act, "_read_proc_cmdline", return_value="paperclip-skills append-system-prompt-file fake"
    ):
        with patch(
            "gimle_watchdog.actions.os.kill"
        ):  # never raises → process survives SIGTERM check
            with patch("gimle_watchdog.actions.asyncio.sleep"):
                result = await act.kill_hanged_proc(hang)
    assert result.status == "forced"


async def test_kill_hanged_proc_already_dead():
    proc = subprocess.Popen(["true"])
    proc.wait()
    hang = HangedProc(pid=proc.pid, etime_s=3600, cpu_s=0, command="dummy")
    result = await act.kill_hanged_proc(hang)
    assert result.status == "already_dead"


async def test_kill_hanged_proc_pid_reused_skip():
    """If cmdline no longer matches filter, skip kill (PID-reuse mitigation)."""
    hang = HangedProc(
        pid=1,
        etime_s=3600,
        cpu_s=0,
        command="old cmd with paperclip-skills append-system-prompt-file",
    )
    with patch.object(act, "_read_proc_cmdline", return_value="/usr/sbin/unrelated --daemon"):
        result = await act.kill_hanged_proc(hang)
    assert result.status == "pid_reused_skip"


def test_read_proc_cmdline_for_nonexistent_returns_none():
    """PID 999999 is extremely unlikely to be alive."""
    assert act._read_proc_cmdline(999999) is None
