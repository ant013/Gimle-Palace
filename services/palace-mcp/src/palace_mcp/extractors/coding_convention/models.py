"""Typed DTOs for coding-convention aggregation and persistence."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Confidence = Literal["certain", "heuristic"]
ViolationSeverity = Literal["low", "medium", "high"]


class ConventionSignal(BaseModel):
    module: str
    kind: str
    choice: str
    file: str
    start_line: int
    end_line: int
    message: str


class ConventionFinding(BaseModel):
    project_id: str
    module: str
    kind: str
    dominant_choice: str
    confidence: Confidence
    sample_count: int
    outliers: int
    run_id: str
    source_context: str = "other"


class ConventionViolation(BaseModel):
    project_id: str
    module: str
    kind: str
    file: str
    start_line: int
    end_line: int
    message: str
    severity: ViolationSeverity
    run_id: str
    source_context: str = "other"


class ConventionExtractionSummary(BaseModel):
    findings: list[ConventionFinding]
    violations: list[ConventionViolation]
