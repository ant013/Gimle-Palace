"""Actions — trigger_respawn + kill_hanged_proc."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass

from gimle_watchdog.detection import HangedProc, PS_FILTER_TOKENS
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


async def trigger_respawn(
    client: PaperclipClient, issue: Issue, assignee_id: str
) -> RespawnResult:
    """PATCH assigneeAgentId=same as primary; POST /release + PATCH as fallback."""
    # Primary
    await client.patch_issue(issue.id, {"assigneeAgentId": assignee_id})
    run_id = await _wait_for_respawn(client, issue.id)
    if run_id is not None:
        return RespawnResult(via="patch", success=True, run_id=run_id)

    # Fallback
    log.info("respawn_fallback_release_patch issue=%s", issue.id)
    try:
        await client.post_release(issue.id)
    except PaperclipError as e:
        log.warning("release_failed issue=%s error=%s", issue.id, e)
    await client.patch_issue(issue.id, {"assigneeAgentId": assignee_id})
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


def kill_hanged_proc(proc: HangedProc) -> KillResult:
    """Kill a hanged claude subprocess with PID-reuse mitigation."""
    current = _read_proc_cmdline(proc.pid)
    if current is None:
        return KillResult(pid=proc.pid, status="already_dead")
    if not all(tok in current for tok in PS_FILTER_TOKENS):
        log.warning(
            "pid_reused pid=%d old_cmd=%r new_cmd=%r",
            proc.pid, proc.command[:80], current[:80],
        )
        return KillResult(pid=proc.pid, status="pid_reused_skip")

    try:
        os.kill(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return KillResult(pid=proc.pid, status="already_dead")

    time.sleep(3)
    try:
        os.kill(proc.pid, 0)  # check if still alive
        os.kill(proc.pid, signal.SIGKILL)
        return KillResult(pid=proc.pid, status="forced")
    except ProcessLookupError:
        return KillResult(pid=proc.pid, status="clean")
