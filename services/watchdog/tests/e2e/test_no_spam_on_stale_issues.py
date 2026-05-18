"""E2E: stale and recovery-origin issues do not generate watchdog comment spam."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from gimle_watchdog import daemon
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

COMPANY_ID = "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
PE_ID = "127068ee-b564-4b37-9370-616c81c63f35"
CR_ID = "bd2d7e20-7ed8-474c-91fc-353d610f4c52"
CTO_ID = "7fb0fdbb-e17f-4487-a4da-16993a907bec"
CODEX_QA_ID = "99d5f8f8-822f-4ddb-baaa-0bdaec6f9399"
BOGUS_ID = "00000000-0000-0000-0000-000000000001"
NOW = datetime(2026, 5, 9, 17, 0, tzinfo=timezone.utc)

STALE_IDS = {
    "stale-comment-only",
    "stale-wrong-assignee",
    "stale-review-owned",
    "stale-cross-team",
    "recovery-ownerless",
    "stale-infra",
    "stale-extra-1",
    "stale-extra-2",
    "stale-extra-3",
    "stale-extra-4",
}


def _cfg(tmp_path: Path, base_url: str) -> Config:
    return Config(
        version=1,
        paperclip=PaperclipConfig(base_url=base_url, api_key="tok"),
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
            per_issue_seconds=300,
            per_agent_cap=3,
            per_agent_window_seconds=900,
        ),
        logging=LoggingConfig(
            path=tmp_path / "watchdog.log",
            level="INFO",
            rotate_max_bytes=1048576,
            rotate_backup_count=1,
        ),
        escalation=EscalationConfig(post_comment_on_issue=False, comment_marker="<!-- m -->"),
        handoff=HandoffConfig(
            handoff_alert_enabled=True,
            handoff_cross_team_enabled=True,
            handoff_ownerless_enabled=True,
            handoff_infra_block_enabled=True,
            handoff_recent_window_min=180,
            handoff_wrong_assignee_min=3,
            handoff_review_owner_min=5,
            handoff_comment_lookback_min=5,
        ),
    )


def _issue(
    status: str,
    updated_at: datetime,
    *,
    assignee: str | None,
    number: int,
    origin_kind: str | None = None,
) -> dict[str, object]:
    return {
        "assigneeAgentId": assignee,
        "status": status,
        "issueNumber": number,
        "updatedAt": updated_at.isoformat().replace("+00:00", "Z"),
        "executionRunId": None,
        "originKind": origin_kind,
    }


@pytest.mark.asyncio
async def test_no_spam_on_stale_or_recovery_issues(mock_paperclip, tmp_path: Path):
    base_url, pstate = mock_paperclip
    stale_updated = NOW - timedelta(hours=4)
    fresh_updated = NOW - timedelta(minutes=10)

    pstate.issues = {
        "stale-comment-only": _issue("in_progress", stale_updated, assignee=PE_ID, number=1),
        "stale-wrong-assignee": _issue("in_progress", stale_updated, assignee=BOGUS_ID, number=2),
        "stale-review-owned": _issue("in_review", stale_updated, assignee=PE_ID, number=3),
        "stale-cross-team": _issue("in_progress", stale_updated, assignee=CODEX_QA_ID, number=4),
        "recovery-ownerless": _issue(
            "done",
            NOW - timedelta(minutes=20),
            assignee=CTO_ID,
            number=5,
            origin_kind="stranded_issue_recovery",
        ),
        "stale-infra": _issue("blocked", stale_updated, assignee=PE_ID, number=6),
        "stale-extra-1": _issue("done", stale_updated, assignee=CTO_ID, number=7),
        "stale-extra-2": _issue("done", stale_updated, assignee=CTO_ID, number=8),
        "stale-extra-3": _issue("in_progress", stale_updated, assignee=PE_ID, number=9),
        "stale-extra-4": _issue("in_review", stale_updated, assignee=PE_ID, number=10),
        "fresh-review-control": _issue("in_review", fresh_updated, assignee=PE_ID, number=11),
        "fresh-cross-team-control": _issue(
            "in_progress",
            fresh_updated,
            assignee=CODEX_QA_ID,
            number=12,
        ),
    }
    pstate.issue_comments = {
        "stale-comment-only": [
            {
                "id": "c-1",
                "body": f"[@CR](agent://{CR_ID}?i=eye) your turn",
                "authorAgentId": PE_ID,
                "createdAt": (stale_updated - timedelta(minutes=5))
                .isoformat()
                .replace("+00:00", "Z"),
            }
        ],
        "stale-infra": [
            {
                "id": "c-2",
                "body": "HTTP 429 Too Many Requests",
                "authorAgentId": CTO_ID,
                "createdAt": (NOW - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
            }
        ],
        "fresh-review-control": [],
        "fresh-cross-team-control": [],
    }
    pstate.agents[COMPANY_ID] = [
        {"id": PE_ID, "name": "PythonEngineer", "status": "idle"},
        {"id": CR_ID, "name": "CodeReviewer", "status": "idle"},
        {"id": CTO_ID, "name": "CTO", "status": "idle"},
    ]

    cfg = _cfg(tmp_path, base_url)
    state = State.load(tmp_path / "state.json")
    client = PaperclipClient(base_url=base_url, api_key="tok")

    try:
        with (
            patch("gimle_watchdog.daemon.detection.scan_idle_hangs", return_value=[]),
            patch(
                "gimle_watchdog.daemon.detection.scan_died_mid_work",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "gimle_watchdog.detection_semantic.load_team_uuids_from_repo",
                return_value={"claude": {PE_ID, CR_ID, CTO_ID}, "codex": {CODEX_QA_ID}},
            ),
            patch.object(client, "_last_response_date", NOW),
        ):
            await daemon._tick(cfg, state, client)
    finally:
        await client.aclose()

    posted_issue_ids = {issue_id for issue_id, _ in pstate.comments_posted}
    assert posted_issue_ids.isdisjoint(STALE_IDS)
    assert "fresh-review-control" in posted_issue_ids
    assert "fresh-cross-team-control" in posted_issue_ids
    assert all(not key.startswith(tuple(STALE_IDS)) for key in state.alerted_handoffs)
