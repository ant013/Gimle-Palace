from __future__ import annotations

import re
from enum import Enum, StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


class EcosystemEnum(StrEnum):
    GITHUB = "github"
    MAVEN = "maven"
    PYPI = "pypi"


class SeverityEnum(Enum):
    UNKNOWN = ("unknown", 0)
    PATCH = ("patch", 1)
    MINOR = ("minor", 2)
    MAJOR = ("major", 3)

    def __init__(self, value: str, rank: int) -> None:
        self._value_ = value
        self.rank = rank


class WarningCodeEnum(StrEnum):
    MEMBER_NOT_INDEXED = "member_not_indexed"
    MEMBER_NOT_REGISTERED = "member_not_registered"
    MEMBER_INVALID_SLUG = "member_invalid_slug"
    PURL_MISSING_VERSION = "purl_missing_version"
    PURL_MALFORMED = "purl_malformed"
    VERSION_UNPARSEABLE_IN_GROUP = "version_unparseable_in_group"


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SkewEntry(FrozenModel):
    scope_id: str
    version: str
    declared_in: str
    declared_constraint: str


class SkewGroup(FrozenModel):
    purl_root: str
    ecosystem: str
    severity: Literal["major", "minor", "patch", "unknown"]
    version_count: int
    entries: tuple[SkewEntry, ...]


class WarningEntry(FrozenModel):
    code: Literal[
        "member_not_indexed",
        "member_not_registered",
        "member_invalid_slug",
        "purl_missing_version",
        "purl_malformed",
        "version_unparseable_in_group",
    ]
    slug: str | None
    message: str


class RunSummary(FrozenModel):
    mode: Literal["project", "bundle"]
    target_slug: str
    member_count: int
    target_status_indexed_count: int
    skew_groups_total: int
    skew_groups_major: int
    skew_groups_minor: int
    skew_groups_patch: int
    skew_groups_unknown: int
    aligned_groups_total: int
    warnings_purl_malformed_count: int
