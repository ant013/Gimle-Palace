from __future__ import annotations

from typing import Any

from neo4j import AsyncManagedTransaction

from palace_mcp.extractors.testability_di.models import (
    DiPattern,
    TestDouble,
    UntestableSite,
)

_DELETE_EXISTING = """
MATCH (n)
WHERE (n:DiPattern OR n:TestDouble OR n:UntestableSite) AND n.project_id = $project_id
DETACH DELETE n
"""

_WRITE_DI_PATTERN = """
CREATE (d:DiPattern)
SET d.project_id = $project_id,
    d.module = $module,
    d.language = $language,
    d.style = $style,
    d.framework = $framework,
    d.sample_count = $sample_count,
    d.outliers = $outliers,
    d.confidence = $confidence,
    d.run_id = $run_id
"""

_WRITE_TEST_DOUBLE = """
CREATE (d:TestDouble)
SET d.project_id = $project_id,
    d.module = $module,
    d.language = $language,
    d.kind = $kind,
    d.target_symbol = $target_symbol,
    d.test_file = $test_file,
    d.run_id = $run_id
"""

_WRITE_UNTESTABLE_SITE = """
CREATE (u:UntestableSite)
SET u.project_id = $project_id,
    u.module = $module,
    u.language = $language,
    u.file = $file,
    u.start_line = $start_line,
    u.end_line = $end_line,
    u.category = $category,
    u.symbol_referenced = $symbol_referenced,
    u.severity = $severity,
    u.message = $message,
    u.run_id = $run_id
"""

_UPDATE_RUN = """
MATCH (run:IngestRun {id: $run_id})
SET run.testability_di_patterns = $di_patterns,
    run.testability_di_test_doubles = $test_doubles,
    run.testability_di_untestable_sites = $untestable_sites
"""


async def replace_project_snapshot(
    driver: Any,
    *,
    project_id: str,
    run_id: str,
    di_patterns: list[DiPattern],
    test_doubles: list[TestDouble],
    untestable_sites: list[UntestableSite],
) -> None:
    async with driver.session() as session:
        await session.execute_write(
            _write_snapshot,
            project_id,
            run_id,
            di_patterns,
            test_doubles,
            untestable_sites,
        )


async def _write_snapshot(
    tx: AsyncManagedTransaction,
    project_id: str,
    run_id: str,
    di_patterns: list[DiPattern],
    test_doubles: list[TestDouble],
    untestable_sites: list[UntestableSite],
) -> None:
    await tx.run(_DELETE_EXISTING, project_id=project_id)
    for di_pattern in di_patterns:
        await tx.run(_WRITE_DI_PATTERN, **di_pattern.model_dump())
    for test_double in test_doubles:
        await tx.run(_WRITE_TEST_DOUBLE, **test_double.model_dump())
    for untestable_site in untestable_sites:
        await tx.run(_WRITE_UNTESTABLE_SITE, **untestable_site.model_dump())
    await tx.run(
        _UPDATE_RUN,
        run_id=run_id,
        di_patterns=len(di_patterns),
        test_doubles=len(test_doubles),
        untestable_sites=len(untestable_sites),
    )
