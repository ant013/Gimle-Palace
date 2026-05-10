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
from gimle_watchdog.models import FindingType


log = logging.getLogger("watchdog.state")

STATE_VERSION = 2
PRUNE_WAKE_HISTORY_SECONDS = 3600  # keep 1h of wake history per agent
# After this many re-escalation cycles (clear+re-escalate), stop auto-clearing.
PERMANENT_ESCALATION_THRESHOLD = 3

_SNAPSHOT_KEYS: dict[FindingType, tuple[str, ...]] = {
    FindingType.COMMENT_ONLY_HANDOFF: (
        "assigneeAgentId",
        "status",
        "mention_comment_id",
        "mention_target_uuid",
    ),
    FindingType.WRONG_ASSIGNEE: ("assigneeAgentId", "status"),
    FindingType.REVIEW_OWNED_BY_IMPLEMENTER: ("assigneeAgentId", "status"),
    # GIM-244 — 3-tier detectors
    FindingType.CROSS_TEAM_HANDOFF: ("assigneeAgentId",),
    FindingType.OWNERLESS_COMPLETION: ("status",),
    FindingType.INFRA_BLOCK: ("error_kind",),
    FindingType.STALE_BUNDLE: ("deployed_sha",),
}


def _snapshot_matches(stored: dict[str, Any], current: dict[str, Any], ftype: FindingType) -> bool:
    keys = _SNAPSHOT_KEYS[ftype]
    return all(stored.get(k) == current.get(k) for k in keys)


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
    alerted_handoffs: dict[str, dict[str, Any]] = field(default_factory=dict)
    recovery_baseline_completed: bool = False

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
        if ver == 1:
            # Migrate v1 → v2: add tier fields to alerted_handoffs entries
            log.info("state_migration v1_to_v2")
            raw_handoffs = dict(raw.get("alerted_handoffs") or {})
            for entry in raw_handoffs.values():
                if "tier" not in entry:
                    entry["tier"] = 1
                    entry["tier_changed_at"] = entry.get("alerted_at", _iso(_now()))
                    entry.setdefault("repaired_at", None)
                    entry.setdefault("escalated_at", None)
                    entry.setdefault("actionable", True)
            raw["alerted_handoffs"] = raw_handoffs
            raw["version"] = STATE_VERSION
            ver = STATE_VERSION
        elif ver != STATE_VERSION:
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
            alerted_handoffs=dict(raw.get("alerted_handoffs") or {}),
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
            "alerted_handoffs": self.alerted_handoffs,
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

    def record_issue_cooldown(self, issue_id: str, recorded_at: _dt.datetime | None = None) -> None:
        now = recorded_at or _now()
        self.issue_cooldowns[issue_id] = {"last_wake_at": _iso(now)}

    def record_wake(self, issue_id: str, agent_id: str) -> None:
        now = _now()
        self.record_issue_cooldown(issue_id, now)
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

    # ------------------------------------------------------------------
    # Handoff alert cooldown (GIM-181)
    # ------------------------------------------------------------------

    def has_active_alert(
        self, issue_id: str, ftype: FindingType, current_snapshot: dict[str, Any]
    ) -> bool:
        """True iff entry exists AND all snapshot keys match stored values."""
        key = f"{issue_id}:{ftype.value}"
        entry = self.alerted_handoffs.get(key)
        if not entry:
            return False
        return _snapshot_matches(entry.get("snapshot", {}), current_snapshot, ftype)

    def cooldown_elapsed(
        self,
        issue_id: str,
        ftype: FindingType,
        now_server: _dt.datetime,
        cooldown_min: int,
    ) -> bool:
        """True iff entry exists AND alerted_at is older than cooldown_min minutes."""
        key = f"{issue_id}:{ftype.value}"
        entry = self.alerted_handoffs.get(key)
        if not entry:
            return False
        alerted_at = _parse_iso(entry["alerted_at"])
        elapsed_min = (now_server - alerted_at).total_seconds() / 60
        return elapsed_min >= cooldown_min

    def record_handoff_alert(
        self,
        issue_id: str,
        ftype: FindingType,
        snapshot: dict[str, Any],
        alerted_at: _dt.datetime,
        actionable: bool = True,
    ) -> None:
        key = f"{issue_id}:{ftype.value}"
        snap_keys = _SNAPSHOT_KEYS.get(ftype, ())
        self.alerted_handoffs[key] = {
            "alerted_at": _iso(alerted_at),
            "snapshot": {k: snapshot.get(k) for k in snap_keys},
            "tier": 1,
            "tier_changed_at": _iso(alerted_at),
            "repaired_at": None,
            "escalated_at": None,
            "actionable": actionable,
        }

    def get_handoff_tier(self, issue_id: str, ftype: FindingType) -> int:
        key = f"{issue_id}:{ftype.value}"
        entry = self.alerted_handoffs.get(key)
        return int(entry.get("tier", 1)) if entry else 0

    def promote_handoff_tier(
        self,
        issue_id: str,
        ftype: FindingType,
        new_tier: int,
        tier_changed_at: _dt.datetime,
    ) -> None:
        key = f"{issue_id}:{ftype.value}"
        entry = self.alerted_handoffs.get(key)
        if entry is None:
            return
        entry["tier"] = new_tier
        entry["tier_changed_at"] = _iso(tier_changed_at)

    def set_handoff_repaired(
        self, issue_id: str, ftype: FindingType, repaired_at: _dt.datetime
    ) -> None:
        key = f"{issue_id}:{ftype.value}"
        entry = self.alerted_handoffs.get(key)
        if entry is not None:
            entry["repaired_at"] = _iso(repaired_at)

    def set_handoff_escalated(
        self, issue_id: str, ftype: FindingType, escalated_at: _dt.datetime
    ) -> None:
        key = f"{issue_id}:{ftype.value}"
        entry = self.alerted_handoffs.get(key)
        if entry is not None:
            entry["escalated_at"] = _iso(escalated_at)

    def get_handoff_alerted_at(self, issue_id: str, ftype: FindingType) -> _dt.datetime | None:
        key = f"{issue_id}:{ftype.value}"
        entry = self.alerted_handoffs.get(key)
        if not entry:
            return None
        try:
            return _parse_iso(entry["alerted_at"])
        except Exception:
            return None

    def get_handoff_actionable(self, issue_id: str, ftype: FindingType) -> bool:
        key = f"{issue_id}:{ftype.value}"
        entry = self.alerted_handoffs.get(key)
        return bool(entry.get("actionable", True)) if entry else True

    def clear_handoff_alert(self, issue_id: str, ftype: FindingType) -> bool:
        """Remove the alert state entry for (issue_id, ftype).

        Returns True if an entry actually existed and was removed; False if
        no entry was present (no-op). Caller uses the return value to decide
        whether to emit the `handoff_alert_state_cleared` JSONL event.
        """
        key = f"{issue_id}:{ftype.value}"
        return self.alerted_handoffs.pop(key, None) is not None
