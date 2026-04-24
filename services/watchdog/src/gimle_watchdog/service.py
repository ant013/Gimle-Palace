"""Platform-native service installer renderers (no system calls)."""

from __future__ import annotations

from pathlib import Path


SERVICE_LABEL = "work.ant013.gimle-watchdog"


def render_plist(
    *,
    venv_python: Path,
    config_path: Path,
    log_path: Path,
    err_path: Path,
) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>{SERVICE_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{venv_python}</string>
        <string>-m</string>
        <string>watchdog</string>
        <string>run</string>
        <string>--config</string>
        <string>{config_path}</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>{log_path}</string>
    <key>StandardErrorPath</key><string>{err_path}</string>
</dict>
</plist>"""


def render_systemd_unit(
    *,
    venv_python: Path,
    config_path: Path,
    log_path: Path,
    err_path: Path,
) -> str:
    return f"""[Unit]
Description=Gimle Palace agent watchdog (GIM-63)
After=network.target

[Service]
Type=simple
ExecStart={venv_python} -m watchdog run --config {config_path}
Restart=on-failure
RestartSec=10s
StandardOutput=append:{log_path}
StandardError=append:{err_path}

[Install]
WantedBy=default.target"""


def render_cron_entry(
    *,
    venv_python: Path,
    config_path: Path,
    poll_interval_seconds: int,
) -> str:
    minutes = max(1, poll_interval_seconds // 60)
    return f"*/{minutes} * * * * {venv_python} -m watchdog tick --config {config_path}"
