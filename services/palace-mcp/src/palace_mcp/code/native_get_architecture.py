"""Native get_architecture implementation for Palace-known projects."""

from __future__ import annotations

from typing import Any, cast

from palace_mcp.code.native_detect_changes import FALLBACK_TO_CM

_ROUTE_PHASE2_NOTE = (
    "routes require Phase 2 extractor support; native get_architecture returns []"
)

_FILE_LANGUAGES_QUERY = """
MATCH (f:File {project_id: $project_id})
WHERE f.language IS NOT NULL AND trim(toString(f.language)) <> ''
RETURN DISTINCT toLower(toString(f.language)) AS language
ORDER BY language
"""

_MODULES_QUERY = """
MATCH (m:Module {project_id: $project_id})
RETURN
    m.slug AS slug,
    m.name AS name,
    m.kind AS kind,
    m.manifest_path AS manifest_path,
    m.source_root AS source_root
ORDER BY m.slug, m.name
"""

_SYMBOL_MODULES_QUERY = """
MATCH (s:Symbol {group_id: $group_id})
WHERE s.module_name IS NOT NULL AND trim(toString(s.module_name)) <> ''
RETURN DISTINCT toString(s.module_name) AS module_name
ORDER BY module_name
"""

_DEPENDENCIES_QUERY = """
MATCH (:Project {slug: $project})-[r:DEPENDS_ON]->(d:ExternalDependency)
RETURN
    d.purl AS purl,
    d.ecosystem AS ecosystem,
    d.resolved_version AS resolved_version,
    r.scope AS scope,
    r.declared_in AS declared_in,
    r.declared_version_constraint AS declared_version_constraint
ORDER BY d.purl, r.scope, r.declared_in
"""

_ENTRY_POINTS_QUERY = """
MATCH (s:Symbol {group_id: $group_id})
WHERE coalesce(s.is_main_entry, false) = true
RETURN
    s.qualified_name AS qualified_name,
    s.file_path AS file_path,
    s.module_name AS module_name,
    s.kind AS kind
ORDER BY s.qualified_name
"""

_LAYERS_QUERY = """
MATCH (l:Layer {project_id: $project_id})
WHERE coalesce(l.summary, false) = false
RETURN
    l.name AS name,
    l.rule_source AS rule_source
ORDER BY l.name
"""

_EDGE_TYPES_QUERY = """
MATCH (a:Symbol {group_id: $group_id})-[r]->(b:Symbol {group_id: $group_id})
RETURN DISTINCT type(r) AS type
UNION
MATCH (:Module {project_id: $project_id})-[r:MODULE_DEPENDS_ON]->(:Module {
    project_id: $project_id
})
RETURN DISTINCT type(r) AS type
UNION
MATCH (:Project {slug: $project})-[r:DEPENDS_ON]->(:ExternalDependency)
RETURN DISTINCT type(r) AS type
"""


def _error(code: str, message: str, *, project: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": False, "error_code": code, "message": message}
    if project is not None:
        result["project"] = project
    return result


async def _rows(session: Any, query: str, **params: Any) -> list[dict[str, Any]]:
    result = await session.run(query, **params)
    return cast(list[dict[str, Any]], await result.data())


def _build_packages(
    module_rows: list[dict[str, Any]],
    symbol_module_rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    packages: list[dict[str, str]] = []
    seen: set[str] = set()

    for row in module_rows:
        name = str(row.get("name") or row.get("slug") or "").strip()
        if not name:
            continue
        slug = str(row.get("slug") or name).strip()
        key = slug or name
        if key in seen:
            continue
        seen.add(key)
        packages.append(
            {
                "name": name,
                "slug": slug,
                "kind": str(row.get("kind") or ""),
                "manifest_path": str(row.get("manifest_path") or ""),
                "source_root": str(row.get("source_root") or ""),
            }
        )

    for row in symbol_module_rows:
        name = str(row.get("module_name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        packages.append(
            {
                "name": name,
                "slug": name,
                "kind": "",
                "manifest_path": "",
                "source_root": "",
            }
        )

    return packages


def _build_dependencies(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    dependencies: list[dict[str, str]] = []
    for row in rows:
        purl = str(row.get("purl") or "").strip()
        if not purl:
            continue
        dependencies.append(
            {
                "purl": purl,
                "ecosystem": str(row.get("ecosystem") or ""),
                "resolved_version": str(row.get("resolved_version") or ""),
                "scope": str(row.get("scope") or ""),
                "declared_in": str(row.get("declared_in") or ""),
                "declared_version_constraint": str(
                    row.get("declared_version_constraint") or ""
                ),
            }
        )
    return dependencies


def _build_entry_points(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    entry_points: list[dict[str, str]] = []
    for row in rows:
        qualified_name = str(row.get("qualified_name") or "").strip()
        if not qualified_name:
            continue
        entry_points.append(
            {
                "qualified_name": qualified_name,
                "file_path": str(row.get("file_path") or ""),
                "module_name": str(row.get("module_name") or ""),
                "kind": str(row.get("kind") or ""),
            }
        )
    return entry_points


def _build_layers(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    layers: list[dict[str, str]] = []
    for row in rows:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        layers.append(
            {
                "name": name,
                "rule_source": str(row.get("rule_source") or ""),
            }
        )
    return layers


def _build_edge_types(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    edge_types = sorted(
        {
            str(row.get("type") or "").strip()
            for row in rows
            if str(row.get("type") or "").strip()
        }
    )
    return [{"type": edge_type} for edge_type in edge_types]


async def native_get_architecture(
    project: str | None = None,
    **_: Any,
) -> dict[str, Any] | object:
    if project is None:
        return FALLBACK_TO_CM

    from palace_mcp.mcp_server import get_driver

    driver = get_driver()
    if driver is None:
        return _error(
            "neo4j_unavailable",
            "Neo4j driver not initialised",
            project=project,
        )

    project_id = f"project/{project}"
    try:
        async with driver.session() as session:
            file_rows = await _rows(
                session, _FILE_LANGUAGES_QUERY, project_id=project_id
            )
            module_rows = await _rows(session, _MODULES_QUERY, project_id=project_id)
            symbol_module_rows = await _rows(
                session, _SYMBOL_MODULES_QUERY, group_id=project_id
            )
            dependency_rows = await _rows(session, _DEPENDENCIES_QUERY, project=project)
            entry_point_rows = await _rows(
                session, _ENTRY_POINTS_QUERY, group_id=project_id
            )
            layer_rows = await _rows(session, _LAYERS_QUERY, project_id=project_id)
            edge_type_rows = await _rows(
                session,
                _EDGE_TYPES_QUERY,
                group_id=project_id,
                project_id=project_id,
                project=project,
            )
    except Exception:  # noqa: BLE001
        return _error("cypher_error", "get_architecture query failed", project=project)

    return {
        "project": project,
        "languages": sorted(
            {
                str(row.get("language") or "").strip()
                for row in file_rows
                if str(row.get("language") or "").strip()
            }
        ),
        "packages": _build_packages(module_rows, symbol_module_rows),
        "dependencies": _build_dependencies(dependency_rows),
        "entry_points": _build_entry_points(entry_point_rows),
        "routes": [],
        "route_note": _ROUTE_PHASE2_NOTE,
        "hotspots": [],
        "boundaries": [],
        "layers": _build_layers(layer_rows),
        "clusters": [],
        "edge_types": _build_edge_types(edge_type_rows),
    }
