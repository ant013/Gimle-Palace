"""Semantic handoff-inconsistency detectors — alert-only, server-time anchored."""

from __future__ import annotations

import importlib.util
import logging
import re
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gimle_watchdog.models import (
    Comment,
    CommentOnlyHandoffFinding,
    CrossTeamHandoffFinding,
    Finding,
    FindingType,
    InfraBlockFinding,
    OwnerlessCompletionFinding,
    ReviewOwnedByImplementerFinding,
    StaleBundleFinding,
    WrongAssigneeFinding,
)
from gimle_watchdog.paperclip import Issue
from gimle_watchdog.role_taxonomy import classify


log = logging.getLogger("watchdog.detection_semantic")

_UUID_RE = re.compile(
    r"agent://([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)

_ELIGIBLE_STATUSES = frozenset({"todo", "in_progress", "in_review"})


@dataclass(frozen=True)
class HandoffDetectionConfig:
    handoff_alert_enabled: bool = False
    handoff_comment_lookback_min: int = 5
    handoff_wrong_assignee_min: int = 3
    handoff_review_owner_min: int = 5
    handoff_comments_per_issue: int = 5
    handoff_max_issues_per_tick: int = 30
    handoff_alert_cooldown_min: int = 30
    # GIM-244 — 3-tier detector config
    handoff_cross_team_enabled: bool = False
    handoff_ownerless_enabled: bool = False
    handoff_infra_block_enabled: bool = False
    handoff_stale_bundle_enabled: bool = False
    handoff_auto_repair_enabled: bool = False
    handoff_escalation_delay_min: int = 90
    handoff_repair_delay_min: int = 60
    handoff_stale_bundle_threshold_hours: int = 24
    handoff_ownerless_comment_limit: int = 50


# QA agent UUIDs expected to author Phase 4.1 evidence
_CLAUDE_QA_UUID = "58b68640-1e83-4d5d-978b-51a5ca9080e0"
_CODEX_QA_UUID = "99d5f8f8-822f-4ddb-baaa-0bdaec6f9399"
_QA_UUIDS: frozenset[str] = frozenset({_CLAUDE_QA_UUID, _CODEX_QA_UUID})

_PHASE_41_RE = re.compile(r"phase\s+4[\.\s]*1", re.IGNORECASE)
_QA_PASS_RE = re.compile(r"qa\s+pass", re.IGNORECASE)

# Infra error patterns that indicate non-actionable blocks
_INFRA_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b1010\b"), "cloudflare_1010"),
    (re.compile(r"\b429\b"), "rate_limit_429"),
    (re.compile(r"\b(502|503)\b"), "service_unavailable"),
    (re.compile(r"cloudflare", re.IGNORECASE), "cloudflare_generic"),
]


def parse_mention_targets(comment_body: str) -> list[str]:
    """Extract agent UUIDs from canonical paperclip @-mention links."""
    return [m.group(1).lower() for m in _UUID_RE.finditer(comment_body)]


def _detect_comment_only_handoff(
    issue: Issue,
    comments: list[Comment],
    lookback_min: int,
) -> CommentOnlyHandoffFinding | None:
    if issue.status not in _ELIGIBLE_STATUSES:
        return None
    if issue.assignee_agent_id is None:
        return None

    qualifying = [
        c
        for c in comments
        if c.author_agent_id == issue.assignee_agent_id and parse_mention_targets(c.body)
    ]
    if not qualifying:
        return None

    c_star = max(qualifying, key=lambda c: c.created_at)
    targets = parse_mention_targets(c_star.body)
    target_uuid = targets[0]

    if target_uuid == issue.assignee_agent_id:
        return None

    age_seconds = (issue.updated_at - c_star.created_at).total_seconds()
    if age_seconds / 60 < lookback_min:
        return None

    return CommentOnlyHandoffFinding(
        type=FindingType.COMMENT_ONLY_HANDOFF,
        issue_id=issue.id,
        issue_number=issue.issue_number,
        current_assignee_id=issue.assignee_agent_id,
        mentioned_agent_id=target_uuid,
        mention_comment_id=c_star.id,
        mention_author_agent_id=issue.assignee_agent_id,
        mention_age_seconds=int(age_seconds),
        issue_status=issue.status,
    )


