from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


def _validate_tz(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("must be tz-aware")
    return v.astimezone(timezone.utc)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class OwnershipCheckpoint(FrozenModel):
    project_id: str
    last_head_sha: str | None
    last_completed_at: datetime
    run_id: str
    updated_at: datetime

    @field_validator("last_completed_at", "updated_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _validate_tz(v)


class OwnershipFileStateRecord(FrozenModel):
    project_id: str
    path: str
    status: Literal["processed", "skipped"]
    no_owners_reason: (
        Literal[
            "binary_or_skipped",
            "all_bot_authors",
            "no_commit_history",
        ]
        | None
    )
    last_run_id: str
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _validate_tz(v)


class BlameAttribution(FrozenModel):
    canonical_id: str
    canonical_name: str
    canonical_email: str
    lines: int
    last_commit_at: datetime | None = None

    @field_validator("last_commit_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        return _validate_tz(v) if v is not None else None


class ChurnShare(FrozenModel):
    canonical_id: str
    canonical_name: str
    canonical_email: str
    recency_score: float
    last_touched_at: datetime
    commit_count: int

    @field_validator("last_touched_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _validate_tz(v)


class OwnershipEdge(FrozenModel):
    project_id: str
    path: str
    canonical_id: str
    canonical_email: str
    canonical_name: str
    weight: float
    blame_share: float
    recency_churn_share: float
    last_touched_at: datetime
    lines_attributed: int
    commit_count: int
    canonical_via: Literal["identity", "mailmap_existing", "mailmap_synthetic"]

    @field_validator("last_touched_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _validate_tz(v)


class OwnershipRunSummary(FrozenModel):
    project_id: str
    run_id: str
    head_sha: str
    prev_head_sha: str | None
    dirty_files_count: int
    deleted_files_count: int
    edges_written: int
    edges_deleted: int
    mailmap_resolver_path: Literal["pygit2", "identity_passthrough"]
    exit_reason: Literal["success", "no_change", "no_dirty", "failed"]
    duration_ms: int
    alpha_used: float
