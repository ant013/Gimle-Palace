"""E2E: recovery age gate skips stale issues."""

from __future__ import annotations

import datetime as dt

import pytest

from gimle_watchdog.daemon import _tick
from gimle_watchdog.paperclip import PaperclipClient
from gimle_watchdog.state import State


@pytest.mark.asyncio
async def test_recovery_skips_issue_older_than_recover_max_age_min(
    recovery_only_config, mock_paperclip, tmp_path
) -> None:
    base_url, state_mock = mock_paperclip
    state_mock.companies = [
        {
            "id": recovery_only_config.companies[0].id,
            "name": recovery_only_config.companies[0].name,
            "archived": False,
        }
    ]
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=4)).isoformat().replace(
        "+00:00", "Z"
    )
    state_mock.issues["stale-uuid"] = {
        "id": "stale-uuid",
        "status": "in_progress",
        "assigneeAgentId": "agent-x",
        "executionRunId": None,
        "originKind": "agent",
        "updatedAt": old,
        "issueNumber": 0,
    }

    client = PaperclipClient(base_url=base_url, api_key="test")
    state = State.load(tmp_path / "state.json")
    try:
        await _tick(recovery_only_config, state, client)
    finally:
        await client.aclose()

    assert state_mock.issues["stale-uuid"]["executionRunId"] is None
