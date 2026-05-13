"""Audit report renderer — pure function, no Neo4j calls.

Takes a dict of AuditSectionData keyed by extractor_name plus metadata,
renders each section via its Jinja2 template, assembles the final report.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, StrictUndefined

from palace_mcp.audit.contracts import (
    AuditSectionData,
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


def _annotate_severity(
    findings: list[dict[str, Any]],
    severity_column: str,
    max_findings: int,
    severity_mapper: Callable[[Any], Severity] | None = None,
) -> tuple[list[dict[str, Any]], Severity | None]:
    """Annotate findings with _severity key, sort by severity, cap at max_findings.

    If ``severity_mapper`` is provided it takes the raw field value and returns
    a Severity directly, enabling domain-typed columns (floats, ints, enum
    strings).  When None, falls back to ``severity_from_str(str(raw))``.
    """
    annotated = []
    for f in findings:
        raw = f.get(severity_column)
        if severity_mapper is not None:
            sev = severity_mapper(raw)
        else:
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
    severity_mapper: Callable[[Any], Severity] | None = None,
) -> str:
    """Render one extractor section to markdown.

    Template resolution order:
    1. ``section.template_name`` (set by the fetcher from ``AuditContract.template_name``)
    2. ``{section.extractor_name}.md`` (backward-compat fallback)
    """
    template_file = (
        section.template_name
        if section.template_name
        else f"{section.extractor_name}.md"
    )
    template = _JINJA_ENV.get_template(template_file)
    annotated_findings, _ = _annotate_severity(
        section.findings, severity_column, max_findings, severity_mapper
    )
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
    severity_mappers: dict[str, Callable[[Any], Severity]] | None = None,
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
        severity_mappers: optional dict keyed by extractor_name → domain severity mapper.
            When provided, overrides the default severity_from_str fallback for the
            corresponding extractor so domain-typed columns (floats, ints, enum strings)
            produce real severity values instead of universally INFORMATIONAL.
        depth: "quick" or "full".
        generated_at: ISO-8601 string; defaults to now.
    """
    ts = generated_at or datetime.now(tz=timezone.utc).isoformat()
    _mappers = severity_mappers or {}

    rendered_sections: list[tuple[Severity, str]] = []
    # Annotated findings collected for executive summary top-3 computation.
    # _annotate_severity is called here (for max_sev) and again inside render_section;
    # the duplication is intentional to keep render_section's API unchanged.
    all_annotated: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _render_one(name: str, sec: AuditSectionData) -> tuple[Severity, str]:
        col = severity_columns.get(name, "_severity")
        cap = max_findings_per_section.get(name, 100)
        mapper = _mappers.get(name)
        annotated, max_sev_or_none = _annotate_severity(sec.findings, col, cap, mapper)
        all_annotated.extend(annotated[:3])
        max_sev = (
            max_sev_or_none if max_sev_or_none is not None else Severity.INFORMATIONAL
        )
        rendered = render_section(sec, col, cap, severity_mapper=mapper)
        return max_sev, rendered

    # 1. Known extractors in preferred display order
    for name in _SECTION_ORDER:
        if name not in sections:
            continue
        seen.add(name)
        rendered_sections.append(_render_one(name, sections[name]))

    # 2. Any extra extractors not in _SECTION_ORDER (paved-path: new extractors
    #    plug in via audit_contract() without requiring orchestrator code changes)
    for name, sec in sections.items():
        if name in seen:
            continue
        col = severity_columns.get(name, "_severity")
        cap = max_findings_per_section.get(name, 100)
        mapper = _mappers.get(name)
        annotated, max_sev_or_none = _annotate_severity(sec.findings, col, cap, mapper)
        all_annotated.extend(annotated[:3])
        max_sev = (
            max_sev_or_none if max_sev_or_none is not None else Severity.INFORMATIONAL
        )
        try:
            rendered = render_section(sec, col, cap, severity_mapper=mapper)
        except TemplateNotFound:
            rendered = f"## {name.replace('_', ' ').title()}\n\n{len(sec.findings)} finding(s) — no template available.\n"
        rendered_sections.append((max_sev, rendered))

    rendered_sections.sort(key=lambda t: SEVERITY_RANK[t[0]])
    ordered_sections = [r for _, r in rendered_sections]

    run_provenance = [
        {"extractor_name": s.extractor_name, "run_id": s.run_id}
        for s in sections.values()
    ]

    total_critical = sum(
        1 for sev, _ in rendered_sections if sev in (Severity.CRITICAL, Severity.HIGH)
    )

    # Top-3 findings for executive summary (worst severity first, across all sections)
    all_annotated.sort(
        key=lambda f: SEVERITY_RANK[severity_from_str(f.get("_severity"))]
    )
    top3 = all_annotated[:3]

    executive_lines = [
        f"Audit of project `{project}` at depth `{depth}`.",
        f"{len(sections)} extractor{'s' if len(sections) != 1 else ''} contributed data.",
    ]
    if blind_spots:
        executive_lines.append(
            f"{len(blind_spots)} extractor(s) had no data (blind spots): {', '.join(f'`{b}`' for b in blind_spots)}."
        )
    if total_critical:
        executive_lines.append(
            f"⚠ {total_critical} section(s) have critical/high findings requiring attention."
        )
    else:
        executive_lines.append("No critical or high severity findings.")
    if top3:
        top3_strs: list[str] = []
        for f in top3:
            sev = (f.get("_severity") or "").upper()
            kind = f.get("kind") or ""
            loc = f.get("file") or f.get("path") or ""
            line = f.get("start_line") or f.get("line") or ""
            msg = (f.get("message") or f.get("description") or "")[:120]
            loc_str = f"`{loc}:{line}`" if loc and line else (f"`{loc}`" if loc else "")
            parts = [f"**{sev}**"]
            if kind:
                parts.append(f"[{kind}]")
            if loc_str:
                parts.append(loc_str)
            if msg:
                parts.append(f"— {msg}")
            top3_strs.append(" ".join(parts))
        executive_lines.append("Top findings: " + "; ".join(top3_strs) + ".")

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
