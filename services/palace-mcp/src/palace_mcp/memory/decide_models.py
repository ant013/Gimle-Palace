"""Pydantic models for palace.memory.decide."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

SLICE_REF_PATTERN = re.compile(
    r"^GIM-\d+$|^N\+\d+[a-z]*(\.\d+)?$|^operator-decision-\d{8}$"
)

VALID_DECISION_MAKERS = frozenset(
    {
        "cto",
        "codereviewer",
        "pythonengineer",
        "opusarchitectreviewer",
        "qaengineer",
        "operator",
        "board",
    }
)


class DecideRequest(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    body: Annotated[str, Field(min_length=1, max_length=2000)]
    slice_ref: str
    decision_maker_claimed: str
    project: str | None = None
    decision_kind: Annotated[str, Field(max_length=80)] | None = None
    tags: Annotated[list[str], Field(max_length=16)] | None = None
    evidence_ref: Annotated[list[str], Field(max_length=32)] | None = None
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0

    @field_validator("slice_ref")
    @classmethod
    def validate_slice_ref(cls, v: str) -> str:
        if not SLICE_REF_PATTERN.match(v):
            raise ValueError(
                f"slice_ref {v!r} does not match allowed patterns: "
                "GIM-<n>, N+<n>[a-z][.<n>], operator-decision-<YYYYMMDD>"
            )
        return v

    @field_validator("decision_maker_claimed")
    @classmethod
    def validate_decision_maker(cls, v: str) -> str:
        if v not in VALID_DECISION_MAKERS:
            raise ValueError(
                f"decision_maker_claimed {v!r} not in allowed set: "
                + ", ".join(sorted(VALID_DECISION_MAKERS))
            )
        return v
