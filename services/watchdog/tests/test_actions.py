"""Tests for watchdog.actions — trigger_respawn + kill_hanged_proc."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from gimle_watchdog import actions as act
from gimle_watchdog.detection import HangedProc
from gimle_watchdog.models import (
    CommentOnlyHandoffFinding,
    FindingType,
    ReviewOwnedByImplementerFinding,
    WrongAssigneeFinding,
)
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
    hang = HangedProc(pid=12345, etime_s=3600, cpu_s=0, cpu_ratio=0.0, command="fake")

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
    hang = HangedProc(pid=12345, etime_s=3600, cpu_s=0, cpu_ratio=0.0, command="fake")

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
    hang = HangedProc(pid=proc.pid, etime_s=3600, cpu_s=0, cpu_ratio=0.0, command="dummy")
    result = await act.kill_hanged_proc(hang)
    assert result.status == "already_dead"


async def test_kill_hanged_proc_pid_reused_skip():
    """If cmdline no longer matches filter, skip kill (PID-reuse mitigation)."""
    hang = HangedProc(
        pid=1,
        etime_s=3600,
        cpu_s=0,
        cpu_ratio=0.0,
        command="old cmd with paperclip-skills append-system-prompt-file",
    )
    with patch.object(act, "_read_proc_cmdline", return_value="/usr/sbin/unrelated --daemon"):
        result = await act.kill_hanged_proc(hang)
    assert result.status == "pid_reused_skip"


def test_read_proc_cmdline_for_nonexistent_returns_none():
    """PID 999999 is extremely unlikely to be alive."""
    assert act._read_proc_cmdline(999999) is None


# ---------------------------------------------------------------------------
# T6: render_handoff_alert_comment + post_handoff_alert
# ---------------------------------------------------------------------------

_PE_ID = "127068ee-b564-4b37-9370-616c81c63f35"
_CR_ID = "bd2d7e20-7ed8-474c-91fc-353d610f4c52"
_TS = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)
_VERSION = "0.3.0"


def _co_finding() -> CommentOnlyHandoffFinding:
    return CommentOnlyHandoffFinding(
        type=FindingType.COMMENT_ONLY_HANDOFF,
        issue_id="issue-42",
        issue_number=42,
        current_assignee_id=_PE_ID,
        mentioned_agent_id=_CR_ID,
        mention_comment_id="cmt-001",
        mention_author_agent_id=_PE_ID,
        mention_age_seconds=600,
        issue_status="in_progress",
    )


def _wa_finding() -> WrongAssigneeFinding:
    return WrongAssigneeFinding(
        type=FindingType.WRONG_ASSIGNEE,
        issue_id="issue-43",
        issue_number=43,
        bogus_assignee_id="00000000-dead-beef-0000-000000000001",
        issue_status="in_progress",
        age_seconds=300,
    )


def _ro_finding() -> ReviewOwnedByImplementerFinding:
    return ReviewOwnedByImplementerFinding(
        type=FindingType.REVIEW_OWNED_BY_IMPLEMENTER,
        issue_id="issue-44",
        issue_number=44,
        implementer_assignee_id=_PE_ID,
        implementer_role_name="PythonEngineer",
        implementer_role_class="implementer",
        age_seconds=420,
    )


def test_render_handoff_alert_comment_for_comment_only():
    body = act.render_handoff_alert_comment(_co_finding(), _VERSION, _TS, "PythonEngineer")
    assert "comment_only_handoff" in body
    assert "@-mention from current assignee but assigneeAgentId not updated" in body
    assert "cmt-001" in body
    assert _CR_ID in body


def test_render_handoff_alert_comment_for_wrong_assignee():
    body = act.render_handoff_alert_comment(_wa_finding(), _VERSION, _TS, None)
    assert "wrong_assignee" in body
    assert "assigneeAgentId is not a hired agent" in body
    assert "valid hired agent UUID required" in body


def test_render_handoff_alert_comment_for_review_owned():
    body = act.render_handoff_alert_comment(_ro_finding(), _VERSION, _TS, "PythonEngineer")
    assert "review_owned_by_implementer" in body
    assert "in_review with implementer-class assignee" in body
    assert "reassign to a code-reviewer-class agent" in body


def test_render_handoff_alert_includes_grep_anchor():
    body = act.render_handoff_alert_comment(_co_finding(), _VERSION, _TS, "PythonEngineer")
    assert body.startswith("## Watchdog handoff alert — ")


def test_render_handoff_alert_handles_unknown_assignee_name():
    body = act.render_handoff_alert_comment(_wa_finding(), _VERSION, _TS, None)
    assert "unknown" in body.lower() or "(unknown)" in body or "None" not in body


async def test_post_handoff_alert_emits_jsonl_event_on_success(caplog):
    import logging

    transport = httpx.MockTransport(lambda req: httpx.Response(201, json={"id": "cmt-new"}))
    client = PaperclipClient(base_url="http://pc.test", api_key="tok", transport=transport)
    try:
        with caplog.at_level(logging.INFO, logger="watchdog.actions"):
            result = await act.post_handoff_alert(client, _co_finding(), _VERSION, _TS, "PE")
        assert result.posted is True
        assert result.comment_id == "cmt-new"
        events = [r for r in caplog.records if getattr(r, "event", None) == "handoff_alert_posted"]
        assert len(events) == 1
    finally:
        await client.aclose()


async def test_post_handoff_alert_emits_jsonl_event_on_failure(caplog):
    import logging

    transport = httpx.MockTransport(lambda req: httpx.Response(500, json={"error": "boom"}))
    client = PaperclipClient(base_url="http://pc.test", api_key="tok", transport=transport)
    try:
        with caplog.at_level(logging.WARNING, logger="watchdog.actions"):
            result = await act.post_handoff_alert(client, _co_finding(), _VERSION, _TS, "PE")
        assert result.posted is False
        assert result.error is not None
        events = [r for r in caplog.records if getattr(r, "event", None) == "handoff_alert_failed"]
        assert len(events) == 1
    finally:
        await client.aclose()
