"""palace.ops.unstick_issue — release stale paperclip execution locks.

Algorithm:
  1. Read issue state from paperclip API. executionRunId=None → noop.
  2. Discover candidate Claude PIDs on the host (SSH or local).
     a. Strict: timing heuristic — match claude --print whose etime ≈
        (now - executionLockedAt) within ±60s.
     b. Permissive fallback: idle claude --print (etime>30m, cpu<0.5%).
  3. dry_run=True → return candidates, no kills.
  4. Refuse if >5 candidates unless force=True.
  5. SIGTERM each candidate.
  6. Poll API until executionRunId clears (every 5s, up to timeout_sec).
  7. Write audit :Episode to Graphiti (wrapped in try/except — kill must
     succeed even when Neo4j/Graphiti is down).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from graphiti_core import Graphiti

from palace_mcp.graphiti_runtime import save_entity_node
from palace_mcp.graphiti_schema.entities import make_episode

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SEC = 5
_STRICT_ETIME_TOLERANCE_SEC = 60
_PID_CAP = 5
_IDLE_ETIME_MIN = 30.0
_IDLE_CPU_MAX_PCT = 0.5  # pcpu column is percent (0..100)


# ---------------------------------------------------------------------------
# ps output parsing
# ---------------------------------------------------------------------------


def _parse_etime_to_minutes(etime: str) -> float:
    """Convert ps etime (e.g. '01:30:00', '2-03:00:00') to minutes."""
    etime = etime.strip()
    days = 0
    if "-" in etime:
        day_str, etime = etime.split("-", 1)
        days = int(day_str)
    parts = etime.split(":")
    if len(parts) == 3:  # hh:mm:ss
        h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    elif len(parts) == 2:  # mm:ss
        h, m, s = 0, int(parts[0]), int(parts[1])
    else:  # ss
        h, m, s = 0, 0, int(parts[0])
    return days * 1440.0 + h * 60.0 + m + s / 60.0


def _parse_ps_output(ps_output: str) -> list[dict[str, Any]]:
    """Parse `ps -A -o pid,etime,pcpu,command` output into row dicts."""
    rows: list[dict[str, Any]] = []
    for line in ps_output.splitlines():
        line = line.strip()
        if not line or line.upper().startswith("PID"):
            continue
        # first 3 cols are fixed-width tokens; remainder is the command
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        try:
            rows.append(
                {
                    "pid": int(parts[0]),
                    "etime": parts[1],
                    "pcpu": float(parts[2]),
                    "command": parts[3],
                }
            )
        except (ValueError, IndexError):
            continue
    return rows


def _find_strict_candidates(
    rows: list[dict[str, Any]], execution_locked_at: str
) -> list[dict[str, Any]]:
    """Return claude --print processes whose etime matches (now - executionLockedAt) ±60s.

    Task 0 spike confirmed that executionRunId is never present in process args,
    so timing-based matching is the only practical strict heuristic.
    """
    try:
        locked_dt = datetime.fromisoformat(execution_locked_at.replace("Z", "+00:00"))
        expected_sec = (datetime.now(timezone.utc) - locked_dt).total_seconds()
    except Exception:
        return []

    result = []
    for r in rows:
        if "claude" not in r["command"] or "--print" not in r["command"]:
            continue
        try:
            etime_sec = _parse_etime_to_minutes(r["etime"]) * 60.0
        except Exception:
            continue
        if abs(etime_sec - expected_sec) <= _STRICT_ETIME_TOLERANCE_SEC:
            result.append(r)
    return result


def _find_permissive_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return idle claude --print processes (etime>30m, pcpu<0.5%)."""
    result = []
    for r in rows:
        if "claude" not in r["command"] or "--print" not in r["command"]:
            continue
        try:
            etime_min = _parse_etime_to_minutes(r["etime"])
        except Exception:
            continue
        if etime_min >= _IDLE_ETIME_MIN and r["pcpu"] < _IDLE_CPU_MAX_PCT:
            result.append(r)
    return result


# ---------------------------------------------------------------------------
# Subprocess helpers (always asyncio.create_subprocess_exec — no blocking I/O)
# ---------------------------------------------------------------------------


async def _run_subprocess(*args: str) -> tuple[str, str, int]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_b, stderr_b = await proc.communicate()
    return (
        stdout_b.decode(errors="replace"),
        stderr_b.decode(errors="replace"),
        proc.returncode or 0,
    )


def _ssh_prefix(ops_host: str, ssh_key: str, ssh_user: str) -> list[str]:
    return [
        "ssh",
        "-i",
        ssh_key,
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        f"{ssh_user}@{ops_host}",
    ]


async def _get_ps_output(ops_host: str, ssh_key: str, ssh_user: str) -> str:
    ps_cmd = ["ps", "-A", "-o", "pid,etime,pcpu,command"]
    if ops_host == "local":
        args = ps_cmd
    else:
        args = _ssh_prefix(ops_host, ssh_key, ssh_user) + ps_cmd
    stdout, stderr, rc = await _run_subprocess(*args)
    if rc != 0:
        raise RuntimeError(f"ps failed (rc={rc}): {stderr.strip()}")
    return stdout


async def _send_sigterm(
    pids: list[int], ops_host: str, ssh_key: str, ssh_user: str
) -> None:
    kill_args = ["kill", "-TERM"] + [str(p) for p in pids]
    if ops_host == "local":
        args = kill_args
    else:
        args = _ssh_prefix(ops_host, ssh_key, ssh_user) + kill_args
    _, stderr, rc = await _run_subprocess(*args)
    if rc != 0:
        logger.warning("kill returned rc=%d: %s", rc, stderr.strip())


