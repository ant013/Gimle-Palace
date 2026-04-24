"""Tests for watchdog.state — persistence, cooldowns, caps, escalations."""

from __future__ import annotations

from pathlib import Path

from freezegun import freeze_time

from gimle_watchdog import state as st
from gimle_watchdog.config import CooldownsConfig


COOLDOWNS = CooldownsConfig(
    per_issue_seconds=300,
    per_agent_cap=3,
    per_agent_window_seconds=900,
)


def test_state_roundtrip(tmp_path: Path):
    path = tmp_path / "state.json"
    s = st.State.load(path)
    s.record_wake("issue-1", "agent-1")
    s.save()
    assert path.exists()
    reloaded = st.State.load(path)
    assert reloaded.issue_cooldowns["issue-1"]["last_wake_at"]
    assert "agent-1" in reloaded.agent_wakes
    assert len(reloaded.agent_wakes["agent-1"]) == 1


def test_corrupt_state_returns_empty(tmp_path: Path, caplog):
    path = tmp_path / "state.json"
    path.write_text("{this is not json")
    s = st.State.load(path)
    assert s.issue_cooldowns == {}
    assert s.agent_wakes == {}


def test_unknown_version_renames_and_restarts(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text('{"version": 999, "issue_cooldowns": {}}')
    s = st.State.load(path)
    assert s.version == 1
    assert s.issue_cooldowns == {}
    # Backup should exist
    backups = list(tmp_path.glob("state.json.bak-*"))
    assert len(backups) == 1


@freeze_time("2026-04-21T10:00:00Z")
def test_is_issue_in_cooldown_within(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    s.record_wake("issue-1", "agent-1")
    assert s.is_issue_in_cooldown("issue-1", COOLDOWNS.per_issue_seconds) is True


def test_is_issue_in_cooldown_after(tmp_path: Path):
    path = tmp_path / "state.json"
    with freeze_time("2026-04-21T10:00:00Z"):
        s = st.State.load(path)
        s.record_wake("issue-1", "agent-1")
    with freeze_time("2026-04-21T10:10:00Z"):  # 10 min later, past 5-min cooldown
        s2 = st.State.load(path)
        assert s2.is_issue_in_cooldown("issue-1", COOLDOWNS.per_issue_seconds) is False


def test_agent_cap_exceeded_within_window(tmp_path: Path):
    path = tmp_path / "state.json"
    with freeze_time("2026-04-21T10:00:00Z"):
        s = st.State.load(path)
        s.record_wake("issue-1", "agent-1")
        s.save()
    with freeze_time("2026-04-21T10:02:00Z"):
        s = st.State.load(path)
        s.record_wake("issue-2", "agent-1")
        s.save()
    with freeze_time("2026-04-21T10:04:00Z"):
        s = st.State.load(path)
        s.record_wake("issue-3", "agent-1")
        s.save()
    with freeze_time("2026-04-21T10:05:00Z"):
        s = st.State.load(path)
        assert s.agent_cap_exceeded("agent-1", COOLDOWNS) is True


def test_agent_cap_not_exceeded_outside_window(tmp_path: Path):
    path = tmp_path / "state.json"
    with freeze_time("2026-04-21T10:00:00Z"):
        s = st.State.load(path)
        s.record_wake("issue-1", "agent-1")
        s.record_wake("issue-2", "agent-1")
        s.save()
    with freeze_time("2026-04-21T10:18:00Z"):  # >15 min past first two
        s = st.State.load(path)
        s.record_wake("issue-3", "agent-1")
        # Only 1 wake within 15-min window now
        assert s.agent_cap_exceeded("agent-1", COOLDOWNS) is False


def test_record_wake_prunes_old_entries(tmp_path: Path):
    path = tmp_path / "state.json"
    with freeze_time("2026-04-21T12:00:00Z"):
        s = st.State.load(path)
        s.record_wake("issue-2", "agent-1")
        assert len(s.agent_wakes["agent-1"]) == 1


def test_escalation_counter_increments(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    s.record_escalation("issue-1", "per_agent_cap")
    s.clear_escalation("issue-1")
    s.record_escalation("issue-1", "per_agent_cap")
    assert s.escalated_issues["issue-1"]["escalation_count"] == 2


def test_permanent_escalation_after_3_cycles(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    for _ in range(3):
        s.record_escalation("issue-1", "per_agent_cap")
        s.clear_escalation("issue-1")
    s.record_escalation("issue-1", "per_agent_cap")  # 4th
    assert s.is_permanently_escalated("issue-1") is True


def test_permanent_flag_survives_save_load(tmp_path: Path):
    path = tmp_path / "state.json"
    s = st.State.load(path)
    for _ in range(4):
        s.record_escalation("issue-1", "per_agent_cap")
        s.clear_escalation("issue-1")
    s.save()
    s2 = st.State.load(path)
    assert s2.is_permanently_escalated("issue-1") is True


def test_explicit_unescalate_clears_permanent(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    for _ in range(4):
        s.record_escalation("issue-1", "per_agent_cap")
        s.clear_escalation("issue-1")
    assert s.is_permanently_escalated("issue-1")
    s.force_unescalate("issue-1")
    assert not s.is_permanently_escalated("issue-1")
