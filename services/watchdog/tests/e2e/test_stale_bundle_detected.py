"""E2E: stale_bundle detector — imac-agents-deploy.log SHA differs from origin/main.

Scenario: log entry is 25h old with a different SHA than a mocked origin/main.
  (a) detector fires
  (b) Board comment posted (when escalation.post_comment_on_issue=True)
  (c) state entry recorded
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from freezegun import freeze_time

from gimle_watchdog.detection_semantic import detect_stale_bundle
from gimle_watchdog.models import FindingType, StaleBundleFinding

DEPLOYED_SHA = "abc1234abc1234abc1234abc1234abc1234abc123"
CURRENT_SHA = "def5678def5678def5678def5678def5678def56"

T0 = datetime(2026, 5, 8, 14, 0, tzinfo=timezone.utc)
DEPLOY_TIME = T0 - timedelta(hours=25)  # 25h ago — stale


def _write_log(path: Path, ts: datetime, sha: str) -> None:
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(f"{ts_str}\tmain_sha={sha}\tdeployed_claude=10\tdeployed_codex=5\n")


# ---------------------------------------------------------------------------
# Unit: detector logic
# ---------------------------------------------------------------------------


def test_detect_stale_bundle_fires_when_sha_differs_and_stale(tmp_path: Path):
    log = tmp_path / "imac-agents-deploy.log"
    _write_log(log, DEPLOY_TIME, DEPLOYED_SHA)

    mock_result = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=CURRENT_SHA + "\n", stderr=""
    )
    with (
        freeze_time(T0),
        patch("subprocess.run", return_value=mock_result),
    ):
        finding = detect_stale_bundle(log, tmp_path, threshold_hours=24, now=T0)

    assert isinstance(finding, StaleBundleFinding)
    assert finding.deployed_sha == DEPLOYED_SHA
    assert finding.current_sha == CURRENT_SHA
    assert finding.stale_hours >= 25.0


def test_detect_stale_no_finding_when_sha_matches(tmp_path: Path):
    log = tmp_path / "imac-agents-deploy.log"
    _write_log(log, DEPLOY_TIME, DEPLOYED_SHA)

    mock_result = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=DEPLOYED_SHA + "\n", stderr=""
    )
    with (
        freeze_time(T0),
        patch("subprocess.run", return_value=mock_result),
    ):
        finding = detect_stale_bundle(log, tmp_path, threshold_hours=24, now=T0)

    assert finding is None


def test_detect_stale_no_finding_when_within_threshold(tmp_path: Path):
    log = tmp_path / "imac-agents-deploy.log"
    recent_time = T0 - timedelta(hours=1)  # only 1h old — not stale
    _write_log(log, recent_time, DEPLOYED_SHA)

    mock_result = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=CURRENT_SHA + "\n", stderr=""
    )
    with (
        freeze_time(T0),
        patch("subprocess.run", return_value=mock_result),
    ):
        finding = detect_stale_bundle(log, tmp_path, threshold_hours=24, now=T0)

    assert finding is None


def test_detect_stale_no_finding_when_log_missing(tmp_path: Path):
    missing = tmp_path / "does-not-exist.log"
    finding = detect_stale_bundle(missing, tmp_path, threshold_hours=24, now=T0)
    assert finding is None


# ---------------------------------------------------------------------------
# E2E: tier pass records state + posts board comment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_bundle_recorded_in_state_and_board_comment_posted(
    mock_paperclip, tmp_path: Path
):
    base_url, pstate = mock_paperclip

    COMPANY_ID = "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
    # Add a sentinel issue that board comment is posted on (first company id)
    pstate.issues[COMPANY_ID] = {
        "assigneeAgentId": None,
        "status": "todo",
        "issueNumber": 1,
        "updatedAt": T0.isoformat().replace("+00:00", "Z"),
        "executionRunId": None,
    }
    pstate.agents[COMPANY_ID] = []

    # Write stale deploy log
    scripts_dir = tmp_path / "paperclips" / "scripts"
    scripts_dir.mkdir(parents=True)
    log_path = scripts_dir / "imac-agents-deploy.log"
    _write_log(log_path, DEPLOY_TIME, DEPLOYED_SHA)

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
    from gimle_watchdog.paperclip import PaperclipClient
    from gimle_watchdog.state import State
    from gimle_watchdog import daemon

    cfg = Config(
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
        escalation=EscalationConfig(post_comment_on_issue=True, comment_marker="<!-- m -->"),
        handoff=HandoffConfig(
            handoff_stale_bundle_enabled=True,
            handoff_stale_bundle_threshold_hours=24,
        ),
    )

    state = State.load(tmp_path / "state.json")
    client = PaperclipClient(base_url=base_url, api_key=None)

    mock_result = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=CURRENT_SHA + "\n", stderr=""
    )
    with (
        freeze_time(T0),
        patch("subprocess.run", return_value=mock_result),
    ):
        await daemon._run_tier_pass(cfg, state, client, T0, tmp_path)

    # State entry recorded
    key = f"_global:{FindingType.STALE_BUNDLE.value}"
    assert key in state.alerted_handoffs
    assert state.alerted_handoffs[key]["snapshot"]["deployed_sha"] == DEPLOYED_SHA

    # Board comment posted
    assert any("stale_bundle" in body for _, body in pstate.comments_posted)
    assert any(DEPLOYED_SHA[:12] in body for _, body in pstate.comments_posted)
