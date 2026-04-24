"""Persistent state — cooldowns, wake counts, escalation tracking."""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gimle_watchdog.config import CooldownsConfig


log = logging.getLogger("watchdog.state")

STATE_VERSION = 1
PRUNE_WAKE_HISTORY_SECONDS = 3600  # keep 1h of wake history per agent
# After this many re-escalation cycles (clear+re-escalate), stop auto-clearing.
PERMANENT_ESCALATION_THRESHOLD = 3


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _iso(dt: _dt.datetime) -> str:
    return dt.astimezone(_dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(s: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


@dataclass
class State:
    path: Path
    version: int = STATE_VERSION
    issue_cooldowns: dict[str, dict[str, Any]] = field(default_factory=dict)
    agent_wakes: dict[str, list[_dt.datetime]] = field(default_factory=dict)
    escalated_issues: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "State":
        if not path.exists():
            return cls(path=path)
        raw_text = path.read_text()
        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError as e:
            log.warning("state_corrupt starting_empty error=%s", e)
            return cls(path=path)

        ver = raw.get("version")
        if ver != STATE_VERSION:
            ts = _now().strftime("%Y%m%dT%H%M%SZ")
            backup = path.with_suffix(path.suffix + f".bak-{ts}")
            path.rename(backup)
            log.warning("state_version_unknown version=%r backup=%s", ver, backup.name)
            return cls(path=path)

        agent_wakes: dict[str, list[_dt.datetime]] = {}
        for agent_id, times in (raw.get("agent_wakes") or {}).items():
            parsed: list[_dt.datetime] = []
            for t in times:
                try:
                    parsed.append(_parse_iso(t))
                except Exception:
                    log.warning("state_bad_timestamp agent=%s value=%r", agent_id, t)
            agent_wakes[agent_id] = parsed

        return cls(
            path=path,
            version=ver,
            issue_cooldowns=dict(raw.get("issue_cooldowns") or {}),
            agent_wakes=agent_wakes,
            escalated_issues=dict(raw.get("escalated_issues") or {}),
        )

    def save(self) -> None:
        """Atomic write via tempfile + os.replace()."""
        payload = {
            "version": self.version,
            "last_updated": _iso(_now()),
            "issue_cooldowns": self.issue_cooldowns,
            "agent_wakes": {
                aid: [_iso(t) for t in times] for aid, times in self.agent_wakes.items()
            },
            "escalated_issues": self.escalated_issues,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_name = tempfile.mkstemp(
            prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(payload, f, indent=2, default=str)
            os.replace(tmp_name, self.path)
            os.chmod(self.path, 0o600)
        except Exception:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

    def record_wake(self, issue_id: str, agent_id: str) -> None:
        now = _now()
        self.issue_cooldowns[issue_id] = {"last_wake_at": _iso(now)}
        wakes = self.agent_wakes.setdefault(agent_id, [])
        wakes.append(now)
        cutoff = now - _dt.timedelta(seconds=PRUNE_WAKE_HISTORY_SECONDS)
        self.agent_wakes[agent_id] = [t for t in wakes if t > cutoff]

    def is_issue_in_cooldown(self, issue_id: str, cooldown_seconds: int) -> bool:
        entry = self.issue_cooldowns.get(issue_id)
        if not entry:
            return False
        last = _parse_iso(entry["last_wake_at"])
        return (_now() - last).total_seconds() < cooldown_seconds

    def agent_cap_exceeded(self, agent_id: str, cooldowns: CooldownsConfig) -> bool:
        now = _now()
        window_start = now - _dt.timedelta(seconds=cooldowns.per_agent_window_seconds)
        wakes = self.agent_wakes.get(agent_id, [])
        recent = [t for t in wakes if t > window_start]
        return len(recent) >= cooldowns.per_agent_cap

    def record_escalation(self, issue_id: str, reason: str) -> None:
        existing = self.escalated_issues.get(issue_id) or {}
        count = int(existing.get("escalation_count", 0)) + 1
        self.escalated_issues[issue_id] = {
            "escalated_at": _iso(_now()),
            "reason": reason,
            "escalation_count": count,
            "permanent": count >= PERMANENT_ESCALATION_THRESHOLD + 1,
            "cleared": False,
        }

    def clear_escalation(self, issue_id: str) -> None:
        """Clear active-flag but preserve escalation_count for recurrence tracking."""
        entry = self.escalated_issues.get(issue_id)
        if not entry:
            return
        if entry.get("permanent"):
            return  # permanent escalations survive auto-clear
        # Preserve count so next re-escalation accumulates correctly.
        self.escalated_issues[issue_id] = {
            "escalation_count": entry.get("escalation_count", 0),
            "permanent": False,
            "cleared": True,
        }

    def force_unescalate(self, issue_id: str) -> None:
        """Explicit operator command — wipes entry fully, including permanent flag."""
        self.escalated_issues.pop(issue_id, None)

    def is_escalated(self, issue_id: str) -> bool:
        entry = self.escalated_issues.get(issue_id)
        if not entry:
            return False
        return not entry.get("cleared", False)

    def is_permanently_escalated(self, issue_id: str) -> bool:
        entry = self.escalated_issues.get(issue_id) or {}
        return bool(entry.get("permanent"))

    def escalation_count(self, issue_id: str) -> int:
        entry = self.escalated_issues.get(issue_id) or {}
        return int(entry.get("escalation_count", 0))
