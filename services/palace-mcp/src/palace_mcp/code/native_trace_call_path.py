"""Native trace_call_path implementation for Palace-known projects."""

from __future__ import annotations

from typing import Any, cast

from palace_mcp.code.edges import CALL_EDGES
from palace_mcp.code.native_detect_changes import FALLBACK_TO_CM

_MIN_DEPTH = 1
_MAX_DEPTH = 6
_PATH_LIMIT = 5000
_VALID_DIRECTIONS = frozenset({"inbound", "outbound", "both"})
_PHASE2_MODES = frozenset({"data_flow", "cross_service"})


def _error(
    code: str,
    message: str,
    *,
    project: str | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": False, "error_code": code, "message": message}
    if project is not None:
        result["project"] = project
    if mode is not None:
        result["mode"] = mode
    return result


def _phase2_required(project: str, mode: str) -> dict[str, Any]:
    return _error(
        "phase2_required",
        f"native palace.code.trace_call_path does not support mode={mode!r} in this slice",
        project=project,
        mode=mode,
    )


def _clamp_depth(depth: int) -> tuple[int, int | None]:
    clamped = min(max(depth, _MIN_DEPTH), _MAX_DEPTH)
    return clamped, clamped if clamped != depth else None


def _relationship_alternation() -> str:
    return "|".join(sorted(CALL_EDGES))


def _path_query(direction: str, depth: int) -> str:
    relationship_types = _relationship_alternation()
    path_pattern = {
        "outbound": f"(root:Symbol)-[:{relationship_types}*1..{depth}]->(target:Symbol)",
        "inbound": f"(root:Symbol)<-[:{relationship_types}*1..{depth}]-(target:Symbol)",
    }[direction]
    return f"""
MATCH path = {path_pattern}
WHERE root.group_id = $group_id
  AND target.group_id = $group_id
  AND ($include_deprecated OR all(node IN nodes(path) WHERE NOT node:Deprecated))
  AND (
    root.qualified_name = $function_name
    OR coalesce(root.short_name, '') = $function_name
    OR coalesce(root.name, '') = $function_name
    OR last(split(coalesce(root.qualified_name, ''), '.')) = $function_name
  )
RETURN
  [node IN nodes(path) | {{
    qualified_name: coalesce(node.qualified_name, ''),
    name: coalesce(
      node.short_name,
      node.name,
      last(split(coalesce(node.qualified_name, ''), '.'))
    ),
    file_path: coalesce(node.file_path, node.path, ''),
    kind: coalesce(node.kind, ''),
    is_test: coalesce(node.is_test, false)
  }}] AS path_nodes,
  [edge IN relationships(path) | {{
    source: coalesce(startNode(edge).qualified_name, ''),
    target: coalesce(endNode(edge).qualified_name, ''),
    type: type(edge)
  }}] AS path_edges,
  length(path) AS hop
ORDER BY hop,
         coalesce(target.qualified_name, ''),
         coalesce(root.qualified_name, '')
LIMIT $limit
""".strip()


async def _rows(session: Any, query: str, **params: Any) -> list[dict[str, Any]]:
    result = await session.run(query, **params)
    return cast(list[dict[str, Any]], await result.data())


def _looks_like_test(name: str, file_path: str) -> bool:
    lowered_name = name.lower()
    if lowered_name.startswith("test_") or lowered_name.endswith("_test"):
        return True
    parts = [part for part in file_path.lower().split("/") if part]
    return any(part in {"test", "tests"} or part.endswith("tests") for part in parts)


def _node_payload(raw: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "qualified_name": str(raw.get("qualified_name") or ""),
        "name": str(raw.get("name") or ""),
        "file_path": str(raw.get("file_path") or ""),
        "kind": str(raw.get("kind") or ""),
    }
    if bool(raw.get("is_test")) or _looks_like_test(
        payload["name"], payload["file_path"]
    ):
        payload["is_test"] = True
    return payload


def _sorted_endpoints(
    endpoints: dict[str, tuple[int, dict[str, Any]]],
) -> list[dict[str, Any]]:
    return [
        payload
        for _, payload in sorted(
            endpoints.values(),
            key=lambda item: (item[0], str(item[1]["qualified_name"])),
        )
    ]


async def native_trace_call_path(
    function_name: str,
    project: str | None = None,
    direction: str = "both",
    depth: int = 3,
    mode: str = "calls",
    include_tests: bool = False,
    include_deprecated: bool = False,
    **_: Any,
) -> dict[str, Any] | object:
    if project is None:
        return FALLBACK_TO_CM
    requested_name = function_name.strip()
    if not requested_name:
        return _error(
            "validation_error",
            "function_name is required",
            project=project,
            mode=mode,
        )
    if mode in _PHASE2_MODES:
        return _phase2_required(project, mode)
    if mode != "calls":
        return _error(
            "validation_error",
            f"unsupported mode: {mode!r}",
            project=project,
            mode=mode,
        )
    if direction not in _VALID_DIRECTIONS:
        return _error(
            "validation_error",
            f"unsupported direction: {direction!r}",
            project=project,
            mode=mode,
        )
    if isinstance(depth, bool) or not isinstance(depth, int):
        return _error(
            "validation_error",
            "depth must be an integer",
            project=project,
            mode=mode,
        )

    from palace_mcp.mcp_server import get_driver

    driver = get_driver()
    if driver is None:
        return _error(
            "neo4j_unavailable",
            "Neo4j driver not initialised",
            project=project,
            mode=mode,
        )

    effective_depth, clamped_depth = _clamp_depth(depth)
    directions = ["inbound", "outbound"] if direction == "both" else [direction]
    node_index: dict[str, dict[str, Any]] = {}
    edge_index: dict[tuple[str, str, str], dict[str, str]] = {}
    callers: dict[str, tuple[int, dict[str, Any]]] = {}
    callees: dict[str, tuple[int, dict[str, Any]]] = {}
    remaining = _PATH_LIMIT

    try:
        async with driver.session() as session:
            for current_direction in directions:
                if remaining <= 0:
                    break
                rows = await _rows(
                    session,
                    _path_query(current_direction, effective_depth),
                    group_id=f"project/{project}",
                    function_name=requested_name,
                    include_deprecated=include_deprecated,
                    limit=remaining,
                )
                remaining -= len(rows)
                for row in rows:
                    hop = int(row.get("hop") or 0)
                    path_nodes = cast(list[dict[str, Any]], row.get("path_nodes") or [])
                    path_edges = cast(list[dict[str, Any]], row.get("path_edges") or [])
                    normalized_nodes = [_node_payload(node) for node in path_nodes]
                    for node in normalized_nodes:
                        qualified_name = str(node["qualified_name"])
                        if qualified_name and qualified_name not in node_index:
                            node_index[qualified_name] = node
                    for edge in path_edges:
                        source = str(edge.get("source") or "")
                        target = str(edge.get("target") or "")
                        edge_type = str(edge.get("type") or "")
                        if source and target and edge_type:
                            edge_index[(source, target, edge_type)] = {
                                "source": source,
                                "target": target,
                                "type": edge_type,
                            }
                    if not normalized_nodes:
                        continue
                    endpoint = dict(normalized_nodes[-1])
                    if endpoint.get("is_test") and not include_tests:
                        continue
                    endpoint["hop"] = hop
                    qualified_name = str(endpoint["qualified_name"])
                    if not qualified_name:
                        continue
                    bucket = callers if current_direction == "inbound" else callees
                    existing = bucket.get(qualified_name)
                    if existing is None or hop < existing[0]:
                        bucket[qualified_name] = (hop, endpoint)
    except Exception as exc:  # noqa: BLE001
        return _error(
            "cypher_error",
            f"trace_call_path query failed: {exc}",
            project=project,
            mode=mode,
        )

    result: dict[str, Any] = {
        "function": requested_name,
        "project": project,
        "direction": direction,
        "mode": mode,
        "nodes": [node_index[key] for key in sorted(node_index)],
        "edges": [
            edge_index[key]
            for key in sorted(
                edge_index,
                key=lambda item: (item[0], item[1], item[2]),
            )
        ],
    }
    if clamped_depth is not None:
        result["clamped_depth"] = clamped_depth
    if direction in {"inbound", "both"}:
        result["callers"] = _sorted_endpoints(callers)
    if direction in {"outbound", "both"}:
        result["callees"] = _sorted_endpoints(callees)
    return result
