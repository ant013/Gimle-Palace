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
      hang_cpu_max_s: 30
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
    assert c.cooldowns.per_agent_cap == 3
    assert c.escalation.post_comment_on_issue is True


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
    thresholds: {died_min: 3, hang_etime_min: 60, hang_cpu_max_s: 30}
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
    thresholds: {died_min: 3, hang_etime_min: 60, hang_cpu_max_s: 30}
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
    thresholds: {{died_min: 3, hang_etime_min: 60, hang_cpu_max_s: 30}}
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
    thresholds: {died_min: -1, hang_etime_min: 60, hang_cpu_max_s: 30}
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
    thresholds: {died_min: 3, hang_etime_min: 60, hang_cpu_max_s: 30}
daemon: {poll_interval_seconds: 120}
cooldowns: {per_issue_seconds: 300, per_agent_cap: 0, per_agent_window_seconds: 900}
logging: {path: /tmp/x.log, level: INFO, rotate_max_bytes: 1, rotate_backup_count: 1}
escalation: {post_comment_on_issue: false, comment_marker: "x"}
""",
    )
    with pytest.raises(cfg.ConfigError, match="per_agent_cap"):
        cfg.load_config(path)
