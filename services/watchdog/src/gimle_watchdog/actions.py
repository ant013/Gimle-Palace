"""Actions — trigger_respawn + kill_hanged_proc + handoff alert."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
from dataclasses import dataclass
from datetime import datetime

from gimle_watchdog.detection import HangedProc, PS_FILTER_TOKENS
from gimle_watchdog.models import (
    AlertResult,
    CommentOnlyHandoffFinding,
    Finding,
    FindingType,
    ReviewOwnedByImplementerFinding,
    WrongAssigneeFinding,
)
from gimle_watchdog.paperclip import Issue, PaperclipClient, PaperclipError


log = logging.getLogger("watchdog.actions")


RESPAWN_POLL_ATTEMPTS = 6
RESPAWN_POLL_INTERVAL_S = 5


@dataclass(frozen=True)
class RespawnResult:
    via: str  # "patch" | "release_patch" | "none"
    success: bool
    run_id: str | None


@dataclass(frozen=True)
class KillResult:
    pid: int
    status: str  # "clean" | "forced" | "already_dead" | "pid_reused_skip"


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def _wait_for_respawn(client: PaperclipClient, issue_id: str) -> str | None:
    for _ in range(RESPAWN_POLL_ATTEMPTS):
        await _sleep(RESPAWN_POLL_INTERVAL_S)
        issue = await client.get_issue(issue_id)
        if issue.execution_run_id is not None:
            return issue.execution_run_id
    return None


async def trigger_respawn(client: PaperclipClient, issue: Issue, assignee_id: str) -> RespawnResult:
    """PATCH assigneeAgentId=same as primary; POST /release + PATCH as fallback.

    GIM-216 (2026-05-06): the fallback PATCH must restore Issue.status, because
    POST /release resets status to "todo" server-side. Without restoration,
    in_review issues silently regress to todo after recovery.
    """
    # Primary — assignee-only PATCH; status was not modified, don't pollute the diff.
    await client.patch_issue(issue.id, {"assigneeAgentId": assignee_id})
    run_id = await _wait_for_respawn(client, issue.id)
    if run_id is not None:
        return RespawnResult(via="patch", success=True, run_id=run_id)

    # Fallback — release wipes status; restore it in the same PATCH that re-triggers wake.
    log.info(
        "respawn_fallback_release_patch issue=%s preserving_status=%s",
        issue.id,
        issue.status or "(empty)",
    )
    try:
        await client.post_release(issue.id)
    except PaperclipError as e:
        log.warning("release_failed issue=%s error=%s", issue.id, e)
    fallback_body: dict[str, str] = {"assigneeAgentId": assignee_id}
    if issue.status:
        # Skip when empty — sending status="" may be rejected; let server keep current.
        fallback_body["status"] = issue.status
    await client.patch_issue(issue.id, fallback_body)
    run_id = await _wait_for_respawn(client, issue.id)
    if run_id is not None:
        return RespawnResult(via="release_patch", success=True, run_id=run_id)

    return RespawnResult(via="none", success=False, run_id=None)


# --- kill -----------------------------------------------------------------------


def _read_proc_cmdline(pid: int) -> str | None:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


async def kill_hanged_proc(proc: HangedProc) -> KillResult:
    """Kill a hanged claude subprocess with PID-reuse mitigation."""
    current = _read_proc_cmdline(proc.pid)
    if current is None:
        return KillResult(pid=proc.pid, status="already_dead")
    if not all(tok in current for tok in PS_FILTER_TOKENS):
        log.warning(
            "pid_reused pid=%d old_cmd=%r new_cmd=%r",
            proc.pid,
            proc.command[:80],
            current[:80],
        )
        return KillResult(pid=proc.pid, status="pid_reused_skip")

    try:
        os.kill(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return KillResult(pid=proc.pid, status="already_dead")

    await asyncio.sleep(3)
    try:
        os.kill(proc.pid, 0)  # check if still alive
        os.kill(proc.pid, signal.SIGKILL)
        return KillResult(pid=proc.pid, status="forced")
    except ProcessLookupError:
        return KillResult(pid=proc.pid, status="clean")


# --- handoff alerts -------------------------------------------------------------

_REASON: dict[FindingType, str] = {
    FindingType.COMMENT_ONLY_HANDOFF: "@-mention from current assignee but assigneeAgentId not updated",
    FindingType.WRONG_ASSIGNEE: "assigneeAgentId is not a hired agent",
    FindingType.REVIEW_OWNED_BY_IMPLEMENTER: "in_review with implementer-class assignee",
}

_EXPECTED: dict[FindingType, str] = {
    FindingType.COMMENT_ONLY_HANDOFF: "assigneeAgentId updated to mentioned agent; valid hired agent UUID required",
    FindingType.WRONG_ASSIGNEE: "valid hired agent UUID required",
    FindingType.REVIEW_OWNED_BY_IMPLEMENTER: "reassign to a code-reviewer-class agent",
}


def render_handoff_alert_comment(
    finding: Finding,
    version: str,
    ts: datetime,
    current_assignee_name: str | None,
) -> str:
    ftype = finding.type
    ts_iso = ts.isoformat().replace("+00:00", "Z")
    name_display = current_assignee_name or "(unknown)"

    if isinstance(finding, CommentOnlyHandoffFinding):
        assignee_id = finding.current_assignee_id
        issue_number = finding.issue_number
        status = finding.issue_status
        extra_lines = [
            f"- Mention comment: {finding.mention_comment_id}",
            f"- Mentioned agent: {finding.mentioned_agent_id}",
        ]
    elif isinstance(finding, WrongAssigneeFinding):
        assignee_id = finding.bogus_assignee_id
        issue_number = finding.issue_number
        status = finding.issue_status
        extra_lines = []
    else:
        assert isinstance(finding, ReviewOwnedByImplementerFinding)
        assignee_id = finding.implementer_assignee_id
        issue_number = finding.issue_number
        status = "in_review"
        extra_lines = [
            f"- Role: {finding.implementer_role_name} ({finding.implementer_role_class})"
        ]

    lines = [
        f"## Watchdog handoff alert — {ftype}",
        "",
        f"Reason: {_REASON[ftype]}",
        "",
        "Detected state:",
        f"- Issue: GIM-{issue_number} (status={status})",
        f"- Current assignee: {assignee_id} ({name_display})",
        f"- Expected: {_EXPECTED[ftype]}",
        *extra_lines,
        "",
        f"Detector: gimle-watchdog v{version}, tick {ts_iso}.",
        "This alert is informational; no automatic repair will be performed.",
    ]
    return "\n".join(lines)


async def post_handoff_alert(
    client: PaperclipClient,
    finding: Finding,
    version: str,
    ts: datetime,
    current_assignee_name: str | None,
) -> AlertResult:
    body = render_handoff_alert_comment(finding, version, ts, current_assignee_name)
    try:
        comment_id = await client.post_issue_comment(finding.issue_id, body)
        log.info(
            "handoff_alert_posted issue=%s type=%s comment=%s",
            finding.issue_id,
            finding.type,
            comment_id,
            extra={
                "event": "handoff_alert_posted",
                "issue_id": finding.issue_id,
                "finding_type": str(finding.type),
                "comment_id": comment_id,
            },
        )
        return AlertResult(
            finding_type=finding.type,
            issue_id=finding.issue_id,
            posted=True,
            comment_id=comment_id,
            error=None,
        )
    except Exception as exc:
        log.warning(
            "handoff_alert_failed issue=%s type=%s error=%s",
            finding.issue_id,
            finding.type,
            exc,
            extra={
                "event": "handoff_alert_failed",
                "issue_id": finding.issue_id,
                "finding_type": str(finding.type),
                "error": str(exc),
            },
        )
        return AlertResult(
            finding_type=finding.type,
            issue_id=finding.issue_id,
            posted=False,
            comment_id=None,
            error=str(exc),
        )
