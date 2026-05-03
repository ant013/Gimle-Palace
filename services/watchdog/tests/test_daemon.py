"""Tests for watchdog.daemon — tick orchestration."""

from __future__ import annotations

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

from gimle_watchdog.paperclip import Issue
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
        daemon=DaemonConfig(poll_interval_seconds=120),
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
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.list_in_progress_issues = AsyncMock(return_value=[_stuck_issue()])
    with patch(
        "gimle_watchdog.daemon.actions.trigger_respawn",
        new=AsyncMock(return_value=RespawnResult(via="patch", success=True, run_id="run-new")),
    ):
        with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
            with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
                await daemon._tick(cfg, state, client)
    assert state.is_issue_in_cooldown("issue-1", cfg.cooldowns.per_issue_seconds)


@pytest.mark.asyncio
async def test_tick_escalates_capped_agent(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    from freezegun import freeze_time

    for ts in ["2026-04-21T09:55:00Z", "2026-04-21T09:57:00Z", "2026-04-21T09:58:00Z"]:
        with freeze_time(ts):
            state.record_wake(f"dummy-{ts}", "agent-1")
    client = MagicMock()
    client.list_in_progress_issues = AsyncMock(return_value=[_stuck_issue()])
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
    client.list_in_progress_issues = AsyncMock(return_value=[])
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
    client.list_in_progress_issues = AsyncMock(return_value=[_stuck_issue()])
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
    client.list_in_progress_issues = AsyncMock(return_value=[_stuck_issue()])
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
    client.list_in_progress_issues = AsyncMock(return_value=[_stuck_issue()])
    with patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
        with patch("gimle_watchdog.daemon._sleep", new=AsyncMock()):
            await daemon._tick(cfg, state, client)
    assert state.is_issue_in_cooldown("issue-1", cfg.cooldowns.per_issue_seconds)


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
    client.list_in_progress_issues = AsyncMock(return_value=[_stuck_issue()])
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
        with patch("gimle_watchdog.daemon.actions.post_handoff_alert", new=AsyncMock(return_value=posted)) as mock_post:
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
        with patch("gimle_watchdog.daemon.actions.post_handoff_alert", new=AsyncMock()) as mock_post:
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
        with patch("gimle_watchdog.daemon.actions.post_handoff_alert", new=AsyncMock()) as mock_post:
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
        with patch("gimle_watchdog.daemon.actions.post_handoff_alert", new=AsyncMock(return_value=posted)) as mock_post:
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
    client.list_in_progress_issues = AsyncMock(return_value=[])

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
