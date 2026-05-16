"""Neo4j snapshot writer for arch_layer extractor (GIM-243).

Uses delete-then-write (single transaction) so re-runs reflect the
current state of the repo: removed modules, closed violations, and
renamed layers are cleaned up automatically.

Edge type `:MODULE_DEPENDS_ON` is distinct from `:DEPENDS_ON` which
is owned by dependency_surface and connects Project -> ExternalDependency.
"""

from __future__ import annotations

from neo4j import AsyncDriver, AsyncManagedTransaction

from palace_mcp.extractors.arch_layer.models import (
    ArchRule,
    ArchViolation,
    Layer,
    Module,
    ModuleEdge,
)

# ---------------------------------------------------------------------------
# Delete existing snapshot for this project_id
# ---------------------------------------------------------------------------

_DELETE_ARCH_NODES = """
MATCH (n)
WHERE (n:Module OR n:Layer OR n:ArchRule OR n:ArchViolation)
  AND n.project_id = $project_id
DETACH DELETE n
"""

# ---------------------------------------------------------------------------
# Node writers
# ---------------------------------------------------------------------------

_WRITE_MODULE = """
CREATE (m:Module)
SET m.project_id = $project_id,
    m.slug       = $slug,
    m.name       = $name,
    m.kind       = $kind,
    m.manifest_path = $manifest_path,
    m.source_root   = $source_root,
    m.run_id     = $run_id
"""

_WRITE_LAYER = """
CREATE (l:Layer)
SET l.project_id  = $project_id,
    l.name        = $name,
    l.rule_source = $rule_source,
    l.run_id      = $run_id
"""

_WRITE_ARCH_RULE = """
CREATE (r:ArchRule)
SET r.project_id  = $project_id,
    r.rule_id     = $rule_id,
    r.kind        = $kind,
    r.severity    = $severity,
    r.rule_source = $rule_source,
    r.run_id      = $run_id
"""

_WRITE_ARCH_VIOLATION = """
CREATE (v:ArchViolation)
SET v.project_id     = $project_id,
    v.kind           = $kind,
    v.severity       = $severity,
    v.src_module     = $src_module,
    v.dst_module     = $dst_module,
    v.rule_id        = $rule_id,
    v.message        = $message,
    v.evidence       = $evidence,
    v.file           = $file,
    v.start_line     = $start_line,
    v.source_context = $source_context,
    v.run_id         = $run_id
"""

# ---------------------------------------------------------------------------
# Edge writers — look up nodes by project_id + slug/name, then CREATE edge
# ---------------------------------------------------------------------------

_WRITE_IN_LAYER = """
MATCH (m:Module {project_id: $project_id, slug: $module_slug})
MATCH (l:Layer  {project_id: $project_id, name: $layer_name})
CREATE (m)-[:IN_LAYER {run_id: $run_id}]->(l)
"""

_WRITE_MODULE_DEPENDS_ON = """
MATCH (src:Module {project_id: $project_id, slug: $src_slug})
MATCH (dst:Module {project_id: $project_id, slug: $dst_slug})
CREATE (src)-[:MODULE_DEPENDS_ON {
    scope: $scope,
    declared_in: $declared_in,
    evidence_kind: $evidence_kind,
    run_id: $run_id
}]->(dst)
"""

_WRITE_VIOLATES_RULE = """
MATCH (v:ArchViolation {project_id: $project_id, rule_id: $rule_id,
                         src_module: $src_module, dst_module: $dst_module,
                         evidence: $evidence})
MATCH (r:ArchRule      {project_id: $project_id, rule_id: $rule_id})
CREATE (v)-[:VIOLATES_RULE]->(r)
"""


async def replace_project_snapshot(
    driver: AsyncDriver,
    *,
    project_id: str,
    modules: list[Module],
    layers: list[Layer],
    rules: list[ArchRule],
    violations: list[ArchViolation],
    edges: list[ModuleEdge],
    module_layers: dict[str, str | None],  # slug -> layer name
    run_id: str,
) -> tuple[int, int]:
    """Delete the old snapshot and write the new one in a single transaction.

    Returns (nodes_written, edges_written).
    """
    nodes = [0]
    edges_count = [0]

    async with driver.session() as session:
        await session.execute_write(
            _write_snapshot,
            project_id,
            modules,
            layers,
            rules,
            violations,
            edges,
            module_layers,
            run_id,
            nodes,
            edges_count,
        )

    return nodes[0], edges_count[0]


async def _write_snapshot(  # noqa: PLR0912, PLR0913
    tx: AsyncManagedTransaction,
    project_id: str,
    modules: list[Module],
    layers: list[Layer],
    rules: list[ArchRule],
    violations: list[ArchViolation],
    edges: list[ModuleEdge],
    module_layers: dict[str, str | None],
    run_id: str,
    nodes: list[int],
    edges_count: list[int],
) -> None:
    await tx.run(_DELETE_ARCH_NODES, project_id=project_id)

    for m in modules:
        await tx.run(_WRITE_MODULE, **m.model_dump())
        nodes[0] += 1

    for la in layers:
        await tx.run(_WRITE_LAYER, **la.model_dump())
        nodes[0] += 1

    for r in rules:
        await tx.run(_WRITE_ARCH_RULE, **r.model_dump())
        nodes[0] += 1

    for v in violations:
        await tx.run(_WRITE_ARCH_VIOLATION, **v.model_dump())
        nodes[0] += 1

    # Edges: IN_LAYER
    for slug, layer_name in module_layers.items():
        if layer_name is None:
            continue
        await tx.run(
            _WRITE_IN_LAYER,
            project_id=project_id,
            module_slug=slug,
            layer_name=layer_name,
            run_id=run_id,
        )
        edges_count[0] += 1

    # Edges: MODULE_DEPENDS_ON
    for edge in edges:
        await tx.run(
            _WRITE_MODULE_DEPENDS_ON,
            project_id=project_id,
            src_slug=edge.src_slug,
            dst_slug=edge.dst_slug,
            scope=edge.scope,
            declared_in=edge.declared_in,
            evidence_kind=edge.evidence_kind,
            run_id=run_id,
        )
        edges_count[0] += 1

    # Edges: VIOLATES_RULE
    for v in violations:
        await tx.run(
            _WRITE_VIOLATES_RULE,
            project_id=project_id,
            rule_id=v.rule_id,
            src_module=v.src_module,
            dst_module=v.dst_module,
            evidence=v.evidence,
        )
        edges_count[0] += 1
