"""Tests for watchdog.__main__ — CLI argparse + dispatch (no system calls)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import httpx

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
    thresholds: {died_min: 3, hang_etime_min: 60, idle_cpu_ratio_max: 0.005, hang_stream_idle_max_s: 300}
daemon: {poll_interval_seconds: 120}
cooldowns: {per_issue_seconds: 300, per_agent_cap: 3, per_agent_window_seconds: 900}
logging: {path: /tmp/x.log, level: INFO, rotate_max_bytes: 10485760, rotate_backup_count: 5}
escalation: {post_comment_on_issue: true, comment_marker: "<!-- x -->"}
""")
    monkeypatch.setattr(sys, "platform", "darwin")
    rc = cli.main(["watchdog", "install", "--config", str(cfg_path), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "work.ant013.gimle-watchdog" in out


def _minimal_cfg(tmp_path: Path, *, paperclip_base_url: str = "http://x") -> Path:
    cfg_path = tmp_path / "cfg.yaml"
    log_path = tmp_path / "watchdog.log"
    cfg_path.write_text(f"""
version: 1
paperclip: {{base_url: {paperclip_base_url}, api_key_source: "inline:k"}}
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds: {{died_min: 3, hang_etime_min: 60, idle_cpu_ratio_max: 0.005, hang_stream_idle_max_s: 300, recover_max_age_min: 180}}
daemon: {{poll_interval_seconds: 120}}
cooldowns: {{per_issue_seconds: 300, per_agent_cap: 3, per_agent_window_seconds: 900}}
logging: {{path: {log_path}, level: INFO, rotate_max_bytes: 10485760, rotate_backup_count: 5}}
escalation: {{post_comment_on_issue: true, comment_marker: "<!-- x -->"}}
""")
    return cfg_path


def test_cmd_status(tmp_path: Path, capsys, monkeypatch, mock_paperclip):
    base_url, state_mock = mock_paperclip
    state_mock.companies = [
        {"id": "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64", "name": "gimle", "archived": False}
    ]
    cfg_path = _minimal_cfg(tmp_path, paperclip_base_url=base_url)
    state_file = tmp_path / "watchdog-state.json"
    monkeypatch.setattr(cli, "_DEFAULT_STATE_PATH", str(state_file))
    rc = cli.main(["watchdog", "status", "--config", str(cfg_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Effective mode:" in out
    assert "Companies configured: 1" in out
    assert "Active cooldowns: 0" in out


def test_cmd_status_prints_mode_and_reconciliation(capsys, monkeypatch, observe_only_config_file):
    monkeypatch.setattr(
        "gimle_watchdog.__main__.PaperclipClient.list_companies",
        AsyncMock(
            return_value=[
                {
                    "id": "9d8f432c-0000-4000-8000-000000000001",
                    "name": "Test",
                    "archived": False,
                }
            ]
        ),
    )

    rc = cli.main(["watchdog", "status", "--config", str(observe_only_config_file)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Effective mode: observe-only" in out
    assert "Recovery enabled: false" in out
    assert "Handoff recent window min: 180" in out
    assert "recover_max_age_min=180" in out
    assert "configured_but_missing" not in out
    assert "live_but_unconfigured" not in out
    assert "Companies configured: 1" in out
    assert "Active cooldowns:" in out


def test_cmd_status_warns_on_live_but_unconfigured(
    capsys, monkeypatch, observe_only_config_file
):
    monkeypatch.setattr(
        "gimle_watchdog.__main__.PaperclipClient.list_companies",
        AsyncMock(
            return_value=[
                {
                    "id": "9d8f432c-0000-4000-8000-000000000001",
                    "name": "Test",
                    "archived": False,
                },
                {"id": "uuid-7", "name": "Trading", "archived": False},
            ]
        ),
    )

    rc = cli.main(["watchdog", "status", "--config", str(observe_only_config_file)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "live_but_unconfigured=uuid-7" in out
    assert "name=Trading" in out


def test_cmd_status_exits_2_on_api_failure(capsys, monkeypatch, observe_only_config_file):
    monkeypatch.setattr(
        "gimle_watchdog.__main__.PaperclipClient.list_companies",
        AsyncMock(side_effect=httpx.ConnectError("dns")),
    )

    rc = cli.main(["watchdog", "status", "--config", str(observe_only_config_file)])
    out = capsys.readouterr().out

    assert rc == 2
    assert "company_inventory=unreachable" in out
    assert "reason=" in out


def test_cmd_status_allow_degraded_returns_0_on_api_failure(
    capsys, monkeypatch, observe_only_config_file
):
    monkeypatch.setattr(
        "gimle_watchdog.__main__.PaperclipClient.list_companies",
        AsyncMock(side_effect=httpx.ConnectError("dns")),
    )

    rc = cli.main(
        ["watchdog", "status", "--allow-degraded", "--config", str(observe_only_config_file)]
    )
    out = capsys.readouterr().out

    assert rc == 0
    assert "company_inventory=unreachable" in out


def test_cmd_tail_no_log(tmp_path: Path, capsys):
    cfg_path = _minimal_cfg(tmp_path)
    rc = cli.main(["watchdog", "tail", "--config", str(cfg_path)])
    assert rc == 1
    assert "does not exist" in capsys.readouterr().err


def test_cmd_tail_with_log(tmp_path: Path, capsys):
    cfg_path = _minimal_cfg(tmp_path)
    log_path = tmp_path / "watchdog.log"
    entry = json.dumps(
        {"ts": "2026-04-21T10:00:00Z", "level": "INFO", "name": "watchdog", "message": "hi"}
    )
    log_path.write_text(entry + "\n")
    rc = cli.main(["watchdog", "tail", "--config", str(cfg_path), "-n", "5"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "hi" in out


def test_cmd_escalate(tmp_path: Path, capsys, monkeypatch):
    import argparse

    state_path = tmp_path / "state.json"
    monkeypatch.setattr(cli, "_DEFAULT_STATE_PATH", str(state_path))
    args = argparse.Namespace(issue="issue-x")
    rc = cli._cmd_escalate(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert "permanently escalated" in out


def test_cmd_unescalate(tmp_path: Path, capsys, monkeypatch):
    import argparse

    state_path = tmp_path / "state.json"
    monkeypatch.setattr(cli, "_DEFAULT_STATE_PATH", str(state_path))
    args = argparse.Namespace(issue="issue-y")
    rc = cli._cmd_unescalate(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert "cleared" in out


# GIM-69 regression: --config must be accepted after the subcommand


def test_config_after_subcommand_run(tmp_path: Path) -> None:
    """'run --config X' must parse without error (matches service renderer output)."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("")
    args = cli._build_parser().parse_args(["run", "--config", str(cfg)])
    assert args.command == "run"
    assert args.config == cfg


def test_config_after_subcommand_tick(tmp_path: Path) -> None:
    """'tick --config X' must parse without error (matches cron renderer output)."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("")
    args = cli._build_parser().parse_args(["tick", "--config", str(cfg)])
    assert args.command == "tick"
    assert args.config == cfg


def test_detect_platform_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert cli._detect_platform() == "linux"


def test_detect_platform_unknown(monkeypatch):
    monkeypatch.setattr(sys, "platform", "freebsd12")
    assert cli._detect_platform() == "unknown"


def test_dry_run_install_linux(tmp_path, monkeypatch, capsys):
    cfg_path = _minimal_cfg(tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    rc = cli.main(["watchdog", "install", "--config", str(cfg_path), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "WantedBy=default.target" in out  # systemd unit marker


def test_install_unsupported_platform(tmp_path, monkeypatch, capsys):
    cfg_path = _minimal_cfg(tmp_path)
    monkeypatch.setattr(sys, "platform", "freebsd12")
    rc = cli.main(["watchdog", "install", "--config", str(cfg_path), "--dry-run"])
    assert rc == 1
    assert "Unsupported" in capsys.readouterr().err


def test_main_no_command(capsys):
    # The no-command path (args.command is None) triggers rc=2
    parser = cli._build_parser()
    args = parser.parse_args([])
    assert args.command is None


def test_main_config_error(tmp_path, capsys):
    bad_cfg = tmp_path / "bad.yaml"
    bad_cfg.write_text("version: 1\n")  # missing required fields
    rc = cli.main(["watchdog", "status", "--config", str(bad_cfg)])
    assert rc == 2
    assert "config error" in capsys.readouterr().err


def test_cmd_debug_watchdog_empty(tmp_path, monkeypatch, capsys):
    from unittest.mock import patch

    cfg_path = _minimal_cfg(tmp_path)
    with patch("gimle_watchdog.detection.scan_idle_hangs", return_value=[]):
        rc = cli.main(["watchdog", "run", "--config", str(cfg_path), "--debug-watchdog"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "No candidate" in out


def test_cmd_debug_watchdog_with_procs(tmp_path, monkeypatch, capsys):
    from unittest.mock import patch

    from gimle_watchdog.detection import HangedProc

    cfg_path = _minimal_cfg(tmp_path)
    proc = HangedProc(
        pid=9999,
        etime_s=3600,
        cpu_s=5,
        cpu_ratio=0.0014,
        command="paperclip-skills test",
    )
    with patch("gimle_watchdog.detection.scan_idle_hangs", return_value=[proc]):
        rc = cli.main(["watchdog", "run", "--config", str(cfg_path), "--debug-watchdog"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "9999" in out
