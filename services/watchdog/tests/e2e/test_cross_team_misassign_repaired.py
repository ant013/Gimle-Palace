"""E2E: cross_team_handoff detector — alert, repair, state lifecycle.

Scenario: Claude PE → CXCTO assignment with no infra-block marker.
  (a) detector fires on first tick → tier-1 alert created
  (b) after simulated repair_delay_min elapsed → tier-2 repair: assignee PATCH to Claude CTO
  (c) state entry cleared (repaired_at set) after successful repair
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from freezegun import freeze_time

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
from gimle_watchdog.detection_semantic import (
    _detect_cross_team_handoff,
)
from gimle_watchdog.models import FindingType, CrossTeamHandoffFinding
from gimle_watchdog.paperclip import Issue, PaperclipClient
from gimle_watchdog.state import State

# Claude PE UUID, CXCTO UUID (from codex-agent-ids.env)
CLAUDE_PE_UUID = "127068ee-b564-4b37-9370-616c81c63f35"
CLAUDE_CTO_UUID = "7fb0fdbb-e17f-4487-a4da-16993a907bec"
CX_CTO_UUID = "da97dbd9-6627-48d0-b421-66af0750eacf"

TEAM_UUIDS: dict[str, set[str]] = {
    "claude": {
        CLAUDE_PE_UUID,
        CLAUDE_CTO_UUID,
        "bd2d7e20-7ed8-474c-91fc-353d610f4c52",  # CR
    },
    "codex": {CX_CTO_UUID},
}

COMPANY_ID = "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
T0 = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)


def _cfg(tmp_path: Path, repair_delay_min: int = 5) -> Config:
    return Config(
        version=1,
        paperclip=PaperclipConfig(base_url="", api_key=None),
        companies=[
            CompanyConfig(
                id=COMPANY_ID,
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
        daemon=DaemonConfig(poll_interval_seconds=60),
        cooldowns=CooldownsConfig(
            per_issue_seconds=300, per_agent_cap=3, per_agent_window_seconds=900
        ),
        logging=LoggingConfig(
            path=tmp_path / "x.log",
            level="INFO",
            rotate_max_bytes=1048576,
            rotate_backup_count=1,
        ),
        escalation=EscalationConfig(post_comment_on_issue=False, comment_marker="<!-- m -->"),
        handoff=HandoffConfig(
            handoff_cross_team_enabled=True,
            handoff_auto_repair_enabled=True,
            handoff_repair_delay_min=repair_delay_min,
            handoff_escalation_delay_min=repair_delay_min + 30,
        ),
    )


# ---------------------------------------------------------------------------
# Unit: detector fires on cross-team assignment
# ---------------------------------------------------------------------------

def test_detector_fires_on_cx_cto_assignment():
    issue = Issue(
        id="issue-xt-1",
        assignee_agent_id=CX_CTO_UUID,
        execution_run_id=None,
        status="in_progress",
        updated_at=T0,
        issue_number=999,
    )
    finding = _detect_cross_team_handoff(issue, [], TEAM_UUIDS, company_team="claude")
    assert isinstance(finding, CrossTeamHandoffFinding)
    assert finding.assignee_team == "codex"
    assert finding.company_team == "claude"


def test_detector_suppressed_by_infra_block_marker():
    from gimle_watchdog.models import Comment

    issue = Issue(
        id="issue-xt-2",
        assignee_agent_id=CX_CTO_UUID,
        execution_run_id=None,
        status="in_progress",
        updated_at=T0,
        issue_number=998,
    )
    comment = Comment(
        id="c1",
        body="Cross-team assignment required, reason: infra-block",
        author_agent_id=CLAUDE_CTO_UUID,
        created_at=T0,
    )
    finding = _detect_cross_team_handoff(issue, [comment], TEAM_UUIDS, company_team="claude")
    assert finding is None


def test_detector_no_finding_for_same_team():
    issue = Issue(
        id="issue-same",
        assignee_agent_id=CLAUDE_PE_UUID,
        execution_run_id=None,
        status="in_progress",
        updated_at=T0,
        issue_number=997,
    )
    finding = _detect_cross_team_handoff(issue, [], TEAM_UUIDS, company_team="claude")
    assert finding is None


# ---------------------------------------------------------------------------
# E2E: tier-1 alert + tier-2 repair via mock Paperclip server
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cross_team_tier1_alert_created(mock_paperclip, tmp_path: Path):
    base_url, pstate = mock_paperclip
    pstate.issues["issue-xt-1"] = {
        "assigneeAgentId": CX_CTO_UUID,
        "status": "in_progress",
        "issueNumber": 999,
        "updatedAt": T0.isoformat().replace("+00:00", "Z"),
        "executionRunId": None,
    }
    pstate.issue_comments["issue-xt-1"] = []
    pstate.agents[COMPANY_ID] = [
        {"id": CLAUDE_CTO_UUID, "name": "CTO", "status": "idle"},
        {"id": CLAUDE_PE_UUID, "name": "PythonEngineer", "status": "idle"},
    ]

    cfg = _cfg(tmp_path, repair_delay_min=60)  # long window → stays tier 1
    state = State.load(tmp_path / "state.json")
    client = PaperclipClient(base_url=base_url, api_key=None)

    from gimle_watchdog import daemon
    from unittest.mock import patch, AsyncMock

    with (
        patch.object(daemon, "_REPO_ROOT", tmp_path),
        patch(
            "gimle_watchdog.detection_semantic.load_team_uuids_from_repo",
            return_value=TEAM_UUIDS,
        ),
        patch("gimle_watchdog.detection.scan_idle_hangs", return_value=[]),
        patch("gimle_watchdog.detection.scan_died_mid_work", new_callable=AsyncMock, return_value=[]),
    ):
        with freeze_time(T0):
            await daemon._run_tier_pass(cfg, state, client, T0, tmp_path)

    # Tier-1 alert recorded
    key = f"issue-xt-1:{FindingType.CROSS_TEAM_HANDOFF.value}"
    assert key in state.alerted_handoffs
    entry = state.alerted_handoffs[key]
    assert entry["tier"] == 1
    assert entry["repaired_at"] is None

    # Alert comment posted
    assert any("cross_team_handoff" in body for _, body in pstate.comments_posted)


@pytest.mark.asyncio
async def test_cross_team_tier2_repair_patches_assignee(mock_paperclip, tmp_path: Path):
    base_url, pstate = mock_paperclip
    pstate.issues["issue-xt-1"] = {
        "assigneeAgentId": CX_CTO_UUID,
        "status": "in_progress",
        "issueNumber": 999,
        "updatedAt": T0.isoformat().replace("+00:00", "Z"),
        "executionRunId": None,
    }
    pstate.issue_comments["issue-xt-1"] = []
    pstate.agents[COMPANY_ID] = [
        {"id": CLAUDE_CTO_UUID, "name": "CTO", "status": "idle"},
    ]

    cfg = _cfg(tmp_path, repair_delay_min=5)  # short window → tier 2 after 5 min
    state = State.load(tmp_path / "state.json")
    client = PaperclipClient(base_url=base_url, api_key=None)

    from gimle_watchdog import daemon
    from unittest.mock import patch, AsyncMock

    with (
        patch.object(daemon, "_REPO_ROOT", tmp_path),
        patch(
            "gimle_watchdog.detection_semantic.load_team_uuids_from_repo",
            return_value=TEAM_UUIDS,
        ),
        patch("gimle_watchdog.detection.scan_idle_hangs", return_value=[]),
        patch("gimle_watchdog.detection.scan_died_mid_work", new_callable=AsyncMock, return_value=[]),
    ):
        # Tick 1: issue discovered → tier 1
        with freeze_time(T0):
            await daemon._run_tier_pass(cfg, state, client, T0, tmp_path)

        key = f"issue-xt-1:{FindingType.CROSS_TEAM_HANDOFF.value}"
        assert state.alerted_handoffs[key]["tier"] == 1

        # Tick 2: 6 min later → repair_delay elapsed → tier 2 → auto-repair
        t1 = T0.replace(minute=T0.minute + 6)
        with freeze_time(t1):
            await daemon._run_tier_pass(cfg, state, client, t1, tmp_path)

    # After repair: assignee should be Claude CTO
    assert pstate.issues["issue-xt-1"]["assigneeAgentId"] == CLAUDE_CTO_UUID
    # State entry cleared (repaired)
    assert key not in state.alerted_handoffs or state.alerted_handoffs.get(key, {}).get("repaired_at")
