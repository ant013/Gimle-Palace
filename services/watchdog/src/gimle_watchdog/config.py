"""Config loader — YAML schema + validation + API key resolution."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
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
    hang_cpu_max_s: int


@dataclass(frozen=True)
class CompanyConfig:
    id: str
    name: str
    thresholds: Thresholds


@dataclass(frozen=True)
class DaemonConfig:
    poll_interval_seconds: int


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


@dataclass(frozen=True)
class Config:
    version: int
    paperclip: PaperclipConfig
    companies: list[CompanyConfig]
    daemon: DaemonConfig
    cooldowns: CooldownsConfig
    logging: LoggingConfig
    escalation: EscalationConfig


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
    return Thresholds(
        died_min=_require_positive_int(raw.get("died_min"), "thresholds.died_min"),
        hang_etime_min=_require_positive_int(raw.get("hang_etime_min"), "thresholds.hang_etime_min"),
        hang_cpu_max_s=_require_positive_int(raw.get("hang_cpu_max_s"), "thresholds.hang_cpu_max_s"),
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
    )

    cooldowns_raw = raw.get("cooldowns") or {}
    per_agent_cap_val = cooldowns_raw.get("per_agent_cap")
    if not isinstance(per_agent_cap_val, int) or isinstance(per_agent_cap_val, bool) or per_agent_cap_val < 1:
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

    return Config(
        version=version,
        paperclip=paperclip,
        companies=companies,
        daemon=daemon,
        cooldowns=cooldowns,
        logging=logging_cfg,
        escalation=escalation,
    )
