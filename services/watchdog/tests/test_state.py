"""Tests for watchdog.state — persistence, cooldowns, caps, escalations."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from freezegun import freeze_time

from gimle_watchdog import state as st
from gimle_watchdog.config import CooldownsConfig
from gimle_watchdog.models import FindingType

_FIXTURES = Path(__file__).parent / "fixtures"


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
    assert s.version == st.STATE_VERSION
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


# ---------------------------------------------------------------------------
# T4: alerted_handoffs — edge-triggered cooldown
# ---------------------------------------------------------------------------

_SNAP_WRONG = {"assigneeAgentId": "bogus-uuid", "status": "in_progress"}
_SNAP_CO = {
    "assigneeAgentId": "agent-pe",
    "status": "in_progress",
    "mention_comment_id": "cmt-001",
    "mention_target_uuid": "agent-cr",
}


def test_has_active_alert_false_when_no_entry(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    assert s.has_active_alert("issue-1", FindingType.WRONG_ASSIGNEE, _SNAP_WRONG) is False


def test_has_active_alert_true_when_snapshot_keys_match(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    alerted_at = datetime(2026, 5, 3, 10, 0, tzinfo=timezone.utc)
    s.record_handoff_alert("issue-1", FindingType.WRONG_ASSIGNEE, _SNAP_WRONG, alerted_at)
    assert s.has_active_alert("issue-1", FindingType.WRONG_ASSIGNEE, _SNAP_WRONG) is True


def test_has_active_alert_false_when_assignee_id_changed(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    alerted_at = datetime(2026, 5, 3, 10, 0, tzinfo=timezone.utc)
    s.record_handoff_alert("issue-1", FindingType.WRONG_ASSIGNEE, _SNAP_WRONG, alerted_at)
    changed = dict(_SNAP_WRONG, assigneeAgentId="different-uuid")
    assert s.has_active_alert("issue-1", FindingType.WRONG_ASSIGNEE, changed) is False


def test_has_active_alert_false_when_status_changed(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    alerted_at = datetime(2026, 5, 3, 10, 0, tzinfo=timezone.utc)
    s.record_handoff_alert("issue-1", FindingType.WRONG_ASSIGNEE, _SNAP_WRONG, alerted_at)
    changed = dict(_SNAP_WRONG, status="in_review")
    assert s.has_active_alert("issue-1", FindingType.WRONG_ASSIGNEE, changed) is False


def test_has_active_alert_true_when_updated_at_drifts_only(tmp_path: Path):
    """updatedAt is NOT a snapshot key — drift alone must not invalidate the alert."""
    s = st.State.load(tmp_path / "state.json")
    alerted_at = datetime(2026, 5, 3, 10, 0, tzinfo=timezone.utc)
    snap = dict(_SNAP_WRONG, updatedAt="2026-05-03T10:00:00Z")
    s.record_handoff_alert("issue-1", FindingType.WRONG_ASSIGNEE, snap, alerted_at)
    drifted = dict(_SNAP_WRONG, updatedAt="2026-05-03T11:00:00Z")
    assert s.has_active_alert("issue-1", FindingType.WRONG_ASSIGNEE, drifted) is True


def test_has_active_alert_for_comment_only_uses_mention_uuid_and_comment_id(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    alerted_at = datetime(2026, 5, 3, 10, 0, tzinfo=timezone.utc)
    s.record_handoff_alert("issue-1", FindingType.COMMENT_ONLY_HANDOFF, _SNAP_CO, alerted_at)
    changed_comment = dict(_SNAP_CO, mention_comment_id="cmt-999")
    assert s.has_active_alert("issue-1", FindingType.COMMENT_ONLY_HANDOFF, _SNAP_CO) is True
    assert s.has_active_alert("issue-1", FindingType.COMMENT_ONLY_HANDOFF, changed_comment) is False


@freeze_time("2026-05-03T10:25:00Z")
def test_cooldown_elapsed_false_when_recent(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    alerted_at = datetime(2026, 5, 3, 10, 0, tzinfo=timezone.utc)
    s.record_handoff_alert("issue-1", FindingType.WRONG_ASSIGNEE, _SNAP_WRONG, alerted_at)
    now_server = datetime(2026, 5, 3, 10, 25, tzinfo=timezone.utc)
    assert s.cooldown_elapsed("issue-1", FindingType.WRONG_ASSIGNEE, now_server, 30) is False


@freeze_time("2026-05-03T10:35:00Z")
def test_cooldown_elapsed_true_when_past_threshold(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    alerted_at = datetime(2026, 5, 3, 10, 0, tzinfo=timezone.utc)
    s.record_handoff_alert("issue-1", FindingType.WRONG_ASSIGNEE, _SNAP_WRONG, alerted_at)
    now_server = datetime(2026, 5, 3, 10, 35, tzinfo=timezone.utc)
    assert s.cooldown_elapsed("issue-1", FindingType.WRONG_ASSIGNEE, now_server, 30) is True


def test_record_handoff_alert_persists_alerted_at(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    alerted_at = datetime(2026, 5, 3, 12, 34, 56, tzinfo=timezone.utc)
    s.record_handoff_alert("issue-1", FindingType.WRONG_ASSIGNEE, _SNAP_WRONG, alerted_at)
    key = f"issue-1:{FindingType.WRONG_ASSIGNEE.value}"
    entry = s.alerted_handoffs[key]
    assert entry["alerted_at"] in ("2026-05-03T12:34:56+00:00", "2026-05-03T12:34:56Z")


def test_clear_handoff_alert_removes_entry(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    alerted_at = datetime(2026, 5, 3, 10, 0, tzinfo=timezone.utc)
    s.record_handoff_alert("issue-1", FindingType.WRONG_ASSIGNEE, _SNAP_WRONG, alerted_at)
    s.clear_handoff_alert("issue-1", FindingType.WRONG_ASSIGNEE)
    key = f"issue-1:{FindingType.WRONG_ASSIGNEE.value}"
    assert key not in s.alerted_handoffs


def test_alerted_handoffs_round_trip_through_json(tmp_path: Path):
    path = tmp_path / "state.json"
    s = st.State.load(path)
    alerted_at = datetime(2026, 5, 3, 10, 0, tzinfo=timezone.utc)
    s.record_handoff_alert("issue-1", FindingType.WRONG_ASSIGNEE, _SNAP_WRONG, alerted_at)
    s.save()
    s2 = st.State.load(path)
    assert s2.has_active_alert("issue-1", FindingType.WRONG_ASSIGNEE, _SNAP_WRONG) is True


def test_state_loads_pre_gim180_json(tmp_path: Path):
    fixture = _FIXTURES / "issue_pre_gim180_state.json"
    path = tmp_path / "state.json"
    path.write_text(fixture.read_text())
    s = st.State.load(path)
    assert s.alerted_handoffs == {}


# ---------------------------------------------------------------------------
# GIM-244 — tier state machine tests
# ---------------------------------------------------------------------------

_SNAP_CT = {"assigneeAgentId": "cx-cto-uuid"}


def test_record_handoff_alert_includes_tier_fields(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    alerted_at = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
    s.record_handoff_alert("issue-1", FindingType.CROSS_TEAM_HANDOFF, _SNAP_CT, alerted_at)
    key = f"issue-1:{FindingType.CROSS_TEAM_HANDOFF.value}"
    entry = s.alerted_handoffs[key]
    assert entry["tier"] == 1
    assert entry["tier_changed_at"] == entry["alerted_at"]
    assert entry["repaired_at"] is None
    assert entry["escalated_at"] is None
    assert entry["actionable"] is True


def test_record_handoff_alert_actionable_false(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    alerted_at = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
    snap = {"error_kind": "cloudflare_1010"}
    s.record_handoff_alert(
        "issue-2", FindingType.INFRA_BLOCK, snap, alerted_at, actionable=False
    )
    key = f"issue-2:{FindingType.INFRA_BLOCK.value}"
    assert s.alerted_handoffs[key]["actionable"] is False


def test_promote_tier_updates_entry(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    alerted_at = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
    promoted_at = datetime(2026, 5, 8, 11, 0, tzinfo=timezone.utc)
    s.record_handoff_alert("issue-1", FindingType.CROSS_TEAM_HANDOFF, _SNAP_CT, alerted_at)
    s.promote_handoff_tier("issue-1", FindingType.CROSS_TEAM_HANDOFF, 2, promoted_at)
    assert s.get_handoff_tier("issue-1", FindingType.CROSS_TEAM_HANDOFF) == 2


def test_set_repaired_records_timestamp(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    alerted_at = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
    repaired_at = datetime(2026, 5, 8, 11, 5, tzinfo=timezone.utc)
    s.record_handoff_alert("issue-1", FindingType.CROSS_TEAM_HANDOFF, _SNAP_CT, alerted_at)
    s.set_handoff_repaired("issue-1", FindingType.CROSS_TEAM_HANDOFF, repaired_at)
    key = f"issue-1:{FindingType.CROSS_TEAM_HANDOFF.value}"
    assert s.alerted_handoffs[key]["repaired_at"] is not None


def test_set_escalated_records_timestamp(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    alerted_at = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
    escalated_at = datetime(2026, 5, 8, 11, 35, tzinfo=timezone.utc)
    s.record_handoff_alert("issue-1", FindingType.CROSS_TEAM_HANDOFF, _SNAP_CT, alerted_at)
    s.set_handoff_escalated("issue-1", FindingType.CROSS_TEAM_HANDOFF, escalated_at)
    key = f"issue-1:{FindingType.CROSS_TEAM_HANDOFF.value}"
    assert s.alerted_handoffs[key]["escalated_at"] is not None


def test_state_v1_migration_adds_tier_fields(tmp_path: Path):
    """v1 state loaded and migrated to v2 — existing alerted_handoffs get tier fields."""
    path = tmp_path / "state.json"
    # Simulate a v1 state file with an existing handoff alert (no tier fields)
    path.write_text(
        '{"version": 1, "issue_cooldowns": {}, "agent_wakes": {}, '
        '"escalated_issues": {}, "alerted_handoffs": '
        '{"issue-old:wrong_assignee": {"alerted_at": "2026-05-01T10:00:00Z", '
        '"snapshot": {"assigneeAgentId": "bogus", "status": "in_progress"}}}}'
    )
    s = st.State.load(path)
    assert s.version == st.STATE_VERSION
    entry = s.alerted_handoffs.get("issue-old:wrong_assignee")
    assert entry is not None
    assert entry["tier"] == 1
    assert entry["tier_changed_at"] == "2026-05-01T10:00:00Z"
    assert entry["repaired_at"] is None
    assert entry["escalated_at"] is None
    assert entry["actionable"] is True


def test_get_handoff_actionable_defaults_true_for_missing(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    assert s.get_handoff_actionable("no-such", FindingType.CROSS_TEAM_HANDOFF) is True