# ---------------------------------------------------------------------------
# Paperclip API helpers
# ---------------------------------------------------------------------------


async def _get_execution_run_id(
    client: httpx.AsyncClient, api_url: str, issue_id: str
) -> str | None:
    resp = await client.get(f"{api_url}/api/issues/{issue_id}")
    resp.raise_for_status()
    value = resp.json().get("executionRunId")
    return str(value) if value is not None else None


async def _poll_until_cleared(
    api_url: str, api_key: str, issue_id: str, timeout_sec: int
) -> bool:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    deadline = asyncio.get_event_loop().time() + timeout_sec
    async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
        while asyncio.get_event_loop().time() < deadline:
            run_id = await _get_execution_run_id(client, api_url, issue_id)
            if run_id is None:
                return True
            await asyncio.sleep(_POLL_INTERVAL_SEC)
    return False


# ---------------------------------------------------------------------------
# Graphiti audit episode
# ---------------------------------------------------------------------------


async def _write_audit_episode(
    graphiti: Graphiti,
    group_id: str,
    issue_id: str,
    killed_pids: list[int],
    outcome: str,
    stale_run_id: str | None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    node = make_episode(
        group_id=group_id,
        name=f"ops.unstick_issue:{issue_id}:{now}",
        kind="ops.unstick_issue",
        source="palace.ops.unstick_issue",
        extractor="palace.ops.unstick_issue",
        extractor_version="1.0.0",
        observed_at=now,
        extra={
            "target_issue": issue_id,
            "killed_pids": killed_pids,
            "outcome": outcome,
            "stale_run_id": stale_run_id,
        },
    )
    await save_entity_node(graphiti, node)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def unstick_issue(
    issue_id: str,
    *,
    dry_run: bool = False,
    force: bool = False,
    timeout_sec: int = 90,
    ops_host: str,
    ssh_key: str,
    ssh_user: str,
    api_url: str,
    api_key: str = "",
    graphiti: Graphiti | None,
    group_id: str,
) -> dict[str, Any]:
    """Force-release a paperclip issue stuck on a stale executionRunId."""

    # Step 1 — read current lock state
    auth_headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=10.0, headers=auth_headers) as client:
        resp = await client.get(f"{api_url}/api/issues/{issue_id}")
        resp.raise_for_status()
        issue_data = resp.json()

    stale_run_id = issue_data.get("executionRunId")
    if stale_run_id is None:
        return {"ok": True, "action": "noop", "issue_id": issue_id}
    stale_run_id = str(stale_run_id)
    execution_locked_at: str = issue_data.get("executionLockedAt") or ""

    # Step 2 — discover candidate PIDs
    try:
        ps_output = await _get_ps_output(ops_host, ssh_key, ssh_user)
    except Exception as exc:
        return {
            "ok": False,
            "error": "ssh_unreachable",
            "details": str(exc),
            "issue_id": issue_id,
        }

    rows = _parse_ps_output(ps_output)
    strict = _find_strict_candidates(rows, execution_locked_at)
    if strict:
        candidates = strict
        heuristic: str = "strict"
    else:
        candidates = _find_permissive_candidates(rows)
        heuristic = "permissive"

    pids = [r["pid"] for r in candidates]

    if dry_run:
        return {
            "ok": True,
            "action": "dry_run",
            "issue_id": issue_id,
            "stale_run_id": stale_run_id,
            "heuristic": heuristic,
            "candidates": pids,
        }

    if len(pids) > _PID_CAP and not force:
        return {
            "ok": False,
            "error": "too_many_candidates",
            "message": (
                f"Found {len(pids)} PIDs (cap={_PID_CAP}). Pass force=True to override."
            ),
            "candidates": pids,
            "heuristic": heuristic,
        }

    if not pids:
        return {
            "ok": False,
            "error": "no_candidates",
            "issue_id": issue_id,
            "stale_run_id": stale_run_id,
            "heuristic": heuristic,
        }

    # Step 3 — SIGTERM
    try:
        await _send_sigterm(pids, ops_host, ssh_key, ssh_user)
    except Exception as exc:
        return {
            "ok": False,
            "error": "kill_failed",
            "details": str(exc),
            "pids": pids,
        }

    # Step 4 — poll for lock clear
    cleared = await _poll_until_cleared(api_url, api_key, issue_id, timeout_sec)

    # Step 5 — audit episode (best-effort; must not block kill outcome)
    outcome = "killed" if cleared else "killed_lock_not_released"
    if graphiti is not None:
        try:
            await _write_audit_episode(
                graphiti, group_id, issue_id, pids, outcome, stale_run_id
            )
        except Exception:
            logger.warning(
                "ops.unstick_issue: audit episode write failed (graphiti unavailable)",
                exc_info=True,
            )

    if cleared:
        return {
            "ok": True,
            "action": "killed",
            "issue_id": issue_id,
            "killed_pids": pids,
            "heuristic": heuristic,
        }

    # Check for respawn (new run on same issue)
    async with httpx.AsyncClient(timeout=10.0, headers=auth_headers) as client:
        new_run_id = await _get_execution_run_id(client, api_url, issue_id)
    if new_run_id is not None and new_run_id != stale_run_id:
        return {
            "ok": True,
            "action": "killed_then_respawned",
            "issue_id": issue_id,
            "killed_pids": pids,
            "heuristic": heuristic,
            "new_run_id": new_run_id,
        }

    return {
        "ok": False,
        "error": "lock_not_released",
        "issue_id": issue_id,
        "stale_run_id": stale_run_id,
        "killed_pids": pids,
        "heuristic": heuristic,
    }
