"""Tests for watchdog.daemon — tick orchestration."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gimle_watchdog import daemon
from gimle_watchdog.actions import RespawnResult
from gimle_watchdog.config import (
    CompanyConfig,
    Config,
    CooldownsConfig,
    DaemonConfig,
    EscalationConfig,
    HandoffConfig,
    LoggingConfig,
    PaperclipConfig,
    Thresholds,
)
from gimle_watchdog.models import (
    AlertResult,
    FindingType,
    ReviewOwnedByImplementerFinding,
)

from gimle_watchdog.paperclip import Issue, PaperclipClient
from gimle_watchdog.state import State


def _cfg(tmp_path: Path) -> Config:
    return Config(
        version=1,
        paperclip=PaperclipConfig(base_url="http://x", api_key="k"),
        companies=[
            CompanyConfig(
                id="9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64",
                name="gimle",
                thresholds=Thresholds(
                    died_min=3,
                    hang_etime_min=60,
                    hang_cpu_max_s=None,
                    idle_cpu_ratio_max=0.005,
                    hang_stream_idle_max_s=300,
                ),
            )
        ],
        daemon=DaemonConfig(
            poll_interval_seconds=120,
            recovery_enabled=True,
            recovery_first_run_baseline_only=False,
            max_actions_per_tick=10,
        ),
        cooldowns=CooldownsConfig(
            per_issue_seconds=300, per_agent_cap=3, per_agent_window_seconds=900
        ),
        logging=LoggingConfig(
            path=tmp_path / "x.log", level="INFO", rotate_max_bytes=1048576, rotate_backup_count=1
        ),
        escalation=EscalationConfig(post_comment_on_issue=True, comment_marker="<!-- m -->"),
    )


def _stuck_issue() -> Issue:
    return Issue(
        id="issue-1",
        assignee_agent_id="agent-1",
        execution_run_id=None,
        status="in_progress",
        updated_at=datetime(2026, 4, 21, 9, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_tick_wakes_stuck_issue(tmp_path: Path):
    from freezegun import freeze_time

    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[_stuck_issue()])
    # Freeze near the stuck issue's updatedAt so recover_max_age_min cap (default 180) does not skip it.
    with freeze_time("2026-04-21T09:30:00Z"):
        with patch(
            "gimle_watchdog.daemon.actions.trigger_respawn",
            new=AsyncMock(return_value=RespawnResult(via="patch", success=True, run_id="run-new")),
        ):
            with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
                with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
                    await daemon._tick(cfg, state, client)
    # Wake recorded in state (cooldown check is time-sensitive and non-frozen-tz; just verify recorded)
    assert "issue-1" in state.issue_cooldowns


@pytest.mark.asyncio
async def test_tick_recovers_in_review_handoff_loss(tmp_path: Path):
    """GIM-216 end-to-end: in_review issue whose wake-event was lost gets
    release + repatch (real actions.trigger_respawn, not mocked) AND ends up
    with status=in_review preserved (not regressed to todo by /release)."""
    import dataclasses

    from freezegun import freeze_time

    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")

    in_review = Issue(
        id="issue-216",
        assignee_agent_id="cr-1",
        execution_run_id=None,
        status="in_review",
        updated_at=datetime(2026, 5, 6, 12, 42, tzinfo=timezone.utc),
        issue_number=216,
    )
    issue_no_run = dataclasses.replace(in_review)  # primary PATCH → still no spawn
    issue_with_run = dataclasses.replace(in_review, execution_run_id="run-cr-1")

    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[in_review])
    client.patch_issue = AsyncMock()
    client.post_release = AsyncMock()
    # Polls: 6 no-run after primary, then 6 with-run after fallback
    client.get_issue = AsyncMock(side_effect=[issue_no_run] * 6 + [issue_with_run] * 6)

    # 18 min after updatedAt — past died_min=3
    with freeze_time("2026-05-06T13:00:00Z"):
        with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
            with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
                with patch("gimle_watchdog.actions._sleep", new=AsyncMock()):
                    await daemon._tick(cfg, state, client)

    # Recovery: release + two PATCHes (primary then fallback with status restore)
    client.post_release.assert_awaited_once_with("issue-216")
    assert client.patch_issue.await_count == 2
    assert client.patch_issue.await_args_list[0].args == (
        "issue-216",
        {"assigneeAgentId": "cr-1"},
    )
    # Crucial: fallback PATCH carries status=in_review (NOT defaulted to todo)
    assert client.patch_issue.await_args_list[1].args == (
        "issue-216",
        {"assigneeAgentId": "cr-1", "status": "in_review"},
    )
    # Wake recorded in state (recovery happened, cooldown tracked)
    assert "issue-216" in state.issue_cooldowns


@pytest.mark.asyncio
async def test_tick_escalates_capped_agent(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    from freezegun import freeze_time

    for ts in ["2026-04-21T09:55:00Z", "2026-04-21T09:57:00Z", "2026-04-21T09:58:00Z"]:
        with freeze_time(ts):
            state.record_wake(f"dummy-{ts}", "agent-1")
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[_stuck_issue()])
    client.post_issue_comment = AsyncMock()
    with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
        with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
            with freeze_time("2026-04-21T10:05:00Z"):
                await daemon._tick(cfg, state, client)
    assert state.is_escalated("issue-1")
    client.post_issue_comment.assert_awaited_once()


@pytest.mark.asyncio
async def test_tick_kills_hanged_procs(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    from gimle_watchdog.detection import HangedProc

    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[])
    hanged = HangedProc(
        pid=12345,
        etime_s=5000,
        cpu_s=10,
        cpu_ratio=0.002,
        command="paperclip-skills append-system-prompt-file",
    )
    kill_mock = AsyncMock(return_value=MagicMock(status="clean", pid=12345))
    with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[hanged]):
        with patch("gimle_watchdog.daemon.actions.kill_hanged_proc", kill_mock):
            with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
                await daemon._tick(cfg, state, client)
    kill_mock.assert_called_once_with(hanged)


@pytest.mark.asyncio
async def test_run_loop_exits_on_tick_timeout(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    client = MagicMock()

    import asyncio

    async def hang(*a: object, **kw: object) -> None:
        await asyncio.sleep(120)

    with patch("gimle_watchdog.daemon._tick", new=hang):
        with patch("gimle_watchdog.daemon.TICK_TIMEOUT_SECONDS", 1):
            with patch("sys.exit") as mock_exit:
                await daemon._run_one_iteration_for_test(cfg, state, client)
                mock_exit.assert_called_with(1)


def test_build_escalation_body_non_permanent(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    state.record_escalation("issue-5", "no_run")
    body = daemon._build_escalation_body("issue-5", "agent-5", state, cfg.escalation.comment_marker)
    assert "agent-5" in body
    assert "auto-unescalate" in body
    assert "PERMANENT" not in body


def test_build_escalation_body_permanent(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    for _ in range(4):
        state.record_escalation("issue-6", "no_run")
    body = daemon._build_escalation_body("issue-6", "agent-6", state, cfg.escalation.comment_marker)
    assert "PERMANENT" in body
    assert "unescalate" in body


@pytest.mark.asyncio
async def test_sleep_delegates_to_asyncio():
    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await daemon._sleep(1.5)
    mock_sleep.assert_awaited_once_with(1.5)


@pytest.mark.asyncio
async def test_tick_logs_wake_failure(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[_stuck_issue()])
    failed = RespawnResult(via="patch", success=False, run_id=None)
    with patch("gimle_watchdog.daemon.actions.trigger_respawn", new=AsyncMock(return_value=failed)):
        with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
            with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
                await daemon._tick(cfg, state, client)


@pytest.mark.asyncio
async def test_tick_escalation_comment_failure_swallowed(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    from freezegun import freeze_time

    for ts in ["2026-04-21T09:55:00Z", "2026-04-21T09:57:00Z", "2026-04-21T09:58:00Z"]:
        with freeze_time(ts):
            state.record_wake(f"dup-{ts}", "agent-1")
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[_stuck_issue()])
    client.post_issue_comment = AsyncMock(side_effect=RuntimeError("network"))
    with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
        with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
            with freeze_time("2026-04-21T10:05:00Z"):
                # Should not raise even if comment posting fails
                await daemon._tick(cfg, state, client)
    assert state.is_escalated("issue-1")


@pytest.mark.asyncio
async def test_tick_skip_action_cooldown(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    state.record_wake("issue-1", "agent-1")  # put issue in cooldown
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[_stuck_issue()])
    with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
        with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
            await daemon._tick(cfg, state, client)
    assert state.is_issue_in_cooldown("issue-1", cfg.cooldowns.per_issue_seconds)


@pytest.mark.asyncio
async def test_tick_recovery_disabled_skips_respawn(tmp_path: Path):
    cfg = _cfg(tmp_path)
    cfg = Config(
        version=cfg.version,
        paperclip=cfg.paperclip,
        companies=cfg.companies,
        daemon=DaemonConfig(
            poll_interval_seconds=cfg.daemon.poll_interval_seconds,
            recovery_enabled=False,
            recovery_first_run_baseline_only=True,
            max_actions_per_tick=1,
        ),
        cooldowns=cfg.cooldowns,
        logging=cfg.logging,
        escalation=cfg.escalation,
        handoff=cfg.handoff,
    )
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[_stuck_issue()])
    with patch("gimle_watchdog.daemon.actions.trigger_respawn", new=AsyncMock()) as mock_respawn:
        with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
            await daemon._tick(cfg, state, client)
    mock_respawn.assert_not_awaited()
    assert state.issue_cooldowns == {}


@pytest.mark.asyncio
async def test_tick_recovery_first_run_baseline_only_seeds_cooldown(tmp_path: Path):
    from freezegun import freeze_time

    cfg = _cfg(tmp_path)
    cfg = Config(
        version=cfg.version,
        paperclip=cfg.paperclip,
        companies=cfg.companies,
        daemon=DaemonConfig(
            poll_interval_seconds=cfg.daemon.poll_interval_seconds,
            recovery_enabled=True,
            recovery_first_run_baseline_only=True,
            max_actions_per_tick=10,
        ),
        cooldowns=cfg.cooldowns,
        logging=cfg.logging,
        escalation=cfg.escalation,
        handoff=cfg.handoff,
    )
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[_stuck_issue()])
    with patch("gimle_watchdog.daemon.actions.trigger_respawn", new=AsyncMock()) as mock_respawn:
        with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
            with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
                with patch("gimle_watchdog.actions._sleep", new=AsyncMock()):
                    with freeze_time("2026-04-21T09:30:00Z"):
                        client.last_response_date = None
                        await daemon._tick(cfg, state, client)
    mock_respawn.assert_not_awaited()
    assert "issue-1" in state.issue_cooldowns
    assert state.recovery_baseline_completed is True


@pytest.mark.asyncio
async def test_tick_recovery_dry_run_scans_without_acting_persistently(tmp_path: Path):
    """recovery_dry_run=True scans + logs candidates every tick without
    persisting baseline_completed, so subsequent ticks stay in scan-only mode."""
    from freezegun import freeze_time

    cfg = _cfg(tmp_path)
    cfg = Config(
        version=cfg.version,
        paperclip=cfg.paperclip,
        companies=cfg.companies,
        daemon=DaemonConfig(
            poll_interval_seconds=cfg.daemon.poll_interval_seconds,
            recovery_enabled=False,
            recovery_first_run_baseline_only=False,
            recovery_dry_run=True,
            max_actions_per_tick=10,
        ),
        cooldowns=cfg.cooldowns,
        logging=cfg.logging,
        escalation=cfg.escalation,
        handoff=cfg.handoff,
    )
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[_stuck_issue()])
    with patch("gimle_watchdog.daemon.actions.trigger_respawn", new=AsyncMock()) as mock_respawn:
        with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
            with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
                with patch("gimle_watchdog.actions._sleep", new=AsyncMock()):
                    with freeze_time("2026-04-21T09:30:00Z"):
                        client.last_response_date = None
                        # Run twice — dry_run must NOT flip baseline_completed
                        await daemon._tick(cfg, state, client)
                        await daemon._tick(cfg, state, client)
    mock_respawn.assert_not_awaited()
    assert state.recovery_baseline_completed is False  # never completes in dry_run


@pytest.mark.asyncio
async def test_tick_recovery_respects_max_actions_per_tick(tmp_path: Path):
    from freezegun import freeze_time

    cfg = _cfg(tmp_path)
    cfg = Config(
        version=cfg.version,
        paperclip=cfg.paperclip,
        companies=cfg.companies,
        daemon=DaemonConfig(
            poll_interval_seconds=cfg.daemon.poll_interval_seconds,
            recovery_enabled=True,
            recovery_first_run_baseline_only=False,
            max_actions_per_tick=1,
        ),
        cooldowns=cfg.cooldowns,
        logging=cfg.logging,
        escalation=cfg.escalation,
        handoff=cfg.handoff,
    )
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.list_active_issues = AsyncMock(
        return_value=[
            _stuck_issue(),
            Issue(
                id="issue-2",
                assignee_agent_id="agent-2",
                execution_run_id=None,
                status="in_progress",
                updated_at=datetime(2026, 4, 21, 9, 0, tzinfo=timezone.utc),
            ),
        ]
    )
    with patch(
        "gimle_watchdog.daemon.actions.trigger_respawn",
        new=AsyncMock(return_value=RespawnResult(via="patch", success=True, run_id="run-new")),
    ) as mock_respawn:
        with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
            with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
                with patch("gimle_watchdog.actions._sleep", new=AsyncMock()):
                    with freeze_time("2026-04-21T09:30:00Z"):
                        client.last_response_date = None
                        await daemon._tick(cfg, state, client)
    assert mock_respawn.await_count == 1


@pytest.mark.asyncio
async def test_tick_escalation_no_comment(tmp_path: Path):
    from freezegun import freeze_time

    cfg_no_comment = _cfg(tmp_path)
    # Rebuild config with post_comment_on_issue=False
    cfg_no_comment = Config(
        version=cfg_no_comment.version,
        paperclip=cfg_no_comment.paperclip,
        companies=cfg_no_comment.companies,
        daemon=cfg_no_comment.daemon,
        cooldowns=cfg_no_comment.cooldowns,
        logging=cfg_no_comment.logging,
        escalation=EscalationConfig(post_comment_on_issue=False, comment_marker="<!-- m -->"),
    )
    state = State.load(tmp_path / "state.json")
    for ts in ["2026-04-21T09:55:00Z", "2026-04-21T09:57:00Z", "2026-04-21T09:58:00Z"]:
        with freeze_time(ts):
            state.record_wake(f"nocom-{ts}", "agent-1")
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[_stuck_issue()])
    client.post_issue_comment = AsyncMock()
    with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
        with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
            with freeze_time("2026-04-21T10:05:00Z"):
                await daemon._tick(cfg_no_comment, state, client)
    assert state.is_escalated("issue-1")
    client.post_issue_comment.assert_not_called()


@pytest.mark.asyncio
async def test_run_one_iteration_tick_exception(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    client = MagicMock()

    async def fail(*a: object, **kw: object) -> None:
        raise RuntimeError("unexpected")

    with patch("gimle_watchdog.daemon._tick", new=fail):
        # Should not raise — exception is swallowed and logged
        await daemon._run_one_iteration_for_test(cfg, state, client)


# --- T7: _run_handoff_pass tests -----------------------------------------------

_NOW_SERVER = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)
_COMPANY_ID = "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
_PE_ID = "127068ee-b564-4b37-9370-616c81c63f35"
_CR_ID = "bd2d7e20-7ed8-474c-91fc-353d610f4c52"


def _handoff_cfg(tmp_path: Path, enabled: bool = True) -> Config:
    base = _cfg(tmp_path)
    return Config(
        version=base.version,
        paperclip=base.paperclip,
        companies=base.companies,
        daemon=base.daemon,
        cooldowns=base.cooldowns,
        logging=base.logging,
        escalation=base.escalation,
        handoff=HandoffConfig(
            handoff_alert_enabled=enabled,
            handoff_comment_lookback_min=5,
            handoff_wrong_assignee_min=3,
            handoff_review_owner_min=5,
            handoff_comments_per_issue=5,
            handoff_max_issues_per_tick=30,
            handoff_alert_cooldown_min=30,
        ),
    )


def _in_review_issue() -> Issue:
    return Issue(
        id="issue-42",
        assignee_agent_id=_PE_ID,
        execution_run_id=None,
        status="in_review",
        updated_at=datetime(2026, 5, 3, 11, 0, tzinfo=timezone.utc),
        issue_number=42,
    )


def _ro_finding() -> ReviewOwnedByImplementerFinding:
    return ReviewOwnedByImplementerFinding(
        type=FindingType.REVIEW_OWNED_BY_IMPLEMENTER,
        issue_id="issue-42",
        issue_number=42,
        implementer_assignee_id=_PE_ID,
        implementer_role_name="PythonEngineer",
        implementer_role_class="implementer",
        age_seconds=3600,
    )


@pytest.mark.asyncio
async def test_handoff_pass_disabled_skips(tmp_path: Path):
    """When handoff_alert_enabled=False, scan is never called."""
    cfg = _handoff_cfg(tmp_path, enabled=False)
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[])
    client.list_company_agents = AsyncMock(return_value=[])

    with patch(
        "gimle_watchdog.daemon.detection_semantic.scan_handoff_inconsistencies",
        new=AsyncMock(return_value=[]),
    ) as mock_scan:
        await daemon._run_handoff_pass(cfg, state, client, _NOW_SERVER)
    mock_scan.assert_not_awaited()


@pytest.mark.asyncio
async def test_handoff_pass_posts_alert_first_time(tmp_path: Path):
    """No prior entry → post_handoff_alert is called once."""
    cfg = _handoff_cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[_in_review_issue()])
    client.list_company_agents = AsyncMock(return_value=[])
    client.list_recent_comments = AsyncMock(return_value=[])

    posted = AlertResult(
        finding_type=FindingType.REVIEW_OWNED_BY_IMPLEMENTER,
        issue_id="issue-42",
        posted=True,
        comment_id="cmt-1",
        error=None,
    )
    with patch(
        "gimle_watchdog.daemon.detection_semantic.scan_handoff_inconsistencies",
        new=AsyncMock(return_value=[_ro_finding()]),
    ):
        with patch(
            "gimle_watchdog.daemon.actions.post_handoff_alert", new=AsyncMock(return_value=posted)
        ) as mock_post:
            await daemon._run_handoff_pass(cfg, state, client, _NOW_SERVER)
    mock_post.assert_awaited_once()


@pytest.mark.asyncio
async def test_handoff_pass_skips_active_alert_same_snapshot(tmp_path: Path):
    """Identical snapshot already alerted → post_handoff_alert not called again."""
    cfg = _handoff_cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    # Pre-populate state with a matching alert entry
    snapshot = {"assigneeAgentId": _PE_ID, "status": "in_review"}
    state.record_handoff_alert(
        "issue-42",
        FindingType.REVIEW_OWNED_BY_IMPLEMENTER,
        snapshot,
        _NOW_SERVER,
    )
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[_in_review_issue()])
    client.list_company_agents = AsyncMock(return_value=[])
    client.list_recent_comments = AsyncMock(return_value=[])

    with patch(
        "gimle_watchdog.daemon.detection_semantic.scan_handoff_inconsistencies",
        new=AsyncMock(return_value=[_ro_finding()]),
    ):
        with patch(
            "gimle_watchdog.daemon.actions.post_handoff_alert", new=AsyncMock()
        ) as mock_post:
            await daemon._run_handoff_pass(cfg, state, client, _NOW_SERVER)
    mock_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_handoff_pass_respects_cooldown(tmp_path: Path):
    """Snapshot changed but cooldown not elapsed → post not called."""
    cfg = _handoff_cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    # Old snapshot (different assignee), alerted 5 min ago (cooldown=30)
    old_snapshot = {"assigneeAgentId": "old-agent", "status": "in_review"}
    alert_time = datetime(2026, 5, 3, 11, 55, tzinfo=timezone.utc)  # 5 min ago
    state.record_handoff_alert(
        "issue-42",
        FindingType.REVIEW_OWNED_BY_IMPLEMENTER,
        old_snapshot,
        alert_time,
    )
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[_in_review_issue()])
    client.list_company_agents = AsyncMock(return_value=[])
    client.list_recent_comments = AsyncMock(return_value=[])

    with patch(
        "gimle_watchdog.daemon.detection_semantic.scan_handoff_inconsistencies",
        new=AsyncMock(return_value=[_ro_finding()]),
    ):
        with patch(
            "gimle_watchdog.daemon.actions.post_handoff_alert", new=AsyncMock()
        ) as mock_post:
            await daemon._run_handoff_pass(cfg, state, client, _NOW_SERVER)
    mock_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_handoff_pass_re_alerts_after_cooldown(tmp_path: Path):
    """Snapshot changed AND cooldown elapsed → re-alerts."""
    cfg = _handoff_cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    old_snapshot = {"assigneeAgentId": "old-agent", "status": "in_review"}
    # Alerted 60 min ago (past cooldown_min=30)
    alert_time = datetime(2026, 5, 3, 11, 0, tzinfo=timezone.utc)
    state.record_handoff_alert(
        "issue-42",
        FindingType.REVIEW_OWNED_BY_IMPLEMENTER,
        old_snapshot,
        alert_time,
    )
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[_in_review_issue()])
    client.list_company_agents = AsyncMock(return_value=[])
    client.list_recent_comments = AsyncMock(return_value=[])

    posted = AlertResult(
        finding_type=FindingType.REVIEW_OWNED_BY_IMPLEMENTER,
        issue_id="issue-42",
        posted=True,
        comment_id="cmt-2",
        error=None,
    )
    with patch(
        "gimle_watchdog.daemon.detection_semantic.scan_handoff_inconsistencies",
        new=AsyncMock(return_value=[_ro_finding()]),
    ):
        with patch(
            "gimle_watchdog.daemon.actions.post_handoff_alert", new=AsyncMock(return_value=posted)
        ) as mock_post:
            await daemon._run_handoff_pass(cfg, state, client, _NOW_SERVER)
    mock_post.assert_awaited_once()


@pytest.mark.asyncio
async def test_handoff_pass_clears_stale_entry_when_no_finding(tmp_path: Path):
    """Issue has no finding anymore → alert entry cleared from state."""
    cfg = _handoff_cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    snapshot = {"assigneeAgentId": _PE_ID, "status": "in_review"}
    state.record_handoff_alert(
        "issue-42",
        FindingType.REVIEW_OWNED_BY_IMPLEMENTER,
        snapshot,
        _NOW_SERVER,
    )
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[_in_review_issue()])
    client.list_company_agents = AsyncMock(return_value=[])
    client.list_recent_comments = AsyncMock(return_value=[])

    with patch(
        "gimle_watchdog.daemon.detection_semantic.scan_handoff_inconsistencies",
        new=AsyncMock(return_value=[]),  # no findings
    ):
        await daemon._run_handoff_pass(cfg, state, client, _NOW_SERVER)

    assert not state.has_active_alert("issue-42", FindingType.REVIEW_OWNED_BY_IMPLEMENTER, snapshot)


@pytest.mark.asyncio
async def test_handoff_pass_isolates_per_company_errors(tmp_path: Path):
    """Exception during agent fetch for one company doesn't raise to caller."""
    cfg = _handoff_cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.list_company_agents = AsyncMock(side_effect=RuntimeError("network"))

    # Should not raise
    await daemon._run_handoff_pass(cfg, state, client, _NOW_SERVER)


