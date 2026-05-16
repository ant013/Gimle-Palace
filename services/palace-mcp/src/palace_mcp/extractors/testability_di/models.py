from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Language = Literal["swift", "kotlin"]
Confidence = Literal["heuristic"]
DiStyle = Literal[
    "init_injection",
    "property_injection",
    "framework_bound",
    "service_locator",
]
TestDoubleKind = Literal[
    "mockk",
    "mockito",
    "cuckoo",
    "spy",
    "stub",
    "fake",
    "mock",
    "hand_rolled",
]
UntestableCategory = Literal[
    "service_locator",
    "direct_clock",
    "direct_session",
    "direct_filesystem",
    "direct_preferences",
]
FindingSeverity = Literal["low", "medium", "high"]


class SourceFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    relative_path: str
    module: str
    language: Language
    is_test: bool
    text: str


class DiPattern(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str
    module: str
    language: Language
    style: DiStyle
    framework: str | None
    sample_count: int
    outliers: int
    confidence: Confidence
    run_id: str


class TestDouble(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str
    module: str
    language: Language
    kind: TestDoubleKind
    target_symbol: str | None
    test_file: str
    run_id: str


class UntestableSite(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str
    module: str
    language: Language
    file: str
    start_line: int
    end_line: int
    category: UntestableCategory
    symbol_referenced: str
    severity: FindingSeverity
    message: str
    run_id: str


class TestabilityExtractionSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    di_patterns: list[DiPattern]
    test_doubles: list[TestDouble]
    untestable_sites: list[UntestableSite]
