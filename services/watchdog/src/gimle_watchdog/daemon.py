"""Main daemon loop — orchestrates detection + actions + state per tick."""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from gimle_watchdog import actions, detection, detection_semantic
from gimle_watchdog.config import Config
from gimle_watchdog.detection_semantic import HandoffDetectionConfig
from gimle_watchdog.models import (
    CommentOnlyHandoffFinding,
    Finding,
    FindingType,
    InfraBlockFinding,
    OwnerlessCompletionFinding,
    ReviewOwnedByImplementerFinding,
    WrongAssigneeFinding,
)
from gimle_watchdog.paperclip import PaperclipClient
from gimle_watchdog.state import State

# Repo root: services/watchdog/src/gimle_watchdog/ → 4 parents up
_REPO_ROOT = Path(__file__).resolve().parents[4]

# Sentinel issue-id used as state key for global stale_bundle alert
_STALE_BUNDLE_KEY = "_global"


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


def _finding_snapshot(finding: Finding) -> dict[str, Any]:
    if isinstance(finding, CommentOnlyHandoffFinding):
        return {
            "assigneeAgentId": finding.current_assignee_id,
            "status": finding.issue_status,
            "mention_comment_id": finding.mention_comment_id,
            "mention_target_uuid": finding.mentioned_agent_id,
        }
    if isinstance(finding, WrongAssigneeFinding):
        return {"assigneeAgentId": finding.bogus_assignee_id, "status": finding.issue_status}
    assert isinstance(finding, ReviewOwnedByImplementerFinding)
    return {"assigneeAgentId": finding.implementer_assignee_id, "status": "in_review"}


def _alert_decision(
    state: State,
    issue_id: str,
    ftype: FindingType,
    snapshot: dict[str, Any],
    now_server: datetime,
    cooldown_min: int,
) -> str:
    """Return one of: "alert" / "skip_already_alerted" / "skip_cooldown".

    Caller emits the appropriate JSONL event per spec §4.9.
    """
    if state.has_active_alert(issue_id, ftype, snapshot):
        return "skip_already_alerted"
    key = f"{issue_id}:{ftype.value}"
    if key in state.alerted_handoffs:
        if state.cooldown_elapsed(issue_id, ftype, now_server, cooldown_min):
            return "alert"
        return "skip_cooldown"
    return "alert"  # first time → always alert


def _tier_snapshot(finding: Finding) -> dict[str, Any]:
    """Extract the snapshot dict for GIM-244 tier findings."""
    if isinstance(finding, OwnerlessCompletionFinding):
        return {"status": "done"}
    if isinstance(finding, InfraBlockFinding):
        return {"error_kind": finding.error_kind}
    return {}


async def _handle_tier_finding(
    state: State,
    client: PaperclipClient,
    finding: OwnerlessCompletionFinding | InfraBlockFinding,
    now_server: datetime,
    repair_delay_min: int,
    escalation_delay_min: int,
    auto_repair_enabled: bool,
    version: str,
) -> None:
    """Drive one finding through the 3-tier state machine for a single tick."""
    issue_id = finding.issue_id
    ftype = finding.type
    snapshot = _tier_snapshot(finding)

    existing_alerted_at = state.get_handoff_alerted_at(issue_id, ftype)
    if existing_alerted_at is None:
        # New finding — tier 1: post alert, record state
        actionable = getattr(finding, "actionable", True)
        state.record_handoff_alert(issue_id, ftype, snapshot, now_server, actionable=actionable)
        try:
            await client.post_issue_comment(
                issue_id,
                (
                    f"## Watchdog alert — {ftype}\n\n"
                    f"Detected at {now_server.isoformat().replace('+00:00', 'Z')}.\n"
                    f"Auto-repair will be attempted in {repair_delay_min} min "
                    f"(if `handoff_auto_repair_enabled`).\n\n"
                    f"<!-- watchdog-alert {ftype} -->"
                ),
            )
        except Exception as exc:
            log.warning("tier_alert_post_failed issue=%s ftype=%s error=%s", issue_id, ftype, exc)
        return

    # Snapshot mismatch → reset to tier 1 (condition changed)
    existing_snap = (state.alerted_handoffs.get(f"{issue_id}:{ftype.value}") or {}).get(
        "snapshot", {}
    )
    from gimle_watchdog.state import (
        _SNAPSHOT_KEYS,
    )  # local import to avoid circular  # noqa: PLC0415

    snap_keys = _SNAPSHOT_KEYS.get(ftype, ())
    if any(existing_snap.get(k) != snapshot.get(k) for k in snap_keys):
        actionable = getattr(finding, "actionable", True)
        state.record_handoff_alert(issue_id, ftype, snapshot, now_server, actionable=actionable)
        return

    elapsed_min = (now_server - existing_alerted_at).total_seconds() / 60
    current_tier = state.get_handoff_tier(issue_id, ftype)
    actionable = state.get_handoff_actionable(issue_id, ftype)

    # Determine expected tier
    if actionable and auto_repair_enabled:
        if elapsed_min >= escalation_delay_min:
            expected_tier = 3
        elif elapsed_min >= repair_delay_min:
            expected_tier = 2
        else:
            expected_tier = 1
    else:
        # Not actionable or auto_repair disabled → skip tier 2
        expected_tier = 3 if elapsed_min >= escalation_delay_min else 1

    if expected_tier <= current_tier:
        return  # no promotion needed

    if expected_tier == 2:
        state.promote_handoff_tier(issue_id, ftype, 2, now_server)
        repaired = False
        if isinstance(finding, OwnerlessCompletionFinding):
            repaired = await actions.repair_ownerless_completion(client, finding)
        if repaired:
            state.set_handoff_repaired(issue_id, ftype, now_server)
            state.clear_handoff_alert(issue_id, ftype)
            log.info("tier_repair_success issue=%s ftype=%s", issue_id, ftype.value)
        else:
            log.warning("tier_repair_failed issue=%s ftype=%s", issue_id, ftype.value)

    elif expected_tier == 3:
        # Skip to escalation
        if current_tier < 3:
            state.promote_handoff_tier(issue_id, ftype, 3, now_server)
        already_escalated = (state.alerted_handoffs.get(f"{issue_id}:{ftype.value}") or {}).get(
            "escalated_at"
        )
        if not already_escalated:
            await actions.post_tier_escalation(client, issue_id, ftype, version, now_server)
            state.set_handoff_escalated(issue_id, ftype, now_server)