@pytest.mark.asyncio
async def test_tick_calls_handoff_pass_when_enabled(tmp_path: Path):
    """_tick calls _run_handoff_pass when handoff_alert_enabled=True."""
    cfg = _handoff_cfg(tmp_path, enabled=True)
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[])

    with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
        with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
            with patch("gimle_watchdog.daemon._run_handoff_pass", new=AsyncMock()) as mock_pass:
                await daemon._tick(cfg, state, client)
    mock_pass.assert_awaited_once()


@pytest.mark.asyncio
async def test_handoff_pass_logs_pass_complete_event(tmp_path: Path, caplog):
    """JSONL event 'handoff_pass_complete' is logged after the pass."""
    import logging

    cfg = _handoff_cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[])
    client.list_company_agents = AsyncMock(return_value=[])

    with patch(
        "gimle_watchdog.daemon.detection_semantic.scan_handoff_inconsistencies",
        new=AsyncMock(return_value=[]),
    ):
        with caplog.at_level(logging.INFO, logger="watchdog.daemon"):
            await daemon._run_handoff_pass(cfg, state, client, _NOW_SERVER)

    events = [r for r in caplog.records if getattr(r, "event", None) == "handoff_pass_complete"]
    assert len(events) == 1


# ---------------------------------------------------------------------------
# GIM-183: missing JSONL events from spec §4.9 + e2e lifecycle + server-Date
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handoff_alert_state_cleared_emits_event(tmp_path: Path, caplog):
    """Pre-existing alert entry, finding now absent → JSONL event emitted."""
    import logging

    cfg = _handoff_cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    snapshot = {"assigneeAgentId": _PE_ID, "status": "in_review"}
    state.record_handoff_alert(
        "issue-42",
        FindingType.REVIEW_OWNED_BY_IMPLEMENTER,
        snapshot,
        _NOW_SERVER,
    )
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[_in_review_issue()])
    client.list_company_agents = AsyncMock(return_value=[])
    client.list_recent_comments = AsyncMock(return_value=[])

    with patch(
        "gimle_watchdog.daemon.detection_semantic.scan_handoff_inconsistencies",
        new=AsyncMock(return_value=[]),  # no findings → trigger clear path
    ):
        with caplog.at_level(logging.INFO, logger="watchdog.daemon"):
            await daemon._run_handoff_pass(cfg, state, client, _NOW_SERVER)

    cleared = [
        r for r in caplog.records if getattr(r, "event", None) == "handoff_alert_state_cleared"
    ]
    assert len(cleared) == 1
    assert cleared[0].issue_id == "issue-42"
    assert cleared[0].finding_type == FindingType.REVIEW_OWNED_BY_IMPLEMENTER.value


