"""Neo4j snapshot writer for coding conventions."""

from __future__ import annotations

from neo4j import AsyncDriver

from palace_mcp.extractors.coding_convention.models import (
    ConventionFinding,
    ConventionViolation,
)

_DELETE_EXISTING = """
MATCH (n)
WHERE (n:Convention OR n:ConventionViolation) AND n.project_id = $project_id
DETACH DELETE n
"""

_WRITE_CONVENTION = """
CREATE (c:Convention)
SET c.project_id = $project_id,
    c.module = $module,
    c.kind = $kind,
    c.dominant_choice = $dominant_choice,
    c.confidence = $confidence,
    c.sample_count = $sample_count,
    c.outliers = $outliers,
    c.run_id = $run_id
"""

_WRITE_VIOLATION = """
CREATE (v:ConventionViolation)
SET v.project_id = $project_id,
    v.module = $module,
    v.kind = $kind,
    v.file = $file,
    v.start_line = $start_line,
    v.end_line = $end_line,
    v.message = $message,
    v.severity = $severity,
    v.run_id = $run_id
"""


async def replace_project_snapshot(
    driver: AsyncDriver,
    *,
    project_id: str,
    findings: list[ConventionFinding],
    violations: list[ConventionViolation],
) -> None:
    async with driver.session() as session:
        await session.run(_DELETE_EXISTING, project_id=project_id)
        for finding in findings:
            await session.run(_WRITE_CONVENTION, **finding.model_dump())
        for violation in violations:
            await session.run(_WRITE_VIOLATION, **violation.model_dump())
