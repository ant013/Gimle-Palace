"""E2E: ownerless_completion detector — done without QA evidence → re-open as blocked.

Scenario: issue status=done without Phase 4.1 QA PASS comment.
  (a) detector fires on first tick → tier-1 alert
  (b) after repair_delay_min → tier-2 repair: PATCH status=blocked + comment
  (c) state entry cleared after repair
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
from gimle_watchdog.detection_semantic import _detect_ownerless_completion, _CLAUDE_QA_UUID
from gimle_watchdog.models import FindingType, OwnerlessCompletionFinding
from gimle_watchdog.paperclip import Issue, PaperclipClient
from gimle_watchdog.state import State

COMPANY_ID = "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
CLAUDE_CTO_UUID = "7fb0fdbb-e17f-4487-a4da-16993a907bec"
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
            handoff_ownerless_enabled=True,
            handoff_auto_repair_enabled=True,
            handoff_repair_delay_min=repair_delay_min,
            handoff_escalation_delay_min=repair_delay_min + 30,
        ),
    )


# ---------------------------------------------------------------------------
# Unit: detector fires when done with no QA comment
# ---------------------------------------------------------------------------

def test_detector_fires_when_done_and_no_qa_comment():
    issue = Issue(
        id="issue-ol-1",
        assignee_agent_id=CLAUDE_CTO_UUID,
        execution_run_id=None,
        status="done",
        updated_at=T0,
        issue_number=100,
    )
    finding = _detect_ownerless_completion(issue, [])
    assert isinstance(finding, OwnerlessCompletionFinding)
    assert finding.issue_id == "issue-ol-1"


def test_detector_suppressed_when_valid_qa_comment_exists():
    from gimle_watchdog.models import Comment

    issue = Issue(
        id="issue-ol-2",
        assignee_agent_id=CLAUDE_CTO_UUID,
        execution_run_id=None,
        status="done",
        updated_at=T0,
        issue_number=101,
    )
    qa_comment = Comment(
        id="qa-1",
        body="## Phase 4.1 — QA PASS ✅\n\nEverything green.",
        author_agent_id=_CLAUDE_QA_UUID,
        created_at=T0,
    )
    finding = _detect_ownerless_completion(issue, [qa_comment])
    assert finding is None


def test_detector_no_finding_when_status_not_done():
    issue = Issue(
        id="issue-ol-3",
        assignee_agent_id=CLAUDE_CTO_UUID,
        execution_run_id=None,
        status="in_progress",
        updated_at=T0,
        issue_number=102,
    )
    finding = _detect_ownerless_completion(issue, [])
    assert finding is None


# ---------------------------------------------------------------------------
# E2E: tier-1 alert + tier-2 repair re-opens as blocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ownerless_tier1_alert_posted(mock_paperclip, tmp_path: Path):
    base_url, pstate = mock_paperclip
    pstate.issues["issue-ol-1"] = {
        "assigneeAgentId": CLAUDE_CTO_UUID,
        "status": "done",
        "issueNumber": 100,
        "updatedAt": T0.isoformat().replace("+00:00", "Z"),
        "executionRunId": None,
    }
    pstate.issue_comments["issue-ol-1"] = []  # no QA comment
    pstate.agents[COMPANY_ID] = [{"id": CLAUDE_CTO_UUID, "name": "CTO", "status": "idle"}]

    cfg = _cfg(tmp_path, repair_delay_min=60)
    state = State.load(tmp_path / "state.json")
    client = PaperclipClient(base_url=base_url, api_key=None)

    from gimle_watchdog import daemon
    from unittest.mock import patch, AsyncMock

    with (
        patch.object(daemon, "_REPO_ROOT", tmp_path),
        patch("gimle_watchdog.detection.scan_idle_hangs", return_value=[]),
        patch("gimle_watchdog.detection.scan_died_mid_work", new_callable=AsyncMock, return_value=[]),
    ):
        with freeze_time(T0):
            await daemon._run_tier_pass(cfg, state, client, T0, tmp_path)

    key = f"issue-ol-1:{FindingType.OWNERLESS_COMPLETION.value}"
    assert key in state.alerted_handoffs
    assert state.alerted_handoffs[key]["tier"] == 1
    assert any("ownerless_completion" in body for _, body in pstate.comments_posted)


@pytest.mark.asyncio
async def test_ownerless_tier2_repair_reopens_as_blocked(mock_paperclip, tmp_path: Path):
    base_url, pstate = mock_paperclip
    pstate.issues["issue-ol-1"] = {
        "assigneeAgentId": CLAUDE_CTO_UUID,
        "status": "done",
        "issueNumber": 100,
        "updatedAt": T0.isoformat().replace("+00:00", "Z"),
        "executionRunId": None,
    }
    pstate.issue_comments["issue-ol-1"] = []
    pstate.agents[COMPANY_ID] = [{"id": CLAUDE_CTO_UUID, "name": "CTO", "status": "idle"}]

    cfg = _cfg(tmp_path, repair_delay_min=5)
    state = State.load(tmp_path / "state.json")
    client = PaperclipClient(base_url=base_url, api_key=None)

    from gimle_watchdog import daemon
    from unittest.mock import patch, AsyncMock

    with (
        patch.object(daemon, "_REPO_ROOT", tmp_path),
        patch("gimle_watchdog.detection.scan_idle_hangs", return_value=[]),
        patch("gimle_watchdog.detection.scan_died_mid_work", new_callable=AsyncMock, return_value=[]),
    ):
        with freeze_time(T0):
            await daemon._run_tier_pass(cfg, state, client, T0, tmp_path)

        t1 = T0.replace(minute=T0.minute + 6)
        with freeze_time(t1):
            await daemon._run_tier_pass(cfg, state, client, t1, tmp_path)

    # Issue re-opened as blocked
    assert pstate.issues["issue-ol-1"]["status"] == "blocked"
    key = f"issue-ol-1:{FindingType.OWNERLESS_COMPLETION.value}"
    # Entry either cleared or has repaired_at set
    entry = state.alerted_handoffs.get(key)
    assert entry is None or entry.get("repaired_at") is not None
