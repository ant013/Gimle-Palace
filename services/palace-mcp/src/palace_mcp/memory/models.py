"""Pydantic v2 models for multi-repo bundle support (GIM-182).

These are wire-contract types shared between bundle CRUD, ingest tracking,
and the MCP tool surface. Keep stable — changes are breaking.

Naming convention: :Bundle.group_id = "bundle/<name>",
:Project.group_id = "project/<slug>" (unchanged from pre-182 schema).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, field_validator

__all__ = [
    "Bundle",
    "BundleIngestState",
    "BundleStatus",
    "FrozenModel",
    "IngestRunResult",
    "ProjectRef",
    "Tier",
]

_BUNDLE_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")


class Tier(StrEnum):
    USER = "user"
    FIRST_PARTY = "first-party"
    VENDOR = "vendor"  # reserved for F1 (ThirdParty bundle); unused in v1


class FrozenModel(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}


class Bundle(FrozenModel):
    name: str
    description: str
    group_id: str  # always "bundle/<name>"
    created_at: datetime

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if not _BUNDLE_NAME_RE.match(v):
            raise ValueError(f"invalid bundle name: {v!r}")
        return v

    @field_validator("created_at")
    @classmethod
    def _check_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("created_at must be tz-aware")
        return v.astimezone(timezone.utc)


class ProjectRef(FrozenModel):
    slug: str
    tier: Tier
    added_to_bundle_at: datetime

    @field_validator("added_to_bundle_at")
    @classmethod
    def _check_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("added_to_bundle_at must be tz-aware")
        return v.astimezone(timezone.utc)


class BundleStatus(FrozenModel):
    name: str
    members_total: int
    members_fresh_within_7d: int
    members_stale: int
    query_failed_slugs: tuple[str, ...]  # transient query-time failures
    ingest_failed_slugs: tuple[str, ...]  # last_run succeeded=False
    never_ingested_slugs: tuple[str, ...]  # last_run is None
    stale_slugs: tuple[str, ...]
    oldest_member_ingest_at: datetime | None
    newest_member_ingest_at: datetime | None
    as_of: datetime  # snapshot timestamp

    @field_validator("as_of", "oldest_member_ingest_at", "newest_member_ingest_at")
    @classmethod
    def _check_tz_optional(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None:
            raise ValueError("datetime must be tz-aware")
        return v.astimezone(timezone.utc)


class IngestRunResult(FrozenModel):
    slug: str
    ok: bool
    run_id: str | None
    error_kind: (
        Literal[
            "file_not_found",
            "extractor_error",
            "tantivy_disk_full",
            "neo4j_unavailable",
            "unknown",
        ]
        | None
    )
    error: str | None
    duration_ms: int
    completed_at: datetime | None = None  # set when per-member ingest finishes

    @field_validator("completed_at")
    @classmethod
    def _check_tz_optional(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None:
            raise ValueError("completed_at must be tz-aware")
        return v.astimezone(timezone.utc)


class BundleIngestState(FrozenModel):
    bundle: str
    run_id: str
    state: Literal["running", "succeeded", "failed"]
    members_total: int
    members_done: int
    members_ok: int
    members_failed: int
    runs: tuple[IngestRunResult, ...]
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None

    @field_validator("started_at", "completed_at")
    @classmethod
    def _check_tz(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None:
            raise ValueError("datetime must be tz-aware")
        return v.astimezone(timezone.utc)
