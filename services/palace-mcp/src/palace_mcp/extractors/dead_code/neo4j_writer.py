"""Neo4j writer for :DeadFinding nodes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from neo4j import AsyncDriver

from palace_mcp.extractors.dead_code.models import DeadFinding

_MERGE_DEAD_FINDING = """
MERGE (f:DeadFinding {finding_id: $finding_id})
SET f += $props
"""

_MERGE_DEAD_SYMBOL_EDGE = """
MATCH (f:DeadFinding {finding_id: $finding_id})
MERGE (s:Symbol {qualified_name: $qualified_name, group_id: $group_id})
MERGE (f)-[:DEAD_SYMBOL]->(s)
"""


@dataclass(frozen=True)
class DeadFindingWriteSummary:
    nodes_created: int = 0
    relationships_created: int = 0
    properties_set: int = 0


async def write_dead_findings(
    *,
    driver: AsyncDriver,
    findings: list[DeadFinding],
    group_id: str,
) -> DeadFindingWriteSummary:
    """Write :DeadFinding nodes in one transaction per finding."""
    total_nodes = 0
    total_rels = 0
    total_props = 0

    async with driver.session() as session:
        for finding in findings:
            summary = await session.execute_write(_write_finding, finding, group_id)
            total_nodes += summary.nodes_created
            total_rels += summary.relationships_created
            total_props += summary.properties_set

    return DeadFindingWriteSummary(
        nodes_created=total_nodes,
        relationships_created=total_rels,
        properties_set=total_props,
    )


async def _write_finding(
    tx: Any, finding: DeadFinding, group_id: str
) -> DeadFindingWriteSummary:
    nodes_created = 0
    rels_created = 0
    props_set = 0

    props: dict[str, Any] = {
        "kind": finding.kind.value,
        "severity": finding.severity.value,
        "project": finding.project,
        "created_at": finding.created_at,
        "size": finding.size,
        "reachable_from_public_surface": finding.reachable_from_public_surface,
        "reachable_from_dynamic_dispatch": finding.reachable_from_dynamic_dispatch,
        "safe_to_delete_score": finding.safe_to_delete_score,
        "evidence_query": finding.evidence_query,
        "members_json": _members_json(finding),
    }
    if finding.git_last_external_ref is not None:
        props["git_last_external_ref"] = finding.git_last_external_ref
    if finding.module_coverage_ratio is not None:
        props["module_coverage_ratio"] = finding.module_coverage_ratio
    if finding.target_dead_type is not None:
        props["target_dead_type"] = finding.target_dead_type

    result = await tx.run(
        _MERGE_DEAD_FINDING,
        finding_id=finding.finding_id,
        props=props,
    )
    s = await result.consume()
    nodes_created += s.counters.nodes_created
    props_set += s.counters.properties_set

    for member in finding.members:
        result = await tx.run(
            _MERGE_DEAD_SYMBOL_EDGE,
            finding_id=finding.finding_id,
            qualified_name=member.qualified_name,
            group_id=group_id,
        )
        s = await result.consume()
        nodes_created += s.counters.nodes_created
        rels_created += s.counters.relationships_created

    return DeadFindingWriteSummary(
        nodes_created=nodes_created,
        relationships_created=rels_created,
        properties_set=props_set,
    )


def _members_json(finding: DeadFinding) -> list[dict[str, Any]]:
    return [
        {
            "qualified_name": m.qualified_name,
            "kind": m.kind,
            "file_path": m.file_path,
        }
        for m in finding.members
    ]
