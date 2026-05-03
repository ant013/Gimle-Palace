"""Tests for watchdog.models — FindingType, finding dataclasses, AlertResult, Comment, Agent."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timezone

import pytest

from gimle_watchdog.models import (
    AlertResult,
    Comment,
    CommentOnlyHandoffFinding,
    Finding,
    FindingType,
    ReviewOwnedByImplementerFinding,
    WrongAssigneeFinding,
)


_UTC = timezone.utc
_NOW = datetime(2026, 5, 3, 12, 0, 0, tzinfo=_UTC)


def test_finding_type_values_are_stable():
    assert FindingType.COMMENT_ONLY_HANDOFF == "comment_only_handoff"
    assert FindingType.WRONG_ASSIGNEE == "wrong_assignee"
    assert FindingType.REVIEW_OWNED_BY_IMPLEMENTER == "review_owned_by_implementer"


def test_construct_each_finding_type_with_required_fields():
    cof = CommentOnlyHandoffFinding(
        type=FindingType.COMMENT_ONLY_HANDOFF,
        issue_id="issue-1",
        issue_number=42,
        current_assignee_id="agent-a",
        mentioned_agent_id="agent-b",
        mention_comment_id="comment-1",
        mention_author_agent_id="agent-a",
        mention_age_seconds=600,
        issue_status="in_progress",
    )
    assert cof.type == FindingType.COMMENT_ONLY_HANDOFF
    assert cof.issue_id == "issue-1"

    waf = WrongAssigneeFinding(
        type=FindingType.WRONG_ASSIGNEE,
        issue_id="issue-2",
        issue_number=43,
        bogus_assignee_id="nobody-uuid",
        issue_status="todo",
        age_seconds=300,
    )
    assert waf.type == FindingType.WRONG_ASSIGNEE

    rof = ReviewOwnedByImplementerFinding(
        type=FindingType.REVIEW_OWNED_BY_IMPLEMENTER,
        issue_id="issue-3",
        issue_number=44,
        implementer_assignee_id="agent-c",
        implementer_role_name="PythonEngineer",
        implementer_role_class="implementer",
        age_seconds=400,
    )
    assert rof.type == FindingType.REVIEW_OWNED_BY_IMPLEMENTER


def test_naive_datetime_in_comment_raises():
    naive = datetime(2026, 5, 3, 12, 0, 0)  # no tzinfo
    with pytest.raises(ValueError, match="tz-aware"):
        Comment(id="c1", body="hi", author_agent_id="a1", created_at=naive)


def test_alert_result_round_trips_via_dataclass_fields():
    ar = AlertResult(
        finding_type=FindingType.WRONG_ASSIGNEE,
        issue_id="issue-5",
        posted=True,
        comment_id="cmt-99",
        error=None,
    )
    field_names = {f.name for f in fields(ar)}
    assert "finding_type" in field_names
    assert "posted" in field_names
    assert "comment_id" in field_names
    assert "error" in field_names
    assert ar.posted is True
    assert ar.error is None


def test_finding_union_type_alias_accepts_all_three():
    cof: Finding = CommentOnlyHandoffFinding(
        type=FindingType.COMMENT_ONLY_HANDOFF,
        issue_id="i",
        issue_number=1,
        current_assignee_id="a",
        mentioned_agent_id="b",
        mention_comment_id="c",
        mention_author_agent_id="a",
        mention_age_seconds=0,
        issue_status="todo",
    )
    waf: Finding = WrongAssigneeFinding(
        type=FindingType.WRONG_ASSIGNEE,
        issue_id="i",
        issue_number=1,
        bogus_assignee_id="x",
        issue_status="todo",
        age_seconds=0,
    )
    rof: Finding = ReviewOwnedByImplementerFinding(
        type=FindingType.REVIEW_OWNED_BY_IMPLEMENTER,
        issue_id="i",
        issue_number=1,
        implementer_assignee_id="a",
        implementer_role_name="PythonEngineer",
        implementer_role_class="implementer",
        age_seconds=0,
    )
    # All three are valid Finding instances
    for f in (cof, waf, rof):
        assert hasattr(f, "type")
        assert hasattr(f, "issue_id")