async def _run_tier_pass(
    cfg: Config,
    state: State,
    client: PaperclipClient,
    now_server: datetime,
    repo_root: Path,
) -> None:
    """GIM-244: 3-tier detect→alert→repair→escalate for ownerless, infra_block, stale_bundle.
    Runs after the existing alert-only handoff pass.
    """
    h = cfg.handoff
    any_tier = (
        h.handoff_ownerless_enabled
        or h.handoff_infra_block_enabled
        or h.handoff_stale_bundle_enabled
    )
    if not any_tier:
        return

    for company in cfg.companies:
        try:
            # Collect issues for enabled detectors
            issues_to_scan: list[Any] = []
            if h.handoff_infra_block_enabled:
                issues_to_scan.extend(await client.list_active_issues(company.id))
            if h.handoff_ownerless_enabled:
                issues_to_scan.extend(await client.list_done_issues(company.id))

            seen_ids: set[str] = set()
            for issue in issues_to_scan:
                if issue.id in seen_ids:
                    continue
                seen_ids.add(issue.id)
                try:
                    comments = await client.list_recent_comments(
                        issue.id, h.handoff_ownerless_comment_limit
                    )
                    # Run enabled detectors (at most one finding per issue per tick)
                    finding: OwnerlessCompletionFinding | InfraBlockFinding | None = None
                    if h.handoff_ownerless_enabled and finding is None:
                        finding = detection_semantic._detect_ownerless_completion(issue, comments)
                    if h.handoff_infra_block_enabled and finding is None:
                        finding = detection_semantic._detect_infra_block(
                            issue, comments, now=now_server
                        )
                    if finding is not None:
                        await _handle_tier_finding(
                            state,
                            client,
                            finding,
                            now_server,
                            h.handoff_repair_delay_min,
                            h.handoff_escalation_delay_min,
                            h.handoff_auto_repair_enabled,
                            "watchdog",
                        )
                    else:
                        # No finding — clear any stale tier alerts for this issue
                        for ftype in (
                            FindingType.OWNERLESS_COMPLETION,
                            FindingType.INFRA_BLOCK,
                        ):
                            state.clear_handoff_alert(issue.id, ftype)
                except Exception as exc:
                    log.exception("tier_pass_issue_failed issue=%s error=%s", issue.id, repr(exc))
        except Exception as exc:
            log.exception("tier_pass_company_failed company=%s error=%s", company.id, repr(exc))

    # Stale-bundle check (global — not per-issue)
    if h.handoff_stale_bundle_enabled:
        deploy_log = repo_root / "paperclips" / "scripts" / "imac-agents-deploy.log"
        sb = detection_semantic.detect_stale_bundle(
            deploy_log, repo_root, h.handoff_stale_bundle_threshold_hours, now_server
        )
        if sb is not None:
            sb_snap = {"deployed_sha": sb.deployed_sha}
            if not state.has_active_alert(_STALE_BUNDLE_KEY, FindingType.STALE_BUNDLE, sb_snap):
                state.record_handoff_alert(
                    _STALE_BUNDLE_KEY, FindingType.STALE_BUNDLE, sb_snap, now_server
                )
            # Always post/update board comment (cheap and idempotent for ops visibility)
            if cfg.escalation.post_comment_on_issue and cfg.companies:
                board_issue_id = cfg.companies[0].id  # use first company id as sentinel
                await actions.post_stale_bundle_alert(
                    client, sb, board_issue_id, "watchdog", now_server
                )
        else:
            state.clear_handoff_alert(_STALE_BUNDLE_KEY, FindingType.STALE_BUNDLE)