@pytest.mark.asyncio
async def test_handoff_alert_state_cleared_silent_when_nothing_to_clear(tmp_path: Path, caplog):
    """No pre-existing alert, finding absent → no clear event (no-op)."""
    import logging

    cfg = _handoff_cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[_in_review_issue()])
    client.list_company_agents = AsyncMock(return_value=[])
    client.list_recent_comments = AsyncMock(return_value=[])

    with patch(
        "gimle_watchdog.daemon.detection_semantic.scan_handoff_inconsistencies",
        new=AsyncMock(return_value=[]),
    ):
        with caplog.at_level(logging.INFO, logger="watchdog.daemon"):
            await daemon._run_handoff_pass(cfg, state, client, _NOW_SERVER)

    cleared = [
        r for r in caplog.records if getattr(r, "event", None) == "handoff_alert_state_cleared"
    ]
    assert cleared == []


@pytest.mark.asyncio
async def test_handoff_alert_skipped_cooldown_emits_event(tmp_path: Path, caplog):
    """Snapshot mismatch + cooldown not elapsed → JSONL event emitted."""
    import logging
    from datetime import timedelta

    cfg = _handoff_cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    # Pre-existing entry with a DIFFERENT snapshot, alerted only 5 minutes ago
    # (cooldown is 30 min in _handoff_cfg, so not elapsed).
    old_snapshot = {"assigneeAgentId": "old-agent", "status": "in_review"}
    state.record_handoff_alert(
        "issue-42",
        FindingType.REVIEW_OWNED_BY_IMPLEMENTER,
        old_snapshot,
        _NOW_SERVER - timedelta(minutes=5),
    )
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[_in_review_issue()])
    client.list_company_agents = AsyncMock(return_value=[])
    client.list_recent_comments = AsyncMock(return_value=[])

    with patch(
        "gimle_watchdog.daemon.detection_semantic.scan_handoff_inconsistencies",
        new=AsyncMock(return_value=[_ro_finding()]),
    ):
        with patch(
            "gimle_watchdog.daemon.actions.post_handoff_alert", new=AsyncMock()
        ) as mock_post:
            with caplog.at_level(logging.INFO, logger="watchdog.daemon"):
                await daemon._run_handoff_pass(cfg, state, client, _NOW_SERVER)

    skipped = [
        r for r in caplog.records if getattr(r, "event", None) == "handoff_alert_skipped_cooldown"
    ]
    assert len(skipped) == 1
    assert skipped[0].issue_id == "issue-42"
    assert skipped[0].cooldown_min == 30
    mock_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_handoff_pass_failed_emits_event_on_company_error(tmp_path: Path, caplog):
    """Per-company exception → JSONL `handoff_pass_failed` with company_id + error."""
    import logging

    cfg = _handoff_cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.list_company_agents = AsyncMock(side_effect=RuntimeError("network drop"))

    with caplog.at_level(logging.ERROR, logger="watchdog.daemon"):
        await daemon._run_handoff_pass(cfg, state, client, _NOW_SERVER)

    failed = [r for r in caplog.records if getattr(r, "event", None) == "handoff_pass_failed"]
    assert len(failed) == 1
    assert "network drop" in failed[0].error


