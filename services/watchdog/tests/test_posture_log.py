"""Tests for watchdog_starting + watchdog_posture structured log events."""

from __future__ import annotations

import json
import logging
import os

import pytest

from gimle_watchdog import __main__ as main_mod
from gimle_watchdog.config import Config, EffectiveMode
from gimle_watchdog.daemon import _tick
from gimle_watchdog.paperclip import PaperclipClient
from gimle_watchdog.state import State


def test_watchdog_starting_emitted_before_config_load(caplog, capfd, tmp_path) -> None:
    """watchdog_starting fires before config load through stderr and logging."""

    bogus_config = tmp_path / "does-not-exist.yaml"

    with caplog.at_level(logging.INFO, logger="watchdog"):
        rc = main_mod.main(["watchdog", "status", "--config", str(bogus_config)])

    assert rc == 2

    err = capfd.readouterr().err
    assert '"event": "watchdog_starting"' in err
    payload = json.loads(_extract_first_json_line(err))
    assert payload["pid"] == os.getpid()
    assert "version" in payload
    assert payload["config_path"] == str(bogus_config)
    assert "argv" in payload

    starting_records = [
        record for record in caplog.records if getattr(record, "event", None) == "watchdog_starting"
    ]
    assert starting_records, "watchdog_starting log record was not emitted"
    assert caplog.records[0] is starting_records[0]


def _extract_first_json_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            return line
    raise AssertionError(f"no JSON line found in: {text!r}")


@pytest.mark.asyncio
async def test_watchdog_posture_emitted_at_tick_start(
    caplog, observe_only_config: Config, mock_paperclip, tmp_path
) -> None:
    """watchdog_posture is emitted at tick start with the full posture payload."""

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
        with caplog.at_level(logging.INFO, logger="watchdog"):
            await _tick(observe_only_config, state, client)
    finally:
        await client.aclose()

    posture_records = [
        record for record in caplog.records if getattr(record, "event", None) == "watchdog_posture"
    ]
    assert len(posture_records) == 1
    record = posture_records[0]

    for field_name in (
        "mode",
        "company_count",
        "company_names",
        "company_ids",
        "configured_but_missing",
        "live_but_unconfigured",
        "recovery_enabled",
        "recovery_baseline_completed",
        "max_actions_per_tick",
        "handoff_recent_window_min",
        "recover_max_age_min_per_company",
        "handoff_alert_enabled",
        "handoff_cross_team_enabled",
        "handoff_ownerless_enabled",
        "handoff_infra_block_enabled",
        "handoff_stale_bundle_enabled",
        "handoff_auto_repair_enabled",
        "alert_budget_soft",
        "alert_budget_hard",
    ):
        assert hasattr(record, field_name), f"watchdog_posture missing field {field_name!r}"

    assert record.mode == EffectiveMode.OBSERVE_ONLY.value
    assert isinstance(record.recover_max_age_min_per_company, dict)
