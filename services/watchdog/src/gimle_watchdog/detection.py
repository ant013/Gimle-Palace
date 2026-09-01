"""Detection primitives — ps parsers + scan_died_mid_work + scan_idle_hangs."""

from __future__ import annotations

import datetime as _dt
import logging
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from gimle_watchdog.config import CompanyConfig, Config
from gimle_watchdog.paperclip import Issue
from gimle_watchdog.state import State


log = logging.getLogger("watchdog.detection")


CLAUDE_FILTER_TOKENS = ("append-system-prompt-file", "paperclip-skills")
# Backward-compatible public name used by older operators/tests.
PS_FILTER_TOKENS = CLAUDE_FILTER_TOKENS
_PAPERCLIP_IDENTITY_KEYS = {
    "company_id": "PAPERCLIP_COMPANY_ID",
    "agent_id": "PAPERCLIP_AGENT_ID",
    "issue_id": "PAPERCLIP_TASK_ID",
    "run_id": "PAPERCLIP_RUN_ID",
    "workspace_id": "PAPERCLIP_WORKSPACE_ID",
}
_UUID_VALUE_RE = (
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}"
)


@dataclass(frozen=True)
class PaperclipProcessIdentity:
    company_id: str
    agent_id: str
    issue_id: str
    run_id: str
    workspace_id: str

    @property
    def correlation_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.company_id,
            self.agent_id,
            self.issue_id,
            self.run_id,
            self.workspace_id,
        )


@dataclass(frozen=True)
class HangedProc:
    pid: int
    etime_s: int
    cpu_s: int
    cpu_ratio: float
    command: str
    runtime: str = "claude"
    ppid: int = 0
    identity: PaperclipProcessIdentity | None = None
    stream_event_age_s: int | None = None  # None means no log file found


@dataclass(frozen=True)
class Action:
    kind: str  # "wake" | "skip" | "escalate"
    issue: Issue
    agent_id: str
    reason: str = ""


class _IssueLister(Protocol):
    async def list_active_issues(self, company_id: str) -> list[Issue]: ...


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


def classify_agent_command(command: str) -> str | None:
    """Return the supported Paperclip runtime shape without broad substring matching."""
    if all(marker in command for marker in CLAUDE_FILTER_TOKENS):
        return "claude"
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if len(tokens) >= 2 and Path(tokens[0]).name == "codex" and tokens[1] == "exec":
        return "codex"
    return None


def count_agent_commands(ps_output: str) -> dict[str, int]:
    """Count supported command shapes without reading or returning process environments."""
    counts = {"claude": 0, "codex": 0}
    for line in ps_output.splitlines()[1:]:
        fields = line.split(None, 1)
        if len(fields) != 2:
            continue
        runtime = classify_agent_command(fields[1])
        if runtime is not None:
            counts[runtime] += 1
    return counts


def parse_paperclip_identity(process_text: str) -> PaperclipProcessIdentity | None:
    """Extract only allowlisted UUID identity fields from a raw process environment.

    The raw input may include PAPERCLIP_API_KEY and wake payloads. Callers must never
    log or persist it; this function returns only non-secret UUID fields.
    """
    values: dict[str, str] = {}
    for field_name, environment_key in _PAPERCLIP_IDENTITY_KEYS.items():
        pattern = rf"(?:^|\s){re.escape(environment_key)}=({_UUID_VALUE_RE})(?=\s|$)"
        matches = re.findall(pattern, process_text)
        if len(matches) != 1:
            return None
        values[field_name] = matches[0].lower()
    return PaperclipProcessIdentity(**values)


