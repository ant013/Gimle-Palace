"""Load SCIP symbol graph from Neo4j into in-memory SymbolGraph."""

from __future__ import annotations

from typing import Any

from neo4j import AsyncDriver

from palace_mcp.extractors.dead_code.models import GraphEdge, SymbolGraph, SymbolNode

# Query the codebase-memory-populated Symbol nodes.
# Falls back gracefully to empty if nodes don't exist.
_LOAD_SYMBOLS = """
MATCH (s:Symbol {group_id: $group_id})
WHERE s.deleted_at IS NULL
  AND NOT s:Deprecated
RETURN
    s.qualified_name AS qualified_name,
    s.kind AS kind,
    s.file_path AS file_path,
    s.module_name AS module_name,
    s.access_modifier AS access_modifier,
    s.is_objc AS is_objc,
    s.is_dynamic AS is_dynamic,
    s.is_objc_members AS is_objc_members,
    s.is_ns_managed AS is_ns_managed,
    s.is_property_wrapper AS is_property_wrapper,
    s.is_codable AS is_codable,
    s.is_iboutlet AS is_iboutlet,
    s.is_ibaction AS is_ibaction,
    s.is_swift_app_storage AS is_swift_app_storage,
    s.is_env_key AS is_env_key,
    s.is_main_entry AS is_main_entry,
    s.referenced_via_mirror AS referenced_via_mirror,
    s.extends_protocol AS extends_protocol
"""

_LOAD_EDGES = """
MATCH (a:Symbol {group_id: $group_id})-[r:CALLS|REFERENCES|EXTENDS|CONFORMS_TO|EXTENSION_OF|EXISTENTIAL_USE]->(b:Symbol {group_id: $group_id})
WHERE a.deleted_at IS NULL
  AND NOT a:Deprecated
  AND b.deleted_at IS NULL
  AND NOT b:Deprecated
RETURN a.qualified_name AS source, b.qualified_name AS target, type(r) AS kind
"""


async def load_symbol_graph(
    driver: AsyncDriver,
    group_id: str,
) -> SymbolGraph:
    """Load all Symbol nodes and edges for group_id into SymbolGraph."""
    graph = SymbolGraph()

    async with driver.session() as session:
        result = await session.run(_LOAD_SYMBOLS, group_id=group_id)
        rows = await result.data()

    for row in rows:
        qn = row.get("qualified_name")
        if not qn:
            continue
        graph.symbols[qn] = _row_to_symbol(row)

    async with driver.session() as session:
        result = await session.run(_LOAD_EDGES, group_id=group_id)
        edge_rows = await result.data()

    for row in edge_rows:
        src = row.get("source")
        tgt = row.get("target")
        kind = row.get("kind")
        if src and tgt and kind:
            graph.edges.append(GraphEdge(source=src, target=tgt, kind=kind))

    graph.build_indexes()
    return graph


def _row_to_symbol(row: dict[str, Any]) -> SymbolNode:
    access = row.get("access_modifier") or ""
    return SymbolNode(
        qualified_name=str(row["qualified_name"]),
        kind=str(row.get("kind") or "unknown"),
        file_path=row.get("file_path"),
        module_name=row.get("module_name"),
        is_public=access in ("public", "open"),
        is_open=access == "open",
        is_objc=bool(row.get("is_objc")),
        is_dynamic=bool(row.get("is_dynamic")),
        is_objc_members=bool(row.get("is_objc_members")),
        is_ns_managed=bool(row.get("is_ns_managed")),
        is_property_wrapper=bool(row.get("is_property_wrapper")),
        is_codable=bool(row.get("is_codable")),
        is_iboutlet=bool(row.get("is_iboutlet")),
        is_ibaction=bool(row.get("is_ibaction")),
        is_swift_app_storage=bool(row.get("is_swift_app_storage")),
        is_env_key=bool(row.get("is_env_key")),
        is_main_entry=bool(row.get("is_main_entry")),
        referenced_via_mirror=bool(row.get("referenced_via_mirror")),
        extends_protocol=row.get("extends_protocol"),
    )


async def load_git_history(
    driver: AsyncDriver,
    project: str,
    qualified_names: list[str],
) -> dict[str, dict[str, Any]]:
    """Load git_history enrichment data for a set of qualified names.

    Returns dict mapping qualified_name → {days_ago, has_external_refs, churn_count}.
    Missing entries are silently omitted — caller uses defaults.
    """
    if not qualified_names:
        return {}
    # TODO(GIM-787): wire to git_history extractor output
    # Joining qualified_name → File node requires Symbol.file_path → File path match.
    # Deferred to a future slice; return empty so caller uses score defaults.
    return {}