def _detect_wrong_assignee(
    issue: Issue,
    hired_ids: frozenset[str],
    now_server: datetime,
    min_age_min: int,
) -> WrongAssigneeFinding | None:
    if issue.status not in _ELIGIBLE_STATUSES:
        return None
    if issue.assignee_agent_id is None:
        return None
    if issue.assignee_agent_id in hired_ids:
        return None

    age_seconds = (now_server - issue.updated_at).total_seconds()
    if age_seconds / 60 < min_age_min:
        return None

    return WrongAssigneeFinding(
        type=FindingType.WRONG_ASSIGNEE,
        issue_id=issue.id,
        issue_number=issue.issue_number,
        bogus_assignee_id=issue.assignee_agent_id,
        issue_status=issue.status,
        age_seconds=int(age_seconds),
    )


def _detect_review_owned_by_implementer(
    issue: Issue,
    hired_ids: frozenset[str],
    name_by_id: dict[str, str],
    now_server: datetime,
    min_age_min: int,
) -> ReviewOwnedByImplementerFinding | None:
    if issue.status != "in_review":
        return None
    if issue.assignee_agent_id is None:
        return None
    if issue.assignee_agent_id not in hired_ids:
        return None

    name = name_by_id.get(issue.assignee_agent_id)
    if name is None:
        return None
    if classify(name) != "implementer":
        return None

    age_seconds = (now_server - issue.updated_at).total_seconds()
    if age_seconds / 60 < min_age_min:
        return None

    return ReviewOwnedByImplementerFinding(
        type=FindingType.REVIEW_OWNED_BY_IMPLEMENTER,
        issue_id=issue.id,
        issue_number=issue.issue_number,
        implementer_assignee_id=issue.assignee_agent_id,
        implementer_role_name=name,
        implementer_role_class="implementer",
        age_seconds=int(age_seconds),
    )


def _detect_cross_team_handoff(
    issue: Issue,
    comments: list[Comment],
    team_uuids: dict[str, set[str]],
    company_team: str = "claude",
) -> CrossTeamHandoffFinding | None:
    """Fire when assigneeAgentId belongs to a different team than company_team.

    Suppressed if any recent comment contains an 'infra-block' marker (signals
    that a human operator intentionally crossed team boundaries).
    """
    if issue.assignee_agent_id is None:
        return None
    assignee = issue.assignee_agent_id.lower()
    for team, uuids in team_uuids.items():
        if assignee in {u.lower() for u in uuids}:
            if team == company_team:
                return None  # same team — no problem
            # Cross-team — check for infra-block marker
            if any("infra-block" in c.body for c in comments):
                return None
            return CrossTeamHandoffFinding(
                type=FindingType.CROSS_TEAM_HANDOFF,
                issue_id=issue.id,
                issue_number=issue.issue_number,
                assignee_id=issue.assignee_agent_id,
                assignee_team=team,
                company_team=company_team,
                issue_status=issue.status,
            )
    return None  # UUID unknown to both teams


def _detect_ownerless_completion(
    issue: Issue,
    comments: list[Comment],
) -> OwnerlessCompletionFinding | None:
    """Fire when issue is done but no Phase 4.1 QA PASS comment from a QA agent exists."""
    if issue.status != "done":
        return None
    for c in comments:
        if c.author_agent_id in _QA_UUIDS:
            if _PHASE_41_RE.search(c.body) and _QA_PASS_RE.search(c.body):
                return None  # valid QA evidence found
    return OwnerlessCompletionFinding(
        type=FindingType.OWNERLESS_COMPLETION,
        issue_id=issue.id,
        issue_number=issue.issue_number,
    )


def _detect_infra_block(
    issue: Issue,
    comments: list[Comment],
    lookback_min: int = 60,
    now: datetime | None = None,
) -> InfraBlockFinding | None:
    """Fire when a recent comment contains known infrastructure error patterns."""
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=lookback_min)
    for c in comments:
        if c.created_at < cutoff:
            continue
        for pattern, kind in _INFRA_PATTERNS:
            if pattern.search(c.body):
                return InfraBlockFinding(
                    type=FindingType.INFRA_BLOCK,
                    issue_id=issue.id,
                    issue_number=issue.issue_number,
                    error_kind=kind,
                    actionable=False,
                )
    return None


