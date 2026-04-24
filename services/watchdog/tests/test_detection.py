"""Tests for watchdog.detection — ps parsers + scan logic."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest
from freezegun import freeze_time

from gimle_watchdog import detection as det
from gimle_watchdog.config import (
    CompanyConfig,
    Config,
    CooldownsConfig,
    DaemonConfig,
    EscalationConfig,
    LoggingConfig,
    PaperclipConfig,
    Thresholds,
)
from gimle_watchdog.paperclip import Issue
from gimle_watchdog.state import State


FIXTURE_DIR = Path(__file__).parent / "fixtures"


# --- Low-level parsers -----------------------------------------------------------


def test_parse_etime_macos_mm_ss():
    assert det._parse_etime("5:30") == 330


def test_parse_etime_macos_hh_mm_ss():
    assert det._parse_etime("1:06:07") == 3967


def test_parse_etime_macos_days_hh_mm_ss():
    # "2-03:15:42" = 2 days + 3h15m42s = 2*86400 + 11742 = 184542
    assert det._parse_etime("2-03:15:42") == 184542


def test_parse_etime_linux_hh_mm_ss():
    assert det._parse_etime("01:06:07") == 3967


def test_parse_etime_linux_days():
    # "1-02:00:00" = 1d2h = 86400 + 7200 = 93600
    assert det._parse_etime("1-02:00:00") == 93600


def test_parse_time_macos_decimal():
    assert det._parse_time("0:05.00") == 5


def test_parse_time_macos_hh_mm_ss_hundredths():
    # "1:02:10.00" = 1h2m10s = 3730
    assert det._parse_time("1:02:10.00") == 3730


def test_parse_time_linux_hms():
    assert det._parse_time("00:00:05") == 5


def test_parse_time_invalid_returns_zero():
    assert det._parse_time("garbage") == 0


# --- parse_ps_output ------------------------------------------------------------


def test_parse_ps_macos_finds_hangs():
    text = (FIXTURE_DIR / "ps_output_macos.txt").read_text()
    # thresholds: etime >= 60 min, cpu <= 30 s
    hangs = det.parse_ps_output(text, etime_min_s=60 * 60, cpu_max_s=30)
    assert len(hangs) == 1
    assert hangs[0].pid == 89879
    assert hangs[0].etime_s == 3967
    assert hangs[0].cpu_s == 5


def test_parse_ps_linux_finds_hangs():
    text = (FIXTURE_DIR / "ps_output_linux.txt").read_text()
    hangs = det.parse_ps_output(text, etime_min_s=60 * 60, cpu_max_s=30)
    assert len(hangs) == 1
    assert hangs[0].pid == 89879


def test_parse_ps_skips_non_paperclip():
    text = (
        "  PID     ELAPSED        TIME COMMAND\n"
        "99999    1:00:00     0:05.00 /usr/bin/some-other-process --flag\n"
    )
    assert det.parse_ps_output(text, etime_min_s=60 * 60, cpu_max_s=30) == []


def test_parse_ps_skips_fresh_procs():
    text = (FIXTURE_DIR / "ps_output_macos.txt").read_text()
    # 91082 has etime 5:30 = 330s, well under 3600
    hangs = det.parse_ps_output(text, etime_min_s=60 * 60, cpu_max_s=30)
    pids = [h.pid for h in hangs]
    assert 91082 not in pids


def test_parse_ps_skips_high_cpu_procs():
    """A process with 65s CPU is not idle even if etime > threshold."""
    text = (
        "  PID     ELAPSED        TIME COMMAND\n"
        "55555    2:00:00    00:01:05 /usr/bin/claude --append-system-prompt-file /tmp/paperclip-skills-abc --add-dir /tmp/paperclip-skills-abc\n"
    )
    hangs = det.parse_ps_output(text, etime_min_s=60 * 60, cpu_max_s=30)
    assert len(hangs) == 0


# --- scan_died_mid_work --------------------------------------------------------


def _make_config(died_min: int = 3, cooldowns: CooldownsConfig | None = None) -> Config:
    cooldowns = cooldowns or CooldownsConfig(
        per_issue_seconds=300, per_agent_cap=3, per_agent_window_seconds=900
    )
    return Config(
        version=1,
        paperclip=PaperclipConfig(base_url="http://x", api_key="k"),
        companies=[
            CompanyConfig(
                id="9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64",
                name="gimle",
                thresholds=Thresholds(
                    died_min=died_min, hang_etime_min=60, hang_cpu_max_s=30
                ),
            )
        ],
        daemon=DaemonConfig(poll_interval_seconds=120),
        cooldowns=cooldowns,
        logging=LoggingConfig(
            path=Path("/tmp/x.log"),
            level="INFO",
            rotate_max_bytes=1048576,
            rotate_backup_count=1,
        ),
        escalation=EscalationConfig(
            post_comment_on_issue=False, comment_marker="<!-- x -->"
        ),
    )


def _issue(
    *,
    id: str = "issue-1",
    assignee: str | None = "agent-1",
    run_id: str | None = None,
    updated_at: _dt.datetime | None = None,
) -> Issue:
    if updated_at is None:
        updated_at = _dt.datetime(2026, 4, 21, 10, 0, tzinfo=_dt.timezone.utc)
    return Issue(
        id=id,
        assignee_agent_id=assignee,
        execution_run_id=run_id,
        status="in_progress",
        updated_at=updated_at,
    )


class _FakeClient:
    def __init__(self, issues: list[Issue]):
        self._issues = issues

    async def list_in_progress_issues(self, company_id: str) -> list[Issue]:
        return list(self._issues)


@pytest.mark.asyncio
@freeze_time("2026-04-21T10:05:00Z")
async def test_scan_died_skips_null_assignee(tmp_path: Path):
    cfg = _make_config()
    st = State.load(tmp_path / "s.json")
    client = _FakeClient(
        [_issue(assignee=None, updated_at=_dt.datetime(2026, 4, 21, 10, 0, tzinfo=_dt.timezone.utc))]
    )
    actions = await det.scan_died_mid_work(cfg.companies[0], client, st, cfg)
    assert actions == []


@pytest.mark.asyncio
@freeze_time("2026-04-21T10:05:00Z")
async def test_scan_died_skips_active_run(tmp_path: Path):
    cfg = _make_config()
    st = State.load(tmp_path / "s.json")
    client = _FakeClient(
        [_issue(run_id="run-1", updated_at=_dt.datetime(2026, 4, 21, 10, 0, tzinfo=_dt.timezone.utc))]
    )
    actions = await det.scan_died_mid_work(cfg.companies[0], client, st, cfg)
    assert actions == []


@pytest.mark.asyncio
@freeze_time("2026-04-21T10:01:00Z")
async def test_scan_died_skips_too_recent(tmp_path: Path):
    cfg = _make_config(died_min=3)
    st = State.load(tmp_path / "s.json")
    # updated 30s ago — below 3-min threshold
    client = _FakeClient(
        [_issue(updated_at=_dt.datetime(2026, 4, 21, 10, 0, 30, tzinfo=_dt.timezone.utc))]
    )
    actions = await det.scan_died_mid_work(cfg.companies[0], client, st, cfg)
    assert actions == []


@pytest.mark.asyncio
@freeze_time("2026-04-21T10:05:00Z")
async def test_scan_died_wakes_stuck_issue(tmp_path: Path):
    cfg = _make_config()
    st = State.load(tmp_path / "s.json")
    client = _FakeClient(
        [_issue(updated_at=_dt.datetime(2026, 4, 21, 10, 0, tzinfo=_dt.timezone.utc))]
    )
    actions = await det.scan_died_mid_work(cfg.companies[0], client, st, cfg)
    assert len(actions) == 1
    assert actions[0].kind == "wake"
    assert actions[0].issue.id == "issue-1"
    assert actions[0].agent_id == "agent-1"


@pytest.mark.asyncio
@freeze_time("2026-04-21T10:05:00Z")
async def test_scan_died_respects_cooldown(tmp_path: Path):
    cfg = _make_config()
    st = State.load(tmp_path / "s.json")
    # Record a recent wake so issue is in cooldown
    with freeze_time("2026-04-21T10:02:00Z"):
        st.record_wake("issue-1", "agent-1")
    client = _FakeClient(
        [_issue(updated_at=_dt.datetime(2026, 4, 21, 10, 0, tzinfo=_dt.timezone.utc))]
    )
    actions = await det.scan_died_mid_work(cfg.companies[0], client, st, cfg)
    assert len(actions) == 1
    assert actions[0].kind == "skip"


@pytest.mark.asyncio
@freeze_time("2026-04-21T10:30:00Z")
async def test_scan_died_escalates_at_cap(tmp_path: Path):
    cfg = _make_config()
    st = State.load(tmp_path / "s.json")
    # Record 3 wakes in last 15 min for agent-1
    for ts in ["2026-04-21T10:20:00Z", "2026-04-21T10:23:00Z", "2026-04-21T10:26:00Z"]:
        with freeze_time(ts):
            st.record_wake(f"dummy-{ts}", "agent-1")
    client = _FakeClient(
        [_issue(updated_at=_dt.datetime(2026, 4, 21, 10, 25, tzinfo=_dt.timezone.utc))]
    )
    actions = await det.scan_died_mid_work(cfg.companies[0], client, st, cfg)
    assert len(actions) == 1
    assert actions[0].kind == "escalate"


@pytest.mark.asyncio
@freeze_time("2026-04-21T11:00:00Z")
async def test_scan_died_auto_unescalates_on_touch(tmp_path: Path):
    cfg = _make_config()
    st = State.load(tmp_path / "s.json")
    # Escalate an issue at 10:00
    with freeze_time("2026-04-21T10:00:00Z"):
        st.record_escalation("issue-1", "per_agent_cap")
    # Operator touches issue at 10:30 (updatedAt > escalated_at)
    client = _FakeClient(
        [_issue(updated_at=_dt.datetime(2026, 4, 21, 10, 30, tzinfo=_dt.timezone.utc))]
    )
    actions = await det.scan_died_mid_work(cfg.companies[0], client, st, cfg)
    # Should clear escalation AND produce wake action
    assert not st.is_escalated("issue-1")
    assert any(a.kind == "wake" for a in actions)


@pytest.mark.asyncio
@freeze_time("2026-04-21T11:00:00Z")
async def test_scan_died_skips_permanently_escalated(tmp_path: Path):
    cfg = _make_config()
    st = State.load(tmp_path / "s.json")
    # Bump into permanent by 4 cycles
    for _ in range(4):
        st.record_escalation("issue-1", "per_agent_cap")
        st.clear_escalation("issue-1")
    assert st.is_permanently_escalated("issue-1")
    client = _FakeClient(
        [_issue(updated_at=_dt.datetime(2026, 4, 21, 10, 30, tzinfo=_dt.timezone.utc))]
    )
    actions = await det.scan_died_mid_work(cfg.companies[0], client, st, cfg)
    assert actions == []
