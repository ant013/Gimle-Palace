"""Semantic handoff-inconsistency detectors — alert-only, server-time anchored."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from gimle_watchdog.models import (
    Comment,
    CommentOnlyHandoffFinding,
    Finding,
    FindingType,
    ReviewOwnedByImplementerFinding,
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
        c for c in comments
        if c.author_agent_id == issue.assignee_agent_id
        and parse_mention_targets(c.body)
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
        except Exception:
            log.exception("handoff_pass_failed_for_issue issue_id=%s", issue.id)
    return findings
