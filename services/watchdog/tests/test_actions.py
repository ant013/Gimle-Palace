"""Tests for watchdog.actions — trigger_respawn + kill_hanged_proc."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from gimle_watchdog import actions as act
from gimle_watchdog.detection import HangedProc, PaperclipProcessIdentity
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
    """Fallback path: PATCH then release+PATCH. Second PATCH must restore
    status because POST /release resets it server-side (GIM-216)."""
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
    # Primary PATCH: assignee only
    assert client.patch_issue.await_args_list[0].args == (
        "issue-1",
        {"assigneeAgentId": "agent-1"},
    )
    # Fallback PATCH: assignee + status restored
    assert client.patch_issue.await_args_list[1].args == (
        "issue-1",
        {"assigneeAgentId": "agent-1", "status": "in_progress"},
    )


@pytest.mark.asyncio
async def test_trigger_respawn_release_path_preserves_in_review_status():
    """GIM-216 case: in_review issue must come out of release+patch still in_review."""
    client = MagicMock(spec=PaperclipClient)
    client.patch_issue = AsyncMock()
    client.post_release = AsyncMock()
    responses = [_issue(run_id=None)] * 6 + [_issue(run_id="run-new")] * 6
    client.get_issue = AsyncMock(side_effect=responses)

    in_review = Issue(
        id="issue-1",
        assignee_agent_id="agent-1",
        execution_run_id=None,
        status="in_review",
        updated_at=datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc),
    )

    with patch.object(act, "_sleep", new=AsyncMock()):
        result = await act.trigger_respawn(client, in_review, "agent-1")

    assert result.via == "release_patch"
    assert client.patch_issue.await_args_list[1].args == (
        "issue-1",
        {"assigneeAgentId": "agent-1", "status": "in_review"},
    )


@pytest.mark.asyncio
async def test_trigger_respawn_release_path_skips_status_when_empty():
    """If Issue.status is empty (paperclip API edge), omit status field —
    sending status='' may be rejected; let server keep current state."""
    client = MagicMock(spec=PaperclipClient)
    client.patch_issue = AsyncMock()
    client.post_release = AsyncMock()
    responses = [_issue(run_id=None)] * 6 + [_issue(run_id="run-new")] * 6
    client.get_issue = AsyncMock(side_effect=responses)

    empty_status = Issue(
        id="issue-1",
        assignee_agent_id="agent-1",
        execution_run_id=None,
        status="",
        updated_at=datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc),
    )

    with patch.object(act, "_sleep", new=AsyncMock()):
        await act.trigger_respawn(client, empty_status, "agent-1")

    # Fallback PATCH must NOT carry a status field when source status is empty
    assert client.patch_issue.await_args_list[1].args == (
        "issue-1",
        {"assigneeAgentId": "agent-1"},
    )


@pytest.mark.asyncio
async def test_trigger_respawn_primary_patch_omits_status_field():
    """Primary path (no release call): PATCH must be assignee-only.
    Avoid polluting the diff with status writes on the happy path."""
    client = MagicMock(spec=PaperclipClient)
    client.patch_issue = AsyncMock()
    client.post_release = AsyncMock()
    client.get_issue = AsyncMock(return_value=_issue(run_id="run-new"))

    with patch.object(act, "_sleep", new=AsyncMock()):
        result = await act.trigger_respawn(client, _issue(), "agent-1")

    assert result.via == "patch"
    assert client.patch_issue.await_count == 1
    assert client.patch_issue.await_args_list[0].args == (
        "issue-1",
        {"assigneeAgentId": "agent-1"},
    )
    client.post_release.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_respawn_ghost_lock_skips_primary_and_releases():
    """GIM-1704: a ghost lock (executionRunId set, no active run) must skip the
    primary assignee-PATCH (it cannot clear the stale lock and would false-succeed
    on _wait_for_respawn) and go straight to the release path, which clears it."""
    client = MagicMock(spec=PaperclipClient)
    client.patch_issue = AsyncMock()
    client.post_release = AsyncMock()
    # First polls still surface the STALE ghost id (must be excluded), then a
    # fresh run id appears after release+patch.
    responses = [_issue(run_id="ghost-run")] * 3 + [_issue(run_id="run-fresh")] * 9
    client.get_issue = AsyncMock(side_effect=responses)

    # execution_run_id set + active_run_id None == ghost lock
    ghost = Issue(
        id="issue-1",
        assignee_agent_id="agent-1",
        execution_run_id="ghost-run",
        active_run_id=None,
        status="in_progress",
        updated_at=datetime(2026, 6, 22, 4, 0, tzinfo=timezone.utc),
    )

    with patch.object(act, "_sleep", new=AsyncMock()):
        result = await act.trigger_respawn(client, ghost, "agent-1")

    assert result.via == "release_patch"
    assert result.success is True
    assert result.run_id == "run-fresh"  # NOT the stale ghost id
    client.post_release.assert_awaited_once_with("issue-1")
    # Primary PATCH skipped — only the fallback (release) PATCH ran.
    assert client.patch_issue.await_count == 1
    assert client.patch_issue.await_args_list[0].args == (
        "issue-1",
        {"assigneeAgentId": "agent-1", "status": "in_progress"},
    )


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


async def test_kill_codex_requires_live_correlation_before_signal():
    identity = PaperclipProcessIdentity(
        company_id="bb8f7183-83f7-4757-a21f-ea4dcc93da9f",
        agent_id="9a6bbfbc-4f0d-4883-b56c-2d82a01122de",
        issue_id="32c71ede-f45a-4f0c-84a7-676ff200c72e",
        run_id="bf1e351b-44e1-4903-82ba-869fda596feb",
        workspace_id="e339e270-d7ce-4dec-a49e-32b4fc8d4e27",
    )
    hang = HangedProc(
        pid=44465,
        ppid=6814,
        etime_s=7200,
        cpu_s=1,
        cpu_ratio=1 / 7200,
        command="/usr/local/bin/codex exec --json",
        runtime="codex",
        identity=identity,
    )
    correlation_guard = AsyncMock(return_value=False)

    with (
        patch.object(act, "_read_proc_cmdline", return_value=hang.command),
        patch.object(act.detection, "process_snapshot_matches", return_value=True),
        patch("gimle_watchdog.actions.os.kill") as kill_mock,
    ):
        result = await act.kill_hanged_proc(hang, pre_signal_guard=correlation_guard)

    assert result.status == "correlation_skip"
    correlation_guard.assert_awaited_once()
    kill_mock.assert_not_called()


async def test_kill_codex_revalidates_snapshot_and_forces_only_exact_pid():
    identity = PaperclipProcessIdentity(
        company_id="bb8f7183-83f7-4757-a21f-ea4dcc93da9f",
        agent_id="9a6bbfbc-4f0d-4883-b56c-2d82a01122de",
        issue_id="32c71ede-f45a-4f0c-84a7-676ff200c72e",
        run_id="bf1e351b-44e1-4903-82ba-869fda596feb",
        workspace_id="e339e270-d7ce-4dec-a49e-32b4fc8d4e27",
    )
    hang = HangedProc(
        pid=44465,
        ppid=6814,
        etime_s=7200,
        cpu_s=1,
        cpu_ratio=1 / 7200,
        command="/usr/local/bin/codex exec --json",
        runtime="codex",
        identity=identity,
    )
    correlation_guard = AsyncMock(return_value=True)

    with (
        patch.object(act, "_read_proc_cmdline", return_value=hang.command),
        patch.object(act.detection, "process_snapshot_matches", side_effect=[True, True]),
        patch("gimle_watchdog.actions.os.kill") as kill_mock,
        patch("gimle_watchdog.actions.asyncio.sleep"),
    ):
        result = await act.kill_hanged_proc(hang, pre_signal_guard=correlation_guard)

    assert result.status == "forced"
    correlation_guard.assert_awaited_once()
    assert kill_mock.call_args_list[0].args == (44465, act.signal.SIGTERM)
    assert kill_mock.call_args_list[-1].args == (44465, act.signal.SIGKILL)


async def test_kill_codex_skips_when_identity_changes_after_sigterm():
    identity = PaperclipProcessIdentity(
        company_id="bb8f7183-83f7-4757-a21f-ea4dcc93da9f",
        agent_id="9a6bbfbc-4f0d-4883-b56c-2d82a01122de",
        issue_id="32c71ede-f45a-4f0c-84a7-676ff200c72e",
        run_id="bf1e351b-44e1-4903-82ba-869fda596feb",
        workspace_id="e339e270-d7ce-4dec-a49e-32b4fc8d4e27",
    )
    hang = HangedProc(
        pid=44465,
        ppid=6814,
        etime_s=7200,
        cpu_s=1,
        cpu_ratio=1 / 7200,
        command="/usr/local/bin/codex exec --json",
        runtime="codex",
        identity=identity,
    )

    with (
        patch.object(act, "_read_proc_cmdline", return_value=hang.command),
        patch.object(act.detection, "process_snapshot_matches", side_effect=[True, False]),
        patch("gimle_watchdog.actions.os.kill") as kill_mock,
        patch("gimle_watchdog.actions.asyncio.sleep"),
    ):
        result = await act.kill_hanged_proc(hang, pre_signal_guard=AsyncMock(return_value=True))

    assert result.status == "post_term_identity_skip"
    assert [call.args[1] for call in kill_mock.call_args_list] == [act.signal.SIGTERM, 0]


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


async def test_repair_comment_only_handoff_interrupts_current_run():
    client = MagicMock(spec=PaperclipClient)
    client.get_issue = AsyncMock(
        return_value=Issue(
            id="issue-42",
            assignee_agent_id=_PE_ID,
            execution_run_id="run-old",
            active_run_id="run-old",
            status="in_progress",
            updated_at=_TS,
            issue_number=42,
        )
    )
    client.patch_issue = AsyncMock()

    repaired = await act.repair_comment_only_handoff(
        client, _co_finding(), frozenset({_PE_ID, _CR_ID})
    )

    assert repaired is True
    client.patch_issue.assert_awaited_once_with(
        "issue-42",
        {
            "assigneeAgentId": _CR_ID,
            "status": "in_progress",
            "interrupt": True,
        },
    )


@pytest.mark.parametrize(
    ("current_assignee", "hired_ids"),
    [
        (_CR_ID, frozenset({_PE_ID, _CR_ID})),
        (_PE_ID, frozenset({_PE_ID})),
    ],
)
async def test_repair_comment_only_handoff_skips_changed_or_unknown_target(
    current_assignee: str, hired_ids: frozenset[str]
):
    client = MagicMock(spec=PaperclipClient)
    client.get_issue = AsyncMock(
        return_value=Issue(
            id="issue-42",
            assignee_agent_id=current_assignee,
            execution_run_id=None,
            status="in_progress",
            updated_at=_TS,
            issue_number=42,
        )
    )
    client.patch_issue = AsyncMock()

    repaired = await act.repair_comment_only_handoff(client, _co_finding(), hired_ids)

    assert repaired is False
    client.patch_issue.assert_not_awaited()


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
