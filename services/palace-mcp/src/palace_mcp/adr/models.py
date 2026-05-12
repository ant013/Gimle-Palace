"""Pydantic models for ADR documents and sections."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

CANONICAL_SECTIONS: tuple[str, ...] = (
    "PURPOSE",
    "STACK",
    "ARCHITECTURE",
    "PATTERNS",
    "TRADEOFFS",
    "PHILOSOPHY",
)

SectionName = Literal[
    "PURPOSE", "STACK", "ARCHITECTURE", "PATTERNS", "TRADEOFFS", "PHILOSOPHY"
]

_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def validate_slug(slug: str) -> str:
    if not _SLUG_RE.match(slug):
        raise ValueError(f"Invalid ADR slug {slug!r}; must match ^[a-z][a-z0-9-]*$")
    return slug


def body_hash_for(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()


class AdrDocument(BaseModel):
    slug: str
    title: str
    status: Literal["active", "superseded", "draft"] = "active"
    created_at: datetime
    updated_at: datetime
    head_sha: str = "unknown"
    source_path: str  # relative path: docs/postulates/<slug>.md


class AdrSection(BaseModel):
    section_name: SectionName
    body: str
    body_hash: str = ""
    body_excerpt: str = ""
    last_edit: datetime

    def model_post_init(self, __context: object) -> None:
        if not self.body_hash:
            object.__setattr__(self, "body_hash", body_hash_for(self.body))
        if not self.body_excerpt:
            object.__setattr__(self, "body_excerpt", self.body[:500])
