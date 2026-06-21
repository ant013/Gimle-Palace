"""Neo4j writer for :DeadFinding nodes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from neo4j import AsyncDriver

from palace_mcp.extractors.dead_code.models import DeadFinding

_MERGE_DEAD_FINDINGS_BATCH = """
UNWIND $rows AS row
MERGE (f:DeadFinding {finding_id: row.finding_id})
SET f += row.props
"""

_MERGE_DEAD_SYMBOL_EDGES_BATCH = """
UNWIND $edges AS edge
MATCH (f:DeadFinding {finding_id: edge.finding_id})
MERGE (s:Symbol {qualified_name: edge.qualified_name, group_id: edge.group_id})
MERGE (f)-[:DEAD_SYMBOL]->(s)
"""

_EVICT_STALE_FINDINGS = """
MATCH (f:DeadFinding {group_id: $group_id})
WHERE NOT f.finding_id IN $kept_ids
DETACH DELETE f
"""


@dataclass(frozen=True)
class DeadFindingWriteSummary:
    nodes_created: int = 0
    relationships_created: int = 0
    properties_set: int = 0
    nodes_deleted: int = 0


async def write_dead_findings(
    *,
    driver: AsyncDriver,
    findings: list[DeadFinding],
    group_id: str,
) -> DeadFindingWriteSummary:
    """Write :DeadFinding nodes then evict stale ones by group_id."""
    kept_ids = [f.finding_id for f in findings]

    async with driver.session() as session:
        write_summary = DeadFindingWriteSummary()
        if findings:
            write_summary = await session.execute_write(
                _write_findings_batch, findings, group_id
            )
        evict_summary = await session.execute_write(
            _evict_stale_findings, group_id, kept_ids
        )

    return DeadFindingWriteSummary(
        nodes_created=write_summary.nodes_created,
        relationships_created=write_summary.relationships_created,
        properties_set=write_summary.properties_set,
        nodes_deleted=evict_summary.nodes_deleted,
    )


async def _write_finding(
    tx: Any, finding: DeadFinding, group_id: str
) -> DeadFindingWriteSummary:
    return await _write_findings_batch(tx, [finding], group_id)


async def _write_findings_batch(
    tx: Any, findings: list[DeadFinding], group_id: str
) -> DeadFindingWriteSummary:
    nodes_created = 0
    rels_created = 0
    props_set = 0

    rows = [
        {
            "finding_id": finding.finding_id,
            "props": _finding_props(finding, group_id),
        }
        for finding in findings
    ]
    if rows:
        result = await tx.run(_MERGE_DEAD_FINDINGS_BATCH, rows=rows)
        s = await result.consume()
        nodes_created += s.counters.nodes_created
        props_set += s.counters.properties_set

    edges = [
        {
            "finding_id": finding.finding_id,
            "qualified_name": member.qualified_name,
            "group_id": group_id,
        }
        for finding in findings
        for member in finding.members
    ]
    if edges:
        result = await tx.run(_MERGE_DEAD_SYMBOL_EDGES_BATCH, edges=edges)
        s = await result.consume()
        nodes_created += s.counters.nodes_created
        rels_created += s.counters.relationships_created

    return DeadFindingWriteSummary(
        nodes_created=nodes_created,
        relationships_created=rels_created,
        properties_set=props_set,
    )


def _finding_props(finding: DeadFinding, group_id: str) -> dict[str, Any]:
    props: dict[str, Any] = {
        "group_id": group_id,
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
    return props


async def _evict_stale_findings(
    tx: Any, group_id: str, kept_ids: list[str]
) -> DeadFindingWriteSummary:
    result = await tx.run(
        _EVICT_STALE_FINDINGS,
        group_id=group_id,
        kept_ids=kept_ids,
    )
    s = await result.consume()
    return DeadFindingWriteSummary(nodes_deleted=s.counters.nodes_deleted)


def _members_json(finding: DeadFinding) -> str:
    return json.dumps(
        [
            {
                "qualified_name": m.qualified_name,
                "kind": m.kind,
                "file_path": m.file_path,
            }
            for m in finding.members
        ],
        sort_keys=True,
    )
