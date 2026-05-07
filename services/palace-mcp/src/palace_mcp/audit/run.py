"""palace.audit.run — synchronous MCP tool that runs a full audit report.

Calls discovery → fetcher → renderer in-process. Returns the assembled
markdown report and metadata. No async agent dispatch (that is S1.9).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from palace_mcp.audit.discovery import find_latest_runs
from palace_mcp.audit.fetcher import fetch_audit_data
from palace_mcp.audit.renderer import render_report

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
        return _err("invalid_args", "exactly one of 'project' or 'bundle' must be provided")

    target = project or bundle
    if target is None:
        return _err("invalid_args", "exactly one of 'project' or 'bundle' must be provided")

    if not _SLUG_RE.match(target):
        return _err("invalid_slug", f"slug {target!r} must match [a-z0-9-]{{1,64}}")

    if depth not in _VALID_DEPTHS:
        return _err("invalid_depth", f"depth must be one of {sorted(_VALID_DEPTHS)}")

    # Discovery
    discovery = await find_latest_runs(driver, project=target)

    # Determine blind spots: extractors with audit_contract() but no IngestRun
    audit_extractors = {
        name
        for name, ext in extractor_registry.items()
        if ext.audit_contract() is not None
    }
    blind_spots = sorted(audit_extractors - set(discovery.keys()))

    # Fetcher — failed_extractors receives names of any extractor whose Cypher errored;
    # they are appended to blind_spots so the report flags them as unavailable.
    fetch_failed: list[str] = []
    sections = await fetch_audit_data(driver, discovery, extractor_registry, failed_extractors=fetch_failed)
    blind_spots = sorted(set(blind_spots) | set(fetch_failed))

    # Build per-section metadata for renderer
    severity_columns: dict[str, str] = {}
    max_findings_per_section: dict[str, int] = {}
    for name, ext in extractor_registry.items():
        contract = ext.audit_contract()
        if contract is not None:
            severity_columns[name] = contract.severity_column
            max_findings_per_section[name] = contract.max_findings

    # Render
    generated_at = datetime.now(tz=timezone.utc).isoformat()
    report_markdown = render_report(
        project=target,
        sections=sections,
        severity_columns=severity_columns,
        max_findings_per_section=max_findings_per_section,
        blind_spots=blind_spots,
        depth=depth,
        generated_at=generated_at,
    )

    return {
        "ok": True,
        "report_markdown": report_markdown,
        "fetched_extractors": list(sections.keys()),
        "blind_spots": blind_spots,
        "provenance": {
            "project": target,
            "generated_at": generated_at,
            "depth": depth,
            "run_ids": {name: s.run_id for name, s in sections.items()},
        },
    }
