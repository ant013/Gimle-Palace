"""Daemon-level mode contract tests."""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import replace

import pytest

from gimle_watchdog.config import EffectiveMode, describe_effective_mode
from gimle_watchdog.daemon import _tick
from gimle_watchdog.paperclip import PaperclipClient
from gimle_watchdog.state import State


def _seed_stuck_issue(state_mock, *, issue_id: str = "issue-stuck-1") -> None:
    now = dt.datetime.now(dt.timezone.utc)
    state_mock.issues[issue_id] = {
        "id": issue_id,
        "title": "Stuck",
        "status": "in_progress",
        "assigneeAgentId": "agent-stuck",
        "executionRunId": None,
        "originKind": "agent",
        "updatedAt": (now - dt.timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        "issueNumber": 999,
    }


@pytest.mark.asyncio
async def test_observe_only_tick_emits_zero_side_effects(
    observe_only_config, mock_paperclip, tmp_path, caplog
) -> None:
    assert describe_effective_mode(observe_only_config) == EffectiveMode.OBSERVE_ONLY

    base_url, state_mock = mock_paperclip
    state_mock.companies = [
        {
            "id": observe_only_config.companies[0].id,
            "name": observe_only_config.companies[0].name,
            "archived": False,
        }
    ]
    client = PaperclipClient(base_url=base_url, api_key="test")
    state = State.load(tmp_path / "state.json")

    try:
        with caplog.at_level(logging.WARNING, logger="watchdog"):
            await _tick(observe_only_config, state, client)
    finally:
        await client.aclose()

    assert state_mock.comments_posted == []
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert not errors, f"unexpected errors during observe-only tick: {errors}"


@pytest.mark.asyncio
async def test_recovery_only_emits_no_alerts(recovery_only_config, mock_paperclip, tmp_path) -> None:
    assert describe_effective_mode(recovery_only_config) == EffectiveMode.RECOVERY_ONLY

    cfg = replace(
        recovery_only_config,
        daemon=replace(recovery_only_config.daemon, recovery_first_run_baseline_only=False),
    )
    base_url, state_mock = mock_paperclip
    state_mock.companies = [
        {
            "id": cfg.companies[0].id,
            "name": cfg.companies[0].name,
            "archived": False,
        }
    ]
    _seed_stuck_issue(state_mock)
    client = PaperclipClient(base_url=base_url, api_key="test")
    state = State.load(tmp_path / "state.json")
    try:
        await _tick(cfg, state, client)
    finally:
        await client.aclose()

    assert state_mock.comments_posted == []
    assert state_mock.issues["issue-stuck-1"]["executionRunId"] is not None


@pytest.mark.asyncio
async def test_alert_only_emits_no_recovery(alert_only_config, mock_paperclip, tmp_path) -> None:
    assert describe_effective_mode(alert_only_config) == EffectiveMode.ALERT_ONLY

    base_url, state_mock = mock_paperclip
    state_mock.companies = [
        {
            "id": alert_only_config.companies[0].id,
            "name": alert_only_config.companies[0].name,
            "archived": False,
        }
    ]
    _seed_stuck_issue(state_mock)
    client = PaperclipClient(base_url=base_url, api_key="test")
    state = State.load(tmp_path / "state.json")
    try:
        await _tick(alert_only_config, state, client)
    finally:
        await client.aclose()

    assert state_mock.issues["issue-stuck-1"]["assigneeAgentId"] == "agent-stuck"
    assert state_mock.issues["issue-stuck-1"]["executionRunId"] is None


@pytest.mark.asyncio
async def test_full_watchdog_budget_respected(full_watchdog_config, mock_paperclip, tmp_path) -> None:
    assert describe_effective_mode(full_watchdog_config) == EffectiveMode.FULL_WATCHDOG

    base_url, state_mock = mock_paperclip
    state_mock.companies = [
        {
            "id": full_watchdog_config.companies[0].id,
            "name": full_watchdog_config.companies[0].name,
            "archived": False,
        }
    ]
    _seed_stuck_issue(state_mock)
    client = PaperclipClient(base_url=base_url, api_key="test")
    state = State.load(tmp_path / "state.json")
    try:
        await _tick(full_watchdog_config, state, client)
    finally:
        await client.aclose()

    hard_budget = full_watchdog_config.handoff.handoff_alert_hard_budget_per_tick
    assert len(state_mock.comments_posted) <= hard_budget


@pytest.mark.asyncio
async def test_unsafe_auto_repair_mode_in_posture_log(
    unsafe_auto_repair_config, mock_paperclip, tmp_path, caplog
) -> None:
    assert describe_effective_mode(unsafe_auto_repair_config) == EffectiveMode.UNSAFE_AUTO_REPAIR

    base_url, state_mock = mock_paperclip
    state_mock.companies = [
        {
            "id": unsafe_auto_repair_config.companies[0].id,
            "name": unsafe_auto_repair_config.companies[0].name,
            "archived": False,
        }
    ]
    client = PaperclipClient(base_url=base_url, api_key="test")
    state = State.load(tmp_path / "state.json")

    try:
        with caplog.at_level(logging.INFO, logger="watchdog"):
            await _tick(unsafe_auto_repair_config, state, client)
    finally:
        await client.aclose()

    posture = [record for record in caplog.records if getattr(record, "event", None) == "watchdog_posture"]
    assert posture
    assert posture[0].mode == "unsafe-auto-repair"
