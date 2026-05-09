"""Tests for watchdog.config — YAML schema + validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from gimle_watchdog import config as cfg


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "watchdog.yaml"
    p.write_text(content)
    return p


def test_valid_config_parses(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TEST_TOKEN", "secret-123")
    path = _write(
        tmp_path,
        """
version: 1
paperclip:
  base_url: http://localhost:3100
  api_key_source: env:TEST_TOKEN
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds:
      died_min: 3
      hang_etime_min: 60
      idle_cpu_ratio_max: 0.005
      hang_stream_idle_max_s: 300
daemon:
  poll_interval_seconds: 120
cooldowns:
  per_issue_seconds: 300
  per_agent_cap: 3
  per_agent_window_seconds: 900
logging:
  path: ~/.paperclip/watchdog.log
  level: INFO
  rotate_max_bytes: 10485760
  rotate_backup_count: 5
escalation:
  post_comment_on_issue: true
  comment_marker: "<!-- watchdog-escalation -->"
handoff:
  handoff_recent_window_min: 240
  handoff_alert_soft_budget_per_tick: 7
  handoff_alert_hard_budget_per_tick: 11
""",
    )
    c = cfg.load_config(path)
    assert c.version == 1
    assert c.paperclip.base_url == "http://localhost:3100"
    assert c.paperclip.api_key == "secret-123"
    assert len(c.companies) == 1
    assert c.companies[0].id == "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
    assert c.companies[0].name == "gimle"
    assert c.companies[0].thresholds.hang_etime_min == 60
    assert c.companies[0].thresholds.idle_cpu_ratio_max == 0.005
    assert c.companies[0].thresholds.hang_stream_idle_max_s == 300
    assert c.companies[0].thresholds.hang_cpu_max_s is None
    assert c.cooldowns.per_agent_cap == 3
    assert c.escalation.post_comment_on_issue is True
    assert c.handoff.handoff_recent_window_min == 240
    assert c.handoff.handoff_alert_soft_budget_per_tick == 7
    assert c.handoff.handoff_alert_hard_budget_per_tick == 11


def test_unknown_version_raises(tmp_path: Path):
    path = _write(tmp_path, "version: 999\ncompanies: []\n")
    with pytest.raises(cfg.ConfigError) as exc:
        cfg.load_config(path)
    assert "version" in str(exc.value)


def test_empty_companies_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """
version: 1
paperclip: {base_url: http://x, api_key_source: "inline:k"}
companies: []
daemon: {poll_interval_seconds: 120}
cooldowns: {per_issue_seconds: 300, per_agent_cap: 3, per_agent_window_seconds: 900}
logging: {path: /tmp/x.log, level: INFO, rotate_max_bytes: 1, rotate_backup_count: 1}
escalation: {post_comment_on_issue: false, comment_marker: "x"}
""",
    )
    with pytest.raises(cfg.ConfigError, match="companies.*non-empty"):
        cfg.load_config(path)


def test_invalid_uuid_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """
version: 1
paperclip: {base_url: http://x, api_key_source: "inline:k"}
companies:
  - id: not-a-uuid
    name: bad
    thresholds: {died_min: 3, hang_etime_min: 60, idle_cpu_ratio_max: 0.005, hang_stream_idle_max_s: 300}
daemon: {poll_interval_seconds: 120}
cooldowns: {per_issue_seconds: 300, per_agent_cap: 3, per_agent_window_seconds: 900}
logging: {path: /tmp/x.log, level: INFO, rotate_max_bytes: 1, rotate_backup_count: 1}
escalation: {post_comment_on_issue: false, comment_marker: "x"}
""",
    )
    with pytest.raises(cfg.ConfigError, match="uuid"):
        cfg.load_config(path)


def test_api_key_env_resolution_missing_warns(tmp_path: Path, monkeypatch, caplog):
    monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
    path = _write(
        tmp_path,
        """
version: 1
paperclip: {base_url: http://x, api_key_source: "env:NONEXISTENT_VAR"}
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds: {died_min: 3, hang_etime_min: 60, idle_cpu_ratio_max: 0.005, hang_stream_idle_max_s: 300}
daemon: {poll_interval_seconds: 120}
cooldowns: {per_issue_seconds: 300, per_agent_cap: 3, per_agent_window_seconds: 900}
logging: {path: /tmp/x.log, level: INFO, rotate_max_bytes: 1, rotate_backup_count: 1}
escalation: {post_comment_on_issue: false, comment_marker: "x"}
""",
    )
    c = cfg.load_config(path)
    assert c.paperclip.api_key is None  # missing env -> None, WARN logged


def test_api_key_file_resolution(tmp_path: Path):
    token_file = tmp_path / "token.txt"
    token_file.write_text("file-token-456\n")
    path = _write(
        tmp_path,
        f"""
version: 1
paperclip:
  base_url: http://x
  api_key_source: "file:{token_file}"
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds: {{died_min: 3, hang_etime_min: 60, idle_cpu_ratio_max: 0.005, hang_stream_idle_max_s: 300}}
daemon: {{poll_interval_seconds: 120}}
cooldowns: {{per_issue_seconds: 300, per_agent_cap: 3, per_agent_window_seconds: 900}}
logging: {{path: /tmp/x.log, level: INFO, rotate_max_bytes: 1, rotate_backup_count: 1}}
escalation: {{post_comment_on_issue: false, comment_marker: "x"}}
""",
    )
    c = cfg.load_config(path)
    assert c.paperclip.api_key == "file-token-456"


def test_negative_threshold_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """
version: 1
paperclip: {base_url: http://x, api_key_source: "inline:k"}
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds: {died_min: -1, hang_etime_min: 60, idle_cpu_ratio_max: 0.005, hang_stream_idle_max_s: 300}
daemon: {poll_interval_seconds: 120}
cooldowns: {per_issue_seconds: 300, per_agent_cap: 3, per_agent_window_seconds: 900}
logging: {path: /tmp/x.log, level: INFO, rotate_max_bytes: 1, rotate_backup_count: 1}
escalation: {post_comment_on_issue: false, comment_marker: "x"}
""",
    )
    with pytest.raises(cfg.ConfigError, match="positive"):
        cfg.load_config(path)


def test_per_agent_cap_zero_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """
version: 1
paperclip: {base_url: http://x, api_key_source: "inline:k"}
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds: {died_min: 3, hang_etime_min: 60, idle_cpu_ratio_max: 0.005, hang_stream_idle_max_s: 300}
daemon: {poll_interval_seconds: 120}
cooldowns: {per_issue_seconds: 300, per_agent_cap: 0, per_agent_window_seconds: 900}
logging: {path: /tmp/x.log, level: INFO, rotate_max_bytes: 1, rotate_backup_count: 1}
escalation: {post_comment_on_issue: false, comment_marker: "x"}
""",
    )
    with pytest.raises(cfg.ConfigError, match="per_agent_cap"):
        cfg.load_config(path)


# --- New GIM-80 threshold tests -------------------------------------------------


_BASE_YAML = """\
version: 1
paperclip: {{base_url: http://x, api_key_source: "inline:k"}}
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds: {thresholds}
daemon: {{poll_interval_seconds: 120}}
cooldowns: {{per_issue_seconds: 300, per_agent_cap: 3, per_agent_window_seconds: 900}}
logging: {{path: /tmp/x.log, level: INFO, rotate_max_bytes: 1, rotate_backup_count: 1}}
escalation: {{post_comment_on_issue: false, comment_marker: "x"}}
"""


def test_config_load_raises_without_idle_cpu_ratio_max(tmp_path: Path):
    path = _write(
        tmp_path,
        _BASE_YAML.format(
            thresholds="{died_min: 3, hang_etime_min: 60, hang_cpu_max_s: 30, hang_stream_idle_max_s: 300}"
        ),
    )
    with pytest.raises(cfg.ConfigError, match="hang_cpu_max_s is no longer supported"):
        cfg.load_config(path)


def test_config_load_warns_on_deprecated_hang_cpu_max_s(tmp_path: Path, caplog):
    import logging

    path = _write(
        tmp_path,
        _BASE_YAML.format(
            thresholds=(
                "{died_min: 3, hang_etime_min: 60, "
                "hang_cpu_max_s: 30, idle_cpu_ratio_max: 0.005, hang_stream_idle_max_s: 300}"
            )
        ),
    )
    with caplog.at_level(logging.WARNING, logger="watchdog.config"):
        c = cfg.load_config(path)
    assert c.companies[0].thresholds.hang_cpu_max_s is None
    assert c.companies[0].thresholds.idle_cpu_ratio_max == 0.005
    assert any("deprecated" in r.message for r in caplog.records)


def test_config_load_validates_ratio_range(tmp_path: Path):
    for bad_ratio in [0.0, 1.0, -0.1, 1.5]:
        path = _write(
            tmp_path,
            _BASE_YAML.format(
                thresholds=f"{{died_min: 3, hang_etime_min: 60, idle_cpu_ratio_max: {bad_ratio}, hang_stream_idle_max_s: 300}}"
            ),
        )
        with pytest.raises(cfg.ConfigError, match="idle_cpu_ratio_max"):
            cfg.load_config(path)


def test_config_load_validates_stream_idle_positive(tmp_path: Path):
    path = _write(
        tmp_path,
        _BASE_YAML.format(
            thresholds="{died_min: 3, hang_etime_min: 60, idle_cpu_ratio_max: 0.005, hang_stream_idle_max_s: 0}"
        ),
    )
    with pytest.raises(cfg.ConfigError, match="positive"):
        cfg.load_config(path)


# --- T7: HandoffConfig ---------------------------------------------------------

_FULL_YAML = """\
version: 1
paperclip: {{base_url: http://x, api_key_source: "inline:k"}}
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds: {{died_min: 3, hang_etime_min: 60, idle_cpu_ratio_max: 0.005, hang_stream_idle_max_s: 300}}
daemon: {{poll_interval_seconds: 120}}
cooldowns: {{per_issue_seconds: 300, per_agent_cap: 3, per_agent_window_seconds: 900}}
logging: {{path: /tmp/x.log, level: INFO, rotate_max_bytes: 1, rotate_backup_count: 1}}
escalation: {{post_comment_on_issue: false, comment_marker: "x"}}
{handoff}
"""


def test_handoff_defaults_when_section_absent(tmp_path: Path):
    """When handoff: section is absent, defaults are applied and alert is disabled."""
    path = _write(tmp_path, _FULL_YAML.format(handoff=""))
    c = cfg.load_config(path)
    assert c.handoff.handoff_alert_enabled is False
    assert c.handoff.handoff_comment_lookback_min == 5
    assert c.handoff.handoff_wrong_assignee_min == 3
    assert c.handoff.handoff_review_owner_min == 5
    assert c.handoff.handoff_comments_per_issue == 5
    assert c.handoff.handoff_max_issues_per_tick == 30
    assert c.handoff.handoff_alert_cooldown_min == 30


def test_handoff_enabled_from_yaml(tmp_path: Path):
    """handoff_alert_enabled: true is parsed correctly and overrides are applied."""
    path = _write(
        tmp_path,
        _FULL_YAML.format(
            handoff="handoff:\n  handoff_alert_enabled: true\n  handoff_alert_cooldown_min: 60"
        ),
    )
    c = cfg.load_config(path)
    assert c.handoff.handoff_alert_enabled is True
    assert c.handoff.handoff_alert_cooldown_min == 60


def test_handoff_unknown_key_raises(tmp_path: Path):
    """Unknown key in handoff: section raises ConfigError (strict validation)."""
    path = _write(
        tmp_path,
        _FULL_YAML.format(handoff="handoff:\n  typo_key: 99"),
    )
    with pytest.raises(cfg.ConfigError, match="handoff"):
        cfg.load_config(path)
