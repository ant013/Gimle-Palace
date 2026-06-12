"""Neo4j writer for :DeadFinding nodes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from neo4j import AsyncDriver

from palace_mcp.extractors.dead_code.models import DeadFinding

_MERGE_DEAD_FINDING = """
MERGE (f:DeadFinding {finding_id: $finding_id})
SET f += $props
"""

_MERGE_DEAD_FINDING_BATCH = """
UNWIND $rows AS row
MERGE (f:DeadFinding {finding_id: row.finding_id})
SET f += row.props
"""

_MERGE_DEAD_SYMBOL_EDGE = """
MATCH (f:DeadFinding {finding_id: $finding_id})
MERGE (s:Symbol {qualified_name: $qualified_name, group_id: $group_id})
MERGE (f)-[:DEAD_SYMBOL]->(s)
"""

_MERGE_DEAD_SYMBOL_EDGE_BATCH = """
UNWIND $rows AS row
MATCH (f:DeadFinding {finding_id: row.finding_id})
UNWIND row.members AS member
MERGE (s:Symbol {qualified_name: member.qualified_name, group_id: $group_id})
MERGE (f)-[:DEAD_SYMBOL]->(s)
"""

_EVICT_STALE_FINDINGS = """
MATCH (f:DeadFinding {group_id: $group_id})
WHERE NOT f.finding_id IN $kept_ids
DETACH DELETE f
"""

_WRITE_BATCH_SIZE = 500


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
    total_nodes = 0
    total_rels = 0
    total_props = 0

    kept_ids = [f.finding_id for f in findings]
    rows = [_finding_row(finding, group_id) for finding in findings]

    async with driver.session() as session:
        for batch in _chunks(rows, _WRITE_BATCH_SIZE):
            summary = await session.execute_write(_write_finding_batch, batch, group_id)
            total_nodes += summary.nodes_created
            total_rels += summary.relationships_created
            total_props += summary.properties_set

        evict_summary = await session.execute_write(
            _evict_stale_findings, group_id, kept_ids
        )

    return DeadFindingWriteSummary(
        nodes_created=total_nodes,
        relationships_created=total_rels,
        properties_set=total_props,
        nodes_deleted=evict_summary.nodes_deleted,
    )


def _finding_row(finding: DeadFinding, group_id: str) -> dict[str, Any]:
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

    return {
        "finding_id": finding.finding_id,
        "props": props,
        "members": [
            {"qualified_name": member.qualified_name} for member in finding.members
        ],
    }


def _chunks(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


async def _write_finding_batch(
    tx: Any, rows: list[dict[str, Any]], group_id: str
) -> DeadFindingWriteSummary:
    if not rows:
        return DeadFindingWriteSummary()

    result = await tx.run(_MERGE_DEAD_FINDING_BATCH, rows=rows)
    node_summary = await result.consume()

    result = await tx.run(
        _MERGE_DEAD_SYMBOL_EDGE_BATCH,
        rows=rows,
        group_id=group_id,
    )
    edge_summary = await result.consume()

    return DeadFindingWriteSummary(
        nodes_created=(
            node_summary.counters.nodes_created + edge_summary.counters.nodes_created
        ),
        relationships_created=edge_summary.counters.relationships_created,
        properties_set=node_summary.counters.properties_set,
    )


async def _write_finding(
    tx: Any, finding: DeadFinding, group_id: str
) -> DeadFindingWriteSummary:
    nodes_created = 0
    rels_created = 0
    props_set = 0

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
