"""Generic audit fetcher — executes audit_contract().query per extractor.

Uses direct Cypher via the Neo4j async driver (no MCP round-trips).
Per spec §3.5 rev4: composite MCP tools are agent-facing; in-process
fetcher goes directly to Neo4j to avoid serialisation overhead.

Parameter note: the fetcher binds BOTH ``$project`` (bare slug, e.g. ``gimle``)
and ``$project_id`` (prefixed form, e.g. ``project/gimle``) in every Cypher
call.  Extractor contracts may use either parameter name — ``hotspot`` and
``code_ownership`` use ``$project_id``; the remaining five use ``$project``.
Both bindings must stay present to avoid silent empty-result regressions when
contracts are refactored.
"""

from __future__ import annotations

import logging
from typing import Any

from palace_mcp.audit.contracts import AuditSectionData, RunInfo
from palace_mcp.extractors.base import BaseExtractor

log = logging.getLogger(__name__)


async def fetch_audit_data(
    driver: Any,
    discovery_result: dict[str, RunInfo],
    extractor_registry: dict[str, BaseExtractor],
    *,
    failed_extractors: list[str] | None = None,
) -> dict[str, AuditSectionData]:
    """Fetch audit data for all discovered extractors.

    For each extractor in discovery_result:
    - Look up the extractor in the registry.
    - Skip if not found or audit_contract() returns None.
    - Execute contract.query via the Neo4j driver with $project and $project_id params.
    - Build AuditSectionData from the results.
    - On Neo4j error, log a warning and append the extractor name to
      ``failed_extractors`` (if provided) so callers can surface it as a blind spot.

    Returns dict keyed by extractor_name.
    """
    results: dict[str, AuditSectionData] = {}
    for extractor_name, run_info in discovery_result.items():
        ext = extractor_registry.get(extractor_name)
        if ext is None:
            continue
        contract = ext.audit_contract()
        if contract is None:
            continue

        findings: list[dict[str, Any]] = []
        try:
            async with driver.session() as session:
                result = await session.run(
                    contract.query,
                    project=run_info.project,
                    project_id=f"project/{run_info.project}",
                )
                async for rec in result:
                    findings.append(dict(rec))
        except Exception:
            log.warning(
                "audit fetch failed for extractor %r", extractor_name, exc_info=True
            )
            if failed_extractors is not None:
                failed_extractors.append(extractor_name)
            continue

        results[extractor_name] = AuditSectionData(
            extractor_name=extractor_name,
            run_id=run_info.run_id,
            project=run_info.project,
            completed_at=run_info.completed_at,
            findings=findings,
            summary_stats=_build_summary_stats(extractor_name, findings),
            template_name=contract.template_name,
        )
    return results


def _build_summary_stats(
    extractor_name: str, findings: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build basic summary stats from raw findings list."""
    stats: dict[str, Any] = {"total": len(findings)}

    if extractor_name == "hotspot":
        scores = [f.get("hotspot_score", 0.0) for f in findings]
        stats["file_count"] = len(findings)
        stats["max_score"] = max(
            (float(s) for s in scores if s is not None), default=0.0
        )
        window_days = findings[0].get("window_days") if findings else None
        stats["window_days"] = int(window_days) if window_days else 90

    elif extractor_name == "dead_symbol_binary_surface":
        states = [f.get("candidate_state", "") for f in findings]
        stats["confirmed_dead"] = sum(1 for s in states if s == "CONFIRMED_DEAD")
        stats["unused_candidate"] = sum(1 for s in states if s == "UNUSED_CANDIDATE")
        stats["skipped"] = sum(1 for s in states if s == "SKIPPED")

    elif extractor_name == "dependency_surface":
        scopes = list({f.get("scope") for f in findings if f.get("scope")})
        stats["scopes"] = scopes

    elif extractor_name == "code_ownership":
        diffuse = [f for f in findings if (f.get("top_owner_weight") or 1.0) < 0.2]
        stats["files_analysed"] = len(findings)
        stats["diffuse_ownership_count"] = len(diffuse)

    elif extractor_name == "cross_repo_version_skew":
        sevs = [f.get("skew_severity", "unknown") for f in findings]
        stats["major"] = sum(1 for s in sevs if s == "major")
        stats["minor"] = sum(1 for s in sevs if s == "minor")
        stats["patch"] = sum(1 for s in sevs if s == "patch")

    elif extractor_name == "public_api_surface":
        modules = {f.get("module_name") for f in findings if f.get("module_name")}
        stats["module_count"] = len(modules)

    elif extractor_name == "cross_module_contract":
        stats["breaking"] = sum(
            1 for f in findings if (f.get("removed_count") or 0) > 0
        )
        stats["signature_changes"] = sum(
            1 for f in findings if (f.get("signature_changed_count") or 0) > 0
        )

    elif extractor_name == "testability_di":
        stats["patterns"] = sum(1 for f in findings if f.get("style") is not None)
        stats["test_doubles"] = len(
            {
                (
                    double.get("kind"),
                    double.get("language"),
                    double.get("target_symbol"),
                    double.get("test_file"),
                )
                for finding in findings
                for double in finding.get("test_doubles") or []
            }
        )
        stats["untestable_sites"] = len(
            {
                (
                    site.get("file"),
                    site.get("start_line"),
                    site.get("end_line"),
                    site.get("category"),
                    site.get("symbol_referenced"),
                    site.get("severity"),
                    site.get("message"),
                )
                for finding in findings
                for site in finding.get("untestable_sites") or []
            }
        )

    return stats
