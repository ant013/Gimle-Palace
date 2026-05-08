from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from palace_mcp.audit.contracts import severity_from_str
from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.testability_di.models import (
    SourceFile,
    TestabilityExtractionSummary,
)
from palace_mcp.extractors.testability_di.neo4j_writer import replace_project_snapshot
from palace_mcp.extractors.testability_di.rules import (
    extract_di_patterns,
    extract_test_doubles,
    extract_untestable_sites,
)
from palace_mcp.extractors.testability_di.scanner import scan_repository

if TYPE_CHECKING:
    from graphiti_core import Graphiti
    from palace_mcp.audit.contracts import AuditContract


_QUERY = """
CALL {
  MATCH (di:DiPattern {project_id: $project_id})
  RETURN di.module AS module
  UNION
  MATCH (td:TestDouble {project_id: $project_id})
  RETURN td.module AS module
  UNION
  MATCH (us:UntestableSite {project_id: $project_id})
  RETURN us.module AS module
}
WITH DISTINCT module
OPTIONAL MATCH (di:DiPattern {project_id: $project_id, module: module})
WITH module,
     [pattern IN collect(DISTINCT di {
       .language, .style, .framework, .sample_count, .outliers, .confidence
     }) WHERE pattern.style IS NOT NULL] AS di_patterns
OPTIONAL MATCH (td:TestDouble {project_id: $project_id, module: module})
WITH module,
     di_patterns,
     [double IN collect(DISTINCT td {
       .kind, .language, .target_symbol, .test_file
     }) WHERE double.kind IS NOT NULL] AS test_doubles
OPTIONAL MATCH (us:UntestableSite {project_id: $project_id, module: module})
WITH module,
     di_patterns,
     test_doubles,
     [site IN collect(DISTINCT us {
       .file, .language, .start_line, .end_line, .category,
       .symbol_referenced, .severity, .message
     }) WHERE site.file IS NOT NULL] AS untestable_sites
WITH module,
     CASE
       WHEN size(di_patterns) = 0 THEN [{
         language: coalesce(
           head([double IN test_doubles WHERE double.language IS NOT NULL | double.language]),
           head([site IN untestable_sites WHERE site.language IS NOT NULL | site.language]),
           "unknown"
         ),
         style: null,
         framework: null,
         sample_count: 0,
         outliers: 0,
         confidence: "heuristic"
       }]
       ELSE di_patterns
     END AS rows,
     test_doubles,
     untestable_sites
UNWIND rows AS row
RETURN module AS module,
       row.language AS language,
       row.style AS style,
       row.framework AS framework,
       row.sample_count AS sample_count,
       row.outliers AS outliers,
       row.confidence AS confidence,
       test_doubles AS test_doubles,
       untestable_sites AS untestable_sites,
       CASE
         WHEN any(site IN untestable_sites WHERE site.severity = "high") THEN "high"
         WHEN row.style = "service_locator" THEN "high"
         WHEN size(untestable_sites) > 0 OR row.outliers > 0 THEN "medium"
         ELSE "low"
       END AS max_severity
ORDER BY max_severity DESC, module, style
LIMIT 100
""".strip()


class TestabilityDiExtractor(BaseExtractor):
    name: ClassVar[str] = "testability_di"
    description: ClassVar[str] = (
        "Detect dependency-injection styles, test doubles, and untestable seams "
        "in Swift and Kotlin repositories."
    )
    constraints: ClassVar[list[str]] = []
    indexes: ClassVar[list[str]] = [
        "CREATE INDEX di_pattern_lookup IF NOT EXISTS "
        "FOR (d:DiPattern) ON (d.project_id, d.module, d.style)",
        "CREATE INDEX test_double_lookup IF NOT EXISTS "
        "FOR (d:TestDouble) ON (d.project_id, d.module, d.kind)",
        "CREATE INDEX untestable_site_severity IF NOT EXISTS "
        "FOR (u:UntestableSite) ON (u.project_id, u.severity)",
    ]

    def audit_contract(self) -> "AuditContract":
        from palace_mcp.audit.contracts import AuditContract

        return AuditContract(
            extractor_name="testability_di",
            template_name="testability_di.md",
            query=_QUERY,
            severity_column="max_severity",
            severity_mapper=severity_from_str,
        )

    async def run(
        self, *, graphiti: "Graphiti", ctx: ExtractorRunContext
    ) -> ExtractorStats:
        sources = scan_repository(repo_path=ctx.repo_path)
        summary = _build_summary(
            project_id=ctx.group_id,
            run_id=ctx.run_id,
            sources=sources,
        )
        nodes_written = (
            len(summary.di_patterns)
            + len(summary.test_doubles)
            + len(summary.untestable_sites)
        )
        await replace_project_snapshot(
            graphiti.driver,
            project_id=ctx.group_id,
            run_id=ctx.run_id,
            di_patterns=summary.di_patterns,
            test_doubles=summary.test_doubles,
            untestable_sites=summary.untestable_sites,
        )
        return ExtractorStats(nodes_written=nodes_written, edges_written=0)


def _build_summary(
    *, project_id: str, run_id: str, sources: list[SourceFile]
) -> TestabilityExtractionSummary:
    return TestabilityExtractionSummary(
        di_patterns=extract_di_patterns(
            sources,
            project_id=project_id,
            run_id=run_id,
        ),
        test_doubles=extract_test_doubles(
            sources,
            project_id=project_id,
            run_id=run_id,
        ),
        untestable_sites=extract_untestable_sites(
            sources,
            project_id=project_id,
            run_id=run_id,
        ),
    )