def read_process_command(pid: int) -> str | None:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def read_process_ppid(pid: int) -> int | None:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "ppid="],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _read_process_environment_text(pid: int) -> str | None:
    if sys.platform.startswith("linux"):
        try:
            return (
                Path(f"/proc/{pid}/environ")
                .read_bytes()
                .replace(b"\0", b" ")
                .decode("utf-8", errors="replace")
            )
        except OSError:
            return None
    try:
        result = subprocess.run(
            ["ps", "eww", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout


def read_paperclip_identity(pid: int) -> PaperclipProcessIdentity | None:
    process_text = _read_process_environment_text(pid)
    if process_text is None:
        return None
    return parse_paperclip_identity(process_text)


def is_paperclip_parent_command(command: str | None) -> bool:
    if command is None:
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    for index, token in enumerate(tokens[:-1]):
        if Path(token).name == "paperclipai" and tokens[index + 1] == "run":
            return True
    return False


def process_snapshot_matches(proc: HangedProc, current_command: str | None = None) -> bool:
    """Revalidate a discovered process without ever returning its raw environment."""
    command = current_command if current_command is not None else read_process_command(proc.pid)
    if command is None or classify_agent_command(command) != proc.runtime:
        return False
    if proc.runtime != "codex":
        return True
    if proc.identity is None or proc.ppid <= 1:
        return False
    if read_process_ppid(proc.pid) != proc.ppid:
        return False
    if not is_paperclip_parent_command(read_process_command(proc.ppid)):
        return False
    return read_paperclip_identity(proc.pid) == proc.identity


def last_stream_event_age_seconds(pid: int) -> int | None:
    """Return seconds since last stream-json write for the given PID, or None if not found.

    On macOS uses lsof to find the process's stdout/stderr log file.
    Falls back to /proc/{pid}/fd/1 on Linux.
    Returns None when no log file can be resolved.
    """
    log_path: Path | None = None

    import sys as _sys

    if _sys.platform.startswith("linux"):
        fd1 = Path(f"/proc/{pid}/fd/1")
        try:
            resolved = fd1.resolve(strict=True)
            if resolved.is_file():
                log_path = resolved
        except OSError:
            pass
    else:
        # macOS: use lsof to find regular file FDs for the process
        try:
            result = subprocess.run(
                ["lsof", "-p", str(pid), "-F", "n"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for lsof_line in result.stdout.splitlines():
                if lsof_line.startswith("n") and lsof_line.endswith(".jsonl"):
                    candidate = Path(lsof_line[1:])
                    if candidate.is_file():
                        log_path = candidate
                        break
        except (subprocess.TimeoutExpired, OSError):
            pass

    if log_path is None:
        return None

    try:
        age = int(time.time() - log_path.stat().st_mtime)
        return max(0, age)
    except OSError:
        return None


def parse_ps_output(
    ps_output: str,
    etime_min_s: int,
    idle_cpu_ratio_max: float,
    hang_stream_idle_max_s: int,
) -> list[HangedProc]:
    """Parse host process output and return attributable, idle agent processes.

    Claude keeps its established command signature. Codex additionally requires a
    Paperclip parent and a complete sanitized Paperclip process identity.
    """
    hangs: list[HangedProc] = []
    lines = ps_output.splitlines()
    if not lines:
        return hangs
    header = lines[0].split()
    has_ppid = len(header) >= 2 and header[1] == "PPID"
    for line in lines[1:]:  # skip header
        if has_ppid:
            fields = line.split(None, 4)
            if len(fields) < 5:
                continue
            pid_str, ppid_str, etime_str, time_str, command = fields
        else:
            fields = line.split(None, 3)
            if len(fields) < 4:
                continue
            pid_str, etime_str, time_str, command = fields
            ppid_str = "0"
        runtime = classify_agent_command(command)
        if runtime is None:
            continue
        try:
            pid = int(pid_str)
            ppid = int(ppid_str)
        except ValueError:
            continue
        identity: PaperclipProcessIdentity | None = None
        if runtime == "codex":
            if ppid <= 1 or not is_paperclip_parent_command(read_process_command(ppid)):
                continue
            identity = read_paperclip_identity(pid)
            if identity is None:
                continue
        etime_s = _parse_etime(etime_str)
        cpu_s = _parse_time(time_str)
        if etime_s < etime_min_s:
            continue
        cpu_ratio = cpu_s / etime_s if etime_s > 0 else 0.0
        stream_age = last_stream_event_age_seconds(pid)
        idle_cpu = cpu_ratio < idle_cpu_ratio_max
        stream_stalled = stream_age is not None and stream_age > hang_stream_idle_max_s
        if idle_cpu or stream_stalled:
            hangs.append(
                HangedProc(
                    pid=pid,
                    etime_s=etime_s,
                    cpu_s=cpu_s,
                    cpu_ratio=cpu_ratio,
                    command=command,
                    runtime=runtime,
                    ppid=ppid,
                    identity=identity,
                    stream_event_age_s=stream_age,
                )
            )
    return hangs


# --- scan_idle_hangs -----------------------------------------------------------


def scan_idle_hangs(config: Config) -> list[HangedProc]:
    """Run ps on host, filter for attributable hung Paperclip agent subprocesses."""
    etime_min_s = min(c.thresholds.hang_etime_min for c in config.companies) * 60
    idle_cpu_ratio_max = min(c.thresholds.idle_cpu_ratio_max for c in config.companies)
    hang_stream_idle_max_s = min(c.thresholds.hang_stream_idle_max_s for c in config.companies)
    try:
        result = subprocess.run(
            ["ps", "-ao", "pid,ppid,etime,time,command"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log.error("ps_failed %s", e)
        return []
    return parse_ps_output(result.stdout, etime_min_s, idle_cpu_ratio_max, hang_stream_idle_max_s)


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
    # GIM-NN (2026-05-06): cap on max age — don't wake long-abandoned issues.
    # After in_review scope landed (#106), 3-week-old archive issues started
    # getting woken because they technically met the (assignee + no-run + stale)
    # gates. Recovery is only meaningful for *recent* lost handoffs.
    max_age_dt = now - _dt.timedelta(minutes=company.thresholds.recover_max_age_min)
    # GIM-216 (2026-05-06): scan in_review too — handoff PATCH may land but
    # wake-event may be lost (e.g. when source PATCH was authored by a
    # SIGTERM'd run). list_active_issues also feeds infra-block tier scans, so
    # recovery must explicitly skip blocked issues below.
    issues = await client.list_active_issues(company.id)

    # Build parent_id -> set of live-child IDs. A parent assignee that's
    # idle while a child is still in_progress / in_review / todo is
    # legitimately waiting on the child to close, not stranded. Skipping
    # these avoids the wake → CTO-exits-idle → wake loop on parent issues
    # (e.g. GIM-283 waiting on GIM-289).
    _LIVE_STATUSES = {"in_progress", "in_review", "todo"}
    live_children_by_parent: dict[str, list[str]] = {}
    for c in issues:
        if c.parent_id and c.status in _LIVE_STATUSES:
            live_children_by_parent.setdefault(c.parent_id, []).append(c.id)

    actions: list[Action] = []
    for issue in issues:
        if issue.status == "blocked":
            continue
        if issue.assignee_agent_id is None:
            continue
        # GIM-1704 (2026-06-22): an executionRunId with NO active run is a stale
        # GHOST LOCK (a dead run left the lock set) — recoverable, NOT "running".
        # Skip only issues with a genuinely live run (active_run_id present); let
        # ghost-locked stuck issues fall through to recovery (trigger_respawn's
        # release path clears the stale lock, then respawns).
        if issue.active_run_id is not None:
            continue
        if issue.id in live_children_by_parent:
            log.info(
                "skip issue=%s reason=parent_waits_children children=%d",
                issue.id,
                len(live_children_by_parent[issue.id]),
            )
            continue
        if issue.updated_at > threshold_dt:
            continue
        if issue.updated_at < max_age_dt:
            # Issue hasn't been touched in too long — treat as abandoned, not
            # a lost-handoff. Operator can manually wake if recovery is needed.
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
