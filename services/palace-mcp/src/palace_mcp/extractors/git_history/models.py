from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationInfo,
    computed_field,
    field_validator,
)

_EMAIL_RE = re.compile(r"^[^@]+@[^@]+\.[^@]+$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TRUNC_MAX = 1024


def _validate_tz(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("must be tz-aware")
    return v.astimezone(timezone.utc)


def _validate_truncated(v: str) -> str:
    if len(v) > _TRUNC_MAX + 3:
        raise ValueError(f"truncated body exceeds {_TRUNC_MAX + 3} chars: {len(v)}")
    return v


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Author(FrozenModel):
    provider: Literal["git", "github"]
    identity_key: str
    email: str | None
    name: str
    is_bot: bool
    first_seen_at: datetime
    last_seen_at: datetime

    @field_validator("identity_key", mode="after")
    @classmethod
    def _normalize_identity(cls, v: str, info: ValidationInfo) -> str:
        return v.lower() if (info.data or {}).get("provider") == "git" else v

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _EMAIL_RE.match(v):
            raise ValueError(f"invalid email: {v!r}")
        return v.lower()

    @field_validator("first_seen_at", "last_seen_at")
    @classmethod
    def _tz_check(cls, v: datetime) -> datetime:
        return _validate_tz(v)


class Commit(FrozenModel):
    project_id: str
    sha: str
    author_provider: Literal["git", "github"]
    author_identity_key: str
    committer_provider: Literal["git", "github"]
    committer_identity_key: str
    message_subject: str
    message_full_truncated: str
    committed_at: datetime
    parents: tuple[str, ...]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def short_sha(self) -> str:
        return self.sha[:7]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1

    @field_validator("sha")
    @classmethod
    def _check_sha(cls, v: str) -> str:
        if not _SHA_RE.match(v):
            raise ValueError(f"invalid sha: {v!r}")
        return v

    @field_validator("message_full_truncated")
    @classmethod
    def _check_truncated(cls, v: str) -> str:
        return _validate_truncated(v)

    @field_validator("committed_at")
    @classmethod
    def _tz_check(cls, v: datetime) -> datetime:
        return _validate_tz(v)


class PR(FrozenModel):
    project_id: str
    number: int
    title: str
    body_truncated: str
    state: Literal["open", "merged", "closed"]
    author_provider: Literal["git", "github"]
    author_identity_key: str
    created_at: datetime
    merged_at: datetime | None
    head_sha: str | None
    base_branch: str

    @field_validator("state", mode="before")
    @classmethod
    def _normalize_state(cls, v: str) -> str:
        return v.lower() if isinstance(v, str) else v

    @field_validator("body_truncated")
    @classmethod
    def _check_truncated(cls, v: str) -> str:
        return _validate_truncated(v)

    @field_validator("created_at", "merged_at")
    @classmethod
    def _tz_check(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        return _validate_tz(v)


class PRComment(FrozenModel):
    project_id: str
    id: str
    pr_number: int
    body_truncated: str
    author_provider: Literal["git", "github"]
    author_identity_key: str
    created_at: datetime

    @field_validator("body_truncated")
    @classmethod
    def _check_truncated(cls, v: str) -> str:
        return _validate_truncated(v)

    @field_validator("created_at")
    @classmethod
    def _tz_check(cls, v: datetime) -> datetime:
        return _validate_tz(v)


class GitHistoryCheckpoint(FrozenModel):
    project_id: str
    last_commit_sha: str | None
    last_pr_updated_at: datetime | None
    last_phase_completed: Literal["none", "phase1", "phase2"]
    updated_at: datetime

    @field_validator("last_pr_updated_at", "updated_at")
    @classmethod
    def _tz_check(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        return _validate_tz(v)


class IngestSummary(FrozenModel):
    project_id: str
    run_id: str
    commits_written: int
    authors_written: int
    prs_written: int
    pr_comments_written: int
    files_touched: int
    full_resync: bool
    last_commit_sha: str | None
    last_pr_updated_at: datetime | None
    duration_ms: int