@pytest.mark.asyncio
async def test_handoff_pass_failed_for_issue_emits_event(tmp_path: Path, caplog):
    """Per-issue exception inside scan_handoff_inconsistencies → JSONL event."""
    import logging

    from gimle_watchdog import detection_semantic as ds

    # Build a minimal Issue + a fetch_comments that raises for it.
    issue = _in_review_issue()

    async def boom_fetch(_: str) -> list:
        raise RuntimeError("comment fetch failed")

    det_cfg = ds.HandoffDetectionConfig(
        handoff_alert_enabled=True,
        handoff_comment_lookback_min=5,
        handoff_wrong_assignee_min=3,
        handoff_review_owner_min=5,
        handoff_comments_per_issue=5,
        handoff_max_issues_per_tick=30,
        handoff_alert_cooldown_min=30,
        handoff_recent_window_min=180,
        handoff_alert_soft_budget_per_tick=5,
        handoff_alert_hard_budget_per_tick=20,
    )

    # Hired ids include the assignee so wrong_assignee does NOT fire and
    # fetch_comments gets called, raising and triggering the per-issue
    # except block we want to test.
    hired = frozenset({_PE_ID})

    with caplog.at_level(logging.ERROR, logger="gimle_watchdog.detection_semantic"):
        findings = await ds.scan_handoff_inconsistencies(
            [issue],
            boom_fetch,
            hired,
            {},
            det_cfg,
            _NOW_SERVER,
        )

    # Pass continues; finding list empty for the failing issue.
    assert findings == []
    per_issue = [
        r for r in caplog.records if getattr(r, "event", None) == "handoff_pass_failed_for_issue"
    ]
    assert len(per_issue) == 1
    assert per_issue[0].issue_id == issue.id