def detect_stale_bundle(
    deploy_log_path: Path,
    repo_root: Path,
    threshold_hours: int,
    now: datetime,
) -> StaleBundleFinding | None:
    """Fire when imac-agents-deploy.log shows a SHA that differs from origin/main
    and the log entry is older than threshold_hours.
    """
    if not deploy_log_path.exists():
        return None
    last_sha: str | None = None
    last_ts: str | None = None
    for line in deploy_log_path.read_text().splitlines():
        parts = line.strip().split("\t")
        if len(parts) < 2:
            continue
        ts_str = parts[0]
        for part in parts[1:]:
            if part.startswith("main_sha="):
                last_sha = part[len("main_sha="):]
                last_ts = ts_str
    if last_sha is None or not last_ts:
        return None
    try:
        deployed_at = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    stale_seconds = (now - deployed_at).total_seconds()
    if stale_seconds < threshold_hours * 3600:
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "origin/main"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=10,
        )
        if result.returncode != 0:
            return None
        current_sha = result.stdout.strip()
    except Exception:
        return None
    if not current_sha or current_sha == last_sha:
        return None
    return StaleBundleFinding(
        type=FindingType.STALE_BUNDLE,
        deployed_sha=last_sha,
        current_sha=current_sha,
        stale_hours=stale_seconds / 3600,
    )


def load_team_uuids_from_repo(repo_root: Path) -> dict[str, set[str]]:
    """Load team UUIDs by delegating to validate_instructions.load_team_uuids.

    Uses importlib to load the script by absolute path — avoids adding
    paperclips/ to the watchdog package's sys.path.  Falls back to empty
    sets if the script is missing.
    """
    script = repo_root / "paperclips" / "scripts" / "validate_instructions.py"
    if not script.is_file():
        log.warning("team_uuids_script_missing path=%s", script)
        return {"claude": set(), "codex": set()}
    spec = importlib.util.spec_from_file_location("_validate_instructions", script)
    if spec is None or spec.loader is None:
        return {"claude": set(), "codex": set()}
    import sys as _sys
    mod = importlib.util.module_from_spec(spec)
    _sys.modules["_validate_instructions"] = mod  # required for dataclass forward-ref resolution
    try:
        loader = spec.loader
        loader.exec_module(mod)
        result: dict[str, set[str]] = mod.load_team_uuids(repo_root)
        return result
    except Exception as exc:
        log.warning("team_uuids_load_failed error=%s", exc)
        return {"claude": set(), "codex": set()}


async def _evaluate_one_issue(
    issue: Issue,
    fetch_comments: Callable[[str], Awaitable[list[Comment]]],
    hired_ids: frozenset[str],
    name_by_id: dict[str, str],
    cfg: HandoffDetectionConfig,
    now_server: datetime,
) -> Finding | None:
    wrong = _detect_wrong_assignee(issue, hired_ids, now_server, cfg.handoff_wrong_assignee_min)
    if wrong is not None:
        return wrong

    comments = await fetch_comments(issue.id)
    comment_only = _detect_comment_only_handoff(issue, comments, cfg.handoff_comment_lookback_min)
    if comment_only is not None:
        return comment_only

    return _detect_review_owned_by_implementer(
        issue, hired_ids, name_by_id, now_server, cfg.handoff_review_owner_min
    )


async def scan_handoff_inconsistencies(
    issues: list[Issue],
    fetch_comments: Callable[[str], Awaitable[list[Comment]]],
    hired_ids: frozenset[str],
    name_by_id: dict[str, str],
    cfg: HandoffDetectionConfig,
    now_server: datetime,
) -> list[Finding]:
    findings: list[Finding] = []
    for issue in issues[: cfg.handoff_max_issues_per_tick]:
        try:
            finding = await _evaluate_one_issue(
                issue, fetch_comments, hired_ids, name_by_id, cfg, now_server
            )
            if finding is not None:
                findings.append(finding)
        except Exception as exc:
            log.exception(
                "handoff_pass_failed_for_issue issue_id=%s",
                issue.id,
                extra={
                    "event": "handoff_pass_failed_for_issue",
                    "issue_id": issue.id,
                    "error": repr(exc),
                },
            )
    return findings
