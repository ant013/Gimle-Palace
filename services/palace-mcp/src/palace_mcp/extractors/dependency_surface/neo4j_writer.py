"""Neo4j writer for dependency_surface extractor.

Writes :ExternalDependency nodes and :DEPENDS_ON edges with counter-precise
idempotency semantics (uses ResultSummary.counters, not MERGE-attempt counts).
"""

from __future__ import annotations

from collections.abc import Iterable

from neo4j import AsyncDriver

from palace_mcp.extractors.dependency_surface.models import ParsedDep

_UPSERT_EXT_DEP = """
MERGE (d:ExternalDependency {purl: $purl})
ON CREATE SET d.ecosystem = $ecosystem,
              d.resolved_version = $resolved_version,
              d.group_id = $group_id,
              d.first_seen_at = datetime()
"""
# No ON MATCH SET: ExternalDependency is first-writer-wins per spec §3.4 inv 1+2.

_UPSERT_DEPENDS_ON_EDGE = """
MATCH (p:Project {slug: $project_slug})
MATCH (d:ExternalDependency {purl: $purl})
MERGE (p)-[r:DEPENDS_ON {scope: $scope, declared_in: $declared_in}]->(d)
ON CREATE SET r.declared_version_constraint = $declared_version_constraint,
              r.first_seen_at = datetime()
"""
# No ON MATCH SET: declared_version_constraint captured on first MERGE only (v1).


async def write_to_neo4j(
    driver: AsyncDriver,
    deps: Iterable[ParsedDep],
    *,
    project_slug: str,
    group_id: str,
) -> tuple[int, int]:
    """Write deps to Neo4j. Returns (nodes_created, relationships_created) from
    ResultSummary counters — not MERGE-attempted counts, so re-run yields (0, 0)."""
    nodes_created = 0
    relationships_created = 0

    async with driver.session() as session:
        for dep in deps:
            result = await session.run(
                _UPSERT_EXT_DEP,
                purl=dep.purl,
                ecosystem=dep.ecosystem,
                resolved_version=dep.resolved_version,
                group_id=group_id,
            )
            summary = await result.consume()
            nodes_created += summary.counters.nodes_created

            result = await session.run(
                _UPSERT_DEPENDS_ON_EDGE,
                project_slug=project_slug,
                purl=dep.purl,
                scope=dep.scope,
                declared_in=dep.declared_in,
                declared_version_constraint=dep.declared_version_constraint,
            )
            summary = await result.consume()
            relationships_created += summary.counters.relationships_created

    return nodes_created, relationships_created