@pytest.mark.asyncio
async def test_tick_uses_client_last_response_date_not_local_clock(tmp_path: Path):
    """_tick reads now_server from client.last_response_date when available
    (spec §4.2.1 server-clock anchoring)."""
    cfg = _handoff_cfg(tmp_path, enabled=True)
    state = State.load(tmp_path / "state.json")
    server_now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)

    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[])
    # Property-style mock for last_response_date.
    type(client).last_response_date = server_now  # type: ignore[misc]

    captured: dict[str, datetime] = {}

    async def _capture(_cfg, _state, _client, now_server, budget=None):
        captured["now_server"] = now_server

    with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
        with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
            with patch("gimle_watchdog.daemon._run_handoff_pass", new=_capture):
                await daemon._tick(cfg, state, client)

    assert captured["now_server"] == server_now


@pytest.mark.asyncio
async def test_tick_falls_back_to_local_clock_when_no_response_date(tmp_path: Path):
    """When client has not yet captured a Date header (cold first tick),
    daemon falls back to local clock — spec §4.2.1 fallback path."""
    cfg = _handoff_cfg(tmp_path, enabled=True)
    state = State.load(tmp_path / "state.json")

    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[])
    type(client).last_response_date = None  # type: ignore[misc]

    captured: dict[str, datetime] = {}

    async def _capture(_cfg, _state, _client, now_server, budget=None):
        captured["now_server"] = now_server

    with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
        with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
            with patch("gimle_watchdog.daemon._run_handoff_pass", new=_capture):
                await daemon._tick(cfg, state, client)

    # Fallback: any tz-aware datetime; we just assert it's not None.
    assert captured["now_server"] is not None
    assert captured["now_server"].tzinfo is not None


