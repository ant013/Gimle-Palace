"""Coding convention extractor scaffolding (Roadmap #6)."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from graphiti_core import Graphiti

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorRunContext,
    ExtractorStats,
)

if TYPE_CHECKING:
    from palace_mcp.audit.contracts import AuditContract


class CodingConventionExtractor(BaseExtractor):
    """Scaffold for project-specific coding convention extraction."""

    name: ClassVar[str] = "coding_convention"
    description: ClassVar[str] = (
        "Detect dominant Swift and Kotlin coding conventions together with outliers."
    )
    constraints: ClassVar[list[str]] = []
    indexes: ClassVar[list[str]] = [
        "CREATE INDEX convention_lookup IF NOT EXISTS "
        "FOR (c:Convention) ON (c.project_id, c.module, c.kind)",
        "CREATE INDEX convention_violation_severity IF NOT EXISTS "
        "FOR (v:ConventionViolation) ON (v.project_id, v.severity)",
    ]

    def audit_contract(self) -> "AuditContract":
        from palace_mcp.audit.contracts import AuditContract, Severity

        def severity_from_outlier_ratio(raw_value: object) -> Severity:
            if isinstance(raw_value, (int, float)):
                ratio = float(raw_value)
            elif isinstance(raw_value, str) and raw_value:
                ratio = float(raw_value)
            else:
                ratio = 0.0
            if ratio >= 0.1:
                return Severity.HIGH
            if ratio > 0:
                return Severity.MEDIUM
            return Severity.LOW

        return AuditContract(
            extractor_name="coding_convention",
            template_name="coding_convention.md",
            query="""
MATCH (c:Convention {project_id: $project})
OPTIONAL MATCH (v:ConventionViolation {
  project_id: $project,
  module: c.module,
  kind: c.kind
})
WITH c, collect(v {
  .file,
  .start_line,
  .end_line,
  .message,
  .severity
}) AS violations,
CASE
  WHEN c.sample_count < 5 THEN 0.0
  WHEN c.sample_count = 0 THEN 0.0
  ELSE toFloat(c.outliers) / toFloat(c.sample_count)
END AS outlier_ratio
RETURN c.module AS module,
       c.kind AS kind,
       c.dominant_choice AS dominant_choice,
       c.confidence AS confidence,
       c.sample_count AS sample_count,
       c.outliers AS outliers,
       violations AS violations,
       outlier_ratio AS outlier_ratio
ORDER BY outlier_ratio DESC, c.module, c.kind
LIMIT 100
""".strip(),
            severity_column="outlier_ratio",
            severity_mapper=severity_from_outlier_ratio,
        )

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        del graphiti, ctx
        return ExtractorStats()
