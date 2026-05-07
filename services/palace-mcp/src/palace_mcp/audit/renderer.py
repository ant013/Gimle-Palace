"""Audit report renderer — pure function, no Neo4j calls.

Takes a dict of AuditSectionData keyed by extractor_name plus metadata,
renders each section via its Jinja2 template, assembles the final report.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from palace_mcp.audit.contracts import (
    AuditSectionData,
    RunInfo,
    Severity,
    SEVERITY_RANK,
    severity_from_str,
)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_REPORT_TEMPLATE = Path(__file__).parent / "report_template.md"

_SECTION_ORDER = [
    "hotspot",
    "dead_symbol_binary_surface",
    "dependency_surface",
    "code_ownership",
    "cross_repo_version_skew",
    "public_api_surface",
    "cross_module_contract",
]

_JINJA_ENV = Environment(
    loader=FileSystemLoader([str(_TEMPLATES_DIR), str(_REPORT_TEMPLATE.parent)]),
    undefined=StrictUndefined,
    autoescape=False,
    keep_trailing_newline=True,
)


def _section_max_severity(section: AuditSectionData) -> Severity:
    if section.max_severity is not None:
        return section.max_severity
    if not section.findings:
        return Severity.INFORMATIONAL
    col = "_severity"
    worst = Severity.INFORMATIONAL
    for f in section.findings:
        sev = severity_from_str(f.get(col))
        if SEVERITY_RANK[sev] < SEVERITY_RANK[worst]:
            worst = sev
    return worst


def _annotate_severity(findings: list[dict[str, Any]], severity_column: str, max_findings: int) -> tuple[list[dict[str, Any]], Severity | None]:
    """Annotate findings with _severity key, sort by severity, cap at max_findings."""
    annotated = []
    for f in findings:
        raw = f.get(severity_column)
        sev = severity_from_str(str(raw) if raw is not None else None)
        annotated.append({**f, "_severity": sev.value})
    annotated.sort(key=lambda f: SEVERITY_RANK[severity_from_str(f["_severity"])])
    capped = annotated[:max_findings]
    max_sev = severity_from_str(capped[0]["_severity"]) if capped else None
    return capped, max_sev


def render_section(
    section: AuditSectionData,
    severity_column: str,
    max_findings: int,
) -> str:
    """Render one extractor section to markdown."""
    template = _JINJA_ENV.get_template(f"{section.extractor_name}.md")
    annotated_findings, _ = _annotate_severity(section.findings, severity_column, max_findings)
    return template.render(
        findings=annotated_findings,
        summary_stats=section.summary_stats,
        run_id=section.run_id,
        completed_at=section.completed_at,
        max_findings=max_findings,
    )


def render_report(
    *,
    project: str,
    sections: dict[str, AuditSectionData],
    severity_columns: dict[str, str],
    max_findings_per_section: dict[str, int],
    blind_spots: list[str],
    depth: str = "full",
    generated_at: str | None = None,
) -> str:
    """Render the complete audit report as markdown.

    Args:
        project: project slug.
        sections: dict keyed by extractor_name → AuditSectionData.
        severity_columns: dict keyed by extractor_name → column name for severity mapping.
        max_findings_per_section: dict keyed by extractor_name → cap.
        blind_spots: extractor names with no IngestRun data.
        depth: "quick" or "full".
        generated_at: ISO-8601 string; defaults to now.
    """
    ts = generated_at or datetime.now(tz=timezone.utc).isoformat()

    rendered_sections: list[tuple[Severity, str]] = []
    for name in _SECTION_ORDER:
        if name not in sections:
            continue
        sec = sections[name]
        col = severity_columns.get(name, "_severity")
        cap = max_findings_per_section.get(name, 100)
        rendered = render_section(sec, col, cap)
        max_sev = _section_max_severity(sec)
        rendered_sections.append((max_sev, rendered))

    rendered_sections.sort(key=lambda t: SEVERITY_RANK[t[0]])
    ordered_sections = [r for _, r in rendered_sections]

    run_provenance = [
        {"extractor_name": s.extractor_name, "run_id": s.run_id}
        for s in sections.values()
    ]

    total_critical = sum(
        1 for s in sections.values()
        if _section_max_severity(s) in (Severity.CRITICAL, Severity.HIGH)
    )
    executive_lines = [
        f"Audit of project `{project}` at depth `{depth}`.",
        f"{len(sections)} extractor{{ '' if len(sections) == 1 else 's' }} contributed data.",
    ]
    if blind_spots:
        executive_lines.append(f"{len(blind_spots)} extractor(s) had no data (blind spots): {', '.join(f'`{b}`' for b in blind_spots)}.")
    if total_critical:
        executive_lines.append(f"⚠ {total_critical} section(s) have critical/high findings requiring attention.")
    else:
        executive_lines.append("No critical or high severity findings.")

    report_template = _JINJA_ENV.get_template("report_template.md")
    return report_template.render(
        project=project,
        generated_at=ts,
        depth=depth,
        executive_summary=" ".join(executive_lines),
        sections=ordered_sections,
        blind_spots=blind_spots,
        fetched_extractors=list(sections.keys()),
        run_provenance=run_provenance,
    )