@pytest.mark.asyncio
async def test_tick_e2e_lifecycle(tmp_path: Path, caplog):
    """End-to-end: alert → assignee fixed (cleared) → assignee broken again (re-alert).

    Walks through a full state-machine cycle within a single test using three
    successive `_run_handoff_pass` calls. Covers the contract that GIM-183 spec
    §4.4 declares: edge-triggered + cooldown + state clearing.
    """
    import logging
    from datetime import timedelta

    cfg = _handoff_cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[_in_review_issue()])
    client.list_company_agents = AsyncMock(return_value=[])
    client.list_recent_comments = AsyncMock(return_value=[])

    posted = AlertResult(
        finding_type=FindingType.REVIEW_OWNED_BY_IMPLEMENTER,
        issue_id="issue-42",
        posted=True,
        comment_id="cmt-1",
        error=None,
    )

    # Phase 1: finding active → expect alert.
    t1 = _NOW_SERVER
    with patch(
        "gimle_watchdog.daemon.detection_semantic.scan_handoff_inconsistencies",
        new=AsyncMock(return_value=[_ro_finding()]),
    ):
        with patch(
            "gimle_watchdog.daemon.actions.post_handoff_alert",
            new=AsyncMock(return_value=posted),
        ) as mock_post_1:
            with caplog.at_level(logging.INFO, logger="watchdog.daemon"):
                await daemon._run_handoff_pass(cfg, state, client, t1)
    assert mock_post_1.await_count == 1
    snapshot_1 = {"assigneeAgentId": _PE_ID, "status": "in_review"}
    assert state.has_active_alert("issue-42", FindingType.REVIEW_OWNED_BY_IMPLEMENTER, snapshot_1)

    # Phase 2: finding gone (operator reassigned) → expect state cleared.
    caplog.clear()
    t2 = t1 + timedelta(minutes=2)
    with patch(
        "gimle_watchdog.daemon.detection_semantic.scan_handoff_inconsistencies",
        new=AsyncMock(return_value=[]),
    ):
        with patch(
            "gimle_watchdog.daemon.actions.post_handoff_alert", new=AsyncMock()
        ) as mock_post_2:
            with caplog.at_level(logging.INFO, logger="watchdog.daemon"):
                await daemon._run_handoff_pass(cfg, state, client, t2)
    mock_post_2.assert_not_awaited()
    cleared = [
        r for r in caplog.records if getattr(r, "event", None) == "handoff_alert_state_cleared"
    ]
    assert len(cleared) == 1
    assert not state.has_active_alert(
        "issue-42", FindingType.REVIEW_OWNED_BY_IMPLEMENTER, snapshot_1
    )

    # Phase 3: finding reactivates (operator re-broke) → expect re-alert
    # (no cooldown gating because state was cleared, so this is a "first time"
    # alert from the state-machine's perspective).
    caplog.clear()
    t3 = t2 + timedelta(minutes=10)
    with patch(
        "gimle_watchdog.daemon.detection_semantic.scan_handoff_inconsistencies",
        new=AsyncMock(return_value=[_ro_finding()]),
    ):
        with patch(
            "gimle_watchdog.daemon.actions.post_handoff_alert",
            new=AsyncMock(return_value=posted),
        ) as mock_post_3:
            with caplog.at_level(logging.INFO, logger="watchdog.daemon"):
                await daemon._run_handoff_pass(cfg, state, client, t3)
    assert mock_post_3.await_count == 1
    assert state.has_active_alert("issue-42", FindingType.REVIEW_OWNED_BY_IMPLEMENTER, snapshot_1)


@pytest.mark.asyncio
async def test_handoff_pass_enforces_shared_soft_and_hard_budget(tmp_path: Path, caplog):
    import logging

    cfg = _handoff_cfg(tmp_path)
    cfg = Config(
        version=cfg.version,
        paperclip=cfg.paperclip,
        companies=cfg.companies,
        daemon=cfg.daemon,
        cooldowns=cfg.cooldowns,
        logging=cfg.logging,
        escalation=cfg.escalation,
        handoff=HandoffConfig(
            **{
                **cfg.handoff.__dict__,
                "handoff_alert_soft_budget_per_tick": 5,
                "handoff_alert_hard_budget_per_tick": 8,
            }
        ),
    )
    state = State.load(tmp_path / "state.json")
    issues = [
        Issue(
            id=f"issue-{n}",
            assignee_agent_id=_PE_ID,
            execution_run_id=None,
            status="in_review",
            updated_at=datetime(2026, 5, 3, 11, 0, tzinfo=timezone.utc),
            issue_number=n,
        )
        for n in range(10)
    ]
    findings = [
        ReviewOwnedByImplementerFinding(
            type=FindingType.REVIEW_OWNED_BY_IMPLEMENTER,
            issue_id=issue.id,
            issue_number=issue.issue_number,
            implementer_assignee_id=_PE_ID,
            implementer_role_name="PythonEngineer",
            implementer_role_class="implementer",
            age_seconds=3600,
        )
        for issue in issues
    ]
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=issues)
    client.list_company_agents = AsyncMock(return_value=[])
    client.list_recent_comments = AsyncMock(return_value=[])

    async def _post(*args, **kwargs) -> AlertResult:
        finding = args[1]
        return AlertResult(
            finding_type=finding.type,
            issue_id=finding.issue_id,
            posted=True,
            comment_id=f"comment-{finding.issue_id}",
            error=None,
        )

    with patch(
        "gimle_watchdog.daemon.detection_semantic.scan_handoff_inconsistencies",
        new=AsyncMock(return_value=findings),
    ):
        with patch(
            "gimle_watchdog.daemon.actions.post_handoff_alert", new=AsyncMock(side_effect=_post)
        ) as mock_post:
            with caplog.at_level(logging.WARNING, logger="watchdog.daemon"):
                await daemon._run_handoff_pass(
                    cfg,
                    state,
                    client,
                    _NOW_SERVER,
                    budget=daemon.AlertPostBudget(soft_limit=5, hard_limit=8),
                )

    assert mock_post.await_count == 8
    assert len(state.alerted_handoffs) == 8
    soft_logs = [r for r in caplog.records if "handoff_alert_soft_budget_reached" in r.message]
    deferred_logs = [r for r in caplog.records if "handoff_alert_deferred_budget" in r.message]
    assert len(soft_logs) == 1
    assert len(deferred_logs) == 2


@pytest.mark.asyncio
async def test_tier_alert_failure_does_not_record_state(tmp_path: Path):
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.post_issue_comment = AsyncMock(side_effect=RuntimeError("network"))
    finding = daemon.CrossTeamHandoffFinding(
        type=FindingType.CROSS_TEAM_HANDOFF,
        issue_id="issue-tier-fail",
        issue_number=11,
        assignee_id="99d5f8f8-822f-4ddb-baaa-0bdaec6f9399",
        assignee_team="codex",
        company_team="claude",
        issue_status="in_progress",
    )

    await daemon._handle_tier_finding(
        state,
        client,
        finding,
        _NOW_SERVER,
        repair_delay_min=60,
        escalation_delay_min=90,
        auto_repair_enabled=False,
        version="watchdog",
        budget=daemon.AlertPostBudget(soft_limit=5, hard_limit=8),
    )

    assert state.alerted_handoffs == {}


