"""Batch-write SCIP-derived :Symbol nodes and edges to Neo4j.

Used by symbol_index_swift (and future SCIP-based extractors) to materialise
the call/reference graph needed by dead_code.graph_loader.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from palace_mcp.extractors.scip_parser import ScipSymbolInfo

_SCIP_KIND_TO_STR: dict[str, str] = {
    "Class": "class",
    "Struct": "struct",
    "Enum": "enum",
    "Protocol": "protocol",
    "Interface": "protocol",
    "Trait": "protocol",
    "Extension": "extension",
    "Function": "function",
    "Method": "function",
    "AbstractMethod": "function",
    "ProtocolMethod": "function",
    "Constructor": "function",
    "Getter": "function",
    "Setter": "function",
    "Accessor": "function",
    "Subscript": "function",
    "StaticMethod": "function",
    "PureVirtualMethod": "function",
    "TraitMethod": "function",
    "Property": "property",
    "Field": "property",
    "EnumMember": "property",
    "Variable": "property",
    "StaticProperty": "property",
    "StaticField": "property",
    "StaticVariable": "property",
    "TypeAlias": "typealias",
    "AssociatedType": "typealias",
}

_BATCH_SIZE = 500

# MERGE with explicit property initialisation so dead_code.graph_loader
# never reads null for the boolean columns it expects.
_MERGE_SYMBOLS = """
UNWIND $rows AS r
MERGE (s:Symbol {qualified_name: r.qualified_name, group_id: r.group_id})
SET s.kind            = r.kind,
    s.file_path       = r.file_path,
    s.module_name     = r.module_name,
    s.access_modifier = '',
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
    s.referenced_via_mirror  = false
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
) -> list[dict[str, Any]]:
    """Build the UNWIND row dicts for :Symbol MERGE from ScipSymbolInfo list.

    Exported so tests can inspect the exact payload without a live Neo4j.
    """
    return [
        {
            "qualified_name": si.qualified_name,
            "group_id": group_id,
            "kind": _SCIP_KIND_TO_STR.get(si.scip_kind_name, "unknown"),
            "file_path": def_file_paths.get(si.qualified_name),
            "module_name": si.module_name or None,
        }
        for si in symbol_infos
    ]


async def write_symbol_nodes(
    driver: "AsyncDriver",
    symbol_infos: list["ScipSymbolInfo"],
    def_file_paths: dict[str, str],
    group_id: str,
) -> int:
    """Write :Symbol nodes and edges to Neo4j in UNWIND batches.

    Returns the number of symbol infos processed (may be 0 when the SCIP
    file carries no SymbolInformation, e.g. older emitter versions).
    """
    if not symbol_infos:
        return 0

    node_rows = build_symbol_node_rows(symbol_infos, def_file_paths, group_id)

    async with driver.session() as session:
        for i in range(0, len(node_rows), _BATCH_SIZE):
            await session.run(_MERGE_SYMBOLS, rows=node_rows[i : i + _BATCH_SIZE])

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
