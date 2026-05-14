"""Config loader — YAML schema + validation + API key resolution."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import yaml


log = logging.getLogger("watchdog.config")

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_API_KEY_SOURCE_RE = re.compile(r"^(env|file|inline):(.+)$")
SUPPORTED_VERSION = 1


class ConfigError(Exception):
    """Raised when the watchdog config is malformed or has unsupported values."""


@dataclass(frozen=True)
class PaperclipConfig:
    base_url: str
    api_key: str | None  # resolved from api_key_source


@dataclass(frozen=True)
class Thresholds:
    died_min: int
    hang_etime_min: int
    hang_cpu_max_s: int | None  # deprecated; None when new fields are used
    idle_cpu_ratio_max: float  # CPU time / elapsed time ratio below which proc is idle
    hang_stream_idle_max_s: int  # seconds since last stream-json event before proc is stalled
    # Skip recovery for issues whose updatedAt is older than this many minutes — avoids
    # waking long-abandoned in_review issues from the archive (GIM-NN, 2026-05-06: after
    # broader scope landed in 6b2419f, watchdog woke 3 weeks-old GIM-44 / 20 / 28 etc.).
    recover_max_age_min: int = field(default=180, kw_only=True)


@dataclass(frozen=True)
class CompanyConfig:
    id: str
    name: str
    thresholds: Thresholds


@dataclass(frozen=True)
class DaemonConfig:
    poll_interval_seconds: int
    recovery_enabled: bool = False
    recovery_first_run_baseline_only: bool = True
    recovery_dry_run: bool = False  # persistent scan+log mode; never acts; ignores baseline_completed
    max_actions_per_tick: int = 1


@dataclass(frozen=True)
class CooldownsConfig:
    per_issue_seconds: int
    per_agent_cap: int
    per_agent_window_seconds: int


@dataclass(frozen=True)
class LoggingConfig:
    path: Path
    level: str
    rotate_max_bytes: int
    rotate_backup_count: int


@dataclass(frozen=True)
class EscalationConfig:
    post_comment_on_issue: bool
    comment_marker: str


_HANDOFF_KNOWN_KEYS = frozenset(
    {
        "handoff_alert_enabled",
        "handoff_comment_lookback_min",
        "handoff_wrong_assignee_min",
        "handoff_review_owner_min",
        "handoff_comments_per_issue",
        "handoff_max_issues_per_tick",
        "handoff_alert_cooldown_min",
        "handoff_recent_window_min",
        "handoff_alert_soft_budget_per_tick",
        "handoff_alert_hard_budget_per_tick",
        # GIM-244 — 3-tier detector keys
        "handoff_cross_team_enabled",
        "handoff_ownerless_enabled",
        "handoff_infra_block_enabled",
        "handoff_stale_bundle_enabled",
        "handoff_auto_repair_enabled",
        "handoff_escalation_delay_min",
        "handoff_repair_delay_min",
        "handoff_stale_bundle_threshold_hours",
        "handoff_ownerless_comment_limit",
    }
)


class EffectiveMode(str, Enum):
    """Operational mode summarising recovery + alert + auto-repair posture."""

    OBSERVE_ONLY = "observe-only"
    ALERT_ONLY = "alert-only"
    RECOVERY_ONLY = "recovery-only"
    FULL_WATCHDOG = "full-watchdog"
    UNSAFE_AUTO_REPAIR = "unsafe-auto-repair"


ALERT_FLAG_NAMES: frozenset[str] = frozenset(
    {
        "handoff_alert_enabled",
        "handoff_cross_team_enabled",
        "handoff_ownerless_enabled",
        "handoff_infra_block_enabled",
        "handoff_stale_bundle_enabled",
    }
)

AUTO_REPAIR_FLAG_NAME: str = "handoff_auto_repair_enabled"

# Every code path that calls PaperclipClient.post_issue_comment MUST be
# enumerated here as "<module_stem>:<enclosing_function>". The AST-based
# registry test fails closed when a new caller lands without updating this set.
POST_COMMENT_PATHS: frozenset[str] = frozenset(
    {
        "actions:post_handoff_alert",
        "actions:post_stale_bundle_alert",
        "actions:post_tier_escalation",
        "actions:repair_cross_team_handoff",
        "actions:repair_ownerless_completion",
        "daemon:_post_tier_one_alert",
        "daemon:_run_recovery_pass",
    }
)


@dataclass(frozen=True)
class HandoffConfig:
    handoff_alert_enabled: bool = False
    handoff_comment_lookback_min: int = 5
    handoff_wrong_assignee_min: int = 3
    handoff_review_owner_min: int = 5
    handoff_comments_per_issue: int = 5
    handoff_max_issues_per_tick: int = 30
    handoff_alert_cooldown_min: int = 30
    handoff_recent_window_min: int = 180
    handoff_alert_soft_budget_per_tick: int = 5
    handoff_alert_hard_budget_per_tick: int = 20
    # GIM-244 — 3-tier detector fields (all disabled by default)
    handoff_cross_team_enabled: bool = False
    handoff_ownerless_enabled: bool = False
    handoff_infra_block_enabled: bool = False
    handoff_stale_bundle_enabled: bool = False
    handoff_auto_repair_enabled: bool = False
    handoff_escalation_delay_min: int = 90
    handoff_repair_delay_min: int = 60
    handoff_stale_bundle_threshold_hours: int = 24
    handoff_ownerless_comment_limit: int = 50


@dataclass(frozen=True)
class Config:
    version: int
    paperclip: PaperclipConfig
    companies: list[CompanyConfig]
    daemon: DaemonConfig
    cooldowns: CooldownsConfig
    logging: LoggingConfig
    escalation: EscalationConfig
    handoff: HandoffConfig = field(default_factory=HandoffConfig)


def describe_effective_mode(cfg: Config) -> EffectiveMode:
    """Classify the watchdog operational posture.

    Total function over (recovery_enabled, any_alert_path_on, auto_repair_enabled).
    Raises ConfigError if a handoff_*_enabled field exists outside the registered
    alert and auto-repair flag sets.
    """

    handoff = cfg.handoff
    known_flags = ALERT_FLAG_NAMES | {AUTO_REPAIR_FLAG_NAME}
    for attr in vars(handoff):
        if attr.startswith("handoff_") and attr.endswith("_enabled") and attr not in known_flags:
            raise ConfigError(
                f"unknown handoff_*_enabled flag {attr!r}; add to "
                "ALERT_FLAG_NAMES or AUTO_REPAIR_FLAG_NAME"
            )

    if getattr(handoff, AUTO_REPAIR_FLAG_NAME):
        return EffectiveMode.UNSAFE_AUTO_REPAIR

    any_alert_path_on = any(getattr(handoff, flag) for flag in ALERT_FLAG_NAMES)
    recovery_on = cfg.daemon.recovery_enabled

    if not recovery_on and not any_alert_path_on:
        return EffectiveMode.OBSERVE_ONLY
    if not recovery_on and any_alert_path_on:
        return EffectiveMode.ALERT_ONLY
    if recovery_on and not any_alert_path_on:
        return EffectiveMode.RECOVERY_ONLY
    return EffectiveMode.FULL_WATCHDOG


def _resolve_api_key(source: str) -> str | None:
    match = _API_KEY_SOURCE_RE.match(source)
    if not match:
        raise ConfigError(
            f"paperclip.api_key_source must match 'env:VAR' | 'file:PATH' | 'inline:VALUE'; got {source!r}"
        )
    kind, value = match.group(1), match.group(2)
    if kind == "env":
        v = os.environ.get(value)
        if v is None:
            log.warning("api_key_env_missing var=%s (daemon will fail on API call)", value)
        return v
    if kind == "file":
        p = Path(value).expanduser()
        if not p.is_file():
            raise ConfigError(f"paperclip.api_key_source file not found: {p}")
        return p.read_text().strip()
    # kind == "inline"
    return value


def _require_positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{name} must be a positive integer, got {value!r}")
    return value


def _parse_thresholds(raw: dict[str, object]) -> Thresholds:
    has_new = "idle_cpu_ratio_max" in raw
    has_old = "hang_cpu_max_s" in raw

    if has_old and not has_new:
        raise ConfigError(
            "thresholds.hang_cpu_max_s is no longer supported. "
            "Add 'idle_cpu_ratio_max: 0.005' and 'hang_stream_idle_max_s: 300' to migrate."
        )

    hang_cpu_max_s: int | None = None
    if has_old and has_new:
        log.warning(
            "thresholds.hang_cpu_max_s is deprecated and will be ignored; "
            "using idle_cpu_ratio_max instead"
        )
        hang_cpu_max_s = None

    ratio_raw = raw.get("idle_cpu_ratio_max")
    if not isinstance(ratio_raw, (int, float)) or isinstance(ratio_raw, bool):
        raise ConfigError(f"thresholds.idle_cpu_ratio_max must be a float, got {ratio_raw!r}")
    ratio = float(ratio_raw)
    if not (0.0 < ratio < 1.0):
        raise ConfigError(f"thresholds.idle_cpu_ratio_max must be in (0.0, 1.0), got {ratio!r}")

    # GIM-NN: optional with safe default (3 hours). Older yaml configs work unchanged.
    recover_max_age_min_raw = raw.get("recover_max_age_min", 180)
    recover_max_age_min = _require_positive_int(
        recover_max_age_min_raw, "thresholds.recover_max_age_min"
    )

    return Thresholds(
        died_min=_require_positive_int(raw.get("died_min"), "thresholds.died_min"),
        hang_etime_min=_require_positive_int(
            raw.get("hang_etime_min"), "thresholds.hang_etime_min"
        ),
        hang_cpu_max_s=hang_cpu_max_s,
        idle_cpu_ratio_max=ratio,
        hang_stream_idle_max_s=_require_positive_int(
            raw.get("hang_stream_idle_max_s"), "thresholds.hang_stream_idle_max_s"
        ),
        recover_max_age_min=recover_max_age_min,
    )


def _parse_company(raw: dict[str, object], index: int) -> CompanyConfig:
    cid = raw.get("id", "")
    if not isinstance(cid, str) or not _UUID_RE.match(cid):
        raise ConfigError(f"companies[{index}].id must be a uuid, got {cid!r}")
    name = raw.get("name", "")
    if not isinstance(name, str) or not name:
        raise ConfigError(f"companies[{index}].name must be a non-empty string")
    thresholds_raw = raw.get("thresholds")
    if not isinstance(thresholds_raw, dict):
        raise ConfigError(f"companies[{index}].thresholds must be a mapping")
    return CompanyConfig(id=cid, name=name, thresholds=_parse_thresholds(thresholds_raw))


def load_config(path: Path) -> Config:
    """Parse + validate a watchdog config YAML. Raises ConfigError on problems."""
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ConfigError(f"Config root must be a mapping, got {type(raw).__name__}")

    version = raw.get("version")
    if version != SUPPORTED_VERSION:
        raise ConfigError(f"Unsupported config version {version!r}; expected {SUPPORTED_VERSION}")

    paperclip_raw = raw.get("paperclip") or {}
    if not isinstance(paperclip_raw, dict):
        raise ConfigError("paperclip section must be a mapping")
    base_url = paperclip_raw.get("base_url")
    if not isinstance(base_url, str) or not base_url:
        raise ConfigError("paperclip.base_url required non-empty string")
    api_key_source = paperclip_raw.get("api_key_source", "")
    api_key = _resolve_api_key(str(api_key_source))
    paperclip = PaperclipConfig(base_url=base_url, api_key=api_key)

    companies_raw = raw.get("companies")
    if not isinstance(companies_raw, list) or not companies_raw:
        raise ConfigError("companies must be a non-empty list")
    companies = [_parse_company(c, i) for i, c in enumerate(companies_raw)]

    daemon_raw = raw.get("daemon") or {}
    daemon = DaemonConfig(
        poll_interval_seconds=_require_positive_int(
            daemon_raw.get("poll_interval_seconds"), "daemon.poll_interval_seconds"
        ),
        recovery_enabled=bool(daemon_raw.get("recovery_enabled", False)),
        recovery_first_run_baseline_only=bool(
            daemon_raw.get("recovery_first_run_baseline_only", True)
        ),
        recovery_dry_run=bool(daemon_raw.get("recovery_dry_run", False)),
        max_actions_per_tick=_require_positive_int(
            daemon_raw.get("max_actions_per_tick", 1),
            "daemon.max_actions_per_tick",
        ),
    )

    cooldowns_raw = raw.get("cooldowns") or {}
    per_agent_cap_val = cooldowns_raw.get("per_agent_cap")
    if (
        not isinstance(per_agent_cap_val, int)
        or isinstance(per_agent_cap_val, bool)
        or per_agent_cap_val < 1
    ):
        raise ConfigError(f"cooldowns.per_agent_cap must be >= 1, got {per_agent_cap_val!r}")
    cooldowns = CooldownsConfig(
        per_issue_seconds=_require_positive_int(
            cooldowns_raw.get("per_issue_seconds"), "cooldowns.per_issue_seconds"
        ),
        per_agent_cap=per_agent_cap_val,
        per_agent_window_seconds=_require_positive_int(
            cooldowns_raw.get("per_agent_window_seconds"), "cooldowns.per_agent_window_seconds"
        ),
    )

    logging_raw = raw.get("logging") or {}
    logging_cfg = LoggingConfig(
        path=Path(str(logging_raw.get("path", "~/.paperclip/watchdog.log"))).expanduser(),
        level=str(logging_raw.get("level", "INFO")),
        rotate_max_bytes=_require_positive_int(
            logging_raw.get("rotate_max_bytes"), "logging.rotate_max_bytes"
        ),
        rotate_backup_count=_require_positive_int(
            logging_raw.get("rotate_backup_count"), "logging.rotate_backup_count"
        ),
    )

    escalation_raw = raw.get("escalation") or {}
    escalation = EscalationConfig(
        post_comment_on_issue=bool(escalation_raw.get("post_comment_on_issue", False)),
        comment_marker=str(escalation_raw.get("comment_marker", "<!-- watchdog-escalation -->")),
    )

    handoff_raw = raw.get("handoff") or {}
    if not isinstance(handoff_raw, dict):
        raise ConfigError("handoff section must be a mapping")
    unknown = set(handoff_raw.keys()) - _HANDOFF_KNOWN_KEYS
    if unknown:
        raise ConfigError(f"handoff section has unknown keys: {sorted(unknown)}")
    handoff = HandoffConfig(
        handoff_alert_enabled=bool(handoff_raw.get("handoff_alert_enabled", False)),
        handoff_comment_lookback_min=_require_positive_int(
            handoff_raw.get("handoff_comment_lookback_min", 5),
            "handoff.handoff_comment_lookback_min",
        ),
        handoff_wrong_assignee_min=_require_positive_int(
            handoff_raw.get("handoff_wrong_assignee_min", 3),
            "handoff.handoff_wrong_assignee_min",
        ),
        handoff_review_owner_min=_require_positive_int(
            handoff_raw.get("handoff_review_owner_min", 5),
            "handoff.handoff_review_owner_min",
        ),
        handoff_comments_per_issue=_require_positive_int(
            handoff_raw.get("handoff_comments_per_issue", 5),
            "handoff.handoff_comments_per_issue",
        ),
        handoff_max_issues_per_tick=_require_positive_int(
            handoff_raw.get("handoff_max_issues_per_tick", 30),
            "handoff.handoff_max_issues_per_tick",
        ),
        handoff_alert_cooldown_min=_require_positive_int(
            handoff_raw.get("handoff_alert_cooldown_min", 30),
            "handoff.handoff_alert_cooldown_min",
        ),
        handoff_recent_window_min=_require_positive_int(
            handoff_raw.get("handoff_recent_window_min", 180),
            "handoff.handoff_recent_window_min",
        ),
        handoff_alert_soft_budget_per_tick=_require_positive_int(
            handoff_raw.get("handoff_alert_soft_budget_per_tick", 5),
            "handoff.handoff_alert_soft_budget_per_tick",
        ),
        handoff_alert_hard_budget_per_tick=_require_positive_int(
            handoff_raw.get("handoff_alert_hard_budget_per_tick", 20),
            "handoff.handoff_alert_hard_budget_per_tick",
        ),
        handoff_cross_team_enabled=bool(handoff_raw.get("handoff_cross_team_enabled", False)),
        handoff_ownerless_enabled=bool(handoff_raw.get("handoff_ownerless_enabled", False)),
        handoff_infra_block_enabled=bool(handoff_raw.get("handoff_infra_block_enabled", False)),
        handoff_stale_bundle_enabled=bool(handoff_raw.get("handoff_stale_bundle_enabled", False)),
        handoff_auto_repair_enabled=bool(handoff_raw.get("handoff_auto_repair_enabled", False)),
        handoff_escalation_delay_min=_require_positive_int(
            handoff_raw.get("handoff_escalation_delay_min", 90),
            "handoff.handoff_escalation_delay_min",
        ),
        handoff_repair_delay_min=_require_positive_int(
            handoff_raw.get("handoff_repair_delay_min", 60),
            "handoff.handoff_repair_delay_min",
        ),
        handoff_stale_bundle_threshold_hours=_require_positive_int(
            handoff_raw.get("handoff_stale_bundle_threshold_hours", 24),
            "handoff.handoff_stale_bundle_threshold_hours",
        ),
        handoff_ownerless_comment_limit=_require_positive_int(
            handoff_raw.get("handoff_ownerless_comment_limit", 50),
            "handoff.handoff_ownerless_comment_limit",
        ),
    )

    return Config(
        version=version,
        paperclip=paperclip,
        companies=companies,
        daemon=daemon,
        cooldowns=cooldowns,
        logging=logging_cfg,
        escalation=escalation,
        handoff=handoff,
    )
