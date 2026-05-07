"""Generic audit fetcher — executes audit_contract().query per extractor.

Uses direct Cypher via the Neo4j async driver (no MCP round-trips).
Per spec §3.5 rev4: composite MCP tools are agent-facing; in-process
fetcher goes directly to Neo4j to avoid serialisation overhead.
"""

from __future__ import annotations

from typing import Any

from palace_mcp.audit.contracts import AuditSectionData, RunInfo
from palace_mcp.extractors.base import BaseExtractor


async def fetch_audit_data(
    driver: Any,
    discovery_result: dict[str, RunInfo],
    extractor_registry: dict[str, BaseExtractor],
) -> dict[str, AuditSectionData]:
    """Fetch audit data for all discovered extractors.

    For each extractor in discovery_result:
    - Look up the extractor in the registry.
    - Skip if not found or audit_contract() returns None.
    - Execute contract.query via the Neo4j driver with $project param.
    - Build AuditSectionData from the results.

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
        async with driver.session() as session:
            result = await session.run(
                contract.query,
                project=run_info.project,
                project_id=f"project/{run_info.project}",
            )
            async for rec in result:
                findings.append(dict(rec))

        results[extractor_name] = AuditSectionData(
            extractor_name=extractor_name,
            run_id=run_info.run_id,
            project=run_info.project,
            completed_at=run_info.completed_at,
            findings=findings,
            summary_stats=_build_summary_stats(extractor_name, findings),
        )
    return results


def _build_summary_stats(extractor_name: str, findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Build basic summary stats from raw findings list."""
    stats: dict[str, Any] = {"total": len(findings)}

    if extractor_name == "hotspot":
        scores = [f.get("hotspot_score", 0.0) for f in findings]
        stats["file_count"] = len(findings)
        stats["max_score"] = max((float(s) for s in scores if s is not None), default=0.0)
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
        stats["breaking"] = sum(1 for f in findings if (f.get("removed_count") or 0) > 0)
        stats["signature_changes"] = sum(1 for f in findings if (f.get("signature_changed_count") or 0) > 0)

    return stats