@pytest.mark.asyncio
async def test_ownerless_alert_state_persisted_before_later_timeout(tmp_path: Path):
    cfg = _handoff_cfg(tmp_path)
    cfg = Config(
        version=cfg.version,
        paperclip=cfg.paperclip,
        companies=cfg.companies,
        daemon=cfg.daemon,
        cooldowns=cfg.cooldowns,
        logging=cfg.logging,
        escalation=cfg.escalation,
        handoff=HandoffConfig(
            **{
                **cfg.handoff.__dict__,
                "handoff_ownerless_enabled": True,
                "handoff_auto_repair_enabled": True,
            }
        ),
    )
    path = tmp_path / "state.json"
    state = State.load(path)
    first_issue = Issue(
        id="issue-ownerless-1",
        assignee_agent_id=None,
        execution_run_id=None,
        status="done",
        updated_at=_NOW_SERVER,
        issue_number=101,
    )
    second_issue = Issue(
        id="issue-ownerless-2",
        assignee_agent_id=None,
        execution_run_id=None,
        status="done",
        updated_at=_NOW_SERVER,
        issue_number=102,
    )
    client = MagicMock()
    client.list_done_issues = AsyncMock(return_value=[first_issue, second_issue])
    client.list_recent_comments = AsyncMock(return_value=[])

    async def _post(issue_id: str, body: str) -> str:
        if issue_id == "issue-ownerless-1":
            return "comment-1"
        await asyncio.sleep(60)
        return "comment-2"

    client.post_issue_comment = AsyncMock(side_effect=_post)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            daemon._run_tier_pass(cfg, state, client, _NOW_SERVER, tmp_path),
            timeout=0.05,
        )

    reloaded = State.load(path)
    key = f"issue-ownerless-1:{FindingType.OWNERLESS_COMPLETION.value}"
    assert key in reloaded.alerted_handoffs


@pytest.mark.asyncio
async def test_ownerless_alert_not_reposted_after_reload_same_snapshot(tmp_path: Path):
    cfg = _handoff_cfg(tmp_path)
    cfg = Config(
        version=cfg.version,
        paperclip=cfg.paperclip,
        companies=cfg.companies,
        daemon=cfg.daemon,
        cooldowns=cfg.cooldowns,
        logging=cfg.logging,
        escalation=cfg.escalation,
        handoff=HandoffConfig(
            **{
                **cfg.handoff.__dict__,
                "handoff_ownerless_enabled": True,
                "handoff_auto_repair_enabled": True,
            }
        ),
    )
    path = tmp_path / "state.json"
    first_state = State.load(path)
    issue = Issue(
        id="issue-ownerless-1",
        assignee_agent_id=None,
        execution_run_id=None,
        status="done",
        updated_at=_NOW_SERVER,
        issue_number=101,
    )
    client = MagicMock()
    client.list_done_issues = AsyncMock(return_value=[issue])
    client.list_recent_comments = AsyncMock(return_value=[])
    client.post_issue_comment = AsyncMock(return_value="comment-1")

    await daemon._run_tier_pass(cfg, first_state, client, _NOW_SERVER, tmp_path)

    second_state = State.load(path)
    await daemon._run_tier_pass(cfg, second_state, client, _NOW_SERVER, tmp_path)

    client.post_issue_comment.assert_awaited_once()


@pytest.mark.asyncio
async def test_shared_budget_carries_from_legacy_into_tier_issue_alerts(tmp_path: Path):
    cfg = _handoff_cfg(tmp_path)
    cfg = Config(
        version=cfg.version,
        paperclip=cfg.paperclip,
        companies=cfg.companies,
        daemon=cfg.daemon,
        cooldowns=cfg.cooldowns,
        logging=cfg.logging,
        escalation=cfg.escalation,
        handoff=HandoffConfig(
            **{
                **cfg.handoff.__dict__,
                "handoff_cross_team_enabled": True,
                "handoff_alert_soft_budget_per_tick": 1,
                "handoff_alert_hard_budget_per_tick": 1,
            }
        ),
    )
    state = State.load(tmp_path / "state.json")
    legacy_issue = _in_review_issue()
    tier_issue = Issue(
        id="issue-tier",
        assignee_agent_id="99d5f8f8-822f-4ddb-baaa-0bdaec6f9399",
        execution_run_id=None,
        status="in_progress",
        updated_at=datetime(2026, 5, 3, 11, 0, tzinfo=timezone.utc),
        issue_number=77,
    )
    client = MagicMock()
    client.list_company_agents = AsyncMock(return_value=[])
    client.list_active_issues = AsyncMock(side_effect=[[legacy_issue], [tier_issue]])
    client.list_recent_comments = AsyncMock(return_value=[])
    client.post_issue_comment = AsyncMock(return_value="tier-comment")
    posted = AlertResult(
        finding_type=FindingType.REVIEW_OWNED_BY_IMPLEMENTER,
        issue_id=legacy_issue.id,
        posted=True,
        comment_id="legacy-comment",
        error=None,
    )

    budget = daemon.AlertPostBudget(soft_limit=1, hard_limit=1)
    with patch(
        "gimle_watchdog.daemon.detection_semantic.scan_handoff_inconsistencies",
        new=AsyncMock(return_value=[_ro_finding()]),
    ):
        with patch(
            "gimle_watchdog.daemon.actions.post_handoff_alert",
            new=AsyncMock(return_value=posted),
        ):
            await daemon._run_handoff_pass(cfg, state, client, _NOW_SERVER, budget=budget)

    with patch(
        "gimle_watchdog.detection_semantic.load_team_uuids_from_repo",
        return_value={
            "claude": {_PE_ID, _CR_ID},
            "codex": {"99d5f8f8-822f-4ddb-baaa-0bdaec6f9399"},
        },
    ):
        await daemon._run_tier_pass(cfg, state, client, _NOW_SERVER, tmp_path, budget=budget)

    client.post_issue_comment.assert_not_awaited()
    assert f"{tier_issue.id}:{FindingType.CROSS_TEAM_HANDOFF.value}" not in state.alerted_handoffs


