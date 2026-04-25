"""Main daemon loop — orchestrates detection + actions + state per tick."""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import sys

from gimle_watchdog import actions, detection
from gimle_watchdog.config import Config
from gimle_watchdog.paperclip import PaperclipClient
from gimle_watchdog.state import State


log = logging.getLogger("watchdog.daemon")


TICK_TIMEOUT_SECONDS = 60


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _build_escalation_body(issue_id: str, agent_id: str, state: State, marker: str) -> str:
    count = state.escalation_count(issue_id)
    permanent = state.is_permanently_escalated(issue_id)
    marker_with_meta = f"{marker[:-4]} issue={issue_id} agent={agent_id} count={count} -->"
    if permanent:
        unescalate_note = (
            f"**PERMANENT escalation** ({count} cycles). Auto-unescalate disabled. "
            f"Requires explicit `gimle-watchdog unescalate --issue {issue_id}` to clear."
        )
    else:
        unescalate_note = (
            "Will auto-unescalate when issue `updatedAt` advances past current escalated_at "
            "(any operator touch — comment, reassign, status change)."
        )
    return (
        f"{marker_with_meta}\n"
        f"⚠ **Watchdog escalation — operator intervention needed**\n\n"
        f"Agent `{agent_id}` exceeded wake cap ({count} escalation cycles).\n\n"
        f"{unescalate_note}\n\n"
        f"Diagnostic: SSH the iMac, `grep '{issue_id}' ~/.paperclip/watchdog.log` for timeline."
    )


async def _tick(cfg: Config, state: State, client: PaperclipClient) -> None:
    """One scan pass: kill hangs, then wake died-mid-work issues."""
    log.info("tick_start companies=%d", len(cfg.companies))

    # Phase 1: kill host-level idle hangs
    hanged = detection.scan_idle_hangs(cfg)
    for proc in hanged:
        res = await actions.kill_hanged_proc(proc)
        log.warning(
            "hang_killed pid=%d etime_s=%d cpu_s=%d cpu_ratio=%.4f stream_age_s=%s status=%s",
            proc.pid,
            proc.etime_s,
            proc.cpu_s,
            proc.cpu_ratio,
            proc.stream_event_age_s,
            res.status,
        )
    if hanged:
        await _sleep(10)

    # Phase 2: respawn stuck assignees per company
    total_actions = 0
    for company in cfg.companies:
        died = await detection.scan_died_mid_work(company, client, state, cfg)
        for action in died:
            if action.kind == "wake":
                result = await actions.trigger_respawn(client, action.issue, action.agent_id)
                state.record_wake(action.issue.id, action.agent_id)
                log.info(
                    "wake_result issue=%s via=%s success=%s",
                    action.issue.id,
                    result.via,
                    result.success,
                )
                if not result.success:
                    log.error(
                        "wake_failed issue=%s — will retry next tick unless cap hit",
                        action.issue.id,
                    )
            elif action.kind == "escalate":
                state.record_escalation(action.issue.id, action.reason)
                log.warning(
                    "escalation issue=%s reason=%s count=%d permanent=%s",
                    action.issue.id,
                    action.reason,
                    state.escalation_count(action.issue.id),
                    state.is_permanently_escalated(action.issue.id),
                )
                if cfg.escalation.post_comment_on_issue:
                    body = _build_escalation_body(
                        action.issue.id, action.agent_id, state, cfg.escalation.comment_marker
                    )
                    try:
                        await client.post_issue_comment(action.issue.id, body)
                    except Exception as e:
                        log.error("escalation_comment_failed issue=%s error=%s", action.issue.id, e)
            elif action.kind == "skip":
                log.info("skip issue=%s reason=%s", action.issue.id, action.reason)
            total_actions += 1

    state.save()
    log.info("tick_end actions=%d", total_actions)


async def _run_one_iteration_for_test(cfg: Config, state: State, client: PaperclipClient) -> None:
    """Single iteration used by test_run_loop_exits_on_tick_timeout."""
    try:
        await asyncio.wait_for(_tick(cfg, state, client), timeout=TICK_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        log.error("tick_timeout_self_exit timeout_s=%d", TICK_TIMEOUT_SECONDS)
        sys.exit(1)
    except Exception:
        log.exception("tick_failed")


async def run(cfg: Config, state: State, client: PaperclipClient) -> None:
    """Persistent loop — called by CLI `run` command in launchd/systemd mode."""
    while True:
        tick_started = _dt.datetime.now(_dt.timezone.utc)
        try:
            await asyncio.wait_for(_tick(cfg, state, client), timeout=TICK_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            log.error("tick_timeout_self_exit timeout_s=%d", TICK_TIMEOUT_SECONDS)
            sys.exit(1)
        except Exception:
            log.exception("tick_failed")
        elapsed_s = (_dt.datetime.now(_dt.timezone.utc) - tick_started).total_seconds()
        await _sleep(max(0.0, cfg.daemon.poll_interval_seconds - elapsed_s))
