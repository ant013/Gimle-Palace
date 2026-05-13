"""Shared watchdog test factories."""

from __future__ import annotations

from pathlib import Path

from gimle_watchdog.config import (
    CompanyConfig,
    Config,
    CooldownsConfig,
    DaemonConfig,
    EscalationConfig,
    HandoffConfig,
    LoggingConfig,
    PaperclipConfig,
    Thresholds,
)


def _make_config(
    *,
    recovery_enabled: bool = False,
    any_alert: bool = False,
    auto_repair: bool = False,
    companies: list[CompanyConfig] | None = None,
) -> Config:
    """Build a minimal Config with the requested posture bits."""

    handoff_kwargs: dict[str, bool] = {
        "handoff_alert_enabled": False,
        "handoff_cross_team_enabled": False,
        "handoff_ownerless_enabled": False,
        "handoff_infra_block_enabled": False,
        "handoff_stale_bundle_enabled": False,
        "handoff_auto_repair_enabled": False,
    }
    if any_alert:
        handoff_kwargs["handoff_alert_enabled"] = True
    if auto_repair:
        handoff_kwargs["handoff_auto_repair_enabled"] = True
    return Config(
        version=1,
        paperclip=PaperclipConfig(base_url="http://test", api_key="test"),
        daemon=DaemonConfig(poll_interval_seconds=60, recovery_enabled=recovery_enabled),
        companies=companies
        if companies is not None
        else [
            CompanyConfig(
                id="9d8f432c-0000-4000-8000-000000000001",
                name="Test",
                thresholds=Thresholds(
                    died_min=30,
                    hang_etime_min=45,
                    hang_cpu_max_s=None,
                    idle_cpu_ratio_max=0.01,
                    hang_stream_idle_max_s=300,
                ),
            )
        ],
        cooldowns=CooldownsConfig(
            per_issue_seconds=60,
            per_agent_cap=10,
            per_agent_window_seconds=3600,
        ),
        logging=LoggingConfig(
            path=Path("/tmp/test.log"),
            level="INFO",
            rotate_max_bytes=1_000_000,
            rotate_backup_count=3,
        ),
        escalation=EscalationConfig(post_comment_on_issue=False, comment_marker="[test]"),
        handoff=HandoffConfig(**handoff_kwargs),
    )
