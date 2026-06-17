"""Batch-write SCIP-derived :Symbol nodes and edges to Neo4j.

Used by symbol_index_swift (and future SCIP-based extractors) to materialise
the call/reference graph needed by dead_code.graph_loader.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from palace_mcp.code.source_scope import classify_source_scope
from palace_mcp.symbol_identity import (
    canonical_symbol_kind,
    canonical_symbol_label,
    canonical_symbol_short_name,
)

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from palace_mcp.extractors.scip_parser import ScipSymbolInfo
    from palace_mcp.smoke.recipe import Recipe

_SCIP_KINDS_WITH_SHADOW_BACKING = frozenset(
    {
        "Variable",
        "Field",
        "Property",
        "Type",
        "Struct",
        "Class",
        "Enum",
        "Protocol",
        "TypeAlias",
    }
)

_BATCH_SIZE = 500

# MERGE with explicit property initialisation so dead_code.graph_loader
# never reads null for the boolean columns it expects.
_MERGE_SYMBOLS = """
UNWIND $rows AS r
MERGE (s:Symbol {qualified_name: r.qualified_name, group_id: r.group_id})
SET s.project_id             = $project_id,
    s.kind                   = r.kind,
    s.label                  = r.label,
    s.short_name             = r.short_name,
    s.file_path              = r.file_path,
    s.module_name            = r.module_name,
    s.source_scope           = r.source_scope,
    s.last_seen_in_run_id    = $run_id,
    s.last_seen_at           = datetime($seen_at),
    s.last_seen_in_commit    = $commit_sha,
    s.access_modifier        = '',
    s.is_objc                = false,
    s.is_dynamic             = false,
    s.is_objc_members        = false,
    s.is_ns_managed          = false,
    s.is_property_wrapper    = false,
    s.is_codable             = false,
    s.is_iboutlet            = false,
    s.is_ibaction            = false,
    s.is_swift_app_storage   = false,
    s.is_env_key             = false,
    s.is_main_entry          = false,
    s.referenced_via_mirror  = false,
    s.deleted_at             = null
