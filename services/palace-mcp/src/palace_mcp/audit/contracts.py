"""Audit contract types — AuditContract, AuditSectionData, Severity.

These are the shared types used across audit/discovery, audit/fetcher,
audit/renderer, and every extractor's audit_contract() method.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict


class Severity(str, Enum):
    """Canonical severity ladder for audit findings."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFORMATIONAL: 4,
}


def severity_from_str(value: str | None) -> Severity:
    """Parse a severity string; unknown values map to INFORMATIONAL."""
    try:
        return Severity(value) if value else Severity.INFORMATIONAL
    except ValueError:
        return Severity.INFORMATIONAL


@dataclass(frozen=True)
class AuditContract:
    """Contract returned by BaseExtractor.audit_contract().

    Tells the fetcher how to query data for an extractor and which template
    to render it with.
    """

    extractor_name: str
    template_name: str  # filename under audit/templates/ (e.g. "hotspot.md")
    query: str  # Cypher query; receives $project param; returns list of rows
    severity_column: str  # key in each result row that drives severity mapping
    max_findings: int = field(default=100)
    # Optional domain-specific severity mapper: (raw_value) -> Severity.
    # When None, the renderer falls back to severity_from_str(str(raw_value)),
    # which maps anything not in {"critical","high","medium","low","informational"}
    # to INFORMATIONAL. Extractors that use domain-typed columns (floats, ints,
    # enum strings like "CONFIRMED_DEAD") must supply a mapper.
    severity_mapper: Callable[[Any], "Severity"] | None = field(
        default=None, hash=False, compare=False
    )


class RunInfo(BaseModel):
    """Metadata for the latest successful :IngestRun for one extractor."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    extractor_name: str
    project: str
    completed_at: str | None = None


class AuditSectionData(BaseModel):
    """Rendered data for one extractor section."""

    model_config = ConfigDict(frozen=True)

    extractor_name: str
    run_id: str
    project: str
    completed_at: str | None
    findings: list[dict[str, Any]]
    summary_stats: dict[str, Any]
    max_severity: Severity | None = None
    # Template filename from AuditContract.template_name.
    # None only for AuditSectionData objects created outside the fetcher
    # (e.g., in unit tests); renderer falls back to f"{extractor_name}.md".
    template_name: str | None = None
