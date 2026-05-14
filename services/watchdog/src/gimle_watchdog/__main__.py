"""CLI — install/uninstall/run/tick/status/tail/escalate/unescalate."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any

from gimle_watchdog import daemon, detection, logger, service
from gimle_watchdog.config import ConfigError, EffectiveMode, describe_effective_mode, load_config
from gimle_watchdog.paperclip import PaperclipClient
from gimle_watchdog.state import State


log = logging.getLogger("watchdog.cli")

DEFAULT_CONFIG_PATH = Path("~/.paperclip/watchdog-config.yaml").expanduser()
_DEFAULT_STATE_PATH = str(Path("~/.paperclip/watchdog-state.json").expanduser())
PLIST_PATH = Path("~/Library/LaunchAgents/work.ant013.gimle-watchdog.plist").expanduser()
SYSTEMD_UNIT_PATH = Path("~/.config/systemd/user/gimle-watchdog.service").expanduser()


def _watchdog_version() -> str:
    try:
        return version("gimle-watchdog")
    except Exception:
        return "unknown"


def _extract_config_path(argv: list[str]) -> str | None:
    for index, token in enumerate(argv):
        if token == "--config" and index + 1 < len(argv):
            return argv[index + 1]
        if token.startswith("--config="):
            return token.split("=", 1)[1]
    return None


def _sanitize_argv(argv: list[str]) -> list[str]:
    return list(argv)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="watchdog", description="Gimle agent watchdog (GIM-63)")

    # Shared --config parent so every subcommand accepts `--config` after the subcommand
    # (e.g. `watchdog run --config X`), matching what service renderers emit.
    # add_help=False avoids a duplicate -h flag conflict.
    config_parent = argparse.ArgumentParser(add_help=False)
    config_parent.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)

    sub = parser.add_subparsers(dest="command")

    p_install = sub.add_parser("install", parents=[config_parent], help="install platform service")
    p_install.add_argument("--dry-run", action="store_true")
    p_install.add_argument("--force", action="store_true")
    p_install.add_argument("--discover-companies", action="store_true")

    sub.add_parser("uninstall", parents=[config_parent], help="remove platform service")

    p_run = sub.add_parser("run", parents=[config_parent], help="run daemon loop (launchd/systemd)")
    p_run.add_argument(
        "--debug-watchdog",
        action="store_true",
        help="scan once, print proc table, exit — no kill, no daemon loop",
    )

    p_tick = sub.add_parser("tick", parents=[config_parent], help="one-shot tick (cron)")
    p_tick.add_argument(
        "--debug-watchdog",
        action="store_true",
        help="scan once, print proc table, exit — no kill, no daemon loop",
    )
    p_status = sub.add_parser("status", parents=[config_parent], help="service + filter health")
    p_status.add_argument(
        "--allow-degraded",
        action="store_true",
        help="exit 0 even if Paperclip API is unreachable",
    )
    p_tail = sub.add_parser("tail", parents=[config_parent], help="tail log")
    p_tail.add_argument("-n", type=int, default=50)
    p_esc = sub.add_parser(
        "escalate", parents=[config_parent], help="manually mark issue permanent escalation"
    )
    p_esc.add_argument("--issue", required=True)
    p_unesc = sub.add_parser("unescalate", parents=[config_parent], help="clear escalation")
    p_unesc.add_argument("--issue", required=True)
    return parser


def _detect_platform() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return "unknown"


def _find_venv_python() -> Path:
    pkg_root = Path(__file__).resolve().parents[2]  # services/watchdog/
    return pkg_root / ".venv" / "bin" / "python"


def _cmd_install(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    venv_python = _find_venv_python()
    log_path = cfg.logging.path
    err_path = log_path.with_suffix(".err")
    platform = _detect_platform()

    if platform == "macos":
        rendered = service.render_plist(
            venv_python=venv_python,
            config_path=args.config,
            log_path=log_path,
            err_path=err_path,
        )
    elif platform == "linux":
        rendered = service.render_systemd_unit(
            venv_python=venv_python,
            config_path=args.config,
            log_path=log_path,
            err_path=err_path,
        )
    else:
        print(f"Unsupported platform {sys.platform}; use cron fallback manually.", file=sys.stderr)
        return 1

    if args.dry_run:
        print(rendered)
        return 0

    if platform == "macos":  # pragma: no cover
        PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        PLIST_PATH.write_text(rendered)
        subprocess.run(["launchctl", "load", "-w", str(PLIST_PATH)], check=True)
        print(f"installed launchd service: {PLIST_PATH}")
    else:  # pragma: no cover
        SYSTEMD_UNIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SYSTEMD_UNIT_PATH.write_text(rendered)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", "gimle-watchdog.service"], check=True
        )
        print(f"installed systemd unit: {SYSTEMD_UNIT_PATH}")
    return 0


def _cmd_uninstall(args: argparse.Namespace) -> int:  # pragma: no cover
    platform = _detect_platform()
    if platform == "macos":
        if PLIST_PATH.exists():
            subprocess.run(["launchctl", "unload", str(PLIST_PATH)], check=False)
            PLIST_PATH.unlink()
            print(f"removed {PLIST_PATH}")
    elif platform == "linux":
        if SYSTEMD_UNIT_PATH.exists():
            subprocess.run(
                ["systemctl", "--user", "disable", "--now", "gimle-watchdog.service"],
                check=False,
            )
            SYSTEMD_UNIT_PATH.unlink()
            print(f"removed {SYSTEMD_UNIT_PATH}")
    return 0


def _cmd_debug_watchdog(cfg_path: Path) -> int:
    """Scan once, print candidate proc table, exit. No kill, no daemon loop."""
    cfg = load_config(cfg_path)
    procs = detection.scan_idle_hangs(cfg)
    if not procs:
        print("No candidate hanged procs found.")
        return 0
    header = f"{'PID':>8}  {'etime_s':>8}  {'cpu_s':>6}  {'cpu_ratio':>10}  {'stream_age_s':>12}  command"
    print(header)
    print("-" * len(header))
    for p in procs:
        stream_age = str(p.stream_event_age_s) if p.stream_event_age_s is not None else "n/a"
        print(
            f"{p.pid:>8}  {p.etime_s:>8}  {p.cpu_s:>6}  {p.cpu_ratio:>10.4f}  {stream_age:>12}  {p.command[:60]}"
        )
    return 0


def _cmd_run(args: argparse.Namespace) -> int:  # pragma: no cover
    if getattr(args, "debug_watchdog", False):
        return _cmd_debug_watchdog(args.config)
    cfg = load_config(args.config)
    logger.setup_logging(cfg.logging)
    state_path = Path(_DEFAULT_STATE_PATH)
    state = State.load(state_path)
    client = PaperclipClient(base_url=cfg.paperclip.base_url, api_key=cfg.paperclip.api_key or "")

    async def _run() -> None:
        try:
            await daemon.run(cfg, state, client)
        finally:
            await client.aclose()

    asyncio.run(_run())
    return 0


def _cmd_tick(args: argparse.Namespace) -> int:  # pragma: no cover
    if getattr(args, "debug_watchdog", False):
        return _cmd_debug_watchdog(args.config)
    cfg = load_config(args.config)
    logger.setup_logging(cfg.logging)
    state_path = Path(_DEFAULT_STATE_PATH)
    state = State.load(state_path)
    client = PaperclipClient(base_url=cfg.paperclip.base_url, api_key=cfg.paperclip.api_key or "")

    async def _tick() -> None:
        try:
            await daemon._tick(cfg, state, client)
        finally:
            await client.aclose()

    asyncio.run(_tick())
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    state_path = Path(_DEFAULT_STATE_PATH)
    state = State.load(state_path)

    mode = describe_effective_mode(cfg)
    if mode == EffectiveMode.UNSAFE_AUTO_REPAIR:
        print("!!! UNSAFE AUTO-REPAIR ENABLED - Board has not approved !!!")
    print(f"Effective mode: {mode.value}")
    print(f"Recovery enabled: {str(cfg.daemon.recovery_enabled).lower()}")
    print(f"Recovery dry-run: {str(cfg.daemon.recovery_dry_run).lower()}")
    baseline_status = (
        "disabled"
        if not cfg.daemon.recovery_first_run_baseline_only
        else ("completed" if state.recovery_baseline_completed else "pending")
    )
    print(f"First-run baseline: {baseline_status}")
    print(f"Max actions per tick: {cfg.daemon.max_actions_per_tick}")
    print(f"Handoff recent window min: {cfg.handoff.handoff_recent_window_min}")
    print(f"Handoff alerts: {'enabled' if cfg.handoff.handoff_alert_enabled else 'disabled'}")
    print(
        "Tier detectors: "
        f"cross_team={str(cfg.handoff.handoff_cross_team_enabled).lower()} "
        f"ownerless={str(cfg.handoff.handoff_ownerless_enabled).lower()} "
        f"infra_block={str(cfg.handoff.handoff_infra_block_enabled).lower()} "
        f"stale_bundle={str(cfg.handoff.handoff_stale_bundle_enabled).lower()}"
    )
    print(f"Auto repair: {'enabled' if cfg.handoff.handoff_auto_repair_enabled else 'disabled'}")
    print(
        "Alert budget: "
        f"soft={cfg.handoff.handoff_alert_soft_budget_per_tick} "
        f"hard={cfg.handoff.handoff_alert_hard_budget_per_tick}"
    )

    try:
        result = subprocess.run(
            ["ps", "-ao", "pid,command"], capture_output=True, text=True, check=True
        )
        matches = sum(
            1
            for line in result.stdout.splitlines()
            if all(tok in line for tok in detection.PS_FILTER_TOKENS)
        )
    except Exception:
        matches = -1

    print(f"Configured companies: {len(cfg.companies)}")
    for company in cfg.companies:
        print(
            f"  - {company.name} ({company.id}) "
            f"recover_max_age_min={company.thresholds.recover_max_age_min}"
        )
    api_reachable, reconciliation_msg = _reconcile_for_status(cfg)
    if reconciliation_msg:
        print(reconciliation_msg)
    if not api_reachable and not args.allow_degraded:
        return 2
    print(f"paperclip-skills procs matching filter now: {matches}")
    print(f"Active cooldowns: {len(state.issue_cooldowns)}")
    print(f"Active escalations: {len(state.escalated_issues)}")
    perm_count = sum(1 for e in state.escalated_issues.values() if e.get("permanent"))
    print(f"Permanent escalations: {perm_count}")
    warnings: list[str] = []
    if not cfg.daemon.recovery_enabled and cfg.companies:
        warnings.append("recovery disabled while active companies are configured")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
    return 0


def _reconcile_for_status(cfg: Any) -> tuple[bool, str]:
    async def _run() -> list[dict[str, object]]:
        client = PaperclipClient(
            base_url=cfg.paperclip.base_url,
            api_key=cfg.paperclip.api_key or "",
        )
        try:
            return await client.list_companies()
        finally:
            await client.aclose()

    try:
        live = asyncio.run(_run())
    except Exception as exc:
        return False, f"company_inventory=unreachable reason={exc!r}"

    live_by_id = {str(company["id"]): company for company in live}
    configured_ids = {company.id for company in cfg.companies}
    missing = sorted(configured_ids - set(live_by_id))
    extra = sorted(set(live_by_id) - configured_ids)
    lines: list[str] = []
    for company_id in missing:
        lines.append(f"configured_but_missing={company_id}")
    for company_id in extra:
        name = live_by_id[company_id].get("name", "?")
        lines.append(f"live_but_unconfigured={company_id} name={name}")
    return True, "\n".join(lines)


def _cmd_tail(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    if not cfg.logging.path.exists():
        print(f"log file does not exist: {cfg.logging.path}", file=sys.stderr)
        return 1
    lines = cfg.logging.path.read_text().splitlines()[-args.n :]
    for line in lines:
        try:
            entry = json.loads(line)
            print(f"[{entry['ts']}] {entry['level']:<5} {entry['name']}: {entry['message']}")
        except Exception:
            print(line)
    return 0


def _cmd_escalate(args: argparse.Namespace) -> int:
    state_path = Path(_DEFAULT_STATE_PATH)
    state = State.load(state_path)
    for _ in range(4):
        state.record_escalation(args.issue, "manual")
        if not state.is_permanently_escalated(args.issue):
            state.clear_escalation(args.issue)
    state.save()
    print(f"issue {args.issue} marked as permanently escalated")
    return 0


def _cmd_unescalate(args: argparse.Namespace) -> int:
    state_path = Path(_DEFAULT_STATE_PATH)
    state = State.load(state_path)
    state.force_unescalate(args.issue)
    state.save()
    print(f"cleared escalation for {args.issue}")
    return 0


_DISPATCH = {
    "install": _cmd_install,
    "uninstall": _cmd_uninstall,
    "run": _cmd_run,
    "tick": _cmd_tick,
    "status": _cmd_status,
    "tail": _cmd_tail,
    "escalate": _cmd_escalate,
    "unescalate": _cmd_unescalate,
}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv

    starting_payload = {
        "event": "watchdog_starting",
        "pid": os.getpid(),
        "version": _watchdog_version(),
        "config_path": _extract_config_path(argv),
        "argv": _sanitize_argv(argv),
    }
    print(json.dumps(starting_payload), file=sys.stderr, flush=True)
    log.info("watchdog_starting", extra=starting_payload)

    parser = _build_parser()
    if len(argv) <= 1:
        parser.print_help(sys.stderr)
        return 2
    args = parser.parse_args(argv[1:])
    if not args.command:
        parser.print_help(sys.stderr)
        return 2
    handler = _DISPATCH[args.command]
    try:
        return handler(args)
    except (ConfigError, OSError) as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