async def _run_handoff_pass(
    cfg: Config,
    state: State,
    client: PaperclipClient,
    now_server: datetime,
) -> None:
    h = cfg.handoff
    if not h.handoff_alert_enabled:
        return

    det_cfg = HandoffDetectionConfig(
        handoff_alert_enabled=h.handoff_alert_enabled,
        handoff_comment_lookback_min=h.handoff_comment_lookback_min,
        handoff_wrong_assignee_min=h.handoff_wrong_assignee_min,
        handoff_review_owner_min=h.handoff_review_owner_min,
        handoff_comments_per_issue=h.handoff_comments_per_issue,
        handoff_max_issues_per_tick=h.handoff_max_issues_per_tick,
        handoff_alert_cooldown_min=h.handoff_alert_cooldown_min,
    )

    total_alerts = 0
    for company in cfg.companies:
        try:
            agents = await client.list_company_agents(company.id)
            hired_ids = frozenset(a.id for a in agents)
            name_by_id = {a.id: a.name for a in agents}
            issues = await client.list_active_issues(company.id)

            async def _fetch_comments(issue_id: str) -> list[Any]:
                return await client.list_recent_comments(
                    issue_id, det_cfg.handoff_comments_per_issue
                )

            findings = await detection_semantic.scan_handoff_inconsistencies(
                issues, _fetch_comments, hired_ids, name_by_id, det_cfg, now_server
            )
            issues_with_findings = {f.issue_id: f for f in findings}

            for issue in issues:
                finding = issues_with_findings.get(issue.id)
                if finding is None:
                    for ftype in FindingType:
                        if state.clear_handoff_alert(issue.id, ftype):
                            log.info(
                                "handoff_alert_state_cleared issue=%s type=%s",
                                issue.id,
                                ftype.value,
                                extra={
                                    "event": "handoff_alert_state_cleared",
                                    "issue_id": issue.id,
                                    "finding_type": ftype.value,
                                },
                            )
                    continue

                ftype = finding.type
                snapshot = _finding_snapshot(finding)
                decision = _alert_decision(
                    state, issue.id, ftype, snapshot, now_server, h.handoff_alert_cooldown_min
                )
                if decision == "skip_already_alerted":
                    continue
                if decision == "skip_cooldown":
                    log.info(
                        "handoff_alert_skipped_cooldown issue=%s type=%s cooldown_min=%d",
                        issue.id,
                        ftype.value,
                        h.handoff_alert_cooldown_min,
                        extra={
                            "event": "handoff_alert_skipped_cooldown",
                            "issue_id": issue.id,
                            "finding_type": ftype.value,
                            "cooldown_min": h.handoff_alert_cooldown_min,
                        },
                    )
                    continue

                assignee_id = snapshot.get("assigneeAgentId", "")
                assignee_name = name_by_id.get(assignee_id)
                result = await actions.post_handoff_alert(
                    client, finding, "watchdog", now_server, assignee_name
                )
                if result.posted:
                    state.record_handoff_alert(issue.id, ftype, snapshot, now_server)
                    total_alerts += 1
        except Exception as exc:
            log.exception(
                "handoff_pass_failed company=%s",
                company.id,
                extra={
                    "event": "handoff_pass_failed",
                    "company_id": company.id,
                    "error": repr(exc),
                },
            )

    log.info(
        "handoff_pass_complete alerts=%d",
        total_alerts,
        extra={"event": "handoff_pass_complete", "alerts": total_alerts},
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

    # Phase 3: handoff inconsistency detection (alert-only)
    # Spec §4.2.1: anchor "now" to server clock via the most recent
    # successful response Date header, not the local clock. Phase-2
    # GETs above already populate it; only fall back to local clock
    # if no successful response was made yet (cold first tick).
    now_server = client.last_response_date or _dt.datetime.now(_dt.timezone.utc)
    await _run_handoff_pass(cfg, state, client, now_server)

    # Phase 4: GIM-244 3-tier detectors (cross_team, ownerless, infra_block, stale_bundle)
    await _run_tier_pass(cfg, state, client, now_server, _REPO_ROOT)

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


async def run(cfg: Config, state: State, client: PaperclipClient) -> None:  # pragma: no cover
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
