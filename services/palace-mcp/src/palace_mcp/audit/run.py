"""palace.audit.run — synchronous MCP tool that runs a full audit report.

Calls discovery → fetcher → renderer in-process. Returns the assembled
markdown report and metadata. No async agent dispatch (that is S1.9).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from palace_mcp.audit.discovery import (
    ExtractorStatus,
    discover_extractor_statuses,
)
from palace_mcp.audit.contracts import RunInfo
from palace_mcp.audit.fetcher import fetch_audit_data
from palace_mcp.audit.renderer import render_report
from palace_mcp.extractors.foundation.profiles import resolve_profile

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_VALID_DEPTHS = {"quick", "full"}


def _err(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error_code": code, "message": message}


async def run_audit(
    driver: Any,
    extractor_registry: dict[str, Any],
    *,
    project: str | None = None,
    bundle: str | None = None,
    depth: str = "full",
) -> dict[str, Any]:
    """Run a synchronous audit report.

    Args:
        driver: Neo4j async driver.
        extractor_registry: dict[name, BaseExtractor] from extractors.registry.
        project: project slug (mutually exclusive with bundle).
        bundle: bundle name (mutually exclusive with project).
        depth: "quick" or "full".
    """
    # Validation
    if (project is None) == (bundle is None):
        return _err(
            "invalid_args", "exactly one of 'project' or 'bundle' must be provided"
        )

    target = project or bundle
    if target is None:
        return _err(
            "invalid_args", "exactly one of 'project' or 'bundle' must be provided"
        )

    if not _SLUG_RE.match(target):
        return _err("invalid_slug", f"slug {target!r} must match [a-z0-9-]{{1,64}}")

    if depth not in _VALID_DEPTHS:
        return _err("invalid_depth", f"depth must be one of {sorted(_VALID_DEPTHS)}")

    # --- Single-project path ---
    # Bundle path (Task 2.3b) reuses bundle_statuses; single-project builds flat dict.
    if project is not None:
        return await _run_single_project(
            driver, extractor_registry, project=project, depth=depth
        )
    else:
        # bundle mode — Task 2.3b
        return await _run_bundle(
            driver,
            extractor_registry,
            bundle=bundle,
            depth=depth,  # type: ignore[arg-type]
        )


async def _run_single_project(
    driver: Any,
    extractor_registry: dict[str, Any],
    *,
    project: str,
    depth: str,
) -> dict[str, Any]:
    """Run audit for a single project using typed status taxonomy."""
    # 1. Resolve language profile
    try:
        profile = await resolve_profile(driver, project)
    except ValueError:
        # Unknown profile — include all auditable registry extractors as applicable
        auditable_names = frozenset(
            name
            for name, ext in extractor_registry.items()
            if ext.audit_contract() is not None
        )
        from palace_mcp.extractors.foundation.profiles import LanguageProfile

        profile = LanguageProfile("unknown", auditable_names)

    # 2. Discover extractor statuses (last-attempt-wins, no success filter)
    all_statuses: dict[str, ExtractorStatus] = await discover_extractor_statuses(
        driver, project=project, profile=profile, registry=extractor_registry
    )

    # 3. Build discovery dict for fetcher: only OK extractors
    discovery: dict[str, RunInfo] = {}
    for name, status in all_statuses.items():
        if status.status == "OK" and status.last_run_id is not None:
            discovery[name] = RunInfo(
                run_id=status.last_run_id,
                extractor_name=name,
                project=project,
                completed_at=None,
            )

    # 4. Fetch data — failed_extractors out-param preserves existing mechanism
    fetch_failed: list[str] = []
    sections = await fetch_audit_data(
        driver, discovery, extractor_registry, failed_extractors=fetch_failed
    )

    # 5. Promote FETCH_FAILED: extractor was OK in discovery but fetcher raised
    for name in fetch_failed:
        all_statuses[name] = ExtractorStatus(
            extractor_name=name,
            status="FETCH_FAILED",
            last_run_id=all_statuses.get(name, ExtractorStatus(name, "OK")).last_run_id,
        )

    # 6. Compute blind_spots (backward-compat): NOT_ATTEMPTED + FETCH_FAILED
    blind_spots = sorted(
        name
        for name, s in all_statuses.items()
        if s.status in ("NOT_ATTEMPTED", "FETCH_FAILED")
    )

    # 7. Status counts for result envelope
    status_counts = _count_statuses(all_statuses)

    # 8. Build per-section metadata for renderer
    severity_columns: dict[str, str] = {}
    max_findings_per_section: dict[str, int] = {}
    severity_mappers = {}
    for name, ext in extractor_registry.items():
        contract = ext.audit_contract()
        if contract is not None:
            severity_columns[name] = contract.severity_column
            max_findings_per_section[name] = contract.max_findings
            if contract.severity_mapper is not None:
                severity_mappers[name] = contract.severity_mapper

    # 9. Render
    generated_at = datetime.now(tz=timezone.utc).isoformat()

    # Buckets by status for renderer new sections (Task 2.4)
    run_failed = {n: s for n, s in all_statuses.items() if s.status == "RUN_FAILED"}
    fetch_failed_statuses = {
        n: s for n, s in all_statuses.items() if s.status == "FETCH_FAILED"
    }
    not_applicable = {
        n: s for n, s in all_statuses.items() if s.status == "NOT_APPLICABLE"
    }

    report_markdown = render_report(
        project=project,
        sections=sections,
        severity_columns=severity_columns,
        max_findings_per_section=max_findings_per_section,
        blind_spots=blind_spots,
        severity_mappers=severity_mappers,
        depth=depth,
        generated_at=generated_at,
        all_statuses=all_statuses,
        run_failed=run_failed,
        fetch_failed_statuses=fetch_failed_statuses,
        not_applicable=not_applicable,
    )

    return {
        "ok": True,
        "report_markdown": report_markdown,
        "fetched_extractors": list(sections.keys()),
        "blind_spots": blind_spots,
        "status_counts": status_counts,
        "provenance": {
            "project": project,
            "generated_at": generated_at,
            "depth": depth,
            "run_ids": {name: s.run_id for name, s in sections.items()},
        },
    }


async def _run_bundle(
    driver: Any,
    extractor_registry: dict[str, Any],
    *,
    bundle: str,
    depth: str,
) -> dict[str, Any]:
    """Run audit for a bundle (per-member discovery, Task 2.3b)."""
    from palace_mcp.memory.bundle import bundle_members, BundleNotFoundError

    try:
        members = await bundle_members(driver, bundle=bundle)
    except BundleNotFoundError:
        return _err("bundle_not_found", f"bundle {bundle!r} not found")

    # Per-member statuses keyed by (member_slug, extractor_name)
    bundle_statuses: dict[tuple[str, str], ExtractorStatus] = {}
    all_sections: dict[str, Any] = {}
    all_blind_spots: list[str] = []
    all_status_counts: dict[str, int] = {}
    all_run_failed: dict[str, ExtractorStatus] = {}
    all_fetch_failed_statuses: dict[str, ExtractorStatus] = {}
    all_not_applicable: dict[str, ExtractorStatus] = {}

    for member in members:
        slug = member.slug
        try:
            profile = await resolve_profile(driver, slug)
        except ValueError:
            from palace_mcp.extractors.foundation.profiles import LanguageProfile

            profile = LanguageProfile("unknown", frozenset())

        member_statuses = await discover_extractor_statuses(
            driver, project=slug, profile=profile, registry=extractor_registry
        )
        for name, status in member_statuses.items():
            bundle_statuses[(slug, name)] = status

        # Fetcher for this member
        discovery: dict[str, RunInfo] = {}
        for name, status in member_statuses.items():
            if status.status == "OK" and status.last_run_id is not None:
                discovery[name] = RunInfo(
                    run_id=status.last_run_id,
                    extractor_name=name,
                    project=slug,
                    completed_at=None,
                )

        fetch_failed: list[str] = []
        sections = await fetch_audit_data(
            driver, discovery, extractor_registry, failed_extractors=fetch_failed
        )
        for name in fetch_failed:
            member_statuses[name] = ExtractorStatus(
                extractor_name=name,
                status="FETCH_FAILED",
                last_run_id=member_statuses.get(
                    name, ExtractorStatus(name, "OK")
                ).last_run_id,
            )
            bundle_statuses[(slug, name)] = member_statuses[name]

        # Merge into bundle-level aggregates (keyed by "<slug>/<extractor>")
        for name, sec in sections.items():
            all_sections[f"{slug}/{name}"] = sec
        for name in (
            n
            for n, s in member_statuses.items()
            if s.status in ("NOT_ATTEMPTED", "FETCH_FAILED")
        ):
            all_blind_spots.append(f"{slug}/{name}")
        for name, s in member_statuses.items():
            if s.status == "RUN_FAILED":
                all_run_failed[f"{slug}/{name}"] = s
            elif s.status == "FETCH_FAILED":
                all_fetch_failed_statuses[f"{slug}/{name}"] = s
            elif s.status == "NOT_APPLICABLE":
                all_not_applicable[f"{slug}/{name}"] = s

        for sv, cnt in _count_statuses(member_statuses).items():
            all_status_counts[sv] = all_status_counts.get(sv, 0) + cnt

    all_blind_spots_sorted = sorted(all_blind_spots)

    # Flatten statuses for renderer
    flat_statuses = {f"{slug}/{name}": s for (slug, name), s in bundle_statuses.items()}

    # Per-section metadata
    severity_columns: dict[str, str] = {}
    max_findings_per_section: dict[str, int] = {}
    severity_mappers = {}
    for name, ext in extractor_registry.items():
        contract = ext.audit_contract()
        if contract is not None:
            severity_columns[name] = contract.severity_column
            max_findings_per_section[name] = contract.max_findings
            if contract.severity_mapper is not None:
                severity_mappers[name] = contract.severity_mapper

    generated_at = datetime.now(tz=timezone.utc).isoformat()
    report_markdown = render_report(
        project=bundle,
        sections=all_sections,
        severity_columns=severity_columns,
        max_findings_per_section=max_findings_per_section,
        blind_spots=all_blind_spots_sorted,
        severity_mappers=severity_mappers,
        depth=depth,
        generated_at=generated_at,
        all_statuses=flat_statuses,
        run_failed=all_run_failed,
        fetch_failed_statuses=all_fetch_failed_statuses,
        not_applicable=all_not_applicable,
    )

    return {
        "ok": True,
        "report_markdown": report_markdown,
        "fetched_extractors": list(all_sections.keys()),
        "blind_spots": all_blind_spots_sorted,
        "status_counts": all_status_counts,
        "provenance": {
            "bundle": bundle,
            "generated_at": generated_at,
            "depth": depth,
            "run_ids": {name: s.run_id for name, s in all_sections.items()},
        },
    }


def _count_statuses(statuses: dict[str, ExtractorStatus]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in statuses.values():
        counts[s.status] = counts.get(s.status, 0) + 1
    return counts