@pytest.mark.asyncio
async def test_handoff_pass_does_not_clear_tier_state_without_legacy_finding(tmp_path: Path):
    cfg = _handoff_cfg(tmp_path)
    cfg = Config(
        version=cfg.version,
        paperclip=cfg.paperclip,
        companies=cfg.companies,
        daemon=cfg.daemon,
        cooldowns=cfg.cooldowns,
        logging=cfg.logging,
        escalation=cfg.escalation,
        handoff=HandoffConfig(**{**cfg.handoff.__dict__, "handoff_cross_team_enabled": True}),
    )
    state = State.load(tmp_path / "state.json")
    tier_issue = Issue(
        id="issue-tier",
        assignee_agent_id="99d5f8f8-822f-4ddb-baaa-0bdaec6f9399",
        execution_run_id=None,
        status="in_progress",
        updated_at=datetime(2026, 5, 3, 11, 0, tzinfo=timezone.utc),
        issue_number=77,
    )
    tier_snapshot = {"assigneeAgentId": tier_issue.assignee_agent_id, "status": tier_issue.status}
    state.record_handoff_alert(
        tier_issue.id,
        FindingType.CROSS_TEAM_HANDOFF,
        tier_snapshot,
        _NOW_SERVER,
    )
    client = MagicMock()
    client.list_company_agents = AsyncMock(return_value=[])
    client.list_active_issues = AsyncMock(return_value=[tier_issue])
    client.list_recent_comments = AsyncMock(return_value=[])

    with patch(
        "gimle_watchdog.daemon.detection_semantic.scan_handoff_inconsistencies",
        new=AsyncMock(return_value=[]),
    ):
        await daemon._run_handoff_pass(cfg, state, client, _NOW_SERVER)

    assert state.has_active_alert(tier_issue.id, FindingType.CROSS_TEAM_HANDOFF, tier_snapshot)


@pytest.mark.asyncio
async def test_tier_snapshot_mismatch_reposts_and_rewrites_state_after_success(tmp_path: Path):
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.post_issue_comment = AsyncMock(return_value="tier-comment-2")
    old_snapshot = {"assigneeAgentId": "old-agent", "status": "in_progress"}
    state.record_handoff_alert(
        "issue-tier",
        FindingType.CROSS_TEAM_HANDOFF,
        old_snapshot,
        _NOW_SERVER,
    )
    finding = daemon.CrossTeamHandoffFinding(
        type=FindingType.CROSS_TEAM_HANDOFF,
        issue_id="issue-tier",
        issue_number=11,
        assignee_id="99d5f8f8-822f-4ddb-baaa-0bdaec6f9399",
        assignee_team="codex",
        company_team="claude",
        issue_status="in_progress",
    )
    budget = daemon.AlertPostBudget(soft_limit=5, hard_limit=8)

    await daemon._handle_tier_finding(
        state,
        client,
        finding,
        _NOW_SERVER,
        repair_delay_min=60,
        escalation_delay_min=90,
        auto_repair_enabled=False,
        version="watchdog",
        budget=budget,
    )

    client.post_issue_comment.assert_awaited_once()
    assert budget.posted_count == 1
    assert state.has_active_alert(
        "issue-tier",
        FindingType.CROSS_TEAM_HANDOFF,
        {"assigneeAgentId": finding.assignee_id, "status": finding.issue_status},
    )


@pytest.mark.asyncio
async def test_shared_budget_blocks_stale_bundle_after_issue_alerts(tmp_path: Path):
    cfg = _handoff_cfg(tmp_path)
    cfg = Config(
        version=cfg.version,
        paperclip=cfg.paperclip,
        companies=cfg.companies,
        daemon=cfg.daemon,
        cooldowns=cfg.cooldowns,
        logging=cfg.logging,
        escalation=cfg.escalation,
        handoff=HandoffConfig(
            **{
                **cfg.handoff.__dict__,
                "handoff_cross_team_enabled": True,
                "handoff_stale_bundle_enabled": True,
                "handoff_alert_soft_budget_per_tick": 1,
                "handoff_alert_hard_budget_per_tick": 1,
            }
        ),
    )
    state = State.load(tmp_path / "state.json")
    tier_issue = Issue(
        id="issue-tier",
        assignee_agent_id="99d5f8f8-822f-4ddb-baaa-0bdaec6f9399",
        execution_run_id=None,
        status="in_progress",
        updated_at=datetime(2026, 5, 3, 11, 0, tzinfo=timezone.utc),
        issue_number=77,
    )
    client = MagicMock()
    client.list_active_issues = AsyncMock(return_value=[tier_issue])
    client.list_recent_comments = AsyncMock(return_value=[])
    client.post_issue_comment = AsyncMock(return_value="tier-comment")

    stale = daemon.detection_semantic.StaleBundleFinding(
        type=FindingType.STALE_BUNDLE,
        deployed_sha="aaa1111111111111111111111111111111111111",
        current_sha="bbb2222222222222222222222222222222222222",
        stale_hours=48.0,
    )

    with patch(
        "gimle_watchdog.detection_semantic.load_team_uuids_from_repo",
        return_value={
            "claude": {_PE_ID, _CR_ID},
            "codex": {"99d5f8f8-822f-4ddb-baaa-0bdaec6f9399"},
        },
    ):
        with patch(
            "gimle_watchdog.daemon.detection_semantic.detect_stale_bundle",
            return_value=stale,
        ):
            with patch(
                "gimle_watchdog.daemon.actions.post_stale_bundle_alert",
                new=AsyncMock(return_value=True),
            ) as mock_stale_post:
                await daemon._run_tier_pass(
                    cfg,
                    state,
                    client,
                    _NOW_SERVER,
                    tmp_path,
                    budget=daemon.AlertPostBudget(soft_limit=1, hard_limit=1),
                )

    client.post_issue_comment.assert_awaited_once()
    mock_stale_post.assert_not_awaited()
    assert f"{_COMPANY_ID}:{FindingType.CROSS_TEAM_HANDOFF.value}" not in state.alerted_handoffs
    assert (
        f"{daemon._STALE_BUNDLE_KEY}:{FindingType.STALE_BUNDLE.value}" not in state.alerted_handoffs
    )


@pytest.mark.asyncio
async def test_tick_passes_same_budget_to_handoff_and_tier(
    full_alert_config: Config,
    fake_paperclip_client: PaperclipClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_tick must pass the same AlertPostBudget instance to both passes."""

    captured: dict[str, object] = {}

    async def fake_handoff(cfg, state, client, now, *, budget=None):  # type: ignore[no-untyped-def]
        captured["handoff"] = budget

    async def fake_tier(  # type: ignore[no-untyped-def]
        cfg, state, client, now, repo_root, *, budget=None
    ):
        captured["tier"] = budget

    monkeypatch.setattr(daemon, "_run_handoff_pass", fake_handoff)
    monkeypatch.setattr(daemon, "_run_tier_pass", fake_tier)

    state = State.load(tmp_path / "state.json")
    await daemon._tick(full_alert_config, state, fake_paperclip_client)

    assert captured["handoff"] is captured["tier"]
    assert captured["handoff"] is not None
