"""Tests for watchdog.__main__ — CLI argparse + dispatch (no system calls)."""

from __future__ import annotations

import sys
from pathlib import Path

from gimle_watchdog import __main__ as cli


def test_main_no_args_prints_help(capsys):
    rc = cli.main(["watchdog"])
    out = capsys.readouterr()
    assert rc == 2
    combined = (out.err + out.out).lower()
    assert "usage" in combined


def test_dispatch_known_commands():
    for cmd in ("install", "uninstall", "run", "tick", "status", "tail", "escalate", "unescalate"):
        parser = cli._build_parser()
        assert cmd in parser.format_help()


def test_dry_run_install_prints_plist_for_macos(tmp_path, monkeypatch, capsys):
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text("""
version: 1
paperclip: {base_url: http://x, api_key_source: "inline:k"}
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds: {died_min: 3, hang_etime_min: 60, hang_cpu_max_s: 30}
daemon: {poll_interval_seconds: 120}
cooldowns: {per_issue_seconds: 300, per_agent_cap: 3, per_agent_window_seconds: 900}
logging: {path: /tmp/x.log, level: INFO, rotate_max_bytes: 10485760, rotate_backup_count: 5}
escalation: {post_comment_on_issue: true, comment_marker: "<!-- x -->"}
""")
    monkeypatch.setattr(sys, "platform", "darwin")
    rc = cli.main(["watchdog", "--config", str(cfg_path), "install", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "work.ant013.gimle-watchdog" in out
