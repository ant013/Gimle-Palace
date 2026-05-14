"""Audit report renderer — pure function, no Neo4j calls.

Takes a dict of AuditSectionData keyed by extractor_name plus metadata,
renders each section via its Jinja2 template, assembles the final report.
"""

from __future__ import annotations

from collections import Counter
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

_SECTION_ORDER = (
    "hotspot",
    "dead_symbol_binary_surface",
    "dependency_surface",
    "code_ownership",
    "cross_repo_version_skew",
    "public_api_surface",
    "cross_module_contract",
)

_JINJA_ENV = Environment(
    loader=FileSystemLoader([str(_TEMPLATES_DIR), str(_REPORT_TEMPLATE.parent)]),
    undefined=StrictUndefined,
    autoescape=False,
    keep_trailing_newline=True,
)


class CoverageCountMismatch(Exception):
    """Raised when all_statuses count != sum of status buckets."""


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
    """Annotate findings with _severity key, sort by severity, cap at max_findings."""
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
    """Render one extractor section to markdown."""
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


def _render_profile_coverage(
    all_statuses: dict[str, Any],
    run_failed: dict[str, Any],
    fetch_failed_statuses: dict[str, Any],
    not_applicable: dict[str, Any],
    blind_spots: list[str],
) -> str:
    """Render §Profile Coverage appendix with R == N+M+K+F+L assertion."""
    total = len(all_statuses)
    ok_count = sum(1 for s in all_statuses.values() if s.status == "OK")
    failed_count = len(run_failed)
    fetch_count = len(fetch_failed_statuses)
    not_attempted_count = sum(
        1 for s in all_statuses.values() if s.status == "NOT_ATTEMPTED"
    )
    na_count = len(not_applicable)

    lines = [
        "\n## Profile Coverage\n",
        "| Status | Count |",
        "|--------|-------|",
        f"| OK | {ok_count} |",
        f"| RUN_FAILED | {failed_count} |",
        f"| FETCH_FAILED | {fetch_count} |",
        f"| NOT_ATTEMPTED | {not_attempted_count} |",
        f"| NOT_APPLICABLE | {na_count} |",
        f"| **Total (R)** | **{total}** |",
    ]
    return "\n".join(lines) + "\n"


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
    all_statuses: dict[str, Any] | None = None,
    run_failed: dict[str, Any] | None = None,
    fetch_failed_statuses: dict[str, Any] | None = None,
    not_applicable: dict[str, Any] | None = None,
) -> str:
    """Render the complete audit report as markdown."""
    ts = generated_at or datetime.now(tz=timezone.utc).isoformat()
    _mappers = severity_mappers or {}
    _run_failed = run_failed or {}
    _fetch_failed = fetch_failed_statuses or {}
    _not_applicable = not_applicable or {}
    _all_statuses = all_statuses or {}

    # Coverage count invariant check: R == sum(OK + RUN_FAILED + FETCH_FAILED + NOT_ATTEMPTED + NOT_APPLICABLE)
    if _all_statuses:
        total_in_all = len(_all_statuses)
        total_in_buckets = (
            sum(1 for s in _all_statuses.values() if s.status == "OK")
            + len(_run_failed)
            + len(_fetch_failed)
            + sum(1 for s in _all_statuses.values() if s.status == "NOT_ATTEMPTED")
            + len(_not_applicable)
        )
        if total_in_all != total_in_buckets:
            raise CoverageCountMismatch(
                f"coverage_count_mismatch: all_statuses has {total_in_all} entries "
                f"but bucket sums to {total_in_buckets}"
            )

    pinned_rendered: list[tuple[Severity, str]] = []
    remainder_rendered: list[tuple[Severity, str]] = []
    all_annotated: list[dict[str, Any]] = []
    all_library_annotated: list[dict[str, Any]] = []
    all_source_contexts: list[str] = []
    library_critical_sections = 0
    seen: set[str] = set()

    def _render_one(name: str, sec: AuditSectionData) -> tuple[Severity, str]:
        nonlocal library_critical_sections
        col = severity_columns.get(name, "_severity")
        cap = max_findings_per_section.get(name, 100)
        mapper = _mappers.get(name)
        annotated, max_sev_or_none = _annotate_severity(sec.findings, col, cap, mapper)
        all_annotated.extend(annotated[:3])
        # Source-context accounting (Task 3.5b + 3.6): use raw findings to avoid cap bias
        all_source_contexts.extend(
            f.get("source_context", "other") for f in sec.findings
        )
        # Library-only critical tracking: annotate without cap, filter, check severity
        uncapped, _ = _annotate_severity(
            sec.findings, col, len(sec.findings) if sec.findings else 1, mapper
        )
        lib_findings = [f for f in uncapped if f.get("source_context") == "library"]
        all_library_annotated.extend(lib_findings[:3])
        if lib_findings:
            lib_max = severity_from_str(lib_findings[0]["_severity"])
            if SEVERITY_RANK[lib_max] <= SEVERITY_RANK[Severity.HIGH]:
                library_critical_sections += 1
        max_sev = (
            max_sev_or_none if max_sev_or_none is not None else Severity.INFORMATIONAL
        )
        rendered = render_section(sec, col, cap, severity_mapper=mapper)
        return max_sev, rendered

    for name in _SECTION_ORDER:
        if name not in sections:
            continue
        seen.add(name)
        pinned_rendered.append(_render_one(name, sections[name]))

    for name, sec in sections.items():
        if name in seen:
            continue
        col = severity_columns.get(name, "_severity")
        cap = max_findings_per_section.get(name, 100)
        mapper = _mappers.get(name)
        annotated, max_sev_or_none = _annotate_severity(sec.findings, col, cap, mapper)
        all_annotated.extend(annotated[:3])
        all_source_contexts.extend(
            f.get("source_context", "other") for f in sec.findings
        )
        uncapped, _ = _annotate_severity(
            sec.findings, col, len(sec.findings) if sec.findings else 1, mapper
        )
        lib_findings = [f for f in uncapped if f.get("source_context") == "library"]
        all_library_annotated.extend(lib_findings[:3])
        if lib_findings:
            lib_max = severity_from_str(lib_findings[0]["_severity"])
            if SEVERITY_RANK[lib_max] <= SEVERITY_RANK[Severity.HIGH]:
                library_critical_sections += 1
        max_sev = (
            max_sev_or_none if max_sev_or_none is not None else Severity.INFORMATIONAL
        )
        try:
            rendered = render_section(sec, col, cap, severity_mapper=mapper)
        except TemplateNotFound:
            rendered = f"## {name.replace('_', ' ').title()}\n\n{len(sec.findings)} finding(s) — no template available.\n"
        remainder_rendered.append((max_sev, rendered))

    remainder_rendered.sort(key=lambda t: SEVERITY_RANK[t[0]])
    ordered_sections = [r for _, r in pinned_rendered + remainder_rendered]

    run_provenance = [
        {"extractor_name": s.extractor_name, "run_id": s.run_id}
        for s in sections.values()
    ]

    # Library-only critical count (Task 3.6): count sections with HIGH+ library findings
    total_critical = library_critical_sections

    # Top-3 findings from library source only (Task 3.6)
    all_library_annotated.sort(
        key=lambda f: SEVERITY_RANK[severity_from_str(f.get("_severity"))]
    )
    top3 = all_library_annotated[:3]

    # Source distribution (Task 3.5b)
    source_dist = Counter(all_source_contexts)
    dist_line = (
        f"Findings by source: library={source_dist['library']} "
        f"example={source_dist['example']} "
        f"test={source_dist['test']} "
        f"other={source_dist['other']}"
    )

    # Library-empty warning: only when total > 10 and 0 library findings (Task 3.5b)
    total_findings = len(all_source_contexts)
    library_findings_warning = ""
    if source_dist["library"] == 0 and total_findings > 10:
        library_findings_warning = (
            "> ⚠ **data_quality: library_findings_empty** — "
            f"0 library findings found out of {total_findings} total. "
            "Source-context classification may have missed library paths."
        )

    executive_lines = [
        f"Audit of project `{project}` at depth `{depth}`.",
        f"{len(sections)} extractor{'s' if len(sections) != 1 else ''} contributed data.",
        dist_line,
    ]
    if blind_spots:
        executive_lines.append(
            f"{len(blind_spots)} extractor(s) had no data (blind spots): {', '.join(f'`{b}`' for b in blind_spots)}."
        )
    if _run_failed:
        executive_lines.append(
            f"⚠ {len(_run_failed)} extractor(s) failed their last run: {', '.join(f'`{n}`' for n in _run_failed)}."
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

    # Render status sections
    failed_extractors_section = ""
    if _run_failed:
        failed_extractors_section = _JINJA_ENV.get_template(
            "failed_extractors.md"
        ).render(
            project=project,
            run_failed=_run_failed,
        )

    data_quality_section = ""
    if _fetch_failed:
        data_quality_section = _JINJA_ENV.get_template("data_quality_issues.md").render(
            project=project,
            fetch_failed=_fetch_failed,
        )

    blind_spots_section = _JINJA_ENV.get_template("blind_spots.md").render(
        project=project,
        blind_spots=blind_spots,
    )

    profile_coverage_section = ""
    if _all_statuses:
        profile_coverage_section = _render_profile_coverage(
            _all_statuses, _run_failed, _fetch_failed, _not_applicable, blind_spots
        )

    report_template = _JINJA_ENV.get_template("report_template.md")
    return report_template.render(
        project=project,
        generated_at=ts,
        depth=depth,
        executive_summary=" ".join(executive_lines),
        library_findings_warning=library_findings_warning,
        sections=ordered_sections,
        blind_spots=blind_spots,
        fetched_extractors=list(sections.keys()),
        run_provenance=run_provenance,
        failed_extractors_section=failed_extractors_section,
        data_quality_section=data_quality_section,
        blind_spots_section=blind_spots_section,
        profile_coverage_section=profile_coverage_section,
        run_failed=_run_failed,
        fetch_failed_statuses=_fetch_failed,
    )
