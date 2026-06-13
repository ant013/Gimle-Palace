"""palace.code.find_dead_code — graph-reachability dead-code analysis.

Distinct from palace.code.find_dead_symbols (Periphery/binary-surface approach).
This tool returns :DeadFinding nodes written by the dead_code extractor (G0d algorithm):
- dead_symbol: single unreachable symbol
- dead_scc_cluster: Tarjan SCC cluster >= 3 symbols
- dead_module: SCC cluster covering >= 50% of a module
- dead_extension_chain: extension chain on a dead type (no existential conformance)
"""

from __future__ import annotations

import json
from typing import Any

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

_GET_PROJECT = "MATCH (p:Project {slug: $slug}) RETURN p LIMIT 1"

_QUERY = """
MATCH (f:DeadFinding {project: $project})
WHERE f.severity IN $severities
RETURN
    f.finding_id AS finding_id,
    f.kind AS kind,
    f.severity AS severity,
    f.size AS size,
    f.safe_to_delete_score AS safe_to_delete_score,
    properties(f)[$git_last_external_ref_key] AS git_last_external_ref,
    f.members_json AS members_json,
    f.module_coverage_ratio AS module_coverage_ratio,
    properties(f)[$target_dead_type_key] AS target_dead_type,
    f.created_at AS created_at
ORDER BY
    CASE f.severity
        WHEN 'critical' THEN 0
        WHEN 'high' THEN 1
        WHEN 'medium' THEN 2
        ELSE 3
    END,
    f.safe_to_delete_score DESC
LIMIT $limit
""".strip()


def _severities_from_min(min_severity: str) -> list[str]:
    order = _SEVERITY_ORDER
    threshold = order.get(min_severity, 3)
    return [s for s, rank in order.items() if rank <= threshold]


def _error(code: str, message: str, project: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error_code": code, "message": message}
    if project is not None:
        out["project"] = project
    return out


async def find_dead_code(
    *,
    driver: Any,
    project: str,
    min_severity: str = "medium",
    include_test_only: bool = False,
    limit: int = 200,
) -> dict[str, Any]:
    """Return :DeadFinding nodes for a project above the given severity threshold."""
    if min_severity not in _SEVERITY_ORDER:
        return _error(
            "invalid_severity",
            f"min_severity must be one of {list(_SEVERITY_ORDER)}",
            project,
        )

    async with driver.session() as sess:
        row = await (await sess.run(_GET_PROJECT, slug=project)).single()
    if row is None:
        return _error(
            "project_not_registered",
            f"no :Project {{slug: {project!r}}}",
            project,
        )

    severities = _severities_from_min(min_severity)
    rows: list[dict[str, Any]] = []
    async with driver.session() as sess:
        result = await sess.run(
            _QUERY,
            project=project,
            severities=severities,
            limit=int(limit),
            git_last_external_ref_key="git_last_external_ref",
            target_dead_type_key="target_dead_type",
        )
        async for rec in result:
            rows.append(
                {
                    "finding_id": rec["finding_id"],
                    "kind": rec["kind"],
                    "severity": rec["severity"],
                    "size": rec["size"],
                    "safe_to_delete_score": rec["safe_to_delete_score"],
                    "git_last_external_ref": rec["git_last_external_ref"],
                    "members": json.loads(rec["members_json"])
                    if rec["members_json"]
                    else [],
                    "module_coverage_ratio": rec["module_coverage_ratio"],
                    "target_dead_type": rec["target_dead_type"],
                    "created_at": rec["created_at"],
                }
            )

    return {
        "ok": True,
        "project": project,
        "min_severity": min_severity,
        "total": len(rows),
        "result": rows,
    }
