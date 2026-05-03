"""Domain types — Finding, AlertResult, Comment, Agent dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal


class FindingType(StrEnum):
    COMMENT_ONLY_HANDOFF = "comment_only_handoff"
    WRONG_ASSIGNEE = "wrong_assignee"
    REVIEW_OWNED_BY_IMPLEMENTER = "review_owned_by_implementer"


@dataclass(frozen=True, slots=True)
class CommentOnlyHandoffFinding:
    type: Literal[FindingType.COMMENT_ONLY_HANDOFF]
    issue_id: str
    issue_number: int
    current_assignee_id: str
    mentioned_agent_id: str
    mention_comment_id: str
    mention_author_agent_id: str
    mention_age_seconds: int
    issue_status: str


@dataclass(frozen=True, slots=True)
class WrongAssigneeFinding:
    type: Literal[FindingType.WRONG_ASSIGNEE]
    issue_id: str
    issue_number: int
    bogus_assignee_id: str
    issue_status: str
    age_seconds: int


@dataclass(frozen=True, slots=True)
class ReviewOwnedByImplementerFinding:
    type: Literal[FindingType.REVIEW_OWNED_BY_IMPLEMENTER]
    issue_id: str
    issue_number: int
    implementer_assignee_id: str
    implementer_role_name: str
    implementer_role_class: Literal["implementer"]
    age_seconds: int


Finding = CommentOnlyHandoffFinding | WrongAssigneeFinding | ReviewOwnedByImplementerFinding


@dataclass(frozen=True, slots=True)
class AlertResult:
    finding_type: FindingType
    issue_id: str
    posted: bool
    comment_id: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class Comment:
    id: str
    body: str
    author_agent_id: str | None
    created_at: datetime  # must be tz-aware UTC

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None:
            raise ValueError(f"Comment.created_at must be tz-aware, got naive: {self.created_at!r}")


@dataclass(frozen=True, slots=True)
class Agent:
    id: str
    name: str
    status: str
