"""Neo4j write logic for localization_accessibility extractor."""

from __future__ import annotations

from typing import Any

from palace_mcp.extractors.localization_accessibility.parsers.coverage import (
    LocaleCoverage,
)
from palace_mcp.extractors.localization_accessibility.rules.semgrep_runner import (
    SemgrepFinding,
)

_DELETE_EXISTING = """
MATCH (n)
WHERE (n:LocaleResource OR n:HardcodedString OR n:A11yMissing)
  AND n.project_id = $project_id
DETACH DELETE n
"""

_WRITE_LOCALE_RESOURCE = """
CREATE (lr:LocaleResource)
SET lr.project_id      = $project_id,
    lr.run_id          = $run_id,
    lr.locale          = $locale,
    lr.source          = $source,
    lr.key_count       = $key_count,
    lr.coverage_pct    = $coverage_pct,
    lr.surface         = $surface
"""

_WRITE_HARDCODED_STRING = """
CREATE (h:HardcodedString)
SET h.project_id   = $project_id,
    h.run_id       = $run_id,
    h.file         = $file,
    h.start_line   = $start_line,
    h.end_line     = $end_line,
    h.literal      = $literal,
    h.context      = $context,
    h.severity     = $severity,
    h.message      = $message
"""

_WRITE_A11Y_MISSING = """
CREATE (a:A11yMissing)
SET a.project_id   = $project_id,
    a.run_id       = $run_id,
    a.file         = $file,
    a.start_line   = $start_line,
    a.end_line     = $end_line,
    a.control_kind = $control_kind,
    a.surface      = $surface,
    a.severity     = $severity,
    a.message      = $message
"""


async def write_snapshot(
    driver: Any,
    *,
    project_id: str,
    run_id: str,
    locale_coverages: list[LocaleCoverage],
    hardcoded: list[SemgrepFinding],
    a11y_missing: list[SemgrepFinding],
) -> tuple[int, int]:
    """Write all loc-a11y data in a single transaction; return (nodes, edges)."""
    async with driver.session() as session:
        result: tuple[int, int] = await session.execute_write(
            _write_snapshot_tx,
            project_id,
            run_id,
            locale_coverages,
            hardcoded,
            a11y_missing,
        )
        return result


async def _write_snapshot_tx(
    tx: Any,
    project_id: str,
    run_id: str,
    locale_coverages: list[LocaleCoverage],
    hardcoded: list[SemgrepFinding],
    a11y_missing: list[SemgrepFinding],
) -> tuple[int, int]:
    cursor = await tx.run(_DELETE_EXISTING, project_id=project_id)
    await cursor.consume()

    nodes = 0

    for lr in locale_coverages:
        c = await tx.run(
            _WRITE_LOCALE_RESOURCE,
            project_id=project_id,
            run_id=run_id,
            locale=lr.locale,
            source=lr.source,
            key_count=lr.key_count,
            coverage_pct=lr.coverage_pct,
            surface=lr.surface,
        )
        await c.consume()
        nodes += 1

    for h in hardcoded:
        c = await tx.run(
            _WRITE_HARDCODED_STRING,
            project_id=project_id,
            run_id=run_id,
            file=h.file,
            start_line=h.start_line,
            end_line=h.end_line,
            literal=h.literal,
            context=h.context,
            severity=h.severity,
            message=h.message,
        )
        await c.consume()
        nodes += 1

    for a in a11y_missing:
        surface = _infer_surface(a.rule_id)
        control_kind = _infer_control_kind(a.context)
        c = await tx.run(
            _WRITE_A11Y_MISSING,
            project_id=project_id,
            run_id=run_id,
            file=a.file,
            start_line=a.start_line,
            end_line=a.end_line,
            control_kind=control_kind,
            surface=surface,
            severity=a.severity,
            message=a.message,
        )
        await c.consume()
        nodes += 1

    return nodes, 0


def _infer_surface(rule_id: str) -> str:
    lower = rule_id.lower()
    if "compose" in lower or "android" in lower:
        return "android"
    return "ios"


def _infer_control_kind(context: str) -> str:
    mapping = {
        "button": "button",
        "image": "image",
        "icon": "icon",
        "textfield": "textfield",
        "tappable_view": "tappable_view",
    }
    return mapping.get(context.lower(), "other")
