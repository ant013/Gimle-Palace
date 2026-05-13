"""GIM-255 cohort isolation tests."""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from gimle_watchdog.config import ALERT_FLAG_NAMES
from gimle_watchdog.daemon import _tick
from gimle_watchdog.paperclip import PaperclipClient
from gimle_watchdog.state import State


_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "gim255_cohort.json"
_TEST_ASSIGNEE_AGENT_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(scope="module")
def cohort() -> dict:
    return json.loads(_FIXTURE.read_text())


def _seed_cohort_into_mock(state_mock, cohort: dict) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    old = (now - dt.timedelta(hours=48)).isoformat().replace("+00:00", "Z")
    for issue_uuid, issue_number in zip(cohort["paperclip_issue_ids"], cohort["issue_numbers"]):
        state_mock.issues[issue_uuid] = {
            "id": issue_uuid,
            "title": f"GIM-{issue_number}",
            "status": "in_progress",
            "assigneeAgentId": _TEST_ASSIGNEE_AGENT_ID,
            "assigneeUserId": (cohort.get("author_user_ids") or [None])[0],
            "executionRunId": None,
            "originKind": "agent",
            "updatedAt": old,
            "issueNumber": issue_number,
        }


@pytest.mark.parametrize("flag_name", sorted(ALERT_FLAG_NAMES))
@pytest.mark.asyncio
async def test_cohort_isolation_per_detector_flag(
    flag_name: str, cohort: dict, observe_only_config, mock_paperclip, tmp_path, caplog
) -> None:
    base_url, state_mock = mock_paperclip
    state_mock.companies = [
        {
            "id": observe_only_config.companies[0].id,
            "name": observe_only_config.companies[0].name,
            "archived": False,
        }
    ]
    _seed_cohort_into_mock(state_mock, cohort)

    cfg = replace(
        observe_only_config, handoff=replace(observe_only_config.handoff, **{flag_name: True})
    )
    client = PaperclipClient(base_url=base_url, api_key="test")
    state = State.load(tmp_path / "state.json")
    try:
        with caplog.at_level(logging.WARNING, logger="watchdog"):
            await _tick(cfg, state, client)
    finally:
        await client.aclose()

    cohort_ids = set(cohort["paperclip_issue_ids"])
    posted_against_cohort = [
        (issue_id, body) for issue_id, body in state_mock.comments_posted if issue_id in cohort_ids
    ]
    patched_against_cohort = [
        issue_id
        for issue_id, issue in state_mock.issues.items()
        if issue_id in cohort_ids and issue.get("executionRunId") is not None
    ]
    assert not posted_against_cohort, f"{flag_name} posted on cohort: {posted_against_cohort}"
    assert not patched_against_cohort, (
        f"{flag_name} patched cohort issues: {patched_against_cohort}"
    )
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert not errors, f"{flag_name} produced unexpected errors: {errors}"


@pytest.mark.asyncio
async def test_cohort_isolation_recovery_path(
    cohort: dict, recovery_only_config, mock_paperclip, tmp_path, caplog
) -> None:
    base_url, state_mock = mock_paperclip
    state_mock.companies = [
        {
            "id": recovery_only_config.companies[0].id,
            "name": recovery_only_config.companies[0].name,
            "archived": False,
        }
    ]
    _seed_cohort_into_mock(state_mock, cohort)

    client = PaperclipClient(base_url=base_url, api_key="test")
    state = State.load(tmp_path / "state.json")
    try:
        with caplog.at_level(logging.WARNING, logger="watchdog"):
            await _tick(recovery_only_config, state, client)
    finally:
        await client.aclose()

    cohort_ids = set(cohort["paperclip_issue_ids"])
    woken = [
        issue_id
        for issue_id, issue in state_mock.issues.items()
        if issue_id in cohort_ids and issue.get("executionRunId") is not None
    ]
    assert not woken, f"recovery woke cohort issues: {woken}"
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert not errors, f"recovery produced unexpected errors: {errors}"