REMOVE s:Deprecated
REMOVE s.deprecated_at, s.deprecated_in_commit
WITH s
OPTIONAL MATCH (s)-[old:LAST_SEEN_IN]->()
DELETE old
WITH s
MATCH (run:IngestRun {run_id: $run_id})
MERGE (s)-[:LAST_SEEN_IN]->(run)
"""

_SOFT_DELETE_ABSENT = """
MATCH (s:Symbol {group_id: $group_id})
WHERE NOT s.qualified_name IN $qnames
SET s.deleted_at = $now
"""

_MERGE_REFERENCES = """
UNWIND $rows AS r
MATCH (a:Symbol {qualified_name: r.source, group_id: r.group_id})
MATCH (b:Symbol {qualified_name: r.target, group_id: r.group_id})
MERGE (a)-[:REFERENCES]->(b)
"""

_MERGE_CONFORMS_TO = """
UNWIND $rows AS r
MATCH (a:Symbol {qualified_name: r.source, group_id: r.group_id})
MATCH (b:Symbol {qualified_name: r.target, group_id: r.group_id})
MERGE (a)-[:CONFORMS_TO]->(b)
"""

_MERGE_EXTENDS = """
UNWIND $rows AS r
MATCH (a:Symbol {qualified_name: r.source, group_id: r.group_id})
MATCH (b:Symbol {qualified_name: r.target, group_id: r.group_id})
MERGE (a)-[:EXTENDS]->(b)
"""

_MERGE_EXTENSION_OF = """
UNWIND $rows AS r
MATCH (a:Symbol {qualified_name: r.source, group_id: r.group_id})
MATCH (b:Symbol {qualified_name: r.target, group_id: r.group_id})
MERGE (a)-[:EXTENSION_OF]->(b)
"""

_MERGE_BACKED_BY_SYMBOL_SHADOWS = """
UNWIND $rows AS r
MATCH (symbol:Symbol {qualified_name: r.qualified_name, group_id: r.group_id})
MATCH (shadow:SymbolOccurrenceShadow {
    symbol_qualified_name: r.qualified_name,
    group_id: r.group_id
})
MERGE (symbol)-[:BACKED_BY_SYMBOL]->(shadow)
"""

_EDGE_QUERIES: dict[str, str] = {
    "REFERENCES": _MERGE_REFERENCES,
    "CONFORMS_TO": _MERGE_CONFORMS_TO,
    "EXTENDS": _MERGE_EXTENDS,
    "EXTENSION_OF": _MERGE_EXTENSION_OF,
}


def build_symbol_node_rows(
    symbol_infos: list["ScipSymbolInfo"],
    def_file_paths: dict[str, str],
    group_id: str,
    *,
    recipe: "Recipe | None" = None,
) -> list[dict[str, Any]]:
    """Build the UNWIND row dicts for :Symbol MERGE from ScipSymbolInfo list.

    Exported so tests can inspect the exact payload without a live Neo4j.
    """
    rows: list[dict[str, Any]] = []
    for si in symbol_infos:
        file_path = def_file_paths.get(si.qualified_name)
        source_scope: str | None = None
        if file_path is not None:
            result = classify_source_scope(file_path, recipe=recipe)
            source_scope = result.scope.value
        kind = canonical_symbol_kind(si.scip_kind_name)
        rows.append(
            {
                "qualified_name": si.qualified_name,
                "group_id": group_id,
                "kind": kind or "unknown",
                "label": canonical_symbol_label(kind or si.scip_kind_name),
                "short_name": canonical_symbol_short_name(si.qualified_name),
                "file_path": file_path,
                "module_name": si.module_name or None,
                "source_scope": source_scope,
            }
        )
    return rows


def build_symbol_shadow_rows(
    symbol_infos: list["ScipSymbolInfo"],
    group_id: str,
) -> list[dict[str, str]]:
    """Build Symbol→shadow link rows for non-callable SCIP kinds."""
    rows: list[dict[str, str]] = []
    seen_qnames: set[str] = set()
    for si in symbol_infos:
        if si.scip_kind_name not in _SCIP_KINDS_WITH_SHADOW_BACKING:
            continue
        if si.qualified_name in seen_qnames:
            continue
        seen_qnames.add(si.qualified_name)
        rows.append(
            {
                "qualified_name": si.qualified_name,
                "group_id": group_id,
            }
        )
    return rows


async def write_symbol_nodes(
    driver: "AsyncDriver",
    symbol_infos: list["ScipSymbolInfo"],
    def_file_paths: dict[str, str],
    group_id: str,
    *,
    project_id: str,
    run_id: str,
    seen_at: datetime,
    commit_sha: str,
    recipe: "Recipe | None" = None,
) -> int:
    """Write :Symbol nodes and edges to Neo4j in UNWIND batches.

    Returns the number of symbol infos processed (may be 0 when the SCIP
    file carries no SymbolInformation, e.g. older emitter versions).
    """
    if not symbol_infos:
        return 0

    node_rows = build_symbol_node_rows(
        symbol_infos, def_file_paths, group_id, recipe=recipe
    )

    async with driver.session() as session:
        for i in range(0, len(node_rows), _BATCH_SIZE):
            await session.run(
                _MERGE_SYMBOLS,
                rows=node_rows[i : i + _BATCH_SIZE],
                project_id=project_id,
                run_id=run_id,
                seen_at=seen_at.isoformat(),
                commit_sha=commit_sha,
            )

    shadow_rows = build_symbol_shadow_rows(symbol_infos, group_id)
    async with driver.session() as session:
        for i in range(0, len(shadow_rows), _BATCH_SIZE):
            await session.run(
                _MERGE_BACKED_BY_SYMBOL_SHADOWS,
                rows=shadow_rows[i : i + _BATCH_SIZE],
            )

    edges_by_type: dict[str, list[dict[str, str]]] = {k: [] for k in _EDGE_QUERIES}
    for si in symbol_infos:
        for target_qname, rel_type in si.relationships:
            if rel_type in edges_by_type:
                edges_by_type[rel_type].append(
                    {
                        "source": si.qualified_name,
                        "target": target_qname,
                        "group_id": group_id,
                    }
                )

    async with driver.session() as session:
        for rel_type, edge_rows in edges_by_type.items():
            cypher = _EDGE_QUERIES[rel_type]
            for i in range(0, len(edge_rows), _BATCH_SIZE):
                await session.run(cypher, rows=edge_rows[i : i + _BATCH_SIZE])

    return len(node_rows)


async def soft_delete_symbols(
    driver: "AsyncDriver",
    group_id: str,
    seen_qnames: set[str],
    now: datetime,
) -> int:
    """Mark :Symbol nodes absent from the new SCIP as soft-deleted.

    Nodes whose qualified_name appears in seen_qnames have already had
    deleted_at cleared by the MERGE in write_symbol_nodes. This function
    stamps deleted_at on the remainder.

    Returns the count of nodes newly stamped.
    """
    async with driver.session() as session:
        result = await session.run(
            _SOFT_DELETE_ABSENT,
            group_id=group_id,
            qnames=list(seen_qnames),
            now=now,
        )
        summary = await result.consume()
        return summary.counters.properties_set
