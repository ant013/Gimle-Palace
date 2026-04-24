"""Detection primitives — ps parsers + scan_died_mid_work + scan_idle_hangs."""

from __future__ import annotations

import datetime as _dt
import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Protocol

from gimle_watchdog.config import CompanyConfig, Config
from gimle_watchdog.paperclip import Issue
from gimle_watchdog.state import State


log = logging.getLogger("watchdog.detection")


PS_FILTER_TOKENS = ("append-system-prompt-file", "paperclip-skills")


@dataclass(frozen=True)
class HangedProc:
    pid: int
    etime_s: int
    cpu_s: int
    command: str


@dataclass(frozen=True)
class Action:
    kind: str  # "wake" | "skip" | "escalate"
    issue: Issue
    agent_id: str
    reason: str = ""


class _IssueLister(Protocol):
    async def list_in_progress_issues(self, company_id: str) -> list[Issue]: ...


# --- ps field parsers ----------------------------------------------------------


_ETIME_DAYS_RE = re.compile(r"^(\d+)-(\d+):(\d+):(\d+)$")
_ETIME_HMS_RE = re.compile(r"^(\d+):(\d+):(\d+)$")
_ETIME_MS_RE = re.compile(r"^(\d+):(\d+)$")


def _parse_etime(s: str) -> int:
    """ps(1) ELAPSED in seconds. Handles macOS + Linux formats."""
    s = s.strip()
    if m := _ETIME_DAYS_RE.match(s):
        d, h, mm, ss = (int(x) for x in m.groups())
        return d * 86400 + h * 3600 + mm * 60 + ss
    if m := _ETIME_HMS_RE.match(s):
        h, mm, ss = (int(x) for x in m.groups())
        return h * 3600 + mm * 60 + ss
    if m := _ETIME_MS_RE.match(s):
        mm, ss = (int(x) for x in m.groups())
        return mm * 60 + ss
    return 0


def _parse_time(s: str) -> int:
    """ps(1) TIME (cpu time) in seconds. Returns integer seconds, 0 on parse error."""
    s = s.strip()
    if "." in s:
        base, _, frac = s.partition(".")
        rounded_up = int(frac[:2].ljust(2, "0")) >= 50 if frac else False
    else:
        base = s
        rounded_up = False

    parts = base.split(":")
    try:
        if len(parts) == 2:
            value = int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            value = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        else:
            return 0
    except ValueError:
        return 0
    return value + (1 if rounded_up else 0)


def parse_ps_output(ps_output: str, etime_min_s: int, cpu_max_s: int) -> list[HangedProc]:
    """Parse `ps -ao pid,etime,time,command` output, return hanged procs.

    Hanged = command matches PS_FILTER_TOKENS AND etime >= etime_min_s AND cpu <= cpu_max_s.
    """
    hangs: list[HangedProc] = []
    lines = ps_output.splitlines()
    for line in lines[1:]:  # skip header
        fields = line.split(None, 3)
        if len(fields) < 4:
            continue
        pid_str, etime_str, time_str, command = fields
        if not all(tok in command for tok in PS_FILTER_TOKENS):
            continue
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        etime_s = _parse_etime(etime_str)
        cpu_s = _parse_time(time_str)
        if etime_s >= etime_min_s and cpu_s <= cpu_max_s:
            hangs.append(HangedProc(pid=pid, etime_s=etime_s, cpu_s=cpu_s, command=command))
    return hangs


# --- scan_idle_hangs -----------------------------------------------------------


def scan_idle_hangs(config: Config) -> list[HangedProc]:
    """Run ps on host, filter for hung paperclip claude subprocesses."""
    etime_min_s = min(c.thresholds.hang_etime_min for c in config.companies) * 60
    cpu_max_s = max(c.thresholds.hang_cpu_max_s for c in config.companies)
    try:
        result = subprocess.run(
            ["ps", "-ao", "pid,etime,time,command"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log.error("ps_failed %s", e)
        return []
    return parse_ps_output(result.stdout, etime_min_s, cpu_max_s)


# --- scan_died_mid_work --------------------------------------------------------


async def scan_died_mid_work(
    company: CompanyConfig,
    client: _IssueLister,
    state: State,
    config: Config,
) -> list[Action]:
    """Find issues stuck in assignee-set + no-run + stale-updatedAt state."""
    now = _dt.datetime.now(_dt.timezone.utc)
    threshold_dt = now - _dt.timedelta(minutes=company.thresholds.died_min)
    issues = await client.list_in_progress_issues(company.id)
    actions: list[Action] = []
    for issue in issues:
        if issue.assignee_agent_id is None:
            continue
        if issue.execution_run_id is not None:
            continue
        if issue.updated_at > threshold_dt:
            continue

        if state.is_escalated(issue.id):
            if state.is_permanently_escalated(issue.id):
                continue
            entry = state.escalated_issues[issue.id]
            escalated_at_str = str(entry.get("escalated_at", "1970-01-01T00:00:00Z"))
            escalated_at = _dt.datetime.fromisoformat(escalated_at_str.replace("Z", "+00:00"))
            if issue.updated_at > escalated_at:
                state.clear_escalation(issue.id)
                # fall through and treat as normal candidate
            else:
                continue

        if state.is_issue_in_cooldown(issue.id, config.cooldowns.per_issue_seconds):
            actions.append(
                Action(
                    kind="skip",
                    issue=issue,
                    agent_id=issue.assignee_agent_id,
                    reason="per_issue_cooldown",
                )
            )
            continue
        if state.agent_cap_exceeded(issue.assignee_agent_id, config.cooldowns):
            actions.append(
                Action(
                    kind="escalate",
                    issue=issue,
                    agent_id=issue.assignee_agent_id,
                    reason="per_agent_cap",
                )
            )
            continue
        actions.append(Action(kind="wake", issue=issue, agent_id=issue.assignee_agent_id))
    return actions
